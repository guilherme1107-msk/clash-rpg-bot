"""API pública do domínio de combate."""

from src.domain.models import (
    MAX_SP,
    MIN_SP,
    EFFECT_TRIGGERS,
    EFFECT_TYPES,
    AttackHit,
    ClashResult,
    ClashRound,
    DamageResult,
    DefenseResult,
    Forecast,
    Modifiers,
    Roll,
    Skill,
    SkillEffect,
    clamp_sp,
    format_skill_effects,
    heads_chance,
    parse_skill_effects,
    triggered_skill_effects,
)
from .engine import (
    clashable_guard_values,
    estimate_clash,
    forecast_label,
    resolve_attack,
    resolve_clash,
    resolve_damage,
    apply_damage_percentage,
    resolve_defense,
    roll_skill,
)

__all__ = [
    "MAX_SP", "MIN_SP", "EFFECT_TRIGGERS", "EFFECT_TYPES",
    "AttackHit", "ClashResult", "ClashRound", "DamageResult", "DefenseResult",
    "Forecast", "Modifiers", "Roll", "Skill", "SkillEffect", "clamp_sp",
    "format_skill_effects", "heads_chance", "parse_skill_effects",
    "triggered_skill_effects", "estimate_clash", "forecast_label", "resolve_attack",
    "resolve_clash", "resolve_damage", "apply_damage_percentage", "resolve_defense", "roll_skill",
    "clashable_guard_values",
]
