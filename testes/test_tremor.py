import unittest

from src.domain.combat import (
    Skill,
    SkillEffect,
    format_skill_effects,
    parse_skill_effects,
    resolve_attack,
    triggered_skill_effects,
)
from src.domain.status import (
    TREMOR_TYPES,
    TREMOR_TYPE_LABELS,
    CombatStatus,
    convert_tremor,
    on_round_end,
    tremor_scorch_burst,
)


class AmplitudeConversionTests(unittest.TestCase):
    """Amplitude Conversion → Tremor - Scorch (Pendência #9)."""

    def test_conversion_preserves_potency_and_count(self):
        tremor = CombatStatus("tremor", 7, 3)

        converted = convert_tremor(tremor, "scorch")

        self.assertEqual(converted.status_type, "tremor")
        self.assertEqual((converted.potency, converted.count), (7, 3))
        self.assertEqual(converted.tremor_type, "scorch")

    def test_conversion_can_revert_to_normal_tremor(self):
        converted = convert_tremor(CombatStatus("tremor", 4, 2), "scorch")

        reverted = convert_tremor(converted, "normal")

        self.assertEqual(reverted.tremor_type, "normal")
        self.assertEqual((reverted.potency, reverted.count), (4, 2))

    def test_conversion_requires_an_active_tremor_status(self):
        with self.assertRaisesRegex(ValueError, "Tremor"):
            convert_tremor(CombatStatus("burn", 4, 2), "scorch")

    def test_conversion_rejects_unknown_variant(self):
        with self.assertRaisesRegex(ValueError, "Tipo de Tremor"):
            convert_tremor(CombatStatus("tremor", 4, 2), "reverb")

    def test_variant_field_only_makes_sense_on_tremor(self):
        with self.assertRaisesRegex(ValueError, "Amplitude Conversion"):
            CombatStatus("burn", 4, 2, "scorch")
        with self.assertRaisesRegex(ValueError, "Tipo de Tremor"):
            CombatStatus("tremor", 4, 2, "reverb")

    def test_every_known_variant_has_a_display_label(self):
        for tremor_type in TREMOR_TYPES:
            self.assertTrue(TREMOR_TYPE_LABELS.get(tremor_type))
        self.assertEqual(TREMOR_TYPE_LABELS["scorch"], "Tremor - Scorch")

    def test_round_end_labels_the_converted_variant(self):
        event = on_round_end(CombatStatus("tremor", 7, 3, "scorch"))
        self.assertEqual(event.label, "Tremor - Scorch")
        self.assertEqual((event.potency_after, event.count_after), (7, 2))
        self.assertEqual(on_round_end(CombatStatus("tremor", 7, 3)).label, "")


class TremorScorchBurstTests(unittest.TestCase):
    """Dano do Burst = (Tremor + Burn) ÷ 2, depois −1 Burn Count."""

    def test_burst_averages_tremor_and_burn_and_spends_burn_count(self):
        event = tremor_scorch_burst(
            CombatStatus("tremor", 8, 2, "scorch"),
            CombatStatus("burn", 6, 3),
        )

        self.assertEqual(event.damage, 7)  # (8 + 6) ÷ 2 = 7
        self.assertEqual(event.count_after, 2)  # Burn perde 1 Count
        self.assertIn("(Tremor + Burn) ÷ 2", event.note)

    def test_burst_without_burn_halves_tremor_rounding_down(self):
        event = tremor_scorch_burst(CombatStatus("tremor", 5, 2, "scorch"), None)

        self.assertEqual(event.damage, 2)  # 5 ÷ 2 = 2,5 → 2
        self.assertEqual(event.count_after, 0)
        self.assertIn("sem Burn", event.note)

    def test_burst_ignores_burn_that_has_no_count_left(self):
        event = tremor_scorch_burst(
            CombatStatus("tremor", 8, 2, "scorch"),
            CombatStatus("burn", 6, 0),
        )

        self.assertEqual(event.damage, 4)
        self.assertEqual(event.count_after, 0)

    def test_burst_requires_the_scorch_variant(self):
        with self.assertRaisesRegex(ValueError, "Scorch"):
            tremor_scorch_burst(CombatStatus("tremor", 8, 2), None)


class AmplitudeConversionEffectTests(unittest.TestCase):
    """A sintaxe da Skill é plana, como o Tremor Burst: gatilho:efeito:valor."""

    def test_effect_parses_without_count(self):
        effects = parse_skill_effects("on_use:amplitude_conversion_scorch:0")

        self.assertEqual(
            effects, (SkillEffect("on_use", "amplitude_conversion_scorch", 0),)
        )
        self.assertIsNone(effects[0].count)

    def test_effect_survives_format_round_trip(self):
        effects = parse_skill_effects("heads_hit:amplitude_conversion_scorch:0:2")

        self.assertEqual(parse_skill_effects(format_skill_effects(effects)), effects)

    def test_effect_rejects_a_count_field(self):
        with self.assertRaisesRegex(ValueError, "Quantidade"):
            SkillEffect("on_use", "amplitude_conversion_scorch", 0, None, 1)

    def test_effect_fires_on_the_configured_trigger(self):
        effect = SkillEffect("heads_hit", "amplitude_conversion_scorch", 0, 2)
        skill = Skill("Conversão", 4, 2, 2, effects=(effect,))

        hits = resolve_attack(skill, 45, 2, faces=[True, True])

        self.assertEqual(
            triggered_skill_effects(skill, "heads_hit", hits=hits), (effect,)
        )
