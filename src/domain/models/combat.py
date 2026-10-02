"""Entidades e tipos de valor do domínio de combate."""

from __future__ import annotations

from dataclasses import dataclass, field


MIN_SP = -45
MAX_SP = 45

EFFECT_TRIGGERS = {
    "on_use", "on_hit", "heads_hit", "clash_win", "clash_lose",
    "before_attack", "after_attack", "on_kill", "on_crit", "on_evade",
    # Os 4 de sessão dos E.G.O Gifts (§5.2 do desenho): `[Início do Encontro]`,
    # `[Início de Combate]`, `[Início da Rodada]` e `[Fim da Rodada]`. O prefixo
    # `session_` existe para não confundir com o `on_round_start` que o Clash já
    # dispara (que é outra coisa, e continua à parte).
    "session_encounter_start", "session_combat_start",
    "session_round_start", "session_round_end",
}
EFFECT_TYPES = {
    "paralysis", "sp", "base_power", "coin_power", "clash_power", "offense_level", "defense_level",
    "burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge", "haste", "special_condition",
    "tremor_burst",
    "final_power",
    "damage_percent",
    "make_unbreakable",
    "consume_special_condition",
    # The Family's Resentment: "curam 30% do **dano** como dano causado". Não é
    # cura de status — o bot **publica** a linha (HP é modo manual, §8) e o
    # autor aplica. `value` é a porcentagem, `condition_max_stacks` o teto.
    "heal_from_damage",
    # O mesmo para o Bloodfeast: a Rosemary consumia a Falsa Fome pelas skills,
    # e o E.G.O Gift precisa enxergar o MESMO recurso. Como a Falsa Fome é um
    # Unique Bloodfeast (decisão do autor), as skills dela passaram a speak
    # `bloodfeast` direto e o `special_condition` ficou só para Trashholder.
    "consume_bloodfeast",
    "self_bleed",
    "consume_devotion_repressed",
    "reuse_coin",
    # Recurso do E.G.O Gift 1.5 (Imperfect Eye) — stack 1–5 no **usuário**.
    "glimpse_of_precognition",
    # Amplitude Conversion → Tremor - Scorch: converte o Tremor do alvo sem
    # mudar Potência/Count (o alvo precisa já ter Tremor ativo).
    "amplitude_conversion_scorch",
    # Recursos dos E.G.O Gifts (§7.4): entram aqui para serem **geráveis** por
    # cláusula de gift/skill — o ramo de status em `apply_skill_trigger` só
    # liga para o que está neste conjunto.
    "bloodfeast", "unique_bloodfeast", "unique_bleed",
}
SKILL_TYPES = {
    "attack", "guard", "counter", "evade", "clashable_guard",
    "clashable_counter", "assist_defense",
}
# "Para quem" a cláusula vale (bloco 4 do desenho dos E.G.O Gifts).
# - `auto` decide pelo sinal (negativo vai no alvo, positivo no usuário);
# - `user`/`target`, o de sempre;
# - `all_allies` = **todos** os do encontro, **inclusive quem usa** (o Limbus
#   escreve "aliados" com visão de time, e o time inclui quem está jogando);
# - `faction` = só os do encontro que declaram a keyword `active_tag` do gift.
EFFECT_OWNERS = {
    "auto", "target", "user", "all_allies", "faction",
}
MULTI_OWNER_EFFECTS = {"all_allies", "faction"}


def clamp_sp(value: int) -> int:
    return max(MIN_SP, min(MAX_SP, value))


def heads_chance(sp: int) -> float:
    """Converte sanidade em chance de Heads entre 5% e 95%."""
    return (50 + clamp_sp(sp)) / 100


