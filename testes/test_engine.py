import random
import unittest

from src.domain.combat import Modifiers, Skill, SkillEffect, apply_damage_percentage, clashable_guard_values, estimate_clash, forecast_label, format_skill_effects, heads_chance, parse_skill_effects, resolve_attack, resolve_clash, resolve_damage, resolve_defense, roll_skill, triggered_skill_effects


class EngineTests(unittest.TestCase):
    def test_damage_percentage_applies_after_level_adjustment(self):
        result = resolve_damage(
            Skill("Percentual", 10, 0, 1), 0, 1, 6, 0, faces=[False],
        )
        apply_damage_percentage(result, 50)
        self.assertEqual(result.damage_before_percent, 12)
        self.assertEqual(result.percent_modifier, 6)
        self.assertEqual(result.final_damage, 18)

    def test_damage_percentage_reduction_is_limited_to_minus_one_hundred(self):
        result = resolve_damage(
            Skill("Redução", 10, 0, 1), 0, 1, 0, 0, faces=[False],
        )
        apply_damage_percentage(result, -250)
        self.assertEqual(result.damage_percent, -100)
        self.assertEqual(result.final_damage, 0)

    def test_damage_percentage_accepts_decimal_values(self):
        result = resolve_damage(
            Skill("Decimal", 1000, 0, 1), 0, 1, 0, 0, faces=[False],
        )
        apply_damage_percentage(result, 0.2)
        self.assertEqual(result.percent_modifier, 2)
        self.assertEqual(result.final_damage, 1002)

    def test_damage_percentage_effect_supports_status_conditions(self):
        effect = SkillEffect(
            "before_attack", "damage_percent", 15,
            condition_status="tremor", condition_min=4,
        )
        self.assertEqual(effect.condition_multiplier(4), 1)

    def test_status_condition_can_scale_bonus_every_x_up_to_a_limit(self):
        effect = SkillEffect(
            "on_use", "clash_power", 1,
            condition_status="charge", condition_owner="user", condition_value="count",
            condition_per=5, condition_max_stacks=2,
        )
        self.assertEqual(effect.condition_multiplier(4), 0)
        self.assertEqual(effect.condition_multiplier(5), 1)
        self.assertEqual(effect.condition_multiplier(9), 1)
        self.assertEqual(effect.condition_multiplier(10), 2)
        self.assertEqual(effect.condition_multiplier(20), 2)

    def test_skill_effect_syntax_round_trip(self):
        effects = parse_skill_effects("on_hit:paralysis:1:2; clash_win:sp:10")
        self.assertEqual(effects[0], SkillEffect("on_hit", "paralysis", 1, 2))
        self.assertEqual(parse_skill_effects(format_skill_effects(effects)), effects)

    def test_critical_coin_reuse_has_a_hard_limit(self):
        effect = SkillEffect("on_crit", "reuse_coin", 5, coin=2)
        self.assertEqual(effect.value, 5)
        with self.assertRaisesRegex(ValueError, "limite entre 1 e 5"):
            SkillEffect("on_crit", "reuse_coin", 6, coin=2)

    def test_status_skill_effect_keeps_potency_count_and_coin_condition(self):
        effects = parse_skill_effects("heads_hit:burn:3,2:2")
        self.assertEqual(effects, (SkillEffect("heads_hit", "burn", 3, 2, 2),))
        self.assertEqual(parse_skill_effects(format_skill_effects(effects)), effects)

    def test_tremor_burst_supports_trigger_and_coin_condition(self):
        effect = SkillEffect("heads_hit", "tremor_burst", 0, 2)
        skill = Skill("Burst", 4, 2, 2, effects=(effect,))
        hits = resolve_attack(skill, 45, 2, faces=[True, True])
        self.assertEqual(triggered_skill_effects(skill, "heads_hit", hits=hits), (effect,))

    def test_unbreakable_enhancement_can_use_charge_or_only_a_condition(self):
        conditional = SkillEffect("on_use", "make_unbreakable", 0, None, None, 0, "tremor", 3)
        self.assertEqual((conditional.condition_status, conditional.condition_min), ("tremor", 3))
        effect = SkillEffect("on_use", "make_unbreakable", 0, 2, None, 5)
        self.assertEqual((effect.coin, effect.charge_cost), (2, 5))

    def test_skill_rejects_effect_for_missing_coin(self):
        with self.assertRaises(ValueError):
            Skill("Teste", 4, 2, 2, effects=(SkillEffect("on_hit", "paralysis", 1, 3),))

    def test_on_hit_triggers_once_per_hit_and_heads_hit_ignores_paralyzed_heads(self):
        skill = Skill(
            "Teste", 4, 2, 2,
            effects=(
                SkillEffect("on_hit", "paralysis", 1),
                SkillEffect("heads_hit", "sp", 2),
            ),
        )
        hits = resolve_attack(skill, 45, 2, faces=[True, True], modifiers=Modifiers(paralysis=1))
        self.assertEqual(len(triggered_skill_effects(skill, "on_hit", hits=hits)), 2)
        self.assertEqual(len(triggered_skill_effects(skill, "heads_hit", hits=hits)), 1)

    def test_skill_accepts_at_most_twenty_effects(self):
        effect = SkillEffect("on_use", "sp", 1)
        with self.assertRaisesRegex(ValueError, "20 efeitos"):
            Skill("Excesso", 4, 2, 2, effects=(effect,) * 21)

    def test_sanity_probability_is_clamped(self):
        self.assertEqual(heads_chance(45), 0.95)
        self.assertEqual(heads_chance(-45), 0.05)
        self.assertEqual(heads_chance(999), 0.95)

    def test_positive_and_negative_ranges(self):
        self.assertEqual(Skill("A", 4, 3, 3).range_with(), (4, 13))
        self.assertEqual(Skill("B", 30, -10, 2).range_with(), (10, 30))

    def test_skill_accepts_at_most_ten_coins(self):
        self.assertEqual(Skill("Limite", 1, 1, 10).coins, 10)
        with self.assertRaises(ValueError):
            Skill("Excesso", 1, 1, 11)

    def test_skill_supports_individual_coin_layout(self):
        skill = Skill(
            "Layout", 3, 2, 3, coin_layout=("normal", "unbreakable", "normal")
        )
        self.assertEqual(skill.unbreakable_coins, 1)
        self.assertFalse(skill.coin_is_unbreakable(1))
        self.assertTrue(skill.coin_is_unbreakable(2))

    def test_attack_marks_the_configured_unbreakable_position(self):
        skill = Skill(
            "Layout", 3, 2, 3, coin_layout=("normal", "unbreakable", "normal")
        )
        hits = resolve_attack(skill, 0, 3, faces=[False, False, False])
        self.assertEqual([hit.active_unbreakable for hit in hits], [False, True, False])

    def test_unbreakable_coin_is_tracked_after_breaking(self):
        result = resolve_clash(
            Skill("Fraca", 1, 0, 2, unbreakable_coins=1), 0,
            Skill("Forte", 20, 0, 2), 0,
            rng=random.Random(1),
        )
        self.assertEqual(result.left_broken_unbreakable, 1)
        self.assertTrue(result.rounds[0].left_unbreakable_broken)
        self.assertTrue(result.rounds[0].left.unbreakable[-1])

    def test_broken_unbreakable_coin_adds_one_damage(self):
        result = resolve_damage(
            Skill("Ataque", 5, 0, 2), 0, 1, 10, 10,
            faces=[False], broken_unbreakable=1,
        )
        self.assertTrue(result.hits[-1].unbreakable)
        self.assertEqual(result.subtotal, 6)
        self.assertEqual(result.final_damage, 6)

    def test_active_unbreakable_coin_is_marked_in_damage(self):
        result = resolve_damage(
            Skill("Ataque", 5, 2, 2, unbreakable_coins=1), 45,
            2, 10, 10, faces=[True, False],
        )
        self.assertFalse(result.hits[0].active_unbreakable)
        self.assertTrue(result.hits[1].active_unbreakable)

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
        self.assertEqual(roll.disabled, [True, True, False])

    def test_damage_marks_paralyzed_coin_without_adding_coin_power(self):
        result = resolve_damage(
            Skill("Teste", 5, 3, 2), 45, 2, 10, 10,
            modifiers=Modifiers(paralysis=1), faces=[True, True],
        )
        self.assertTrue(result.hits[0].paralyzed)
        self.assertEqual([hit.power for hit in result.hits], [5, 8])
        self.assertEqual(result.final_damage, 8)

    def test_power_modifiers(self):
        roll, _ = roll_skill(
            Skill("A", 5, 4, 1), 45, 1, random.Random(1),
            Modifiers(base_power=-2, coin_power=3),
        )
        self.assertEqual(roll.power, 10)

    def test_plus_coin_modifier_does_not_change_minus_coin(self):
        roll, _ = roll_skill(
            Skill("Minus", 20, -5, 1), 45, 1, random.Random(1),
            Modifiers(coin_power=3),
        )
        self.assertEqual(roll.power, 15)

    def test_clash_power_modifier_is_added(self):
        result = resolve_clash(
            Skill("A", 5, 0, 1), 0,
            Skill("B", 5, 0, 1), 0,
            left_modifiers=Modifiers(clash_power=2),
            rng=random.Random(1),
        )
        self.assertEqual(result.winner, "left")

    def test_forecast_labels(self):
        self.assertEqual(forecast_label(0.10)[0], "HOPELESS")
        self.assertEqual(forecast_label(0.50)[0], "NEUTRAL")
        self.assertEqual(forecast_label(0.90)[0], "DOMINATING")

    def test_forecast_favors_stronger_skill(self):
        forecast = estimate_clash(
            Skill("Forte", 20, 5, 3), 45,
            Skill("Fraca", 1, 1, 1), 0,
            simulations=100, rng=random.Random(3),
        )
        self.assertGreater(forecast.win_chance, 0.8)

    def test_guard_only_rolls_a_coin(self):
        result = resolve_defense(
            Skill("Ataque", 8, 0, 1), 0,
            Skill("Guarda", 6, 0, 1, skill_type="guard"), 45,
            attack_modifiers=Modifiers(level=10),
            defense_modifiers=Modifiers(level=16),
            rng=random.Random(1),
        )
        self.assertIsNone(result.success)
        self.assertEqual(len(result.defense_rolls[0].faces), 1)

    def test_guard_final_power_includes_defense_level_advantage(self):
        result = resolve_defense(
            Skill("Ataque", 1, 0, 1), 0,
            Skill("Guard", 5, 0, 1, skill_type="guard"), 0,
            attack_modifiers=Modifiers(level=0),
            defense_modifiers=Modifiers(level=9),
            rng=random.Random(1),
        )
        self.assertEqual(result.defense_rolls[0].power, 8)

    def test_clashable_guard_win_reports_manual_stagger_value(self):
        guard = Skill("Muralha", 30, 0, 1, skill_type="clashable_guard")
        attack = Skill("Ataque", 1, 0, 1)
        result = resolve_clash(guard, 0, attack, 0, rng=random.Random(1))
        stagger, shield = clashable_guard_values(result, guard, attack)
        self.assertEqual(stagger, 30)
        self.assertEqual(shield, 0)

    def test_losing_clashable_guard_reduces_incoming_damage(self):
        guard = Skill("Muralha", 4, 0, 1, skill_type="clashable_guard")
        attack = Skill("Ataque", 20, 0, 1)
        result = resolve_clash(guard, 0, attack, 0, rng=random.Random(1))
        stagger, shield = clashable_guard_values(result, guard, attack)
        self.assertEqual(stagger, 0)
        self.assertEqual(shield, 4)

    def test_evade_checks_each_attack_coin(self):
        result = resolve_defense(
            Skill("Ataque", 5, 1, 3), 0,
            Skill("Evasão", 20, 0, 1, skill_type="evade"), 0,
            rng=random.Random(2),
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.attack_rolls), 3)

    def test_counter_rolls_activation_coin_without_clash(self):
        result = resolve_defense(
            Skill("Ataque", 5, 1, 2), 0,
            Skill("Counter", 7, 2, 1, skill_type="counter"), 0,
            rng=random.Random(4),
        )
        self.assertIsNone(result.success)
        self.assertIsNotNone(result.counter_roll)

    def test_damage_applies_level_difference_once_at_end(self):
        result = resolve_damage(
            Skill("Ataque", 5, 3, 3), 0, 3, 15, 9,
            faces=[False, True, True],
        )
        self.assertEqual([hit.power for hit in result.hits], [5, 8, 11])
        self.assertEqual(result.subtotal, 11)
        self.assertEqual(result.level_modifier, 2)
        self.assertEqual(result.final_damage, 13)

    def test_negative_level_modifier_truncates_toward_zero(self):
        result = resolve_damage(
            Skill("Ataque", 5, 0, 1), 0, 1, 7, 15, faces=[False],
        )
        self.assertEqual(result.level_modifier, -2)
        self.assertEqual(result.final_damage, 3)


if __name__ == "__main__":
    unittest.main()
