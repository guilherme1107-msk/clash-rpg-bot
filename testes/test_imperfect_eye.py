"""Teste de fábrica — Imperfect Eye of Precognition na SPEC v2.

NUNCA toca no banco real: copia clash_rpg.sqlite3 pra um arquivo temporário
(aborta se vier sujo) e aponta o bot pra cópia.

Cenário pedido pelo autor:
    alvo já com 6 de Tremor Count  →  5 clash wins
    e ver onde para (ele calculou ~28x1)
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
WORK = Path(tempfile.gettempdir()) / "clash_rpg_ieye_test.sqlite3"

GUILD = 1392000415108960426      # Arcana [RPG]
ROSEMARY = 1034518001535430777   # quem usa o gift
BLADE = 730180911332851772       # alvo

# limpa o alvo de teste antes de comecar
for suffix in ("", "-wal", "-shm"):
    stale = Path(str(WORK) + suffix)
    if stale.exists():
        stale.unlink()
shutil.copy2(SRC, WORK)

import sqlite3  # noqa: E402
# A partir do item 4 do P7 (2026-10-01) o banco real **tem** a spec v2 gravada.
# A guarda antiga abortava quando a copia vinha "suja" — agora ela guarda o que
# veio, e a comparação com a SPEC_V2 acontece mais abaixo, em voz alta, para
# pega deriva entre o gravado e o esperado em vez de esconder num abort genérico.
with sqlite3.connect(f"file:{WORK.as_posix()}?mode=ro", uri=True) as _c:
    _c.row_factory = sqlite3.Row
    GRAVADO = {r["name"]: r["effects_json"] for r in _c.execute(
        "SELECT name,effects_json FROM ego_gifts")}
print(f"copied -> {WORK.name} ({WORK.stat().st_size:,} bytes)")

os.environ["DATABASE_PATH"] = str(WORK)
os.environ.setdefault("DISCORD_TOKEN", "gift-factory-test")
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402

# Ver `test_gifts.py`: sem `setup()` as migrações nunca rodam nestas fábricas,
# porque elas importam `bot` sem chegar a subir o cliente.
bot.db.setup()
from src.domain.combat import Skill  # noqa: E402

# ------------------------------------------------- SPEC v2 do Imperfect Eye
# Ordem importa: o Glimpse tem que existir ANTES de ler o 2x/4x/6x... dele.
COND = {
    "condition_status": "glimpse_of_precognition",
    "condition_owner": "user",     # o Glimpse mora no usuário do gift
    "condition_operator": "at_least",
    "condition_min": 1,
    "condition_per": 1,            # a cada 1 stack => multiplicador = stack
    "condition_max_stacks": 5,     # teto = teto do proprio Glimpse
}
SPEC_V2 = [
    # (1) ganhe 1 Glimpse  (o clamp de 5 mora em CombatStatus)
    {"trigger": "clash_win", "effect_type": "glimpse_of_precognition",
     "value": 1, "count": 1, "effect_owner": "user"},
    # (2) Tremor = 2 x Glimpse, SEM count extra
    {"trigger": "clash_win", "effect_type": "tremor", "value": 2, "count": 0,
     **COND},
    # (3) Burn = 2 x Glimpse, SEM count extra
    {"trigger": "clash_win", "effect_type": "burn", "value": 2, "count": 0,
     **COND},
    # (4) Amplitude Conversion -> Tremor - Scorch (o chat do Amplitude fechou).
    #     ANTES do burst: vira Scorch mantendo Pot./Count, e dai o burst
    #     roda em cima do Scorch (bot.py:906) disparando o dano (T+B)/2.
    {"trigger": "clash_win", "effect_type": "amplitude_conversion_scorch",
     "value": 0},
    # (5) Tremor Burst -> -1 Count (motor)
    {"trigger": "clash_win", "effect_type": "tremor_burst", "value": 1},
    # [Ao Critar] — limite de 2x por rodada (SkillEffect.max_per_round)
    {"trigger": "on_crit", "effect_type": "tremor_burst", "value": 1,
     "max_per_round": 2},
]

# ------------------------------------------------------- o banco tem a spec?
def _norm(clauses):
    """Compara só o que importa — a ordem das chaves não pode gerar falso verde."""
    return sorted(
        (c.get("trigger"), c.get("effect_type"), c.get("value"), c.get("count"),
         c.get("condition_status"), c.get("condition_min"), c.get("condition_per"),
         c.get("condition_owner"), c.get("max_per_round"))
        for c in clauses
    )


_ieye = next((n for n in GRAVADO if "Imperfect" in n), None)
_ja_gravada = json.loads(GRAVADO[_ieye] or "[]") if _ieye else []
if _ja_gravada and _norm(_ja_gravada) == _norm(SPEC_V2):
    print("\nspec v2 JA GRAVADA no banco bate com a de referencia.")
else:
    print(f"\nspec v2 divergentou do banco (gravadas={len(_ja_gravada)} "
          f"referencia={len(SPEC_V2)}). Gravando a de referencia na COPIA.")
    if _ja_gravada:
        print(f"  banco   : {_norm(_ja_gravada)}")
    print(f"  ref.    : {_norm(SPEC_V2)}")

# ------------------------------------------------------------------ setup
print("\nantes:")
for g in bot.db.list_ego_gifts(GUILD, "player", ROSEMARY):
    print(f"  {g['name']!r}  T{g['tier']}  ativo={g['is_active']}  "
          f"clausulas={len(json.loads(g['effects_json'] or '[]'))}")

for gift in bot.db.list_ego_gifts(GUILD, "player", ROSEMARY):
    clauses = SPEC_V2 if "Imperfect" in gift["name"] else []
    bot.db.save_ego_gift(GUILD, "player", ROSEMARY, {
        "id": gift["id"], "name": gift["name"], "tier": gift["tier"],
        "description": gift["description"], "effects": clauses,
        "base_power_mod": gift["base_power_mod"], "coin_power_mod": gift["coin_power_mod"],
        "clash_power_mod": gift["clash_power_mod"],
        "offense_level_mod": gift["offense_level_mod"],
        "defense_level_mod": gift["defense_level_mod"],
    })
print("\ndepois (so o Imperfect Eye com clausulas):")
for g in bot.db.list_ego_gifts(GUILD, "player", ROSEMARY):
    n = len(json.loads(g["effects_json"] or "[]"))
    print(f"  {g['name']!r} -> {n} clausula(s)")

# ---------------------------------------------- alvo: Tremor com 6 de Count
for st in ("tremor", "burn", "glimpse_of_precognition"):
    bot.db.set_status(GUILD, "player", BLADE, st, 0, 0)
bot.db.set_status(GUILD, "player", ROSEMARY, "glimpse_of_precognition", 0, 0)
bot.db.set_status(GUILD, "player", BLADE, "tremor", 0, 6)

def show(tag):
    tr = bot.db.get_status(GUILD, "player", BLADE, "tremor")
    bu = bot.db.get_status(GUILD, "player", BLADE, "burn")
    gl = bot.db.get_status(GUILD, "player", ROSEMARY, "glimpse_of_precognition")
    mods = bot.db.get_total_ego_gift_modifiers(GUILD, "player", ROSEMARY)
    fmt = lambda s: "—" if s is None else f"{s.potency}×{s.count}"
    print(f"  {tag:<26} Tremor {fmt(tr):<8} Burn {fmt(bu):<8} Glimpse {fmt(gl):<8} "
          f"Mods={mods}")
    return tr, bu, gl

print("\n" + "=" * 78)
print("TESTE — alvo com 0×6 de Tremor, 5 clash wins")
print("=" * 78)
show("inicio")

SKILL = Skill("Golpe de Teste", 4, 2, 2, "", "attack", 0, (), ("normal", "normal"))
total_stagger = 0
for i in range(1, 6):
    print(f"\n--- clash win #{i} ---")
    for line in bot.apply_skill_trigger(
        GUILD, "player", ROSEMARY, "player", BLADE, SKILL, "clash_win",
    ):
        if "Stagger Threshold" in line:
            try:
                total_stagger += int(line.split("+")[1].split(" ")[0])
            except Exception:
                pass
        print(f"    {line}")
    show(f"apos win #{i}")

print("\n" + "=" * 78)
print(f"STagger Threshold acumulado pelos 5 bursts: +{total_stagger}")
print("=" * 78)
show("FINAL")

# ------------------------------------------------------ on_crit continua
print("\n--- bonus: [Ao Critar] 4x seguidas (limite = 2x por rodada) ---")
for i in range(1, 5):
    log = bot.apply_skill_trigger(
        GUILD, "player", ROSEMARY, "player", BLADE, SKILL, "on_crit",
    )
    print(f"  on_crit #{i}: " + (" | ".join(l for l in log if "limite" in l or "Stagger" in l) or "(nada)"))
show(f"apos on_crit #{i}")

print("\n--- fim de rodada (process_round_end_statuses) ---")
evs = bot.db.process_round_end_statuses(GUILD)
print(f"  {len(evs)} evento(s)")
for _kind, _id, e in evs:
    print(f"    {e.status_type}: count_after={e.count_after} {e.note}")
show("apos fim de rodada")

print("\n--- [Ao Critar] de novo apos a troca de rodada (deve voltar a 2x) ---")
for i in range(1, 4):
    log = bot.apply_skill_trigger(
        GUILD, "player", ROSEMARY, "player", BLADE, SKILL, "on_crit",
    )
    print(f"  on_crit #{i}: " + (" | ".join(l for l in log if "limite" in l or "Stagger" in l) or "(nada)"))
show("FINAL")
