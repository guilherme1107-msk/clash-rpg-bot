"""Etapa 4 — prova ponta a ponta dos gatilhos de sessão, numa CÓPIA do banco real.

Injeta as cláusulas que os prints pedem, roda o fluxo de batalha e mostra o
efeito caindo na ficha certa. Nada toca o banco real.
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
WORK = Path(tempfile.gettempdir()) / "clash_rpg_session_test.sqlite3"

GUILD = 1392000415108960426
CHANNEL = 55501
ROSEMARY = 1034518001535430777
BLADE = 730180911332851772

for suffix in ("", "-wal", "-shm"):
    stale = Path(str(WORK) + suffix)
    if stale.exists():
        stale.unlink()
shutil.copy2(SRC, WORK)
os.environ["DATABASE_PATH"] = str(WORK)
os.environ.setdefault("DISCORD_TOKEN", "session-test")
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402

db = bot.db
db.setup()

# Os gifts REAIS continuam na cópia e disparam junto — o The Family's dá
# +6 de Offense por rodada para todo o time, e o Carousel também entra.
# Isso muda os números que a CONFERENCIA lá embaixo espera e faz o teste
# "divergir" sem ser o motor. Deixa os outros inertes: este script prova o
# Carousel (id 2) sozinho, e é ele que a linha logo abaixo sobrescreve.
db.connection.execute("UPDATE ego_gifts SET effects_json='[]' WHERE id<>2")
db.connection.execute("DELETE FROM ego_gift_state")
db.connection.commit()

# ── as cláusulas que as prints pedem ────────────────────────────────────
db.save_ego_gift(GUILD, "player", ROSEMARY, {
    "id": 2,  # Carousel Figurine
    "name": "Carousel Figurine", "tier": 5,
    "description": db.list_ego_gifts(GUILD, "player", ROSEMARY)[1]["description"],
    "base_power_mod": 0, "coin_power_mod": 0, "clash_power_mod": 0,
    "offense_level_mod": 0, "defense_level_mod": 0,
    "active_status": "",   # tira o gate La Manchaland só para o teste
    "effects": [
        # "[Primeira Rodada] Aumente Bloodfeast em 300"
        {"trigger": "session_round_start", "effect_type": "bloodfeast",
         "value": 300, "count": 1, "effect_owner": "user", "condition_turn": 1},
        # "[Início da Rodada] Ganhe 3 Sanidade" (Volatile)
        {"trigger": "session_round_start", "effect_type": "sp", "value": 3},
        # "[Início do Encontro] ..." (Livro)
        {"trigger": "session_encounter_start", "effect_type": "offense_level",
         "value": 2, "effect_owner": "user"},
        # "[Fim da Rodada] ..." (teste de que o turno certo é o que está acabando)
        {"trigger": "session_round_end", "effect_type": "coin_power", "value": 1},
    ],
})

print("=" * 76)
print("FLUXO DE BATALHA — 2 rodadas")
print("=" * 76)


def ficha(uid):
    row = db.get_character(GUILD, uid)
    return (f"sp={row['sp']:>3}  offense_mod={row['offense_level_mod']:>2}"
            f"  coin_mod={row['coin_power_mod']:>2}  "
            f"bloodfeast={(db.get_status(GUILD, 'player', uid, 'bloodfeast') or type('x',(),{'count':0})) .count}")


db.start_battle(GUILD, CHANNEL, "Teste de Sessão", ROSEMARY)
db.join_battle(GUILD, CHANNEL, ROSEMARY, "Rosemary Véspera")
db.join_battle(GUILD, CHANNEL, BLADE, "Blade")
# SP começa em 45 (o teto) na cópia real — zerar, senão o "+3 Sanidade" some no
# clamp e o teste não prova nada.
db.connection.execute("UPDATE characters SET sp=0 WHERE guild_id=?", (GUILD,))
db.connection.commit()

print(f"\n  antes          · Rosemary {ficha(ROSEMARY)}")
print(f"                 Blade    {ficha(BLADE)}   (sem gift, precisa ficar em 0)")

print("\n  --- rodada 1:-DE -> DECLARATION ---")
db.set_battle_phase(GUILD, CHANNEL, "declaration")
sp_r1 = db.get_character(GUILD, ROSEMARY)["sp"]
print(f"  depois         · Rosemary {ficha(ROSEMARY)}")

print("\n  --- fecha a rodada 1 (FIM DA RODADA) e vira para a 2 ---")
db.set_battle_phase(GUILD, CHANNEL, "resolution")
db.next_battle_turn(GUILD, CHANNEL)
sp_entre = db.get_character(GUILD, ROSEMARY)["sp"]
print(f"  depois         · Rosemary {ficha(ROSEMARY)}   (turno {db.current_turn(GUILD, CHANNEL)})")

print("\n  --- rodada 2: DE -> DECLARATION ---")
db.set_battle_phase(GUILD, CHANNEL, "declaration")
sp_r2 = db.get_character(GUILD, ROSEMARY)["sp"]
print(f"  depois         · Rosemary {ficha(ROSEMARY)}")

print()
print("=" * 76)
print("CONFERENCIA")
print("=" * 76)
blood = db.get_status(GUILD, "player", ROSEMARY, "bloodfeast")
ros = db.get_character(GUILD, ROSEMARY)
blade = db.get_character(GUILD, BLADE)
esperado = [
    ("Bloodfeast = 300 (só na primeira rodada, e guardado no Count)", blood is not None and blood.count == 300),
    ("+3 Sanidade na rodada 1", sp_r1 == 3),
    ("+3 Sanidade na rodada 2 (o meio da rodada é a regra da propria Rosemary)", sp_r2 - sp_entre == 3),
    ("Offense +2 veio do Início do Encontro", ros["offense_level_mod"] == 2),
    ("Coin Power +1 veio do Fim da Rodada", ros["coin_power_mod"] == 1),
    ("Blade (sem gift) ficou em zero", blade["sp"] == 0 and blade["offense_level_mod"] == 0
     and blade["coin_power_mod"] == 0),
    ("[Primeira Rodada] NÃO repetiu na rodada 2", blood.count == 300),
]
for texto, ok in esperado:
    print(f"  [{'ok' if ok else 'FALHOU'}] {texto}")
resultado = all(ok for _, ok in esperado)
print("\n  RESULTADO:", "TUDO OK" if resultado else "*** DIVERGIU ***")
# Sem isto o script imprimia "*** DIVERGIU ***" e saía com exit=0, e toda
# checagem que só olhava o código de saída passava batido.
sys.exit(0 if resultado else 1)