@dataclass(frozen=True)
class SkillEffect:
    trigger: str
    effect_type: str
    value: float
    coin: int | None = None
    count: int | None = None
    charge_cost: int = 0
    condition_status: str | None = None
    condition_min: int = 0
    condition_owner: str = "target"
    condition_value: str = "potency"
    condition_per: int = 0
    condition_max_stacks: int = 0
    consume_condition: bool = False
    effect_owner: str = "auto"
    condition_operator: str = "at_least"
    # Limite "N vezes por rodada" (ex.: [Ao Critar] do Imperfect Eye = 2x).
    # 0 = sem limite. O contador zera quando a rodada termina.
    max_per_round: int = 0
    # "[Primeira Rodada]" / "na rodada N". None = qualquer rodada.
    # Só faz sentido nos gatilhos `session_*`; ver o filtro em `triggered_effects`
    # — clause com `condition_turn` e sem turno conhecido NÃO dispara (falha
    # fechada), para nunca valer "em toda rodada" por acidente.
    condition_turn: int | None = None
    # Etapa 5 — "Quanto dura" (bloco 5) e "Limite" (bloco 6) dos prints.
    # `duration_turns` = a cláusula NÃO aplica na hora: fica pendente e é
    # aplicada em cada início de rodada por N rodadas (*"por 2 Rodadas"*,
    # *"na próxima rodada"*).
    duration_turns: int = 0
    # `max_activations` + `activation_window` = "1x por rodada", "1x por
    # personagem por rodada". 0/None = sem limite.
    max_activations: int | None = None
    activation_window: str = "combat"      # combat | round

    def __post_init__(self) -> None:
        if self.trigger not in EFFECT_TRIGGERS:
            raise ValueError("Gatilho de efeito inválido.")
        if self.effect_type not in EFFECT_TYPES:
            raise ValueError("Tipo de efeito inválido.")
        if self.coin is not None and self.coin < 1:
            raise ValueError("A moeda do efeito deve começar em 1.")
        if self.effect_type in {
            "burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge", "haste",
            "special_condition", "devotion_repressed", "bloodfiend", "bloodbag", "self_bleed",
            "glimpse_of_precognition",
            # Os 3 recursos da Etapa 2. **Precavam** estar aqui: sem esta lista,
            # `count` num `bloodfeast` levantava ValueError e o
            # `_effects_from_row` descartava a cláusula em silêncio — o gift
            # ficava gravado no banco e nunca fazia nada.
            "bloodfeast", "unique_bloodfeast", "unique_bleed",
        }:
            if self.value < 0 or not float(self.value).is_integer() or self.count is None or self.count < 0:
                raise ValueError("Status exige Potência e Quantidade não negativas.")
        elif self.effect_type == "consume_special_condition":
            if self.value < 0 or not float(self.value).is_integer():
                raise ValueError("O consumo máximo da Condição Especial deve ser inteiro e não negativo.")
        elif self.count is not None:
            raise ValueError("Quantidade só pode ser usada em status principais.")
        scalar_conditions = {"sp", "base_power", "coin_power", "clash_power", "offense_level", "defense_level"}
        if min(self.charge_cost, self.condition_per, self.condition_max_stacks) < 0:
            raise ValueError("Custos e escalas da condição não podem ser negativos.")
        if self.condition_min < 0 and self.condition_status not in scalar_conditions:
            raise ValueError("Somente SP e modificadores temporários aceitam referência negativa.")
        if self.condition_status is not None and self.condition_status not in {
            "burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge", "haste", "special_condition",
            "special_condition_consumed", "bloodfeast", "bloodfeast_consumed",
            # A soma do Bloodfeast consumido **do time inteiro** — o
            # "(Compartilhado)" da print do The Family's Resentment. Sem isso,
            # dois aliados consumindo 30 cada dariam 30 quando a regra e 50.
            "shared_bloodfeast_consumed",
            # Não é um status da ficha: é uma pergunta sobre o **resultado** da
            # skill ("ela inflictiu Bleed?"). O bot responde comparando o Bleed
            # do alvo antes e depois da resolução — vale para qualquer skill,
            # inclusive as que aplicam por moeda.
            "inflicted_bleed",
            "bloodfiend_or_bloodbag", "paralysis", "sp",
            "base_power", "coin_power", "clash_power", "offense_level", "defense_level",
            "glimpse_of_precognition",
        }:
            raise ValueError("Status circunstancial inválido.")
        if self.condition_owner not in {"target", "user"}:
            raise ValueError("Dono da condição deve ser usuário ou alvo.")
        if self.effect_owner not in EFFECT_OWNERS:
            raise ValueError("O efeito deve ser aplicado no alvo ou no usuário.")
        if self.condition_operator not in {"has", "at_least", "at_most", "exactly"}:
            raise ValueError("Comparação da condição inválida.")
        if self.effect_type == "reuse_coin" and not 1 <= int(self.value) <= 5:
            raise ValueError("Reutilizar moeda exige um limite entre 1 e 5.")
        if self.condition_value not in {"potency", "count"}:
            raise ValueError("A condição deve consultar Potência ou Quantidade.")
        if self.consume_condition and self.condition_status in {"special_condition_consumed", "bloodfeast_consumed"}:
            raise ValueError("O histórico do Encounter pode ser consultado, mas não consumido.")

    def condition_multiplier(self, current_value: int) -> int:
        """Quantidade de vezes que o bônus escala pelo valor do status."""
        scalar = self.condition_status in {"sp", "base_power", "coin_power", "clash_power", "offense_level", "defense_level"}
        matches = {
            "has": current_value != 0 if scalar else current_value > 0,
            "at_least": current_value >= self.condition_min,
            "at_most": current_value <= self.condition_min if scalar else 0 < current_value <= self.condition_min,
            "exactly": current_value == self.condition_min,
        }[self.condition_operator]
        if not matches:
            return 0
        if self.condition_per <= 0:
            return 1
        # O primeiro bônus nasce no valor de referência; "a cada" controla
        # somente os bônus adicionais. Ex.: mínimo 1, a cada 6 => 1–6 = ×1,
        # 7–12 = ×2.
        first_threshold = self.condition_min if self.condition_min > 0 else self.condition_per
        if current_value < first_threshold:
            return 0
        multiplier = 1 + (current_value - first_threshold) // self.condition_per
        if self.condition_max_stacks > 0:
            multiplier = min(multiplier, self.condition_max_stacks)
        return multiplier


