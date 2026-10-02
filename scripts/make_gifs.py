"""Gera GIFs próprios para os embeds — sem depender de link de terceiro.

Por que gerar em vez de linkar: o clash_gifs.example.txt diz "use somente URLs
diretas para arquivos próprios ou licenciados". Um GIF desenhado aqui é
próprio por definição, não tem copyright de terceiro e não depende do Tenor
continuar no ar (o projeto já tem uma cadeia frágil em attach_damage_gif
que precisa raspar a página do Tenor para achar a mídia).

Estado encontrado na inspeção:

* clash_gifs.txt NÃO EXISTE -> clash_gif_for() devolve None sempre -> as
  chamadas set_image de prediction_embed, queued_clash_embed e
  animated_embed nunca disparam.
* DAMAGE_RESOLUTION_GIF está vazio no .env -> attach_damage_gif() retorna
  None no primeiro if -> damage_embed, o embed mais usado do bot, nunca
  recebeu imagem.
* Só UNBREAKABLE_FOLLOWUP_GIF está preenchido (meme do Don Quixote).

Ou seja: o caminho do código existe, o conteúdo é que não. Estes GIFs
preenchem o lado que falta.

Uso:  .venv\\Scripts\\python.exe scripts\\make_gifs.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "gifs"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 480, 270
SS = 2  # supersampling: desenha grande e reduz, para borda lisa
BG = (24, 25, 28)
ACCENT = (179, 24, 36)
GOLD = (202, 164, 75)
WHITE = (245, 245, 247)
EMBER = (232, 140, 60)


def canvas() -> tuple[Image.Image, Image.Draw]:
    img = Image.new("RGB", (W * SS, H * SS), BG)
    return img, ImageDraw.Draw(img)


def vignette(img: Image.Image, strength: int = 42) -> Image.Image:
    """Escurece so o extremo das bordas.

    A primeira versao usava 90 com uma elipse estreita, e acabava
    apagando justamente a regiao onde a acao acontece. O vinheta existe
    para o GIF nao brigar com o fundo do embed, nao para escurecer a cena.
    """
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    w, h = img.size
    d.ellipse((-w * 0.45, -h * 0.85, w * 1.45, h * 1.85), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(w // 10))
    dark = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, strength / 255), mask)


def glow_layer(size, draw_fn) -> Image.Image:
    """Desenha numa camada e borra devagar, para virar halo."""
    layer = Image.new("RGB", size, (0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return layer


def add_glow(img: Image.Image, layer: Image.Image, factor: float = 1.0) -> None:
    """Borra curto e mistura por screen: o resultado brilha em vez de virar lama.

    A versao anterior borrava em size/40 e colava com peso 0.75, o que
    transformava qualquer brilho forte numa mancha marrom. Screen mantem
    o preto intacto e so soma luz.
    """
    if factor <= 0:
        return
    tight = layer.filter(ImageFilter.GaussianBlur(img.size[0] // 150 + 1))
    wide = layer.filter(ImageFilter.GaussianBlur(img.size[0] // 55 + 2))
    halo = ImageChops.screen(tight, Image.eval(wide, lambda v: int(v * 0.55)))
    halo = Image.eval(halo, lambda v: min(255, int(v * factor)))
    img.paste(ImageChops.screen(img, halo), (0, 0))


def core(img: Image.Image, cx: float, cy: float, radius: float, color, strength: float) -> None:
    """Nucleo quente que persiste no fim da animacao.

    Sem isto os 40% finais das animacoes de impacto ficam vazios: o
    anel ja saiu do quadro e nao ha mais nada acontecendo.
    """
    if strength <= 0:
        return
    layer = Image.new("RGB", img.size, (0, 0, 0))
    d = ImageDraw.Draw(layer)
    steps = 7
    for i in range(steps, 0, -1):
        f = i / steps
        r = radius * f
        a = (1 - f) ** 1.6 * strength
        d.ellipse((cx - r, cy - r, cx + r, cy + r),
                  fill=tuple(int(c * a) for c in color))
    layer = layer.filter(ImageFilter.GaussianBlur(img.size[0] // 70 + 2))
    img.paste(ImageChops.screen(img, layer), (0, 0))


def save(frames: list[Image.Image], name: str, duration: int = 70) -> Path:
    out = []
    for f in frames:
        small = f.resize((W, H), Image.LANCZOS)
        out.append(small.convert("P", palette=Image.ADAPTIVE, colors=128))
    path = OUT / name
    out[0].save(
        path, save_all=True, append_images=out[1:],
        duration=duration, loop=0, optimize=True, disposal=2,
    )
    return path


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


# ═══════════════════════════════════════════════════════════════════
# 1. coin_flip.gif  ->  prediction_embed / queued_prediction_embed
#    A moeda gira em 3D (elipse que afina) e pousa em HEADS.
#    É a imagem certa para o momento da previsão: o jogo inteiro é
#   _heads/tails, e hoje esse embed não tem imagem nenhuma.
# ═══════════════════════════════════════════════════════════════════
def coin_flip() -> list[Image.Image]:
    frames = []
    cx, cy, r = W * SS * 0.5, H * SS * 0.47, 66 * SS
    total = 26
    for i in range(total):
        img, d = canvas()
        t = i / (total - 1)
        # Rotacao: 3 voltas completas desacelerando.
        turns = 3.0
        angle = t * turns * math.tau
        # O flip achata na ALTURA. Achar na largura fazia a moeda parecer
        # um ovo girando em torno do eixo vertical, que nao e um flip.
        squash = abs(math.cos(angle))

        # Halo dourado que intensifica conforme a moeda desacelera.
        def halo(dl, t=t):
            a = 0.35 + 0.65 * ease_out(t)
            rr = r * (1.06 + 0.14 * t)
            dl.ellipse((cx - rr, cy - rr, cx + rr, cy + rr),
                       outline=tuple(int(c * a) for c in GOLD), width=int(14 * SS * a) or 2)
        add_glow(img, glow_layer(img.size, halo), 0.55 + 0.45 * t)

        # Movimento vertical: sobe e desce no pouso.
        lift = math.sin(t * math.pi) * -20 * SS
        cyy = cy + lift
        # A altura e o que varia; a largura e constante.
        rh = r * squash

        # Contorno: quanto mais fina, mais brilhante.
        edge = max(2, int(4 * SS))
        if squash < 0.30:
            edge = int(6 * SS)
        d.ellipse((cx - r, cyy - max(rh, 1.5 * SS), cx + r, cyy + max(rh, 1.5 * SS)),
                  outline=GOLD, width=edge)

        # Face HEADS legivel apenas quando a moeda esta aberta.
        if squash > 0.52:
            alpha = min(1.0, (squash - 0.52) / 0.30)
            shade = tuple(int(c * alpha) for c in WHITE)
            arm, thick = int(r * 0.30), int(4 * SS)
            # Um H de verdade: dois tracos verticais e a travessa. A versao
            # anterior desenhava uma linha horizontal e uma vertical, o que
            # saia como "+" e nao lia como a face HEADS.
            d.line((cx - arm, cyy - arm, cx - arm, cyy + arm), fill=shade, width=thick)
            d.line((cx + arm, cyy - arm, cx + arm, cyy + arm), fill=shade, width=thick)
            d.line((cx - arm, cyy, cx + arm, cyy), fill=shade, width=thick)
        elif squash > 0.22:
            # Marca de borda para a moeda nao virar um risco vazio.
            a = int(150 * (squash - 0.22) / 0.30)
            d.ellipse((cx - r * 0.72, cyy - rh * 0.72, cx + r * 0.72, cyy + rh * 0.72),
                      outline=tuple(int(c * a / 255) for c in GOLD), width=int(2 * SS))

        # Pouso: anel de choque no chão.
        if t > 0.82:
            p = (t - 0.82) / 0.18
            rr = r * (1.0 + 1.5 * ease_out(p))
            a = int(200 * (1 - p))
            if a > 4:
                d.ellipse((cx - rr * 1.5, cyy + r * 0.86 - rr * 0.14,
                           cx + rr * 1.5, cyy + r * 0.86 + rr * 0.14),
                          outline=tuple(int(c * a / 255) for c in GOLD), width=max(1, int(2 * SS)))

        # Faixa de chão.
        d.line((cx - r * 2.6, cyy + r * 0.86, cx + r * 2.6, cyy + r * 0.86),
               fill=(52, 54, 58), width=int(2 * SS))

        frames.append(vignette(img))
    return frames


# ═══════════════════════════════════════════════════════════════════
# 2. damage_resolution.gif  ->  damage_embed
#    O embed mais usado do bot e hoje está com DAMAGE_RESOLUTION_GIF
#    vazio no .env. Esta é a lacuna que mais vale fechar.
# ═══════════════════════════════════════════════════════════════════
def damage_resolution() -> list[Image.Image]:
    frames = []
    cx, cy = W * SS * 0.5, H * SS * 0.52
    for i in range(28):
        img, d = canvas()
        t = i / 27

        if t < 0.30:
            # Antecipacao: a lamina desce da direita.
            p = t / 0.30
            sx = W * SS * 1.05
            sy = H * SS * (-0.10 + 0.55 * p)
            d.line((sx, sy, sx - 190 * SS, sy + 150 * SS), fill=(210, 214, 222), width=int(9 * SS))
            d.line((sx, sy, sx - 190 * SS, sy + 150 * SS), fill=WHITE, width=int(3 * SS))
            d.line((sx, sy, sx - 240 * SS, sy + 190 * SS), fill=(120, 124, 132), width=int(2 * SS))
        else:
            p = (t - 0.30) / 0.70
            # Flash de impacto.
            if p < 0.10:
                a = 1 - p / 0.10
                d.ellipse((cx - 70 * SS * (0.4 + p), cy - 70 * SS * (0.4 + p),
                           cx + 70 * SS * (0.4 + p), cy + 70 * SS * (0.4 + p)),
                          fill=tuple(int(c * a) for c in WHITE))
            # Linhas radiais.
            rays = 14
            for k in range(rays):
                ang = (k / rays) * math.tau + p * 0.6
                inner = (26 + 150 * ease_out(p)) * SS
                outer = (26 + 150 * ease_out(p) + 60 * (1 - p)) * SS
                a = int(235 * (1 - p) ** 1.4)
                if a <= 3:
                    continue
                col = ACCENT if k % 2 else EMBER
                d.line((cx + math.cos(ang) * inner, cy + math.sin(ang) * inner * 0.82,
                        cx + math.cos(ang) * outer, cy + math.sin(ang) * outer * 0.82),
                       fill=tuple(int(c * a / 255) for c in col), width=int(3 * SS))
            # Onda de choque. O raio e limitado de proposito: deixar crescer
            # ate 210 deixava o circulo maior que o quadro e o resultado era
            # um arco fino e quase invisivel nas bordas.
            for ring, delay in ((0.0, 0.0), (0.24, 0.32)):
                q = p - delay
                if 0 <= q < 0.75:
                    rr = ease_out(q / 0.75) * 148 * SS
                    a = int(215 * (1 - q / 0.75))
                    d.ellipse((cx - rr, cy - rr * 0.82, cx + rr, cy + rr * 0.82),
                              outline=tuple(int(c * a / 255) for c in WHITE), width=int(3 * SS))
            # Brasas caindo.
            for k in range(10):
                seed = (k * 37) % 11
                px = cx + (seed - 5) * 26 * SS + p * (seed - 5) * 34 * SS
                py = cy + p * (70 + seed * 16) * SS
                a = int(220 * (1 - p))
                if a > 4:
                    d.ellipse((px - 2 * SS, py - 2 * SS, px + 2 * SS, py + 2 * SS),
                              fill=tuple(int(c * a / 255) for c in EMBER))
            # Rachadura no "piso".
            if p > 0.18:
                q = min(1.0, (p - 0.18) / 0.5)
                for k in range(5):
                    a0 = math.pi + (k - 2) * 0.34
                    x0, y0 = cx + math.cos(a0) * 40 * SS, cy + 60 * SS
                    x1, y1 = cx + math.cos(a0) * (40 + 120 * q) * SS, cy + 60 * SS
                    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2 + 9 * SS
                    d.line((x0, y0, xm, ym), fill=ACCENT, width=int(2 * SS))
                    d.line((xm, ym, x1, y1), fill=ACCENT, width=int(2 * SS))

        def halo(dl, p=max(0.0, (t - 0.30) / 0.70)):
            a = max(0.0, 1 - p) * 0.9
            rr = (60 + 110 * ease_out(p)) * SS
            dl.ellipse((cx - rr, cy - rr * 0.82, cx + rr, cy + rr * 0.82),
                       outline=tuple(int(c * a) for c in ACCENT), width=int(20 * SS * a) or 2)
        add_glow(img, glow_layer(img.size, halo), 0.7)
        # Nucleo quente que nao deixa a segunda metade vazia.
        core(img, cx, cy, 54 * SS, EMBER, max(0.0, 1 - (t - 0.34) / 0.66) * 0.85)

        frames.append(vignette(img))
    return frames


# ═══════════════════════════════════════════════════════════════════
# 3. clash_impact.gif  ->  queued_clash_embed / animated_embed
#    Duas laminas colidem no centro. O "CLASH ENGAGED" e o painel que
#    se re-edita a cada rodada ganham uma imagem so dramaticamente.
# ═══════════════════════════════════════════════════════════════════
def clash_impact() -> list[Image.Image]:
    frames = []
    cx, cy = W * SS * 0.5, H * SS * 0.5
    for i in range(26):
        img, d = canvas()
        t = i / 25
        shake = 0

        if t < 0.34:
            # As duas laminas se aproximam.
            p = t / 0.34
            reach = 120 * SS + ease_out(p) * 118 * SS
            for sign, tone in ((-1, (222, 226, 234)), (1, (188, 192, 200))):
                d.line((cx + sign * reach, cy - sign * 62 * SS,
                        cx + sign * (reach - 108 * SS), cy + sign * 16 * SS),
                       fill=tone, width=int(8 * SS))
                d.line((cx + sign * reach, cy - sign * 62 * SS,
                        cx + sign * (reach - 108 * SS), cy + sign * 16 * SS),
                       fill=WHITE, width=int(2 * SS))
        else:
            p = (t - 0.34) / 0.66
            shake = int((1 - p) * 9 * SS) if p < 0.35 else 0
            # Tremor shorteno: a colisao sacode a moldura e depois acalma.
            # Faisca central em cruz.
            s = 90 * SS * (1 + 0.5 * (1 - min(1, p * 3)))
            a = int(250 * max(0.0, 1 - p * 1.25))
            if a > 5:
                d.line((cx - s, cy, cx + s, cy), fill=tuple(int(c * a / 255) for c in WHITE), width=int(5 * SS))
                d.line((cx, cy - s * 0.72, cx, cy + s * 0.72), fill=tuple(int(c * a / 255) for c in WHITE), width=int(5 * SS))
            # Faiscas radiais: joga particulas em todas as direcoes.
            sparks = 18
            for k in range(sparks):
                ang = (k / sparks) * math.tau + 0.3
                sp = 40 + (k % 5) * 34
                dist = (sp + 190 * ease_out(p)) * SS
                a = int(240 * (1 - p) ** 1.3)
                if a <= 4:
                    continue
                col = GOLD if k % 3 == 0 else ACCENT
                x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist * 0.78
                r = max(1, int(3 * SS * (1 - p)))
                d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(c * a / 255) for c in col))
            # Onda de choque, com raio limitado ao quadro.
            q = p
            rr = ease_out(q / 0.8) * 150 * SS
            a = int(225 * (1 - q / 0.8))
            if a > 4:
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr),
                          outline=tuple(int(c * a / 255) for c in GOLD),
                          width=int(3 * SS))

        def halo(dl, p=max(0.0, (t - 0.34) / 0.66)):
            a = max(0.0, 1 - p) * 0.9
            rr = (52 + 128 * ease_out(p)) * SS
            dl.ellipse((cx - rr, cy - rr, cx + rr, cy + rr),
                       outline=tuple(int(c * a) for c in GOLD), width=int(22 * SS * a) or 2)
        add_glow(img, glow_layer(img.size, halo), 0.6 + 0.4 * max(0.0, 1 - t))
        # Nucleo: sem ele o terco final fica vazio depois que o anel sai.
        core(img, cx, cy, 46 * SS, WHITE, max(0.0, 1 - (t - 0.34) / 0.66) * 0.9)

        out = vignette(img)
        if shake:
            out = out.transform(out.size, Image.AFFINE, (1, 0, -shake, 0, 1, int(shake * 0.4)),
                                resample=Image.BILINEAR, fillcolor=BG)
        frames.append(out)
    return frames


# ═══════════════════════════════════════════════════════════════════
# 4. shield_absorb.gif  ->  etapa de escudo do damage_embed
#    O escudo e a unica etapa do dano que NAO pertence ao atacante.
#    Vale uma imagem propria para o mestre ver "isto foi absorvido".
# ═══════════════════════════════════════════════════════════════════
def shield_absorb() -> list[Image.Image]:
    """O escudo e a unica etapa do dano que nao pertence ao atacante.

    A primeira versao desenhava as ondas e as trincas num ponto ACIMA do
    hexagono, o que deixava um rabisco vermelho flutuando sem relacao com a
    barreira. Aqui o impacto acontece no vertice superior do hexagono e as
    trincas descem para dentro dele: e a leitura de "segurou".
    """
    frames = []
    cx, cy = W * SS * 0.5, H * SS * 0.54
    rad = 104 * SS
    top = (cx, cy - rad * 0.88)  # vertice superior: onde o golpe bate

    def hexagon(ccx, ccy, r):
        return [(ccx + math.cos(math.radians(60 * k - 30)) * r,
                 ccy + math.sin(math.radians(60 * k - 30)) * r * 0.88) for k in range(6)]

    for i in range(28):
        img, d = canvas()
        t = i / 27

        # --- barreira em fade ---
        appear = min(1.0, max(0.0, (t - 0.12) / 0.16))
        fade = 1 - max(0.0, (t - 0.72) / 0.28)
        shield_a = appear * fade
        if shield_a > 0.02:
            pts = hexagon(cx, cy, rad)
            a = int(225 * shield_a)
            d.polygon(pts, outline=tuple(int(c * a) for c in GOLD), width=int(3 * SS))
            d.polygon(pts, outline=tuple(int(c * a * 0.28) for c in GOLD), width=int(12 * SS))
            # Preenchimento bem leve para a barreira ter corpo.
            d.polygon(pts, fill=(26, 30, 34) if shield_a > 0.3 else None)

        # --- impacto no vertice superior ---
        if t > 0.28:
            p = (t - 0.28) / 0.72
            # Flash no ponto de contato.
            if p < 0.10:
                f = 1 - p / 0.10
                rr = 26 * SS * (0.5 + p * 6)
                d.ellipse((top[0] - rr, top[1] - rr, top[0] + rr, top[1] + rr),
                          fill=tuple(int(c * f) for c in WHITE))
            # Ondas concentricas ancoradas no ponto de impacto.
            for k in range(3):
                q = p - k * 0.17
                if 0 <= q < 0.78:
                    rr = ease_out(q / 0.78) * rad * 1.25
                    a = int(235 * (1 - q / 0.78))
                    if a > 5:
                        col = WHITE if k == 0 else GOLD
                        d.arc((top[0] - rr, top[1] - rr, top[0] + rr, top[1] + rr),
                              start=8, end=172,
                              fill=tuple(int(c * a / 255) for c in col), width=int(3 * SS))
            # Trincas descendo do vertice para dentro do escudo.
            if p > 0.16:
                grow = min(1.0, (p - 0.16) / 0.5)
                a = int(235 * (1 - max(0.0, (p - 0.62) / 0.38)))
                if a > 5:
                    for k in range(7):
                        # Leque para baixo: de 200 a 340 graus.
                        ang = math.radians(200 + k * 23)
                        x1 = top[0] + math.cos(ang) * rad * 0.95 * grow
                        y1 = top[1] + math.sin(ang) * rad * 0.80 * grow
                        xm = (top[0] + x1) / 2 + (k - 3) * 3 * SS
                        ym = (top[1] + y1) / 2
                        tone = tuple(int(c * a / 255) for c in ACCENT)
                        d.line((top[0], top[1], xm, ym), fill=tone, width=int(2 * SS))
                        d.line((xm, ym, x1, y1), fill=tone, width=int(2 * SS))
            # A barreira segura: contrai um pouco e o brilho baixa por dentro.
            if p > 0.55:
                q = (p - 0.55) / 0.45
                a = int(150 * (1 - q))
                if a > 5:
                    pts = hexagon(cx, cy, rad * (1 - 0.05 * q))
                    d.polygon(pts, outline=tuple(int(c * a / 255) for c in GOLD), width=int(2 * SS))

        def halo(dl, p=max(0.0, (t - 0.28) / 0.72)):
            a = max(0.0, 1 - p) * 0.75
            rr = (34 + 96 * ease_out(p)) * SS
            dl.ellipse((top[0] - rr, top[1] - rr * 0.9, top[0] + rr, top[1] + rr * 0.9),
                       outline=tuple(int(c * a) for c in GOLD), width=int(18 * SS * a) or 2)
        add_glow(img, glow_layer(img.size, halo), 0.55)
        # Nucleo no ponto de impacto, para a segunda metade nao ficar vazia.
        core(img, top[0], top[1], 40 * SS, GOLD, max(0.0, 1 - (t - 0.28) / 0.72) * 0.8)

        frames.append(vignette(img))
    return frames


def main() -> None:
    jobs = [
        ("coin_flip.gif", coin_flip, "prediction_embed / queued_prediction_embed"),
        ("damage_resolution.gif", damage_resolution, "damage_embed (DAMAGE_RESOLUTION_GIF vazio)"),
        ("clash_impact.gif", clash_impact, "queued_clash_embed / animated_embed"),
        ("shield_absorb.gif", shield_absorb, "etapa de escudo do damage_embed"),
    ]
    for name, fn, target in jobs:
        path = save(fn(), name)
        kb = path.stat().st_size / 1024
        print(f"{name:24} {kb:7.1f} KB  -> {target}")
    print(f"\nsalvos em {OUT}")


if __name__ == "__main__":
    main()
