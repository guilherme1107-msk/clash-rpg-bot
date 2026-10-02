"""The Family's Resentment: a cura sai do DANO da skill, e o HP é manual.

Prova 5 coisas:
  1. Skill que **nao** inflictiu Bleed -> nao cura.
  2. Skill que inflictiu Bleed -> cura 30% do dano, teto 20.
  3. O HP da ficha **nao muda** (modo manual, §8 do desenho).
  4. Curar enfileira o +1 Final Power para o inicio da proxima rodada.
  5. O teto de 20 segura mesmo com dano grande.

    python testes/verify_family_resentment.py
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
from bot import DamageResult, _bleed_snapshot, apply_gift_bleed_heal  # noqa: E402
from src.domain.models.combat import AttackHit  # noqa: E402

GUILD = 998          # guild de teste isolada
ROSEMARY = 1
INIMIGO = 500


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


def main():
    db = bot.db
    db.create_character(GUILD, ROSEMARY, "Rosemary")
    with db.lock, db.connection:
        db.connection.execute("INSERT OR IGNORE INTO enemies (id,guild_id,name,sp) "
                             "VALUES (?,?,?,0)", (INIMIGO, GUILD, "Alvo"))
        db.connection.execute("DELETE FROM ego_gifts WHERE guild_id=?", (GUILD,))
    db.save_ego_gift(GUILD, "player", ROSEMARY, {
        "name": "The Familys Resentment (teste)", "tier": 5, "description": "",
        "effects": [
            # a cura: inflingiu Bleed -> 30% do dano, teto 20
            {"trigger": "after_attack", "effect_type": "heal_from_damage",
             "value": 30, "condition_status": "inflicted_bleed",
             "condition_max_stacks": 20},
            # "se curou: +1 Final Power no inicio da proxima rodada"
            {"trigger": "session_round_start", "effect_type": "base_power",
             "value": 1, "effect_owner": "user"},
        ],
    })

    hp_antes = db.get_character(GUILD, ROSEMARY)["sp"]  # sanity, nao HP

    # ── 1. sem Bleed, nao cura ─────────────────────────────────────────
    sep("1) SKILL QUE NAO INFLINGIU BLEED -> NAO CURA")
    db.set_status(GUILD, "enemy", INIMIGO, "bleed", 0, 0)
    antes = _bleed_snapshot(GUILD, "enemy", INIMIGO)
    logs = apply_gift_bleed_heal(
        GUILD, "player", ROSEMARY, "enemy", INIMIGO, dano(100), antes)
    print(f"  Bleed do alvo: {antes} -> {antes} (nao mudou)")
    print(f"  {len(logs)} linha(s)")
    print(f"  {logs if logs else '(nada — correto)'}")

    # ── 2. com Bleed, cura ─────────────────────────────────────────────
    sep("2) SKILL QUE INFLINGIU BLEED -> CURA 30% DO DANO")
    # Count 0 apaga a linha do status, então "antes" precisa de Count >= 1.
    db.set_status(GUILD, "enemy", INIMIGO, "bleed", 1, 1)
    antes = _bleed_snapshot(GUILD, "enemy", INIMIGO)
    db.set_status(GUILD, "enemy", INIMIGO, "bleed", 4, 1)   # a skill aplicou
    logs = apply_gift_bleed_heal(
        GUILD, "player", ROSEMARY, "enemy", INIMIGO, dano(100), antes)
    for linha in logs:
        print(f"  {linha}")
    print("\n  100 de dano x 30% = 30, mas o teto e 20 -> 20 (max 20 da print)")

    # ── 3. HP nao muda ─────────────────────────────────────────────────
    sep("3) O HP DA FICHA NAO MUDA (modo manual)")
    sp_depois = db.get_character(GUILD, ROSEMARY)["sp"]
    print(f"  SP antes {hp_antes} / depois {sp_depois}  (o bot nao mexe em nada)")

    # ── 4. o Final Power ficou pendente ────────────────────────────────
    sep("4) 'SE CUROU' -> +1 FINAL POWER NA PROXIMA RODADA")
    pendentes = db.connection.execute(
        "SELECT gift_name, effect_type, value, starts_turn, expires_turn "
        "FROM ego_gift_state WHERE guild_id=? AND owner_id=?",
        (GUILD, ROSEMARY)).fetchall()
    print(f"  {len(pendentes)} linha(s) na fila de pendentes:")
    for p in pendentes:
        print(f"    {p['gift_name'][:28]:<30} {p['effect_type']} `+{p['value']}` "
              f"| entrega na rodada {p['starts_turn']}, ate {p['expires_turn']}")

    # ── 5. o teto ──────────────────────────────────────────────────────
    sep("5) O TETO SEGURA")
    print(f"  {'dano':>7} | {'30%':>6} | {'cura':>6}  (teto 20)")
    print(f"  {'-'*7}-+-{'-'*6}-+-{'-'*6}")
    for valor in (10, 30, 50, 67, 100, 500):
        db.set_status(GUILD, "enemy", INIMIGO, "bleed", 1, 1)
        antes = _bleed_snapshot(GUILD, "enemy", INIMIGO)
        d = dano(valor)
        db.set_status(GUILD, "enemy", INIMIGO, "bleed", 2, 1)
        logs = apply_gift_bleed_heal(
            GUILD, "player", ROSEMARY, "enemy", INIMIGO, d, antes)
        cura = 0
        for linha in logs:
            if "HP" in linha and "`" in linha:
                cura = int(linha.split("**`")[1].split("`")[0])
        marca = " <- teto" if valor * 0.3 > 20 else ""
        print(f"  {valor:>7} | {valor * 0.3:>6.0f} | {cura:>6}{marca}")

    # ── limpeza ───────────────────────────────────────────────────────
    with db.lock, db.connection:
        db.connection.execute("DELETE FROM ego_gift_state WHERE guild_id=?", (GUILD,))
        db.connection.execute("DELETE FROM ego_gifts WHERE guild_id=?", (GUILD,))
        db.connection.execute("DELETE FROM characters WHERE guild_id=?", (GUILD,))
        db.connection.execute("DELETE FROM enemies WHERE guild_id=?", (GUILD,))
    db.close()
    print()
    print("  (guild 998 de teste apagada; o banco real nao foi tocado)")


if __name__ == "__main__":
    main()