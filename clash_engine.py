"""Motor puro das moedas, sanidade e Clash."""

from __future__ import annotations

from dataclasses import dataclass, field
import random


MIN_SP = -45
MAX_SP = 45


def clamp_sp(value: int) -> int:
    return max(MIN_SP, min(MAX_SP, value))


def heads_chance(sp: int) -> float:
    """0 SP = 50%; cada ponto de SP altera a chance em 1%."""
    return (50 + clamp_sp(sp)) / 100


@dataclass(frozen=True)
class Skill:
    name: str
    base_power: int
    coin_power: int
    coins: int
    description: str = ""
    level_type: str = "offense"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A skill precisa de um nome.")
        if not 1 <= self.coins <= 10:
            raise ValueError("A quantidade de moedas deve ficar entre 1 e 10.")
        if self.level_type not in ("offense", "defense"):
            raise ValueError("level_type deve ser offense ou defense.")

    def range_with(self, remaining_coins: int | None = None) -> tuple[int, int]:
        count = self.coins if remaining_coins is None else remaining_coins
        values = (self.base_power, self.base_power + self.coin_power * count)
        return min(values), max(values)


@dataclass
class Roll:
    power: int
    faces: list[bool]

    @property
    def heads(self) -> int:
        return sum(self.faces)

    @property
    def face_text(self) -> str:
        return " ".join("H" if face else "T" for face in self.faces)


@dataclass
class ClashRound:
    number: int
    left: Roll
    right: Roll
    result: str


@dataclass
class ClashResult:
    winner: str
    left_coins: int
    right_coins: int
    rounds: list[ClashRound] = field(default_factory=list)
    left_paralysis: int = 0
    right_paralysis: int = 0


@dataclass
class Modifiers:
    base_power: int = 0
    coin_power: int = 0
    paralysis: int = 0
    level: int = 0


@dataclass
class AttackHit:
    coin: int
    face: bool
    power: int


def roll_skill(
    skill: Skill, sp: int, remaining_coins: int, rng: random.Random,
    modifiers: Modifiers | None = None,
) -> tuple[Roll, int]:
    modifiers = modifiers or Modifiers()
    faces = [rng.random() < heads_chance(sp) for _ in range(remaining_coins)]
    paralysis_used = min(modifiers.paralysis, remaining_coins)
    effective_heads = sum(faces[paralysis_used:])
    power = skill.base_power + modifiers.base_power
    power += (skill.coin_power + modifiers.coin_power) * effective_heads
    return Roll(power, faces), modifiers.paralysis - paralysis_used


def resolve_clash(
    left: Skill,
    left_sp: int,
    right: Skill,
    right_sp: int,
    *,
    rng: random.Random | None = None,
    max_rounds: int = 100,
    left_modifiers: Modifiers | None = None,
    right_modifiers: Modifiers | None = None,
) -> ClashResult:
    """Empates repetem a rodada; quem perde uma rodada perde uma moeda."""
    rng = rng or random.Random()
    left_coins, right_coins = left.coins, right.coins
    left_modifiers = left_modifiers or Modifiers()
    right_modifiers = right_modifiers or Modifiers()
    level_difference = left_modifiers.level - right_modifiers.level
    left_level_bonus = max(0, level_difference // 3)
    right_level_bonus = max(0, (-level_difference) // 3)
    rounds: list[ClashRound] = []

    for number in range(1, max_rounds + 1):
        left_roll, left_modifiers.paralysis = roll_skill(left, left_sp, left_coins, rng, left_modifiers)
        right_roll, right_modifiers.paralysis = roll_skill(right, right_sp, right_coins, rng, right_modifiers)
        left_roll.power += left_level_bonus
        right_roll.power += right_level_bonus
        if left_roll.power > right_roll.power:
            right_coins -= 1
            result = "left"
        elif right_roll.power > left_roll.power:
            left_coins -= 1
            result = "right"
        else:
            result = "tie"
        rounds.append(ClashRound(number, left_roll, right_roll, result))

        if left_coins == 0:
            return ClashResult("right", left_coins, right_coins, rounds, left_modifiers.paralysis, right_modifiers.paralysis)
        if right_coins == 0:
            return ClashResult("left", left_coins, right_coins, rounds, left_modifiers.paralysis, right_modifiers.paralysis)

    raise RuntimeError("Clash excedeu o limite de rodadas; tente novamente.")


def resolve_attack(
    skill: Skill, sp: int, remaining_coins: int, *, rng: random.Random | None = None
) -> list[AttackHit]:
    """No ataque, cada moeda é jogada em sequência e Heads acumulam Coin Power."""
    rng = rng or random.Random()
    power = skill.base_power
    hits: list[AttackHit] = []
    for coin in range(1, remaining_coins + 1):
        face = rng.random() < heads_chance(sp)
        if face:
            power += skill.coin_power
        hits.append(AttackHit(coin, face, power))
    return hits
