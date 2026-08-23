import unittest

import clash_engine
import src.domain.combat as combat
from src.domain.combat import Skill, SkillEffect, heads_chance, resolve_clash


class PublicCombatApiTests(unittest.TestCase):
    def test_public_api_exposes_working_combat_engine(self):
        left = Skill("Left", 5, 2, 2, effects=(SkillEffect("clash_win", "sp", 5),))
        right = Skill("Right", 1, 0, 1)
        result = resolve_clash(left, 45, right, -45)

        self.assertEqual(heads_chance(45), 0.95)
        self.assertEqual(result.winner, "left")

    def test_models_are_owned_by_the_new_domain_package(self):
        self.assertEqual(Skill.__module__, "src.domain.models.combat")
        self.assertEqual(SkillEffect.__module__, "src.domain.models.combat")

    def test_legacy_module_is_a_compatibility_wrapper(self):
        self.assertIs(clash_engine.Skill, Skill)
        self.assertIs(clash_engine.resolve_clash, combat.resolve_clash)


if __name__ == "__main__":
    unittest.main()
