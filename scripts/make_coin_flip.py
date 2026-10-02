"""coin_flip.gif em pixel art — versão refeita following research.

Regras vindas da pesquisa (as tres que eu violava antes):

1. Nearest-neighbor e ESCALA INTEIRA. A versao anterior desenhava em
   960x540 e reduzia com LANCZOS, o que produz vetor suavizado, nao pixel.
   Aqui se desenha em 80x45 e cada pixel vira um bloco 6x6 (480x270).
   Escala nao-inteira deixa linhas verticais com espessuras diferentes.

2. Poucos frames com timing DESIGUAL. Fontes de animacao de sprite dizem
   que 4 a 8 frames e o padrao real de jogos entregues, e que segurar o
   frame de impacto mais longo e o que separa trabalho amador de
   profissional. Aqui sao 16 frames, mas o pouso dura 460ms contra os
   60ms do topo da rotacao.

3. Giro por LARGURA/ALTURA em pixels inteiros, sem interpolacao. A
   ilusao de 3D vem da grade encolher, nao de um retangulo escalado.

4. Sem antialias e paleta curta. Rampa de ouro de 6 tons mais contorno.

Uso:  .venv\\Scripts\\python.exe scripts\\make_coin_flip.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "gifs"
OUT.mkdir(parents=True, exist_ok=True)

CW, CH = 80, 45          # canvas de baixa resolucao
SCALE = 6                # 80*6=480, 45*6=270, escala inteira
CX, CY = 40, 22          # centro da moeda no canvas
BASE = 16                # diametro da moeda cheia

# Rampas curtas, estilo 8-bit: 6 tons por metal, sem gradiente e sem
# antialias. Sao DUAS rampas porque as duas faces precisam se separar em
# tres canais ao mesmo tempo — forma do emblema, tom do metal e brilho.
# Com uma rampa so, o anel de TAILS usava a mesma cor do highlight e
# desaparecia dentro da propria moeda. A referencia de OpenGameArt
# (Clint Bellanger, moedas de ouro/prata/cobre) resolve o mesmo problema
# do mesmo jeito: uma rampa por moeda.
GOLD = {
    "o": (26, 18, 8),      # contorno
    "d": (74, 51, 17),     # sombra
    "m": (117, 82, 26),    # medio
    "l": (166, 121, 40),   # claro
    "h": (206, 158, 62),   # destaque
    "b": (240, 206, 122),  # brilho
    "w": (253, 246, 218),  # glint
}
COPPER = {
    "o": (34, 15, 10),
    "d": (92, 42, 24),
    "m": (128, 60, 33),
    "l": (166, 84, 45),
    "h": (203, 112, 59),
    "b": (231, 154, 92),
    "w": (250, 208, 158),
}
TRANSPARENT = (24, 25, 28)  # igual ao BG do embed, entao nao ha borda visivel


def new_canvas() -> Image.Image:
    return Image.new("RGB", (CW, CH), TRANSPARENT)


def ellipse(img: Image.Image, cx: int, cy: int, rx: int, ry: int, color) -> None:
    """Preenche uma elipse em pixels INTEIROS, sem antialias.

    Varre linha a linha e pinta uma corrida horizontal. Como as bordas sao
    arredondadas para inteiro, o resultado ja e pixel art: nao existe
    meio pixel em nenhum ponto.
    """
    if rx < 0 or ry < 0:
        return
    px = img.load()
    for y in range(cy - ry, cy + ry + 1):
        # Normalizado: dentro = |dx/rx|^2 + |dy/ry|^2 <= 1
        dy = (y - cy) / (ry or 1)
        span = int(rx * (1 - dy * dy) ** 0.5 + 0.5) if abs(dy) <= 1 else -1
        if span < 0:
            continue
        for x in range(cx - span, cx + span + 1):
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = color


def ring(img: Image.Image, cx: int, cy: int, r: int, color) -> None:
    """Anel de 1px: emblema da face TAILS."""
    px = img.load()
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and not (
                (x - cx) ** 2 + (y - cy) ** 2 <= (r - 1) ** 2
            ):
                if 0 <= x < CW and 0 <= y < CH:
                    px[x, y] = color


def diamond(img: Image.Image, cx: int, cy: int, r: int, color) -> None:
    """Losango CONTORNADO de 1px: emblema da face HEADS.

    A primeira versao preenchia o losango e punha um miolo branco. Com 5px
    de altura isso vira uma mancha de brilho e as duas faces ficam
    indistinguiveis — justamente o que o jogador precisa ler. Contorno
    aberto separa as formas sem competir com o glint.
    """
    px = img.load()
    for y in range(cy - r, cy + r + 1):
        span = r - abs(y - cy)
        if span == 0:
            continue
        for x in (cx - span, cx + span):
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = color
    # Fecha as pontas.
    for y in (cy - r, cy + r):
        for x in (cx - 1, cx, cx + 1):
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = color


def bar(img: Image.Image, cx: int, cy: int, half_w: int, color) -> None:
    """Barra horizontal: emblema auxiliar de TAILS."""
    px = img.load()
    for y in range(cy - 1, cy + 2):
        for x in range(cx - half_w, cx + half_w + 1):
            if 0 <= x < CW and 0 <= y < CH:
                px[x, y] = color


def coin(img: Image.Image, cy: int, rx: int, ry: int, *, face: str) -> None:
    """Desenha a moeda com o diametro pedido.

    Tres estados de face:

    * "heads" — ouro + losango contornado
    * "tails" — cobre + anel contornado
    * "back"  — disco sem emblema, tom chapado

    O "back" existe porque a versao anterior trocava de face no meio da
    rotacao e pousava no cobre, para virar ouro no frame seguinte. O
    salto lia como glitch. Mostrando o verso durante a volta e a face
    so no pouso, nao ha discontinuidade: e assim que coin flip aparece
    em jogo.

    As faces se separam por tres canais ao mesmo tempo — metal, formato
    do emblema e brilho. Com um canal so o jogador nao sabe qual caiu.
    """
    r = COPPER if face == "tails" else GOLD
    px = img.load()

    ellipse(img, CX, cy, rx + 1, ry + 1, r["o"])   # contorno
    ellipse(img, CX, cy, rx, ry, r["m"])           # corpo

    if face == "back":
        # O verso precisa ser LISO. A primeira versao reaproveitava as
        # elipses aninhadas do brilho e elas apareciam como circulos
        # concentricos no centro — ou seja, o verso tinha um "emblema" e
        # o jogador via um anel no meio da rotacao. Aqui nao ha brilho
        # radial: so a sombra da base e um ponto de luz deslocado, que
        # nao se confunde com simbolo.
        for y in range(cy + max(0, ry - 2), cy + ry + 1):
            for x in range(CX - (rx - 1), CX + rx):
                if 0 <= x < CW and 0 <= y < CH and px[x, y] == r["m"]:
                    px[x, y] = r["d"]
        if rx >= 5 and ry >= 5:
            px[CX - rx // 2, cy - ry // 2] = r["l"]
            px[CX - rx // 2, cy - ry // 2 + 1] = r["d"]
    else:
        # Luz do alto-esquerda, em dois degraus.
        ellipse(img, CX, cy - 1, rx - 1, ry - 1, r["l"])
        ellipse(img, CX, cy - 2, rx - 2, max(0, ry - 3), r["h"])
        # Sombra na base, para o disco nao ficar chapado.
        for y in range(cy + max(0, ry - 2), cy + ry + 1):
            for x in range(CX - (rx - 1), CX + rx):
                if 0 <= x < CW and 0 <= y < CH and px[x, y] == r["m"]:
                    px[x, y] = r["d"]

        # Emblema contornado, no brilho maximo da rampa. O raio e
        # limitado por min(3, ...) porque com 4 o losango preenchia a
        # moeda inteira nos frames achatados da antecipacao.
        if rx >= 5 and ry >= 5:
            if face == "heads":
                diamond(img, CX, cy, min(3, ry - 2), r["b"])
            else:
                ring(img, CX, cy, min(3, ry - 2), r["b"])

    # Glint no canto superior esquerdo, longe do emblema para nao competir
    # com ele. So no ouro e com a moeda bem aberta.
    if face == "heads" and rx >= 7 and ry >= 7:
        gx, gy = CX - rx + 2, cy - ry + 2
        for dy in range(2):
            for dx in range(2):
                if 0 <= gx + dx < CW and 0 <= gy + dy < CH:
                    px[gx + dx, gy + dy] = r["w"]


def shadow(img: Image.Image, ground_y: int, rx: int, strength: float) -> None:
    """Sombra no chao: encolhe e some quando a moeda sobe.

    A primeira versao pintava um traco de 1px quase preto, que no canvas
    de 80x45 virava uma sujeira. Aqui a sombra e uma elipse achatada de
    dois tons, e so aparece com forca acima de um piso.
    """
    if strength <= 0.12 or rx < 2:
        return
    px = img.load()
    fade = (strength - 0.12) / 0.88
    core_w = max(1, int(rx * (0.55 + 0.45 * fade)))
    soft_w = max(core_w + 1, int(rx * (1.05 + 0.5 * fade)))
    dark = (16, 17, 19)
    softer = (20, 21, 24)
    for x in range(CX - soft_w, CX + soft_w + 1):
        if not (0 <= x < CW and 0 <= ground_y < CH):
            continue
        if px[x, ground_y] != TRANSPARENT:
            continue
        px[x, ground_y] = dark if abs(x - CX) <= core_w else softer


# ═══════════════════════════════════════════════════════════════════
#  Storyboard
#  A altura da moeda e a unica variavel livre. Os valores sao alturas
#  inteiras: 16 cheia, 2 quase de perfil, 1 a linha de perfil.
#  A troca de face acontece na virada, como numa moeda real.
# ═══════════════════════════════════════════════════════════════════
GROUND = 33

# (cy, rx, ry, face, duracao_ms, sombra, papel)
#
# face = "A" usa a face sorteada no pouso. Durante a volta o verso
# ("back") aparece, entao a virada acontece no instante em que a moeda
# pousa — sem salto de imagem no meio da animacao.
STORYBOARD = [
    ( 32,  9,  6, "A",  90, 1.00, "antecipacao: achata antes de subir"),
    ( 28,  7, 10, "A",  60, 0.72, "lancamento: estica na direcao do movimento"),
    ( 22,  8,  8, "b",  60, 0.34, "topo da rotacao, verso a mostra"),
    ( 20,  7,  7, "b",  60, 0.30, "descida acelerando"),
    ( 18,  6,  6, "b",  65, 0.28, ""),
    ( 16,  5,  4, "b",  70, 0.26, ""),
    ( 15,  3,  2, "b",  75, 0.25, "quase de perfil"),
    ( 14,  2,  1, "b",  80, 0.25, "perfil: a linha"),
    ( 15,  3,  2, "b",  80, 0.25, "sai do perfil, ainda verso"),
    ( 17,  5,  4, "b",  85, 0.27, ""),
    ( 20,  6,  6, "b",  90, 0.30, ""),
    ( 24,  7,  7, "A",  95, 0.36, "virada: a face aparece no ar"),
    ( 29,  8,  8, "A", 110, 0.55, "pouso"),
    ( 31,  9,  6, "A",  90, 1.00, "amortecao: o peso do impacto"),
    ( 32,  8,  8, "A", 460, 1.00, "SEGURA no resultado: o frame mais longo"),
    ( 32,  8,  8, "A", 140, 1.00, "volta ao repouso"),
]


def build(result: str) -> list[tuple[Image.Image, int]]:
    frames = []
    for cy, rx, ry, face, ms, sh, _ in STORYBOARD:
        img = new_canvas()
        shadow(img, GROUND, rx, sh)
        coin(img, cy, rx, ry, face=result if face == "A" else face)
        frames.append((img, ms))
    return frames


def write(result: str, name: str) -> Path:
    frames = build(result)
    # Duplica o primeiro frame no fim para o loop nao piscar ao reiniciar.
    frames.append((frames[0][0], 120))

    prepared = []
    for img, ms in frames:
        big = img.resize((CW * SCALE, CH * SCALE), Image.NEAREST)
        prepared.append((big.convert("P", palette=Image.ADAPTIVE, colors=64), ms))

    path = OUT / name
    prepared[0][0].save(
        path,
        save_all=True,
        append_images=[p for p, _ in prepared[1:]],
        duration=[ms for _, ms in prepared],
        loop=0,
        optimize=True,
        disposal=1,
    )
    total = sum(ms for _, ms in frames) / 1000
    print(f"{name:20} {path.stat().st_size / 1024:5.0f} KB  "
          f"{len(prepared)} frames  {total:.2f}s  cai em {result.upper()}")
    return path


def main() -> None:
    # As duas variantes. O bot pode escolher pela previsao: se o forecast
    # favorece o atacante, mostra heads; se o destino e pior, tails. A
    # imagem deixa de ser enfeite e passa a concordar com o texto do embed.
    write("heads", "coin_heads.gif")
    write("tails", "coin_tails.gif")
    print(f"\ncanvas {CW}x{CH} • escala {SCALE}x NEAREST • "
          f"{len(GOLD)} tons de ouro + {len(COPPER)} de cobre")


if __name__ == "__main__":
    main()
