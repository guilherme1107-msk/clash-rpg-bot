"""Etapa 3 do P7 — keywords na ficha, gate do gift e teto por Uptie.

Roda direto:  .venv\\Scripts\\python.exe testes\\test_keywords.py
"""
import json
import os
import tempfile
import unittest

from database import (
    Database,
    EGO_GIFT_MAX_BY_UPTIE,
    KEYWORD_ALIASES,
    normalize_keywords,
)


class KeywordTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.db = Database(self.path)
        self.db.setup()
        for uid in (100, 101, 102, 103):
            self.db.create_character(1, uid, f"Ficha{uid}")

    def tearDown(self):
        self.db.close()
        os.remove(self.path)

    # ------------------------------------------------------------ migração
    def test_migration_adds_keyword_and_gift_gate_columns(self):
        for table, keys in (
            ("characters", {"keywords"}),
            ("enemies", {"keywords"}),
            ("ego_gifts", {"active_status", "active_tag", "active_scope", "active_min"}),
        ):
            have = {r[1] for r in self.db.connection.execute(f"PRAGMA table_info({table})")}
            self.assertTrue(keys <= have, f"{table} sem {keys - have}")

    # ------------------------------------------------------------ keywords
    def test_keywords_roundtrip_normalizes_and_dedupes(self):
        self.db.set_keywords(1, "player", 100, ["Poise", "poise", " Middle ", ""])
        self.assertEqual(self.db.get_keywords(1, "player", 100), frozenset({"poise", "middle"}))

    def test_false_hunger_is_labeled_unique_bloodfeast_but_only_as_keyword(self):
        # decisão 10: a tela continua "Falsa Fome"; o sistema rotula.
        self.db.set_keywords(1, "player", 100, ["false_hunger"])
        self.assertEqual(KEYWORD_ALIASES["false_hunger"], "unique_bloodfeast")
        self.assertEqual(
            self.db.get_keywords(1, "player", 100), frozenset({"unique_bloodfeast"}),
        )
        self.assertEqual(normalize_keywords('"false_hunger"'), frozenset({"unique_bloodfeast"}))

    def test_garbage_keyword_json_becomes_empty_set_instead_of_raising(self):
        for bad in ("{não é lista", "", None, 42, "[não, é, lista]"):
            self.assertEqual(normalize_keywords(bad), frozenset(), f"entrada {bad!r}")

    def test_a_bare_string_becomes_one_keyword_instead_of_falling_ignorantly(self):
        self.assertEqual(normalize_keywords('"poise"'), frozenset({"poise"}))

    def test_keywords_of_an_unknown_sheet_are_empty(self):
        self.assertEqual(self.db.get_keywords(1, "player", 9999), frozenset())

    # ------------------------------------------------------- count_allies
    def test_count_allies_includes_self_and_respects_guild(self):
        self.db.set_keywords(1, "player", 100, ["poise"])
        self.db.set_keywords(1, "player", 101, ["poise"])
        self.db.set_keywords(1, "player", 102, ["poise"])
        self.db.set_keywords(1, "player", 103, ["middle"])
        self.db.create_character(2, 200, "Outro")
        self.db.set_keywords(2, "player", 200, ["poise"])

        # O time do Limbus inclui quem está jogando: 100, 101 e 102 = 3.
        # O 103 não tem poise e o 200 é de outro servidor.
        self.assertEqual(self.db.count_allies_with(1, "player", 100, "poise"), 3)
        # só o 103 tem middle → 1
        self.assertEqual(self.db.count_allies_with(1, "player", 100, "middle"), 1)
        # a ficha de middle vê os 3 de poise
        self.assertEqual(self.db.count_allies_with(1, "player", 103, "poise"), 3)

    def test_active_battle_narrows_the_crew_to_its_own_panel(self):
        for uid in (100, 101, 102):
            self.db.set_keywords(1, "player", uid, ["middle"])
        # sem batalha o encontro é o grupo inteiro
        self.assertEqual(self.db.count_allies_with(1, "player", 100, "middle"), 3)

        self.db.start_battle(1, 10, "Encontro", 100)
        self.db.join_battle(1, 10, 100, "Ficha100")
        self.db.join_battle(1, 10, 101, "Ficha101")

        # agora o encontro é o painel: 102 ficou de fora
        self.assertEqual(self.db.encounter_member_ids(1, "player", 100), {100, 101})
        self.assertEqual(self.db.count_allies_with(1, "player", 100, "middle"), 2)
        # quem não entrou na batalha continua no grupo do servidor
        self.assertEqual(self.db.count_allies_with(1, "player", 102, "middle"), 3)

    def test_count_allies_applies_the_same_alias(self):
        self.db.set_keywords(1, "player", 100, ["false_hunger"])
        self.db.set_keywords(1, "player", 101, ["false_hunger"])
        # quem pede "unique_bloodfeast" acha quem marcou "false_hunger"
        self.assertEqual(self.db.count_allies_with(1, "player", 100, "unique_bloodfeast"), 2)

    # ------------------------------------------------------------ gate 7
    def _gift(self, uid, name, **gate):
        payload = {
            "name": name, "tier": 5, "description": "",
            "effects": [{"trigger": "clash_win", "effect_type": "sp", "value": 5}],
        }
        payload.update(gate)
        return self.db.save_ego_gift(1, "player", uid, payload)

    def _names(self, uid):
        return [name for name, _, _tag in self.db.list_active_ego_gift_effects(1, "player", uid)]

    def test_gift_without_gate_is_always_active(self):
        self._gift(100, "Sem Gate")
        self.assertEqual(self._names(100), ["Sem Gate"])

    def test_gate_by_own_keyword_hides_the_gift_until_the_sheet_marks_it(self):
        self._gift(100, "Da Middle", active_status="middle")
        self.assertEqual(self._names(100), [])
        self.db.set_keywords(1, "player", 100, ["middle"])
        self.assertEqual(self._names(100), ["Da Middle"])
        # outra ficha sem a keyword continua sem o gift
        self.assertEqual(self._names(101), [])

    def test_gate_by_allies_needs_the_minimum_number_in_the_crew(self):
        self._gift(
            100, "3 da Middle",
            active_status="middle", active_tag="middle", active_scope="allies", active_min=3,
        )
        # "3 ou mais aliados da Middle" conta o próprio: 3 no total.
        self.db.set_keywords(1, "player", 100, ["middle"])
        self.assertEqual(self._names(100), [])              # 1 no encontro

        self.db.set_keywords(1, "player", 101, ["middle"])
        self.assertEqual(self._names(100), [])              # 2 no encontro

        self.db.set_keywords(1, "player", 102, ["middle"])
        self.assertEqual(self._names(100), ["3 da Middle"])  # 3 ✓

    def test_gate_narrowed_by_the_panel_sees_only_who_joined(self):
        self._gift(
            100, "Companhia",
            active_status="middle", active_tag="middle", active_scope="allies", active_min=2,
        )
        self.db.set_keywords(1, "player", 100, ["middle"])
        self.db.set_keywords(1, "player", 103, ["middle"])
        self.assertEqual(self._names(100), ["Companhia"])   # 2 no grupo do servidor

        self.db.start_battle(1, 10, "Encontro", 100)
        self.db.join_battle(1, 10, 100, "Ficha100")
        self.assertEqual(self._names(100), [])              # 1 no painel → insuficiente

    def test_gate_needs_own_keyword_and_allies_at_the_same_time(self):
        self._gift(
            100, "Oligopólio",
            active_status="middle", active_tag="middle", active_scope="allies", active_min=1,
        )
        self.db.set_keywords(1, "player", 101, ["middle"])   # aliado ok
        self.assertEqual(self._names(100), [])                # próprio sem keyword
        self.db.set_keywords(1, "player", 100, ["middle"])
        self.assertEqual(self._names(100), ["Oligopólio"])

    def test_gate_is_case_insensitive_and_survives_odd_scopes(self):
        self._gift(100, "Sensível", active_status="MiDdLe")
        self.assertEqual(self._names(100), [])
        self.db.set_keywords(1, "player", 100, ["MIDDLE"])
        self.assertEqual(self._names(100), ["Sensível"])

        # scope desconhecido não pode desligar o teste de aliados por acidente
        self._gift(100, "Escopo Ruim", active_tag="middle", active_scope="banana", active_min=5)
        self.assertEqual(sorted(self._names(100)), ["Escopo Ruim", "Sensível"])

    # ---------------------------------------------------- teto por Uptie
    def test_empty_uptie_table_means_no_limit_at_all(self):
        self.assertEqual(EGO_GIFT_MAX_BY_UPTIE, {})
        for _ in range(4):
            self._gift(100, "Empilhado")
        self.assertIsNone(
            self.db.ego_gift_limit_warning(1, "player", 100, 4),
        )

    def test_filled_uptie_table_warns_without_blocking(self):
        import database
        original = dict(database.EGO_GIFT_MAX_BY_UPTIE)
        try:
            database.EGO_GIFT_MAX_BY_UPTIE.update({1: 1})
            self.assertIsNone(self.db.ego_gift_limit_warning(1, "player", 100, 1))
            warning = self.db.ego_gift_limit_warning(1, "player", 100, 3)
            self.assertIn("Uptie 1", warning)
            self.assertIn("3", warning)
            # inimigos ficam de fora: o teto é da ficha
            self.assertIsNone(self.db.ego_gift_limit_warning(1, "enemy", 7, 99))
        finally:
            database.EGO_GIFT_MAX_BY_UPTIE.clear()
            database.EGO_GIFT_MAX_BY_UPTIE.update(original)

    def test_save_returns_the_warning_and_persists_the_gate(self):
        result = self.db.save_ego_gift(1, "player", 100, {
            "name": "Gateado", "tier": 5, "description": "",
            "effects": [], "active_status": "middle",
            "active_tag": "middle", "active_scope": "allies", "active_min": 3,
        })
        self.assertIn("limit_warning", result)
        row = self.db.connection.execute(
            "SELECT active_status, active_tag, active_scope, active_min FROM ego_gifts WHERE id=?",
            (result["id"],),
        ).fetchone()
        self.assertEqual(
            (row["active_status"], row["active_tag"], row["active_scope"], row["active_min"]),
            ("middle", "middle", "allies", 3),
        )
        # vazio no payload volta ao padrão de "sempre vale"
        self.db.save_ego_gift(1, "player", 100, {
            "id": result["id"], "name": "Gateado", "tier": 5, "description": "",
            "effects": [], "active_scope": "qualquer-coisa",
        })
        row = self.db.connection.execute(
            "SELECT active_status, active_tag, active_scope, active_min FROM ego_gifts WHERE id=?",
            (result["id"],),
        ).fetchone()
        self.assertEqual(
            (row["active_status"], row["active_tag"], row["active_scope"], row["active_min"]),
            ("", "", "self", 0),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
