"""Prova: a Falsa Fome é Bloodfeast, e o E.G.O Gift enxerga o MESMO recurso.

Antes: as skills dela falavam `special_condition` e o gift olhava `bloodfeast`
— dois status diferentes para a mesma coisa, então o gift nunca via o recurso
que as skills dela consumiam. Agora as duas pontas falam `bloodfeast`.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from database import Database, _effects_from_row

GUILD = 1
ROSE = 100
ZOTE = 200


class BloodfeastCompartilhado(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.setup()
        # o consumo grava o "já consumido" na ficha, então ela precisa existir
        self.db.create_character(GUILD, ROSE, "Rosemary")
        self.db.create_character(GUILD, ZOTE, "Zote")

    def tearDown(self):
        self.db.close()

    # ── o vocabulary novo existe ───────────────────────────────────────
    def test_consume_bloodfeast_eh_efeito_valido(self):
        from src.domain.models.combat import EFFECT_TYPES
        self.assertIn("consume_bloodfeast", EFFECT_TYPES)
        self.assertIn("bloodfeast", EFFECT_TYPES)

    def test_alias_false_hunger_vira_bloodfeast(self):
        linha = {
            "trigger": "on_use", "effect_type": "false_hunger", "value": 0, "count": 10,
        }
        lido = _effects_from_row({"effects_json": json.dumps([linha])})
        self.assertEqual(lido[0].effect_type, "bloodfeast")

    def test_alias_condicao_false_hunger_vira_bloodfeast(self):
        linha = {
            "trigger": "on_hit", "effect_type": "damage_percent", "value": 30,
            "condition_status": "false_hunger", "condition_min": 80, "condition_value": "count",
        }
        lido = _effects_from_row({"effects_json": json.dumps([linha])})
        self.assertEqual(lido[0].condition_status, "bloodfeast")

    # ── consumir conta no bloodfeast, e o gift lê o MESMO número ───────
    def test_consumo_registra_no_mesmo_recurso_do_gift(self):
        self.db.set_status(GUILD, "player", ROSE, "bloodfeast", 0, 100)

        _saved, consumido, total = self.db.consume_bloodfeast(GUILD, "player", ROSE, 30)

        self.assertEqual(consumido, 30)
        self.assertEqual(total, 30)
        # o saldo caiu do jeito certo
        self.assertEqual(self.db.total_bloodfeast(GUILD, "player", ROSE), 70)
        # o "já consumido" é o que as condições dela consultam
        self.assertEqual(self.db.get_bloodfeast_consumed(GUILD, "player", ROSE), 30)
        # e não sobrou nada de Condição Especial
        self.assertIsNone(self.db.get_status(GUILD, "player", ROSE, "special_condition"))

    def test_consumo_parcial_nao_falha(self):
        self.db.set_status(GUILD, "player", ROSE, "bloodfeast", 0, 20)
        _saved, consumido, total = self.db.consume_bloodfeast(GUILD, "player", ROSE, 50)
        self.assertEqual(consumido, 20)
        self.assertEqual(total, 20)
        # saldo zerado: a linha some, então o gift vê 0 (não há Bloodfeast)
        self.assertEqual(self.db.total_bloodfeast(GUILD, "player", ROSE), 0)

    def test_consumo_de_bloodfeast_nao_toca_condicao_especial(self):
        # as duas colunas de "consumido" são independentes: o Trashholder de
        # outras fichas não pode ser afetado por uma skill da Rosemary.
        self.db.set_status(GUILD, "player", ZOTE, "special_condition", 0, 40)
        self.db.consume_special_condition(GUILD, "player", ZOTE, 10)
        self.assertEqual(self.db.get_special_condition_consumed(GUILD, "player", ZOTE), 10)
        self.assertEqual(self.db.get_bloodfeast_consumed(GUILD, "player", ZOTE), 0)

        self.db.set_status(GUILD, "player", ROSE, "bloodfeast", 0, 40)
        self.db.consume_bloodfeast(GUILD, "player", ROSE, 10)
        self.assertEqual(self.db.get_bloodfeast_consumed(GUILD, "player", ROSE), 10)
        self.assertEqual(self.db.get_special_condition_consumed(GUILD, "player", ROSE), 0)

    def test_recurso_generico_falha_fechado(self):
        with self.assertRaises(ValueError):
            self.db.get_resource_consumed(GUILD, "banana", ROSE, "bloodfeast")
        with self.assertRaises(ValueError):
            self.db.consume_resource(GUILD, "player", ROSE, "bloodfeast", -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)