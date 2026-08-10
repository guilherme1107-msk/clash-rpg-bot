"""Persistência SQLite do bot."""

from __future__ import annotations

import json
import sqlite3
import threading

from clash_engine import Skill, SkillEffect, clamp_sp


def _effects_json(skill: Skill) -> str:
    return json.dumps([
        {"trigger": effect.trigger, "effect_type": effect.effect_type, "value": effect.value, "coin": effect.coin}
        for effect in skill.effects
    ], ensure_ascii=False)


def _effects_from_row(row) -> tuple[SkillEffect, ...]:
    raw = row["effects_json"] if "effects_json" in row.keys() else "[]"
    try:
        return tuple(SkillEffect(**item) for item in json.loads(raw or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()


class Database:
    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.Lock()

    def setup(self) -> None:
        with self.lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    sp INTEGER NOT NULL DEFAULT 0 CHECK(sp BETWEEN -45 AND 45),
                    offense_level INTEGER NOT NULL DEFAULT 0,
                    defense_level INTEGER NOT NULL DEFAULT 0,
                    paralysis INTEGER NOT NULL DEFAULT 0,
                    base_power_mod INTEGER NOT NULL DEFAULT 0,
                    coin_power_mod INTEGER NOT NULL DEFAULT 0,
                    clash_power_mod INTEGER NOT NULL DEFAULT 0,
                    offense_level_mod INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    base_power INTEGER NOT NULL,
                    coin_power INTEGER NOT NULL,
                    coins INTEGER NOT NULL CHECK(coins BETWEEN 1 AND 10),
                    unbreakable_coins INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    effects_json TEXT NOT NULL DEFAULT '[]',
                    level_type TEXT NOT NULL DEFAULT 'offense',
                    UNIQUE (guild_id, owner_id, name)
                );
                CREATE TABLE IF NOT EXISTS enemies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    sp INTEGER NOT NULL DEFAULT 0 CHECK(sp BETWEEN -45 AND 45),
                    offense_level INTEGER NOT NULL DEFAULT 0,
                    defense_level INTEGER NOT NULL DEFAULT 0,
                    uses_sanity INTEGER NOT NULL DEFAULT 1,
                    paralysis INTEGER NOT NULL DEFAULT 0,
                    base_power_mod INTEGER NOT NULL DEFAULT 0,
                    coin_power_mod INTEGER NOT NULL DEFAULT 0,
                    clash_power_mod INTEGER NOT NULL DEFAULT 0,
                    offense_level_mod INTEGER NOT NULL DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    UNIQUE (guild_id, name)
                );
                CREATE TABLE IF NOT EXISTS enemy_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enemy_id INTEGER NOT NULL REFERENCES enemies(id) ON DELETE CASCADE,
                    name TEXT NOT NULL COLLATE NOCASE,
                    base_power INTEGER NOT NULL,
                    coin_power INTEGER NOT NULL,
                    coins INTEGER NOT NULL CHECK(coins BETWEEN 1 AND 10),
                    unbreakable_coins INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    effects_json TEXT NOT NULL DEFAULT '[]',
                    skill_type TEXT NOT NULL DEFAULT 'attack',
                    UNIQUE (enemy_id, name)
                );
                CREATE TABLE IF NOT EXISTS battle_sessions (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    turn INTEGER NOT NULL DEFAULT 1,
                    created_by INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    panel_message_id INTEGER,
                    phase TEXT NOT NULL DEFAULT 'preparation',
                    PRIMARY KEY (guild_id, channel_id)
                );
                CREATE TABLE IF NOT EXISTS battle_field_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    enemy_name TEXT NOT NULL,
                    enemy_skill TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    claimed_by INTEGER,
                    player_skill TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id, channel_id)
                        REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS battle_participants (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    character_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'waiting',
                    ready INTEGER NOT NULL DEFAULT 0,
                    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id, user_id),
                    FOREIGN KEY (guild_id, channel_id)
                        REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                """
            )
            # Migração de bancos criados pela primeira versão.
            character_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(characters)")}
            for name, definition in {
                "offense_level": "INTEGER NOT NULL DEFAULT 0",
                "defense_level": "INTEGER NOT NULL DEFAULT 0",
                "paralysis": "INTEGER NOT NULL DEFAULT 0",
                "base_power_mod": "INTEGER NOT NULL DEFAULT 0",
                "coin_power_mod": "INTEGER NOT NULL DEFAULT 0",
                "clash_power_mod": "INTEGER NOT NULL DEFAULT 0",
                "offense_level_mod": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in character_columns:
                    self.connection.execute(f"ALTER TABLE characters ADD COLUMN {name} {definition}")
            skill_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(skills)")}
            if "level_type" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN level_type TEXT NOT NULL DEFAULT 'offense'")
            if "unbreakable_coins" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN unbreakable_coins INTEGER NOT NULL DEFAULT 0")
            if "effects_json" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN effects_json TEXT NOT NULL DEFAULT '[]'")
            enemy_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(enemies)")}
            if "uses_sanity" not in enemy_columns:
                self.connection.execute("ALTER TABLE enemies ADD COLUMN uses_sanity INTEGER NOT NULL DEFAULT 1")
            if "defense_level" not in enemy_columns:
                self.connection.execute("ALTER TABLE enemies ADD COLUMN defense_level INTEGER NOT NULL DEFAULT 0")
            for name in ("paralysis", "base_power_mod", "coin_power_mod", "clash_power_mod", "offense_level_mod"):
                if name not in enemy_columns:
                    self.connection.execute(f"ALTER TABLE enemies ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            enemy_skill_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(enemy_skills)")}
            if "skill_type" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN skill_type TEXT NOT NULL DEFAULT 'attack'")
            if "unbreakable_coins" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN unbreakable_coins INTEGER NOT NULL DEFAULT 0")
            if "effects_json" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN effects_json TEXT NOT NULL DEFAULT '[]'")
            battle_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(battle_sessions)")}
            if "phase" not in battle_columns:
                self.connection.execute(
                    "ALTER TABLE battle_sessions ADD COLUMN phase TEXT NOT NULL DEFAULT 'preparation'"
                )
            participant_columns = {
                r[1] for r in self.connection.execute("PRAGMA table_info(battle_participants)")
            }
            if "ready" not in participant_columns:
                self.connection.execute(
                    "ALTER TABLE battle_participants ADD COLUMN ready INTEGER NOT NULL DEFAULT 0"
                )
            battle_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(battle_sessions)")}
            if "panel_message_id" not in battle_columns:
                self.connection.execute("ALTER TABLE battle_sessions ADD COLUMN panel_message_id INTEGER")

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def create_character(self, guild_id: int, user_id: int, name: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO characters(guild_id,user_id,name,sp) VALUES(?,?,?,0)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET name=excluded.name""",
                (guild_id, user_id, name),
            )

    def get_character(self, guild_id: int, user_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()

    def list_characters(self, guild_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM characters WHERE guild_id=? ORDER BY name", (guild_id,)
            ).fetchall()

    def change_sp(self, guild_id: int, user_id: int, delta: int):
        character = self.get_character(guild_id, user_id)
        if character is None:
            return None
        new_sp = clamp_sp(character["sp"] + delta)
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET sp=? WHERE guild_id=? AND user_id=?",
                (new_sp, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def set_offense_level(self, guild_id: int, user_id: int, offense: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET offense_level=? WHERE guild_id=? AND user_id=?",
                (offense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def set_levels(self, guild_id: int, user_id: int, offense: int, defense: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET offense_level=?, defense_level=? WHERE guild_id=? AND user_id=?",
                (offense, defense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def add_effects(self, guild_id: int, user_id: int, paralysis: int, base: int, coin: int, clash: int = 0, offense: int = 0):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?,
                   clash_power_mod=clash_power_mod+?, offense_level_mod=offense_level_mod+?
                   WHERE guild_id=? AND user_id=?""",
                (paralysis, base, coin, clash, offense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def consume_clash_effects(self, guild_id: int, user_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=?, base_power_mod=0, coin_power_mod=0,
                   clash_power_mod=0, offense_level_mod=0
                   WHERE guild_id=? AND user_id=?""",
                (remaining_paralysis, guild_id, user_id),
            )

    def save_skill(self, guild_id: int, owner_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO skills(guild_id,owner_id,name,base_power,coin_power,coins,unbreakable_coins,description,level_type,effects_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,owner_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, unbreakable_coins=excluded.unbreakable_coins,
                   description=excluded.description, level_type=excluded.level_type,
                   effects_json=excluded.effects_json""",
                (guild_id, owner_id, skill.name, skill.base_power, skill.coin_power,
                 skill.coins, skill.unbreakable_coins, skill.description, skill.skill_type, _effects_json(skill)),
            )

    def get_skill(self, guild_id: int, owner_id: int, name: str) -> Skill | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? AND name=?",
                (guild_id, owner_id, name),
            ).fetchone()
        return None if row is None else Skill(
            row["name"], row["base_power"], row["coin_power"],
            row["coins"], row["description"],
            {"offense": "attack", "defense": "guard"}.get(row["level_type"], row["level_type"]),
            row["unbreakable_coins"], _effects_from_row(row)
        )

    def list_skills(self, guild_id: int, owner_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
                (guild_id, owner_id),
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], {"offense": "attack", "defense": "guard"}.get(r["level_type"], r["level_type"]), r["unbreakable_coins"], _effects_from_row(r)) for r in rows]

    def delete_skill(self, guild_id: int, owner_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM skills WHERE guild_id=? AND owner_id=? AND name=?",
                (guild_id, owner_id, name),
            )
        return cursor.rowcount > 0

    def save_enemy(self, guild_id: int, created_by: int, name: str, sp: int, offense: int, defense: int, uses_sanity: bool = True):
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO enemies(guild_id,name,sp,offense_level,defense_level,uses_sanity,created_by) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,name) DO UPDATE SET
                   sp=excluded.sp, offense_level=excluded.offense_level,
                   defense_level=excluded.defense_level, uses_sanity=excluded.uses_sanity""",
                (guild_id, name, clamp_sp(sp), offense, defense, int(uses_sanity), created_by),
            )
        return self.get_enemy(guild_id, name)

    def get_enemy(self, guild_id: int, name: str):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE guild_id=? AND name=?", (guild_id, name)
            ).fetchone()

    def list_enemies(self, guild_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE guild_id=? ORDER BY name", (guild_id,)
            ).fetchall()

    def delete_enemy(self, guild_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM enemies WHERE guild_id=? AND name=?", (guild_id, name)
            )
        return cursor.rowcount > 0

    def change_enemy_sp(self, enemy_id: int, delta: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE enemies SET sp=MAX(-45,MIN(45,sp+?)) WHERE id=?", (delta, enemy_id)
            )
            return self.connection.execute("SELECT * FROM enemies WHERE id=?", (enemy_id,)).fetchone()

    def add_enemy_effects(self, enemy_id: int, paralysis: int, base: int, coin: int, clash: int, offense: int):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemies SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?,
                   clash_power_mod=clash_power_mod+?, offense_level_mod=offense_level_mod+?
                   WHERE id=?""",
                (paralysis, base, coin, clash, offense, enemy_id),
            )
            return self.connection.execute("SELECT * FROM enemies WHERE id=?", (enemy_id,)).fetchone()

    def consume_enemy_effects(self, enemy_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemies SET paralysis=?, base_power_mod=0, coin_power_mod=0,
                   clash_power_mod=0, offense_level_mod=0 WHERE id=?""",
                (remaining_paralysis, enemy_id),
            )

    def save_enemy_skill(self, enemy_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO enemy_skills(enemy_id,name,base_power,coin_power,coins,unbreakable_coins,description,skill_type,effects_json)
                   VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(enemy_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, unbreakable_coins=excluded.unbreakable_coins,
                   description=excluded.description, skill_type=excluded.skill_type,
                   effects_json=excluded.effects_json""",
                (enemy_id, skill.name, skill.base_power, skill.coin_power, skill.coins, skill.unbreakable_coins, skill.description, skill.skill_type, _effects_json(skill)),
            )

    def get_enemy_skill(self, enemy_id: int, name: str) -> Skill | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, name)
            ).fetchone()
        return None if row is None else Skill(
            row["name"], row["base_power"], row["coin_power"], row["coins"], row["description"], row["skill_type"], row["unbreakable_coins"], _effects_from_row(row)
        )

    def list_enemy_skills(self, enemy_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM enemy_skills WHERE enemy_id=? ORDER BY name", (enemy_id,)
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], r["skill_type"], r["unbreakable_coins"], _effects_from_row(r)) for r in rows]

    def delete_enemy_skill(self, enemy_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, name)
            )
        return cursor.rowcount > 0

    def start_battle(self, guild_id: int, channel_id: int, name: str, created_by: int):
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM battle_field_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_participants WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                """INSERT INTO battle_sessions(guild_id,channel_id,name,turn,created_by,active,phase)
                   VALUES(?,?,?,1,?,1,'preparation')
                   ON CONFLICT(guild_id,channel_id) DO UPDATE SET
                   name=excluded.name, turn=1, created_by=excluded.created_by,
                   active=1, panel_message_id=NULL, phase='preparation'""",
                (guild_id, channel_id, name, created_by),
            )
        return self.get_battle(guild_id, channel_id)

    def get_battle(self, guild_id: int, channel_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM battle_sessions WHERE guild_id=? AND channel_id=? AND active=1",
                (guild_id, channel_id),
            ).fetchone()

    def set_battle_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_sessions SET panel_message_id=? WHERE guild_id=? AND channel_id=?",
                (message_id, guild_id, channel_id),
            )

    def end_battle(self, guild_id: int, channel_id: int) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE battle_sessions SET active=0 WHERE guild_id=? AND channel_id=? AND active=1",
                (guild_id, channel_id),
            )
        return cursor.rowcount > 0

    def add_field_action(self, guild_id: int, channel_id: int, enemy_name: str, enemy_skill: str):
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """INSERT INTO battle_field_actions(guild_id,channel_id,enemy_name,enemy_skill)
                   VALUES(?,?,?,?)""",
                (guild_id, channel_id, enemy_name, enemy_skill),
            )
            return self.connection.execute(
                "SELECT * FROM battle_field_actions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()

    def list_field_actions(self, guild_id: int, channel_id: int, status: str | None = None):
        query = "SELECT * FROM battle_field_actions WHERE guild_id=? AND channel_id=?"
        params: list[object] = [guild_id, channel_id]
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY id"
        with self.lock:
            return self.connection.execute(query, params).fetchall()

    def get_field_action(self, action_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM battle_field_actions WHERE id=?", (action_id,)
            ).fetchone()

    def claim_field_action(self, action_id: int, user_id: int, player_skill: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """UPDATE battle_field_actions
                   SET status='claimed', claimed_by=?, player_skill=?
                   WHERE id=? AND status='open'""",
                (user_id, player_skill, action_id),
            )
        return cursor.rowcount > 0

    def resolve_field_action(self, action_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_field_actions SET status='resolved' WHERE id=?", (action_id,)
            )

    def release_field_action(self, action_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE battle_field_actions
                   SET status='open', claimed_by=NULL, player_skill=NULL WHERE id=?""",
                (action_id,),
            )

    def next_battle_turn(self, guild_id: int, channel_id: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_sessions SET turn=turn+1 WHERE guild_id=? AND channel_id=? AND active=1",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_field_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "UPDATE battle_participants SET status='waiting', ready=0 WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "UPDATE battle_sessions SET phase='preparation' WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
        return self.get_battle(guild_id, channel_id)

    def join_battle(self, guild_id: int, channel_id: int, user_id: int, character_name: str):
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO battle_participants(guild_id,channel_id,user_id,character_name,status)
                   VALUES(?,?,?,?, 'waiting')
                   ON CONFLICT(guild_id,channel_id,user_id) DO UPDATE SET
                   character_name=excluded.character_name""",
                (guild_id, channel_id, user_id, character_name),
            )
        return self.get_battle_participant(guild_id, channel_id, user_id)

    def leave_battle(self, guild_id: int, channel_id: int, user_id: int) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM battle_participants WHERE guild_id=? AND channel_id=? AND user_id=?",
                (guild_id, channel_id, user_id),
            )
        return cursor.rowcount > 0

    def get_battle_participant(self, guild_id: int, channel_id: int, user_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM battle_participants
                   WHERE guild_id=? AND channel_id=? AND user_id=?""",
                (guild_id, channel_id, user_id),
            ).fetchone()

    def list_battle_participants(self, guild_id: int, channel_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM battle_participants
                   WHERE guild_id=? AND channel_id=? ORDER BY joined_at, user_id""",
                (guild_id, channel_id),
            ).fetchall()

    def set_battle_participant_status(
        self, guild_id: int, channel_id: int, user_id: int, status: str,
    ) -> None:
        if status not in {"waiting", "clashing", "done"}:
            raise ValueError("Status de participante inválido")
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE battle_participants SET status=?
                   WHERE guild_id=? AND channel_id=? AND user_id=?""",
                (status, guild_id, channel_id, user_id),
            )

    def set_battle_participant_ready(
        self, guild_id: int, channel_id: int, user_id: int, ready: bool,
    ) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE battle_participants SET ready=?
                   WHERE guild_id=? AND channel_id=? AND user_id=?""",
                (int(ready), guild_id, channel_id, user_id),
            )

    def set_battle_phase(self, guild_id: int, channel_id: int, phase: str):
        if phase not in {"preparation", "declaration", "resolution", "complete"}:
            raise ValueError("Fase de batalha inválida")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """UPDATE battle_sessions SET phase=?
                   WHERE guild_id=? AND channel_id=? AND active=1""",
                (phase, guild_id, channel_id),
            )
        return self.get_battle(guild_id, channel_id) if cursor.rowcount else None

    def reset_battle_readiness(self, guild_id: int, channel_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_participants SET ready=0 WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
