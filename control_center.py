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
from src.domain.combat import Skill, SkillEffect


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
    "defense_level": ("EMOJI_DEFENSE_LEVEL", "🛡️"),
    "make_unbreakable": ("EMOJI_COIN_UNBREAKABLE", "<:MI:1535257836966117376>"),
    "burn": ("EMOJI_STATUS_BURN", "<:EBu:1537502509168459896>"),
    "bleed": ("EMOJI_STATUS_BLEED", "<:EBl:1537502804820623432>"),
    "tremor": ("EMOJI_STATUS_TREMOR", "<:ETr:1537502576860332124>"),
    "rupture": ("EMOJI_STATUS_RUPTURE", "<:ERu:1537502748768075916>"),
    "sinking": ("EMOJI_STATUS_SINKING", "<:ESi:1537502845186875472>"),
    "poise": ("EMOJI_STATUS_POISE", "<:EPo:1537503433651785840>"),
    "charge": ("EMOJI_STATUS_CHARGE", "<:ECh:1537503388906954923>"),
    "special_condition": ("EMOJI_STATUS_SPECIAL_CONDITION", "<:PlH:1538709761757806813>"),
    "devotion_repressed": ("EMOJI_STATUS_DEVOTION_REPRESSED", "🩸"),
    "bloodfiend": ("EMOJI_STATUS_BLOODFIEND", "🧛"),
    "bloodbag": ("EMOJI_STATUS_BLOODBAG", "🩸"),
    "tremor_burst": ("EMOJI_TREMOR_BURST", "<:ETB:1537527981537231009>"),
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
    return {
        "entity": rows[0], "statuses": statuses, "skills": api_skills(kind, owner_id, guild_id),
        "tags": tags,
        "media_sync": media_jobs[0] if media_jobs else None,
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
    return {
        "ok": True, "name": moved["name"],
        "old_owner_id": str(old_owner), "new_owner_id": str(new_owner),
    }


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
    """Importa ao app apenas IDs que a auditoria atual confirmou como ausentes."""
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
            created = _discord_api_json(
                f"/applications/{bot['id']}/emojis", method="POST",
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
    return {
        "ok": True, "message_id": str(results[0]["id"]),
        "message_ids": [str(result["id"]) for result in results],
        "parts": len(results), "channel_id": channel_id,
    }


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
    effects = tuple(SkillEffect(**effect) for effect in payload.get("effects", []))
    coins = int(payload["coins"])
    layout = tuple(payload.get("coin_layout") or ["normal"] * coins)
    skill = Skill(
        str(payload["name"])[:50], int(payload["base_power"]), int(payload["coin_power"]),
        coins, str(payload.get("description", ""))[:300], str(payload.get("skill_type", "attack")),
        layout.count("unbreakable"), effects, layout,
    )
    database = Database(str(database_path()))
    database.setup()
    try:
        old_name = str(payload.get("old_name", "")).strip()
        if kind == "enemy":
            if old_name and old_name.casefold() != skill.name.casefold():
                database.delete_enemy_skill(owner_id, old_name)
            database.save_enemy_skill(owner_id, skill)
        else:
            if old_name and old_name.casefold() != skill.name.casefold():
                database.delete_skill(guild_id, owner_id, old_name)
            database.save_skill(guild_id, owner_id, skill)
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
    return {"battles": sessions}


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
            enemy_id = int(payload["enemy_id"])
            enemy_rows = db_rows("SELECT name FROM enemies WHERE guild_id=? AND id=?", (guild_id, enemy_id))
            skill_rows = db_rows("SELECT name FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, str(payload["skill"])))
            if not enemy_rows or not skill_rows:
                raise ValueError("Hostil ou skill não foi encontrado nesse servidor.")
            database.add_field_action(guild_id, channel_id, enemy_rows[0]["name"], skill_rows[0]["name"])
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
        self.end_headers()
        self.wfile.write(raw)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

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
            elif parsed.path == "/api/entities":
                guild = int(query["guild_id"][0]) if query.get("guild_id") else None
                self.send_json(api_entities(guild))
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
            elif parsed.path == "/api/composer/emojis":
                self.send_json(composer_emojis(int(query["guild_id"][0])))
            elif parsed.path == "/api/composer/emoji-audit":
                self.send_json(composer_emoji_audit())
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
                "/api/entity/appearance": lambda: save_appearance(payload),
                "/api/entity/statuses": lambda: save_entity_statuses(payload),
                "/api/entity/tags": lambda: save_enemy_tags(payload),
                "/api/composer/send": lambda: composer_send(payload),
                "/api/composer/import-emojis": lambda: composer_import_emojis(payload),
                "/api/battles/action": lambda: battle_control(payload),
                "/api/entity/create": lambda: create_entity(payload),
                "/api/uploads/image": lambda: upload_image(payload),
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
    args = parser.parse_args()
    database = Database(str(database_path()))
    database.setup()
    database.close()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Central do Clash RPG disponível em {url}")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        BOT_PROCESS.stop()
        server.server_close()


if __name__ == "__main__":
    main()
