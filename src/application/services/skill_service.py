"""Validação única para Skills recebidas pelas interfaces."""
from __future__ import annotations
import math
import re
from src.domain.combat import EFFECT_TRIGGERS, EFFECT_TYPES, Skill, SkillEffect

DEFENSIVE_SKILL_TYPES = {"guard", "evade", "counter", "clashable_guard", "clashable_counter", "assist_defense", "defense"}

# Condições aceitas em `condition_status`. Fica no módulo (e não dentro da
# função) para que o editor do Control Center leia a MESMA lista que valida —
# era uma cópia escrita à mão no HTML que já tinha divergido.
VALID_CONDITIONS = {"burn","bleed","tremor","rupture","sinking","poise","charge","haste","special_condition","special_condition_consumed","bloodfeast","bloodfeast_consumed","shared_bloodfeast_consumed","allies_with_keyword","bloodfiend_or_bloodbag","paralysis","sp","base_power","coin_power","clash_power","offense_level","defense_level"}

def normalize_skill_slot(value: object, skill_type: str = "attack") -> str:
    slot = str(value or "").strip().lower()
    attack_match = re.fullmatch(r"s([1-3])(?:-([1-9]|1\d|20))?", slot)
    defense_match = re.fullmatch(r"d([1-9]|1\d|20)(?:-([1-9]|1\d|20))?", slot)
    if attack_match:
        return slot
    if defense_match:
        return slot
    return "d1" if skill_type in DEFENSIVE_SKILL_TYPES else "s1"

def parse_skill_payload(payload: object) -> tuple[Skill, str]:
    if not isinstance(payload, dict): raise ValueError("Skill inválida.")
    name = str(payload.get("name", "")).strip(); coins = int(payload.get("coins", 0)); skill_type = str(payload.get("skill_type", "attack"))[:20]
    if not name or len(name) > 50 or not 1 <= coins <= 10: raise ValueError("Nome (até 50 caracteres) e 1–10 moedas são obrigatórios.")
    raw_effects = payload.get("effects", [])
    if not isinstance(raw_effects, list) or len(raw_effects) > 20: raise ValueError("Uma skill pode ter no máximo 20 efeitos.")
    # `max_per_round` e `condition_turn` estavam fora desta lista e eram
    # descartados em silêncio ao salvar uma skill pela UI.
    allowed = {"trigger","effect_type","value","coin","count","charge_cost","condition_status","condition_min","condition_owner","condition_value","condition_per","condition_max_stacks","consume_condition","effect_owner","condition_operator","max_per_round","condition_turn","condition_keyword"}
    counted = {"burn","bleed","tremor","rupture","sinking","poise","charge","haste","special_condition","bloodfeast","self_bleed"}; effects = []
    for index, item in enumerate(raw_effects, 1):
        if not isinstance(item, dict): raise ValueError(f"Efeito {index}: configuração inválida.")
        clean = {key:item[key] for key in allowed if key in item}
        clean["trigger"] = str(clean.get("trigger") or "").strip()
        clean["effect_type"] = str(clean.get("effect_type") or "").strip()
        if not clean["trigger"] or not clean["effect_type"]: raise ValueError(f"Efeito {index}: selecione o gatilho e o tipo do efeito.")
        if clean["trigger"] not in EFFECT_TRIGGERS or clean["effect_type"] not in EFFECT_TYPES: raise ValueError(f"Efeito {index}: gatilho ou tipo não reconhecido.")
        # Falha fechada: o escudo é lido **só** de `ego_gifts` (por
        # `gift_shield`, que soma no número solto do Clash). Numa skill ele
        # não faria nada — e o mestre só descobriria no meio do combate.
        if clean["effect_type"] == "shield": raise ValueError(f"Efeito {index}: Escudo é de E.G.O Gift — numa skill ele não faria nada, porque só os gifts entram no `gift_shield`.")
        if clean["trigger"] == "on_evade" and skill_type != "evade": raise ValueError(f"Efeito {index}: Ao Esquivar só pode ser usado em uma skill Evasiva.")
        try:
            clean["value"] = float(clean.get("value", 0) or 0)
            if not math.isfinite(clean["value"]): raise ValueError
            for key in ("coin", "count"): clean[key] = None if clean.get(key) in {None, ""} else int(clean[key])
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Efeito {index}: valor, Count ou moeda inválido.") from None
        if clean["coin"] is not None and not 1 <= clean["coin"] <= coins: raise ValueError(f"Efeito {index}: a moeda deve estar entre 1 e {coins}.")
        if clean["effect_type"] not in counted: clean["count"] = None
        elif clean["count"] is None: raise ValueError(f"Efeito {index}: {clean['effect_type'].title()} precisa de Count (use 0 se não aplicar Count).")
        try:
            for key in ("charge_cost","condition_min","condition_per","condition_max_stacks"): clean[key] = int(clean.get(key, 0) or 0)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Efeito {index}: custo ou condição numérica inválida.") from None
        clean["effect_owner"] = str(clean.get("effect_owner") or "auto").strip()
        condition = str(clean.get("condition_status") or "").strip()
        if condition == "false_hunger": condition = "bloodfeast"
        clean["condition_status"] = condition or None
        if clean["condition_status"] is None:
            clean.update(condition_owner="target", condition_value="potency", condition_operator="at_least", condition_min=0, condition_per=0, condition_max_stacks=0, consume_condition=False)
        else:
            if clean["condition_status"] not in VALID_CONDITIONS: raise ValueError(f"Efeito {index}: condição não reconhecida.")
            clean["condition_owner"] = str(clean.get("condition_owner") or "target")
            clean["condition_value"] = str(clean.get("condition_value") or "potency")
            clean["condition_operator"] = str(clean.get("condition_operator") or "at_least")
            clean["consume_condition"] = bool(clean.get("consume_condition", False))
        try:
            effects.append(SkillEffect(**clean))
        except ValueError as error:
            raise ValueError(f"Efeito {index}: {error}") from None
    layout = payload.get("coin_layout", ["normal"] * coins)
    if not isinstance(layout, (list, tuple)) or len(layout) != coins or any(item not in {"normal","unbreakable"} for item in layout): raise ValueError("Layout de moedas inválido.")
    skill = Skill(name, max(-99,min(99,int(payload.get("base_power",0)))), max(-99,min(99,int(payload.get("coin_power",0)))), coins, str(payload.get("description",""))[:300], skill_type, tuple(layout).count("unbreakable"), tuple(effects), tuple(layout))
    return skill, str(payload.get("old_name", "")).strip()
