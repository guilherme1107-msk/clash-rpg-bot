"""Persistência SQLite do bot."""

from __future__ import annotations

import json
import sqlite3
import threading

from src.domain.combat import Skill, SkillEffect, clamp_sp
from src.domain.status import CombatStatus, STATUS_TYPES, on_round_end


def _effects_json(skill: Skill) -> str:
    return json.dumps([
        {"trigger": effect.trigger, "effect_type": effect.effect_type, "value": effect.value,
         "coin": effect.coin, "count": effect.count, "charge_cost": effect.charge_cost,
         "condition_status": effect.condition_status, "condition_min": effect.condition_min,
         "condition_owner": effect.condition_owner, "condition_value": effect.condition_value,
         "condition_per": effect.condition_per,
         "condition_max_stacks": effect.condition_max_stacks,
         "consume_condition": effect.consume_condition}
        for effect in skill.effects
    ], ensure_ascii=False)


def _effects_from_row(row) -> tuple[SkillEffect, ...]:
    raw = row["effects_json"] if "effects_json" in row.keys() else "[]"
    try:
        items = json.loads(raw or "[]")
        for item in items:
            if item.get("effect_type") == "false_hunger":
                item["effect_type"] = "special_condition"
            if item.get("condition_status") == "false_hunger":
                item["condition_status"] = "special_condition"
        return tuple(SkillEffect(**item) for item in items)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()


def _coin_layout_json(skill: Skill) -> str:
    return json.dumps(list(skill.coin_layout))


def _coin_layout_from_row(row) -> tuple[str, ...]:
    if "coin_layout_json" not in row.keys():
        return ()
    try:
        layout = tuple(json.loads(row["coin_layout_json"] or "[]"))
        return layout if len(layout) == row["coins"] else ()
    except (TypeError, json.JSONDecodeError):
        return ()


