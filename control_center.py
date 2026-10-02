"""Central local de controle do Clash RPG Bot, sem dependências adicionais."""

from __future__ import annotations

import argparse
import base64
from collections import deque
import json
import os
from pathlib import Path
import re
import sqlite3
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser
import mimetypes
import uuid
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from database import Database
from rosemary_panel import RosemaryPanelRepository, save_rosemary_content, update_rosemary_mechanics
from src.application.services import VALID_CONDITIONS, normalize_skill_slot, parse_skill_payload
from src.application.services.core_gateway import commit_sqlite_event
from src.application.services.profile_service import default_profile, normalize_profile, normalize_profile_update
from src.domain.combat import EFFECT_TRIGGERS, EFFECT_TYPES


ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "control_center.html"
ENV_PATH = ROOT / ".env"
AUDIT_PATH = ROOT / "clash_audit.log"
CONTROL_STATE_PATH = ROOT / "control_center_state.json"
UPLOAD_DIR = ROOT / "control_center_uploads"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
CONFIG_KEYS = (
    "DISCORD_GUILD_ID", "DATABASE_PATH", "CLASH_GUILD_ID", "CLASH_CHANNEL_ID", "CLASH_CHANNELS",
    "AUDIT_CHANNEL_ID", "APPEARANCE_CHANNEL_ID", "PRIVATE_SKILL_OWNER_ID",
    "UNBREAKABLE_FOLLOWUP_GIF", "DAMAGE_RESOLUTION_GIF",
)
DEFAULT_APPEARANCE_CHANNEL_ID = "1537587461629280266"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
UI_EMOJI_DEFAULTS = {
    "coin_active": ("EMOJI_COIN_ACTIVE", "<:ML:1534094500815831181>"),
    "coin_normal": ("EMOJI_COIN_NORMAL", "<:MN:1534094257915297954>"),
    "coin_broken": ("EMOJI_COIN_BROKEN", "<:SA:1538694912877269032>"),
    "coin_heads": ("EMOJI_COIN_HEADS", "<:CG:1534127740381302864>"),
    "coin_unbreakable": ("EMOJI_COIN_UNBREAKABLE", "<:MI:1535257836966117376>"),
    "coin_unbreakable_heads": ("EMOJI_COIN_UNBREAKABLE_HEADS", "<:MIA:1535261448694145124>"),
    "paralysis": ("EMOJI_PARALYZE", "<:EP:1534104414183493702>"),
    "glimpse_of_precognition": ("EMOJI_GLIMPSE_OF_PRECOGNITION", "<:GlimpseofPrecognition:1553633485090988052>"),
    "base_power": ("EMOJI_ATTACK_UP", "<:EAU:1535263226936295565>"),
    "base_power_down": ("EMOJI_ATTACK_DOWN", "<:EAD:1534104291772469258>"),
    "final_power": ("EMOJI_ATTACK_UP", "<:EAU:1535263226936295565>"),
    "final_power_down": ("EMOJI_ATTACK_DOWN", "<:EAD:1534104291772469258>"),
    "damage_percent": ("EMOJI_ATTACK_UP", "<:EAU:1535263226936295565>"),
    "damage_percent_down": ("EMOJI_ATTACK_DOWN", "<:EAD:1534104291772469258>"),
    "coin_power": ("EMOJI_PLUS_COIN_BOOST", "<:PCB:1534122027143921766>"),
    "coin_power_down": ("EMOJI_PLUS_COIN_DROP", "<:PCD:1534122057187590344>"),
    "clash_power": ("EMOJI_CLASH_UP", "<:ECU:1534104390896455740>"),
    "clash_power_down": ("EMOJI_CLASH_DOWN", "<:ECD:1534104363658641479>"),
    "offense_level": ("EMOJI_OFFENSE_UP", "<:OLU:1534122107716501534>"),
    "offense_level_down": ("EMOJI_OFFENSE_DOWN", "<:OLD:1534122151911758111>"),
    "defense_level": ("EMOJI_DEFENSE_LEVEL", "<:Defense_Up:1539383241604210802>"),
    "make_unbreakable": ("EMOJI_COIN_UNBREAKABLE", "<:MI:1535257836966117376>"),
    "burn": ("EMOJI_STATUS_BURN", "<:Burn:1539383118191140914>"),
    "bleed": ("EMOJI_STATUS_BLEED", "<:Bleed:1539383114957070397>"),
    "tremor": ("EMOJI_STATUS_TREMOR", "<:Tremor:1539383133772714015>"),
    "rupture": ("EMOJI_STATUS_RUPTURE", "<:Rupture:1539383143298240523>"),
    "sinking": ("EMOJI_STATUS_SINKING", "<:Sinking:1539383130371391589>"),
    "poise": ("EMOJI_STATUS_POISE", "<:Poise:1539383124285198337>"),
    "charge": ("EMOJI_STATUS_CHARGE", "<:Charge:1539383121227681942>"),
    "haste": ("EMOJI_STATUS_HASTE", "<:Haste:1539383205575131298>"),
    "special_condition": ("EMOJI_STATUS_SPECIAL_CONDITION", "<:PlH:1538709761757806813>"),
    "devotion_repressed": ("EMOJI_STATUS_DEVOTION_REPRESSED", "🩸"),
    "bloodfiend": ("EMOJI_STATUS_BLOODFIEND", "🧛"),
    "bloodbag": ("EMOJI_STATUS_BLOODBAG", "🩸"),
    # E.G.O Gifts — recurso e variantes únicas (emojis do autor, 2026-10-01).
    "bloodfeast": ("EMOJI_STATUS_BLOODFEAST", "<:Bloodfeast:1539383222566260832>"),
    "unique_bleed": ("EMOJI_STATUS_UNIQUE_BLEED", "<:Efeito_Bleed_Unique:1539412731071955006>"),
    "unique_bloodfeast": ("EMOJI_STATUS_UNIQUE_BLOODFEAST", "<:Bloodfeast:1539383222566260832>"),
    "tremor_burst": ("EMOJI_TREMOR_BURST", "<:Tremor_Burst:1539383137069703208>"),
    "tremor_scorch": ("EMOJI_STATUS_TREMOR_SCORCH", "<:Tremor_Scorch:1539383164621815968>"),
    "amplitude_conversion_scorch": ("EMOJI_AMPLITUDE_CONVERSION", "<:Tremor_Conversion:1539383102801969192>"),
}


def env_config() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def database_path() -> Path:
    raw = env_config().get("DATABASE_PATH", "clash_rpg.sqlite3")
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def ui_assets() -> dict:
    config = env_config()
    assets = {}
    for key, (env_key, fallback) in UI_EMOJI_DEFAULTS.items():
        raw = config.get(env_key) or fallback
        match = re.fullmatch(r"<(a?):([A-Za-z0-9_]+):(\d+)>", raw)
        if not match:
            continue
        animated, name, emoji_id = match.groups()
        extension = "gif" if animated else "webp"
        assets[key] = {
            "name": name, "id": emoji_id,
            "url": f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?size=64&quality=lossless",
        }
    return {"emojis": assets}


class BotProcess:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.RLock()
        self.output: deque[str] = deque(maxlen=1500)
        self.started_at: float | None = None

    @property
    def running(self) -> bool:
        return (self.process is not None and self.process.poll() is None) or self._control("PING") is not None

    @staticmethod
    def _control(command: str, timeout: float = 0.35) -> str | None:
        port = int(env_config().get("BOT_INSTANCE_LOCK_PORT", "47653") or 47653)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
                connection.sendall(command.encode("ascii"))
                return connection.recv(128).decode("ascii", errors="replace")
        except OSError:
            return None

    def remote_pid(self) -> int | None:
        reply = self._control("PING")
        if not reply or not reply.startswith("PONG "):
            return None
        try:
            return int(reply.split()[1])
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _venv_python() -> str:
        """Retorna o interpretador do .venv se existir, senão sys.executable."""
        if os.name == "nt":
            candidate = ROOT / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = ROOT / ".venv" / "bin" / "python"
        return str(candidate) if candidate.is_file() else sys.executable

    def start(self) -> dict:
        with self.lock:
            if self.running:
                return self.status("O bot já está ligado.")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            python = self._venv_python()
            self.process = subprocess.Popen(
                [python, "bot.py"], cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=creationflags,
            )
            self.started_at = time.time()
            threading.Thread(target=self._read_output, daemon=True).start()
            return self.status("Bot iniciado pela Central.")

    def _read_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.output.append(ANSI_RE.sub("", line.rstrip()))
        code = process.wait()
        self.output.append(f"[PROCESSO ENCERRADO] código={code}")

    def stop(self) -> dict:
        with self.lock:
            if not self.running:
                return self.status("O bot já está desligado.")
            reply = self._control("STOP", timeout=1.0)
            if reply == "STOPPING":
                deadline = time.time() + 10
                while time.time() < deadline and self._control("PING") is not None:
                    time.sleep(0.15)
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=3)
            if self.running:
                return self.status("Não consegui desligar o bot; confira os logs.")
            return self.status("Bot desligado pela Central.")

    def restart(self) -> dict:
        self.stop()
        time.sleep(0.4)
        return self.start()

    def status(self, message: str = "") -> dict:
        running = self.running
        remote_pid = self.remote_pid() if running else None
        code = None if self.process is None or running else self.process.returncode
        return {
            "running": running,
            "pid": remote_pid or (self.process.pid if running and self.process else None),
            "exit_code": code,
            "started_at": self.started_at,
            "uptime": int(time.time() - self.started_at) if running and self.started_at else 0,
            "managed": bool(self.process is not None and self.process.poll() is None),
            "message": message,
        }


BOT_PROCESS = BotProcess()


def db_rows(query: str, params: tuple = ()) -> list[dict]:
    path = database_path()
    if not path.exists():
        return []
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(query, params).fetchall()]
    finally:
        connection.close()


