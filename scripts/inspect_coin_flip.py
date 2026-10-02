"""Inspecao do coin_flip em pixel art: frames em tamanho real +Ampliados.

Mostra duas coisas que a animacao esconde quando roda:
* o canvas de 80x45 como ele e de fato (pixels de 1px), que e onde se
  ve se a silhueta esta limpa;
* cada frame ampliado 6x, que e como o Discord vai mostrar.

Uso:  .venv\\Scripts\\python.exe scripts\\inspect_coin_flip.py
"""

from __future__ import annotations

import html
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
GIF = ROOT / "assets" / "gifs" / "coin_heads.gif"

CELL = 150   # celula do canvas ampliado
PAD = 8
NATIVE = 4   # ampliacao do canvas 80x45 para inspecao


def read_frames() -> list[Image.Image]:
    frames = []
    with Image.open(GIF) as im:
        for i in range(im.n_frames):
            im.seek(i)
            frames.append(im.convert("RGB").copy())
    return frames


def grid(frames: list[Image.Image], scale: int) -> Image.Image:
    w, h = frames[0].size
    tw, th = w * scale, h * scale
    cols = 6
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + PAD) + PAD, rows * (th + PAD + 12) + PAD), (49, 51, 56))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        x = PAD + c * (tw + PAD)
        y = PAD + r * (th + PAD + 12)
        sheet.paste(f.resize((tw, th), Image.NEAREST), (x, y + 12))
        d.text((x + 1, y), f"f{i}", fill=(210, 210, 215))
    return sheet


def main() -> None:
    frames = read_frames()
    with Image.open(GIF) as im:
        total_ms = sum(
            im.seek(i) or im.info.get("duration", 0) for i in range(im.n_frames)
        ) / 1000

    grid(frames, 3).save(ROOT / "scripts" / "sheet" / "coin_natural.png")
    grid(frames, 2).save(ROOT / "scripts" / "sheet" / "coin_frames.png")

    native = grid(frames, NATIVE)
    native.save(ROOT / "scripts" / "sheet" / "coin_native.png")

    durations = []
    with Image.open(GIF) as im:
        for i in range(im.n_frames):
            im.seek(i)
            durations.append(im.info.get("duration", 0))

    rows = "".join(
        f'<tr><td>f{i}</td><td>{d} ms</td>'
        f'<td><img src="sheet/coin_frames_{i}.png" alt="f{i}"></td></tr>'
        for i, d in enumerate(durations)
    )
    # exporta cada frame separado para a tabela
    for i, f in enumerate(frames):
        f.resize((f.width * 2, f.height * 2), Image.NEAREST).save(
            ROOT / "scripts" / "sheet" / f"coin_frames_{i}.png"
        )

    page = f"""<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>
<title>coin_flip em pixel art</title><style>
body{{background:#313338;color:#dbdee1;font:14px/1.5 'Segoe UI',system-ui,sans-serif;margin:0;padding:26px}}
h1{{color:#f2f3f5;font-size:21px;margin:0 0 4px}}
p.sub{{color:#949ba4;font-size:13px;margin:0 0 22px;max-width:720px}}
h2{{color:#f2f3f5;font-size:15px;margin:24px 0 6px}}
img{{image-rendering:pixelated;display:block;max-width:100%}}
.loop{{border:1px solid #1e1f22;border-radius:6px;background:#18191c;padding:8px;width:500px}}
table{{border-collapse:collapse;font:12px ui-monospace,Consolas,monospace}}
td,th{{padding:2px 8px;border-bottom:1px solid #3a3c41;text-align:left}}
th{{color:#949ba4}}
code{{background:#1e1f22;padding:1px 5px;border-radius:3px}}
</style></head><body>
<h1>coin_flip.gif — pixel art</h1>
<p class=sub>Canvas {frames[0].width}x{frames[0].height}, escala inteira 6x com NEAREST.
{len(frames)} frames, {total_ms:.2f}s. O GIF tem {GIF.stat().st_size/1024:.0f} KB
— o vetorial anterior pesava 393 KB.</p>

<h2>Loop completo — cai em HEADS</h2>
<div class=loop><img src="../assets/gifs/coin_heads.gif" alt="heads"></div>

<h2>Loop completo — cai em TAILS</h2>
<div class=loop><img src="../assets/gifs/coin_tails.gif" alt="tails"></div>

<h2>Canvas 1:1 (cada pixel é 1 pixel) — é aqui que a silhueta se julga</h2>
<img src="sheet/coin_native.png" alt="nativo">

<h2>Frames com a duração de cada um</h2>
<table><tr><th>frame</th><th>duração</th><th></th></tr>{rows}</table>
</body></html>"""

    out = ROOT / "scripts" / "preview_coin.html"
    out.write_text(page, encoding="utf-8")
    print(out)
    print("durações:", ", ".join(f"{d}ms" for d in durations))


if __name__ == "__main__":
    main()