def parse_skill_effects(raw: str) -> tuple[SkillEffect, ...]:
    """Lê ``gatilho:efeito:valor[:moeda]`` por linha ou separado por ponto e vírgula."""
    effects = []
    for entry in raw.replace(";", "\n").splitlines():
        entry = entry.strip()
        if not entry:
            continue
        parts = [part.strip().lower() for part in entry.split(":")]
        if len(parts) not in {3, 4}:
            raise ValueError("Use gatilho:efeito:valor[:moeda].")
        value_parts = parts[2].split(",", 1)
        value = float(value_parts[0].replace(",", "."))
        count = int(value_parts[1]) if len(value_parts) == 2 else None
        coin = int(parts[3]) if len(parts) == 4 and parts[3] else None
        effects.append(SkillEffect(parts[0], parts[1], value, coin, count))
    return tuple(effects)


def format_skill_effects(effects: tuple[SkillEffect, ...]) -> str:
    return "\n".join(
        f"{effect.trigger}:{effect.effect_type}:{effect.value:g}"
        + (f",{effect.count}" if effect.count is not None else "")
        + (f":{effect.coin}" if effect.coin is not None else "")
        for effect in effects
    )


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
    coin_layout: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A skill precisa de um nome.")
        if not 1 <= self.coins <= 10:
            raise ValueError("A quantidade de moedas deve ficar entre 1 e 10.")
        if not 0 <= self.unbreakable_coins <= self.coins:
            raise ValueError("Moedas inquebráveis devem ficar entre 0 e o total de moedas.")
        layout = self.coin_layout or (
            ("normal",) * (self.coins - self.unbreakable_coins)
            + ("unbreakable",) * self.unbreakable_coins
        )
        if len(layout) != self.coins or any(kind not in {"normal", "unbreakable"} for kind in layout):
            raise ValueError("A configuração individual das moedas é inválida.")
        object.__setattr__(self, "coin_layout", tuple(layout))
        object.__setattr__(self, "unbreakable_coins", layout.count("unbreakable"))
        if any(effect.coin is not None and effect.coin > self.coins for effect in self.effects):
            raise ValueError("Um efeito aponta para uma moeda inexistente.")
        if len(self.effects) > 20:
            raise ValueError("Uma skill pode ter no máximo 20 efeitos.")
        if self.skill_type not in SKILL_TYPES:
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

    def coin_is_unbreakable(self, position: int) -> bool:
        """Consulta uma posição de moeda iniciada em 1."""
        return 1 <= position <= self.coins and self.coin_layout[position - 1] == "unbreakable"

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
    damage_before_percent: int = 0
    damage_percent: float = 0
    percent_modifier: int = 0
    coin_damage_percent: list[tuple[int, float]] = field(default_factory=list)
    coin_percent_modifier: int = 0
    critical_hits: list[int] = field(default_factory=list)


@dataclass
class DefenseResult:
    kind: str
    success: bool | None
    attack_rolls: list[Roll]
    defense_rolls: list[Roll]
    summary: str
    counter_roll: Roll | None = None


def triggered_effects(
    effects, trigger: str, *, remaining_coins: int | None = None,
    hits: list[AttackHit] | None = None, turn: int | None = None,
) -> tuple[SkillEffect, ...]:
    """Seleciona efeitos cujo gatilho e condição de moeda foram satisfeitos.

    Ganho genérico: opera sobre **qualquer** sequência de ``SkillEffect`` —
    é o que permite a mesma regra valer tanto para as cláusulas de uma skill
    quanto para as cláusulas de um E.G.O Gift, sem motor novo.

    ``turn`` é o número da rodada, para o ``condition_turn`` dos prints
    (*"[Primeira Rodada]"*). Cláusula com ``condition_turn`` e sem turno
    conhecido **não dispara**: falha fechada, para um gift não virar "vale em
    toda rodada" só porque o chamador esqueceu de informar o turno.
    """
    selected = []
    for effect in effects:
        if effect.trigger != trigger:
            continue
        if effect.condition_turn is not None and effect.condition_turn != turn:
            continue
        if effect.coin is None:
            if trigger == "on_hit":
                selected.extend(effect for _ in (hits or []))
            elif trigger == "heads_hit":
                selected.extend(effect for hit in (hits or []) if hit.face and not hit.paralyzed)
            elif trigger == "on_crit" and hits:
                selected.append(effect)
            else:
                selected.append(effect)
            continue
        if trigger in {"on_hit", "heads_hit", "on_crit"}:
            matching = next((hit for hit in (hits or []) if hit.coin == effect.coin), None)
            if matching is None:
                continue
            if trigger == "heads_hit" and (not matching.face or matching.paralyzed):
                continue
            selected.append(effect)
        elif remaining_coins is None or effect.coin <= remaining_coins:
            selected.append(effect)
    return tuple(selected)


def triggered_skill_effects(
    skill: Skill, trigger: str, *, remaining_coins: int | None = None,
    hits: list[AttackHit] | None = None, turn: int | None = None,
) -> tuple[SkillEffect, ...]:
    """Seleciona efeitos da skill cujo gatilho e condição de moeda foram satisfeitos."""
    return triggered_effects(
        skill.effects, trigger, remaining_coins=remaining_coins, hits=hits, turn=turn,
    )
