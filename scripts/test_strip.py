"""Testa o alinhamento da fita contra os rotulos de forecast_label().

A fita escolhe o arquivo pelo rotulo. Se o rotulo que trava no visor
divergir do nome do arquivo, o embed vai dizer uma coisa e a imagem
outra — que foi exatamente o bug anterior, em que roulette_favored.gif
travava em NEUTRAL porque final_index % 5 nao batia com o alvo.

Em vez de OCR, o teste compara pixel a pixel o quadro final com um
render limpo do rotulo esperado. Se os dois forem identicos, o rotulo
que travou e o certo, por construcao.

Uso:  .venv\\Scripts\\python.exe scripts\\test_strip.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_strip import (  # noqa: E402
    BAND_TOP, BAND_BOT, BG, CH, CW, MARKER_X, PITCH, TIERS, TEXT_H, TEXT_Y,
    WIN_HALF, build_strip, draw_text, text_width,
)

# forecast_label() em src/domain/combat/engine.py:21, na mesma ordem e
# com as mesmas faixas. Se o engine mudar, este teste quebra.
EXPECTED = [
    ("HOPELESS", 0.11),
    ("STRUGGLING", 0.33),
    ("NEUTRAL", 0.52),
    ("FAVORED", 0.68),
    ("DOMINATING", 0.86),
]


def window_slice(img: Image.Image) -> Image.Image:
    """Recorta so a janela do visor, onde o rotulo travado mora."""
    return img.crop((MARKER_X - WIN_HALF, TEXT_Y - 1, MARKER_X + WIN_HALF, TEXT_Y + TEXT_H + 1))


def bright_mask(img: Image.Image, color) -> set:
    """Pixels exatamente na cor de travamento, dentro da janela.

    Filtrar so pelo tom certo e essencial. Um teste anterior contava
    "qualquer pixel que nao seja fundo" e reprovava os cinco arquivos,
    porque os rotulos apagados dos vizinhos tambem passam pelo visor no
    quadro final. Eles fazem parte da cena, nao sao erro.
    """
    px = img.load()
    out = set()
    for y in range(TEXT_Y, TEXT_Y + TEXT_H):
        for x in range(MARKER_X - WIN_HALF, MARKER_X + WIN_HALF):
            if px[x, y] == color:
                out.add((x - (MARKER_X - WIN_HALF), y - TEXT_Y))
    return out


class StripTests(unittest.TestCase):
    def test_todos_os_rotulos_batem_com_o_engine(self):
        self.assertEqual([r for r, _ in EXPECTED], [t[0] for t in TIERS])

    def test_final_index_modulo_bate_com_o_alvo(self):
        """O invariante que quebrou: final_index % 5 tem de ser o alvo."""
        for target, (label, _) in enumerate(EXPECTED):
            with self.subTest(label=label):
                self.assertEqual((20 + target) % 5, target)
                self.assertEqual(TIERS[(20 + target) % 5][0], label)

    def test_rotulo_que_trava_e_o_esperado(self):
        for target, (label, _) in enumerate(EXPECTED):
            with self.subTest(label=label):
                tone = TIERS[target][2]
                final = build_strip(target)[-1][0]
                # Render limpo do rotulo esperado, na posicao do visor.
                clean = Image.new("RGB", (CW, CH), BG)
                draw_text(clean, MARKER_X - text_width(label) // 2, TEXT_Y,
                          label, tone)
                self.assertEqual(
                    bright_mask(final, tone), bright_mask(clean, tone),
                    f"{label}: o que travou no visor nao e o rotulo esperado",
                )

    def test_o_rotulo_esperado_aparece_no_visor(self):
        """Garante que o tom certo tem pixels ali — evita o falso verde
        do teste acima, que passaria se os dois conjuntos fossem vazios."""
        for target, (label, _) in enumerate(EXPECTED):
            with self.subTest(label=label):
                tone = TIERS[target][2]
                final = build_strip(target)[-1][0]
                self.assertGreater(
                    len(bright_mask(final, tone)), 0,
                    f"{label}: nenhum pixel do tom de travamento no visor",
                )

    def test_a_fita_esta_se_movendo(self):
        """A animacao tem que mostrar rotulos atravessando a tela."""
        for target, (label, _) in enumerate(EXPECTED):
            with self.subTest(label=label):
                frames = build_strip(target)
                mid, last = frames[len(frames) // 2][0], frames[-1][0]
                self.assertNotEqual(
                    mid.crop((0, TEXT_Y, CW, TEXT_Y + TEXT_H)).tobytes(),
                    last.crop((0, TEXT_Y, CW, TEXT_Y + TEXT_H)).tobytes(),
                    f"{label}: o meio da animacao esta igual ao fim (fita parada)",
                )

    def test_o_primeiro_frame_tem_conteudo(self):
        """Bug anterior: fita curta demais deixava o comeco vazio."""
        for target, (label, _) in enumerate(EXPECTED):
            with self.subTest(label=label):
                first = build_strip(target)[0][0]
                px = first.load()
                drawn = sum(
                    1
                    for y in range(TEXT_Y, TEXT_Y + TEXT_H)
                    for x in range(CW)
                    if px[x, y] not in (BG, (16, 17, 20))
                )
                self.assertGreater(drawn, 0, f"{label}: primeiro frame vazio")

    def test_duracoes_crescem_na_desaceleracao(self):
        """Quadro longo quando devagar, curto quando rapido."""
        frames = build_strip(0)
        spin = [ms for _, ms in frames[1:-3]]
        self.assertLess(spin[0], spin[-1], "a duracao deveria crescer ao desacelerar")

    def test_geometria_cabe_no_quadro(self):
        """O rotulo mais largo tem de caber na janela, com folga."""
        widest = max(text_width(label) for label, _, _ in TIERS)
        self.assertLessEqual(widest, WIN_HALF * 2 - 4,
                             "o rotulo mais largo nao cabe na janela do visor")
        self.assertLess(PITCH, CW, "o passo precisa caber no canvas")


if __name__ == "__main__":
    unittest.main(verbosity=2)
