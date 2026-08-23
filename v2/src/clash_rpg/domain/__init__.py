"""API pública do domínio da V2."""

from .clash import ClashResult, ClashRound, resolve_clash
from .models import CoinKind, CoinSpec, Combatant, Modifiers, Skill

__all__ = [
    "ClashResult",
    "ClashRound",
    "CoinKind",
    "CoinSpec",
    "Combatant",
    "Modifiers",
    "Skill",
    "resolve_clash",
]

