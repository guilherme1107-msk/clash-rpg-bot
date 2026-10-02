"""Folhas de contato da fita: percurso e os cinco travados.

Gera duas imagens estaticas para conferir o resultado sem esperar o loop:
uma com o percurso frame a frame, outra com as cinco variantes paradas.

Uso:  .venv\\Scripts\\python.exe scripts\\strip_sheets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_strip import CH, CW, TIERS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GIFS = ROOT / "assets" / "gifs"
OUT = ROOT / "scripts" / "sheet"
OUT.mkdir(parents=True, exist_ok=True)


def frames_of(name: str) -> list[Image.Image]:
    out = []
    with Image.open(GIFS / name) as im:
        for i in range(im.n_frames):
            im.seek(i)
            out.append(im.convert("RGB").copy())
    return out


def sheet(frames: list[Image.Image], scale: int, rows: int, bg=(49, 51, 56)) -> Image.Image:
    w, h = frames[0].size
    tw, th = w * scale, h * scale
    pad, lab = 4, 12
    cols = (len(frames) + rows - 1) // rows
    out = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad + lab) + pad), bg)
    d = ImageDraw.Draw(out)
    for i, im in enumerate(frames):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + pad + lab)
        out.paste(im.resize((tw, th), Image.NEAREST), (x, y + lab))
        d.text((x + 1, y), f"f{i}", fill=(210, 210, 215))
    return out


def main() -> None:
    path = sheet(frames_of("roulette_favored.gif"), scale=3, rows=3)
    path.save(OUT / "strip_path.png")

    stops = [frames_of(f"roulette_{label.lower()}.gif")[-1] for label, _, _ in TIERS]
    five = sheet(stops, scale=3, rows=1)
    d = ImageDraw.Draw(five)
    for i, (label, _, _) in enumerate(TIERS):
        w = CW * 3
        d.text((4 + i * (w + 4) + 1, 2), label, fill=(210, 210, 215))
    five.save(OUT / "strip_five.png")

    print(OUT / "strip_path.png")
    print(OUT / "strip_five.png")


if __name__ == "__main__":
    main()
