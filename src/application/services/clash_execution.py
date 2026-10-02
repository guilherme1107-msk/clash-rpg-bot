"""Execução autoritativa de Clash, usada somente pelo processo do bot."""
from __future__ import annotations
import os

from src.domain.combat import Modifiers, Skill, clamp_sp, prediction_with_paralysis, resolve_clash, resolve_damage
from src.application.services.core_gateway import commit_database_event


def execute_clash_job(database, request: dict, effects: dict | None = None) -> dict:
    """Rola um Clash com os efeitos de Skill injetados nos momentos certos.

    ``effects`` vem do chamador (o bot) porque a sequência de efeitos vive no
    bot e este módulo não pode importá-lo. São três gatilhos, cada um
    devolvendo ``(efeitos_de_skill, efeitos_de_dano)``:

    - ``on_round_start(esquerda, direita)`` — antes das moedas. É aqui que o
      ``on_use`` roda, para que os mods que ele escrever entram de verdade na
      previsão e na rolagem (antes ele rodava depois do dano e era só registro).
    - ``on_before_damage(ctx)`` — já com o vencedor, antes do dano. Clã,
      ``before_attack`` e Bleed entram aqui.
    - ``on_after_damage(ctx)`` — na resolução do dano: dano %, Poise, críticos,
      status do acerto e ``after_attack``.

    Os "efeitos de dano" são o cálculo separado que a Activity mostra embaixo
    de ``〔 DANO FINAL 〕``; os de skill ficam no campo de efeitos normal.
    """
    guild_id = int(request["guild_id"]); user_id = int(request["user_id"])
    target_kind = str(request["target_kind"]); target_id = int(request["target_id"])
    connection = database.connection
    skill_effects: list[str] = []
    damage_effects: list[str] = []

    def fire(stage: str, *args) -> None:
        hook = (effects or {}).get(stage)
        if hook is None:
            return
        before, after = hook(*args)
        skill_effects.extend(before)
        damage_effects.extend(after)

    def reload_left():
        return connection.execute(
            "SELECT * FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        ).fetchone()

    def reload_right():
        if target_kind == "enemy_group_member":
            return database.get_enemy_group_member_combatant(guild_id, target_id)
        if target_kind == "enemy":
            return connection.execute("SELECT * FROM enemies WHERE id=?", (target_id,)).fetchone()
        return connection.execute("SELECT * FROM characters WHERE user_id=?", (target_id,)).fetchone()

    left_row = connection.execute("SELECT * FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
    if left_row is None:
        left_row = connection.execute("SELECT * FROM characters WHERE user_id=? ORDER BY guild_id DESC", (user_id,)).fetchone()
        if left_row: guild_id = int(left_row["guild_id"])
    left = database.get_skill(guild_id, user_id, str(request["left_skill"]))
    if target_kind == "enemy":
        right_row = connection.execute("SELECT * FROM enemies WHERE id=?", (target_id,)).fetchone()
        right = None if right_row is None else database.get_enemy_skill(target_id, str(request["right_skill"]))
    elif target_kind == "enemy_group_member":
        right_row = database.get_enemy_group_member_combatant(guild_id, target_id)
        right = None if right_row is None else database.get_enemy_skill(int(right_row["id"]), str(request["right_skill"]))
    else:
        right_row = connection.execute("SELECT * FROM characters WHERE user_id=?", (target_id,)).fetchone()
        right = None if right_row is None else database.get_skill(int(right_row["guild_id"]), target_id, str(request["right_skill"]))
    if left_row is None or left is None or right_row is None or right is None:
        raise ValueError("Uma ficha ou Skill escolhida não existe mais.")

    left_side = {"kind": "player", "id": user_id, "name": left_row["name"], "skill": left}
    right_side = {"kind": target_kind, "id": target_id, "name": right_row["name"], "skill": right}

    # 1) on_use de cada lado ANTES das moedas — é o que faz o efeito valer.
    fire("on_round_start", left_side, right_side)
    left_row = reload_left() or left_row
    right_row = reload_right() or right_row

    left_ego = database.get_total_ego_gift_modifiers(guild_id, "player", user_id)
    right_ego = database.get_total_ego_gift_modifiers(guild_id, target_kind, target_id)
    left_level = (left_row["defense_level"] + left_row["defense_level_mod"] + left_ego["defense_level_mod"] if left.uses_defense_level else left_row["offense_level"] + left_row["offense_level_mod"] + left_ego["offense_level_mod"])
    right_level = (right_row["defense_level"] + right_row["defense_level_mod"] + right_ego["defense_level_mod"] if right.uses_defense_level else right_row["offense_level"] + right_row["offense_level_mod"] + right_ego["offense_level_mod"])
    lm = Modifiers(left_row["base_power_mod"] + left_ego["base_power_mod"], left_row["coin_power_mod"] + left_ego["coin_power_mod"], left_row["paralysis"], left_level, left_row["clash_power_mod"] + left_ego["clash_power_mod"])
    rm = Modifiers(right_row["base_power_mod"] + right_ego["base_power_mod"], right_row["coin_power_mod"] + right_ego["coin_power_mod"], right_row["paralysis"], right_level, right_row["clash_power_mod"] + right_ego["clash_power_mod"])
    right_uses_sanity = target_kind not in {"enemy", "enemy_group_member"} or bool(right_row["uses_sanity"])
    forecast = prediction_with_paralysis(
        left, left_row["sp"], right, right_row["sp"] if right_uses_sanity else 0,
        left_modifiers=lm, right_modifiers=rm,
    )
    result = resolve_clash(left, left_row["sp"], right, right_row["sp"] if right_uses_sanity else 0, left_modifiers=lm, right_modifiers=rm)
    winner_skill = left if result.winner == "left" else right
    remaining = result.left_coins if result.winner == "left" else result.right_coins
    broken = result.left_broken_unbreakable if result.winner == "left" else result.right_broken_unbreakable
    winner_side = left_side if result.winner == "left" else right_side
    loser_side = right_side if result.winner == "left" else left_side

    # O Clash confirma SP, paralisia e o zera dos mods ANTES dos efeitos do
    # vencedor: assim o que eles escreverem sobreviva, como já acontecia no
    # comando do Discord. Os efeitos de rolagem do vencedor são consumidos
    # depois, em on_after_damage, pelo revert_temporary_self_trigger.
    left_sp_value = clamp_sp(left_row["sp"] + (5 if result.winner == "left" else -5))
    right_sp_value = clamp_sp(right_row["sp"] + (5 if result.winner == "right" else -5)) if right_uses_sanity else right_row["sp"]
    with connection:
        connection.execute("""UPDATE characters SET sp=?,paralysis=?,coin_power_mod=0,clash_power_mod=0,offense_level_mod=0,defense_level_mod=0 WHERE guild_id=? AND user_id=?""", (left_sp_value, result.left_paralysis, guild_id, user_id))
        if target_kind == "enemy_group_member":
            database.update_enemy_group_member_combat(guild_id, target_id, sp=right_sp_value, paralysis=result.right_paralysis)
            table, key = "enemy_group_members", "id"
        else:
            table, key = ("enemies", "id") if target_kind == "enemy" else ("characters", "user_id")
            connection.execute(f"""UPDATE {table} SET sp=?,paralysis=?,coin_power_mod=0,clash_power_mod=0,offense_level_mod=0,defense_level_mod=0 WHERE guild_id=? AND {key}=?""", (right_sp_value, result.right_paralysis, guild_id, target_id))
        left_core = commit_database_event(
            database, guild_id=guild_id, command="combat.clash_resolved", source="bot",
            entity_kind="character", entity_id=user_id,
            payload={"sp": left_sp_value, "opponent_kind": target_kind, "opponent_id": target_id},
        )
        right_core = commit_database_event(
            database, guild_id=guild_id, command="combat.clash_resolved", source="bot",
            entity_kind=target_kind, entity_id=target_id,
            payload={"sp": right_sp_value, "opponent_kind": "character", "opponent_id": user_id},
        )

    # 2) vencedor já conhecido: clã, Bleed e before_attack rodam aqui, para que
    #    entrem no dano em vez de virarem só registro depois dele.
    fire("on_before_damage", {
        "left": left_side, "right": right_side, "result": result,
        "attacker": winner_side, "defender": loser_side,
        "attacker_skill": winner_skill, "attacker_coins": remaining,
    })
    left_row = reload_left() or left_row
    right_row = reload_right() or right_row
    winner_row = left_row if result.winner == "left" else right_row
    loser_row = right_row if result.winner == "left" else left_row
    winner_sp = winner_row["sp"] if result.winner == "left" or right_uses_sanity else 0

    # P9 (decisão 7 do autor): o gift entra **no Clash e no dano**. Antes ele
    # contava só no Clash (linhas 80-83) e ficava de fora de `resolve_damage`,
    # então um E.G.O Gift com Base/Offense/Defense não mudava dano nenhum.
    # Não é dupla contagem: as linhas 103/109 zeram os `*_mod` da ficha no
    # momento do Clash, e os mods do gift vivem em `ego_gifts` (persistentes)
    # mais o que `get_total_ego_gift_modifiers` tira do Glimpse.
    winner_ego = left_ego if result.winner == "left" else right_ego
    loser_ego = right_ego if result.winner == "left" else left_ego

    damage_result = resolve_damage(
        winner_skill, winner_sp, remaining,
        winner_row["offense_level"] + winner_row["offense_level_mod"] + winner_ego["offense_level_mod"],
        loser_row["defense_level"] + loser_row["defense_level_mod"] + loser_ego["defense_level_mod"],
        modifiers=Modifiers(
            winner_row["base_power_mod"] + winner_ego["base_power_mod"],
            winner_row["coin_power_mod"] + winner_ego["coin_power_mod"],
            result.left_paralysis if result.winner == "left" else result.right_paralysis,
        ),
        broken_unbreakable=broken,
    ) if winner_skill.deals_damage else None
    damage = damage_result.final_damage if damage_result else 0
    losing_skill = right if result.winner == "left" else left
    cracked = result.right_broken_unbreakable if result.winner == "left" else result.left_broken_unbreakable
    followup_damage = 0
    followup_attacker = followup_target = ""
    if winner_skill.deals_damage and losing_skill.deals_damage and cracked > 0:
        followup_row = right_row if result.winner == "left" else left_row
        followup_target_row = left_row if result.winner == "left" else right_row
        followup_sp = (right_row["sp"] if right_uses_sanity else 0) if result.winner == "left" else left_row["sp"]
        cracked_skill = Skill(
            losing_skill.name, losing_skill.base_power, -1 if losing_skill.coin_power < 0 else 1,
            cracked, losing_skill.description, losing_skill.skill_type, cracked,
        )
        # O follow-up é disparado pelo PERDEDOR: os mods do gift dele vêm de
        # `loser_ego`, e os do alvo (o vencedor) de `winner_ego`.
        followup_damage = resolve_damage(
            cracked_skill, followup_sp, cracked,
            followup_row["offense_level"] + followup_row["offense_level_mod"] + loser_ego["offense_level_mod"],
            followup_target_row["defense_level"] + followup_target_row["defense_level_mod"] + winner_ego["defense_level_mod"],
            modifiers=Modifiers(
                followup_row["base_power_mod"] + loser_ego["base_power_mod"],
                followup_row["coin_power_mod"] + loser_ego["coin_power_mod"],
                result.right_paralysis if result.winner == "left" else result.left_paralysis,
            ),
        ).final_damage
        followup_attacker = followup_row["name"]
        followup_target = followup_target_row["name"]

    # HP: só o integrante de grupo tem coluna. Os demais ficam para P4.
    if damage > 0 and result.winner == "left":
        if target_kind == "enemy_group_member":
            current_member = database.get_enemy_group_member_combatant(guild_id, target_id)
            new_hp = max(0, int(current_member.get("hp", 0)) - damage)
            database.update_enemy_group_member(guild_id, target_id, {"hp": new_hp})
        elif "hp" in loser_row:
            new_hp = max(0, int(loser_row["hp"]) - damage)
            connection.execute(f"UPDATE {table} SET hp=? WHERE guild_id=? AND {key}=?", (new_hp, guild_id, target_id))

    if loser_side["kind"] in {"enemy", "enemy_group_member"}:
        try:
            defender_sanity = loser_row["sp"] if loser_row["uses_sanity"] else None
        except (KeyError, IndexError):
            defender_sanity = None
    else:
        defender_sanity = loser_row["sp"]

    # 3) resolução do dano: dano %, Poise, críticos, status do acerto e
    #    after_attack. Sai em "damage_effects", separado do dano final.
    fire("on_after_damage", {
        "left": left_side, "right": right_side, "result": result,
        "attacker": winner_side, "defender": loser_side,
        "attacker_skill": winner_skill, "attacker_coins": remaining,
        "damage": damage_result, "defender_sanity": defender_sanity,
    })

    # O resultado público usa os valores confirmados pelo banco, não apenas o
    # cálculo em memória. Isso mantém embed e Activity na mesma fonte.
    left_sp = int(connection.execute(
        "SELECT sp FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id),
    ).fetchone()["sp"])
    if target_kind == "enemy_group_member":
        right_sp = int(database.get_enemy_group_member_combatant(guild_id, target_id)["sp"])
    else:
        right_sp = int(connection.execute(
            f"SELECT sp FROM {table} WHERE guild_id=? AND {key}=?", (guild_id, target_id),
        ).fetchone()["sp"])
    return {
        "winner":result.winner, "winner_name":left_row["name"] if result.winner == "left" else right_row["name"],
        "damage":damage, "left_name":left_row["name"], "right_name":right_row["name"],
        "left_skill":left.name, "right_skill":right.name, "left_sp":left_sp, "right_sp":right_sp,
        "core_trace":left_core["trace_id"], "left_version":left_core["version"], "right_version":right_core["version"],
        "left_total":left.coins, "right_total":right.coins,
        "left_base":left.base_power, "right_base":right.base_power,
        "left_coin_power":left.coin_power, "right_coin_power":right.coin_power,
        "left_level":left_level, "right_level":right_level,
        "left_base_mod":left_row["base_power_mod"], "right_base_mod":right_row["base_power_mod"],
        "left_coin_mod":left_row["coin_power_mod"], "right_coin_mod":right_row["coin_power_mod"],
        "left_clash_mod":left_row["clash_power_mod"], "right_clash_mod":right_row["clash_power_mod"],
        "left_range":list(left.range_with()), "right_range":list(right.range_with()),
        "forecast_chance":forecast.win_chance, "forecast_label":forecast.label, "forecast_label_pt":forecast.label_pt,
        "left_remaining":result.left_coins, "right_remaining":result.right_coins,
        "left_broken_unbreakable":result.left_broken_unbreakable,
        "right_broken_unbreakable":result.right_broken_unbreakable,
        "followup_damage":followup_damage, "followup_coins":cracked,
        "followup_attacker":followup_attacker, "followup_target":followup_target,
        "unbreakable_broken":bool(result.left_broken_unbreakable or result.right_broken_unbreakable),
        "winner_side":result.winner,
        "damage_hits":[] if damage_result is None else [{"coin":hit.coin,"face":hit.face,"power":hit.power,"paralyzed":hit.paralyzed,"unbreakable":hit.unbreakable,"active_unbreakable":hit.active_unbreakable} for hit in damage_result.hits],
        "rounds":[{"number":r.number,"left_power":r.left.power,"right_power":r.right.power,"left_faces":r.left.faces,"right_faces":r.right.faces,"left_unbreakable_broken":r.left_unbreakable_broken,"right_unbreakable_broken":r.right_unbreakable_broken,"result":r.result} for r in result.rounds],
        "effects":skill_effects, "damage_effects":damage_effects,
    }
