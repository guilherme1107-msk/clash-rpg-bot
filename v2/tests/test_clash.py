import unittest
from random import Random

from clash_rpg.domain import CoinKind, CoinSpec, Combatant, Modifiers, Skill, resolve_clash


class ClashTests(unittest.TestCase):
    def test_seeded_clash_is_reproducible(self):
        left = Combatant("p1", "Alice", sanity=30)
        right = Combatant("p2", "Bruno", sanity=0)
        left_skill = Skill("Corte", 4, 3, (CoinSpec(), CoinSpec(), CoinSpec()))
        right_skill = Skill("Golpe", 5, 2, (CoinSpec(), CoinSpec()))

        first = resolve_clash(left, left_skill, right, right_skill, rng=Random(20))
        second = resolve_clash(left, left_skill, right, right_skill, rng=Random(20))
        self.assertEqual(first, second)

    def test_paralysis_is_consumed_by_coins_and_zeros_their_coin_power(self):
        left = Combatant("p1", "Paralisado", sanity=45, paralysis=2)
        right = Combatant("p2", "Alvo", sanity=-45)
        skill = Skill("Três moedas", 5, 5, (CoinSpec(), CoinSpec(), CoinSpec()))
        weak = Skill("Fraca", 1, 0, (CoinSpec(),))

        result = resolve_clash(left, skill, right, weak, rng=Random(1))
        first_roll = result.rounds[0].left_roll
        self.assertEqual(first_roll.paralyzed, (True, True, False))
        self.assertEqual(first_roll.paralysis_remaining, 0)

    def test_unbreakable_coin_is_fractured_instead_of_deleted(self):
        left = Combatant("p1", "Fraco", sanity=-45)
        right = Combatant("p2", "Forte", sanity=45, modifiers=Modifiers(clash_power=20))
        unbreakable = Skill("Persistente", 1, 0, (CoinSpec(CoinKind.UNBREAKABLE),))
        strong = Skill("Dominante", 5, 5, (CoinSpec(),))

        result = resolve_clash(left, unbreakable, right, strong, rng=Random(2))
        self.assertEqual(result.winner, "right")
        self.assertEqual(len(result.left_coins), 1)
        self.assertTrue(result.left_coins[0].fractured)
        self.assertEqual(result.fractured_follow_up("left"), result.left_coins)

    def test_level_difference_adds_one_power_per_three_levels(self):
        left = Combatant("p1", "Nivelado", offense_level=9, sanity=-45)
        right = Combatant("p2", "Base", offense_level=0, sanity=-45)
        skill = Skill("Igual", 5, 0, (CoinSpec(),))

        result = resolve_clash(left, skill, right, skill, rng=Random(4))
        self.assertEqual(result.rounds[0].left_roll.power, 8)
        self.assertEqual(result.rounds[0].right_roll.power, 5)


if __name__ == "__main__":
    unittest.main()
