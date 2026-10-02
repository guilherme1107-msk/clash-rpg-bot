"""Exporta frames das duas variantes em PNG, para ver o resultado estatico.

O leitor de imagem mostra so o primeiro frame de um GIF. Esta pagina
mostra a animacao inteira montada em PNGs, o que permite conferir cada
momento sem depender do loop.

Uso:  .venv\\Scripts\\python.exe scripts\\export_coin_frames.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
GIFS = ROOT / "assets" / "gifs"
OUT = ROOT / "scripts" / "sheet"

# Frames que contam a historia. Nao sao todos de proposito: a repeticao
# no meio da rotacao nao acrescenta leitura.
PICKS = [0, 1, 2, 4, 7, 9, 11, 12, 13, 14, 15]


def read(path: Path) -> list[Image.Image]:
    frames = []
    with Image.open(path) as im:
        for i in range(im.n_frames):
            im.seek(i)
            frames.append(im.convert("RGB").copy())
    return frames


def row(frames: list[Image.Image], picks: list[int]) -> Image.Image:
    tw, th = 160, 90
    pad, lab = 6, 11
    sheet = Image.new(
        "RGB",
        (len(picks) * (tw + pad) + pad, th + lab + pad * 2),
        (49, 51, 56),
    )
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(picks):
        if n >= len(frames):
            continue
        x = pad + i * (tw + pad)
        tile = frames[n].resize((tw, th), Image.NEAREST)
        sheet.paste(tile, (x, pad + lab))
        d.text((x + 1, pad), f"f{n}", fill=(210, 210, 215))
        d.rectangle((x, pad + lab, x + tw - 1, pad + lab + th - 1),
                    outline=(80, 82, 88))
    return sheet


def main() -> None:
    heads = read(GIFS / "coin_heads.gif")
    tails = read(GIFS / "coin_tails.gif")

    rh = row(heads, PICKS)
    rt = row(tails, PICKS)
    gap = 12
    combined = Image.new(
        "RGB", (max(rh.width, rt.width), rh.height + rt.height + gap), (49, 51, 56)
    )
    combined.paste(rh, (0, 0))
    combined.paste(rt, (0, rh.height + gap))
    combined.save(OUT / "coin_both.png")

    print(f"frames heads: {len(heads)}  tails: {len(tails)}")
    print(OUT / "coin_both.png")


if __name__ == "__main__":
    main()
