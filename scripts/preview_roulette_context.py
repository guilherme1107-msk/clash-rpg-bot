"""As cinco roletas dentro do prediction_embed real.

Um GIF solto nao prova nada. O que importa e ver a imagem na posicao
exata do embed, com o rotulo do forecast logo acima dela — porque a
promessa do conceito e que os dois concordam.

Uso:  .venv\\Scripts\\python.exe scripts\\preview_roulette_context.py
"""

from __future__ import annotations

import base64
import html
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_roul.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "roul-only")

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import Skill, SkillEffect, prediction_with_paralysis  # noqa: E402
from src.domain.models import Modifiers  # noqa: E402

GIFS = ROOT / "assets" / "gifs"
OUT = ROOT / "scripts" / "preview_roulette.html"

# Mesma ordem e mesmos nomes de forecast_label() em engine.py:21.
CASES = [
    ("HOPELESS",  0.11),
    ("STRUGGLING", 0.33),
    ("NEUTRAL",   0.52),
    ("FAVORED",   0.68),
    ("DOMINATING", 0.86),
]


def data_uri(name: str) -> str:
    raw = (GIFS / name).read_bytes()
    return "data:image/gif;base64," + base64.b64encode(raw).decode()


def md(text: str) -> str:
    out = html.escape(text or "").replace("`", "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"^#{1,3}\s*(.+)$", r'<div class="big">\1</div>', out, flags=re.M)
    return out.replace("\n", "<br>")


def card(label: str, chance: float, embed: discord.Embed) -> str:
    color = f"#{embed.colour.value:06x}"
    p = [f'<div class="embed" style="border-left-color:{color}">']
    if embed.title:
        p.append(f'<div class="title">{md(embed.title)}</div>')
    if embed.description:
        p.append(f'<div class="desc">{md(embed.description)}</div>')
    for f in embed.fields:
        p.append(f'<div class="fname">{md(f.name)}</div><div class="fval">{md(f.value)}</div>')
    p.append(f'<img class="art" src="{data_uri("roulette_" + label.lower() + ".gif")}">')
    if embed.footer and embed.footer.text:
        p.append(f'<div class="footer">{md(embed.footer.text)}</div>')
    p.append("</div>")
    return f'<div class="slot"><p class="cap">{label} — {chance:.0%}</p>{"".join(p)}</div>'


def main() -> None:
    left = Skill("Corte Ascendente", 14, 6, 3, "", "attack",
                 effects=(SkillEffect("on_hit", "bleed", 3, count=2),))
    right = Skill("Riposte Punida", 11, 4, 2, "", "counter")

    slots = []
    for label, chance in CASES:
        # Reproduz a previsao com os modificadores necessarios para cair
        # no rotulo desejado, para o embed exibir o mesmo par do GIF.
        boost = (chance - 0.5) * 60
        mods = Modifiers(0, 0, 0, 0, int(round(boost)))
        forecast = prediction_with_paralysis(left, 0, right, 0, mods, Modifiers())
        embed = B.prediction_embed("Yi Sang", left, "Cavaleiro Aberrante", right,
                                   forecast, None)
        got = embed.fields[0].name.replace("⌁ ", "")
        flag = "" if got == label else f"  <span class=bad>(engine devolveu {got})</span>"
        slots.append(card(label, forecast.win_chance, embed).replace(
            f'<p class="cap">{label}', f'<p class="cap">{got}{flag}'))

    page = f"""<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>
<title>Roleta da previsao</title><style>
body{{background:#313338;color:#dbdee1;font:15px/1.55 'Segoe UI',system-ui,sans-serif;margin:0;padding:28px}}
h1{{color:#f2f3f5;font-size:22px;margin:0 0 4px}}
p.sub{{color:#949ba4;font-size:13px;margin:0 0 8px;max-width:760px}}
p.note{{color:#e6a23c;font-size:13px;margin:0 0 24px;max-width:760px}}
h2{{color:#f2f3f5;font-size:15px;margin:26px 0 8px}}
.embed{{background:#2b2d31;border-radius:8px;border-left:4px solid #888;padding:12px 16px;max-width:440px;margin-bottom:6px}}
.title{{color:#fff;font-weight:700;font-size:16px;margin-bottom:6px}}
.desc{{color:#dbdee1;margin:4px 0 8px}}
.big{{font-size:20px;font-weight:700;color:#fff;margin:6px 0}}
.fname{{color:#fff;font-weight:600;font-size:14px;margin-bottom:2px}}
.fval{{color:#dbdee1;font-size:14px}}
.art{{display:block;width:100%;margin-top:10px;border-radius:4px;image-rendering:pixelated}}
.footer{{color:#949ba4;font-size:12px;margin-top:10px}}
.slot{{margin-bottom:22px}}
.cap{{color:#949ba4;font:12px ui-monospace,Consolas,monospace;margin:0 0 6px}}
.bad{{color:#e05252}}
table{{border-collapse:collapse;font:12px ui-monospace,Consolas,monospace;margin-top:8px}}
td,th{{padding:3px 10px;border-bottom:1px solid #3a3c41;text-align:left}}
th{{color:#949ba4}}
code{{background:#1e1f22;padding:1px 5px;border-radius:3px}}
</style></head><body>
<h1>Roleta da previsao</h1>
<p class=sub>Cinco GIFs, um por rotulo de <code>forecast_label()</code> em
<code>src/domain/combat/engine.py:21</code>. Canvas 80&times;45, escala 6&times;,
nearest-neighbor, 82&thinsp;KB cada. A roda para com o setor do forecast
sob a agulha, entao a imagem concorda com o numero do campo acima dela.</p>
<p class="note">O campo do embed continua sendo a fonte da verdade. A imagem
nao calcula nada: ela so evita que o preview pareca decoracao solta.</p>
<h2>Nos cinco casos</h2>
{"".join(slots)}
<h2>Como o bot escolhe</h2>
<table>
<tr><th>forecast_label</th><th>faixa</th><th>gif</th><th>pipas</th></tr>
<tr><td>HOPELESS</td><td>&lt; 20%</td><td>roulette_hopeless.gif</td><td>1</td></tr>
<tr><td>STRUGGLING</td><td>&lt; 40%</td><td>roulette_struggling.gif</td><td>2</td></tr>
<tr><td>NEUTRAL</td><td>&lt; 60%</td><td>roulette_neutral.gif</td><td>3</td></tr>
<tr><td>FAVORED</td><td>&lt; 80%</td><td>roulette_favored.gif</td><td>4</td></tr>
<tr><td>DOMINATING</td><td>&ge; 80%</td><td>roulette_dominating.gif</td><td>5</td></tr>
</table>
</body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
