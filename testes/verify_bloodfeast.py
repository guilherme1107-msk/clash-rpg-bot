"""Confere que NENHUMA cláusula das skills da Rosemary é descartada em silêncio.

O `_effects_from_row` joga fora a cláusula inválida sem avisar. A migração
trocou `special_condition` -> `bloodfeast`; se `bloodfeast` não estivesse na
lista de `condition_status` válidos, as cláusulas de escala dela (que leem o
"já consumido") teriam sumido — e o teste passaria, porque a skill continua
ali, só que pela metade.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"C:\Users\Usuário\Documents\clash-rpg-bot")
sys.path.insert(0, str(ROOT))

from database import _effects_from_row  # noqa: E402

G, ROSE = 1392000415108960426, 1034518001535430777
DB = ROOT / "clash_rpg.sqlite3"

con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

print("=" * 78)
print("CLÁUSULAS DA ROSEMARY: gravado x lido")
print("=" * 78)
total_gravado = total_lido = 0
perdeu = []
for r in con.execute(
    "SELECT name, effects_json FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
    (G, ROSE),
):
    gravado = json.loads(r["effects_json"] or "[]")
    lido = _effects_from_row(r)
    total_gravado += len(gravado)
    total_lido += len(lido)
    marca = "" if len(gravado) == len(lido) else f"   <-- PERDEU {len(gravado) - len(lido)}"
    if len(gravado) != len(lido):
        perde.extend((r["name"], g) for g in gravado[len(lido):])
    print(f"  {r['name']:<42} {len(gravado):>3} gravado / {len(lido):>3} lido{marca}")

print(f"\n  total: {total_gravado} gravado / {total_lido} lido")

# as condições de escala (as que o gift depende) sobreviveram?
print()
print("=" * 78)
print("CONDIÇÕES DE ESCALA DELA (leem o 'já consumido')")
print("=" * 78)
n = 0
for r in con.execute(
    "SELECT name, effects_json FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
    (G, ROSE),
):
    for e in _effects_from_row(r):
        if e.condition_status and "consumed" in str(e.condition_status):
            n += 1
            print(f"  {r['name']:<42} {e.trigger:<14} {e.effect_type:<16} "
                  f"{e.condition_status}>={e.condition_min:g} ({e.condition_value})")
print(f"\n  condições de escala vivas: {n}")

print()
print("=" * 78)
print("ESTADO FINAL DA FICHA")
print("=" * 78)
r = con.execute(
    "SELECT name, keywords, bloodfeast_consumed, special_condition_consumed "
    "FROM characters WHERE guild_id=? AND user_id=?", (G, ROSE)).fetchone()
print(f"  {r['name']}: keywords={r['keywords']}")
print(f"  bloodfeast_consumed={r['bloodfeast_consumed']}  "
      f"special_condition_consumed={r['special_condition_consumed']}")
for s in con.execute(
    "SELECT status_type, potency, count FROM combat_statuses WHERE guild_id=? AND owner_id=? "
    "AND status_type IN ('bloodfeast','special_condition')", (G, ROSE)
):
    print(f"  status {s['status_type']}: {s['potency']}x{s['count']}")

con.close()

if perdeu:
    print()
    print(f"  FALHA: {len(perdeu)} cláusula(s) descartada(s) em silêncio:")
    for nome, e in perde[:5]:
        print(f"    {nome}: {json.dumps(e, ensure_ascii=False)}")
    raise SystemExit(1)
print()
print("  OK: nenhuma cláusula foi descartada.")