import os
import tempfile
import unittest

from src.domain.combat import Skill, SkillEffect
from database import Database
from battle_flow import advance_when_all_ready


class BattleDatabaseTests(unittest.TestCase):
    def test_media_upload_keeps_permanent_source_and_exposes_discord_copy(self):
        self.db.save_appearance(1, "player", 100, "/uploads/permanent.png", "#aa1122", "Teste")
        job_id = self.db.queue_media_upload(1, "player", 100, "/uploads/permanent.png")

        self.db.finish_media_upload(job_id, "https://cdn.discordapp.com/temporary.png")

        raw = self.db.connection.execute(
            "SELECT image_url FROM profile_appearance WHERE guild_id=1 AND owner_kind='player' AND owner_id=100"
        ).fetchone()
        self.assertEqual(raw["image_url"], "/uploads/permanent.png")
        self.assertEqual(
            self.db.get_appearance(1, "player", 100)["image_url"],
            "https://cdn.discordapp.com/temporary.png",
        )

    def test_characters_can_be_listed_for_unified_clash_targets(self):
        self.db.create_character(1, 100, "Sancho")
        self.db.create_character(1, 101, "Don")
        self.db.create_character(2, 200, "Outro servidor")
        self.assertEqual(
            [(row["user_id"], row["name"]) for row in self.db.list_characters(1)],
            [(101, "Don"), (100, "Sancho")],
        )

    def test_character_transfer_moves_complete_sheet_and_frees_old_owner(self):
        self.db.create_character(1, 100, "Sancho")
        self.db.save_skill(1, 100, Skill("Réplica", 4, 2, 2))
        self.db.add_status(1, "player", 100, "bleed", 3, 2)
        self.db.save_appearance(1, "player", 100, "https://example.com/a.png", "#aa1122", "Teste")

        moved = self.db.transfer_character(1, 100, 200)

        self.assertEqual(moved["name"], "Sancho")
        self.assertIsNone(self.db.get_character(1, 100))
        self.assertIsNotNone(self.db.get_skill(1, 200, "Réplica"))
        self.assertEqual(self.db.get_status(1, "player", 200, "bleed").potency, 3)
        self.assertEqual(self.db.get_appearance(1, "player", 200)["subtitle"], "Teste")

    def test_character_transfer_rejects_owner_that_already_has_sheet(self):
        self.db.create_character(1, 100, "Sancho")
        self.db.create_character(1, 200, "Don")
        with self.assertRaisesRegex(ValueError, "já possui"):
            self.db.transfer_character(1, 100, 200)

    def test_character_transfer_is_blocked_during_active_battle(self):
        self.db.create_character(1, 100, "Sancho")
        self.db.start_battle(1, 10, "Teste", 999)
        self.db.join_battle(1, 10, 100, "Sancho")
        with self.assertRaisesRegex(ValueError, "batalha ativa"):
            self.db.transfer_character(1, 100, 200)

    def test_skill_effects_are_persisted(self):
        skill = Skill(
            "Réplica", 5, 2, 3,
            effects=(SkillEffect("on_hit", "paralysis", 1, 2),),
        )
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, "Réplica").effects, skill.effects)

    def test_status_skill_effect_is_persisted(self):
        skill = Skill(
            "Status", 4, 2, 2,
            effects=(SkillEffect("on_hit", "burn", 3, 1, 2),),
        )
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, "Status").effects, skill.effects)

    def test_charge_cost_and_target_condition_are_persisted(self):
        effect = SkillEffect("on_use", "final_power", 3, None, None, 5, "bleed", 4)
        skill = Skill("Condicional", 4, 2, 2, effects=(effect,))
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, "Condicional").effects, (effect,))

    def test_special_condition_and_consumable_decimal_damage_effect_are_persisted(self):
        status = self.db.set_status(1, "player", 100, "special_condition", 1, 200)
        self.assertEqual((status.potency, status.count), (1, 200))
        effect = SkillEffect(
            "before_attack", "damage_percent", 0.2,
            condition_status="special_condition", condition_min=1,
            condition_owner="user", condition_value="count",
            condition_per=1, condition_max_stacks=200, consume_condition=True,
        )
        skill = Skill("Passiva escalável", 4, 2, 2, effects=(effect,))
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, skill.name).effects, (effect,))

    def test_user_charge_count_and_poise_potency_conditions_are_persisted(self):
        effects = (
            SkillEffect(
                "on_use", "final_power", 2, charge_cost=5,
                condition_status="charge", condition_min=10,
                condition_owner="user", condition_value="count",
                condition_per=5, condition_max_stacks=2,
            ),
            SkillEffect(
                "on_use", "coin_power", 1,
                condition_status="poise", condition_min=4,
                condition_owner="user", condition_value="potency",
            ),
        )
        skill = Skill("Recursos", 4, 2, 2, effects=effects)
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, "Recursos").effects, effects)

    def test_individual_coin_layout_is_persisted(self):
        skill = Skill(
            "Layout", 4, 2, 3,
            coin_layout=("normal", "unbreakable", "normal"),
        )
        self.db.save_skill(1, 100, skill)
        loaded = self.db.get_skill(1, 100, "Layout")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.coin_layout, skill.coin_layout)

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

    def test_unopposed_player_action_is_registered_and_cleared_next_turn(self):
        self.db.start_battle(1, 10, "Teste", 99)
        action = self.db.add_player_action(
            1, 10, 100, "Sancho", "Hostil", "Réplica", "unopposed", 12,
        )
        self.assertEqual(action["final_damage"], 12)
        self.assertEqual(len(self.db.list_player_actions(1, 10)), 1)
        self.db.next_battle_turn(1, 10)
        self.assertEqual(self.db.list_player_actions(1, 10), [])

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

    def test_defense_level_modifier_is_saved_and_consumed(self):
        self.db.create_character(1, 100, "Sancho")
        row = self.db.add_effects(1, 100, 0, 0, 0, 0, 0, -3)
        self.assertEqual(row["defense_level_mod"], -3)

        self.db.consume_clash_effects(1, 100, 0)

        self.assertEqual(self.db.get_character(1, 100)["defense_level_mod"], 0)

    def test_enemy_defense_level_modifier_is_saved_and_consumed(self):
        enemy = self.db.save_enemy(1, 999, "Hostil", 0, 10, 10)
        row = self.db.add_enemy_effects(enemy["id"], 0, 0, 0, 0, 0, -3)
        self.assertEqual(row["defense_level_mod"], -3)

        self.db.consume_enemy_effects(enemy["id"], 0)

        self.assertEqual(self.db.get_enemy_by_id(enemy["id"])["defense_level_mod"], 0)

    def test_enemy_groups_create_and_add_independent_members(self):
        enemy = self.db.save_enemy(1, 999, "Boneco", -10, 4, 3)

        members = self.db.create_enemy_group(1, enemy["id"], "Grupo de teste", 2, 25)
        more = self.db.add_enemy_group_members(1, self.db.list_enemy_groups(1)[0]["id"], 1)

        self.assertEqual(len(members), 2)
        self.assertEqual(len(more), 3)
        self.assertEqual([row["hp"] for row in more], [25, 25, 25])
        self.assertEqual([row["sp"] for row in more], [-10, -10, -10])

    def test_status_potency_and_count_are_persisted_with_charge_cap(self):
        self.db.set_status(1, "player", 100, "burn", 5, 3)
        self.db.set_status(1, "player", 100, "charge", 0, 99)
        self.assertEqual(self.db.get_status(1, "player", 100, "burn").potency, 5)
        self.assertEqual(self.db.get_status(1, "player", 100, "charge").count, 20)

    def test_first_status_application_supplies_missing_initial_value(self):
        count_only = self.db.add_status(1, "player", 100, "bleed", 0, 3)
        potency_only = self.db.add_status(1, "player", 101, "rupture", 4, 0)
        self.assertEqual((count_only.potency, count_only.count), (1, 3))
        self.assertEqual((potency_only.potency, potency_only.count), (4, 1))
        stacked = self.db.add_status(1, "player", 100, "bleed", 0, 2)
        self.assertEqual((stacked.potency, stacked.count), (1, 5))

    def test_charge_consumption_builds_potency_every_ten_spent(self):
        self.db.create_character(1, 100, "W Corp")
        self.db.set_charge_potency_mode(1, "player", 100, True)
        self.db.add_status(1, "player", 100, "charge", 0, 20)

        first, gain, progress = self.db.consume_charge(1, "player", 100, 6)
        self.assertEqual((first.potency, first.count, gain, progress), (1, 14, 0, 6))
        second, gain, progress = self.db.consume_charge(1, "player", 100, 4)
        self.assertEqual((second.potency, second.count, gain, progress), (2, 10, 1, 0))

    def test_status_is_removed_when_count_reaches_zero(self):
        self.db.create_character(1, 100, "W Corp")
        self.db.set_charge_potency_mode(1, "player", 100, True)
        self.db.set_status(1, "player", 100, "charge", 2, 5)
        saved, _, _ = self.db.consume_charge(1, "player", 100, 5)
        self.assertEqual((saved.potency, saved.count), (0, 0))
        self.assertIsNone(self.db.get_status(1, "player", 100, "charge"))

    def test_reapplying_count_does_not_restore_expired_potency(self):
        self.db.set_status(1, "player", 100, "bleed", 7, 1)
        self.db.set_status(1, "player", 100, "bleed", 7, 0)
        restored = self.db.add_status(1, "player", 100, "bleed", 0, 3)
        self.assertEqual((restored.potency, restored.count), (1, 3))

    def test_new_encounter_resets_charge_consumption_progress(self):
        self.db.create_character(1, 100, "W Corp")
        self.db.set_charge_potency_mode(1, "player", 100, True)
        self.db.add_status(1, "player", 100, "charge", 0, 10)
        self.db.consume_charge(1, "player", 100, 6)
        self.assertEqual(self.db.get_character(1, 100)["charge_spent"], 6)
        self.db.start_battle(1, 10, "Novo encontro", 999)
        self.assertEqual(self.db.get_character(1, 100)["charge_spent"], 0)

    def test_special_condition_tracks_consumed_total_for_current_encounter(self):
        self.db.create_character(1, 100, "Hemófago")
        self.db.set_status(1, "player", 100, "special_condition", 1, 24)

        saved, consumed, encounter_total = self.db.consume_special_condition(
            1, "player", 100, 10,
        )
        self.assertEqual((saved.count, consumed, encounter_total), (14, 10, 10))
        saved, consumed, encounter_total = self.db.consume_special_condition(
            1, "player", 100, 20,
        )
        self.assertEqual((saved.count, consumed, encounter_total), (0, 14, 24))

        self.db.start_battle(1, 10, "Novo encontro", 999)
        self.assertEqual(self.db.get_special_condition_consumed(1, "player", 100), 0)

    def test_character_markers_and_devotion_are_persisted(self):
        bloodfiend = self.db.set_status(1, "enemy", 50, "bloodfiend", 1, 1)
        devotion = self.db.set_status(1, "player", 100, "devotion_repressed", 1, 3)
        self.assertEqual((bloodfiend.potency, bloodfiend.count), (1, 1))
        self.assertEqual((devotion.potency, devotion.count), (1, 3))

    def test_enemy_tags_are_normalized_and_persisted(self):
        enemy = self.db.save_enemy(1, 999, "Nobre", 0, 5, 5)
        saved = self.db.set_enemy_tags(
            1, enemy["id"], ["Bloodfiend", " bloodfiend ", "Chefe", ""],
        )
        self.assertEqual(saved, ["Bloodfiend", "Chefe"])
        self.assertEqual(self.db.get_enemy_tags(enemy["id"]), ["Bloodfiend", "Chefe"])

    def test_consumed_encounter_condition_and_consume_effect_are_persisted(self):
        effects = (
            SkillEffect("on_use", "consume_special_condition", 15),
            SkillEffect(
                "before_attack", "damage_percent", 5,
                condition_status="special_condition_consumed", condition_min=20,
                condition_owner="user", condition_value="count",
                condition_per=20, condition_max_stacks=6,
            ),
        )
        skill = Skill("Fome", 4, 4, 2, effects=effects)
        self.db.save_skill(1, 100, skill)
        self.assertEqual(self.db.get_skill(1, 100, "Fome").effects, effects)

    def test_round_end_deals_burn_and_decrements_supported_counts(self):
        self.db.set_status(1, "player", 100, "burn", 4, 2)
        self.db.set_status(1, "player", 100, "poise", 3, 2)
        events = self.db.process_round_end_statuses(1)
        burn = next(event for _, _, event in events if event.status_type == "burn")
        self.assertEqual(burn.damage, 4)
        self.assertEqual(self.db.get_status(1, "player", 100, "burn").count, 1)
        self.assertEqual(self.db.get_status(1, "player", 100, "poise").count, 1)

    def test_amplitude_conversion_round_trip_preserves_potency_and_count(self):
        self.db.set_status(1, "player", 100, "tremor", 7, 3)

        converted = self.db.convert_tremor(1, "player", 100, "scorch")

        self.assertEqual(
            (converted.potency, converted.count, converted.tremor_type),
            (7, 3, "scorch"),
        )
        stored = self.db.get_status(1, "player", 100, "tremor")
        self.assertEqual(stored.tremor_type, "scorch")

    def test_reapplying_tremor_keeps_the_converted_variant(self):
        self.db.set_status(1, "player", 100, "tremor", 7, 3)
        self.db.convert_tremor(1, "player", 100, "scorch")

        self.db.set_status(1, "player", 100, "tremor", 9, 4)

        stored = self.db.get_status(1, "player", 100, "tremor")
        self.assertEqual((stored.potency, stored.count), (9, 4))
        self.assertEqual(stored.tremor_type, "scorch")

    def test_round_end_keeps_variant_and_labels_the_decay_event(self):
        self.db.set_status(1, "player", 100, "tremor", 7, 3)
        self.db.convert_tremor(1, "player", 100, "scorch")

        events = self.db.process_round_end_statuses(1)

        tremor_event = next(
            event for _, _, event in events if event.status_type == "tremor"
        )
        self.assertEqual(tremor_event.label, "Tremor - Scorch")
        stored = self.db.get_status(1, "player", 100, "tremor")
        self.assertEqual((stored.count, stored.tremor_type), (2, "scorch"))

    def test_convert_tremor_handles_missing_status_and_bad_target(self):
        self.assertIsNone(self.db.convert_tremor(1, "player", 100, "scorch"))
        with self.assertRaisesRegex(ValueError, "Tipo de Tremor"):
            self.db.convert_tremor(1, "player", 100, "reverb")

    def test_group_member_tremor_variant_is_persisted(self):
        enemy = self.db.save_enemy(1, 999, "Boneco", -10, 4, 3)
        member = self.db.create_enemy_group(
            1, enemy["id"], "Grupo convertido", 1, 25
        )[0]
        self.db.set_status(1, "enemy_group_member", member["id"], "tremor", 6, 2)

        self.db.convert_tremor(1, "enemy_group_member", member["id"], "scorch")

        stored = self.db.get_status(1, "enemy_group_member", member["id"], "tremor")
        self.assertEqual(
            (stored.potency, stored.count, stored.tremor_type), (6, 2, "scorch")
        )

    def test_next_turn_only_processes_statuses_inside_that_battle(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.db.join_battle(1, 10, 100, "Sancho")
        self.db.set_status(1, "player", 100, "burn", 4, 2)
        self.db.set_status(1, "player", 200, "burn", 9, 2)

        self.db.next_battle_turn(1, 10)

        self.assertEqual(self.db.get_status(1, "player", 100, "burn").count, 1)
        self.assertEqual(self.db.get_status(1, "player", 200, "burn").count, 2)
        self.assertEqual(sum(event.damage for _, _, event in self.db.last_round_status_events), 4)

    def test_battle_phase_is_persisted_and_next_turn_returns_to_preparation(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.assertEqual(self.db.get_battle(1, 10)["phase"], "preparation")
        self.db.set_battle_phase(1, 10, "declaration")
        self.db.set_battle_phase(1, 10, "resolution")
        self.db.set_battle_phase(1, 10, "complete")
        self.assertEqual(self.db.get_battle(1, 10)["phase"], "complete")

        self.db.next_battle_turn(1, 10)

        self.assertEqual(self.db.get_battle(1, 10)["phase"], "preparation")

    def test_readiness_advances_every_phase_and_starts_next_turn(self):
        self.db.start_battle(1, 10, "Teste", 99)
        self.db.join_battle(1, 10, 100, "Sancho")
        self.db.join_battle(1, 10, 101, "Don")
        self.db.add_field_action(1, 10, "Hostil", "Golpe")

        for user_id in (100, 101):
            self.db.set_battle_participant_ready(1, 10, user_id, True)
        self.assertEqual(advance_when_all_ready(self.db, 1, 10)[0], "declaration")
        self.assertEqual(self.db.get_battle(1, 10)["phase"], "declaration")

        for user_id in (100, 101):
            self.db.set_battle_participant_ready(1, 10, user_id, True)
        self.assertEqual(advance_when_all_ready(self.db, 1, 10)[0], "resolution")
        self.assertEqual(self.db.get_battle(1, 10)["phase"], "resolution")

        for user_id in (100, 101):
            self.db.set_battle_participant_ready(1, 10, user_id, True)
        self.assertEqual(advance_when_all_ready(self.db, 1, 10)[0], "preparation")
        self.assertEqual(self.db.get_battle(1, 10)["turn"], 2)
        self.assertEqual(self.db.list_field_actions(1, 10), [])


if __name__ == "__main__":
    unittest.main()