class Database:
    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.Lock()
        self.last_round_status_events = []

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
                    defense_level_mod INTEGER NOT NULL DEFAULT 0,
                    charge_potency_enabled INTEGER NOT NULL DEFAULT 0,
                    charge_spent INTEGER NOT NULL DEFAULT 0,
                    special_condition_consumed INTEGER NOT NULL DEFAULT 0,
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
                    coin_layout_json TEXT NOT NULL DEFAULT '[]',
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
                    defense_level_mod INTEGER NOT NULL DEFAULT 0,
                    charge_potency_enabled INTEGER NOT NULL DEFAULT 0,
                    charge_spent INTEGER NOT NULL DEFAULT 0,
                    special_condition_consumed INTEGER NOT NULL DEFAULT 0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
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
                    coin_layout_json TEXT NOT NULL DEFAULT '[]',
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
                CREATE TABLE IF NOT EXISTS battle_player_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    character_name TEXT NOT NULL,
                    target_enemy TEXT NOT NULL,
                    player_skill TEXT NOT NULL,
                    action_type TEXT NOT NULL DEFAULT 'unopposed',
                    final_damage INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id, channel_id)
                        REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS combat_statuses (
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('player','enemy')),
                    owner_id INTEGER NOT NULL,
                    status_type TEXT NOT NULL,
                    potency INTEGER NOT NULL DEFAULT 0 CHECK(potency >= 0),
                    count INTEGER NOT NULL DEFAULT 0 CHECK(count >= 0),
                    PRIMARY KEY (guild_id, owner_kind, owner_id, status_type)
                );
                CREATE TABLE IF NOT EXISTS guild_registry (
                    guild_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profile_appearance (
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('player','enemy')),
                    owner_id INTEGER NOT NULL,
                    image_url TEXT NOT NULL DEFAULT '',
                    accent_color TEXT NOT NULL DEFAULT '#b31824',
                    subtitle TEXT NOT NULL DEFAULT '',
                    secondary_color TEXT NOT NULL DEFAULT '#17181a',
                    image_mode TEXT NOT NULL DEFAULT 'banner',
                    image_position TEXT NOT NULL DEFAULT 'center',
                    footer_text TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (guild_id, owner_kind, owner_id)
                );
                CREATE TABLE IF NOT EXISTS media_upload_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('player','enemy')),
                    owner_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result_url TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                "defense_level_mod": "INTEGER NOT NULL DEFAULT 0",
                "charge_potency_enabled": "INTEGER NOT NULL DEFAULT 0",
                "charge_spent": "INTEGER NOT NULL DEFAULT 0",
                "special_condition_consumed": "INTEGER NOT NULL DEFAULT 0",
                "tags_json": "TEXT NOT NULL DEFAULT '[]'",
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
            if "coin_layout_json" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN coin_layout_json TEXT NOT NULL DEFAULT '[]'")
            enemy_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(enemies)")}
            if "uses_sanity" not in enemy_columns:
                self.connection.execute("ALTER TABLE enemies ADD COLUMN uses_sanity INTEGER NOT NULL DEFAULT 1")
            if "defense_level" not in enemy_columns:
                self.connection.execute("ALTER TABLE enemies ADD COLUMN defense_level INTEGER NOT NULL DEFAULT 0")
            for name in (
                "paralysis", "base_power_mod", "coin_power_mod", "clash_power_mod",
                "offense_level_mod", "defense_level_mod",
            ):
                if name not in enemy_columns:
                    self.connection.execute(f"ALTER TABLE enemies ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            for name, definition in {
                "charge_potency_enabled": "INTEGER NOT NULL DEFAULT 0",
                "charge_spent": "INTEGER NOT NULL DEFAULT 0",
                "special_condition_consumed": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in enemy_columns:
                    self.connection.execute(f"ALTER TABLE enemies ADD COLUMN {name} {definition}")
            # Bloodfiend/Bloodbag nasceram como status nas primeiras versões. Agora
            # são tags permanentes do hostil; a migração preserva as fichas antigas.
            legacy_markers = self.connection.execute(
                """SELECT owner_id,status_type FROM combat_statuses
                   WHERE owner_kind='enemy' AND status_type IN ('bloodfiend','bloodbag')
                   AND count>0"""
            ).fetchall()
            for marker in legacy_markers:
                enemy = self.connection.execute(
                    "SELECT tags_json FROM enemies WHERE id=?", (marker["owner_id"],)
                ).fetchone()
                if enemy is None:
                    continue
                try:
                    tags = list(json.loads(enemy["tags_json"] or "[]"))
                except (TypeError, json.JSONDecodeError):
                    tags = []
                if marker["status_type"] not in {tag.casefold() for tag in tags}:
                    tags.append(marker["status_type"])
                self.connection.execute(
                    "UPDATE enemies SET tags_json=? WHERE id=?",
                    (json.dumps(tags, ensure_ascii=False), marker["owner_id"]),
                )
            self.connection.execute(
                """DELETE FROM combat_statuses WHERE owner_kind='enemy'
                   AND status_type IN ('bloodfiend','bloodbag')"""
            )
            enemy_skill_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(enemy_skills)")}
            if "skill_type" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN skill_type TEXT NOT NULL DEFAULT 'attack'")
            if "unbreakable_coins" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN unbreakable_coins INTEGER NOT NULL DEFAULT 0")
            if "effects_json" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN effects_json TEXT NOT NULL DEFAULT '[]'")
            if "coin_layout_json" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN coin_layout_json TEXT NOT NULL DEFAULT '[]'")
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
            appearance_columns = {
                row[1] for row in self.connection.execute("PRAGMA table_info(profile_appearance)")
            }
            for name, definition in {
                "secondary_color": "TEXT NOT NULL DEFAULT '#17181a'",
                "image_mode": "TEXT NOT NULL DEFAULT 'banner'",
                "image_position": "TEXT NOT NULL DEFAULT 'center'",
                "footer_text": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in appearance_columns:
                    self.connection.execute(f"ALTER TABLE profile_appearance ADD COLUMN {name} {definition}")
            # Status sem Count não permanece guardado: isso impede que uma
            # aplicação futura apenas de Count recupere Potência antiga.
            self.connection.execute(
                """UPDATE combat_statuses SET status_type='special_condition'
                   WHERE status_type='false_hunger' AND NOT EXISTS (
                       SELECT 1 FROM combat_statuses AS current
                       WHERE current.guild_id=combat_statuses.guild_id
                         AND current.owner_kind=combat_statuses.owner_kind
                         AND current.owner_id=combat_statuses.owner_id
                         AND current.status_type='special_condition'
                   )"""
            )
            self.connection.execute("DELETE FROM combat_statuses WHERE status_type='false_hunger'")
            self.connection.execute("DELETE FROM combat_statuses WHERE count<=0")

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def save_guild(self, guild_id: int, name: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO guild_registry(guild_id,name) VALUES(?,?)
                   ON CONFLICT(guild_id) DO UPDATE SET name=excluded.name""",
                (guild_id, name[:100]),
            )

    def get_appearance(self, guild_id: int, owner_kind: str, owner_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT image_url,accent_color,subtitle,secondary_color,image_mode,
                          image_position,footer_text FROM profile_appearance
                   WHERE guild_id=? AND owner_kind=? AND owner_id=?""",
                (guild_id, owner_kind, owner_id),
            ).fetchone()

    def save_appearance(
        self, guild_id: int, owner_kind: str, owner_id: int,
        image_url: str, accent_color: str, subtitle: str,
        secondary_color: str | None = None, image_mode: str | None = None,
        image_position: str | None = None, footer_text: str | None = None,
    ) -> None:
        if owner_kind not in {"player", "enemy"}:
            raise ValueError("Tipo de ficha inválido.")
        current = self.get_appearance(guild_id, owner_kind, owner_id)
        secondary_color = secondary_color or (current["secondary_color"] if current else "#17181a")
        image_mode = image_mode or (current["image_mode"] if current else "banner")
        image_position = image_position or (current["image_position"] if current else "center")
        footer_text = footer_text if footer_text is not None else (current["footer_text"] if current else "")
        if image_mode not in {"banner", "thumbnail", "none"}:
            raise ValueError("Modo de imagem inválido.")
        if image_position not in {"center", "top", "bottom", "left", "right"}:
            raise ValueError("Posição da imagem inválida.")
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO profile_appearance
                   (guild_id,owner_kind,owner_id,image_url,accent_color,subtitle,
                    secondary_color,image_mode,image_position,footer_text)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id,owner_kind,owner_id)
                   DO UPDATE SET image_url=excluded.image_url,
                                 accent_color=excluded.accent_color,
                                 subtitle=excluded.subtitle,
                                 secondary_color=excluded.secondary_color,
                                 image_mode=excluded.image_mode,
                                 image_position=excluded.image_position,
                                 footer_text=excluded.footer_text""",
                (guild_id, owner_kind, owner_id, image_url[:1000], accent_color[:7], subtitle[:120],
                 secondary_color[:7], image_mode, image_position, footer_text[:160]),
            )

    def queue_media_upload(
        self, guild_id: int, owner_kind: str, owner_id: int, source_url: str,
    ) -> int:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE media_upload_jobs SET status='superseded',updated_at=CURRENT_TIMESTAMP
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status='pending'""",
                (guild_id, owner_kind, owner_id),
            )
            cursor = self.connection.execute(
                """INSERT INTO media_upload_jobs(guild_id,owner_kind,owner_id,source_url)
                   VALUES(?,?,?,?)""",
                (guild_id, owner_kind, owner_id, source_url[:1000]),
            )
        return int(cursor.lastrowid)

    def pending_media_uploads(self, limit: int = 5):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM media_upload_jobs WHERE status='pending'
                   ORDER BY id LIMIT ?""", (limit,),
            ).fetchall()

    def finish_media_upload(self, job_id: int, result_url: str) -> None:
        with self.lock, self.connection:
            job = self.connection.execute(
                "SELECT * FROM media_upload_jobs WHERE id=?", (job_id,),
            ).fetchone()
            if job is None or job["status"] != "pending":
                return
            self.connection.execute(
                """UPDATE media_upload_jobs SET status='complete',result_url=?,error='',
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""", (result_url, job_id),
            )
            self.connection.execute(
                """UPDATE profile_appearance SET image_url=?
                   WHERE guild_id=? AND owner_kind=? AND owner_id=?""",
                (result_url, job["guild_id"], job["owner_kind"], job["owner_id"]),
            )

    def fail_media_upload(self, job_id: int, error: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE media_upload_jobs SET status='failed',error=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""", (error[:500], job_id),
            )

    def set_status(
        self, guild_id: int, owner_kind: str, owner_id: int, status_type: str,
        potency: int, count: int,
    ) -> CombatStatus:
        if owner_kind not in {"player", "enemy"}:
            raise ValueError("Dono de status inválido.")
        if status_type not in STATUS_TYPES:
            raise ValueError("Status inválido.")
        if count <= 0:
            with self.lock, self.connection:
                self.connection.execute(
                    """DELETE FROM combat_statuses
                       WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type=?""",
                    (guild_id, owner_kind, owner_id, status_type),
                )
            return CombatStatus(status_type, 0, 0)
        status = CombatStatus(status_type, potency, count)
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO combat_statuses(guild_id,owner_kind,owner_id,status_type,potency,count)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(guild_id,owner_kind,owner_id,status_type)
                   DO UPDATE SET potency=excluded.potency,count=excluded.count""",
                (guild_id, owner_kind, owner_id, status.status_type, status.potency, status.count),
            )
        return status

    def add_status(
        self, guild_id: int, owner_kind: str, owner_id: int, status_type: str,
        potency: int, count: int,
    ) -> CombatStatus:
        current = self.get_status(guild_id, owner_kind, owner_id, status_type)
        old_potency = current.potency if current else 0
        old_count = current.count if current else 0
        new_potency = old_potency + potency
        new_count = old_count + count
        # No Limbus, um status de dois valores precisa de ambos para formar sua
        # pilha inicial. Quando o Count acaba, set_status remove a linha inteira.
        already_exists = old_potency > 0 and old_count > 0
        if not already_exists:
            if new_potency > 0 and new_count == 0:
                new_count = 1
            elif new_count > 0 and new_potency == 0:
                new_potency = 1
        return self.set_status(
            guild_id, owner_kind, owner_id, status_type,
            new_potency, new_count,
        )

    def consume_charge(
        self, guild_id: int, owner_kind: str, owner_id: int, amount: int,
    ) -> tuple[CombatStatus, int, int]:
        """Consome Count e converte cada 10 gastos em Potência, quando habilitado.

        Retorna ``(charge_atual, potência_ganha, progresso_0_a_9)``.
        """
        if amount < 0:
            raise ValueError("O consumo de Charge não pode ser negativo.")
        charge = self.get_status(guild_id, owner_kind, owner_id, "charge")
        if charge is None or charge.count < amount:
            raise ValueError("Charge Count insuficiente.")
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        with self.lock:
            row = self.connection.execute(
                f"SELECT charge_potency_enabled,charge_spent FROM {table} WHERE guild_id=? AND {key}=?",
                (guild_id, owner_id),
            ).fetchone()
        if row is None:
            raise ValueError("Ficha não encontrada para consumir Charge.")
        enabled = bool(row["charge_potency_enabled"])
        accumulated = row["charge_spent"] + amount if enabled else 0
        potency_gain, progress = divmod(accumulated, 10) if enabled else (0, 0)
        new_count = charge.count - amount
        new_potency = charge.potency + potency_gain
        if new_count <= 0:
            new_potency = 0
        with self.lock, self.connection:
            self.connection.execute(
                f"UPDATE {table} SET charge_spent=? WHERE guild_id=? AND {key}=?",
                (progress, guild_id, owner_id),
            )
        saved = self.set_status(
            guild_id, owner_kind, owner_id, "charge", new_potency, new_count,
        )
        return saved, potency_gain, progress

    def get_special_condition_consumed(
        self, guild_id: int, owner_kind: str, owner_id: int,
    ) -> int:
        """Total de Condição Especial consumido durante o Encounter atual."""
        if owner_kind not in {"player", "enemy"}:
            raise ValueError("Dono da Condição Especial inválido.")
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        with self.lock:
            row = self.connection.execute(
                f"SELECT special_condition_consumed FROM {table} WHERE guild_id=? AND {key}=?",
                (guild_id, owner_id),
            ).fetchone()
        return 0 if row is None else int(row["special_condition_consumed"])

    def consume_special_condition(
        self, guild_id: int, owner_kind: str, owner_id: int, maximum: int,
    ) -> tuple[CombatStatus, int, int]:
        """Consome até ``maximum`` de Count e registra o total do Encounter."""
        if maximum < 0:
            raise ValueError("O consumo máximo não pode ser negativo.")
        current = self.get_status(guild_id, owner_kind, owner_id, "special_condition")
        amount = min(maximum, current.count if current else 0)
        if amount:
            saved = self.set_status(
                guild_id, owner_kind, owner_id, "special_condition",
                current.potency, current.count - amount,
            )
        else:
            saved = current or CombatStatus("special_condition", 0, 0)
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                f"UPDATE {table} SET special_condition_consumed="
                f"special_condition_consumed+? WHERE guild_id=? AND {key}=?",
                (amount, guild_id, owner_id),
            )
        if not cursor.rowcount:
            raise ValueError("Ficha não encontrada para consumir Condição Especial.")
        return saved, amount, self.get_special_condition_consumed(guild_id, owner_kind, owner_id)

    def set_charge_potency_mode(
        self, guild_id: int, owner_kind: str, owner_id: int, enabled: bool,
    ) -> None:
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        if owner_kind not in {"player", "enemy"}:
            raise ValueError("Dono de Charge inválido.")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                f"UPDATE {table} SET charge_potency_enabled=?,charge_spent=0 "
                f"WHERE guild_id=? AND {key}=?",
                (1 if enabled else 0, guild_id, owner_id),
            )
        if not cursor.rowcount:
            raise ValueError("Ficha não encontrada.")

    def get_status(self, guild_id: int, owner_kind: str, owner_id: int, status_type: str) -> CombatStatus | None:
        if status_type not in STATUS_TYPES:
            raise ValueError("Status inválido.")
        with self.lock:
            row = self.connection.execute(
                """SELECT status_type,potency,count FROM combat_statuses
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type=?""",
                (guild_id, owner_kind, owner_id, status_type),
            ).fetchone()
        return None if row is None else CombatStatus(row["status_type"], row["potency"], row["count"])

    def list_statuses(self, guild_id: int, owner_kind: str, owner_id: int) -> list[CombatStatus]:
        with self.lock:
            rows = self.connection.execute(
                """SELECT status_type,potency,count FROM combat_statuses
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND count>0
                   ORDER BY status_type""",
                (guild_id, owner_kind, owner_id),
            ).fetchall()
        return [CombatStatus(row["status_type"], row["potency"], row["count"]) for row in rows]

    def process_round_end_statuses(self, guild_id: int, channel_id: int | None = None):
        """Aplica decaimento do fim da rodada e retorna eventos informativos."""
        events = []
        with self.lock:
            rows = self.connection.execute(
                """SELECT owner_kind,owner_id,status_type,potency,count FROM combat_statuses
                   WHERE guild_id=? AND count>0""", (guild_id,)
            ).fetchall()
            active_owners = None
            if channel_id is not None:
                active_owners = {
                    ("player", row["user_id"])
                    for row in self.connection.execute(
                        """SELECT user_id FROM battle_participants
                           WHERE guild_id=? AND channel_id=?""",
                        (guild_id, channel_id),
                    ).fetchall()
                }
                enemy_names = {
                    row["enemy_name"] for row in self.connection.execute(
                        """SELECT enemy_name FROM battle_field_actions
                           WHERE guild_id=? AND channel_id=?""",
                        (guild_id, channel_id),
                    ).fetchall()
                }
                enemy_names.update(
                    row["target_enemy"] for row in self.connection.execute(
                        """SELECT target_enemy FROM battle_player_actions
                           WHERE guild_id=? AND channel_id=?""",
                        (guild_id, channel_id),
                    ).fetchall()
                )
                for name in enemy_names:
                    enemy = self.connection.execute(
                        "SELECT id FROM enemies WHERE guild_id=? AND name=?",
                        (guild_id, name),
                    ).fetchone()
                    if enemy is not None:
                        active_owners.add(("enemy", enemy["id"]))
        for row in rows:
            if active_owners is not None and (row["owner_kind"], row["owner_id"]) not in active_owners:
                continue
            event = on_round_end(CombatStatus(row["status_type"], row["potency"], row["count"]))
            if event is None:
                continue
            self.set_status(
                guild_id, row["owner_kind"], row["owner_id"], row["status_type"],
                event.potency_after, event.count_after,
            )
            events.append((row["owner_kind"], row["owner_id"], event))
        return events

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

    def delete_character(self, guild_id: int, user_id: int) -> bool:
        """Remove a ficha e os dados que pertencem exclusivamente a ela."""
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM skills WHERE guild_id=? AND owner_id=?", (guild_id, user_id),
            )
            self.connection.execute(
                "DELETE FROM combat_statuses WHERE guild_id=? AND owner_kind='player' AND owner_id=?",
                (guild_id, user_id),
            )
            self.connection.execute(
                "DELETE FROM profile_appearance WHERE guild_id=? AND owner_kind='player' AND owner_id=?",
                (guild_id, user_id),
            )
            cursor = self.connection.execute(
                "DELETE FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id),
            )
        return bool(cursor.rowcount)

    def transfer_character(self, guild_id: int, old_owner: int, new_owner: int):
        """Move ficha e dependências para outro usuário do mesmo servidor."""
        if old_owner == new_owner:
            raise ValueError("O novo dono precisa ser diferente do dono atual.")
        with self.lock, self.connection:
            source = self.connection.execute(
                "SELECT * FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, old_owner),
            ).fetchone()
            if source is None:
                raise ValueError("A ficha original não foi encontrada.")
            if self.connection.execute(
                "SELECT 1 FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, new_owner),
            ).fetchone():
                raise ValueError("O novo dono já possui uma ficha neste servidor.")
            if self.connection.execute(
                """SELECT 1 FROM battle_participants p
                   JOIN battle_sessions b ON b.guild_id=p.guild_id AND b.channel_id=p.channel_id
                   WHERE p.guild_id=? AND p.user_id=? AND b.active=1 LIMIT 1""",
                (guild_id, old_owner),
            ).fetchone():
                raise ValueError("Encerre a batalha ativa antes de transferir esta ficha.")
            for table in ("skills", "combat_statuses", "profile_appearance", "media_upload_jobs"):
                self.connection.execute(
                    f"UPDATE {table} SET owner_id=? WHERE guild_id=? AND owner_id=?"
                    + (" AND owner_kind='player'" if table != "skills" else ""),
                    (new_owner, guild_id, old_owner),
                )
            self.connection.execute(
                "UPDATE characters SET user_id=? WHERE guild_id=? AND user_id=?",
                (new_owner, guild_id, old_owner),
            )
        return self.get_character(guild_id, new_owner)

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

    def add_effects(
        self, guild_id: int, user_id: int, paralysis: int, base: int, coin: int,
        clash: int = 0, offense: int = 0, defense: int = 0,
    ):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?,
                   clash_power_mod=clash_power_mod+?, offense_level_mod=offense_level_mod+?,
                   defense_level_mod=defense_level_mod+?
                   WHERE guild_id=? AND user_id=?""",
                (paralysis, base, coin, clash, offense, defense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def consume_clash_effects(self, guild_id: int, user_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=?, base_power_mod=0, coin_power_mod=0,
                   clash_power_mod=0, offense_level_mod=0, defense_level_mod=0
                   WHERE guild_id=? AND user_id=?""",
                (remaining_paralysis, guild_id, user_id),
            )

    def save_skill(self, guild_id: int, owner_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO skills(guild_id,owner_id,name,base_power,coin_power,coins,unbreakable_coins,description,level_type,effects_json,coin_layout_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,owner_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, unbreakable_coins=excluded.unbreakable_coins,
                   description=excluded.description, level_type=excluded.level_type,
                   effects_json=excluded.effects_json, coin_layout_json=excluded.coin_layout_json""",
                (guild_id, owner_id, skill.name, skill.base_power, skill.coin_power,
                 skill.coins, skill.unbreakable_coins, skill.description, skill.skill_type,
                 _effects_json(skill), _coin_layout_json(skill)),
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
            row["unbreakable_coins"], _effects_from_row(row), _coin_layout_from_row(row)
        )

    def list_skills(self, guild_id: int, owner_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
                (guild_id, owner_id),
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], {"offense": "attack", "defense": "guard"}.get(r["level_type"], r["level_type"]), r["unbreakable_coins"], _effects_from_row(r), _coin_layout_from_row(r)) for r in rows]

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

    def get_enemy_by_id(self, enemy_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE id=?", (enemy_id,)
            ).fetchone()

    def list_enemies(self, guild_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE guild_id=? ORDER BY name", (guild_id,)
            ).fetchall()

    @staticmethod
    def _normalize_enemy_tags(tags) -> list[str]:
        """Normaliza tags livres sem transformar texto do mestre em SQL/Markdown."""
        if isinstance(tags, str):
            tags = tags.split(",")
        result: list[str] = []
        seen: set[str] = set()
        for raw in tags or []:
            tag = " ".join(str(raw).strip().split())[:32]
            key = tag.casefold()
            if not tag or key in seen:
                continue
            seen.add(key)
            result.append(tag)
            if len(result) == 12:
                break
        return result

    def get_enemy_tags(self, enemy_id: int) -> list[str]:
        with self.lock:
            row = self.connection.execute(
                "SELECT tags_json FROM enemies WHERE id=?", (enemy_id,)
            ).fetchone()
        if row is None:
            return []
        try:
            return self._normalize_enemy_tags(json.loads(row["tags_json"] or "[]"))
        except (TypeError, json.JSONDecodeError):
            return []

    def set_enemy_tags(self, guild_id: int, enemy_id: int, tags) -> list[str]:
        normalized = self._normalize_enemy_tags(tags)
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE enemies SET tags_json=? WHERE guild_id=? AND id=?",
                (json.dumps(normalized, ensure_ascii=False), guild_id, enemy_id),
            )
        if not cursor.rowcount:
            raise ValueError("Inimigo não encontrado.")
        return normalized

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

    def add_enemy_effects(
        self, enemy_id: int, paralysis: int, base: int, coin: int,
        clash: int, offense: int, defense: int = 0,
    ):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemies SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?,
                   clash_power_mod=clash_power_mod+?, offense_level_mod=offense_level_mod+?,
                   defense_level_mod=defense_level_mod+?
                   WHERE id=?""",
                (paralysis, base, coin, clash, offense, defense, enemy_id),
            )
            return self.connection.execute("SELECT * FROM enemies WHERE id=?", (enemy_id,)).fetchone()

    def consume_enemy_effects(self, enemy_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemies SET paralysis=?, base_power_mod=0, coin_power_mod=0,
                   clash_power_mod=0, offense_level_mod=0, defense_level_mod=0 WHERE id=?""",
                (remaining_paralysis, enemy_id),
            )

    def save_enemy_skill(self, enemy_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO enemy_skills(enemy_id,name,base_power,coin_power,coins,unbreakable_coins,description,skill_type,effects_json,coin_layout_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(enemy_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, unbreakable_coins=excluded.unbreakable_coins,
                   description=excluded.description, skill_type=excluded.skill_type,
                   effects_json=excluded.effects_json, coin_layout_json=excluded.coin_layout_json""",
                (enemy_id, skill.name, skill.base_power, skill.coin_power, skill.coins,
                 skill.unbreakable_coins, skill.description, skill.skill_type,
                 _effects_json(skill), _coin_layout_json(skill)),
            )

    def get_enemy_skill(self, enemy_id: int, name: str) -> Skill | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, name)
            ).fetchone()
        return None if row is None else Skill(
            row["name"], row["base_power"], row["coin_power"], row["coins"], row["description"], row["skill_type"], row["unbreakable_coins"], _effects_from_row(row), _coin_layout_from_row(row)
        )

    def list_enemy_skills(self, enemy_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM enemy_skills WHERE enemy_id=? ORDER BY name", (enemy_id,)
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], r["skill_type"], r["unbreakable_coins"], _effects_from_row(r), _coin_layout_from_row(r)) for r in rows]

    def delete_enemy_skill(self, enemy_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, name)
            )
        return cursor.rowcount > 0

    def start_battle(self, guild_id: int, channel_id: int, name: str, created_by: int):
        with self.lock, self.connection:
            # Contadores de consumo pertencem somente ao encontro atual.
            self.connection.execute(
                "UPDATE characters SET charge_spent=0,special_condition_consumed=0 WHERE guild_id=?", (guild_id,),
            )
            self.connection.execute(
                "UPDATE enemies SET charge_spent=0,special_condition_consumed=0 WHERE guild_id=?", (guild_id,),
            )
            self.connection.execute(
                "DELETE FROM battle_field_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_player_actions WHERE guild_id=? AND channel_id=?",
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

    def add_player_action(
        self, guild_id: int, channel_id: int, user_id: int, character_name: str,
        target_enemy: str, player_skill: str, action_type: str, final_damage: int,
    ):
        if action_type not in {"unopposed", "follow_up"}:
            raise ValueError("Tipo de ação do jogador inválido")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """INSERT INTO battle_player_actions(
                       guild_id,channel_id,user_id,character_name,target_enemy,
                       player_skill,action_type,final_damage
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (guild_id, channel_id, user_id, character_name, target_enemy,
                 player_skill, action_type, final_damage),
            )
            return self.connection.execute(
                "SELECT * FROM battle_player_actions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()

    def list_player_actions(self, guild_id: int, channel_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM battle_player_actions
                   WHERE guild_id=? AND channel_id=? ORDER BY id""",
                (guild_id, channel_id),
            ).fetchall()

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
        self.last_round_status_events = self.process_round_end_statuses(guild_id, channel_id)
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
                "DELETE FROM battle_player_actions WHERE guild_id=? AND channel_id=?",
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
