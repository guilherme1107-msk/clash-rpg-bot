"""Folha de contato: frames-chave de cada GIF, lado a lado, para inspecao.

Nao envia nada. Serve para ver o que os GIFs estao fazendo frame a frame
antes de plugar no bot.

Uso:  .venv\\Scripts\\python.exe scripts\\gif_contact_sheet.py
"""

from __future__ import annotations

import html
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
GIFS = ROOT / "assets" / "gifs"

# nome -> indices de frame que valem a inspecao
PICKS = {
    "coin_flip.gif": [0, 4, 8, 12, 16, 19, 21, 23, 25],
    "damage_resolution.gif": [0, 5, 8, 10, 12, 14, 17, 21, 26],
    "clash_impact.gif": [0, 4, 7, 9, 11, 13, 16, 20, 24],
    "shield_absorb.gif": [0, 4, 8, 11, 14, 17, 21, 24, 27],
}

# O GIF e 480x270. A primeira versao da folha usava um tile 200x200 e
# redimensionava direto, o que achatava a imagem na horizontal: uma moeda
# redonda aparecia como oval e a inspecao levava a "consertar" um bug que
# nao existia. O tile agora respeita o aspecto.
TILE_W, TILE_H = 220, 124
PAD = 10
LABEL = 16


def strip(path: Path, indices: list[int]) -> Image.Image:
    frames = []
    with Image.open(path) as im:
        total = im.n_frames
        for i in indices:
            im.seek(min(i, total - 1))
            frames.append((i, im.convert("RGB").copy()))
    cols = len(frames)
    width = cols * TILE_W + (cols + 1) * PAD
    height = TILE_H + LABEL + PAD * 2
    sheet = Image.new("RGB", (width, height), (49, 51, 56))
    d = ImageDraw.Draw(sheet)
    for idx, (num, frame) in enumerate(frames):
        tile = frame.resize((TILE_W, TILE_H), Image.LANCZOS)
        x = PAD + idx * (TILE_W + PAD)
        sheet.paste(tile, (x, PAD + LABEL))
        d.text((x + 2, PAD + 2), f"f{num}", fill=(200, 200, 205))
        d.rectangle((x, PAD + LABEL, x + TILE_W - 1, PAD + LABEL + TILE_H - 1),
                    outline=(80, 82, 88))
    return sheet


def main() -> None:
    rows = []
    for name, indices in PICKS.items():
        path = GIFS / name
        if not path.exists():
            continue
        kb = path.stat().st_size / 1024
        with Image.open(path) as im:
            frames, ms = im.n_frames, im.info.get("duration")
        rows.append(f'<h2>{html.escape(name)} '
                    f'<small>{frames} frames • {ms}ms • {kb:.0f} KB</small></h2>')
        rows.append(f'<img src="gifs/{html.escape(name)}">')
        rows.append('<p class="sub">frames-chave:</p>')
        rows.append(f'<img src="sheet/{html.escape(name)}.png">')

    page = (
        "<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>"
        "<title>Inspeção de GIF</title><style>"
        "body{background:#313338;color:#dbdee1;font:14px/1.5 'Segoe UI',system-ui,sans-serif;"
        "margin:0;padding:24px}"
        "h2{color:#f2f3f5;font-size:15px;margin:22px 0 8px}"
        "h2 small{color:#949ba4;font-weight:400;font-size:12px}"
        "p.sub{color:#949ba4;font-size:12px;margin:4px 0}"
        "img{max-width:100%;display:block;border-radius:4px}"
        "</style></head><body>"
        "<h1>Animação completa e frames-chave</h1>"
        "<p class=sub>Loop animationado em cima; abaixo, o que acontece em cada instante.</p>"
        + "".join(rows) + "</body></html>"
    )

    sheet_dir = ROOT / "scripts" / "sheet"
    sheet_dir.mkdir(exist_ok=True)
    for name, indices in PICKS.items():
        path = GIFS / name
        if path.exists():
            strip(path, indices).save(sheet_dir / f"{name}.png")

    (ROOT / "scripts" / "preview_gifs.html").write_text(page, encoding="utf-8")
    print(ROOT / "scripts" / "preview_gifs.html")


if __name__ == "__main__":
    main()
