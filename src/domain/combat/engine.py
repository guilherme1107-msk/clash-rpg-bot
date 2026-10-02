"""Regras puras de rolagem, Clash, defesa, previsão e dano."""

from __future__ import annotations

import random

from src.domain.models import (
    AttackHit,
    ClashResult,
    ClashRound,
    DamageResult,
    DefenseResult,
    Forecast,
    Modifiers,
    Roll,
    Skill,
    heads_chance,
)


def forecast_label(chance: float) -> tuple[str, str]:
    if chance < 0.20:
        return "HOPELESS", "Sem esperança"
    if chance < 0.40:
        return "STRUGGLING", "Lutando"
    if chance < 0.60:
        return "NEUTRAL", "Neutro"
    if chance < 0.80:
        return "FAVORED", "Favorecido"
    return "DOMINATING", "Dominante"


def clashable_guard_values(result: ClashResult, left: Skill, right: Skill) -> tuple[int, int]:
    """Retorna ``(stagger_manual, escudo_na_derrota)`` da Clashable Guard."""
    if not result.rounds:
        return 0, 0
    final_round = result.rounds[-1]
    if result.winner == "left":
        winning_skill, losing_skill = left, right
        winner_power, loser_power = final_round.left.power, final_round.right.power
    else:
        winning_skill, losing_skill = right, left
        winner_power, loser_power = final_round.right.power, final_round.left.power
    stagger = (
        winner_power
        if winning_skill.skill_type == "clashable_guard" and losing_skill.deals_damage
        else 0
    )
    shield = loser_power if losing_skill.skill_type == "clashable_guard" and winning_skill.deals_damage else 0
    return max(0, stagger), max(0, shield)


def estimate_clash(
    left: Skill, left_sp: int, right: Skill, right_sp: int, *,
    left_modifiers: Modifiers | None = None,
    right_modifiers: Modifiers | None = None,
    simulations: int = 1000,
    rng: random.Random | None = None,
) -> Forecast:
    """Estima a vitória do lado esquerdo sem alterar o Clash real."""
    if simulations < 1:
        raise ValueError("simulations deve ser positivo")
    rng = rng or random.Random()
    lm, rm = left_modifiers or Modifiers(), right_modifiers or Modifiers()
    wins = 0
    for _ in range(simulations):
        result = resolve_clash(
            left, left_sp, right, right_sp, rng=rng,
            left_modifiers=Modifiers(lm.base_power, lm.coin_power, lm.paralysis, lm.level, lm.clash_power),
            right_modifiers=Modifiers(rm.base_power, rm.coin_power, rm.paralysis, rm.level, rm.clash_power),
        )
        wins += result.winner == "left"
    chance = wins / simulations
    label, label_pt = forecast_label(chance)
    return Forecast(chance, label, label_pt)


def prediction_with_paralysis(
    left: Skill, left_sp: int, right: Skill, right_sp: int,
    left_modifiers: Modifiers, right_modifiers: Modifiers, *,
    simulations: int = 50,
) -> Forecast:
    """Previsão de Clash compartilhada por bot e Activity.

    Viva em um único lugar para que as duas rotas nunca divirjam: antes o bot
    usava 5 simulações e a Activity 50, e só o bot tinha a regra de Paralisia.
    """
    if left_modifiers.paralysis > 0 and right_modifiers.paralysis == 0:
        return Forecast(0.0, "HOPELESS", "Sem esperança — Paralisia detectada")
    if right_modifiers.paralysis > 0 and left_modifiers.paralysis == 0:
        return Forecast(1.0, "DOMINATING", "Dominante — alvo com Paralisia")
    return estimate_clash(
        left, left_sp, right, right_sp,
        left_modifiers=left_modifiers, right_modifiers=right_modifiers,
        simulations=simulations,
    )


