"""Motor puro das moedas, sanidade e Clash."""

from __future__ import annotations

from dataclasses import dataclass, field
import random


MIN_SP = -45
MAX_SP = 45

EFFECT_TRIGGERS = {
    "on_use", "on_hit", "heads_hit", "clash_win", "clash_lose", "before_attack", "after_attack",
}
EFFECT_TYPES = {
    "paralysis", "sp", "base_power", "coin_power", "clash_power", "offense_level",
}


def clamp_sp(value: int) -> int:
    return max(MIN_SP, min(MAX_SP, value))


def heads_chance(sp: int) -> float:
    """0 SP = 50%; cada ponto de SP altera a chance em 1%."""
    return (50 + clamp_sp(sp)) / 100


@dataclass(frozen=True)
class SkillEffect:
    trigger: str
    effect_type: str
    value: int
    coin: int | None = None

    def __post_init__(self) -> None:
        if self.trigger not in EFFECT_TRIGGERS:
            raise ValueError("Gatilho de efeito inválido.")
        if self.effect_type not in EFFECT_TYPES:
            raise ValueError("Tipo de efeito inválido.")
        if self.coin is not None and self.coin < 1:
            raise ValueError("A moeda do efeito deve começar em 1.")


def parse_skill_effects(raw: str) -> tuple[SkillEffect, ...]:
    """Lê `gatilho:efeito:valor[:moeda]`, com um efeito por linha ou `;`."""
    effects = []
    for entry in raw.replace(";", "\n").splitlines():
        entry = entry.strip()
        if not entry:
            continue
        parts = [part.strip().lower() for part in entry.split(":")]
        if len(parts) not in {3, 4}:
            raise ValueError("Use gatilho:efeito:valor[:moeda].")
        coin = int(parts[3]) if len(parts) == 4 and parts[3] else None
        effects.append(SkillEffect(parts[0], parts[1], int(parts[2]), coin))
    return tuple(effects)


def format_skill_effects(effects: tuple[SkillEffect, ...]) -> str:
    return "\n".join(
        f"{effect.trigger}:{effect.effect_type}:{effect.value}"
        + (f":{effect.coin}" if effect.coin is not None else "")
        for effect in effects
    )


def triggered_skill_effects(
    skill: "Skill", trigger: str, *, remaining_coins: int | None = None,
    hits: list["AttackHit"] | None = None,
) -> tuple[SkillEffect, ...]:
    """Seleciona efeitos cujo gatilho e condição de moeda foram satisfeitos."""
    selected = []
    for effect in skill.effects:
        if effect.trigger != trigger:
            continue
        if effect.coin is None:
            if trigger == "on_hit":
                selected.extend(effect for _ in (hits or []))
            elif trigger == "heads_hit":
                selected.extend(effect for hit in (hits or []) if hit.face and not hit.paralyzed)
            else:
                selected.append(effect)
            continue
        if trigger in {"on_hit", "heads_hit"}:
            matching = next((hit for hit in (hits or []) if hit.coin == effect.coin), None)
            if matching is None:
                continue
            if trigger == "heads_hit" and (not matching.face or matching.paralyzed):
                continue
            selected.append(effect)
        elif remaining_coins is None or effect.coin <= remaining_coins:
            selected.append(effect)
    return tuple(selected)


