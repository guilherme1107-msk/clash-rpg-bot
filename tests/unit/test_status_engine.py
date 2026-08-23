import unittest

from src.domain.status import CombatStatus, on_action, on_damage_taken, poise_values, tremor_burst


class StatusEngineTests(unittest.TestCase):
    def test_rupture_deals_potency_and_consumes_count(self):
        event = on_damage_taken(CombatStatus("rupture", 6, 2))
        self.assertEqual((event.damage, event.count_after), (6, 1))

    def test_sinking_reduces_sanity_or_becomes_damage_at_minus_45(self):
        normal = on_damage_taken(CombatStatus("sinking", 5, 2), sanity=-20)
        corroded = on_damage_taken(CombatStatus("sinking", 5, 2), sanity=-45)
        self.assertEqual(normal.sanity_loss, 5)
        self.assertEqual(corroded.damage, 5)

    def test_bleed_triggers_on_action(self):
        event = on_action(CombatStatus("bleed", 4, 3))
        self.assertEqual((event.damage, event.count_after), (4, 2))

    def test_bleed_triggers_once_per_offensive_coin(self):
        event = on_action(CombatStatus("bleed", 4, 3), coins=2)
        self.assertEqual((event.damage, event.count_after), (8, 1))

    def test_tremor_and_poise_expose_manual_values(self):
        self.assertEqual(tremor_burst(CombatStatus("tremor", 7, 2)).stagger_threshold, 7)
        self.assertEqual(poise_values(CombatStatus("poise", 5, 2)), (10, 0.5))


if __name__ == "__main__":
    unittest.main()
