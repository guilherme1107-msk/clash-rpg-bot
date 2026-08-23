"""Coordenação das fases de batalha do protótipo, sem dependência do Discord."""

from __future__ import annotations

from typing import Protocol, Any


class BattleStore(Protocol):
    def get_battle(self, guild_id: int, channel_id: int) -> Any: ...
    def list_battle_participants(self, guild_id: int, channel_id: int) -> list[Any]: ...
    def list_field_actions(self, guild_id: int, channel_id: int, status: str | None = None) -> list[Any]: ...
    def set_battle_phase(self, guild_id: int, channel_id: int, phase: str) -> Any: ...
    def reset_battle_readiness(self, guild_id: int, channel_id: int) -> None: ...
    def set_battle_participant_status(self, guild_id: int, channel_id: int, user_id: int, status: str) -> None: ...
    def next_battle_turn(self, guild_id: int, channel_id: int) -> Any: ...


def advance_when_all_ready(
    store: BattleStore, guild_id: int, channel_id: int,
) -> tuple[str | None, str]:
    """Avança uma fase somente quando todos os participantes confirmaram."""
    battle = store.get_battle(guild_id, channel_id)
    participants = store.list_battle_participants(guild_id, channel_id)
    if battle is None or not participants or not all(bool(row["ready"]) for row in participants):
        return None, ""

    phase = battle["phase"]
    if phase == "preparation":
        if not store.list_field_actions(guild_id, channel_id):
            return None, "Todos estão prontos; aguardando o mestre colocar ao menos uma ação no campo."
        store.set_battle_phase(guild_id, channel_id, "declaration")
        store.reset_battle_readiness(guild_id, channel_id)
        for participant in participants:
            store.set_battle_participant_status(guild_id, channel_id, participant["user_id"], "waiting")
        return "declaration", "Todos estão prontos. A fase de **Declaração** começou."

    if phase == "declaration":
        if store.list_field_actions(guild_id, channel_id, "claimed"):
            return None, "Todos confirmaram, mas ainda existe um Clash em andamento."
        store.set_battle_phase(guild_id, channel_id, "resolution")
        store.reset_battle_readiness(guild_id, channel_id)
        return "resolution", "Declarações encerradas. A fase de **Resolução** começou."

    if phase in {"resolution", "complete"}:
        next_battle = store.next_battle_turn(guild_id, channel_id)
        return "preparation", f"Turno **{next_battle['turn']}** iniciado automaticamente."

    return None, ""

