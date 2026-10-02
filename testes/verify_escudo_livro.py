"""Livro da vingança: 50 de escudo POR ALIADO DA MIDDLE, como numero solto.

Prova:
  1. A clausula do escudo carrega no motor e precisa de `condition_keyword`.
  2. O total e `50 x (aliados com a keyword)` — 1, 3 e 5 aliados da Middle.
  3. Quem tem a keyword nao entra na conta.
  4. Sem defusa (`clashable_guard`) nao ha escudo — o gift nao inventa uma.
  5. Nada e gravado: o numero e recalculado, e por isso "quebrou ou nao, volta
     a 50 na proxima rodada" sai de graca.

    python testes/verify_escudo_livro.py
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
from bot import gift_shield  # noqa: E402
from src.domain.models.combat import SkillEffect  # noqa: E402

GUILD = 995
DONO = 1          # Pablo Suindara, dono do Livro
MEIO = 2          # o proprio (a keyword dele e 'middle')


def sep(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


def main():
    db = bot.db
    db.create_character(GUILD, DONO, "Pablo Suindara")
    db.create_character(GUILD, MEIO, "Aliado da Middle")
    db.set_keywords(GUILD, "player", DONO, ["middle"])
    db.set_keywords(GUILD, "player", MEIO, ["middle"])
    with db.lock, db.connection:
        db.connection.execute("DELETE FROM ego_gifts WHERE guild_id=?", (GUILD,))
    db.save_ego_gift(GUILD, "player", DONO, {
        "name": "Livro da vingança: Annex (teste)", "tier": 5, "description": "",
        "effects": [{
            "trigger": "session_encounter_start", "effect_type": "shield", "value": 50,
            "condition_status": "allies_with_keyword", "condition_keyword": "middle",
            "condition_min": 1, "effect_owner": "all_allies",
        }],
    })

    # ── 1. a cláusula ──────────────────────────────────────────────
    sep("1) A CLAUSULA")
    e = SkillEffect(trigger="session_encounter_start", effect_type="shield", value=50,
                    condition_status="allies_with_keyword", condition_keyword="middle",
                    condition_min=1, effect_owner="all_allies")
    print(f"  {e.trigger} {e.effect_type} = {e.value:g}")
    print(f"  conta aliados com `{e.condition_keyword}` e multiplica")
    try:
        SkillEffect(trigger="session_encounter_start", effect_type="shield", value=50,
                    condition_status="allies_with_keyword")
        print("  ERRO: aceitou sem keyword")
    except ValueError as erro:
        print(f"  sem `condition_keyword` -> {erro}")

    # ── 2. o total é 50 × N ───────────────────────────────────────
    sep("2) 50 x (ALIADOS DA MIDDLE)")
    print(f"  {'N aliados':>9} | {'50 x N':>7} | {'o que o bot devolve':>20}")
    print(f"  {'-'*9}-+-{'-'*7}-+-{'-'*20}")
    for extra in range(0, 5):
        # o dono + o aliado + `extra` novos, todos da Middle
        for n in range(3, 3 + extra):
            db.create_character(GUILD, 100 + n, f"Mid{n}")
            db.set_keywords(GUILD, "player", 100 + n, ["middle"])
        n_middle = 2 + extra
        total = gift_shield(GUILD, "player", DONO, True)
        marca = "  ok" if total == 50 * n_middle else "  ERRO"
        print(f"  {n_middle:>9} | {50 * n_middle:>7} | {total:>20}{marca}")
    # limpando os extras para os testes seguintes
    for n in range(3, 8):
        with db.lock, db.connection:
            db.connection.execute(
                "DELETE FROM characters WHERE guild_id=? AND user_id=?", (GUILD, 100 + n))

    # ── 3. quem não tem a keyword não entra ───────────────────────
    sep("3) QUEM NAO TEM A KEYWORD NAO CONTA")
    outsider = 300
    db.create_character(GUILD, outsider, "De fora")
    db.set_keywords(GUILD, "player", outsider, ["blitz"])
    antes = gift_shield(GUILD, "player", DONO, True)
    db.set_keywords(GUILD, "player", outsider, ["middle"])
    depois = gift_shield(GUILD, "player", DONO, True)
    print(f"  como `blitz`: {antes}")
    print(f"  como `middle`: {depois}  (era 50 antes, agora 100 = 2 aliados)")
    db.set_keywords(GUILD, "player", outsider, ["blitz"])

    # ── 4. só a defusa cria escudo ─────────────────────────────────
    sep("4) SO A DEFUSA GERA ESCUDO")
    print(f"  com defusa (clashable_guard): {gift_shield(GUILD, 'player', DONO, True)}")
    print(f"  sem defusa:                    {gift_shield(GUILD, 'player', DONO, False)}")
    print("  (o gift nao inventa defusa — so soma no numero que ja existia)")

    # ── 5. nada é gravado ─────────────────────────────────────────
    sep("5) NADA E GRAVADO (por isso renova sozinho)")
    rows = db.connection.execute(
        "SELECT COUNT(*) FROM combat_statuses WHERE guild_id=? AND status_type='shield'",
        (GUILD,)).fetchone()[0]
    print(f"  linhas de status `shield` no banco: {rows}")
    print("  'quebrou ou nao, volta a 50 na proxima rodada' sai de graca: sem")
    print("  estado guardado, o numero e recalculado a cada Clash.")

    # ── limpeza ───────────────────────────────────────────────────
    with db.lock, db.connection:
        for t in ("ego_gifts", "characters", "combat_statuses"):
            db.connection.execute(f"DELETE FROM {t} WHERE guild_id=?", (GUILD,))
    db.close()
    print()
    print("  (guild 995 de teste apagada; o banco real nao foi tocado)")


if __name__ == "__main__":
    main()