"""Regras puras dos principais status de combate."""

from __future__ import annotations

from dataclasses import dataclass

STATUS_TYPES = {
    "burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge", "haste",
    "special_condition", "devotion_repressed", "bloodfiend", "bloodbag",
    # Recurso temporário do E.G.O Gift 1.5 (Imperfect Eye). Fica fora do
    # conjunto de ``on_round_end`` de propósito: ele **não** decai sozinho —
    # só zera quando a regra própria expira (chegou a 5 → troca de rodada).
    "glimpse_of_precognition",
    # Variantes únicas (§7.4 do desenho): são **dois status, não uma família
    # com regra** — é assim que os prints já os listam separados. Hoje são
    # recurso puro: `on_round_end` não os conhece, então não decaem sozinhos.
    # Se um gift exigir decaimento, é adicionar a regra deles à mão ali.
    "bloodfeast", "unique_bloodfeast", "unique_bleed",
}

# Amplitude Conversion (Limbus): o Tremor convertido continua sendo a MESMA
# pilha de Potência/Count — só o tipo muda. Por isso a variante mora num campo
# do próprio ``tremor`` e não num status separado.
TREMOR_TYPES = {"normal", "scorch"}
TREMOR_TYPE_LABELS = {"normal": "Tremor", "scorch": "Tremor - Scorch"}


@dataclass(frozen=True)
class CombatStatus:
    status_type: str
    potency: int = 0
    count: int = 0
    tremor_type: str = "normal"

    def __post_init__(self) -> None:
        if self.status_type not in STATUS_TYPES:
            raise ValueError("Status inválido.")
        if self.potency < 0 or self.count < 0:
            raise ValueError("Potência e Quantidade não podem ser negativas.")
        if self.tremor_type not in TREMOR_TYPES:
            raise ValueError("Tipo de Tremor inválido.")
        if self.tremor_type != "normal" and self.status_type != "tremor":
            raise ValueError("Só o Tremor aceita Amplitude Conversion.")
        if self.status_type == "charge" and self.count > 20:
            object.__setattr__(self, "count", 20)
        # Glimpse of Precognition (E.G.O Gift 1.5): o stack é o próprio valor e
        # o teto é 5. Sem teto, o escalamento Tremor/Burn cresceria sem limite.
        if self.status_type == "glimpse_of_precognition":
            object.__setattr__(self, "count", min(self.count, 5))
            object.__setattr__(self, "potency", min(self.potency, 5))


@dataclass(frozen=True)
class StatusEvent:
    status_type: str
    damage: int = 0
    sanity_loss: int = 0
    stagger_threshold: int = 0
    potency_after: int = 0
    count_after: int = 0
    note: str = ""
    # Rótulo de exibição quando a variante do Tremor difere do normal.
    label: str = ""


def on_damage_taken(status: CombatStatus, *, sanity: int | None = None) -> StatusEvent | None:
    """O que o status faz quando o alvo sofre dano.

    ``sanity`` é a Sanidade atual do alvo. ``None`` significa que a unidade
    **não usa Sanidade** (inimigo com sanidade inativa). Aí não existe SP para
    consumir, então o Sinking vira dano direto. Antes disso o SP era reduzido de
    qualquer jeito e nada acontecia (P5).
    """
    if status.count <= 0:
        return None
    remaining = status.count - 1
    if status.status_type == "rupture":
        return StatusEvent("rupture", damage=status.potency, potency_after=status.potency, count_after=remaining)
    if status.status_type == "sinking":
        if sanity is None:
            return StatusEvent("sinking", damage=status.potency, potency_after=status.potency,
                               count_after=remaining, note="Unidade sem Sanidade; Sinking convertido em dano.")
        if sanity <= -45:
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
    if status.status_type in {"tremor", "sinking", "poise", "charge", "haste"}:
        potency_after = status.potency
        if status.status_type == "charge" and count_after == 0 and potency_after < 2:
            potency_after = 0
        label = (
            TREMOR_TYPE_LABELS.get(status.tremor_type, "")
            if status.status_type == "tremor" and status.tremor_type != "normal" else ""
        )
        return StatusEvent(status.status_type, potency_after=potency_after, count_after=count_after,
                           note="Quantidade reduzida no final da rodada.", label=label)
    if status.status_type == "glimpse_of_precognition":
        # EGO_GIFTS.md §1.5:70 — "Expira na próxima rodada depois de chegar
        # em 5 Stack". Antes disso ele NÃO decai (senão nunca chegaria a 5).
        if status.count >= 5:
            return StatusEvent(
                "glimpse_of_precognition", potency_after=0, count_after=0,
                note="Glimpse of Precognition expirou (chegou ao teto de 5).",
            )
        return None
    return None


def tremor_burst(status: CombatStatus) -> StatusEvent:
    """Tremor Burst: dano de Stagger = Potência, e **o alvo perde 1 Count**.

    A Potência fica intacta (não se "tira a potência inteira"); o que se gasta
    é o Count. Quando o Count chega a 0, ``set_status`` apaga a linha do status
    — isso é intencional: no E.G.O Gift 1.5 o escalamento mora no Glimpse, não
    no Tremor, então o ``0×0`` depois do burst é o caminho esperado.
    """
    if status.status_type != "tremor":
        raise ValueError("Tremor Burst exige Tremor.")
    return StatusEvent("tremor", stagger_threshold=status.potency,
                       potency_after=status.potency,
                       count_after=max(0, status.count - 1),
                       note="Tremor Burst: alvo perdeu 1 Tremor Count.")


def convert_tremor(status: CombatStatus, target: str) -> CombatStatus:
    """Amplitude Conversion: troca só o tipo de Tremor.

    Potência e Count **não mudam** na conversão — é a mesma pilha com outro
    efeito ativo, como no Limbus.
    """
    if status.status_type != "tremor":
        raise ValueError("Amplitude Conversion exige Tremor.")
    if target not in TREMOR_TYPES:
        raise ValueError("Tipo de Tremor inválido.")
    return CombatStatus("tremor", status.potency, status.count, target)


def tremor_scorch_burst(tremor: CombatStatus, burn: CombatStatus | None) -> StatusEvent:
    """Tremor - Scorch no Burst: dano = (Tremor + Burn) ÷ 2 e −1 Burn Count.

    Sem Sin Affinity no bot, o "dano de Wrath" é dano normal. O Burn só entra
    na conta (e só perde Count) quando está ativo no alvo; sem Burn o dano é a
    metade arredondada para baixo da Potência de Tremor.
    """
    if tremor.status_type != "tremor" or tremor.tremor_type != "scorch":
        raise ValueError("O dano de Scorch exige Tremor - Scorch.")
    burn_active = burn is not None and burn.count > 0
    burn_potency = burn.potency if burn_active else 0
    return StatusEvent(
        "burn",
        damage=(tremor.potency + burn_potency) // 2,
        count_after=max(0, burn.count - 1) if burn_active else 0,
        note="Tremor - Scorch: dano = (Tremor + Burn) ÷ 2; alvo perdeu 1 Burn Count."
        if burn_active else
        "Tremor - Scorch: dano = Tremor ÷ 2 (alvo sem Burn).",
    )


def poise_values(status: CombatStatus) -> tuple[int, float]:
    if status.status_type != "poise":
        raise ValueError("O cálculo exige Poise.")
    return status.potency * 2, status.potency / 10
