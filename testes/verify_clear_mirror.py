"""Clear Mirror + Etapa 5 — prova ponta a ponta numa COPIA do banco real.

  1. critico do Poise vira `Potencia x 2% + 70%` (o gift do Blade)
  2. "se o critico consumiu Poise Count" consome 1 Count
  3. o +10 Offense fica PENDENTE para a proxima rodada
  4. "1x por personagem, por rodada": o segundo critico da rodada nao repete
  5. na rodada seguinte o pendente cai e o limite zera
"""
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"C:\Users\Usuário\Documents\clash-rpg-bot")
SRC = ROOT / "clash_rpg.sqlite3"
WORK = Path(tempfile.gettempdir()) / "clash_rpg_clear_mirror.sqlite3"

GUILD = 1392000415108960426
CHANNEL = 99901
BLADE = 730180911332851772
ROSEMARY = 1034518001535430777

for suffix in ("", "-wal", "-shm"):
    stale = Path(str(WORK) + suffix)
    if stale.exists():
        stale.unlink()
shutil.copy2(SRC, WORK)
os.environ["DATABASE_PATH"] = str(WORK)
os.environ.setdefault("DISCORD_TOKEN", "clear-mirror-test")
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402
from src.domain.combat import Modifiers, Skill, resolve_damage  # noqa: E402

db = bot.db
db.setup()
SKILL = Skill("Golpe", 4, 2, 4, "", "attack", 0, (), ("normal", "normal", "normal", "normal"))
ENEMY = 10


def estado():
    poise = db.get_status(GUILD, "player", BLADE, "poise")
    row = db.get_character(GUILD, BLADE)
    pend = db.connection.execute(
        "SELECT COUNT(*) FROM ego_gift_state WHERE owner_id=? AND effect_type<>''", (BLADE,)
    ).fetchone()[0]
    return (f"poise={poise.potency}x{poise.count}  offense_mod={row['offense_level_mod']}"
            f"  pendentes={pend}")


def critico(rng_seed=99):
    """Rola o dano e aplica o critico do Poise (d20 secreto, dai o rng)."""
    dano = resolve_damage(SKILL, 0, 4, 0, 0, modifiers=Modifiers(0, 0, 0),
                          rng=random.Random(7))
    log = bot.apply_poise_critical(GUILD, "player", BLADE, dano, rng=random.Random(rng_seed))
    return dano, log


print("=" * 78)
print("ENCONTRO + ESTADO INICIAL")
print("=" * 78)
db.start_battle(GUILD, CHANNEL, "Clear Mirror", BLADE)
db.join_battle(GUILD, CHANNEL, BLADE, "Blade")
db.join_battle(GUILD, CHANNEL, ROSEMARY, "Rosemary Véspera")
db.set_keywords(GUILD, "player", BLADE, [])
db.set_keywords(GUILD, "player", ROSEMARY, [])
db.connection.execute("UPDATE characters SET sp=0 WHERE guild_id=?", (GUILD,))
for uid in (BLADE, ROSEMARY):
    row = db.get_character(GUILD, uid)
    db.add_effects(GUILD, uid, 0, 0, 0, 0, -row["offense_level_mod"])
db.set_status(GUILD, "player", BLADE, "poise", 10, 3)   # 10 de Potencia = 20% de critico
db.connection.commit()
db.set_battle_phase(GUILD, CHANNEL, "declaration")
print(f"  {estado()}")
print("  (Poise 10 de Potencia = 20% de critico; o gift do Blade soma +70)")

print()
print("=" * 78)
print("1) CRITICO — 20% do Poise + 70 do gift = 90%")
print("=" * 78)
dano, log = critico()
for linha in log:
    print(f"  {linha}")
print(f"  dano final apos o critico: {dano.final_damage}")
antes = estado()
print(f"  {antes}")

print()
print("=" * 78)
print("2) A CLAUSULA [Ao Critar] — consome Poise e deixa o +10 pendente")
print("=" * 78)
linhas = bot.apply_skill_trigger(
    GUILD, "player", BLADE, "enemy", ENEMY, SKILL, "on_crit", hits=dano.hits,
)
for linha in linhas:
    print(f"  {linha}")
print(f"  {estado()}")

print()
print("=" * 78)
print("3) SEGUNDO CRITICO NA MESMA RODADA — limite de 1x por rodada")
print("=" * 78)
linhas = bot.apply_skill_trigger(
    GUILD, "player", BLADE, "enemy", ENEMY, SKILL, "on_crit", hits=dano.hits,
)
for linha in linhas:
    print(f"  {linha}")
print(f"  {estado()}")

print()
print("=" * 78)
print("4) RODADA SEGUINTE — o pendente cai e o limite zera")
print("=" * 78)
db.set_battle_phase(GUILD, CHANNEL, "resolution")
db.next_battle_turn(GUILD, CHANNEL)
db.set_status(GUILD, "player", BLADE, "poise", 10, 3)
db.set_battle_phase(GUILD, CHANNEL, "declaration")
print(f"  {estado()}")
linhas = bot.apply_skill_trigger(
    GUILD, "player", BLADE, "enemy", ENEMY, SKILL, "on_crit", hits=dano.hits,
)
print("  --- agora um critico novo deve funcionar de novo ---")
for linha in linhas:
    print(f"  {linha}")
print(f"  {estado()}")

print()
print("=" * 78)
print("CONFERENCIA")
print("=" * 78)
bl = db.get_character(GUILD, BLADE)
ro = db.get_character(GUILD, ROSEMARY)
poise = db.get_status(GUILD, "player", BLADE, "poise")
pendentes = db.connection.execute(
    "SELECT COUNT(*) FROM ego_gift_state WHERE owner_id=? AND effect_type<>''", (BLADE,)
).fetchone()[0]
esperado = [
    ("Blade tem +10 Offense (ele e que critou)", bl["offense_level_mod"] == 10),
    ("Rosemary NAO ganhou (o print diz 'o aliado' que critou)", ro["offense_level_mod"] == 0),
    ("o pendente da rodada 1 foi ENTREGUE e saiu da fila (so o novo sobrou)",
     pendentes == 1),
]
for texto, ok in esperado:
    print(f"  [{'ok' if ok else 'FALHOU'}] {texto}")
print("\n  RESULTADO:", "TUDO OK" if all(ok for _, ok in esperado) else "*** DIVERGIU ***")
