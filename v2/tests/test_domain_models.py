import unittest

from clash_rpg.domain import CoinKind, CoinSpec, Combatant, Skill


class DomainModelTests(unittest.TestCase):
    def test_skill_has_individually_configured_coins(self):
        skill = Skill(
            "Teste",
            4,
            2,
            (CoinSpec(), CoinSpec(CoinKind.UNBREAKABLE)),
        )
        self.assertEqual(skill.coins[0].kind, CoinKind.NORMAL)
        self.assertEqual(skill.coins[1].kind, CoinKind.UNBREAKABLE)

    def test_skill_rejects_more_than_ten_coins(self):
        with self.assertRaises(ValueError):
            Skill("Excesso", 1, 1, tuple(CoinSpec() for _ in range(11)))

    def test_sanity_controls_heads_chance(self):
        self.assertEqual(Combatant("1", "Alta", sanity=45).heads_chance, 0.95)
        self.assertEqual(Combatant("2", "Baixa", sanity=-45).heads_chance, 0.05)
        self.assertEqual(
            Combatant("3", "Sem SP", sanity=45, uses_sanity=False).heads_chance,
            0.5,
        )


if __name__ == "__main__":
    unittest.main()