def resolve_defense(
    attack: Skill, attack_sp: int, defense: Skill, defense_sp: int, *,
    attack_modifiers: Modifiers | None = None,
    defense_modifiers: Modifiers | None = None,
    rng: random.Random | None = None,
) -> DefenseResult:
    """Resolve Guard, Evade ou Counter sem administrar HP."""
    rng = rng or random.Random()
    am, dm = attack_modifiers or Modifiers(), defense_modifiers or Modifiers()
    level_bonus = max(0, (dm.level - am.level) // 3)
    if defense.skill_type == "counter":
        attack_roll, _ = roll_skill(attack, attack_sp, attack.coins, rng, am)
        counter_roll, _ = roll_skill(defense, defense_sp, 1, rng, dm)
        return DefenseResult("counter", None, [attack_roll], [], "Moeda de Counter rolada.", counter_roll)
    if defense.skill_type == "guard":
        attack_roll, _ = roll_skill(attack, attack_sp, attack.coins, rng, am)
        defense_roll, _ = roll_skill(defense, defense_sp, 1, rng, dm)
        defense_roll.power += level_bonus
        return DefenseResult("guard", None, [attack_roll], [defense_roll], "Moeda de Defesa rolada.")
    if defense.skill_type == "evade":
        attack_rolls, defense_rolls = [], []
        attack_power = attack.base_power + am.base_power
        paralysis = am.paralysis
        for _ in range(attack.coins):
            face = rng.random() < heads_chance(attack_sp)
            coin_enabled = paralysis <= 0
            paralysis = max(0, paralysis - 1)
            if face and coin_enabled:
                attack_power += attack.coin_power + (am.coin_power if attack.coin_power > 0 else 0)
            attack_roll = Roll(attack_power, [face])
            defense_roll, dm.paralysis = roll_skill(defense, defense_sp, defense.coins, rng, dm)
            defense_roll.power += level_bonus
            attack_rolls.append(attack_roll)
            defense_rolls.append(defense_roll)
            if defense_roll.power < attack_roll.power:
                return DefenseResult(
                    "evade", False, attack_rolls, defense_rolls,
                    "Evasão falhou; a sequência foi interrompida.",
                )
        return DefenseResult("evade", True, attack_rolls, defense_rolls, "Todas as moedas foram evadidas.")
    raise ValueError("A skill informada não é uma defesa comum.")


def roll_skill(
    skill: Skill, sp: int, remaining_coins: int, rng: random.Random,
    modifiers: Modifiers | None = None, active_unbreakable: int | None = None,
) -> tuple[Roll, int]:
    modifiers = modifiers or Modifiers()
    faces = [rng.random() < heads_chance(sp) for _ in range(remaining_coins)]
    paralysis_used = min(modifiers.paralysis, remaining_coins)
    disabled = [index < paralysis_used for index in range(remaining_coins)]
    if active_unbreakable is None:
        unbreakable = [skill.coin_is_unbreakable(index + 1) for index in range(remaining_coins)]
    else:
        active_unbreakable = min(active_unbreakable, remaining_coins)
        unbreakable = [index < active_unbreakable for index in range(remaining_coins)]
    effective_heads = sum(faces[paralysis_used:])
    power = skill.base_power + modifiers.base_power
    effective_coin_power = skill.coin_power + (modifiers.coin_power if skill.coin_power > 0 else 0)
    power += effective_coin_power * effective_heads
    return Roll(power, faces, disabled, unbreakable), modifiers.paralysis - paralysis_used


def resolve_clash(
    left: Skill, left_sp: int, right: Skill, right_sp: int, *,
    rng: random.Random | None = None,
    max_rounds: int = 100,
    left_modifiers: Modifiers | None = None,
    right_modifiers: Modifiers | None = None,
) -> ClashResult:
    """Empates repetem a rodada; quem perde uma rodada perde uma moeda."""
    rng = rng or random.Random()
    left_coins, right_coins = left.coins, right.coins
    left_broken_unbreakable = right_broken_unbreakable = 0
    left_modifiers = left_modifiers or Modifiers()
    right_modifiers = right_modifiers or Modifiers()
    level_difference = left_modifiers.level - right_modifiers.level
    left_level_bonus = max(0, level_difference // 3)
    right_level_bonus = max(0, (-level_difference) // 3)
    rounds: list[ClashRound] = []

    for number in range(1, max_rounds + 1):
        left_roll, left_modifiers.paralysis = roll_skill(
            left, left_sp, left_coins, rng, left_modifiers,
        )
        right_roll, right_modifiers.paralysis = roll_skill(
            right, right_sp, right_coins, rng, right_modifiers,
        )
        left_roll.power += left_level_bonus + left_modifiers.clash_power
        right_roll.power += right_level_bonus + right_modifiers.clash_power
        if left_roll.power > right_roll.power:
            right_unbreakable_broken = right.coin_is_unbreakable(right_coins)
            right_coins -= 1
            if right_unbreakable_broken:
                right_broken_unbreakable += 1
            result = "left"
        elif right_roll.power > left_roll.power:
            left_unbreakable_broken = left.coin_is_unbreakable(left_coins)
            left_coins -= 1
            if left_unbreakable_broken:
                left_broken_unbreakable += 1
            result = "right"
        else:
            left_unbreakable_broken = right_unbreakable_broken = False
            result = "tie"
        if result == "left":
            left_unbreakable_broken = False
        elif result == "right":
            right_unbreakable_broken = False
        rounds.append(ClashRound(
            number, left_roll, right_roll, result,
            left_unbreakable_broken, right_unbreakable_broken,
        ))
        if left_coins == 0:
            return ClashResult(
                "right", left_coins, right_coins, rounds,
                left_modifiers.paralysis, right_modifiers.paralysis,
                left_broken_unbreakable, right_broken_unbreakable,
            )
        if right_coins == 0:
            return ClashResult(
                "left", left_coins, right_coins, rounds,
                left_modifiers.paralysis, right_modifiers.paralysis,
                left_broken_unbreakable, right_broken_unbreakable,
            )
    raise RuntimeError("Clash excedeu o limite de rodadas; tente novamente.")


def resolve_attack(
    skill: Skill, sp: int, remaining_coins: int, *, rng: random.Random | None = None,
    modifiers: Modifiers | None = None, faces: list[bool] | None = None,
    active_unbreakable: int | None = None,
) -> list[AttackHit]:
    """Rola cada moeda em sequência e acumula Coin Power em Heads."""
    rng = rng or random.Random()
    modifiers = modifiers or Modifiers()
    power = skill.base_power + modifiers.base_power
    effective_coin_power = skill.coin_power + (modifiers.coin_power if skill.coin_power > 0 else 0)
    paralysis = modifiers.paralysis
    active_flags = (
        [skill.coin_is_unbreakable(index + 1) for index in range(remaining_coins)]
        if active_unbreakable is None
        else [index < min(active_unbreakable, remaining_coins) for index in range(remaining_coins)]
    )
    hits = []
    for coin in range(1, remaining_coins + 1):
        face = faces[coin - 1] if faces is not None else rng.random() < heads_chance(sp)
        coin_enabled = paralysis <= 0
        paralysis = max(0, paralysis - 1)
        if face and coin_enabled:
            power += effective_coin_power
        hits.append(AttackHit(coin, face, power, not coin_enabled, False, active_flags[coin - 1]))
    return hits


def resolve_damage(
    skill: Skill, sp: int, remaining_coins: int, offense_level: int,
    defense_level: int, *, rng: random.Random | None = None,
    modifiers: Modifiers | None = None, faces: list[bool] | None = None,
    broken_unbreakable: int = 0,
) -> DamageResult:
    """Acumula Coin Power sobre a Base e aplica a diferença de níveis ao final."""
    hits = resolve_attack(
        skill, sp, remaining_coins, rng=rng, modifiers=modifiers, faces=faces,
        active_unbreakable=None,
    )
    for index in range(broken_unbreakable):
        hits.append(AttackHit(remaining_coins + index + 1, False, 1, False, True))
    regular_power = next((hit.power for hit in reversed(hits) if not hit.unbreakable), 0)
    subtotal = regular_power + broken_unbreakable
    level_modifier = int((offense_level - defense_level) / 3)
    result = DamageResult(
        hits, subtotal, level_modifier, max(0, subtotal + level_modifier),
        offense_level, defense_level,
    )
    return apply_damage_percentage(result, 0)


def apply_damage_percentage(result: DamageResult, percent: float) -> DamageResult:
    """Aplica modificador percentual ao dano pós-nível; redução para em -100%."""
    percent = max(-100, percent)
    before = max(0, result.subtotal + result.level_modifier)
    modifier = int(before * percent / 100)
    result.damage_before_percent = before
    result.damage_percent = percent
    result.percent_modifier = modifier
    result.final_damage = max(0, before + modifier)
    return result
