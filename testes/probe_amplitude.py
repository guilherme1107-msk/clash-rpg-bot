"""Sonda: flag de Amplitude Conversion — nascer Scorch / voltar ao normal."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
work = Path(tempfile.gettempdir()) / "ampl_probe.sqlite3"
for suffix in ("", "-wal", "-shm"):
    p = Path(str(work) + suffix)
    if p.exists():
        p.unlink()
shutil.copy2(ROOT / "clash_rpg.sqlite3", work)

os.environ["DATABASE_PATH"] = str(work)
os.environ.setdefault("DISCORD_TOKEN", "x")
sys.path.insert(0, str(ROOT))

import database  # noqa: E402

db = database.Database(str(work))
G, K, O = 1392000415108960426, "player", 730180911332851772
t = lambda: db.get_status(G, K, O, "tremor")
flag = lambda: (G, K, O) in database._AMPLITUDE_FLAGS
line = lambda tag: print(f"  {tag:<52} {str(t()):<74} flag={flag()}")

print("\nA) convertido -> tremor de OUTROS MEIOS na linha")
db.set_status(G, K, O, "tremor", 7, 3)
db.convert_tremor(G, K, O, "scorch")
line("   a1. conversion feita")
db.add_status(G, K, O, "tremor", 5, 1)
line("   a2. outra fonte aplicou +5/+1 -> nasce scorch?")

print("\nB) count zerou -> volta ao normal")
db.set_status(G, K, O, "tremor", 0, 0)
line("   b1. count 0 (linha apagada)")
db.add_status(G, K, O, "tremor", 4, 1)
line("   b2. tremor novo depois de zerar -> normal?")

print("\nC) linha sumiu SEM zerar count (ex.: limpeza) -> flag segura o scorch")
db.convert_tremor(G, K, O, "scorch")
line("   c1. reconvertido (flag ligado)")
with db.lock, db.connection:
    db.connection.execute(
        "DELETE FROM combat_statuses WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type='tremor'",
        (G, K, O),
    )
line("   c2. linha removida por fora (flag continua)")
db.add_status(G, K, O, "tremor", 6, 2)
line("   c3. tremor novo -> nasce scorch?")

print("\nD) dano do Scorch: so no Tremor Burst")
src = (ROOT / "bot.py").read_text(encoding="utf-8")
print(f"   tremor_scorch_burst chamado em: {src.count('tremor_scorch_burst(')} lugar(es) do bot")
