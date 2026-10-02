"""roulette_<label>.gif — roleta de previsao em pixel art.

A ideia substitui a moeda: em vez de uma imagem generica de "heads", a
roleta para no setor que o proprio bot ja calculou. Os cinco rotulos vem
de ``forecast_label()`` em src/domain/combat/engine.py:21:

    HOPELESS  < 20%      STRUGGLING  < 40%      NEUTRAL  < 60%
    FAVORED   < 80%      DOMINATING >= 80%

Cinco GIFs, um por rotulo. O bot escolhe pelo forecast que ja tem na mao,
entao a imagem concorda com o numero em vez de decorar ao lado dele.

Desenho da roda
---------------
Cada pixel do disco e testado em coordenadas polares: o angulo decide o
setor e a cor. Nao ha rotacao de imagem, nao ha interpolacao, nao existe
filtro. Isso importa porque rotacionar arte de pixel art com Lanczos
produz aquela suavizacao que entrega "vetor" em vez de pixel; testando
setor por setor cada frame e geometricamente exato e o recorte continua
duro.

Leitura do nivel
----------------
Cada setor carrega de 1 a 5 pipas ao longo da bissetriz. Assim a
intensidade e lida por contagem, sem depender de cor — e a cor sozinha
nao sobrevive bem a um embed pequeno.

Uso:  .venv\\Scripts\\python.exe scripts\\make_roulette.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "gifs"
OUT.mkdir(parents=True, exist_ok=True)

CW, CH = 80, 45
SCALE = 6                 # 480x270, escala inteira
CX, CY = 40, 25           # centro da roda
R = 17                    # raio: 34px de diametro, sobra a agulha no topo
SEGMENTS = 5
SEG_SPAN = 360 / SEGMENTS

BG = (24, 25, 28)

# (rotulo, corpo, claro, pip, contorno)
#
# A rampa e monotona em brilho: morto, vermelho abafado, cinza medio, ouro,
# ouro quase branco. HOPELESS e NEUTRAL nao podem ser dois cinzas: na
# primeira versao eram quase indistinguiveis e so a contagem de pipas
# separava os dois. HOPELESS e frio e escuro, NEUTRAL e um cinza claramente
# mais claro e mais neutro.
WHEEL = [
    ("HOPELESS",   (38, 41, 50),  (54, 58, 69),  (86, 92, 106), (16, 18, 24)),
    ("STRUGGLING", (94, 32, 36),  (132, 47, 49), (184, 74, 68),  (34, 15, 16)),
    ("NEUTRAL",    (98, 100, 106),(140, 143, 150),(186, 190, 198),(32, 33, 36)),
    ("FAVORED",    (146, 106, 28),(190, 146, 50), (226, 188, 90), (42, 30, 10)),
    ("DOMINATING", (204, 160, 50),(236, 198, 88), (253, 240, 178),(52, 40, 13)),
]


def new_canvas() -> Image.Image:
    return Image.new("RGB", (CW, CH), BG)


def wheel(img: Image.Image, rotation: float) -> None:
    """Desenha a roda girada por `rotation` graus.

    O setor 0 fica centrado na vertical (12h) quando rotation == 0. Por
    isso o indice do setor em um pixel e funcao direta do angulo do pixel
    mais a rotacao — sem nenhuma imagem de referencia rotacionada.
    """
    px = img.load()
    for y in range(CY - R - 1, CY + R + 2):
        for x in range(CX - R - 1, CX + R + 2):
            if not (0 <= x < CW and 0 <= y < CH):
                continue
            dx, dy = x - CX, y - CY
            dist = math.hypot(dx, dy)
            if dist > R:
                continue
            ang = math.degrees(math.atan2(dy, dx))
            # 0 graus aponta para baixo (atan2 com y para baixo). Desloca
            # -90 para o setor 0 cair na vertical, na direcao 12h.
            rel = (ang + 90 - rotation) % 360
            index = int(rel // SEG_SPAN) % SEGMENTS
            _, body, light, pip, rim = WHEEL[index]

            if dist > R - 1:
                color = rim
            else:
                # Iluminacao vinda do alto: quanto mais perto do topo do
                # setor, mais claro. E o que da volume ao disco.
                within = (rel % SEG_SPAN) / SEG_SPAN      # 0..1 no setor
                across = abs(within - 0.5) * 2            # 0 no meio, 1 nas bordas
                color = light if across < 0.22 else body
                # Sombreado na metade de baixo de cada setor.
                if dy > R * 0.45 and dist > R * 0.55:
                    color = rim if dist > R - 2 else body
            px[x, y] = color

    # Divisoria entre setores, no angulo exato de cada limite.
    for k in range(SEGMENTS):
        angle = math.radians(k * SEG_SPAN - 90 + rotation)
        dx, dy = math.cos(angle), math.sin(angle)
        for r in range(2, R):
            x = round(CX + dx * r)
            y = round(CY + dy * r)
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = (16, 17, 20)

    # Pipas de contagem, ao longo da bissetriz de cada setor.
    for index, (_, _, _, pip, _) in enumerate(WHEEL):
        angle = math.radians(index * SEG_SPAN + SEG_SPAN / 2 - 90 + rotation)
        dx, dy = math.cos(angle), math.sin(angle)
        count = index + 1
        for n in range(count):
            r = 4 + n * 3
            x = round(CX + dx * r)
            y = round(CY + dy * r)
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = pip
                # Cada pip e um quadradinho de 2px, nao um ponto solto.
                if 0 <= x + 1 < CW and 0 <= y < CH:
                    px[x + 1, y] = pip


def pointer(img: Image.Image) -> None:
    """Agulha fixa em 12h. Nao gira com a roda — e o referencial."""
    px = img.load()
    tip = (CX, CY - R - 3)
    for i, half in enumerate((0, 1, 2)):
        y = tip[1] + i
        if not (0 <= y < CH):
            continue
        for x in range(CX - half, CX + half + 1):
            if 0 <= x < CW:
                px[x, y] = (240, 240, 244)
    base = CY - R - 1
    for x in range(CX - 2, CX + 3):
        if 0 <= x < CW and 0 <= base < CH:
            px[x, base] = (188, 190, 196)


def hub(img: Image.Image) -> None:
    """Miolo da roda, para os setores nao parecerem fatias soltas."""
    px = img.load()
    for y in range(CY - 2, CY + 3):
        for x in range(CX - 2, CX + 3):
            if 0 <= x < CW and 0 <= y < CH and math.hypot(x - CX, y - CY) <= 2.6:
                px[x, y] = (22, 23, 27)
    px[CX, CY] = (70, 73, 80)


def final_rotation(target: int) -> float:
    """Rotacao que coloca o CENTRO do setor `target` sob a agulha.

    Cuidado com a meia casa. O setor t ocupa rel de t*72 a (t+1)*72, entao
    o centro dele fica em t*72 + 36. A primeira versao devolvia so
    -t*72 e a agulha pousava em cima da divisoria entre dois setores — o
    embed dizia STRUGGLING e a imagem apontava para o meio de dois
    setores ao mesmo tempo. Por isso o +36.
    """
    return (-(target * SEG_SPAN + SEG_SPAN / 2)) % 360


def ease_out(t: float, power: float = 2.6) -> float:
    return 1 - (1 - t) ** power


# (frames, duracao_ms, papel)
# A roleta parte em 5 voltas completas e termina quase parada. O ultimo
# trecho e o que importa: e onde o olho confirma o setor.
TURNS = 5.0
SPIN = 22
STORY = [
    ("antecipacao", 110),
    ("lancamento", 55),
]
HOLD = 620


def build(target: int) -> list[tuple[Image.Image, int]]:
    frames: list[tuple[Image.Image, int]] = []

    # 0: parada antes de girar, ja no neutro para o jogador ter um ref.
    img = new_canvas()
    wheel(img, 0.0)
    pointer(img)
    hub(img)
    frames.append((img, STORY[0][1]))

    # 1..SPIN: a roleta desacelera. A duracao cresce junto com a
    # desaceleração, e o que faz parecer uma roleta e nao um giro solto.
    for i in range(1, SPIN + 1):
        t = i / SPIN
        rot = TURNS * 360 * ease_out(t, 2.6)
        img = new_canvas()
        wheel(img, rot)
        pointer(img)
        hub(img)
        # De 40ms no topo da velocidade a 150ms quase parado.
        ms = int(40 + 110 * (1 - ease_out(t, 1.4)) ** 1.6)
        frames.append((img, max(40, ms)))

    # Pouso: desloca so o resto ate o setor alvo sob a agulha.
    current = TURNS * 360
    dest = TURNS * 360 + final_rotation(target)
    for k in range(3):
        t = (k + 1) / 3
        rot = current + (dest - current) * t
        img = new_canvas()
        wheel(img, rot)
        pointer(img)
        hub(img)
        frames.append((img, 120))

    # Segura no resultado: o frame mais longo da animacao inteira.
    img = new_canvas()
    wheel(img, dest)
    pointer(img)
    hub(img)
    frames.append((img, HOLD))
    return frames


def write(target: int) -> Path:
    label = WHEEL[target][0].lower()
    frames = build(target)
    prepared = []
    for img, ms in frames:
        big = img.resize((CW * SCALE, CH * SCALE), Image.NEAREST)
        prepared.append((big.convert("P", palette=Image.ADAPTIVE, colors=64), ms))
    path = OUT / f"roulette_{label}.gif"
    prepared[0][0].save(
        path, save_all=True, append_images=[p for p, _ in prepared[1:]],
        duration=[ms for _, ms in prepared], loop=0, optimize=True, disposal=1,
    )
    total = sum(ms for _, ms in frames) / 1000
    pip = WHEEL[target][3]
    print(f"roulette_{label + '.gif':26} {path.stat().st_size / 1024:5.0f} KB  "
          f"{len(prepared):2} frames  {total:.2f}s  pip={pip}")
    return path


def main() -> None:
    for target in range(SEGMENTS):
        write(target)
    print(f"\ncanvas {CW}x{CH} • escala {SCALE}x NEAREST • "
          f"{SEGMENTS} setores • {TURNS:g} voltas")
    print("escolha pelo forecast_label() do engine — os cinco nomes batem com ele")


if __name__ == "__main__":
    main()
