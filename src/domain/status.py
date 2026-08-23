"""Regras puras dos principais status de combate."""

from __future__ import annotations

from dataclasses import dataclass

STATUS_TYPES = {
    "burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge",
    "special_condition", "devotion_repressed", "bloodfiend", "bloodbag",
}


@dataclass(frozen=True)
class CombatStatus:
    status_type: str
    potency: int = 0
    count: int = 0

    def __post_init__(self) -> None:
        if self.status_type not in STATUS_TYPES:
            raise ValueError("Status inválido.")
        if self.potency < 0 or self.count < 0:
            raise ValueError("Potência e Quantidade não podem ser negativas.")
        if self.status_type == "charge" and self.count > 20:
            object.__setattr__(self, "count", 20)


@dataclass(frozen=True)
class StatusEvent:
    status_type: str
    damage: int = 0
    sanity_loss: int = 0
    stagger_threshold: int = 0
    potency_after: int = 0
    count_after: int = 0
    note: str = ""


def on_damage_taken(status: CombatStatus, *, sanity: int | None = None) -> StatusEvent | None:
    if status.count <= 0:
        return None
    remaining = status.count - 1
    if status.status_type == "rupture":
        return StatusEvent("rupture", damage=status.potency, potency_after=status.potency, count_after=remaining)
    if status.status_type == "sinking":
        if sanity is not None and sanity <= -45:
            return StatusEvent("sinking", damage=status.potency, potency_after=status.potency,
                               count_after=remaining, note="Sanidade em -45; convertido em dano.")
        return StatusEvent("sinking", sanity_loss=status.potency, potency_after=status.potency, count_after=remaining)
    return None


def on_action(status: CombatStatus, coins: int = 1) -> StatusEvent | None:
    if status.status_type != "bleed" or status.count <= 0:
        return None
    spent = min(status.count, max(0, coins))
    if spent <= 0:
        return None
    return StatusEvent(
        "bleed", damage=status.potency * spent,
        potency_after=status.potency, count_after=status.count - spent,
        note=f"{spent} moeda(s) ofensiva(s) consumiram Bleed.",
    )


def on_round_end(status: CombatStatus) -> StatusEvent | None:
    if status.count <= 0:
        return None
    count_after = status.count - 1
    if status.status_type == "burn":
        return StatusEvent("burn", damage=status.potency, potency_after=status.potency, count_after=count_after)
    if status.status_type in {"tremor", "sinking", "poise", "charge"}:
        potency_after = status.potency
        if status.status_type == "charge" and count_after == 0 and potency_after < 2:
            potency_after = 0
        return StatusEvent(status.status_type, potency_after=potency_after, count_after=count_after,
                           note="Quantidade reduzida no final da rodada.")
    return None


def tremor_burst(status: CombatStatus) -> StatusEvent:
    if status.status_type != "tremor":
        raise ValueError("Tremor Burst exige Tremor.")
    return StatusEvent("tremor", stagger_threshold=status.potency,
                       potency_after=status.potency, count_after=status.count,
                       note="Ajuste manual de Stagger Threshold.")


def poise_values(status: CombatStatus) -> tuple[int, float]:
    if status.status_type != "poise":
        raise ValueError("O cálculo exige Poise.")
    return status.potency * 2, status.potency / 10
