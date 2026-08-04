import random
import unittest

from clash_engine import Modifiers, Skill, heads_chance, resolve_attack, resolve_clash, roll_skill


class EngineTests(unittest.TestCase):
    def test_sanity_probability_is_clamped(self):
        self.assertEqual(heads_chance(45), 0.95)
        self.assertEqual(heads_chance(-45), 0.05)
        self.assertEqual(heads_chance(999), 0.95)

    def test_positive_and_negative_ranges(self):
        self.assertEqual(Skill("A", 4, 3, 3).range_with(), (4, 13))
        self.assertEqual(Skill("B", 30, -10, 2).range_with(), (10, 30))

    def test_seeded_clash_finishes(self):
        result = resolve_clash(
            Skill("A", 5, 4, 3), 30,
            Skill("B", 8, 2, 2), 0,
            rng=random.Random(7),
        )
        self.assertIn(result.winner, ("left", "right"))
        self.assertTrue(result.left_coins == 0 or result.right_coins == 0)

    def test_attack_has_one_hit_per_remaining_coin(self):
        hits = resolve_attack(Skill("A", 5, 4, 3), 45, 2, rng=random.Random(1))
        self.assertEqual(len(hits), 2)

    def test_paralysis_zeros_coin_power_and_is_consumed(self):
        roll, remaining = roll_skill(
            Skill("A", 5, 4, 3), 45, 3, random.Random(1), Modifiers(paralysis=2)
        )
        self.assertEqual(roll.power, 9)
        self.assertEqual(remaining, 0)

    def test_power_modifiers(self):
        roll, _ = roll_skill(
            Skill("A", 5, 4, 1), 45, 1, random.Random(1),
            Modifiers(base_power=-2, coin_power=3),
        )
        self.assertEqual(roll.power, 10)


if __name__ == "__main__":
    unittest.main()