@dataclass(frozen=True)
class Skill:
    name: str
    base_power: int
    coin_power: int
    coins: int
    description: str = ""
    skill_type: str = "attack"
    unbreakable_coins: int = 0
    effects: tuple[SkillEffect, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A skill precisa de um nome.")
        if not 1 <= self.coins <= 10:
            raise ValueError("A quantidade de moedas deve ficar entre 1 e 10.")
        if not 0 <= self.unbreakable_coins <= self.coins:
            raise ValueError("Moedas inquebráveis devem ficar entre 0 e o total de moedas.")
        if any(effect.coin is not None and effect.coin > self.coins for effect in self.effects):
            raise ValueError("Um efeito aponta para uma moeda inexistente.")
        allowed = {"attack", "guard", "counter", "evade", "clashable_guard", "clashable_counter", "assist_defense"}
        if self.skill_type not in allowed:
            raise ValueError("Tipo de skill inválido.")

    @property
    def uses_defense_level(self) -> bool:
        return self.skill_type in {"guard", "evade", "clashable_guard", "assist_defense"}

    @property
    def is_clashable(self) -> bool:
        return self.skill_type in {"attack", "clashable_guard", "clashable_counter", "assist_defense"}

    @property
    def deals_damage(self) -> bool:
        return self.skill_type in {"attack", "counter", "clashable_counter"}

    def range_with(self, remaining_coins: int | None = None) -> tuple[int, int]:
        count = self.coins if remaining_coins is None else remaining_coins
        values = (self.base_power, self.base_power + self.coin_power * count)
        return min(values), max(values)


@dataclass
class Roll:
    power: int
    faces: list[bool]
    disabled: list[bool] = field(default_factory=list)
    unbreakable: list[bool] = field(default_factory=list)

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
    left_unbreakable_broken: bool = False
    right_unbreakable_broken: bool = False


@dataclass
class ClashResult:
    winner: str
    left_coins: int
    right_coins: int
    rounds: list[ClashRound] = field(default_factory=list)
    left_paralysis: int = 0
    right_paralysis: int = 0
    left_broken_unbreakable: int = 0
    right_broken_unbreakable: int = 0


@dataclass
class Modifiers:
    base_power: int = 0
    coin_power: int = 0
    paralysis: int = 0
    level: int = 0
    clash_power: int = 0


@dataclass(frozen=True)
class Forecast:
    win_chance: float
    label: str
    label_pt: str


def forecast_label(chance: float) -> tuple[str, str]:
    if chance < 0.20:
        return "HOPELESS", "Sem esperança"
    if chance < 0.40:
        return "STRUGGLING", "Lutando"
    if chance < 0.60:
        return "NEUTRAL", "Neutro"
    if chance < 0.80:
        return "FAVORED", "Favorecido"
    return "DOMINATING", "Dominante"


def estimate_clash(
    left: Skill, left_sp: int, right: Skill, right_sp: int, *,
    left_modifiers: Modifiers | None = None,
    right_modifiers: Modifiers | None = None,
    simulations: int = 1000,
    rng: random.Random | None = None,
) -> Forecast:
    """Estima a vitória do lado esquerdo; não altera o Clash real."""
    if simulations < 1:
        raise ValueError("simulations deve ser positivo")
    rng = rng or random.Random()
    lm, rm = left_modifiers or Modifiers(), right_modifiers or Modifiers()
    wins = 0
    for _ in range(simulations):
        result = resolve_clash(
            left, left_sp, right, right_sp, rng=rng,
            left_modifiers=Modifiers(lm.base_power, lm.coin_power, lm.paralysis, lm.level, lm.clash_power),
            right_modifiers=Modifiers(rm.base_power, rm.coin_power, rm.paralysis, rm.level, rm.clash_power),
        )
        wins += result.winner == "left"
    chance = wins / simulations
    label, label_pt = forecast_label(chance)
    return Forecast(chance, label, label_pt)


@dataclass
class AttackHit:
    coin: int
    face: bool
    power: int
    paralyzed: bool = False
    unbreakable: bool = False
    active_unbreakable: bool = False


@dataclass
class DamageResult:
    hits: list[AttackHit]
    subtotal: int
    level_modifier: int
    final_damage: int
    offense_level: int
    defense_level: int


@dataclass
class DefenseResult:
    kind: str
    success: bool | None
    attack_rolls: list[Roll]
    defense_rolls: list[Roll]
    summary: str
    counter_roll: Roll | None = None


def resolve_defense(
    attack: Skill, attack_sp: int, defense: Skill, defense_sp: int, *,
    attack_modifiers: Modifiers | None = None,
    defense_modifiers: Modifiers | None = None,
    rng: random.Random | None = None,
) -> DefenseResult:
    """Resolve Guard, Evade ou Counter sem HP/dano."""
    rng = rng or random.Random()
    am, dm = attack_modifiers or Modifiers(), defense_modifiers or Modifiers()
    level_bonus = max(0, (dm.level - am.level) // 3)
    if defense.skill_type == "counter":
        attack_roll, _ = roll_skill(attack, attack_sp, attack.coins, rng, am)
        counter_roll, _ = roll_skill(defense, defense_sp, 1, rng, dm)
        return DefenseResult("counter", None, [attack_roll], [], "Moeda de Counter rolada.", counter_roll)
    if defense.skill_type == "guard":
        attack_roll, _ = roll_skill(attack, attack_sp, attack.coins, rng, am)
        defense_roll, _ = roll_skill(defense, defense_sp, 1, rng, dm)
        return DefenseResult("guard", None, [attack_roll], [defense_roll], "Moeda de Defesa rolada.")
    if defense.skill_type == "evade":
        attack_rolls, defense_rolls = [], []
        attack_power = attack.base_power + am.base_power
        paralysis = am.paralysis
        for _ in range(attack.coins):
            face = rng.random() < heads_chance(attack_sp)
            coin_enabled = paralysis <= 0
            paralysis = max(0, paralysis - 1)
            if face and coin_enabled:
                attack_power += attack.coin_power + (am.coin_power if attack.coin_power > 0 else 0)
            ar = Roll(attack_power, [face])
            dr, dm.paralysis = roll_skill(defense, defense_sp, defense.coins, rng, dm)
            dr.power += level_bonus
            attack_rolls.append(ar)
            defense_rolls.append(dr)
            if dr.power < ar.power:
                return DefenseResult("evade", False, attack_rolls, defense_rolls, "Evasão falhou; a sequência foi interrompida.")
        return DefenseResult("evade", True, attack_rolls, defense_rolls, "Todas as moedas foram evadidas.")
    raise ValueError("A skill informada não é uma defesa comum.")


def roll_skill(
    skill: Skill, sp: int, remaining_coins: int, rng: random.Random,
    modifiers: Modifiers | None = None, active_unbreakable: int | None = None,
) -> tuple[Roll, int]:
    modifiers = modifiers or Modifiers()
    faces = [rng.random() < heads_chance(sp) for _ in range(remaining_coins)]
    paralysis_used = min(modifiers.paralysis, remaining_coins)
    disabled = [index < paralysis_used for index in range(remaining_coins)]
    active_unbreakable = min(
        skill.unbreakable_coins if active_unbreakable is None else active_unbreakable,
        remaining_coins,
    )
    unbreakable = [index < active_unbreakable for index in range(remaining_coins)]
    effective_heads = sum(faces[paralysis_used:])
    power = skill.base_power + modifiers.base_power
    effective_coin_power = skill.coin_power + (modifiers.coin_power if skill.coin_power > 0 else 0)
    power += effective_coin_power * effective_heads
    return Roll(power, faces, disabled, unbreakable), modifiers.paralysis - paralysis_used


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
    left_unbreakable = left.unbreakable_coins
    right_unbreakable = right.unbreakable_coins
    left_broken_unbreakable = right_broken_unbreakable = 0
    left_modifiers = left_modifiers or Modifiers()
    right_modifiers = right_modifiers or Modifiers()
    level_difference = left_modifiers.level - right_modifiers.level
    left_level_bonus = max(0, level_difference // 3)
    right_level_bonus = max(0, (-level_difference) // 3)
    rounds: list[ClashRound] = []

    for number in range(1, max_rounds + 1):
        left_roll, left_modifiers.paralysis = roll_skill(left, left_sp, left_coins, rng, left_modifiers, left_unbreakable)
        right_roll, right_modifiers.paralysis = roll_skill(right, right_sp, right_coins, rng, right_modifiers, right_unbreakable)
        left_roll.power += left_level_bonus + left_modifiers.clash_power
        right_roll.power += right_level_bonus + right_modifiers.clash_power
        if left_roll.power > right_roll.power:
            right_coins -= 1
            right_unbreakable_broken = right_unbreakable > 0
            if right_unbreakable_broken:
                right_unbreakable -= 1
                right_broken_unbreakable += 1
            result = "left"
        elif right_roll.power > left_roll.power:
            left_coins -= 1
            left_unbreakable_broken = left_unbreakable > 0
            if left_unbreakable_broken:
                left_unbreakable -= 1
                left_broken_unbreakable += 1
            result = "right"
        else:
            left_unbreakable_broken = right_unbreakable_broken = False
            result = "tie"
        if result == "left":
            left_unbreakable_broken = False
        elif result == "right":
            right_unbreakable_broken = False
        rounds.append(ClashRound(
            number, left_roll, right_roll, result,
            left_unbreakable_broken, right_unbreakable_broken,
        ))

        if left_coins == 0:
            return ClashResult("right", left_coins, right_coins, rounds, left_modifiers.paralysis, right_modifiers.paralysis, left_broken_unbreakable, right_broken_unbreakable)
        if right_coins == 0:
            return ClashResult("left", left_coins, right_coins, rounds, left_modifiers.paralysis, right_modifiers.paralysis, left_broken_unbreakable, right_broken_unbreakable)

    raise RuntimeError("Clash excedeu o limite de rodadas; tente novamente.")


def resolve_attack(
    skill: Skill, sp: int, remaining_coins: int, *, rng: random.Random | None = None,
    modifiers: Modifiers | None = None, faces: list[bool] | None = None,
    active_unbreakable: int | None = None,
) -> list[AttackHit]:
    """No ataque, cada moeda é jogada em sequência e Heads acumulam Coin Power."""
    rng = rng or random.Random()
    modifiers = modifiers or Modifiers()
    power = skill.base_power + modifiers.base_power
    effective_coin_power = skill.coin_power + (modifiers.coin_power if skill.coin_power > 0 else 0)
    paralysis = modifiers.paralysis
    active_unbreakable = min(
        skill.unbreakable_coins if active_unbreakable is None else active_unbreakable,
        remaining_coins,
    )
    hits: list[AttackHit] = []
    for coin in range(1, remaining_coins + 1):
        face = faces[coin - 1] if faces is not None else rng.random() < heads_chance(sp)
        coin_enabled = paralysis <= 0
        paralysis = max(0, paralysis - 1)
        if face and coin_enabled:
            power += effective_coin_power
        hits.append(AttackHit(coin, face, power, not coin_enabled, False, coin <= active_unbreakable))
    return hits


def resolve_damage(
    skill: Skill, sp: int, remaining_coins: int, offense_level: int,
    defense_level: int, *, rng: random.Random | None = None,
    modifiers: Modifiers | None = None, faces: list[bool] | None = None,
    broken_unbreakable: int = 0,
) -> DamageResult:
    """Acumula Coin Power sobre a Base e aplica a diferença de níveis ao final."""
    hits = resolve_attack(
        skill, sp, remaining_coins, rng=rng, modifiers=modifiers, faces=faces,
        active_unbreakable=max(0, skill.unbreakable_coins - broken_unbreakable),
    )
    for index in range(broken_unbreakable):
        hits.append(AttackHit(remaining_coins + index + 1, False, 1, False, True))
    # Cada moeda modifica o poder anterior; os valores intermediários não são
    # somados como golpes separados. O dano da skill é o último poder alcançado.
    regular_power = next((hit.power for hit in reversed(hits) if not hit.unbreakable), 0)
    subtotal = regular_power + broken_unbreakable
    level_modifier = int((offense_level - defense_level) / 3)
    return DamageResult(
        hits, subtotal, level_modifier, max(0, subtotal + level_modifier),
        offense_level, defense_level,
    )
