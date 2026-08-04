"""Persistência SQLite do bot."""

from __future__ import annotations

import sqlite3
import threading

from clash_engine import Skill, clamp_sp


class Database:
    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
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
                    description TEXT NOT NULL DEFAULT '',
                    level_type TEXT NOT NULL DEFAULT 'offense',
                    UNIQUE (guild_id, owner_id, name)
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
            }.items():
                if name not in character_columns:
                    self.connection.execute(f"ALTER TABLE characters ADD COLUMN {name} {definition}")
            skill_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(skills)")}
            if "level_type" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN level_type TEXT NOT NULL DEFAULT 'offense'")

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

    def set_levels(self, guild_id: int, user_id: int, offense: int, defense: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET offense_level=?, defense_level=? WHERE guild_id=? AND user_id=?",
                (offense, defense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def add_effects(self, guild_id: int, user_id: int, paralysis: int, base: int, coin: int):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?
                   WHERE guild_id=? AND user_id=?""",
                (paralysis, base, coin, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def consume_clash_effects(self, guild_id: int, user_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=?, base_power_mod=0, coin_power_mod=0
                   WHERE guild_id=? AND user_id=?""",
                (remaining_paralysis, guild_id, user_id),
            )

    def save_skill(self, guild_id: int, owner_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO skills(guild_id,owner_id,name,base_power,coin_power,coins,description,level_type)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,owner_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, description=excluded.description, level_type=excluded.level_type""",
                (guild_id, owner_id, skill.name, skill.base_power, skill.coin_power,
                 skill.coins, skill.description, skill.level_type),
            )

    def get_skill(self, guild_id: int, owner_id: int, name: str) -> Skill | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? AND name=?",
                (guild_id, owner_id, name),
            ).fetchone()
        return None if row is None else Skill(
            row["name"], row["base_power"], row["coin_power"],
            row["coins"], row["description"], row["level_type"]
        )

    def list_skills(self, guild_id: int, owner_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
                (guild_id, owner_id),
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], r["level_type"]) for r in rows]
