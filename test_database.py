import os
import tempfile
import unittest

from clash_engine import Skill, SkillEffect
from database import Database


class BattleDatabaseTests(unittest.TestCase):
    def test_characters_can_be_listed_for_unified_clash_targets(self):
        self.db.create_character(1, 100, "Sancho")
        self.db.create_character(1, 101, "Don")
        self.db.create_character(2, 200, "Outro servidor")
        self.assertEqual(
            [(row["user_id"], row["name"]) for row in self.db.list_characters(1)],
            [(101, "Don"), (100, "Sancho")],
        )

    def test_skill_effects_are_persisted(self):
        skill = Skill(
            "Réplica", 5, 2, 3,
            effects=(SkillEffect("on_hit", "paralysis", 1, 2),),
        )
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, "Réplica").effects, skill.effects)

    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.db = Database(self.path)
        self.db.setup()

    def tearDown(self):
        self.db.close()
        os.remove(self.path)

    def test_only_first_player_can_claim_field_action(self):
        self.db.start_battle(1, 10, "Teste", 99)
        action = self.db.add_field_action(1, 10, "Hostil", "Golpe")
        self.assertTrue(self.db.claim_field_action(action["id"], 100, "Skill A"))
        self.assertFalse(self.db.claim_field_action(action["id"], 101, "Skill B"))

    def test_next_turn_clears_field(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.db.add_field_action(1, 10, "Hostil", "Golpe")
        battle = self.db.next_battle_turn(1, 10)
        self.assertEqual(battle["turn"], 2)
        self.assertEqual(self.db.list_field_actions(1, 10), [])

    def test_fixed_panel_message_is_persisted(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.db.set_battle_panel_message(1, 10, 123456)
        self.assertEqual(self.db.get_battle(1, 10)["panel_message_id"], 123456)

    def test_participant_status_is_reset_on_next_turn(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.db.join_battle(1, 10, 100, "Sancho")
        self.db.set_battle_participant_status(1, 10, 100, "done")
        self.assertEqual(self.db.get_battle_participant(1, 10, 100)["status"], "done")

        self.db.next_battle_turn(1, 10)

        participant = self.db.get_battle_participant(1, 10, 100)
        self.assertEqual(participant["character_name"], "Sancho")
        self.assertEqual(participant["status"], "waiting")

    def test_restart_battle_clears_old_participants(self):
        self.db.start_battle(1, 10, "Primeira", 99)
        self.db.join_battle(1, 10, 100, "Sancho")
        self.db.start_battle(1, 10, "Segunda", 99)
        self.assertEqual(self.db.list_battle_participants(1, 10), [])

    def test_ready_is_persisted_and_reset_on_next_turn(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.db.join_battle(1, 10, 100, "Sancho")
        self.db.set_battle_participant_ready(1, 10, 100, True)
        self.assertEqual(self.db.get_battle_participant(1, 10, 100)["ready"], 1)

        self.db.next_battle_turn(1, 10)

        self.assertEqual(self.db.get_battle_participant(1, 10, 100)["ready"], 0)

    def test_battle_phase_is_persisted_and_next_turn_returns_to_preparation(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.assertEqual(self.db.get_battle(1, 10)["phase"], "preparation")
        self.db.set_battle_phase(1, 10, "declaration")
        self.db.set_battle_phase(1, 10, "resolution")
        self.db.set_battle_phase(1, 10, "complete")
        self.assertEqual(self.db.get_battle(1, 10)["phase"], "complete")

        self.db.next_battle_turn(1, 10)

        self.assertEqual(self.db.get_battle(1, 10)["phase"], "preparation")


if __name__ == "__main__":
    unittest.main()
