"""A fita lateral dentro do prediction_embed real.

GIF solto nao prova nada. O que importa e ver a imagem na posicao exata
do embed, com o rotulo do forecast logo acima dela — porque a promessa
do conceito e que os dois concordem.

Uso:  .venv\\Scripts\\python.exe scripts\\preview_strip_context.py
"""

from __future__ import annotations

import base64
import html
import io
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_stripctx.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "strip-ctx-only")

from PIL import Image, ImageDraw  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import Modifiers, Skill, SkillEffect, prediction_with_paralysis  # noqa: E402

GIFS = ROOT / "assets" / "gifs"
OUT = ROOT / "scripts" / "preview_strip.html"

# (rotulo, chance) — mesma ordem de forecast_label() em engine.py:21
CASES = [
    ("HOPELESS", 0.11), ("STRUGGLING", 0.33), ("NEUTRAL", 0.52),
    ("FAVORED", 0.68), ("DOMINATING", 0.86),
]


def data_uri(name: str) -> str:
    return "data:image/gif;base64," + base64.b64encode((GIFS / name).read_bytes()).decode()


def md(text: str) -> str:
    out = html.escape(text or "").replace("`", "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"^#{1,3}\s*(.+)$", r'<div class="big">\1</div>', out, flags=re.M)
    return out.replace("\n", "<br>")


def embed_html(embed) -> str:
    color = f"#{embed.colour.value:06x}"
    p = [f'<div class="embed" style="border-left-color:{color}">']
    if embed.title:
        p.append(f'<div class="title">{md(embed.title)}</div>')
    if embed.description:
        p.append(f'<div class="desc">{md(embed.description)}</div>')
    for f in embed.fields:
        p.append(f'<div class="fname">{md(f.name)}</div><div class="fval">{md(f.value)}</div>')
    p.append("</div>")
    return "".join(p)


def path_sheet(label: str, scale: int = 3) -> str:
    """O percurso frame a frame, para ver a fita passar."""
    name = f"roulette_{label.lower()}.gif"
    frames = []
    with Image.open(GIFS / name) as im:
        for i in range(im.n_frames):
            im.seek(i)
            frames.append(im.convert("RGB").copy())
    w, h = frames[0].size
    tw, th = w // 3 * scale, h // 3 * scale
    pad = 4
    rows = 3
    cols = (len(frames) + rows - 1) // rows
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad + 12) + pad),
                      (49, 51, 56))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(frames):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + pad + 12)
        sheet.paste(im.resize((tw, th), Image.NEAREST), (x, y + 12))
        d.text((x + 1, y), f"f{i}", fill=(210, 210, 215))
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def main() -> None:
    left = Skill("Corte Ascendente", 14, 6, 3, "", "attack",
                 effects=(SkillEffect("on_hit", "bleed", 3, count=2),))
    right = Skill("Riposte Punida", 11, 4, 2, "", "counter")

    slots = []
    for label, chance in CASES:
        boost = (chance - 0.5) * 60
        forecast = prediction_with_paralysis(
            left, 0, right, 0, Modifiers(0, 0, 0, 0, int(round(boost))), Modifiers())
        embed = B.prediction_embed("Yi Sang", left, "Cavaleiro Aberrante",
                                   right, forecast, None)
        got = embed.fields[0].name.replace("⌁ ", "")
        flag = "" if got == label else f' <span class="bad">engine devolveu {got}</span>'
        slots.append(
            f'<div class="slot"><p class="cap">{got} — {forecast.win_chance:.0%}{flag}</p>'
            f'{embed_html(embed)}'
            f'<img class="art" src="{data_uri("roulette_" + label.lower() + ".gif")}"></div>'
        )

    b64 = path_sheet("FAVORED")
    sizes = " · ".join(
        f'<code>roulette_{l.lower()}.gif</code> {(GIFS / f"roulette_{l.lower()}.gif").stat().st_size / 1024:.0f} KB'
        for l, _ in CASES)

    page = f"""<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>
<title>Fita lateral da previsao</title><style>
body{{background:#313338;color:#dbdee1;font:15px/1.55 'Segoe UI',system-ui,sans-serif;margin:0;padding:28px}}
h1{{color:#f2f3f5;font-size:22px;margin:0 0 4px}}
h2{{color:#f2f3f5;font-size:15px;margin:26px 0 6px}}
p.sub,p.note{{color:#949ba4;font-size:13px;margin:0 0 20px;max-width:780px}}
p.cap{{color:#949ba4;font:12px ui-monospace,Consolas,monospace;margin:0 0 6px}}
p.note{{color:#e6a23c}}
.embed{{background:#2b2d31;border-radius:8px;border-left:4px solid #888;padding:12px 16px;max-width:430px}}
.title{{color:#fff;font-weight:700;font-size:16px;margin-bottom:6px}}
.desc{{color:#dbdee1;margin:4px 0 8px}}
.big{{font-size:20px;font-weight:700;color:#fff;margin:6px 0}}
.fname{{color:#fff;font-weight:600;font-size:14px;margin-bottom:2px}}
.fval{{color:#dbdee1;font-size:14px}}
.art{{display:block;width:430px;max-width:100%;margin-top:8px;border-radius:4px;image-rendering:pixelated}}
.slot{{margin-bottom:24px}}
.bad{{color:#e05252}}
code{{background:#1e1f22;padding:1px 5px;border-radius:3px}}
.path{{display:block;max-width:100%;border-radius:4px}}
table{{border-collapse:collapse;font:12px ui-monospace,Consolas,monospace;margin-top:8px}}
td,th{{padding:3px 10px;border-bottom:1px solid #3a3c41;text-align:left}}
th{{color:#949ba4}}
</style></head><body>
<h1>Fita lateral da previsao</h1>
<p class=sub>Cinco GIFs, um por rotulo de <code>forecast_label()</code> em
<code>engine.py:21</code>. Canvas 96&times;54, escala inteira 5&times;, nearest-neighbor,
fonte 3x5 autorada. Os nomes passam da esquerda para a direita e param no
visor em <b>0,87s</b> — a roda levava 2,65s. {sizes}.</p>
<p class="note">O visor e uma moldura fixa. O rotulo que entra nele ganha o tom
claro da propria rampa, e esse contraste e o "trancar": os vizinhos continuam
visiveis, mas apagados. Sem seta animada, sem numero.</p>

<h2>Nos cinco casos, dentro do embed real</h2>
{"".join(slots)}

<h2>O percurso frame a frame (FAVORED)</h2>
<img class="path" src="data:image/png;base64,{b64}">

<h2>Como o bot escolhe</h2>
<table>
<tr><th>forecast_label</th><th>faixa</th><th>gif</th></tr>
<tr><td>HOPELESS</td><td>&lt; 20%</td><td>roulette_hopeless.gif</td></tr>
<tr><td>STRUGGLING</td><td>&lt; 40%</td><td>roulette_struggling.gif</td></tr>
<tr><td>NEUTRAL</td><td>&lt; 60%</td><td>roulette_neutral.gif</td></tr>
<tr><td>FAVORED</td><td>&lt; 80%</td><td>roulette_favored.gif</td></tr>
<tr><td>DOMINATING</td><td>&ge; 80%</td><td>roulette_dominating.gif</td></tr>
</table>
</body></html>"""
    OUT.with_suffix(".tmp.png").unlink(missing_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
