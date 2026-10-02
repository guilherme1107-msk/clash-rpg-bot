"""As duas correcoes do The Family's Resentment.

1. **max 3** do "se curou: +1 Final Power" — sem `reserve_gift_activation` o
   `queue_gift_effect` so acumulava e a 4a cura da rodada empilhava +4.
2. **Bloodfeast Consumido (Compartilhado)** — a print pede o total **do time**;
   `bloodfeast_consumed` sozinho e por ficha, e dois aliados consumindo 30 cada
   dariam 30 quando a regra e 50.

    python testes/verify_family_limites.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import bot  # noqa: E402
from bot import (  # noqa: E402
    DamageResult, _bleed_snapshot, apply_gift_bleed_heal, skill_condition_value,
)
from src.domain.models.combat import AttackHit, SkillEffect  # noqa: E402

GUILD = 997
ROSEMARY = 1
INIMIGO = 500
TIME = (11, 22, 33)          # 3 aliadas, 2 delas com Bloodfeast consumido


def dano(valor):
    return DamageResult(
        hits=[AttackHit(coin=i, face="heads", power=10) for i in range(1, 4)],
        subtotal=valor, level_modifier=0, final_damage=valor,
        offense_level=0, defense_level=0,
    )


def sep(titulo):
    print()
    print("=" * 74)
    print(titulo)
    print("=" * 74)


def curar():
    """Uma skill que inflingiu Bleed: chama a cura e devolve as linhas."""
    bot.db.set_status(GUILD, "enemy", INIMIGO, "bleed", 1, 1)
    antes = _bleed_snapshot(GUILD, "enemy", INIMIGO)
    bot.db.set_status(GUILD, "enemy", INIMIGO, "bleed", 2, 1)
    return apply_gift_bleed_heal(
        GUILD, "player", ROSEMARY, "enemy", INIMIGO, dano(50), antes)


def main():
    db = bot.db
    for uid in (ROSEMARY, *TIME):
        db.create_character(GUILD, uid, f"Ficha{uid}")
    with db.lock, db.connection:
        db.connection.execute("INSERT OR IGNORE INTO enemies (id,guild_id,name,sp) "
                             "VALUES (?,?,?,0)", (INIMIGO, GUILD, "Alvo"))
        db.connection.execute("DELETE FROM ego_gifts WHERE guild_id=?", (GUILD,))
    db.save_ego_gift(GUILD, "player", ROSEMARY, {
        "name": "The Familys Resentment (teste)", "tier": 5, "description": "",
        "effects": [
            {"trigger": "after_attack", "effect_type": "heal_from_damage",
             "value": 30, "condition_status": "inflicted_bleed",
             "condition_max_stacks": 20},
            {"trigger": "session_round_start", "effect_type": "base_power",
             "value": 1, "effect_owner": "user",
             "max_activations": 3, "activation_window": "round"},
            # "cada 50 Bloodfeast Consumido (Compartilhado): todos +1 Offense (max 6)"
            {"trigger": "session_round_start", "effect_type": "offense_level",
             "value": 1, "condition_status": "shared_bloodfeast_consumed",
             "condition_owner": "user", "condition_operator": "at_least",
             "condition_min": 50, "condition_per": 50,
             "condition_max_stacks": 6, "effect_owner": "all_allies"},
        ],
    })

    # ── 1. o teto de 3 ────────────────────────────────────────────────
    sep("1) 'SE CUROU' — max 3 POR RODADA")
    print("  5 curas na MESMA rodada, teto = 3:")
    for n in range(1, 6):
        linhas = curar()
        # A notinha e uma linha so (autor 21:5x): "devolve N HP ... +1 Base Power
        # na proxima rodada". O "teto" e o texto quando o limite bateu.
        entrou = next((l for l in linhas if "próxima rodada" in l), "")
        barrado = next((l for l in linhas if "teto" in l), "")
        print(f"    cura {n}: {'ENTROU' if entrou else 'BARRADO'}"
              f"{'  (teto ' + barrado.split('teto ')[1][:8] + ')' if barrado else ''}")
    fila = db.connection.execute(
        "SELECT COALESCE(SUM(value),0) total FROM ego_gift_state WHERE guild_id=? "
        "AND owner_id=? AND effect_type='base_power'", (GUILD, ROSEMARY)).fetchone()
    print(f"\n  soma na fila: `+{fila['total']}`  <- 3, nao 5")
    print("  (a 4a e a 5a falaram no `reserve_gift_activation`)")

    # ── 2. o round novo libera ────────────────────────────────────────
    sep("2) A RODADA VIRANDO ZERA O CONTADOR")
    db.clear_gift_state(GUILD, "player", ROSEMARY)
    print("  fila limpa (simulando a entrega no inicio da rodada).")
    # O contador do limite mora na MESMA tabela (`effect_type=''`, `window_key`),
    # nao em uma tabela separada.
    with db.lock, db.connection:
        db.connection.execute(
            "DELETE FROM ego_gift_state WHERE guild_id=? AND effect_type=''",
            (GUILD,))
    print("  agora 3 curas de novo:")
    for n in range(1, 4):
        linhas = curar()
        ok = any("próxima rodada" in l for l in linhas)
        print(f"    cura {n}: {'entrou' if ok else 'barrada'}")
    fila = db.connection.execute(
        "SELECT COALESCE(SUM(value),0) total FROM ego_gift_state WHERE guild_id=? "
        "AND owner_id=? AND effect_type='base_power'", (GUILD, ROSEMARY)).fetchone()
    print(f"\n  soma na fila: `+{fila['total']}`  <- o teto e por rodada, nao por encontro")

    # ── 3. Bloodfeast Consumido (Compartilhado) ────────────────────────
    sep("3) 'BLOODFEAST CONSUMIDO (COMPARTILHADO)' — A SOMA DO TIME")
    print("  Cada ficha consumiu:")
    for uid in (ROSEMARY, *TIME):
        db.set_status(GUILD, "player", uid, "bloodfeast", 0, 200)
    consumos = {ROSEMARY: 20, TIME[0]: 30, TIME[1]: 30}
    for uid, valor in consumos.items():
        with db.lock, db.connection:
            db.connection.execute(
                "UPDATE characters SET bloodfeast_consumed=? WHERE guild_id=? AND user_id=?",
                (valor, GUILD, uid))
    for uid in (ROSEMARY, *TIME):
        print(f"    ficha {uid}: {db.get_bloodfeast_consumed(GUILD, 'player', uid)}")
    total = db.shared_bloodfeast_consumed(GUILD, "player", ROSEMARY)
    print(f"\n  por ficha (Rosemary): {db.get_bloodfeast_consumed(GUILD, 'player', ROSEMARY)}")
    print(f"  COMPARTILHADO (time): {total}   <- 20+30+30")
    print("  A regra e 'cada 50': por ficha ninguem chega a 50, o time chega a 80.")

    # ── 4. a escala ────────────────────────────────────────────────────
    sep("4) A CLAUSULA ESCALA COM O TOTAL COMPARTILHADO")
    efeito = SkillEffect(
        trigger="session_round_start", effect_type="offense_level", value=1,
        condition_status="shared_bloodfeast_consumed", condition_owner="user",
        condition_operator="at_least", condition_min=50, condition_per=50,
        condition_max_stacks=6, effect_owner="all_allies",
    )
    print(f"  {'consumido do time':>18} | {'+Offense':>9} | {'levels':>7}")
    print(f"  {'-'*18}-+-{'-'*9}-+-{'-'*7}")
    for valor, esperado in ((0, 0), (30, 0), (50, 1), (80, 1), (100, 2), (320, 6)):
        with db.lock, db.connection:
            db.connection.execute(
                "UPDATE characters SET bloodfeast_consumed=0 WHERE guild_id=?", (GUILD,))
            db.connection.execute(
                "UPDATE characters SET bloodfeast_consumed=? WHERE guild_id=? AND user_id=?",
                (valor, GUILD, ROSEMARY))
        got = db.shared_bloodfeast_consumed(GUILD, "player", ROSEMARY)
        saida = skill_condition_value(
            GUILD, "player", ROSEMARY, "enemy", INIMIGO, efeito)
        val = saida[-1]
        print(f"  {got:>18} | {val:>9} | {esperado:>7} {'' if val == esperado else '<-- ERRO'}")

    # ── limpeza ───────────────────────────────────────────────────────
    with db.lock, db.connection:
        for tabela in ("ego_gift_state", "ego_gifts", "characters", "combat_statuses"):
            db.connection.execute(f"DELETE FROM {tabela} WHERE guild_id=?", (GUILD,))
        db.connection.execute("DELETE FROM enemies WHERE guild_id=?", (GUILD,))
    db.close()
    print()
    print("  (guild 997 de teste apagada; o banco real nao foi tocado)")


if __name__ == "__main__":
    main()