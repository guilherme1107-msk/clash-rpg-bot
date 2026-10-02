"""Inspecao das cinco roletas: sectors, pipas e o quadro de parada.

Tres coisas precisam ser conferidas separadamente:

1. A roda parada: os cinco setores tem que ser distinguiveis entre si.
2. A contagem de pipas: 1 a 5, e o numero tem que bater com o rotulo.
3. O quadro de parada: o setor alvo tem que estar exatamente sob a
   agulha. Se o calculo de final_rotation() estiver errado, a imagem
   vai parar num setor e o texto do embed vai falar outro.

Uso:  .venv\\Scripts\\python.exe scripts\\inspect_roulette.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
GIFS = ROOT / "assets" / "gifs"
OUT = ROOT / "scripts" / "sheet"
LABELS = ["hopeless", "struggling", "neutral", "favored", "dominating"]


def frames_of(name: str) -> list[Image.Image]:
    out = []
    with Image.open(GIFS / name) as im:
        for i in range(im.n_frames):
            im.seek(i)
            out.append(im.convert("RGB").copy())
    return out


def band(images: list[Image.Image], scale: int, pad: int = 6) -> Image.Image:
    tw, th = images[0].width * scale, images[0].height * scale
    lab = 11
    sheet = Image.new(
        "RGB", (len(images) * (tw + pad) + pad, th + lab + pad * 2), (49, 51, 56)
    )
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(images):
        x = pad + i * (tw + pad)
        sheet.paste(im.resize((tw, th), Image.NEAREST), (x, pad + lab))
        d.rectangle((x, pad + lab, x + tw - 1, pad + lab + th - 1), outline=(80, 82, 88))
    return sheet


def main() -> None:
    # 1. A roda parada em cada variante, no quadro final.
    stops = []
    for label in LABELS:
        fr = frames_of(f"roulette_{label}.gif")
        stops.append((label, fr[-1]))
    sheet1 = band([im for _, im in stops], 3)

    # 2. A mesma roleta (favored) ao longo do tempo: comeco, meio, parada.
    fr = frames_of("roulette_favored.gif")
    picks = [0, 3, 8, 14, 20, len(fr) - 1]
    sheet2 = band([fr[i] for i in picks], 3)

    # 3. Nativo 1:1 da roda parada, que e onde a divisoria e a pipa se
    # revelam. Em 3x a pipa de 2px parece uma linha.
    sheet3 = band([im for _, im in stops], 5)

    sheet1.save(OUT / "roulette_stops.png")
    sheet2.save(OUT / "roulette_time.png")
    sheet3.save(OUT / "roulette_native.png")

    for label, im in stops:
        with Image.open(GIFS / f"roulette_{label}.gif") as g:
            n = g.n_frames
        print(f"{label:12} {n:2} frames  ultimo frame {im.size}")

    print()
    print(OUT / "roulette_stops.png")
    print(OUT / "roulette_time.png")
    print(OUT / "roulette_native.png")


if __name__ == "__main__":
    main()