def database_revision() -> dict:
    """Assinatura barata para o cliente detectar alterações sem baixar tudo."""
    path = database_path()
    parts = []
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            stat = candidate.stat()
            parts.append(f"{candidate.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except FileNotFoundError:
            continue
    return {"revision": "|".join(parts) or "missing"}


def api_entities(guild_id: int | None = None) -> dict:
    where = " WHERE guild_id=?" if guild_id is not None else ""
    params = (guild_id,) if guild_id is not None else ()
    characters = db_rows(
        "SELECT guild_id,user_id,name,sp,offense_level,defense_level,charge_potency_enabled,charge_spent FROM characters" + where + " ORDER BY name",
        params,
    )
    enemies = db_rows(
        "SELECT id,guild_id,name,sp,uses_sanity,offense_level,defense_level,charge_potency_enabled,charge_spent FROM enemies" + where + " ORDER BY name",
        params,
    )
    appearance_rows = db_rows(
        """SELECT guild_id,owner_kind,owner_id,image_url,accent_color,subtitle,
                  secondary_color,image_mode,image_position,footer_text FROM profile_appearance"""
    )
    appearances = {
        (row["guild_id"], row["owner_kind"], row["owner_id"]): row
        for row in appearance_rows
    }
    for row in characters:
        row.update(appearances.get((row["guild_id"], "player", row["user_id"]), {}))
    for row in enemies:
        row.update(appearances.get((row["guild_id"], "enemy", row["id"]), {}))
    known = {row["guild_id"]: row["name"] for row in db_rows("SELECT guild_id,name FROM guild_registry")}
    guild_ids = sorted({row["guild_id"] for row in characters + enemies} | set(known))
    guilds = [{"id": str(value), "name": known.get(value, f"Servidor {value}")} for value in guild_ids]
    # IDs Snowflake do Discord ultrapassam a precisão segura do JavaScript.
    # A API sempre os envia como texto para que não sejam arredondados no navegador.
    for row in characters:
        row["guild_id"] = str(row["guild_id"])
        row["user_id"] = str(row["user_id"])
    for row in enemies:
        row["guild_id"] = str(row["guild_id"])
        row["id"] = str(row["id"])
    return {"guilds": guilds, "characters": characters, "enemies": enemies}


def api_entity_detail(kind: str, guild_id: int, owner_id: int) -> dict:
    table, key = ("enemies", "id") if kind == "enemy" else ("characters", "user_id")
    rows = db_rows(f"SELECT * FROM {table} WHERE guild_id=? AND {key}=?", (guild_id, owner_id))
    if not rows:
        raise ValueError("Ficha não encontrada.")
    appearance = db_rows(
        """SELECT image_url,accent_color,subtitle,secondary_color,image_mode,
                  image_position,footer_text FROM profile_appearance
           WHERE guild_id=? AND owner_kind=? AND owner_id=?""",
        (guild_id, kind, owner_id),
    )
    statuses = db_rows(
        """SELECT status_type,potency,count FROM combat_statuses
           WHERE guild_id=? AND owner_kind=? AND owner_id=? AND count>0
           ORDER BY status_type""",
        (guild_id, kind, owner_id),
    )
    private_owner = int(env_config().get("PRIVATE_SKILL_OWNER_ID", "1034518001535430777") or 0)
    if kind != "player" or owner_id != private_owner:
        statuses = [row for row in statuses if row["status_type"] != "devotion_repressed"]
    media_jobs = db_rows(
        """SELECT id,status,error,result_url,updated_at FROM media_upload_jobs
           WHERE guild_id=? AND owner_kind=? AND owner_id=? ORDER BY id DESC LIMIT 1""",
        (guild_id, kind, owner_id),
    )
    tags = []
    if kind == "enemy":
        try:
            tags = Database._normalize_enemy_tags(json.loads(rows[0].get("tags_json") or "[]"))
        except (TypeError, json.JSONDecodeError):
            tags = []
    db = Database(database_path())
    passives = db.list_passives(guild_id, kind, owner_id)
    if kind == "player" and owner_id == private_owner:
        rosemary_rules = db.rosemary_passive_rules(guild_id, owner_id)
        rosemary_passives = []
        if rosemary_rules.get("mode") == "chains":
            rosemary_passives = [
                {"id": -1, "name": "Correntes da Redenção (Uptie 4)", "description": "Concede +2% de dano por cada 4 de Bleed no alvo (máx. 10%). Se o alvo tiver 20+ Bleed, a última moeda recebe +20% de dano final. Ao final do turno com 30+ SP, consome 10 SP para progredir Selos."},
                {"id": -2, "name": "Devoção Reprimida & Apressada", "description": "Ganha Haste +2 na 1ª ação e Haste +1 nas demais. Converte Devoção Reprimida em Selos de Sangue no combate."},
            ]
        elif rosemary_rules.get("mode") == "hunger":
            rosemary_passives = [
                {"id": -1, "name": "Possua-me (Uptie 3)", "description": "Ganha +0.1% de dano para cada ponto de Falsa Fome consumido (máx. +15%)."},
            ]
        passives = rosemary_passives + passives
    ego_gifts = db.list_ego_gifts(guild_id, kind, owner_id)
    rosemary_state = dict(db.get_rosemary_state(guild_id, owner_id)) if (kind == "player" and owner_id == private_owner) else None
    return {
        "entity": dict(rows[0]), "statuses": [dict(s) for s in statuses], "skills": api_skills(kind, owner_id, guild_id),
        "passives": passives, "ego_gifts": ego_gifts, "rosemary_state": rosemary_state,
        "tags": tags,
        # §7.3 — keywords da ficha, que alimentam os cards da aba KEYWORDS.
        "keywords": sorted(db.get_keywords(guild_id, kind, owner_id)),
        "media_sync": dict(media_jobs[0]) if media_jobs else None,
        "appearance": appearance[0] if appearance else {
            "image_url": "", "accent_color": "#b31824", "subtitle": "",
            "secondary_color": "#17181a", "image_mode": "banner",
            "image_position": "center", "footer_text": "",
        },
    }


def save_entity(payload: dict) -> dict:
    kind, guild_id, owner_id = str(payload["kind"]), int(payload["guild_id"]), int(payload["owner_id"])
    table, key = ("enemies", "id") if kind == "enemy" else ("characters", "user_id")
    name = str(payload["name"]).strip()[:50]
    if not name:
        raise ValueError("A ficha precisa de um nome.")
    sp = max(-45, min(45, int(payload.get("sp", 0))))
    fields = ["name=?", "sp=?", "offense_level=?", "defense_level=?"]
    values = [name, sp, int(payload.get("offense_level", 0)), int(payload.get("defense_level", 0))]
    modifier_names = (
        "paralysis", "base_power_mod", "coin_power_mod", "clash_power_mod", "offense_level_mod",
    )
    if kind == "player":
        modifier_names += ("defense_level_mod",)
    for modifier in modifier_names:
        if modifier in payload:
            fields.append(f"{modifier}=?")
            values.append(int(payload[modifier]))
    if kind == "enemy" and "uses_sanity" in payload:
        fields.append("uses_sanity=?")
        values.append(1 if payload["uses_sanity"] else 0)
    if "charge_potency_enabled" in payload:
        fields.append("charge_potency_enabled=?")
        values.append(1 if payload["charge_potency_enabled"] else 0)
    connection = sqlite3.connect(database_path(), timeout=5)
    try:
        with connection:
            cursor = connection.execute(
                f"UPDATE {table} SET {','.join(fields)} WHERE guild_id=? AND {key}=?",
                (*values, guild_id, owner_id),
            )
            if not cursor.rowcount:
                raise ValueError("Ficha não encontrada.")
    finally:
        connection.close()
    return {"ok": True}


def transfer_character(payload: dict) -> dict:
    """Transfere uma ficha e todos os dados vinculados para outro usuário."""
    guild_id = int(payload["guild_id"])
    old_owner = int(payload["owner_id"])
    new_owner = int(payload["new_owner_id"])
    if not 10**14 <= new_owner < 10**22:
        raise ValueError("Informe um ID válido de usuário do Discord.")
    database = Database(str(database_path()))
    database.setup()
    try:
        moved = database.transfer_character(guild_id, old_owner, new_owner)
    except sqlite3.IntegrityError as error:
        raise ValueError(
            "O novo dono possui dados antigos que entram em conflito com esta ficha."
        ) from error
    finally:
        database.close()
def save_passive(payload: dict) -> dict:
    guild_id, kind, owner_id = int(payload["guild_id"]), str(payload["kind"]), int(payload["owner_id"])
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("A passiva precisa de um nome.")
    desc = str(payload.get("description", "")).strip()
    db = Database(database_path())
    pid = int(payload["id"]) if payload.get("id") else None
    return db.save_passive(guild_id, kind, owner_id, name, desc, passive_id=pid)

def delete_passive(payload: dict) -> dict:
    guild_id, kind, owner_id = int(payload["guild_id"]), str(payload["kind"]), int(payload["owner_id"])
    pid = int(payload["id"])
    db = Database(database_path())
    db.delete_passive(guild_id, kind, owner_id, pid)
    return {"ok": True}

def save_rosemary_state(payload: dict) -> dict:
    guild_id, owner_id = int(payload["guild_id"]), int(payload["owner_id"])
    db = Database(database_path())
    changes = {}
    if "false_hunger_consumed_total" in payload:
        changes["false_hunger_consumed_total"] = int(payload["false_hunger_consumed_total"])
    if "seals" in payload:
        changes["seals"] = int(payload["seals"])
    if "unpacked" in payload:
        changes["unpacked"] = 1 if payload["unpacked"] else 0
    db.update_rosemary_state(guild_id, owner_id, **changes)
    return {"ok": True}

def save_ego_gift(payload: dict) -> dict:
    guild_id, kind, owner_id = int(payload["guild_id"]), str(payload["kind"]), int(payload["owner_id"])
    if not str(payload.get("name", "")).strip():
        raise ValueError("O E.G.O Gift precisa de um nome.")
    db = Database(database_path())
    return db.save_ego_gift(guild_id, kind, owner_id, payload)

def delete_ego_gift(payload: dict) -> dict:
    guild_id, kind, owner_id = int(payload["guild_id"]), str(payload["kind"]), int(payload["owner_id"])
    gid = int(payload["id"])
    db = Database(database_path())
    db.delete_ego_gift(guild_id, kind, owner_id, gid)
    return {"ok": True}


def guild_members(guild_id: int) -> dict:
    """Lista membros para seletores da Central sem expor o token do bot."""
    # O banco é um fallback útil quando o Discord bloqueia a listagem completa
    # (bot ausente ou Server Members Intent desativado).
    known = db_rows("SELECT user_id,name FROM characters WHERE guild_id=? ORDER BY name", (guild_id,))
    members = [{"id": str(item["user_id"]), "name": item["name"], "username": "", "source": "ficha"} for item in known]
    warning = ""
    try:
        raw = _discord_api_json(f"/guilds/{guild_id}/members?limit=1000")
    except ValueError as error:
        raw = []
        warning = "O Discord não liberou a lista completa. Ative Server Members Intent e confirme que o bot está neste servidor."
    by_id = {item["id"]: item for item in members}
    for item in raw if isinstance(raw, list) else []:
        user = item.get("user") or {}
        if user.get("bot"):
            continue
        user_id = str(user.get("id", ""))
        display = item.get("nick") or user.get("global_name") or user.get("username") or user_id
        by_id[user_id] = {"id": user_id, "name": display, "username": user.get("username", ""), "source": "discord"}
    members = list(by_id.values())
    members.sort(key=lambda item: item["name"].casefold())
    return {"guild_id": str(guild_id), "members": members, "warning": warning}


def move_entity(payload: dict) -> dict:
    kind = str(payload.get("kind", "player"))
    source = int(payload["guild_id"]); destination = int(payload["new_guild_id"])
    owner_id = int(payload["owner_id"])
    if source == destination:
        raise ValueError("A ficha já está neste servidor.")
    connection = sqlite3.connect(database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            if kind == "player":
                row = connection.execute("SELECT * FROM characters WHERE guild_id=? AND user_id=?", (source, owner_id)).fetchone()
                if row is None: raise ValueError("Ficha não encontrada.")
                if connection.execute("SELECT 1 FROM characters WHERE guild_id=? AND user_id=?", (destination, owner_id)).fetchone():
                    raise ValueError("Este dono já possui uma ficha no servidor de destino.")
                if connection.execute("SELECT 1 FROM battle_participants p JOIN battle_sessions b ON b.guild_id=p.guild_id AND b.channel_id=p.channel_id WHERE p.guild_id=? AND p.user_id=? AND b.active=1", (source, owner_id)).fetchone():
                    raise ValueError("Encerre o Encounter ativo antes de mover esta ficha.")
                columns = list(row.keys()); values = [destination if key == "guild_id" else row[key] for key in columns]
                connection.execute(f"INSERT INTO characters({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", values)
                for table in ("skills", "combat_statuses", "profile_appearance", "media_upload_jobs"):
                    suffix = " AND owner_kind='player'" if table != "skills" else ""
                    connection.execute(f"UPDATE {table} SET guild_id=? WHERE guild_id=? AND owner_id=?{suffix}", (destination, source, owner_id))
                connection.execute("UPDATE character_profiles SET guild_id=? WHERE guild_id=? AND user_id=?", (destination, source, owner_id))
                connection.execute("DELETE FROM characters WHERE guild_id=? AND user_id=?", (source, owner_id))
                name = row["name"]
            elif kind == "enemy":
                row = connection.execute("SELECT * FROM enemies WHERE guild_id=? AND id=?", (source, owner_id)).fetchone()
                if row is None: raise ValueError("Hostil não encontrado.")
                if connection.execute("SELECT 1 FROM enemies WHERE guild_id=? AND name=? COLLATE NOCASE", (destination, row["name"])).fetchone():
                    raise ValueError("Já existe um hostil com este nome no servidor de destino.")
                if connection.execute("SELECT 1 FROM battle_field_actions a JOIN battle_sessions b ON b.guild_id=a.guild_id AND b.channel_id=a.channel_id WHERE a.guild_id=? AND a.enemy_name=? AND b.active=1", (source, row["name"])).fetchone():
                    raise ValueError("Encerre o Encounter deste hostil antes de movê-lo.")
                connection.execute("UPDATE enemies SET guild_id=? WHERE guild_id=? AND id=?", (destination, source, owner_id))
                for table in ("combat_statuses", "profile_appearance", "media_upload_jobs"):
                    connection.execute(f"UPDATE {table} SET guild_id=? WHERE guild_id=? AND owner_kind='enemy' AND owner_id=?", (destination, source, owner_id))
                name = row["name"]
            else:
                raise ValueError("Tipo de ficha inválido.")
    finally:
        connection.close()
    return {"ok": True, "kind": kind, "name": name, "guild_id": str(destination), "owner_id": str(owner_id)}


def delete_entity(payload: dict) -> dict:
    kind = str(payload.get("kind", "player")); guild_id = int(payload["guild_id"]); owner_id = int(payload["owner_id"])
    connection = sqlite3.connect(database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            table, key = ("enemies", "id") if kind == "enemy" else ("characters", "user_id")
            row = connection.execute(f"SELECT name FROM {table} WHERE guild_id=? AND {key}=?", (guild_id, owner_id)).fetchone()
            if row is None: raise ValueError("Ficha não encontrada.")
            if kind == "player":
                connection.execute("DELETE FROM skills WHERE guild_id=? AND owner_id=?", (guild_id, owner_id))
                connection.execute("DELETE FROM character_profiles WHERE guild_id=? AND user_id=?", (guild_id, owner_id))
            else:
                connection.execute("DELETE FROM enemy_skills WHERE enemy_id=?", (owner_id,))
            for linked in ("combat_statuses", "profile_appearance", "media_upload_jobs"):
                connection.execute(f"DELETE FROM {linked} WHERE guild_id=? AND owner_kind=? AND owner_id=?", (guild_id, kind, owner_id))
            connection.execute(f"DELETE FROM {table} WHERE guild_id=? AND {key}=?", (guild_id, owner_id))
            name = row["name"]
    finally:
        connection.close()
    return {"ok": True, "name": name}


def _image_bytes(image_url: str) -> tuple[bytes, str, str]:
    if image_url.startswith("/uploads/"):
        target = UPLOAD_DIR / Path(image_url).name
        if not target.is_file() or target.parent.resolve() != UPLOAD_DIR.resolve():
            raise ValueError("O arquivo local da imagem não foi encontrado.")
        raw = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return raw, target.name, mime
    try:
        req = urlrequest.Request(image_url, headers={"User-Agent": "ClashRPG-ControlCenter/1.0"})
        with urlrequest.urlopen(req, timeout=20) as response:
            raw = response.read(MAX_UPLOAD_BYTES + 1)
            mime = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError(f"Não foi possível baixar a imagem pública: {error}") from error
    if not mime.startswith("image/"):
        raise ValueError("O endereço informado não retornou uma imagem.")
    extension = mimetypes.guess_extension(mime) or ".png"
    return raw, f"appearance{extension}", mime


def _persist_image_locally(image_url: str) -> str:
    """Mantém a fonte da Central independente de URLs temporárias externas."""
    if not image_url or image_url.startswith("/uploads/"):
        return image_url
    raw, _, mime = _image_bytes(image_url)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("A imagem deve ter no máximo 8 MB.")
    extension = {
        "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(mime)
    if extension is None:
        raise ValueError("A imagem precisa ser PNG, JPG, GIF ou WEBP.")
    UPLOAD_DIR.mkdir(exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    (UPLOAD_DIR / filename).write_bytes(raw)
    return f"/uploads/{filename}"


def _mirror_image_to_discord(image_url: str, payload: dict) -> str:
    config = env_config()
    token = config.get("DISCORD_TOKEN", "")
    channel_id = config.get("APPEARANCE_CHANNEL_ID") or DEFAULT_APPEARANCE_CHANNEL_ID
    if not token:
        raise ValueError("DISCORD_TOKEN não foi encontrado no .env da Central.")
    raw, filename, mime = _image_bytes(image_url)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("A imagem deve ter no máximo 8 MB.")
    boundary = f"----ClashRPG{uuid.uuid4().hex}"
    message = json.dumps({
        "content": (
            f"🖼️ **ARQUIVO DE APARÊNCIA**\n"
            f"Tipo: `{payload.get('kind', 'ficha')}` • Servidor: `{payload.get('guild_id')}` "
            f"• Registro: `{payload.get('owner_id')}`"
        ),
        "attachments": [{"id": 0, "filename": filename}],
    }, ensure_ascii=False)
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
        f"Content-Type: application/json\r\n\r\n{message}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8") + raw + f"\r\n--{boundary}--\r\n".encode("ascii")
    req = urlrequest.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages", data=body, method="POST",
        headers={"Authorization": f"Bot {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise ValueError(f"Discord recusou a imagem ({error.code}): {detail}") from error
    except (URLError, TimeoutError) as error:
        raise ValueError(f"Não foi possível acessar o Discord: {error}") from error
    attachments = result.get("attachments", [])
    if not attachments:
        raise ValueError("O Discord recebeu a mensagem, mas não devolveu o anexo.")
    return str(attachments[0]["url"])


def save_appearance(payload: dict) -> dict:
    image_url = str(payload.get("image_url", "")).strip()
    # Aceita os formatos que o Discord costuma copiar: <url> e [texto](url).
    markdown_link = re.fullmatch(r"\[[^]]*\]\((https?://[^)]+)\)", image_url)
    if markdown_link:
        image_url = markdown_link.group(1)
    image_url = image_url.strip("<> ")
    if image_url and not image_url.startswith(("https://", "http://", "/uploads/")):
        raise ValueError("Use um link direto ou envie uma imagem pela Central.")
    # Links de anexos do Discord são assinados e expiram. A Central sempre
    # converte uma fonte remota em arquivo local antes de persistir a ficha.
    image_url = _persist_image_locally(image_url)
    color = str(payload.get("accent_color", "#b31824"))
    secondary_color = str(payload.get("secondary_color", "#17181a"))
    if not all(re.fullmatch(r"#[0-9a-fA-F]{6}", value) for value in (color, secondary_color)):
        raise ValueError("As cores precisam estar no formato #RRGGBB.")
    database = Database(str(database_path()))
    database.setup()
    try:
        guild_id, kind, owner_id = (
            int(payload["guild_id"]), str(payload["kind"]), int(payload["owner_id"]),
        )
        database.save_appearance(
            guild_id, kind, owner_id, image_url, color, str(payload.get("subtitle", "")),
            secondary_color, str(payload.get("image_mode", "banner")),
            str(payload.get("image_position", "center")), str(payload.get("footer_text", "")),
        )
        job_id = database.queue_media_upload(guild_id, kind, owner_id, image_url) if image_url else None
    finally:
        database.close()
    return {"ok": True, "image_url": image_url, "sync_pending": bool(job_id), "job_id": job_id}


def save_entity_statuses(payload: dict) -> dict:
    guild_id, kind, owner_id = int(payload["guild_id"]), str(payload["kind"]), int(payload["owner_id"])
    if kind not in {"player", "enemy"}:
        raise ValueError("Tipo de ficha inválido.")
    database = Database(str(database_path()))
    database.setup()
    try:
        saved = []
        for item in payload.get("statuses", []):
            status_type = str(item["status_type"])
            private_owner = int(env_config().get("PRIVATE_SKILL_OWNER_ID", "1034518001535430777") or 0)
            if status_type == "devotion_repressed" and (kind != "player" or owner_id != private_owner):
                raise ValueError("Este recurso pertence somente à ficha privada autorizada.")
            if status_type in {"bloodfiend", "bloodbag"}:
                raise ValueError("Bloodfiend e Bloodbag agora devem ser cadastrados como tags do hostil.")
            potency, count = max(0, int(item.get("potency", 0))), int(item.get("count", 0))
            status = database.set_status(guild_id, kind, owner_id, status_type, potency, count)
            saved.append({"status_type": status_type, "potency": status.potency, "count": status.count})
    finally:
        database.close()
    return {"ok": True, "statuses": saved}


def save_enemy_tags(payload: dict) -> dict:
    guild_id, enemy_id = int(payload["guild_id"]), int(payload["owner_id"])
    database = Database(str(database_path()))
    database.setup()
    try:
        tags = database.set_enemy_tags(guild_id, enemy_id, payload.get("tags", []))
    finally:
        database.close()
    return {"ok": True, "tags": tags}


def save_entity_keywords(payload: dict) -> dict:
    """§7.3 — grava as keywords da ficha (quem marca é o mestre, igual equipar)."""
    guild_id, kind, owner_id = int(payload["guild_id"]), str(payload.get("kind", "player")), int(payload["owner_id"])
    keywords = payload.get("keywords", [])
    if not isinstance(keywords, list):
        raise ValueError("Keywords precisam ser uma lista.")
    database = Database(str(database_path()))
    database.setup()
    try:
        saved = database.set_keywords(guild_id, kind, owner_id, keywords)
    finally:
        database.close()
    return {"ok": True, "keywords": sorted(saved)}


def _discord_api_json(path: str, *, method: str = "GET", payload: dict | None = None):
    token = env_config().get("DISCORD_TOKEN", "")
    if not token:
        raise ValueError("DISCORD_TOKEN não foi encontrado no .env.")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urlrequest.Request(
        f"https://discord.com/api/v10{path}", data=data, method=method,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "ClashRPG-ControlCenter/1.0",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise ValueError(f"Discord recusou a operação ({error.code}): {detail}") from error
    except (URLError, TimeoutError) as error:
        raise ValueError(f"Não foi possível acessar o Discord: {error}") from error


def composer_emojis(guild_id: int) -> dict:
    known = db_rows(
        """SELECT 1 FROM guild_registry WHERE guild_id=?
           UNION SELECT 1 FROM characters WHERE guild_id=?
           UNION SELECT 1 FROM enemies WHERE guild_id=? LIMIT 1""",
        (guild_id, guild_id, guild_id),
    )
    if not known:
        raise ValueError("Servidor não registrado no ClashBot.")
    bot = _discord_api_json("/users/@me")
    sources = []
    for path, source in (
        (f"/applications/{bot['id']}/emojis", "application"),
        (f"/guilds/{guild_id}/emojis", "guild"),
    ):
        try:
            result = _discord_api_json(path)
            items = result.get("items", []) if isinstance(result, dict) else result
            for emoji in items:
                if emoji.get("available", True):
                    sources.append({
                        "id": str(emoji["id"]), "name": emoji["name"],
                        "animated": bool(emoji.get("animated")), "source": source,
                        "url": f"https://cdn.discordapp.com/emojis/{emoji['id']}.webp?size=64",
                    })
        except ValueError:
            continue
    unique = {emoji["id"]: emoji for emoji in sources}
    return {"emojis": sorted(unique.values(), key=lambda item: item["name"].casefold())}


def _composer_registered_guilds() -> list[dict]:
    """Servidores conhecidos pela Central, inclusive os que só possuem fichas."""
    return db_rows(
        """SELECT guild_id,MAX(name) AS name FROM (
               SELECT guild_id,name FROM guild_registry
               UNION ALL SELECT guild_id,'' AS name FROM characters
               UNION ALL SELECT guild_id,'' AS name FROM enemies
           ) GROUP BY guild_id ORDER BY name,guild_id"""
    )


def composer_emoji_audit() -> dict:
    """Compara emojis de todos os servidores com os emojis próprios do app."""
    bot = _discord_api_json("/users/@me")
    app_result = _discord_api_json(f"/applications/{bot['id']}/emojis")
    app_emojis = app_result.get("items", []) if isinstance(app_result, dict) else app_result
    app_names = {str(item.get("name", "")).casefold() for item in app_emojis}
    missing_by_name: dict[str, dict] = {}
    unavailable: list[dict] = []
    guilds = _composer_registered_guilds()
    for guild in guilds:
        guild_id = int(guild["guild_id"])
        guild_name = guild.get("name") or f"Servidor {guild_id}"
        try:
            emojis = _discord_api_json(f"/guilds/{guild_id}/emojis")
        except ValueError as error:
            unavailable.append({"guild_id": str(guild_id), "guild_name": guild_name, "error": str(error)})
            continue
        for emoji in emojis:
            name = str(emoji.get("name", "")).strip()
            key = name.casefold()
            if not name or key in app_names:
                continue
            current = missing_by_name.get(key)
            source = {"guild_id": str(guild_id), "guild_name": guild_name}
            if current is not None:
                current["sources"].append(source)
                continue
            animated = bool(emoji.get("animated"))
            emoji_id = str(emoji["id"])
            missing_by_name[key] = {
                "id": emoji_id, "name": name, "animated": animated,
                "url": f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'webp'}?size=96",
                "source_guild_id": str(guild_id), "source_guild_name": guild_name,
                "sources": [source],
            }
    missing = sorted(missing_by_name.values(), key=lambda item: item["name"].casefold())
    return {
        "application_count": len(app_emojis), "guild_count": len(guilds),
        "missing_count": len(missing), "missing": missing, "unavailable": unavailable,
    }


def composer_import_emojis(payload: dict) -> dict:
    """Importa ao app ou servidor apenas IDs que a auditoria atual confirmou como ausentes."""
    selected = {str(value) for value in payload.get("emoji_ids", [])}
    if not selected:
        raise ValueError("Selecione pelo menos um emoji ausente.")
    if len(selected) > 50:
        raise ValueError("Importe no máximo 50 emojis por vez.")
    audit_result = composer_emoji_audit()
    allowed = {item["id"]: item for item in audit_result["missing"]}
    requested = [allowed[emoji_id] for emoji_id in selected if emoji_id in allowed]
    if not requested:
        raise ValueError("Os emojis selecionados não estão mais ausentes.")
    bot = _discord_api_json("/users/@me")
    imported, failed = [], []
    for emoji in requested:
        try:
            raw, _, mime = _image_bytes(emoji["url"])
            if len(raw) > 256 * 1024:
                raise ValueError("arquivo maior que 256 KB")
            safe_name = re.sub(r"[^A-Za-z0-9_]", "_", emoji["name"])[:32].strip("_")
            if len(safe_name) < 2:
                safe_name = f"emoji_{emoji['id'][-8:]}"
            target_mode = str(payload.get("target", "application")).lower()
            target_guild_id = int(payload.get("guild_id", 0))
            if target_mode == "guild" and target_guild_id:
                api_path = f"/guilds/{target_guild_id}/emojis"
            else:
                api_path = f"/applications/{bot['id']}/emojis"
            created = _discord_api_json(
                api_path, method="POST",
                payload={"name": safe_name, "image": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"},
            )
            imported.append({"id": str(created["id"]), "name": created["name"]})
        except (KeyError, ValueError) as error:
            failed.append({"id": emoji["id"], "name": emoji["name"], "error": str(error)})
    return {"ok": not failed, "imported": imported, "failed": failed}


def composer_send(payload: dict) -> dict:
    guild_id, channel_id = int(payload["guild_id"]), str(payload["channel_id"])
    content = str(payload.get("content", "")).strip()
    if not re.fullmatch(r"\d{15,22}", channel_id):
        raise ValueError("ID de canal inválido.")
    if not content or len(content) > 4000:
        raise ValueError("A mensagem precisa ter entre 1 e 4.000 caracteres.")
    channel = _discord_api_json(f"/channels/{channel_id}")
    if int(channel.get("guild_id", 0)) != guild_id:
        raise ValueError("O canal não pertence ao servidor selecionado.")
    # O editor aceita 4k, mas cada mensagem enviada por bot continua limitada a
    # 2k. Divide preferencialmente em uma quebra de linha ou espaço.
    parts: list[str] = []
    remaining = content
    while len(remaining) > 2000:
        candidate = remaining[:2001]
        split_at = max(candidate.rfind("\n"), candidate.rfind(" "))
        if split_at <= 0:
            split_at = 2000
        parts.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        parts.append(remaining)

    results = [
        _discord_api_json(
            f"/channels/{channel_id}/messages", method="POST",
            payload={"content": part, "allowed_mentions": {"parse": []}},
        )
        for part in parts
    ]
    database = Database(str(database_path())); database.setup()
    try:
        with database.lock, database.connection:
            for part, result in zip(parts, results):
                database.connection.execute(
                    """INSERT INTO composer_messages(guild_id,channel_id,channel_name,message_id,content)
                       VALUES(?,?,?,?,?)""",
                    (guild_id, int(channel_id), str(channel.get("name", "")), int(result["id"]), part),
                )
    finally:
        database.close()
    return {
        "ok": True, "message_id": str(results[0]["id"]),
        "message_ids": [str(result["id"]) for result in results],
        "parts": len(results), "channel_id": channel_id,
    }


def composer_messages(guild_id: int | None = None) -> dict:
    database = Database(str(database_path())); database.setup()
    try:
        query = "SELECT * FROM composer_messages"
        params: tuple = ()
        if guild_id:
            query += " WHERE guild_id=?"; params = (guild_id,)
        query += " ORDER BY id DESC LIMIT 100"
        with database.lock:
            rows = [dict(row) for row in database.connection.execute(query, params).fetchall()]
    finally:
        database.close()
    for row in rows:
        for key in ("id", "guild_id", "channel_id", "message_id"):
            row[key] = str(row[key])
    return {"messages": rows}


def composer_edit_message(payload: dict) -> dict:
    record_id = int(payload["id"]); content = str(payload.get("content", "")).strip()
    if not content or len(content) > 2000:
        raise ValueError("A edição precisa ter entre 1 e 2.000 caracteres.")
    database = Database(str(database_path())); database.setup()
    try:
        with database.lock:
            row = database.connection.execute("SELECT * FROM composer_messages WHERE id=? AND status='sent'", (record_id,)).fetchone()
        if row is None: raise ValueError("Mensagem do Composer não encontrada ou já apagada.")
        _discord_api_json(f"/channels/{row['channel_id']}/messages/{row['message_id']}", method="PATCH", payload={"content": content, "allowed_mentions": {"parse": []}})
        with database.lock, database.connection:
            database.connection.execute("UPDATE composer_messages SET content=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (content, record_id))
    finally:
        database.close()
    return {"ok": True, "id": str(record_id), "content": content}


def composer_delete_message(payload: dict) -> dict:
    record_id = int(payload["id"])
    database = Database(str(database_path())); database.setup()
    try:
        with database.lock:
            row = database.connection.execute("SELECT * FROM composer_messages WHERE id=? AND status='sent'", (record_id,)).fetchone()
        if row is None: raise ValueError("Mensagem do Composer não encontrada ou já apagada.")
        _discord_api_json(f"/channels/{row['channel_id']}/messages/{row['message_id']}", method="DELETE")
        with database.lock, database.connection:
            database.connection.execute("UPDATE composer_messages SET status='deleted',deleted_at=CURRENT_TIMESTAMP WHERE id=?", (record_id,))
    finally:
        database.close()
    return {"ok": True, "id": str(record_id)}


def upload_image(payload: dict) -> dict:
    encoded = str(payload.get("data", ""))
    match = re.fullmatch(r"data:(image/(?:png|jpeg|gif|webp));base64,(.+)", encoded, re.DOTALL)
    if not match:
        raise ValueError("Envie uma imagem PNG, JPG, GIF ou WEBP.")
    raw = base64.b64decode(match.group(2), validate=True)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("A imagem deve ter no máximo 8 MB.")
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}[match.group(1)]
    UPLOAD_DIR.mkdir(exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    (UPLOAD_DIR / filename).write_bytes(raw)
    return {"ok": True, "url": f"/uploads/{filename}"}


def create_entity(payload: dict) -> dict:
    kind, guild_id = str(payload.get("kind", "player")), int(payload["guild_id"])
    name = str(payload.get("name", "")).strip()[:50]
    if kind not in {"player", "enemy"} or not name:
        raise ValueError("Tipo ou nome da ficha inválido.")
    sp = max(-45, min(45, int(payload.get("sp", 0))))
    offense, defense = int(payload.get("offense_level", 0)), int(payload.get("defense_level", 0))
    connection = sqlite3.connect(database_path(), timeout=5)
    try:
        with connection:
            if kind == "player":
                owner_id = int(payload["user_id"])
                connection.execute(
                    """INSERT INTO characters
                       (guild_id,user_id,name,sp,offense_level,defense_level,charge_potency_enabled)
                       VALUES(?,?,?,?,?,?,?)""",
                    (guild_id, owner_id, name, sp, offense, defense,
                     1 if payload.get("charge_potency_enabled") else 0),
                )
            else:
                cursor = connection.execute(
                    """INSERT INTO enemies
                       (guild_id,name,sp,offense_level,defense_level,uses_sanity,
                        charge_potency_enabled,created_by)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (guild_id, name, sp, offense, defense,
                     1 if payload.get("uses_sanity", True) else 0,
                     1 if payload.get("charge_potency_enabled") else 0, 0),
                )
                owner_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("Já existe uma ficha com esse usuário ou nome neste servidor.") from error
    finally:
        connection.close()
    return {"ok": True, "kind": kind, "guild_id": str(guild_id), "owner_id": str(owner_id)}


def api_skills(kind: str, owner_id: int, guild_id: int = 0) -> list[dict]:
    if kind == "enemy":
        rows = db_rows("SELECT * FROM enemy_skills WHERE enemy_id=? ORDER BY name", (owner_id,))
    else:
        rows = db_rows(
            "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
            (guild_id, owner_id),
        )
    for row in rows:
        row["effects"] = json.loads(row.pop("effects_json", "[]") or "[]")
        row["coin_layout"] = json.loads(row.pop("coin_layout_json", "[]") or "[]")
    return rows


def save_skill(payload: dict) -> dict:
    kind = payload.get("owner_kind", "player")
    if kind not in {"player", "enemy"}:
        raise ValueError("Tipo de proprietário inválido.")
    owner_id = int(payload["owner_id"])
    guild_id = int(payload.get("guild_id", 0))
    private_owner_id = int(env_config().get("PRIVATE_SKILL_OWNER_ID", "1034518001535430777") or 0)
    private_names = {
        "eu posso ser útil.", "ajoelhe-se.", "aceite minha oferenda.",
        "você não merece esse sangue.",
    }
    requested_name = str(payload.get("name", "")).strip()
    if requested_name.casefold() in private_names and (kind != "player" or owner_id != private_owner_id):
        raise ValueError("Esta skill é privada e só pode ser salva na ficha do proprietário configurado.")
    if kind == "enemy":
        owners = db_rows("SELECT id FROM enemies WHERE id=? AND guild_id=?", (owner_id, guild_id))
    else:
        owners = db_rows(
            "SELECT user_id FROM characters WHERE user_id=? AND guild_id=?",
            (owner_id, guild_id),
        )
    if not owners:
        raise ValueError("A ficha selecionada não existe neste servidor.")
    skill, old_name = parse_skill_payload(payload)
    database = Database(str(database_path()))
    database.setup()
    try:
        if kind == "enemy":
            if old_name and old_name.casefold() != skill.name.casefold():
                database.delete_enemy_skill(owner_id, old_name)
            database.save_enemy_skill(owner_id, skill)
            with database.lock, database.connection:
                database.connection.execute("UPDATE enemy_skills SET skill_slot=? WHERE enemy_id=? AND name=?", (normalize_skill_slot(payload.get("skill_slot"), skill.skill_type), owner_id, skill.name))
        else:
            if old_name and old_name.casefold() != skill.name.casefold():
                database.delete_skill(guild_id, owner_id, old_name)
            database.save_skill(guild_id, owner_id, skill)
            with database.lock, database.connection:
                database.connection.execute("UPDATE skills SET skill_slot=? WHERE guild_id=? AND owner_id=? AND name=?", (normalize_skill_slot(payload.get("skill_slot"), skill.skill_type), guild_id, owner_id, skill.name))
    finally:
        database.close()
    return {"ok": True, "name": skill.name}


def delete_skill(payload: dict) -> dict:
    database = Database(str(database_path()))
    database.setup()
    try:
        if payload.get("owner_kind") == "enemy":
            removed = database.delete_enemy_skill(int(payload["owner_id"]), str(payload["name"]))
        else:
            removed = database.delete_skill(
                int(payload["guild_id"]), int(payload["owner_id"]), str(payload["name"]),
            )
    finally:
        database.close()
    return {"ok": removed}


# Ordem de exibição no editor — Isto NÃO é a lista de conteúdo, é só o
# arranjo visual. Qualquer membro do domínio que não esteja aqui entra
# sozinho, no final, em ordem alfabética.
DISPLAY_TRIGGERS = ["on_use", "on_hit", "heads_hit", "clash_win", "clash_lose", "before_attack", "after_attack", "on_kill", "on_crit", "on_evade"]
DISPLAY_EFFECT_TYPES = ["paralysis", "sp", "base_power", "coin_power", "clash_power", "offense_level", "defense_level", "final_power", "damage_percent", "burn", "bleed", "tremor", "tremor_burst", "amplitude_conversion_scorch", "rupture", "sinking", "poise", "charge", "haste", "special_condition", "make_unbreakable", "consume_special_condition", "consume_bloodfeast", "self_bleed", "consume_devotion_repressed", "reuse_coin", "glimpse_of_precognition", "bloodfeast", "unique_bleed", "unique_bloodfeast"]
DISPLAY_CONDITIONS = ["burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge", "haste", "special_condition", "special_condition_consumed", "bloodfiend_or_bloodbag", "paralysis", "sp", "base_power", "coin_power", "clash_power", "offense_level", "defense_level"]


def _ordered_display(members, preferred: list[str]) -> list[str]:
    """Guarda a ordem combinada e anexa o que for novo, sem perder ninguém."""
    members = set(members)
    ordered = [name for name in preferred if name in members]
    return ordered + sorted(members - set(ordered))


def api_meta_effects() -> dict:
    """Vocabulário do editor de efeitos, derivado do domínio.

    O HTML copiava essas listas à mão e já tinha divergido: faltavam os
    gatilhos ``on_crit``/``on_evade``, os efeitos ``haste``/``reuse_coin`` e
    oito condições — o motor aceitava tudo, só que o mestre não conseguia
    escolher no dropdown. ``conditionOwners``/``conditionValues`` ficam no
    HTML: não têm conjunto equivalente no domínio.
    """
    return {
        "triggers": _ordered_display(EFFECT_TRIGGERS, DISPLAY_TRIGGERS),
        "effectTypes": _ordered_display(EFFECT_TYPES, DISPLAY_EFFECT_TYPES),
        "conditions": [""] + _ordered_display(VALID_CONDITIONS, DISPLAY_CONDITIONS),
    }


def api_battles(guild_id: int | None = None) -> dict:
    where = " AND guild_id=?" if guild_id is not None else ""
    params = (guild_id,) if guild_id is not None else ()
    sessions = db_rows(
        "SELECT * FROM battle_sessions WHERE active=1" + where + " ORDER BY guild_id,channel_id",
        params,
    )
    known = {row["guild_id"]: row["name"] for row in db_rows("SELECT guild_id,name FROM guild_registry")}
    for battle in sessions:
        guild, channel = battle["guild_id"], battle["channel_id"]
        battle["guild_name"] = known.get(guild, f"Servidor {guild}")
        battle["guild_id"] = str(guild)
        battle["channel_id"] = str(channel)
        battle["created_by"] = str(battle["created_by"])
        battle["panel_message_id"] = str(battle["panel_message_id"] or "")
        battle["participants"] = db_rows(
            """SELECT p.*,c.sp,c.offense_level,c.defense_level
               FROM battle_participants p
               LEFT JOIN characters c ON c.guild_id=p.guild_id AND c.user_id=p.user_id
               WHERE p.guild_id=? AND p.channel_id=? ORDER BY p.joined_at,p.user_id""",
            (guild, channel),
        )
        for row in battle["participants"]:
            row["user_id"] = str(row["user_id"])
        battle["field_actions"] = db_rows(
            "SELECT * FROM battle_field_actions WHERE guild_id=? AND channel_id=? ORDER BY id",
            (guild, channel),
        )
        for row in battle["field_actions"]:
            row["claimed_by"] = str(row["claimed_by"] or "")
        battle["player_actions"] = db_rows(
            "SELECT * FROM battle_player_actions WHERE guild_id=? AND channel_id=? ORDER BY id",
            (guild, channel),
        )
        for row in battle["player_actions"]:
            row["user_id"] = str(row["user_id"])
        battle["enemy_free_actions"] = db_rows(
            "SELECT * FROM battle_enemy_free_actions WHERE guild_id=? AND channel_id=? ORDER BY id",
            (guild, channel),
        )
        for row in battle["enemy_free_actions"]:
            row["enemy_id"] = str(row["enemy_id"])
            row["target_user_id"] = str(row["target_user_id"])
            if row.get("enemy_group_member_id") is not None:
                row["enemy_group_member_id"] = str(row["enemy_group_member_id"])
    return {"battles": sessions}


def sentinel_overview() -> dict:
    """Paridade com /sentinela status: saúde dos núcleos sem precisar do Discord."""
    clash_counts = {row["status"]: row["total"] for row in db_rows(
        "SELECT status,COUNT(*) AS total FROM clash_jobs GROUP BY status")}
    outbox_counts = {row["status"]: row["total"] for row in db_rows(
        "SELECT status,COUNT(*) AS total FROM discord_outbox GROUP BY status")}
    last_jobs = db_rows(
        "SELECT id,status,error,updated_at FROM clash_jobs ORDER BY id DESC LIMIT 5")
    for row in last_jobs:
        row["id"] = str(row["id"])
    last_events = db_rows(
        "SELECT id,event_type,status,error,created_at FROM discord_outbox ORDER BY id DESC LIMIT 5")
    for row in last_events:
        row["id"] = str(row["id"])
    last_core = db_rows(
        """SELECT trace_id,command,source,entity_kind,entity_id,version,status,created_at
           FROM core_events ORDER BY id DESC LIMIT 5""")
    encounters = db_rows(
        "SELECT guild_id,channel_id,name,turn,phase FROM battle_sessions WHERE active=1 ORDER BY channel_id LIMIT 10")
    for row in encounters:
        row["guild_id"] = str(row["guild_id"])
        row["channel_id"] = str(row["channel_id"])
    open_actions = db_rows(
        "SELECT COUNT(*) AS total FROM battle_field_actions WHERE status IN ('open','claimed')")
    active_statuses = db_rows(
        "SELECT COUNT(*) AS total FROM combat_statuses WHERE potency>0 OR count>0")
    activity_online = BOT_PROCESS._control("PING") is not None
    try:
        with socket.create_connection(("127.0.0.1", int(env_config().get("ACTIVITY_PORT", "8780") or 8780)), timeout=0.2):
            pass
        # Se o bot responde, a porta da Activity foi testada separadamente abaixo.
        activity_port_open = True
    except OSError:
        activity_port_open = False
    return {
        "bot_online": BOT_PROCESS.running,
        "activity_port_open": activity_port_open,
        "clash_counts": clash_counts, "outbox_counts": outbox_counts,
        "last_jobs": last_jobs, "last_events": last_events,
        "last_core_events": last_core, "encounters": encounters,
        "open_actions": (open_actions[0]["total"] if open_actions else 0),
        "active_statuses": (active_statuses[0]["total"] if active_statuses else 0),
        "_bot_ping": activity_online,
    }


def clash_targets(guild_id: int) -> dict:
    """Alvos do Clash manual: mesma base do /clash e da Activity."""
    players = []
    for row in db_rows(
            "SELECT guild_id,user_id,name,sp,offense_level,defense_level FROM characters WHERE guild_id=? ORDER BY name",
            (guild_id,)):
        skills = db_rows(
            "SELECT name,level_type AS skill_type,base_power,coin_power,coins FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
            (guild_id, row["user_id"]))
        players.append({
            "kind": "player", "id": str(row["user_id"]), "name": row["name"],
            "sp": row["sp"], "skills": skills,
        })
    enemies = []
    for row in db_rows("SELECT id,name,sp FROM enemies WHERE guild_id=? ORDER BY name", (guild_id,)):
        skills = db_rows(
            "SELECT name,skill_type,base_power,coin_power,coins FROM enemy_skills WHERE enemy_id=? ORDER BY name",
            (row["id"],))
        enemies.append({
            "kind": "enemy", "id": str(row["id"]), "name": row["name"],
            "sp": row["sp"], "skills": skills,
        })
    database = Database(str(database_path()))
    database.setup()
    try:
        for group in database.list_enemy_groups(guild_id):
            template_skills = [
                {"name": s.name, "skill_type": s.skill_type,
                 "base_power": s.base_power, "coin_power": s.coin_power, "coins": s.coins}
                for s in database.list_enemy_skills(int(group["template_enemy_id"]))]
            for member in database.list_enemy_group_members(int(group["id"])):
                enemies.append({
                    "kind": "enemy_group_member", "id": f"group:{member['id']}",
                    "member_id": str(member["id"]), "name": member["member_name"],
                    "group_name": group["name"], "sp": member["sp"],
                    "skills": template_skills,
                })
    finally:
        database.close()
    return {"players": players, "enemies": enemies}


def request_clash(payload: dict) -> dict:
    """Enfileira um Clash como a Activity faz: a Central não rola moedas."""
    guild_id, channel_id = int(payload["guild_id"]), int(payload.get("channel_id", 0) or 0)
    user_id = int(payload["user_id"])
    target_kind = str(payload.get("target_kind", ""))
    raw_target = str(payload.get("target_id", ""))
    member_id = 0
    if raw_target.startswith("group:"):
        target_kind = "enemy_group_member"
        member_id = int(raw_target.split(":")[1])
        target_id = member_id
    else:
        target_id = int(raw_target)
    if target_kind not in {"player", "enemy", "enemy_group_member"}:
        raise ValueError("Alvo inválido.")
    left_skill, right_skill = str(payload.get("left_skill", "")), str(payload.get("right_skill", ""))
    if not left_skill:
        raise ValueError("Escolha a skill do atacante.")
    database = Database(str(database_path()))
    database.setup()
    try:
        job_id = database.enqueue_clash_job(guild_id, channel_id, user_id, {
            "guild_id": guild_id, "channel_id": channel_id, "user_id": user_id,
            "target_kind": target_kind, "target_id": target_id,
            "target_enemy_group_member_id": member_id,
            "left_skill": left_skill, "right_skill": right_skill,
            "source": "control_center_manual", "encounter": "", "turn": 0,
        })
    finally:
        database.close()
    BOT_PROCESS._control("OUTBOX_WAKE", timeout=0.5)
    return {"ok": True, "job_id": str(job_id)}


def clash_job_summary(status: str, error: str, result: dict | None) -> str:
    """Resumo em português do job para as visões visuais."""
    if status == "completed" and result:
        winner = str(result.get("winner_name") or "Empate")
        damage = result.get("damage", 0)
        try:
            damage = int(damage)
        except (TypeError, ValueError):
            damage = 0
        forecast = str(result.get("forecast_label_pt") or result.get("forecast_label") or "").strip()
        extra = f" • {forecast}" if forecast else ""
        return f"{winner} venceu • {damage} de dano{extra}"
    if status == "failed":
        return f"Falhou — {(error or 'sem detalhe')[:120]}"
    if status == "cancelled":
        return "Cancelado antes do bot resolver"
    if status == "processing":
        return "O bot está rolando as moedas…"
    return "Na fila, aguardando o bot…"


def clash_job_detail(job_id: int) -> dict:
    rows = db_rows("SELECT * FROM clash_jobs WHERE id=?", (job_id,))
    if not rows:
        raise ValueError("Job não encontrado.")
    job = dict(rows[0])
    for key in ("id", "guild_id", "channel_id", "requester_id"):
        job[key] = str(job[key])
    try:
        job["request"] = json.loads(job.get("request_json") or "{}")
    except json.JSONDecodeError:
        job["request"] = {}
    try:
        job["result"] = json.loads(job.get("result_json") or "{}") if job.get("result_json") else None
    except json.JSONDecodeError:
        job["result"] = None
    job["summary"] = clash_job_summary(job.get("status", ""), job.get("error", ""), job["result"])
    return {"job": job}


def clash_jobs_recent(limit: int = 20) -> dict:
    rows = db_rows(
        "SELECT id,guild_id,channel_id,requester_id,status,error,result_json,created_at,updated_at FROM clash_jobs ORDER BY id DESC LIMIT ?",
        (max(1, min(50, limit)),))
    for row in rows:
        for key in ("id", "guild_id", "channel_id", "requester_id"):
            row[key] = str(row[key])
        try:
            result = json.loads(row.pop("result_json") or "{}") or None
        except json.JSONDecodeError:
            result = None
        row["summary"] = clash_job_summary(row.get("status", ""), row.get("error", ""), result)
        if result:
            row["winner_name"] = str(result.get("winner_name") or "")
            try:
                row["damage"] = int(result.get("damage", 0))
            except (TypeError, ValueError):
                row["damage"] = 0
    return {"jobs": rows}


def api_dashboard() -> dict:
    """Visão Geral viva: contadores, encounters, últimos clashes e atenção."""
    characters = db_rows("SELECT COUNT(*) AS total FROM characters")
    enemies = db_rows("SELECT COUNT(*) AS total FROM enemies")
    battles = db_rows("SELECT COUNT(*) AS total FROM battle_sessions WHERE active=1")
    open_actions = db_rows(
        "SELECT COUNT(*) AS total FROM battle_field_actions WHERE status IN ('open','claimed')")
    known = {row["guild_id"]: row["name"] for row in db_rows("SELECT guild_id,name FROM guild_registry")}
    encounters = db_rows(
        "SELECT guild_id,channel_id,name,turn,phase FROM battle_sessions WHERE active=1 ORDER BY channel_id LIMIT 6")
    for row in encounters:
        row["guild_name"] = known.get(row["guild_id"], f"Servidor {row['guild_id']}")
        row["guild_id"] = str(row["guild_id"])
        row["channel_id"] = str(row["channel_id"])
    recent = db_rows(
        "SELECT id,status,error,result_json,created_at FROM clash_jobs ORDER BY id DESC LIMIT 6")
    recent_jobs = []
    for row in recent:
        try:
            result = json.loads(row.pop("result_json") or "{}") or None
        except json.JSONDecodeError:
            result = None
        recent_jobs.append({
            "id": str(row["id"]), "status": row["status"],
            "summary": clash_job_summary(row["status"], row["error"], result),
            "created_at": row["created_at"],
        })
    failed = db_rows(
        "SELECT id,error,updated_at FROM clash_jobs WHERE status='failed' ORDER BY id DESC LIMIT 3")
    for row in failed:
        row["id"] = str(row["id"])
    failed_mail = db_rows(
        "SELECT id,event_type,error FROM discord_outbox WHERE status='failed' ORDER BY id DESC LIMIT 3")
    for row in failed_mail:
        row["id"] = str(row["id"])
    return {
        "counts": {
            "characters": (characters[0]["total"] if characters else 0),
            "enemies": (enemies[0]["total"] if enemies else 0),
            "battles": (battles[0]["total"] if battles else 0),
            "open_actions": (open_actions[0]["total"] if open_actions else 0),
        },
        "encounters": encounters, "recent_jobs": recent_jobs,
        "failed_jobs": failed, "failed_outbox": failed_mail,
        "bot_online": BOT_PROCESS.running,
    }


def api_profile(guild_id: int, user_id: int) -> dict:
    """Vitais da ficha (HP/Light/Stagger) para edição na Central."""
    rows = db_rows("SELECT name FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    if not rows:
        raise ValueError("Ficha não encontrada.")
    stored = db_rows(
        "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
        (guild_id, user_id))
    try:
        profile = normalize_profile(json.loads(stored[0]["profile_json"])) if stored else default_profile()
    except (TypeError, json.JSONDecodeError):
        profile = default_profile()
    vitals = {key: profile.get(key) for key in (
        "level", "hp", "max_hp", "max_hp_override", "automatic_max_hp",
        "light", "max_light", "stagger", "max_stagger", "sp")}
    return {"name": rows[0]["name"], "vitals": vitals}


def save_profile(payload: dict) -> dict:
    guild_id, user_id = int(payload["guild_id"]), int(payload["user_id"])
    rows = db_rows("SELECT sp FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    if not rows:
        raise ValueError("Ficha não encontrada.")
    stored = db_rows(
        "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
        (guild_id, user_id))
    try:
        previous = json.loads(stored[0]["profile_json"]) if stored else default_profile()
    except (TypeError, json.JSONDecodeError):
        previous = default_profile()
    incoming = dict(previous)
    for key in ("level", "hp", "max_hp_override", "light", "stagger", "sp"):
        if key in payload.get("vitals", {}):
            incoming[key] = payload["vitals"][key]
    profile = normalize_profile_update(incoming, previous)
    database = Database(str(database_path()))
    database.setup()
    try:
        with database.lock, database.connection:
            database.connection.execute(
                """INSERT INTO character_profiles(guild_id,user_id,profile_json,updated_at)
                   VALUES(?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET
                   profile_json=excluded.profile_json,updated_at=CURRENT_TIMESTAMP""",
                (guild_id, user_id, json.dumps(profile, ensure_ascii=False)))
            database.connection.execute(
                "UPDATE characters SET sp=?,offense_level=?,defense_level=? WHERE guild_id=? AND user_id=?",
                (max(-45, min(45, profile["sp"])), profile["offense_level"],
                 profile["defense_level"], guild_id, user_id))
            core = commit_sqlite_event(
                database.connection, guild_id=guild_id, command="profile.save",
                source="control_center", entity_kind="character", entity_id=user_id,
                payload={"hp": profile["hp"], "light": profile["light"],
                         "stagger": profile["stagger"], "level": profile["level"]})
    finally:
        database.close()
    return {"ok": True, "vitals": {key: profile.get(key) for key in (
        "level", "hp", "max_hp", "max_hp_override", "automatic_max_hp",
        "light", "max_light", "stagger", "max_stagger", "sp")}, "core": core}


def bulk_update_entities(payload: dict) -> dict:
    """Ajuste em massa: SP (delta) e/ou Offense/Defense (valor) numa lista de fichas."""
    guild_id = int(payload["guild_id"])
    kind = str(payload.get("kind", "both"))
    ids = [int(value) for value in payload.get("ids", [])]
    if not ids:
        raise ValueError("Selecione ao menos uma ficha.")
    if kind not in {"player", "enemy", "both"}:
        raise ValueError("Tipo inválido.")
    sp_delta = payload.get("sp_delta", 0)
    try:
        sp_delta = int(sp_delta)
    except (TypeError, ValueError):
        sp_delta = 0
    offense = payload.get("offense_level")
    defense = payload.get("defense_level")
    offense = None if offense in (None, "") else int(offense)
    defense = None if defense in (None, "") else int(defense)
    if not sp_delta and offense is None and defense is None:
        raise ValueError("Informe SP, Offense ou Defense para aplicar.")
    updated = 0
    connection = sqlite3.connect(database_path(), timeout=10)
    try:
        with connection:
            if kind in {"player", "both"}:
                sets, params = [], []
                if sp_delta:
                    sets.append("sp=MAX(-45,MIN(45,sp+?))")
                    params.append(sp_delta)
                if offense is not None:
                    sets.append("offense_level=?")
                    params.append(offense)
                if defense is not None:
                    sets.append("defense_level=?")
                    params.append(defense)
                if sets:
                    placeholders = ",".join("?" for _ in ids)
                    cursor = connection.execute(
                        f"UPDATE characters SET {','.join(sets)} WHERE guild_id=? AND user_id IN ({placeholders})",
                        (*params, guild_id, *ids))
                    updated += cursor.rowcount
            if kind in {"enemy", "both"}:
                sets, params = [], []
                if sp_delta:
                    sets.append("sp=MAX(-45,MIN(45,sp+?))")
                    params.append(sp_delta)
                if offense is not None:
                    sets.append("offense_level=?")
                    params.append(offense)
                if defense is not None:
                    sets.append("defense_level=?")
                    params.append(defense)
                if sets:
                    placeholders = ",".join("?" for _ in ids)
                    cursor = connection.execute(
                        f"UPDATE enemies SET {','.join(sets)} WHERE guild_id=? AND id IN ({placeholders})",
                        (*params, guild_id, *ids))
                    updated += cursor.rowcount
    finally:
        connection.close()
    return {"ok": True, "updated": updated}


def duplicate_entity(payload: dict) -> dict:
    """Copia uma ficha (base + skills + status + aparência + perfil) para outro servidor."""
    kind = str(payload.get("kind", "player"))
    source, destination = int(payload["guild_id"]), int(payload["new_guild_id"])
    owner_id = int(payload["owner_id"])
    if source == destination:
        raise ValueError("Escolha um servidor de destino diferente.")
    if kind not in {"player", "enemy"}:
        raise ValueError("Tipo de ficha inválido.")
    new_owner = int(payload.get("new_owner_id", 0) or 0)
    connection = sqlite3.connect(database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            if kind == "player":
                if not new_owner:
                    raise ValueError("Informe o ID do dono no servidor de destino.")
                row = connection.execute(
                    "SELECT * FROM characters WHERE guild_id=? AND user_id=?",
                    (source, owner_id)).fetchone()
                if row is None:
                    raise ValueError("Ficha não encontrada.")
                if connection.execute(
                        "SELECT 1 FROM characters WHERE guild_id=? AND user_id=?",
                        (destination, new_owner)).fetchone():
                    raise ValueError("Este usuário já tem ficha no destino.")
                columns = list(row.keys())
                values = [(destination if key == "guild_id" else
                           new_owner if key == "user_id" else row[key]) for key in columns]
                connection.execute(
                    f"INSERT INTO characters({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                    values)
                for skill in connection.execute(
                        "SELECT * FROM skills WHERE guild_id=? AND owner_id=?",
                        (source, owner_id)).fetchall():
                    skill_columns = [key for key in skill.keys() if key != "id"]
                    skill_values = [(destination if key == "guild_id" else
                                     new_owner if key == "owner_id" else skill[key])
                                    for key in skill_columns]
                    connection.execute(
                        f"INSERT INTO skills({','.join(skill_columns)}) VALUES({','.join('?' for _ in skill_columns)})",
                        skill_values)
                profile = connection.execute(
                    "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
                    (source, owner_id)).fetchone()
                if profile is not None:
                    connection.execute(
                        "INSERT INTO character_profiles(guild_id,user_id,profile_json) VALUES(?,?,?)",
                        (destination, new_owner, profile["profile_json"]))
                owner_key, new_key = "player", new_owner
            else:
                row = connection.execute(
                    "SELECT * FROM enemies WHERE guild_id=? AND id=?",
                    (source, owner_id)).fetchone()
                if row is None:
                    raise ValueError("Hostil não encontrado.")
                if connection.execute(
                        "SELECT 1 FROM enemies WHERE guild_id=? AND name=? COLLATE NOCASE",
                        (destination, row["name"])).fetchone():
                    raise ValueError("Já existe um hostil com este nome no destino.")
                enemy_columns = [key for key in row.keys() if key != "id"]
                enemy_values = [(destination if key == "guild_id" else row[key])
                                for key in enemy_columns]
                cursor = connection.execute(
                    f"INSERT INTO enemies({','.join(enemy_columns)}) VALUES({','.join('?' for _ in enemy_columns)})",
                    enemy_values)
                new_key = cursor.lastrowid
                for skill in connection.execute(
                        "SELECT * FROM enemy_skills WHERE enemy_id=?", (owner_id,)).fetchall():
                    skill_columns = [key for key in skill.keys() if key != "id"]
                    skill_values = [(new_key if key == "enemy_id" else skill[key])
                                    for key in skill_columns]
                    connection.execute(
                        f"INSERT INTO enemy_skills({','.join(skill_columns)}) VALUES({','.join('?' for _ in skill_columns)})",
                        skill_values)
                owner_key = "enemy"
            for table in ("combat_statuses", "profile_appearance"):
                for item in connection.execute(
                        f"SELECT * FROM {table} WHERE guild_id=? AND owner_kind=? AND owner_id=?",
                        (source, kind, owner_id)).fetchall():
                    item_columns = [key for key in item.keys() if key != "id"]
                    item_values = [(destination if key == "guild_id" else
                                    new_key if key == "owner_id" else item[key])
                                   for key in item_columns]
                    connection.execute(
                        f"INSERT INTO {table}({','.join(item_columns)}) VALUES({','.join('?' for _ in item_columns)})",
                        item_values)
            for table, extra in (("passives", {}), ("ego_gifts", {})):
                for item in connection.execute(
                        f"SELECT * FROM {table} WHERE guild_id=? AND owner_kind=? AND owner_id=?",
                        (source, kind, owner_id)).fetchall():
                    item_columns = [key for key in item.keys() if key != "id"]
                    item_values = [(destination if key == "guild_id" else
                                    new_key if key == "owner_id" else item[key])
                                   for key in item_columns]
                    connection.execute(
                        f"INSERT INTO {table}({','.join(item_columns)}) VALUES({','.join('?' for _ in item_columns)})",
                        item_values)
            name = row["name"]
    except sqlite3.IntegrityError as error:
        raise ValueError("Conflito ao duplicar: o destino já tem dados desta ficha.") from error
    finally:
        connection.close()
    return {"ok": True, "kind": kind, "name": name,
            "guild_id": str(destination), "owner_id": str(new_key)}


def api_enemy_groups(guild_id: int) -> dict:
    database = Database(str(database_path()))
    database.setup()
    try:
        groups = []
        for group in database.list_enemy_groups(guild_id):
            members = [dict(m) for m in database.list_enemy_group_members(int(group["id"]))]
            for member in members:
                member["id"] = str(member["id"])
                member["statuses"] = [dict(s) for s in database.list_enemy_group_member_statuses(int(member["id"]))]
            groups.append({
                "id": str(group["id"]), "name": group["name"],
                "template_enemy_id": str(group["template_enemy_id"]),
                "template_name": group["template_name"],
                "member_count": group["member_count"], "members": members,
            })
        return {"groups": groups}
    finally:
        database.close()


def enemy_group_action(payload: dict) -> dict:
    operation = str(payload.get("operation", ""))
    guild_id = int(payload["guild_id"])
    database = Database(str(database_path()))
    database.setup()
    try:
        if operation == "create":
            members = database.create_enemy_group(
                guild_id, int(payload["template_enemy_id"]),
                str(payload.get("name", "Grupo hostil"))[:80],
                int(payload.get("quantity", 1) or 1), int(payload.get("hp_max", 100) or 100))
            return {"ok": True, "members": [dict(m) for m in members]}
        if operation == "add_members":
            members = database.add_enemy_group_members(
                guild_id, int(payload["group_id"]), int(payload.get("quantity", 1) or 1))
            return {"ok": True, "members": [dict(m) for m in members]}
        if operation == "update_member":
            member = database.update_enemy_group_member(
                guild_id, int(payload["member_id"]),
                payload.get("member") if isinstance(payload.get("member"), dict) else {})
            return {"ok": True, "member": dict(member)}
        if operation == "save_statuses":
            statuses = database.save_enemy_group_member_statuses(
                guild_id, int(payload["member_id"]),
                payload.get("statuses") if isinstance(payload.get("statuses"), list) else [])
            return {"ok": True, "statuses": [dict(s) for s in statuses]}
        if operation == "remove_member":
            if not database.remove_enemy_group_member(guild_id, int(payload["member_id"])):
                raise ValueError("Integrante não encontrado.")
            return {"ok": True}
        if operation == "delete_group":
            with database.lock, database.connection:
                cursor = database.connection.execute(
                    "DELETE FROM enemy_groups WHERE guild_id=? AND id=?",
                    (guild_id, int(payload["group_id"])))
                if not cursor.rowcount:
                    raise ValueError("Grupo não encontrado.")
            return {"ok": True}
        raise ValueError("Operação de grupo inválida.")
    finally:
        database.close()


def guild_settings(guild_id: int) -> dict:
    database = Database(str(database_path()))
    database.setup()
    try:
        return {"settings": database.get_guild_settings(guild_id)}
    finally:
        database.close()


def save_guild_settings(payload: dict) -> dict:
    database = Database(str(database_path()))
    database.setup()
    try:
        settings = database.set_guild_settings(
            int(payload["guild_id"]),
            payload.get("settings") if isinstance(payload.get("settings"), dict) else {})
        return {"ok": True, "settings": settings}
    finally:
        database.close()


def battle_control(payload: dict) -> dict:
    operation = str(payload.get("operation", "")).strip()
    guild_id, channel_id = int(payload["guild_id"]), int(payload["channel_id"])
    database = Database(str(database_path()))
    database.setup()
    try:
        battle = database.get_battle(guild_id, channel_id)
        if operation == "start":
            name = str(payload.get("name", "Novo Encontro")).strip()[:80]
            if not name:
                raise ValueError("Informe o nome do encontro.")
            battle = database.start_battle(guild_id, channel_id, name, int(payload.get("created_by", 0)))
            rosemary_id = int(env_config().get("PRIVATE_SKILL_OWNER_ID", "0") or 0)
            if rosemary_id and database.get_character(guild_id, rosemary_id):
                database.start_rosemary_encounter(guild_id, rosemary_id)
        elif operation == "end":
            if not database.end_battle(guild_id, channel_id):
                raise ValueError("Não existe batalha ativa nesse canal.")
            battle = None
        elif battle is None:
            raise ValueError("Não existe batalha ativa nesse canal.")
        elif operation == "advance_phase":
            transitions = {"preparation": "declaration", "declaration": "resolution", "resolution": "complete"}
            next_phase = transitions.get(battle["phase"])
            if next_phase is None:
                raise ValueError("O turno já chegou à fase completa.")
            if battle["phase"] == "preparation" and (
                not database.list_battle_participants(guild_id, channel_id)
                or not database.list_field_actions(guild_id, channel_id)
            ):
                raise ValueError("Adicione ao menos um Sinner e uma ação hostil antes das declarações.")
            if battle["phase"] == "declaration" and database.list_field_actions(guild_id, channel_id, "claimed"):
                raise ValueError("Ainda existe um Clash reivindicado e não resolvido.")
            battle = database.set_battle_phase(guild_id, channel_id, next_phase)
            database.reset_battle_readiness(guild_id, channel_id)
        elif operation == "previous_phase":
            transitions = {"declaration": "preparation", "resolution": "declaration", "complete": "resolution"}
            previous = transitions.get(battle["phase"])
            if previous is None:
                raise ValueError("A batalha já está na preparação.")
            battle = database.set_battle_phase(guild_id, channel_id, previous)
            database.reset_battle_readiness(guild_id, channel_id)
        elif operation == "next_turn":
            if battle["phase"] != "complete":
                raise ValueError("Conclua a fase de resolução antes de avançar o turno.")
            battle = database.next_battle_turn(guild_id, channel_id)
        elif operation == "add_participant":
            user_id = int(payload["user_id"])
            rows = db_rows("SELECT name FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            if not rows:
                raise ValueError("A ficha selecionada não pertence a esse servidor.")
            database.join_battle(guild_id, channel_id, user_id, rows[0]["name"])
        elif operation == "remove_participant":
            if not database.leave_battle(guild_id, channel_id, int(payload["user_id"])):
                raise ValueError("Participante não encontrado.")
        elif operation == "participant_ready":
            database.set_battle_participant_ready(
                guild_id, channel_id, int(payload["user_id"]), bool(payload.get("ready")),
            )
        elif operation == "participant_status":
            database.set_battle_participant_status(
                guild_id, channel_id, int(payload["user_id"]), str(payload["status"]),
            )
        elif operation == "add_field_action":
            if battle["phase"] != "preparation":
                raise ValueError("Ações hostis só podem ser adicionadas na Preparação.")
            enemy_id = int(payload.get("enemy_id", 0) or 0)
            member_id = int(payload.get("enemy_group_member_id", 0) or 0)
            target_user_id = int(payload.get("target_user_id", 0) or 0) or None
            quantity = max(1, min(10, int(payload.get("quantity", 1) or 1)))
            if member_id:
                combatant = database.get_enemy_group_member_combatant(guild_id, member_id)
                if combatant is None or int(combatant["guild_id"]) != guild_id:
                    raise ValueError("Integrante do grupo não encontrado.")
                enemy_name = combatant["name"]
                skill_rows = db_rows("SELECT name FROM enemy_skills WHERE enemy_id=? AND name=?", (int(combatant["id"]), str(payload["skill"])))
            else:
                enemy_rows = db_rows("SELECT name FROM enemies WHERE guild_id=? AND id=?", (guild_id, enemy_id))
                skill_rows = db_rows("SELECT name FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, str(payload["skill"])))
                if not enemy_rows:
                    raise ValueError("Hostil ou skill não foi encontrado nesse servidor.")
                enemy_name = enemy_rows[0]["name"]
            if not skill_rows:
                raise ValueError("Hostil ou skill não foi encontrado nesse servidor.")
            if target_user_id and not database.get_battle_participant(guild_id, channel_id, target_user_id):
                raise ValueError("Escolha um participante do Encounter como alvo.")
            for _ in range(quantity):
                database.add_field_action(guild_id, channel_id, enemy_name, skill_rows[0]["name"], target_user_id, member_id or None)
        elif operation == "add_free_action":
            if battle["phase"] != "preparation":
                raise ValueError("Ataques livres são configurados durante a Preparação.")
            enemy_id = int(payload.get("enemy_id", 0) or 0)
            member_id = int(payload.get("enemy_group_member_id", 0) or 0)
            target_user_id = int(payload.get("target_user_id", 0) or 0)
            variant = str(payload.get("variant", "unopposed"))
            combatant = database.get_enemy_group_member_combatant(guild_id, member_id) if member_id else None
            skill_owner = int(combatant["id"]) if combatant else enemy_id
            skill_rows = db_rows("SELECT name,skill_type FROM enemy_skills WHERE enemy_id=? AND name=?", (skill_owner, str(payload.get("skill", ""))))
            if combatant is None and member_id:
                raise ValueError("Integrante do grupo não encontrado.")
            if not member_id and not db_rows("SELECT 1 FROM enemies WHERE guild_id=? AND id=?", (guild_id, enemy_id)):
                raise ValueError("Hostil não encontrado.")
            if not skill_rows or skill_rows[0]["skill_type"] != "attack":
                raise ValueError("Escolha uma skill de ataque válida.")
            if database.get_battle_participant(guild_id, channel_id, target_user_id) is None:
                raise ValueError("Escolha um participante do Encounter como alvo.")
            database.add_enemy_free_action(guild_id, channel_id, skill_owner, skill_rows[0]["name"], target_user_id, variant, member_id or None)
        elif operation == "remove_free_action":
            connection = sqlite3.connect(database_path(), timeout=5)
            try:
                with connection:
                    cursor = connection.execute(
                        "DELETE FROM battle_enemy_free_actions WHERE id=? AND guild_id=? AND channel_id=?",
                        (int(payload["action_id"]), guild_id, channel_id),
                    )
                    if not cursor.rowcount:
                        raise ValueError("Ataque livre não encontrado.")
            finally:
                connection.close()
        elif operation == "remove_field_action":
            connection = sqlite3.connect(database_path(), timeout=5)
            try:
                with connection:
                    cursor = connection.execute(
                        "DELETE FROM battle_field_actions WHERE id=? AND guild_id=? AND channel_id=?",
                        (int(payload["action_id"]), guild_id, channel_id),
                    )
                    if not cursor.rowcount:
                        raise ValueError("Ação de campo não encontrada.")
            finally:
                connection.close()
        else:
            raise ValueError("Operação de batalha inválida.")
    finally:
        database.close()
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(
            f"[{time.strftime('%d/%m/%Y %H:%M:%S')}] [CENTRAL DE BATALHA] "
            f"operação={operation} | servidor={guild_id} | canal={channel_id}\n"
        )
    sync_reply = BOT_PROCESS._control(f"BATTLE_REFRESH {guild_id} {channel_id}", timeout=1.0)
    return {
        "ok": True, "operation": operation, "battle": dict(battle) if battle else None,
        "discord_sync": sync_reply == "REFRESHING",
    }


def read_logs() -> str:
    persisted = ""
    if AUDIT_PATH.exists():
        with AUDIT_PATH.open("rb") as handle:
            handle.seek(max(0, AUDIT_PATH.stat().st_size - 220_000))
            persisted = handle.read().decode("utf-8", errors="replace")
    live = "\n".join(BOT_PROCESS.output)
    return (persisted + ("\n--- SAÍDA DO PROCESSO ---\n" + live if live else ""))[-240_000:]


LOG_LINE_RE = re.compile(r"^\[(?P<time>[^\]]+)\]\s*\[(?P<tag>[^\]]+)\]\s*(?P<detail>.*)$")

LOG_KIND_BY_TAG = {
    "falha no clash": "erro", "falha ao sincronizar": "erro",
    "clash pelo bot": "clash", "rpg": "clash",
    "central de batalha": "batalha",
    "gif local anexado": "midia", "gif anexado": "midia",
    "gif tenor resolvido": "midia",
    "gif local ausente": "aviso", "rotulo de previsao desconhecido": "aviso",
    "media sincronizada": "midia",
    "online": "sistema", "controle local": "sistema",
}


def _summarize_log(tag: str, detail: str) -> str:
    """Resumo de uma linha para a visão visual de logs."""
    low = tag.casefold()
    clean = detail.strip()
    if low == "clash pelo bot":
        job = re.search(r"job=(\d+)", clean)
        winner = re.search(r"vencedor=([^|]+)", clean)
        damage = re.search(r"dano=(-?\d+)", clean)
        parts = []
        if job:
            parts.append(f"Clash #{job.group(1)}")
        if winner:
            parts.append(f"venceu {winner.group(1).strip()}")
        if damage:
            parts.append(f"({damage.group(1)} de dano)")
        if parts:
            return " ".join(parts)
        return clean[:140]
    if low == "falha no clash":
        job = re.search(r"job=(\d+)", clean)
        error = clean.split("|", 1)[-1].strip() if "|" in clean else clean
        prefix = f"Clash #{job.group(1)} falhou" if job else "Clash falhou"
        return f"{prefix} — {error[:120]}"
    if low == "central de batalha":
        return clean.replace(" | ", " • ")[:140]
    if low in {"gif local anexado", "gif anexado"}:
        name = re.search(r"(?:arquivo=)?([\w\-.]+\.gif)", clean)
        size = re.search(r"(\d+)\s*bytes", clean)
        label = name.group(1) if name else "GIF"
        extra = f" ({int(size.group(1)) // 1024} KB)" if size else ""
        return f"{label}{extra} pronto para o embed"
    if low == "gif tenor resolvido":
        return "GIF do Tenor resolvido para anexo"
    if low == "gif local ausente":
        return f"GIF ausente: {clean[:100]} (caiu no reserva)"
    if low == "rotulo de previsao desconhecido":
        return f"Previsão desconhecida — usou GIF reserva ({clean[:80]})"
    if low == "media sincronizada":
        return clean[:140]
    if low == "falha ao sincronizar":
        return f"Mídia não sincronizou: {clean[:120]}"
    if low == "online":
        servers = re.search(r"servidores=(\d+)", clean)
        return f"Bot online em {servers.group(1)} servidor(es)" if servers else "Bot online"
    if low == "controle local":
        return clean[:140]
    return clean[:140] or tag


def read_logs_parsed(limit: int = 200) -> dict:
    """Logs como entradas estruturadas com resumo, do mais recente ao mais antigo."""
    raw = read_logs()
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        match = LOG_LINE_RE.match(line)
        if not match:
            continue
        tag = match.group("tag").strip()
        detail = match.group("detail").strip()
        low = tag.casefold()
        kind = "info"
        for key, mapped in LOG_KIND_BY_TAG.items():
            if key in low:
                kind = mapped
                break
        entries.append({
            "time": match.group("time").strip(), "tag": tag, "kind": kind,
            "summary": _summarize_log(tag, detail), "detail": detail[:500],
        })
    entries = entries[-max(1, min(500, limit)):][::-1]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return {"entries": entries, "counts": counts, "total": len(entries)}


def read_commands() -> list[dict]:
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    commands = []
    pattern = re.compile(
        r"@(?P<group>[a-zA-Z_][\w.]*)\.command\(name=\"(?P<name>[^\"]+)\",\s*description=\"(?P<description>[^\"]*)\"",
    )
    disabled = set(read_control_state().get("disabled_commands", []))
    for match in pattern.finditer(source):
        group = match.group("group") or "bot.tree"
        clean_group = "" if group == "bot.tree" else group.replace("_group", "")
        qualified = " ".join(filter(None, (clean_group, match.group("name"))))
        commands.append({
            "group": clean_group, "name": match.group("name"),
            "qualified_name": qualified, "enabled": qualified not in disabled,
            "description": match.group("description"),
        })
    return commands


def read_control_state() -> dict:
    if not CONTROL_STATE_PATH.exists():
        return {"disabled_commands": []}
    try:
        return json.loads(CONTROL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"disabled_commands": []}


def set_command_enabled(payload: dict) -> dict:
    qualified = str(payload["qualified_name"]).strip()
    enabled = bool(payload["enabled"])
    state = read_control_state()
    disabled = set(state.get("disabled_commands", []))
    disabled.discard(qualified) if enabled else disabled.add(qualified)
    state["disabled_commands"] = sorted(disabled)
    CONTROL_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "qualified_name": qualified, "enabled": enabled}


def save_config(payload: dict) -> dict:
    current = env_config()
    for key in CONFIG_KEYS:
        if key in payload:
            current[key] = str(payload[key]).replace("\n", "").replace("\r", "")
    lines = [f"{key}={value}" for key, value in current.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "restart_required": BOT_PROCESS.running}


class Handler(BaseHTTPRequestHandler):
    server_version = "ClashControlCenter/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def send_json(self, data, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "")
        if origin in {"http://localhost:5173", "http://127.0.0.1:5173"}:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(raw)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin in {"http://localhost:5173", "http://127.0.0.1:5173"}:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                raw = HTML_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif parsed.path.startswith("/uploads/"):
                filename = Path(parsed.path).name
                target = UPLOAD_DIR / filename
                if not target.is_file() or target.parent.resolve() != UPLOAD_DIR.resolve():
                    self.send_error(404)
                    return
                raw = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(raw)
            elif parsed.path == "/api/status":
                self.send_json(BOT_PROCESS.status())
            elif parsed.path == "/api/revision":
                self.send_json(database_revision())
            elif parsed.path == "/api/ui-assets":
                self.send_json(ui_assets())
            elif parsed.path == "/api/logs":
                self.send_json({"logs": read_logs()})
            elif parsed.path == "/api/logs/parsed":
                self.send_json(read_logs_parsed(int(query.get("limit", ["200"])[0]) if query.get("limit") else 200))
            elif parsed.path == "/api/entities":
                guild = int(query["guild_id"][0]) if query.get("guild_id") else None
                self.send_json(api_entities(guild))
            elif parsed.path == "/api/guild/members":
                self.send_json(guild_members(int(query["guild_id"][0])))
            elif parsed.path in {"/api/rosemary/state", "/api/rosemary/log", "/api/rosemary/snapshot"}:
                guild = int(query["guild_id"][0]) if query.get("guild_id") else None
                owner = int(query["owner_id"][0]) if query.get("owner_id") else None
                limit = max(1, min(100, int(query.get("limit", [12])[0])))
                snapshot = RosemaryPanelRepository(database_path()).snapshot(guild, owner, limit)
                self.send_json(snapshot["state"] if parsed.path.endswith("/state") else snapshot["log"] if parsed.path.endswith("/log") else snapshot)
            elif parsed.path == "/api/entity/detail":
                self.send_json(api_entity_detail(
                    query.get("kind", ["player"])[0], int(query["guild_id"][0]),
                    int(query["owner_id"][0]),
                ))
            elif parsed.path == "/api/skills":
                self.send_json(api_skills(
                    query.get("kind", ["player"])[0], int(query["owner_id"][0]),
                    int(query.get("guild_id", [0])[0]),
                ))
            elif parsed.path == "/api/battles":
                guild = int(query["guild_id"][0]) if query.get("guild_id") else None
                self.send_json(api_battles(guild))
            elif parsed.path == "/api/config":
                config = env_config()
                self.send_json({key: config.get(key, "") for key in CONFIG_KEYS})
            elif parsed.path == "/api/commands":
                self.send_json(read_commands())
            elif parsed.path == "/api/meta/effects":
                self.send_json(api_meta_effects())
            elif parsed.path == "/api/composer/emojis":
                self.send_json(composer_emojis(int(query["guild_id"][0])))
            elif parsed.path == "/api/composer/emoji-audit":
                self.send_json(composer_emoji_audit())
            elif parsed.path == "/api/composer/messages":
                guild = int(query["guild_id"][0]) if query.get("guild_id") else None
                self.send_json(composer_messages(guild))
            elif parsed.path == "/api/sentinel":
                self.send_json(sentinel_overview())
            elif parsed.path == "/api/clash/targets":
                self.send_json(clash_targets(int(query["guild_id"][0])))
            elif parsed.path == "/api/clash/jobs":
                self.send_json(clash_jobs_recent(int(query.get("limit", ["20"])[0]) if query.get("limit") else 20))
            elif parsed.path == "/api/clash/job":
                self.send_json(clash_job_detail(int(query["job_id"][0])))
            elif parsed.path == "/api/enemy-groups":
                self.send_json(api_enemy_groups(int(query["guild_id"][0])))
            elif parsed.path == "/api/guild/settings":
                self.send_json(guild_settings(int(query["guild_id"][0])))
            elif parsed.path == "/api/dashboard":
                self.send_json(api_dashboard())
            elif parsed.path == "/api/profile":
                self.send_json(api_profile(int(query["guild_id"][0]), int(query["user_id"][0])))
            else:
                self.send_json({"error": "Rota não encontrada."}, 404)
        except Exception as error:
            self.send_json({"error": f"{type(error).__name__}: {error}"}, 500)

    def do_POST(self) -> None:
        try:
            payload = self.body()
            routes = {
                "/api/bot/start": BOT_PROCESS.start,
                "/api/bot/stop": BOT_PROCESS.stop,
                "/api/bot/restart": BOT_PROCESS.restart,
                "/api/skills/save": lambda: save_skill(payload),
                "/api/skills/delete": lambda: delete_skill(payload),
                "/api/config/save": lambda: save_config(payload),
                "/api/commands/toggle": lambda: set_command_enabled(payload),
                "/api/entity/save": lambda: save_entity(payload),
                "/api/entity/transfer": lambda: transfer_character(payload),
                "/api/entity/move": lambda: move_entity(payload),
                "/api/entity/delete": lambda: delete_entity(payload),
                "/api/entity/appearance": lambda: save_appearance(payload),
                "/api/entity/statuses": lambda: save_entity_statuses(payload),
                "/api/entity/tags": lambda: save_enemy_tags(payload),
                "/api/entity/keywords": lambda: save_entity_keywords(payload),
                "/api/composer/send": lambda: composer_send(payload),
                "/api/composer/message/edit": lambda: composer_edit_message(payload),
                "/api/composer/message/delete": lambda: composer_delete_message(payload),
                "/api/composer/import-emojis": lambda: composer_import_emojis(payload),
                "/api/battles/action": lambda: battle_control(payload),
                "/api/entity/create": lambda: create_entity(payload),
                "/api/uploads/image": lambda: upload_image(payload),
                "/api/rosemary/content": lambda: save_rosemary_content(payload, database_path()),
                "/api/passives/save": lambda: save_passive(payload),
                "/api/passives/delete": lambda: delete_passive(payload),
                "/api/ego_gifts/save": lambda: save_ego_gift(payload),
                "/api/ego_gifts/delete": lambda: delete_ego_gift(payload),
                "/api/rosemary/state": lambda: save_rosemary_state(payload),
                "/api/clash/request": lambda: request_clash(payload),
                "/api/enemy-groups/action": lambda: enemy_group_action(payload),
                "/api/guild/settings/save": lambda: save_guild_settings(payload),
                "/api/profile/save": lambda: save_profile(payload),
                "/api/entity/bulk": lambda: bulk_update_entities(payload),
                "/api/entity/duplicate": lambda: duplicate_entity(payload),
            }
            action = routes.get(urlparse(self.path).path)
            if action is None:
                self.send_json({"error": "Rota não encontrada."}, 404)
                return
            self.send_json(action())
        except (KeyError, TypeError, ValueError, sqlite3.Error) as error:
            self.send_json({"error": f"{type(error).__name__}: {error}"}, 400)
        except Exception as error:
            self.send_json({"error": f"{type(error).__name__}: {error}"}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Central local do Clash RPG Bot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--start-bot", action="store_true", help="Inicia o bot junto com a Central.")
    args = parser.parse_args()
    database = Database(str(database_path()))
    database.setup()
    database.close()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Central do Clash RPG disponível em {url}")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    if args.start_bot:
        BOT_PROCESS.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        BOT_PROCESS.stop()
        server.server_close()


if __name__ == "__main__":
    main()
