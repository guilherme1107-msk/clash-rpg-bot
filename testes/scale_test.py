"""O Clash Win do Imperfect Eye ESCALA? 3 disparos seguidos. Copia limpa."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"C:\Users\Usuário\Documents\clash-rpg-bot")
SRC = ROOT / "clash_rpg.sqlite3"
WORK = Path(tempfile.gettempdir()) / "clash_rpg_scale.sqlite3"

for suffix in ("", "-wal", "-shm"):
    p = Path(str(WORK) + suffix)
    if p.exists():
        p.unlink()
shutil.copy2(SRC, WORK)

os.environ["DATABASE_PATH"] = str(WORK)
os.environ.setdefault("DISCORD_TOKEN", "scale-test")
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402
from src.domain.combat import Skill  # noqa: E402

GUILD, ROSEMARY, BLADE = 1392000415108960426, 1034518001535430777, 730180911332851772

gift = next(g for g in bot.db.list_ego_gifts(GUILD, "player", ROSEMARY)
            if g["name"].startswith("Imperfect"))
bot.db.save_ego_gift(GUILD, "player", ROSEMARY, {
    "id": gift["id"], "name": gift["name"], "tier": gift["tier"],
    "description": gift["description"],
    "effects": [
        {"trigger": "clash_win", "effect_type": "tremor", "value": 2, "count": 2},
        {"trigger": "clash_win", "effect_type": "burn", "value": 2, "count": 2},
        {"trigger": "clash_win", "effect_type": "tremor_burst", "value": 1},
    ],
})

SKILL = Skill("Golpe", 4, 2, 2, "", "attack", 0, (), ("normal", "normal"))
print("10 Clash Wins seguidos do Imperfect Eye:\n")
print(f"  {'win':>3}  {'Tremor':>9}  {'Burn':>9}  {'Stagger Threshold do Burst':>28}")
for i in range(1, 11):
    log = bot.apply_skill_trigger(GUILD, "player", ROSEMARY, "player", BLADE,
                                   SKILL, "clash_win")
    t = bot.db.get_status(GUILD, "player", BLADE, "tremor")
    b = bot.db.get_status(GUILD, "player", BLADE, "burn")
    st = next((ln for ln in log if "Stagger Threshold" in ln), "")
    import re as _re
    m = _re.search(r"\+(\d+) Stagger", st)
    stg = f"+{m.group(1)}" if m else "-"
    print(f"  {i:>3}  {t.potency:>4}×{t.count:<4}  {b.potency:>4}×{b.count:<4}  {stg:>28}")

print("\n--- o que diz o código ---")
print("  bot.py:725   multiplier = 1                  (padrão: nada escala)")
print("  bot.py:794   effective_value = value * multiplier")
print("  database.py:827  new_potency = old_potency + potency   (SOMA)")
print("  status.py:94     stagger_threshold = potency  |  potency_after = potency")
print("                     => Tremor Burst NÃO consome (preserva potency e count)")
