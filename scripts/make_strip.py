"""roulette_<label>.gif — fita lateral da previsao, em pixel art.

Substitui a roda. Um disco de 34px com cinco setores era grande demais
para o que comunicava, e acertar o setor dependia de meio angulo. Aqui a
leitura e literal: os cinco nomes passam da esquerda para a direita e
param no visor.

    HOPELESS → STRUGGLING → NEUTRAL → FAVORED → DOMINATING
       1           2           3          4           5

Visor
-----
O visor e uma moldura FIXA no centro; o texto passa por cima dela. O
rotulo que esta dentro da janela ganha o tom claro da propria rampa, e
isso e o "trancar": nao ha seta animada nem numero, so a mudanca de tom.
Nomes fora da janela ficam no tom escuro, mas continuam visiveis — eles
sao o contexto, e e ver a fita passar que da sensacao de roleta.

A primeira versao recortava tudo fora da janela. O resultado era o
oposto do pedido: os nomes que deveriam passar ficavam invisiveis, e o
visor virava um buraco preto com uma palavra dentro.

Texto
-----
Fonte 3x5 autorada no arquivo. Fonte de sistema daria antialias e
suavizaria a borda, que e o que nao pode acontecer num sprite.

Velocidade
----------
"para rapido" e levante a risca: 1,05s no total e 320ms parado, contra
2,65s e 620ms da roda.

Uso:  .venv\\Scripts\\python.exe scripts\\make_strip.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "gifs"
OUT.mkdir(parents=True, exist_ok=True)

CW, CH = 96, 54           # 96*5=480, 54*5=270, escala inteira
SCALE = 5

BG = (22, 23, 26)
BAND_TOP, BAND_BOT = 17, 37
MARKER_X = 48             # centro do visor
PITCH = 48                # 96/48 = dois rotulos visiveis ao mesmo tempo
WIN_HALF = 24             # meia janela: a cabeca exatamente um rotulo
GLYPH, GLYPH_GAP, TEXT_H = 3, 1, 5
TEXT_Y = BAND_TOP + (BAND_BOT - BAND_TOP - TEXT_H) // 2

# (rotulo, tom fora do visor, tom dentro do visor)
#
# Os tons fora do visor ficam bem mais escuros de proposito. Na primeira
# versao o DOMINATING parado (184,142,42) era quase tao claro quanto o
# FAVORED travado (244,204,100), e nao ficava claro qual tinha travado.
# O contraste entre dim e bright e o que faz o visor funcionar.
TIERS = [
    ("HOPELESS",   (48, 53, 63),  (150, 160, 178)),
    ("STRUGGLING", (78, 30, 32),  (222, 100, 90)),
    ("NEUTRAL",    (72, 74, 80),  (206, 210, 218)),
    ("FAVORED",    (92, 68, 22),  (246, 206, 102)),
    ("DOMINATING", (116, 90, 28), (253, 240, 176)),
]

FONT = {
    "A": ["###", "#.#", "###", "#.#", "#.#"],
    "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".#."],
    "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#.#", "###", "###", "#.#", "#.#"],
    "N": ["#.#", "###", "###", "###", "#.#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."],
    "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#.#", "#.#", "###", "###", "#.#"],
    "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."],
    "Z": ["###", "..#", ".#.", "#..", "###"],
}


def text_width(label: str) -> int:
    return len(label) * (GLYPH + GLYPH_GAP) - GLYPH_GAP


def draw_text(img: Image.Image, x: int, y: int, label: str, color) -> None:
    px = img.load()
    cursor = x
    for char in label:
        glyph = FONT.get(char)
        if glyph:
            for row, line in enumerate(glyph):
                for col, cell in enumerate(line):
                    if cell != "#":
                        continue
                    gx, gy = cursor + col, y + row
                    if 0 <= gx < CW and 0 <= gy < CH:
                        px[gx, gy] = color
        cursor += GLYPH + GLYPH_GAP


def base(img: Image.Image) -> None:
    """Faixa e moldura do visor. Nao se move com o texto."""
    px = img.load()
    for y in range(BAND_TOP, BAND_BOT):
        for x in range(CW):
            px[x, y] = (52, 55, 62) if y in (BAND_TOP, BAND_BOT - 1) else (16, 17, 20)
    # Travessas do visor, nas duas pontas da janela.
    for y in range(BAND_TOP - 2, BAND_BOT + 2):
        edge = y in (BAND_TOP - 2, BAND_BOT + 1)
        for x in (MARKER_X - WIN_HALF, MARKER_X + WIN_HALF):
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = (238, 238, 242) if edge else (74, 78, 86)
    # Setas apontando para dentro, acima e abaixo.
    for i in range(4):
        span = i * 2 + 1
        for dx in range(span):
            x = MARKER_X - i + dx
            for y in (BAND_TOP - 6 + i, BAND_BOT + 5 - i):
                if 0 <= x < CW and 0 <= y < CH:
                    px[x, y] = (238, 238, 242)


def build_strip(target: int):
    # A fita precisa cobrir o percurso inteiro, senao o comeco da animacao
    # sai vazio. Com PITCH=48 e travel de dois ciclos, o primeiro indice
    # visivel fica em final_index + ~9; por isso total bem maior que o
    # indice final. Antes, total=18 deixava o item alvo fora da fita e o
    # GIF era fundido para um unico frame.
    total = 38
    items = [i % len(TIERS) for i in range(total)]
    # final_index tem que satisfazer final_index % 5 == target. Com 20 a
    # conta fecha; com 19 fechava no rotulo ANTERIOR e a fita travava em
    # NEUTRAL dentro do arquivo favored.
    final_index = 20 + target

    target_w = text_width(TIERS[target][0])
    # Centralizacao INTEIRA. A versao anterior usava
    # MARKER_X - target_w/2, que com largura impar dava 48 - 19.5 = 28.5 e
    # o round() dentro do compose caia em 28 — o rotulo travava 1px a
    # esquerda do centro da janela. Afetava todo rotulo de largura impar.
    scroll_end = final_index * PITCH - (MARKER_X - target_w // 2)
    travel = PITCH * len(TIERS) * 2
    scroll_start = scroll_end + travel

    def compose(scroll: float) -> Image.Image:
        img = Image.new("RGB", (CW, CH), BG)
        base(img)
        for index, tier_index in enumerate(items):
            label, dim, bright = TIERS[tier_index]
            w = text_width(label)
            left = index * PITCH - scroll
            if left > CW or left + w < 0:
                continue
            inside = abs(left + w / 2 - MARKER_X) <= WIN_HALF - 2
            draw_text(img, round(left), TEXT_Y, label, bright if inside else dim)
        # Esmaece as pontas em vez de recortar: o rotulo entra e sai em vez
        # de sumir de repente na borda.
        px = img.load()
        for y in range(BAND_TOP + 1, BAND_BOT - 1):
            for x in list(range(0, 4)) + list(range(CW - 4, CW)):
                px[x, y] = (32, 34, 40)
        return img

    frames: list[tuple[Image.Image, int]] = []
    frames.append((compose(scroll_start), 50))
    spin = 9
    for i in range(1, spin + 1):
        t = i / spin
        eased = 1 - (1 - t) ** 2.1
        # A duracao CRESCE conforme a fita desacelera. A primeira versao
        # usava 38 + 42*(1-t)^1.4, o que dava 74ms no comeco e 38ms no fim:
        # quadro longo quando corre rapido e curto quando quase parada. Era
        # o oposto de peso, e a cauda da animacao parecia travada.
        ms = int(32 + 40 * t ** 1.3)
        frames.append((compose(scroll_start + (scroll_end - scroll_start) * eased), ms))
    # Encaixe final: ainda anda alguns pixels e desacelera de vez, para o
    # alvo assentar no visor em vez de parar seco no meio de um frame.
    for k in range(2):
        t = (k + 1) / 2
        frames.append((compose(scroll_end - 6 * (1 - (1 - t) ** 3)), 50))
    frames.append((compose(scroll_end), 260))
    return frames


def write(target: int) -> Path:
    label = TIERS[target][0].lower()
    frames = build_strip(target)
    prepared = []
    for img, ms in frames:
        big = img.resize((CW * SCALE, CH * SCALE), Image.NEAREST)
        prepared.append((big.convert("P", palette=Image.ADAPTIVE, colors=32), ms))
    path = OUT / f"roulette_{label}.gif"
    prepared[0][0].save(
        path, save_all=True, append_images=[p for p, _ in prepared[1:]],
        duration=[ms for _, ms in prepared], loop=0, optimize=True, disposal=1,
    )
    total_s = sum(ms for _, ms in frames) / 1000
    print(f"roulette_{label + '.gif':26} {path.stat().st_size / 1024:5.0f} KB  "
          f"{len(prepared):2} frames  {total_s:.2f}s  -> {TIERS[target][0]}")
    return path


def main() -> None:
    for target in range(len(TIERS)):
        write(target)
    print(f"\ncanvas {CW}x{CH} • escala {SCALE}x NEAREST • fonte 3x5 • "
          f"passo {PITCH}px • visor em x={MARKER_X} (meia {WIN_HALF})")


if __name__ == "__main__":
    main()
