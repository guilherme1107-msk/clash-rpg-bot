"""Testa a ligacao entre forecast_label() e a fita de GIFs.

O ponto critico do conceito: o embed diz um rotulo e a imagem precisa
dizer o mesmo. Se divergirem, a fita vira enfeite — que e o oposto do
que ela foi feita para.

Cobre tambem o caminho que dependia de variavel de ambiente: com
DAMAGE_RESOLUTION_GIF vazio no .env, attach_damage_gif devolvia None e o
embed mais usado do bot ficava sem imagem nenhuma.

Uso:  .venv\\Scripts\\python.exe -m unittest discover -s scripts -p test_gif_wiring.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_gifwire.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "gif-wiring-test")

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import Skill, forecast_label  # noqa: E402

# Faixas de forecast_label() em src/domain/combat/engine.py:21
BANDS = [(0.05, "HOPELESS"), (0.30, "STRUGGLING"), (0.50, "NEUTRAL"),
         (0.70, "FAVORED"), (0.90, "DOMINATING")]


class ForecastGifWiring(unittest.TestCase):
    def test_mapa_tem_exatamente_os_rotulos_do_engine(self):
        engine_labels = {forecast_label(c)[0] for c, _ in BANDS}
        self.assertEqual(set(B.FORECAST_GIF), engine_labels)

    def test_toda_faixa_acha_o_gif_certo(self):
        for chance, expected in BANDS:
            with self.subTest(chance=chance):
                label, _ = forecast_label(chance)
                self.assertEqual(label, expected)
                embed = discord.Embed(title="t", color=B.GOLD)
                file = B.attach_forecast_gif(embed, B.Forecast(chance, label, "pt"))
                self.assertIsNotNone(file, f"{label}: nenhum GIF anexado")
                self.assertEqual(
                    embed.image.url, f"attachment://{B.FORECAST_GIF[label]}"
                )

    def test_arquivo_anexado_existe_no_disco(self):
        for label, filename in B.FORECAST_GIF.items():
            with self.subTest(label=label):
                self.assertTrue((B.GIF_ASSETS_DIR / filename).exists())

    def test_rotulo_desconhecido_cai_no_gif_mais_proximo(self):
        """Um forecast novo do engine nao pode deixar a previsao sem imagem."""
        embed = discord.Embed(title="t", color=B.GOLD)
        file = B.attach_forecast_gif(embed, B.Forecast(0.95, "LUCKY", "pt"))
        self.assertIsNotNone(file)
        # O nome do arquivo e minusculo; comparar pelo mapa, e nao por
        # substring em caixa alta.
        self.assertEqual(embed.image.url, f"attachment://{B.FORECAST_GIF['DOMINATING']}")

    def test_attach_asset_nao_quebra_com_arquivo_ausente(self):
        embed = discord.Embed(title="t", color=B.GOLD)
        self.assertIsNone(B.attach_asset(embed, "nao_existe_esse.gif"))
        self.assertIsNone(embed.image.url)

    def test_damage_gif_cai_no_arquivo_proprio(self):
        """O bug original: DAMAGE_RESOLUTION_GIF vazio deixava sem imagem."""
        self.assertEqual(B.DAMAGE_RESOLUTION_GIF, "",
                         "o .env de teste precisa ter DAMAGE_RESOLUTION_GIF vazio")
        embed = discord.Embed(title="t", color=B.ACCENT)
        file = asyncio.run(B.attach_damage_gif(embed))
        self.assertIsNotNone(file, "attach_damage_gif devolveu None")
        self.assertEqual(embed.image.url, f"attachment://{B.DAMAGE_GIF_ASSET}")

    def test_forecast_do_result_reconstroi_o_rotulo(self):
        """Caminho do Activity, que serializa o job em dict."""
        from src.domain.combat import Forecast
        rebuilt = B._forecast_from_result({
            "forecast_chance": 0.72, "forecast_label": "FAVORED",
            "forecast_label_pt": "Favorecido",
        })
        self.assertIsInstance(rebuilt, Forecast)
        self.assertEqual(rebuilt.label, "FAVORED")
        # Sem rotulo no dict: tem de recalcular pela chance.
        bare = B._forecast_from_result({"forecast_chance": 0.11})
        self.assertEqual(bare.label, "HOPELESS")

    def test_prediction_embed_nao_quebra_sem_gif(self):
        """A assinatura antiga aceitava gif=None; continua aceitando."""
        embed = B.prediction_embed(
            "A", Skill("x", 1, 1, 1, "", "attack"),
            "B", Skill("y", 1, 1, 1, "", "attack"),
            B.Forecast(0.7, "FAVORED", "Favorecido"), None,
        )
        self.assertIsNotNone(embed)

    def test_todos_os_embeds_ficam_dentro_do_orcamento(self):
        """GIF nao consome os 6000 caracteres: ele vai como imagem."""
        embed = B.prediction_embed(
            "Yi Sang", Skill("Corte", 14, 6, 3, "", "attack"),
            "Cavaleiro", Skill("Riposte", 11, 4, 2, "", "counter"),
            B.Forecast(0.7, "FAVORED", "Favorecido"), None,
        )
        self.assertLess(len(embed), 6000)
        self.assertLessEqual(len(embed.fields), 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
