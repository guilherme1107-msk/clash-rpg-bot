"""Regras de ficha compartilhadas por bot, Activity e Central.

Este módulo não conhece Discord, HTTP ou SQLite. Assim todos os clientes usam
o mesmo cálculo de progressão sem copiar fórmulas para suas interfaces.
"""

from __future__ import annotations


def default_profile() -> dict:
    return {
        "version": 1, "uptie": 1, "level": 1, "hp": 0, "max_hp": 0,
        "max_hp_override": 0, "automatic_max_hp": 0,
        "sp": 0, "rd": 0, "movement": 9, "light": 0, "max_light": 3,
        "stagger": 0, "max_stagger": 0, "hp_roll_total": 54,
        "special_effect_name": "Efeito Trashholder",
        "attributes": {
            "strength": 10, "dexterity": 10, "constitution": 10,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
        },
        "proficiencies": [], "resistances": [], "passives": [],
        "identity": {
            "age": "", "origin": "", "affiliation": "",
            "description": "", "appearance": "",
        },
        "records": {
            "inventory": [], "notes": [], "relationships": [], "memories": [],
        },
    }


def ability_modifier(value: int) -> int:
    return max(-5, min(10, (value - 10) // 2))


def normalize_profile(raw: object) -> dict:
    """Valida a ficha e recalcula todos os valores derivados do nível."""
    base = default_profile()
    if not isinstance(raw, dict):
        return base
    integer_fields = (
        "uptie", "level", "hp", "max_hp", "sp", "light", "max_light",
        "stagger", "max_stagger", "hp_roll_total", "rd", "movement", "max_hp_override",
    )
    for key in integer_fields:
        if key in raw:
            try:
                base[key] = int(raw[key])
            except (TypeError, ValueError):
                pass
    base["uptie"] = max(1, min(5, base["uptie"]))
    base["level"] = max(1, min(100, base["level"]))
    base["sp"] = max(-45, min(45, base["sp"]))
    base["hp_roll_total"] = max(1, min(200, base["hp_roll_total"]))
    if "special_effect_name" in raw:
        custom_name = str(raw.get("special_effect_name") or "").strip()
        base["special_effect_name"] = custom_name[:40] or "Efeito Trashholder"

    attrs = raw.get("attributes", {})
    if isinstance(attrs, dict):
        for key in base["attributes"]:
            try:
                base["attributes"][key] = max(
                    1, min(30, int(attrs.get(key, base["attributes"][key])))
                )
            except (TypeError, ValueError):
                pass
    for key in ("proficiencies", "resistances", "passives"):
        if isinstance(raw.get(key), list):
            base[key] = raw[key][:40]
    for key in ("identity", "records"):
        if isinstance(raw.get(key), dict):
            base[key].update(raw[key])

    constitution = ability_modifier(base["attributes"]["constitution"])
    strength = ability_modifier(base["attributes"]["strength"])
    base["offense_level"] = base["level"] * (3 + strength // 2)
    base["defense_level"] = base["level"] * (3 + constitution // 2)
    automatic_max_hp = max(
        1,
        base["hp_roll_total"] + 50 + 10 * max(0, constitution)
        + (base["level"] - 1) * (5 + constitution),
    )
    base["automatic_max_hp"] = automatic_max_hp
    base["max_hp_override"] = max(0, min(99999, base["max_hp_override"]))
    base["max_hp"] = base["max_hp_override"] or automatic_max_hp
    base["stagger_thresholds"] = [round(base["max_hp"] * 0.20), round(base["max_hp"] * 0.50)]
    base["max_stagger"] = base["max_hp"] // 2
    base["max_light"] = 3 + base["level"] // 4 + (
        7 if base["level"] >= 30 else 5 if base["level"] >= 20 else 0
    )
    for key in ("hp", "light", "stagger"):
        maximum = base["max_" + key]
        base[key] = max(0, min(maximum, base[key] if key in raw else maximum))
    return base


def normalize_profile_update(raw: object, previous: object) -> dict:
    """Normaliza uma edição e conserva o dano ao aumentar o nível.

    Quando a progressão aumenta a Vida Máxima, a Vida Atual recebe o mesmo
    acréscimo. Assim subir de nível não deixa o personagem artificialmente mais
    ferido, mas também não funciona como uma cura completa.
    """
    old_profile = normalize_profile(previous)
    new_profile = normalize_profile(raw)
    if new_profile["level"] > old_profile["level"]:
        gained_hp = max(0, new_profile["max_hp"] - old_profile["max_hp"])
        new_profile["hp"] = min(new_profile["max_hp"], new_profile["hp"] + gained_hp)
    return new_profile
