"""Confere se sanitize_embed() realmente respeita o teto de 6000 do Discord.

Regra real da API: title + description + fields(name+value) + footer + author
<= 6000 caracteres. sanitize_embed() limita o footer a 2048 e o description a
3800, mas sobe o orcamento de campos usando title+description+footer+author como
base -- e nao reduz nenhum deles para caber no teto.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_sanitize_probe.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "probe-only")

import discord  # noqa: E402
import bot as B  # noqa: E402

API_LIMIT = 6000


def true_total(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    total += sum(len(f.name) + len(f.value) for f in embed.fields)
    if embed.footer and embed.footer.text:
        total += len(embed.footer.text)
    if embed.author and embed.author.name:
        total += len(embed.author.name)
    return total


def probe(label: str, build) -> None:
    embed = build()
    before = true_total(embed)
    B.sanitize_embed(embed)
    after = true_total(embed)
    status = "OK" if after <= API_LIMIT else "ACIMA DO LIMITE"
    print(f"{label:38} antes={before:6}  depois={after:6}  {status}")
    return after


def full():
    e = discord.Embed(title="T" * 400, description="D" * 5000, color=B.ACCENT)
    e.set_author(name="A" * 400)
    e.set_footer(text="F" * 3000)
    for i in range(6):
        e.add_field(name=f"C{i}", value="X" * 1500)
    return e


print(f"Teto real da API do Discord: {API_LIMIT} caracteres\n")

# 1. Pior caso de title + description + footer, sem fields.
probe("title+desc+footer, sem campos", lambda: discord.Embed(
    title="T" * 400, description="D" * 5000, color=B.ACCENT,
).set_footer(text="F" * 3000))

# 2. Pior caso realista: author + footer + fields.
probe("author+footer+campos", full)
worst = probe("pior caso combinado", full)
print()
if worst and worst > API_LIMIT:
    print("CONFIRMADO: sanitize_embed() devolve um embed que a API rejeitaria.")
    print(f"  Excesso de {worst - API_LIMIT} caracteres.")
