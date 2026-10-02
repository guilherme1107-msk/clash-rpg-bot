"""Núcleo Geral v1: versões e eventos para todas as escritas importantes.

O módulo não conhece Discord ou React. Quem recebe uma ação usa este gateway
na mesma transação que altera o estado. Assim o banco guarda tanto o resultado
confirmado quanto o evento que Activity, bot e Sentinela podem consultar.
"""
from __future__ import annotations

import json
import uuid
from typing import Any


def review_encounter_command(command: str, *, enemy_id: int, skill_name: str,
                             target_user_id: int, variant: str = "unopposed") -> dict[str, Any]:
    """Revisão mínima, compartilhada, para comandos ofensivos do Encounter.

    A Activity continua identificando o usuário e consultando o Encounter; este
    núcleo valida o formato e devolve a ordem normalizada antes que qualquer
    ação seja registrada ou enviada ao motor de combate.
    """
    if command not in {"encounter.hostile_action_queued", "encounter.enemy_free_queued"}:
        raise ValueError("Comando de Encounter não reconhecido pelo Núcleo Geral.")
    if enemy_id <= 0 or target_user_id <= 0 or not skill_name.strip():
        raise ValueError("O Núcleo Geral recusou a ação: hostil, Skill e alvo são obrigatórios.")
    if variant not in {"unopposed", "follow_up"}:
        raise ValueError("O Núcleo Geral recusou a variação do ataque.")
    return {
        "command": command, "enemy_id": enemy_id, "skill_name": skill_name.strip(),
        "target_user_id": target_user_id, "variant": variant, "approved": True,
    }


def commit_sqlite_event(connection, *, guild_id: int, command: str, source: str,
                        entity_kind: str, entity_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
    identity = str(entity_id)
    row = connection.execute(
        "SELECT version FROM core_entity_versions WHERE guild_id=? AND entity_kind=? AND entity_id=?",
        (guild_id, entity_kind, identity),
    ).fetchone()
    version = int(row["version"] if row else 0) + 1
    connection.execute(
        """INSERT INTO core_entity_versions(guild_id,entity_kind,entity_id,version,updated_at)
           VALUES(?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(guild_id,entity_kind,entity_id) DO UPDATE SET version=excluded.version,updated_at=CURRENT_TIMESTAMP""",
        (guild_id, entity_kind, identity, version),
    )
    trace_id = uuid.uuid4().hex[:16].upper()
    connection.execute(
        """INSERT INTO core_events(trace_id,guild_id,command,source,entity_kind,entity_id,version,payload_json)
           VALUES(?,?,?,?,?,?,?,?)""",
        (trace_id, guild_id, command, source, entity_kind, identity, version, json.dumps(payload, ensure_ascii=False)),
    )
    return {"trace_id": trace_id, "version": version}


def commit_database_event(database, **kwargs) -> dict[str, Any]:
    """Versão para os núcleos que já trabalham através de Database."""
    return commit_sqlite_event(database.connection, **kwargs)
