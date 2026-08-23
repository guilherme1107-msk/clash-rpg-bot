"""Resolução determinística e auditável de Clash."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .models import CoinKind, Combatant, Skill


@dataclass(frozen=True, slots=True)
class CoinState:
    position: int
    kind: CoinKind
    active: bool = True
    fractured: bool = False


@dataclass(frozen=True, slots=True)
class PowerRoll:
    power: int
    heads: tuple[bool, ...]
    paralyzed: tuple[bool, ...]
    paralysis_remaining: int


@dataclass(frozen=True, slots=True)
class ClashRound:
    number: int
    left_roll: PowerRoll
    right_roll: PowerRoll
    winner: str | None
    left_coins: tuple[CoinState, ...]
    right_coins: tuple[CoinState, ...]


@dataclass(frozen=True, slots=True)
class ClashResult:
    winner: str
    loser: str
    rounds: tuple[ClashRound, ...]
    left_coins: tuple[CoinState, ...]
    right_coins: tuple[CoinState, ...]
    left_paralysis: int
    right_paralysis: int

    def fractured_follow_up(self, side: str) -> tuple[CoinState, ...]:
        coins = self.left_coins if side == "left" else self.right_coins
        return tuple(coin for coin in coins if coin.fractured)


def _level_for(skill: Skill, owner: Combatant) -> int:
    if skill.uses_defense_level:
        return owner.defense_level + owner.modifiers.defense_level
    return owner.offense_level + owner.modifiers.offense_level


def _roll(
    skill: Skill,
    owner: Combatant,
    coins: tuple[CoinState, ...],
    paralysis: int,
    level_bonus: int,
    rng: Random,
) -> PowerRoll:
    heads: list[bool] = []
    paralyzed: list[bool] = []
    coin_power = skill.coin_power
    if coin_power > 0:
        coin_power += owner.modifiers.coin_power

    power = skill.base_power + owner.modifiers.base_power + owner.modifiers.clash_power
    power += level_bonus
    for coin in (coin for coin in coins if coin.active):
        is_head = rng.random() < owner.heads_chance
        is_paralyzed = paralysis > 0
        if is_paralyzed:
            paralysis -= 1
        elif is_head:
            power += coin_power
        heads.append(is_head)
        paralyzed.append(is_paralyzed)
    return PowerRoll(power, tuple(heads), tuple(paralyzed), paralysis)


def _lose_coin(coins: tuple[CoinState, ...]) -> tuple[CoinState, ...]:
    result = list(coins)
    index = max(index for index, coin in enumerate(result) if coin.active)
    coin = result[index]
    result[index] = CoinState(
        position=coin.position,
        kind=coin.kind,
        active=False,
        fractured=coin.kind is CoinKind.UNBREAKABLE,
    )
    return tuple(result)


def _has_active(coins: tuple[CoinState, ...]) -> bool:
    return any(coin.active for coin in coins)


def resolve_clash(
    left: Combatant,
    left_skill: Skill,
    right: Combatant,
    right_skill: Skill,
    *,
    rng: Random | None = None,
    max_rounds: int = 100,
) -> ClashResult:
    """Resolve um Clash sem modificar combatentes ou skills de entrada."""

    randomizer = rng or Random()
    left_coins = tuple(CoinState(i + 1, spec.kind) for i, spec in enumerate(left_skill.coins))
    right_coins = tuple(CoinState(i + 1, spec.kind) for i, spec in enumerate(right_skill.coins))
    left_paralysis = left.paralysis
    right_paralysis = right.paralysis
    rounds: list[ClashRound] = []

    level_difference = _level_for(left_skill, left) - _level_for(right_skill, right)
    left_level_bonus = max(0, level_difference // 3)
    right_level_bonus = max(0, (-level_difference) // 3)

    for number in range(1, max_rounds + 1):
        left_roll = _roll(
            left_skill, left, left_coins, left_paralysis, left_level_bonus, randomizer
        )
        right_roll = _roll(
            right_skill, right, right_coins, right_paralysis, right_level_bonus, randomizer
        )
        left_paralysis = left_roll.paralysis_remaining
        right_paralysis = right_roll.paralysis_remaining

        round_winner: str | None = None
        if left_roll.power > right_roll.power:
            round_winner = "left"
            right_coins = _lose_coin(right_coins)
        elif right_roll.power > left_roll.power:
            round_winner = "right"
            left_coins = _lose_coin(left_coins)

        rounds.append(
            ClashRound(
                number,
                left_roll,
                right_roll,
                round_winner,
                left_coins,
                right_coins,
            )
        )

        if not _has_active(left_coins):
            return ClashResult(
                "right", "left", tuple(rounds), left_coins, right_coins,
                left_paralysis, right_paralysis,
            )
        if not _has_active(right_coins):
            return ClashResult(
                "left", "right", tuple(rounds), left_coins, right_coins,
                left_paralysis, right_paralysis,
            )

    raise RuntimeError(f"Clash não terminou após {max_rounds} rodadas.")

