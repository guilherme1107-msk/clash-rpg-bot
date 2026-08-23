"""Entidades e objetos de valor puros do combate."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


MIN_SP = -45
MAX_SP = 45
MAX_COINS = 10


class CoinKind(StrEnum):
    NORMAL = "normal"
    UNBREAKABLE = "unbreakable"


@dataclass(frozen=True, slots=True)
class CoinSpec:
    kind: CoinKind = CoinKind.NORMAL


@dataclass(frozen=True, slots=True)
class Modifiers:
    base_power: int = 0
    coin_power: int = 0
    clash_power: int = 0
    offense_level: int = 0
    defense_level: int = 0


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    base_power: int
    coin_power: int
    coins: tuple[CoinSpec, ...]
    description: str = ""
    uses_defense_level: bool = False

    def __post_init__(self) -> None:
        clean_name = self.name.strip()
        if not clean_name:
            raise ValueError("A skill precisa de um nome.")
        if not 1 <= len(self.coins) <= MAX_COINS:
            raise ValueError(f"A skill deve possuir entre 1 e {MAX_COINS} moedas.")
        object.__setattr__(self, "name", clean_name)


@dataclass(frozen=True, slots=True)
class Combatant:
    identifier: str
    name: str
    sanity: int = 0
    offense_level: int = 0
    defense_level: int = 0
    paralysis: int = 0
    modifiers: Modifiers = field(default_factory=Modifiers)
    uses_sanity: bool = True

    def __post_init__(self) -> None:
        if not self.identifier.strip() or not self.name.strip():
            raise ValueError("Combatente precisa de identificador e nome.")
        if self.uses_sanity and not MIN_SP <= self.sanity <= MAX_SP:
            raise ValueError(f"Sanidade deve ficar entre {MIN_SP} e {MAX_SP}.")
        if self.paralysis < 0:
            raise ValueError("Paralisia não pode ser negativa.")

    @property
    def heads_chance(self) -> float:
        if not self.uses_sanity:
            return 0.5
        return (50 + self.sanity) / 100

