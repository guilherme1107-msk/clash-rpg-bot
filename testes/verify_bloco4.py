"""Bloco 4 — `effect_owner` = all_allies / faction. Cópia do banco real.

Prova que a cláusula de time cai na ficha de **todo** o encounter (inclusive do
dono) e que a `faction` filtra pela keyword `active_tag` do gift — e que não sai
N vezes N.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"C:\Users\Usuário\Documents\clash-rpg-bot")
SRC = ROOT / "clash_rpg.sqlite3"
WORK = Path(tempfile.gettempdir()) / "clash_rpg_bloco4.sqlite3"

GUILD = 1392000415108960426
CHANNEL = 77701
ROSEMARY = 1034518001535430777
BLADE = 730180911332851772
ZERO = 693092062828036119

for suffix in ("", "-wal", "-shm"):
    stale = Path(str(WORK) + suffix)
    if stale.exists():
        stale.unlink()
shutil.copy2(SRC, WORK)
os.environ["DATABASE_PATH"] = str(WORK)
os.environ.setdefault("DISCORD_TOKEN", "bloco4-test")
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402

db = bot.db
db.setup()

# Os gifts REAIS da cópia disparam junto com os que este script cria (o
# The Family's dá +6 de Offense por rodada a todo o time), o que jogava
# todas as contas da CONFERENCIA lá embaixo fora. Deixa todos inertes:
# o `gift()` logo abaixo cria os seus, e estes não entram mais.
db.connection.execute("UPDATE ego_gifts SET effects_json='[]'")
db.connection.execute("DELETE FROM ego_gift_state")
db.connection.commit()
ROSTER = (("Rosemary", ROSEMARY), ("Blade", BLADE), ("Zero", ZERO))


def zerar(limpar_keywords=True):
    # add_effects(guild, uid, paralysis, base, coin, clash, offense, defense) —
    # o offense e o SETIMO argumento. Errar aqui escrevia no Clash Power.
    for nome, uid in ROSTER:
        row = db.get_character(GUILD, uid)
        db.add_effects(GUILD, uid, 0, 0, 0, 0, -row["offense_level_mod"])
    if limpar_keywords:
        for nome, uid in ROSTER:
            db.set_keywords(GUILD, "player", uid, [])
    db.connection.commit()


def mods():
    return {nome: db.get_character(GUILD, uid)["offense_level_mod"] for nome, uid in ROSTER}


def gift(nome, clauses, gate=None):
    db.save_ego_gift(GUILD, "player", ROSEMARY, {
        "name": nome, "tier": 5, "description": "", "effects": clauses, **(gate or {}),
    })


def combate(tag):
    print(f"\n  --- {tag} ---")
    zerar()
    db.start_battle(GUILD, CHANNEL, "Bloco 4", ROSEMARY)
    for nome, uid in ROSTER:
        db.join_battle(GUILD, CHANNEL, uid, nome)
    db.connection.commit()
    db.set_battle_phase(GUILD, CHANNEL, "declaration")
    print(f"      Offense Level -> {mods()}")


print("=" * 78)
print("BLOCO 4 — all_allies e faction")
print("=" * 78)

# 1) all_allies: todo mundo do encounter, inclusive a dona
gift("Time", [{"trigger": "session_round_start", "effect_type": "offense_level",
               "value": 2, "effect_owner": "all_allies"}])
combate("all_allies +2")
r_time = mods()

# 2) all_allies SEM chave: o gift de um aluno nao aplica em ninguem
db.connection.execute("UPDATE ego_gifts SET is_active=0 WHERE name='Time'")
db.connection.commit()
zerar()
print("\n  --- gift desativado ---")
db.set_battle_phase(GUILD, CHANNEL, "declaration")
print(f"      Offense Level -> {mods()}")
r_off = mods()

# 3) faction: so quem marca a keyword da active_tag do gift
gift("Facção", [{"trigger": "session_round_start", "effect_type": "offense_level",
                 "value": 3, "effect_owner": "faction"}],
     gate={"active_tag": "middle"})
zerar()
db.start_battle(GUILD, CHANNEL, "Bloco 4b", ROSEMARY)
for nome, uid in ROSTER:
    db.join_battle(GUILD, CHANNEL, uid, nome)
db.set_keywords(GUILD, "player", BLADE, ["middle"])
db.set_keywords(GUILD, "player", ROSEMARY, ["middle"])
db.connection.commit()
print("\n  --- faction=middle (Rosemary e Blade marcados) ---")
db.set_battle_phase(GUILD, CHANNEL, "declaration")
print(f"      Offense Level -> {mods()}")
r_faction = mods()

# 4) faction SEM active_tag: falha fechada, ninguem recebe
gift("Facção", [{"trigger": "session_round_start", "effect_type": "offense_level",
                 "value": 3, "effect_owner": "faction"}])
zerar()
db.start_battle(GUILD, CHANNEL, "Bloco 4c", ROSEMARY)
for nome, uid in ROSTER:
    db.join_battle(GUILD, CHANNEL, uid, nome)
db.connection.commit()
print("\n  --- faction sem active_tag (falha fechada) ---")
db.set_battle_phase(GUILD, CHANNEL, "declaration")
print(f"      Offense Level -> {mods()}")
r_sem_tag = mods()

print()
print("=" * 78)
print("CONFERENCIA")
print("=" * 78)
esperado = [
    ("all_allies pegou os 3 do encounter, inclusive a dona",
     r_time == {"Rosemary": 2, "Blade": 2, "Zero": 2}),
    ("gift desativado nao aplica em ninguem",
     r_off == {"Rosemary": 0, "Blade": 0, "Zero": 0}),
    ("faction pegou SO os 2 que marcaram middle",
     r_faction == {"Rosemary": 3, "Blade": 3, "Zero": 0}),
    ("faction sem active_tag falha fechada (ninguem)",
     r_sem_tag == {"Rosemary": 0, "Blade": 0, "Zero": 0}),
    ("N vezes N nao aconteceu (2 aliados x 3 participantes seria 6)",
     r_faction["Rosemary"] == 3 and r_faction["Blade"] == 3),
]
for texto, ok in esperado:
    print(f"  [{'ok' if ok else 'FALHOU'}] {texto}")
resultado = all(ok for _, ok in esperado)
print("\n  RESULTADO:", "TUDO OK" if resultado else "*** DIVERGIU ***")
# Sem isto o script imprimia "*** DIVERGIU ***" e saía com exit=0, e toda
# checagem que só olhava o código de saída passava batido.
sys.exit(0 if resultado else 1)
