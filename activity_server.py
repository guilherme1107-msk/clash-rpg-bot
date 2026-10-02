"""Servidor público e restrito da Discord Activity.

Este processo não importa nem publica as rotas administrativas da Central.
Cada leitura de ficha é vinculada ao usuário autenticado pelo OAuth2 do Discord.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import socket
import threading
import time
import uuid
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import parse, request
from urllib.error import HTTPError, URLError

from dotenv import dotenv_values
from database import Database
from battle_flow import advance_when_all_ready


def _session_hook(guild_id: int, channel_id: int, trigger: str, turn: int) -> None:
    """Encaminha os gatilhos de sessão para o motor de efeitos do bot.

    Import dentro da função: `bot` importa `activity_server` no topo do arquivo
    dele, então importar aqui criaria ciclo. Só roda quando um gift com
    cláusula de sessão existe de fato.
    """
    from bot import apply_session_trigger  # noqa: PLC0415 - intencional

    apply_session_trigger(guild_id, channel_id, trigger, turn)
from src.domain.combat import Skill, SkillEffect
from src.domain.status import STATUS_TYPES, TREMOR_TYPES
from src.application.services import ability_modifier, default_profile, normalize_profile, normalize_profile_update, normalize_skill_slot, parse_skill_payload
from src.application.services.core_gateway import commit_sqlite_event, review_encounter_command

# O bot é o único executor do combate; a Activity só espera e exibe.
# Antes existia uma cópia local das funções de combate que assumia quando o
# bot não respondia em 300 ms — assim o mesmo comando dava resultados
# diferentes conforme a carga do servidor.
CLASH_RESOLUTION_TIMEOUT = float(os.getenv("ACTIVITY_CLASH_TIMEOUT", "10"))
# Quanto a mais espera cada Clash que está na frente na fila do bot.
CLASH_QUEUE_TIMEOUT = float(os.getenv("ACTIVITY_CLASH_QUEUE_TIMEOUT", "5"))


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
STATIC_DIR = ROOT / "ui" / "discord-activity" / "dist"
UPLOAD_DIR = ROOT / "control_center_uploads"
MAX_BODY_BYTES = 12 * 1024 * 1024
DISCORD_API = "https://discord.com/api/v10"
ACTIVITY_LOCK_SOCKET: socket.socket | None = None
DISCORD_CACHE: dict[tuple[str, str], tuple[float, object]] = {}
DISCORD_CACHE_LOCK = threading.Lock()
DISCORD_CACHE_TTL = 20.0
DISCORD_CACHE_LIMIT = 256

# Chaves configuráveis na Central. A Activity recebe apenas URLs públicas de
# emojis; tokens e mensagens do Discord nunca são expostos ao navegador.
UI_EMOJI_DEFAULTS = {
    "coin_active": ("EMOJI_COIN_ACTIVE", "<:ML:1534094500815831181>"),
    "coin_unbreakable": ("EMOJI_COIN_UNBREAKABLE", "<:MI:1535257836966117376>"),
    "burn": ("EMOJI_STATUS_BURN", "<:Burn:1539383118191140914>"),
    "bleed": ("EMOJI_STATUS_BLEED", "<:Bleed:1539383114957070397>"),
    "tremor": ("EMOJI_STATUS_TREMOR", "<:Tremor:1539383133772714015>"),
    "amplitude_conversion_scorch": ("EMOJI_AMPLITUDE_CONVERSION", "<:Tremor_Conversion:1539383102801969192>"),
    "rupture": ("EMOJI_STATUS_RUPTURE", "<:Rupture:1539383143298240523>"),
    "sinking": ("EMOJI_STATUS_SINKING", "<:Sinking:1539383130371391589>"),
    "poise": ("EMOJI_STATUS_POISE", "<:Poise:1539383124285198337>"),
    "charge": ("EMOJI_STATUS_CHARGE", "<:Charge:1539383121227681942>"),
    # E.G.O Gifts — recurso e variantes únicas (emojis do autor, 2026-10-01).
    "bloodfeast": ("EMOJI_STATUS_BLOODFEAST", "<:Bloodfeast:1539383222566260832>"),
    "unique_bleed": ("EMOJI_STATUS_UNIQUE_BLEED", "<:Efeito_Bleed_Unique:1539412731071955006>"),
    "unique_bloodfeast": ("EMOJI_STATUS_UNIQUE_BLOODFEAST", "<:Bloodfeast:1539383222566260832>"),
    "tremor_scorch": ("EMOJI_STATUS_TREMOR_SCORCH", "<:Tremor_Scorch:1539383164621815968>"),
    "special_condition": ("EMOJI_STATUS_SPECIAL_CONDITION", "<:PlH:1538709761757806813>"),
    "haste": ("EMOJI_STATUS_HASTE", "<:Haste:1539383205575131298>"),
    "paralysis": ("EMOJI_PARALYZE", "<:EP:1534104414183493702>"),
    "base_power": ("EMOJI_ATTACK_UP", "<:EAU:1535263226936295565>"),
    "coin_power": ("EMOJI_PLUS_COIN_BOOST", "<:PCB:1534122027143921766>"),
    "clash_power": ("EMOJI_CLASH_UP", "<:ECU:1534104390896455740>"),
    "offense_level": ("EMOJI_OFFENSE_UP", "<:OLU:1534122107716501534>"),
    "defense_level": ("EMOJI_DEFENSE_LEVEL", "<:Defense_Up:1539383241604210802>"),
}


def config() -> dict[str, str]:
    values = {key: str(value) for key, value in dotenv_values(ENV_PATH).items() if value is not None}
    values.update(os.environ)
    return values


def database_path() -> Path:
    value = config().get("DATABASE_PATH", "clash_rpg.sqlite3")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def activity_status() -> dict:
    settings = config()
    public_url = str(settings.get("ACTIVITY_PUBLIC_URL", "") or settings.get("PUBLIC_ACTIVITY_URL", "")).strip()
    return {
        "ok": True,
        "client_id_configured": bool(settings.get("DISCORD_CLIENT_ID", "").strip()),
        "client_secret_configured": bool(settings.get("DISCORD_CLIENT_SECRET", "").strip()),
        "static_build": STATIC_DIR.joinpath("index.html").is_file(),
        "public_url_configured": bool(public_url),
        "public_url": public_url,
    }


def ensure_profile_table(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS character_profiles (
        guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, profile_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (guild_id, user_id))""")


def discord_json(path: str, access_token: str):
    # A tela abre ficha, Encounter e permissões quase ao mesmo tempo. Evitar
    # repetir /users/@me e /users/@me/guilds deixa a entrada muito mais rápida
    # e reduz a chance de rate limit sem guardar nada em disco.
    cache_key = (access_token, path)
    now = time.monotonic()
    with DISCORD_CACHE_LOCK:
        cached = DISCORD_CACHE.get(cache_key)
        if cached and now - cached[0] < DISCORD_CACHE_TTL:
            return cached[1]
    req = request.Request(
        f"{DISCORD_API}{path}",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": "ClashRPG-Activity/1.0"},
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            with DISCORD_CACHE_LOCK:
                if len(DISCORD_CACHE) >= DISCORD_CACHE_LIMIT:
                    expired = sorted(DISCORD_CACHE, key=lambda key: DISCORD_CACHE[key][0])[:64]
                    for key in expired:
                        DISCORD_CACHE.pop(key, None)
                DISCORD_CACHE[cache_key] = (now, result)
            return result
    except HTTPError as error:
        if error.code in {401, 403}:
            raise PermissionError("Sessão do Discord inválida ou expirada.") from error
        raise RuntimeError(f"Discord respondeu HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Não foi possível validar a sessão com o Discord.") from error


def exchange_code(code: str) -> dict:
    settings = config()
    client_id = settings.get("DISCORD_CLIENT_ID", "")
    client_secret = settings.get("DISCORD_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("Configure DISCORD_CLIENT_ID e DISCORD_CLIENT_SECRET no .env.")
    body = parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
    }).encode("ascii")
    req = request.Request(
        "https://discord.com/api/v10/oauth2/token", data=body, method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "DiscordBot (https://github.com/guilherme1107-msk/clash-rpg-bot, 1.0)",
        },
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        # Discord's OAuth errors do not include secrets. Preserve the useful
        # error code/description so local Activity failures can be diagnosed.
        try:
            details = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            details = {}
        oauth_error = str(details.get("error", "oauth_error"))
        description = str(details.get("error_description", "Código de autorização recusado."))
        print(f"OAuth Discord: {oauth_error} — {description}")
        raise PermissionError(f"Discord OAuth: {oauth_error} — {description}") from error
    token = result.get("access_token")
    if not token:
        raise PermissionError("O Discord não devolveu um token de acesso.")
    return {"access_token": token}


def _skill_payload(row) -> dict:
    if isinstance(row, Skill):
        base, coin, coins = row.base_power, row.coin_power, row.coins
        low, high = sorted((base, base + coin * coins))
        effects = []
        for eff in row.effects:
            if isinstance(eff, SkillEffect):
                effects.append({
                    "trigger": eff.trigger,
                    "effect_type": eff.effect_type,
                    "value": eff.value,
                    "potency": eff.value,
                    "count": eff.count,
                    "coin": eff.coin,
                    "charge_cost": eff.charge_cost,
                    "condition_status": eff.condition_status,
                    "condition_min": eff.condition_min,
                    "condition_owner": eff.condition_owner,
                    "condition_value": eff.condition_value,
                    "condition_per": eff.condition_per,
                    "condition_max_stacks": eff.condition_max_stacks,
                    "consume_condition": eff.consume_condition,
                    "effect_owner": eff.effect_owner,
                    "condition_operator": eff.condition_operator,
                })
            elif isinstance(eff, dict):
                effects.append(eff)
        effects = [item for item in effects if item.get("effect_type") != "consume_devotion_repressed"]
        return {
            "name": row.name, "base_power": base, "coin_power": coin, "coins": coins,
            "description": row.description, "skill_type": row.skill_type,
            "skill_slot": getattr(row, "skill_slot", ""),
            "coin_layout": list(row.coin_layout), "effects": effects, "minimum": low, "maximum": high,
        }
    base, coin, coins = row["base_power"], row["coin_power"], row["coins"]
    type_column = "level_type" if "level_type" in row.keys() else "skill_type"
    low, high = sorted((base, base + coin * coins))
    try:
        layout = json.loads(row["coin_layout_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        layout = []
    try:
        effects = json.loads(row["effects_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        effects = []
    effects = [item for item in effects if isinstance(item, dict) and item.get("effect_type") != "consume_devotion_repressed"]
    return {
        "name": row["name"], "base_power": base, "coin_power": coin, "coins": coins,
        "description": row["description"], "skill_type": row[type_column],
        "skill_slot": row["skill_slot"] if "skill_slot" in row.keys() else "",
        "coin_layout": layout, "effects": effects, "minimum": low, "maximum": high,
    }


def activity_ui_assets() -> dict:
    settings = config()
    assets = {}
    for key, (env_key, fallback) in UI_EMOJI_DEFAULTS.items():
        match = re.fullmatch(r"<(a?):[A-Za-z0-9_]+:(\d+)>", settings.get(env_key, fallback))
        if match:
            animated, emoji_id = match.groups()
            assets[key] = {"url": f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'webp'}?size=64&quality=lossless"}
    # Catálogo extensível: EMOJI_EFFECT_FALSE_HUNGER gera a chave false_hunger.
    for env_key, emoji in settings.items():
        if not env_key.startswith("EMOJI_EFFECT_"):
            continue
        match = re.fullmatch(r"<(a?):[A-Za-z0-9_]+:(\d+)>", emoji)
        if match:
            animated, emoji_id = match.groups()
            key = env_key.removeprefix("EMOJI_EFFECT_").lower()
            assets[key] = {"url": f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'webp'}?size=64&quality=lossless"}
    for key, env_key in {"clash_damage_gif":"DAMAGE_RESOLUTION_GIF", "clash_unbreakable_gif":"UNBREAKABLE_FOLLOWUP_GIF"}.items():
        url = settings.get(env_key, "").strip()
        if url.startswith(("https://cdn.discordapp.com/", "https://media.discordapp.net/")):
            assets[key] = {"url":url}
    return assets


def is_activity_admin(user_id: int, guilds: list[dict], guild_id: int) -> bool:
    configured = {item.strip() for item in config().get("ACTIVITY_ADMIN_USER_IDS", "").split(",") if item.strip()}
    if str(user_id) in configured:
        return True
    member = next((item for item in guilds if str(item.get("id")) == str(guild_id)), None)
    return bool(member and (bool(member.get("owner")) or (int(member.get("permissions", "0")) & 0x8)))


def own_sheet(access_token: str, requested_guild_id: str | None) -> dict:
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    guild_id = int(requested_guild_id) if requested_guild_id else None
    guilds = []
    if guild_id is not None:
        guilds = discord_json("/users/@me/guilds", access_token)
        if str(guild_id) not in {str(item["id"]) for item in guilds}:
            raise PermissionError("Você não pertence a este servidor.")

    connection = sqlite3.connect(database_path(), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        ensure_profile_table(connection)
        if guild_id is None:
            character = connection.execute(
                "SELECT * FROM characters WHERE user_id=? ORDER BY guild_id LIMIT 1", (user_id,),
            ).fetchone()
        else:
            character = connection.execute(
                "SELECT * FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id),
            ).fetchone()
        if character is None:
            return {"user": user, "character": None, "message": "Você ainda não possui ficha neste servidor."}
        guild_id = int(character["guild_id"])
        appearance = connection.execute(
            """SELECT image_url,accent_color,subtitle,secondary_color,image_mode,
                      image_position,footer_text FROM profile_appearance
               WHERE guild_id=? AND owner_kind='player' AND owner_id=?""",
            (guild_id, user_id),
        ).fetchone()
        statuses = connection.execute(
            """SELECT status_type,potency,count,tremor_type FROM combat_statuses
               WHERE guild_id=? AND owner_kind='player' AND owner_id=? AND count>0
                 AND status_type<>'devotion_repressed'
               ORDER BY status_type""",
            (guild_id, user_id),
        ).fetchall()
        skills = connection.execute(
            "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
            (guild_id, user_id),
        ).fetchall()
        profile_row = connection.execute("SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
        try: profile = normalize_profile(json.loads(profile_row["profile_json"])) if profile_row else normalize_profile({})
        except (TypeError, json.JSONDecodeError): profile = normalize_profile({})
        public_character_keys = (
            "name", "sp", "offense_level", "defense_level", "paralysis",
            "base_power_mod", "coin_power_mod", "clash_power_mod",
            "offense_level_mod", "defense_level_mod", "charge_potency_enabled", "charge_spent",
        )
        return {
            "user": {key: user.get(key) for key in ("id", "username", "global_name", "avatar")},
            "guild_id": str(guild_id),
            "character": {key: character[key] for key in public_character_keys},
            "appearance": dict(appearance) if appearance else {},
            "statuses": [dict(row) for row in statuses],
            "skills": [_skill_payload(row) for row in skills],
            "ui_assets": activity_ui_assets(),
            "profile": profile,
            "is_master": is_activity_admin(user_id, guilds, guild_id),
        }
    finally:
        connection.close()


def save_own_profile(access_token: str, requested_guild_id: str | None, raw_profile: object) -> dict:
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor da ficha inválido.")
    guild_id = int(requested_guild_id)
    guilds = discord_json("/users/@me/guilds", access_token)
    if str(guild_id) not in {str(item["id"]) for item in guilds}:
        raise PermissionError("Você não pertence a este servidor.")
    connection = sqlite3.connect(database_path(), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        ensure_profile_table(connection)
        exists = connection.execute("SELECT sp FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
        if not exists: raise PermissionError("Você não possui ficha neste servidor.")
        stored = connection.execute(
            "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ).fetchone()
        try:
            previous_profile = json.loads(stored["profile_json"]) if stored else default_profile()
        except (TypeError, ValueError, json.JSONDecodeError):
            previous_profile = default_profile()
        incoming = dict(raw_profile) if isinstance(raw_profile, dict) else {}
        update_combat_sp = bool(incoming.pop("_update_combat_sp", False))
        if not update_combat_sp:
            incoming["sp"] = int(exists["sp"])
        profile = normalize_profile_update(incoming, previous_profile)
        with connection:
            connection.execute("""INSERT INTO character_profiles(guild_id,user_id,profile_json,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id,user_id) DO UPDATE SET profile_json=excluded.profile_json,updated_at=CURRENT_TIMESTAMP""", (guild_id, user_id, json.dumps(profile, ensure_ascii=False)))
            connection.execute(
                "UPDATE characters SET sp=?,offense_level=?,defense_level=? WHERE guild_id=? AND user_id=?",
                (max(-45, min(45, profile["sp"])), profile["offense_level"], profile["defense_level"], guild_id, user_id),
            )
            core_commit = commit_sqlite_event(
                connection, guild_id=guild_id, command="profile.save", source="activity",
                entity_kind="character", entity_id=user_id,
                payload={"sp": profile["sp"], "level": profile["level"], "light": profile["light"], "hp": profile["hp"]},
            )
    finally:
        connection.close()
    return {"ok": True, "profile": profile, "core": core_commit}


def save_own_statuses(access_token: str, requested_guild_id: object, statuses: object) -> dict:
    user = discord_json("/users/@me", access_token); user_id = int(user["id"])
    if not requested_guild_id or not str(requested_guild_id).isdigit(): raise ValueError("Servidor da ficha inválido.")
    guild_id = int(requested_guild_id)
    if not isinstance(statuses, list) or len(statuses) > 30: raise ValueError("Lista de efeitos inválida.")
    database = Database(str(database_path())); database.setup()
    try:
        if database.get_character(guild_id, user_id) is None: raise PermissionError("Você não possui ficha neste servidor.")
        merged: dict[str, tuple[int, int]] = {}
        requested_tremor = None
        for item in statuses:
            if not isinstance(item, dict):
                raise ValueError("Cada efeito precisa ter tipo, Potência e Quantidade.")
            kind = re.sub(r"[^a-z0-9_]", "", str(item.get("status_type", "")).lower())[:40]
            if kind not in STATUS_TYPES:
                raise ValueError("Escolha um efeito válido do ClashBot.")
            if kind == "devotion_repressed":
                # É privado e controlado pelo sistema, não pelo editor comum.
                continue
            if kind == "tremor":
                raw_tremor = str(item.get("tremor_type", "") or "")
                if raw_tremor in TREMOR_TYPES:
                    requested_tremor = raw_tremor
            potency, count = max(0, int(item.get("potency", 0))), max(0, int(item.get("count", 0)))
            if count:
                old_potency, old_count = merged.get(kind, (0, 0))
                merged[kind] = (old_potency + potency, old_count + count)
        with database.lock, database.connection:
            # O editor não conhece Amplitude Conversion: o Tremor já convertido
            # só muda se o cliente enviar outro tipo válido.
            stored = database.connection.execute(
                "SELECT tremor_type FROM combat_statuses WHERE guild_id=? AND owner_kind='player' AND owner_id=? AND status_type='tremor'",
                (guild_id, user_id),
            ).fetchone()
            preserved_tremor = stored["tremor_type"] if stored else "normal"
            database.connection.execute("DELETE FROM combat_statuses WHERE guild_id=? AND owner_kind='player' AND owner_id=? AND status_type<>'devotion_repressed'", (guild_id,user_id))
            for kind, (potency, count) in merged.items():
                tremor_type = (
                    (requested_tremor if requested_tremor is not None else preserved_tremor)
                    if kind == "tremor" else "normal"
                )
                database.connection.execute(
                    "INSERT INTO combat_statuses(guild_id,owner_kind,owner_id,status_type,potency,count,tremor_type) VALUES(?,?,?,?,?,?,?)",
                    (guild_id, "player", user_id, kind, potency, count, tremor_type),
                )
        return {"ok":True}
    finally: database.close()


def skill_from_payload(payload: object) -> tuple[Skill, str]:
    # Adaptador temporário mantido para compatibilidade com testes e rotas.
    return parse_skill_payload(payload)


def _legacy_skill_from_payload(payload: object) -> tuple[Skill, str]:
    if not isinstance(payload, dict):
        raise ValueError("Skill inválida.")
    name = str(payload.get("name", "")).strip()
    coins = int(payload.get("coins", 0))
    if not name or len(name) > 50 or not 1 <= coins <= 10:
        raise ValueError("Nome (até 50 caracteres) e 1–10 moedas são obrigatórios.")
    effects_raw = payload.get("effects", [])
    if not isinstance(effects_raw, list) or len(effects_raw) > 20:
        raise ValueError("Uma skill pode ter no máximo 20 efeitos.")
    allowed_effect_keys = {"trigger", "effect_type", "value", "coin", "count", "charge_cost", "condition_status", "condition_min", "condition_owner", "condition_value", "condition_per", "condition_max_stacks", "consume_condition"}
    effects = []
    for item in effects_raw:
        if not isinstance(item, dict):
            raise ValueError("Efeito inválido.")
        clean = {key: item[key] for key in allowed_effect_keys if key in item}
        if not str(clean.get("effect_type", "")).strip() or not str(clean.get("trigger", "")).strip():
            raise ValueError("Todo efeito precisa de gatilho e tipo.")
        clean["value"] = float(clean.get("value", 0))
        for key in ("coin", "count"):
            clean[key] = None if clean.get(key) in {None, ""} else int(clean[key])
        if clean["effect_type"] not in {"burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge", "haste", "special_condition", "self_bleed"}:
            clean["count"] = None
        for key in ("charge_cost", "condition_min", "condition_per", "condition_max_stacks"):
            clean[key] = int(clean.get(key, 0) or 0)
        clean["consume_condition"] = bool(clean.get("consume_condition", False))
        effects.append(SkillEffect(**clean))
    layout = payload.get("coin_layout", ["normal"] * coins)
    if not isinstance(layout, list) or len(layout) != coins or any(item not in {"normal", "unbreakable"} for item in layout):
        raise ValueError("Layout de moedas inválido.")
    skill = Skill(name, max(-99, min(99, int(payload.get("base_power", 0)))), max(-99, min(99, int(payload.get("coin_power", 0)))), coins, str(payload.get("description", ""))[:300], str(payload.get("skill_type", "attack"))[:20], layout.count("unbreakable"), tuple(effects), tuple(layout))
    return skill, str(payload.get("old_name", "")).strip()


def save_own_skill(access_token: str, requested_guild_id: str | None, payload: object) -> dict:
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor da ficha inválido.")
    guild_id = int(requested_guild_id)
    guilds = discord_json("/users/@me/guilds", access_token)
    if str(guild_id) not in {str(item["id"]) for item in guilds}:
        raise PermissionError("Você não pertence a este servidor.")
    skill, old_name = skill_from_payload(payload)
    database = Database(str(database_path()))
    database.setup()
    try:
        if database.get_character(guild_id, user_id) is None:
            raise PermissionError("Você não possui ficha neste servidor.")
        if old_name and old_name.casefold() != skill.name.casefold():
            database.delete_skill(guild_id, user_id, old_name)
        database.save_skill(guild_id, user_id, skill)
        slot = normalize_skill_slot(payload.get("skill_slot") if isinstance(payload, dict) else "", skill.skill_type)
        with database.lock, database.connection:
            database.connection.execute("UPDATE skills SET skill_slot=? WHERE guild_id=? AND owner_id=? AND name=?", (slot, guild_id, user_id, skill.name))
    finally:
        database.close()
    return {"ok": True, "name": skill.name}


def delete_own_skill(access_token: str, requested_guild_id: str | None, name: object) -> dict:
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor da ficha inválido.")
    guild_id = int(requested_guild_id)
    guilds = discord_json("/users/@me/guilds", access_token)
    if str(guild_id) not in {str(item["id"]) for item in guilds}:
        raise PermissionError("Você não pertence a este servidor.")
    database = Database(str(database_path()))
    database.setup()
    try:
        if database.get_character(guild_id, user_id) is None:
            raise PermissionError("Você não possui ficha neste servidor.")
        removed = database.delete_skill(guild_id, user_id, str(name)[:50])
    finally:
        database.close()
    return {"ok": removed}


def admin_overview(access_token: str, requested_guild_id: str | None) -> dict:
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor inválido.")
    guild_id = int(requested_guild_id)
    guilds = discord_json("/users/@me/guilds", access_token)
    if not is_activity_admin(int(discord_json("/users/@me", access_token)["id"]), guilds, guild_id):
        raise PermissionError("Apenas administradores do servidor podem abrir esta visão.")
    connection = sqlite3.connect(database_path(), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("""SELECT c.name,c.user_id,c.sp,c.offense_level,c.defense_level,
            (SELECT COUNT(*) FROM skills s WHERE s.guild_id=c.guild_id AND s.owner_id=c.user_id) AS skills
            FROM characters c WHERE c.guild_id=? ORDER BY c.name""", (guild_id,)).fetchall()
        enemies = connection.execute("""SELECT e.id,e.name,e.sp,e.offense_level,e.defense_level,
            (SELECT COUNT(*) FROM enemy_skills s WHERE s.enemy_id=e.id) AS skills
            FROM enemies e WHERE e.guild_id=? ORDER BY e.name""", (guild_id,)).fetchall()
        battles = connection.execute("SELECT channel_id,name,turn,phase FROM battle_sessions WHERE guild_id=? AND active=1 ORDER BY channel_id", (guild_id,)).fetchall()
        characters = [dict(row) for row in rows]
        hostile_rows = [dict(row) for row in enemies]
        battle_rows = [dict(row) for row in battles]
        groups = connection.execute(
            """SELECT g.id,g.name,e.name AS template_name,COUNT(m.id) AS members
               FROM enemy_groups g JOIN enemies e ON e.id=g.template_enemy_id
               LEFT JOIN enemy_group_members m ON m.group_id=g.id
               WHERE g.guild_id=? GROUP BY g.id ORDER BY g.name""", (guild_id,),
        ).fetchall()
        group_rows = [dict(row) for row in groups]
        for item in characters:
            item["user_id"] = str(item["user_id"])
        for item in hostile_rows:
            item["id"] = str(item["id"])
        for item in battle_rows:
            item["channel_id"] = str(item["channel_id"])
        for item in group_rows:
            item["id"] = str(item["id"])
        db = Database(str(database_path())); db.setup()
        try: settings = db.get_guild_settings(guild_id)
        finally: db.close()
        return {"characters": characters, "enemies": hostile_rows, "groups": group_rows, "battles": battle_rows, "settings": settings}
    finally:
        connection.close()


def save_admin_settings(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict): raise ValueError("Configurações inválidas.")
    _, guild_id = require_activity_admin(access_token, payload.get("guild_id"))
    database = Database(str(database_path())); database.setup()
    try:
        settings = database.set_guild_settings(guild_id, payload.get("settings") if isinstance(payload.get("settings"), dict) else {})
        return {"ok": True, "settings": settings}
    finally:
        database.close()


def require_activity_admin(access_token: str, requested_guild_id: object) -> tuple[int, int]:
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor inválido.")
    guild_id = int(requested_guild_id)
    user = discord_json("/users/@me", access_token)
    guilds = discord_json("/users/@me/guilds", access_token)
    if not is_activity_admin(int(user["id"]), guilds, guild_id):
        raise PermissionError("Apenas administradores podem realizar esta ação.")
    return int(user["id"]), guild_id


def admin_entity_detail(access_token: str, requested_guild_id: object, kind: object, owner_id: object) -> dict:
    _, guild_id = require_activity_admin(access_token, requested_guild_id)
    kind = str(kind)
    if kind not in {"player", "enemy"}: raise ValueError("Tipo de ficha inválido.")
    table, key = ("enemies", "id") if kind == "enemy" else ("characters", "user_id")
    connection = sqlite3.connect(database_path(), timeout=5); connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(f"SELECT * FROM {table} WHERE guild_id=? AND {key}=?", (guild_id, int(owner_id))).fetchone()
        if row is None: raise ValueError("Ficha não encontrada.")
        statuses = connection.execute("SELECT status_type,potency,count,tremor_type FROM combat_statuses WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type<>'devotion_repressed' ORDER BY status_type", (guild_id, kind, int(owner_id))).fetchall()
        if kind == "enemy":
            skills = connection.execute("SELECT * FROM enemy_skills WHERE enemy_id=? ORDER BY name", (int(owner_id),)).fetchall()
        else:
            skills = connection.execute("SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name", (guild_id, int(owner_id))).fetchall()
        entity = dict(row)
        entity[key] = str(entity[key])
        appearance = connection.execute("SELECT image_url,accent_color,subtitle FROM profile_appearance WHERE guild_id=? AND owner_kind=? AND owner_id=?", (guild_id, kind, int(owner_id))).fetchone()
        return {"entity": entity, "statuses":[dict(item) for item in statuses], "skills":[_skill_payload(item) for item in skills], "appearance":dict(appearance) if appearance else {}, "ui_assets":activity_ui_assets()}
    finally: connection.close()


def save_admin_image(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Imagem inválida.")
    _, guild_id = require_activity_admin(access_token, payload.get("guild_id"))
    owner_kind, owner_id = str(payload.get("owner_kind", "")), int(payload.get("owner_id", 0))
    if owner_kind not in {"enemy", "enemy_group"} or owner_id <= 0:
        raise ValueError("Destino da imagem inválido.")
    data = str(payload.get("data", ""))
    matched = re.fullmatch(r"data:(image/(?:png|jpeg|gif|webp));base64,([A-Za-z0-9+/=\s]+)", data)
    if not matched:
        raise ValueError("Cole uma imagem PNG, JPG, GIF ou WEBP.")
    raw = base64.b64decode(matched.group(2), validate=False)
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError("A imagem deve ter no máximo 8 MB.")
    extension = {"image/png":".png", "image/jpeg":".jpg", "image/gif":".gif", "image/webp":".webp"}[matched.group(1)]
    database = Database(str(database_path())); database.setup()
    try:
        if owner_kind == "enemy":
            exists = database.connection.execute("SELECT 1 FROM enemies WHERE guild_id=? AND id=?", (guild_id, owner_id)).fetchone()
        else:
            exists = database.connection.execute("SELECT 1 FROM enemy_groups WHERE guild_id=? AND id=?", (guild_id, owner_id)).fetchone()
        if not exists: raise ValueError("Ficha não encontrada.")
        UPLOAD_DIR.mkdir(exist_ok=True)
        filename = f"{uuid.uuid4().hex}{extension}"
        (UPLOAD_DIR / filename).write_bytes(raw)
        image_url = f"/uploads/{filename}"
        current = database.get_appearance(guild_id, owner_kind, owner_id)
        database.save_appearance(guild_id, owner_kind, owner_id, image_url, current["accent_color"] if current else "#b31824", current["subtitle"] if current else "")
        database.queue_media_upload(guild_id, owner_kind, owner_id, image_url)
        return {"ok": True, "image_url": image_url}
    finally:
        database.close()


def save_admin_entity(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict): raise ValueError("Dados inválidos.")
    _, guild_id = require_activity_admin(access_token, payload.get("guild_id"))
    kind, owner_id = str(payload.get("kind")), int(payload.get("owner_id", 0))
    if kind not in {"player", "enemy"}: raise ValueError("Tipo de ficha inválido.")
    table, key = ("enemies", "id") if kind == "enemy" else ("characters", "user_id")
    name = str(payload.get("name", "")).strip()[:50]
    if not name: raise ValueError("A ficha precisa de um nome.")
    sp = max(-45, min(45, int(payload.get("sp", 0))))
    connection = sqlite3.connect(database_path(), timeout=5)
    try:
        with connection:
            cursor = connection.execute(
                f"""UPDATE {table} SET name=?,sp=?,offense_level=?,defense_level=?,paralysis=?,
                    base_power_mod=?,coin_power_mod=?,clash_power_mod=?,offense_level_mod=?,defense_level_mod=?
                    WHERE guild_id=? AND {key}=?""",
                (name, sp, int(payload.get("offense_level", 0)), int(payload.get("defense_level", 0)),
                 max(0, int(payload.get("paralysis", 0))), int(payload.get("base_power_mod", 0)),
                 int(payload.get("coin_power_mod", 0)), int(payload.get("clash_power_mod", 0)),
                 int(payload.get("offense_level_mod", 0)), int(payload.get("defense_level_mod", 0)),
                 guild_id, owner_id),
            )
            if not cursor.rowcount: raise ValueError("Ficha não encontrada.")
            statuses = payload.get("statuses", [])
            if not isinstance(statuses, list) or len(statuses) > 30: raise ValueError("Lista de status inválida.")
            # O editor não conhece Amplitude Conversion: o Tremor já convertido
            # só muda se o cliente enviar outro tipo válido.
            stored = connection.execute(
                "SELECT tremor_type FROM combat_statuses WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type='tremor'",
                (guild_id, kind, owner_id),
            ).fetchone()
            preserved_tremor = stored["tremor_type"] if stored else "normal"
            requested_tremor = None
            connection.execute("DELETE FROM combat_statuses WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type<>'devotion_repressed'", (guild_id, kind, owner_id))
            for item in statuses:
                status_type = re.sub(r"[^a-z0-9_]", "", str(item.get("status_type", "")).lower())[:40]
                if status_type == "tremor":
                    raw_tremor = str(item.get("tremor_type", "") or "")
                    if raw_tremor in TREMOR_TYPES:
                        requested_tremor = raw_tremor
                potency, count = max(0, int(item.get("potency", 0))), max(0, int(item.get("count", 0)))
                if status_type and status_type != "devotion_repressed" and count:
                    tremor_type = (
                        (requested_tremor if requested_tremor is not None else preserved_tremor)
                        if status_type == "tremor" else "normal"
                    )
                    connection.execute("INSERT INTO combat_statuses(guild_id,owner_kind,owner_id,status_type,potency,count,tremor_type) VALUES(?,?,?,?,?,?,?)", (guild_id, kind, owner_id, status_type, potency, count, tremor_type))
    finally: connection.close()
    return {"ok":True}


def admin_skill_action(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Dados inválidos.")
    _, guild_id = require_activity_admin(access_token, payload.get("guild_id"))
    kind = str(payload.get("kind", ""))
    owner_id = int(payload.get("owner_id", 0))
    if kind not in {"player", "enemy"} or owner_id <= 0:
        raise ValueError("Dono da Skill inválido.")
    database = Database(str(database_path()))
    database.setup()
    try:
        exists = database.connection.execute(
            "SELECT 1 FROM enemies WHERE guild_id=? AND id=?" if kind == "enemy" else "SELECT 1 FROM characters WHERE guild_id=? AND user_id=?",
            (guild_id, owner_id),
        ).fetchone()
        if not exists:
            raise ValueError("Ficha não encontrada.")
        operation = str(payload.get("operation", "save"))
        if operation == "delete":
            name = str(payload.get("name", ""))[:50]
            removed = database.delete_enemy_skill(owner_id, name) if kind == "enemy" else database.delete_skill(guild_id, owner_id, name)
            return {"ok": bool(removed)}
        if operation != "save":
            raise ValueError("Ação de Skill inválida.")
        skill, old_name = skill_from_payload(payload.get("skill"))
        if old_name and old_name.casefold() != skill.name.casefold():
            if kind == "enemy":
                database.delete_enemy_skill(owner_id, old_name)
            else:
                database.delete_skill(guild_id, owner_id, old_name)
        if kind == "enemy":
            database.save_enemy_skill(owner_id, skill)
            table, where, params = "enemy_skills", "enemy_id=? AND name=?", (owner_id, skill.name)
        else:
            database.save_skill(guild_id, owner_id, skill)
            table, where, params = "skills", "guild_id=? AND owner_id=? AND name=?", (guild_id, owner_id, skill.name)
        slot = normalize_skill_slot((payload.get("skill") or {}).get("skill_slot"), skill.skill_type)
        with database.lock, database.connection:
            database.connection.execute(f"UPDATE {table} SET skill_slot=? WHERE {where}", (slot, *params))
        return {"ok": True, "name": skill.name}
    finally:
        database.close()


def admin_enemy_action(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict): raise ValueError("Dados inválidos.")
    user_id, guild_id = require_activity_admin(access_token, payload.get("guild_id"))
    operation = str(payload.get("operation", ""))
    database = Database(str(database_path())); database.setup()
    try:
        if operation == "create":
            name = str(payload.get("name", "Novo Hostil")).strip()[:50]
            with database.connection:
                cursor = database.connection.execute("INSERT INTO enemies(guild_id,name,sp,offense_level,defense_level,uses_sanity,created_by) VALUES(?,?,?,?,?,?,?)", (guild_id, name, 0, 3, 3, 1, user_id))
            return {"ok":True, "id":str(cursor.lastrowid)}
        if operation == "delete":
            enemy_id = int(payload.get("owner_id", 0))
            row = database.connection.execute("SELECT name FROM enemies WHERE guild_id=? AND id=?", (guild_id, enemy_id)).fetchone()
            if not row: raise ValueError("Hostil não encontrado.")
            database.delete_enemy(guild_id, row["name"])
            return {"ok":True}
        if operation == "create_group":
            template_enemy_id = int(payload.get("template_enemy_id", 0))
            name = str(payload.get("name", "Grupo hostil")).strip()[:80]
            if not name: raise ValueError("Dê um nome ao grupo.")
            members = database.create_enemy_group(
                guild_id, template_enemy_id, name,
                int(payload.get("quantity", 1) or 1), int(payload.get("hp_max", 100) or 100),
            )
            return {"ok":True,"members":[dict(member) for member in members]}
        if operation == "group_detail":
            group = database.get_enemy_group(guild_id, int(payload.get("group_id", 0)))
            if group is None: raise ValueError("Grupo não encontrado.")
            group_data = dict(group)
            appearance = database.get_appearance(guild_id, "enemy_group", int(group["id"])) or database.get_appearance(guild_id, "enemy", int(group["template_enemy_id"]))
            skills = database.list_enemy_skills(int(group["template_enemy_id"]))
            members = [{**dict(member), "statuses":[dict(status) for status in database.list_enemy_group_member_statuses(int(member["id"]))]} for member in database.list_enemy_group_members(int(group["id"]))]
            return {"ok":True,"group":group_data,"members":members,"appearance":dict(appearance) if appearance else {},"skills":[_skill_payload(item) for item in skills],"ui_assets":activity_ui_assets()}
        if operation == "group_add_members":
            members = database.add_enemy_group_members(guild_id, int(payload.get("group_id", 0)), int(payload.get("quantity", 1) or 1))
            return {"ok":True,"members":[dict(member) for member in members]}
        if operation == "group_update_member":
            member = database.update_enemy_group_member(guild_id, int(payload.get("member_id", 0)), payload.get("member") if isinstance(payload.get("member"), dict) else {})
            return {"ok":True,"member":dict(member)}
        if operation == "group_save_statuses":
            statuses = database.save_enemy_group_member_statuses(guild_id, int(payload.get("member_id", 0)), payload.get("statuses") if isinstance(payload.get("statuses"), list) else [])
            return {"ok":True,"statuses":[dict(status) for status in statuses]}
        if operation == "group_remove_member":
            if not database.remove_enemy_group_member(guild_id, int(payload.get("member_id", 0))): raise ValueError("Integrante não encontrado.")
            return {"ok":True}
        raise ValueError("Ação de hostil inválida.")
    finally: database.close()


def admin_battle_action(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict): raise ValueError("Dados inválidos.")
    user_id, guild_id = require_activity_admin(access_token, payload.get("guild_id"))
    operation, channel_id = str(payload.get("operation", "")), int(payload.get("channel_id", 0))
    if channel_id <= 0: raise ValueError("Informe o ID do canal da batalha.")
    database = Database(str(database_path())); database.setup()
    try:
        battle = database.get_battle(guild_id, channel_id)
        if operation == "start": battle = database.start_battle(guild_id, channel_id, str(payload.get("name", "Novo Encontro"))[:80], user_id)
        elif battle is None: raise ValueError("Não existe batalha ativa neste canal.")
        elif operation == "end": database.end_battle(guild_id, channel_id); battle = None
        elif operation == "next_turn": battle = database.next_battle_turn(guild_id, channel_id)
        elif operation in {"advance", "previous"}:
            transitions = ({"preparation":"declaration","declaration":"resolution","resolution":"complete"} if operation == "advance" else {"declaration":"preparation","resolution":"declaration","complete":"resolution"})
            phase = transitions.get(battle["phase"])
            if phase is None: raise ValueError("Não há fase disponível nesta direção.")
            battle = database.set_battle_phase(guild_id, channel_id, phase)
        else: raise ValueError("Ação de batalha inválida.")
        return {"ok":True,"battle":dict(battle) if battle else None}
    finally: database.close()


def activity_combat_targets(access_token: str, requested_guild_id: str | None) -> dict:
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor inválido.")
    guild_id = int(requested_guild_id)
    guilds = discord_json("/users/@me/guilds", access_token)
    if str(guild_id) not in {str(item.get("id")) for item in guilds}:
        raise PermissionError("Você não pertence a este servidor.")
    connection = sqlite3.connect(database_path(), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("SELECT 1 FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone() is None:
            raise PermissionError("Você não possui ficha neste servidor.")
        targets = []
        for row in connection.execute("SELECT id,name,sp,offense_level,defense_level FROM enemies WHERE guild_id=? ORDER BY name", (guild_id,)):
            skills = connection.execute("SELECT * FROM enemy_skills WHERE enemy_id=? ORDER BY name", (row["id"],)).fetchall()
            targets.append({"kind":"enemy", "id":str(row["id"]), "name":row["name"], "sp":row["sp"], "offense":row["offense_level"], "defense":row["defense_level"], "skills":[_skill_payload(skill) for skill in skills]})
        for row in connection.execute("SELECT user_id,name,sp,offense_level,defense_level FROM characters WHERE guild_id=? AND user_id<>? ORDER BY name", (guild_id, user_id)):
            skills = connection.execute("SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name", (guild_id, row["user_id"])).fetchall()
            targets.append({"kind":"player", "id":str(row["user_id"]), "name":row["name"], "sp":row["sp"], "offense":row["offense_level"], "defense":row["defense_level"], "skills":[_skill_payload(skill) for skill in skills]})
        return {"targets":targets}
    finally:
        connection.close()


def _clashes_ahead(job_id: int) -> int:
    """Quantos Clashes estão na frente deste job na fila do bot.

    O bot resolve um Clash por vez, então quem chega depois espera mais.
    Jobs parados há mais de uma hora não contam: são órfãos de uma queda
    do bot, não fila de verdade.
    """
    watcher = Database(str(database_path())); watcher.setup()
    try:
        row = watcher.connection.execute(
            "SELECT COUNT(*) AS ahead FROM clash_jobs "
            "WHERE id < ? AND status IN ('pending','processing') "
            "AND updated_at >= datetime('now', '-1 hour')",
            (job_id,),
        ).fetchone()
        return int(row["ahead"]) if row else 0
    finally:
        watcher.close()


def request_bot_clash(access_token: str, requested_guild_id: str | None, payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Clash inválido.")
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    guild_id = int(requested_guild_id or 0)
    guilds = discord_json("/users/@me/guilds", access_token)
    if not guild_id or str(guild_id) not in {str(item.get("id")) for item in guilds}:
        raise PermissionError("Servidor inválido para o Clash.")
    raw_target_id = str(payload.get("target_id", "0"))
    if raw_target_id.startswith("group:"):
        target_kind = "enemy_group_member"
        target_id = int(raw_target_id.replace("group:", ""))
        member_id = target_id
    else:
        target_kind = str(payload.get("target_kind", ""))
        target_id = int(raw_target_id.split(":")[-1] if ":" in raw_target_id else (raw_target_id if raw_target_id.isdigit() else 0))
        member_id = int(payload.get("target_enemy_group_member_id", 0) or 0)
        if member_id:
            target_kind = "enemy_group_member"
    if target_kind not in {"player", "enemy", "enemy_group_member"}:
        raise ValueError("Alvo inválido.")
    channel_id = int(payload.get("channel_id", 0) or 0)
    database = Database(str(database_path())); database.setup()
    if not channel_id:
        settings = database.get_guild_settings(guild_id)
        channel_id = int(settings.get("audit_channel_id", "0") or "0")
    request_data = {
        "guild_id": guild_id, "channel_id": channel_id, "user_id": user_id,
        "target_kind": target_kind, "target_id": target_id,
        "target_enemy_group_member_id": member_id if target_kind == "enemy_group_member" else int(payload.get("target_enemy_group_member_id", 0) or 0),
        "left_skill": str(payload.get("left_skill", "")),
        "right_skill": str(payload.get("right_skill", "")),
        "actor_enemy_id": int(payload.get("actor_enemy_id", 0) or 0),
        "actor_enemy_group_member_id": int(payload.get("actor_enemy_group_member_id", 0) or 0),
        "enemy_skill": str(payload.get("enemy_skill", "")),
        "source": str(payload.get("source", "free_clash")),
        "encounter": str(payload.get("encounter", "")), "turn": int(payload.get("turn", 0) or 0),
    }
    try:
        job_id = database.enqueue_clash_job(guild_id, channel_id, user_id, request_data)
    finally:
        database.close()
    notify_bot_outbox()
    ahead = _clashes_ahead(job_id)
    timeout = min(CLASH_RESOLUTION_TIMEOUT + CLASH_QUEUE_TIMEOUT * ahead, 60.0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        watcher = Database(str(database_path())); watcher.setup()
        try:
            job = watcher.get_clash_job(job_id)
            if job and job["status"] == "completed":
                return json.loads(job["result_json"] or "{}")
            if job and job["status"] in {"failed", "cancelled"}:
                raise ValueError(job["error"] or "O bot não conseguiu resolver este Clash.")
        finally:
            watcher.close()
        time.sleep(0.05)

    # Tempo esgotado. A Activity NÃO resolve combate por conta própria: quem
    # calcula é o bot, a Activity só exibe. Se o job ainda estiver pendente ele
    # é cancelado, para o bot não processá-lo depois (isso duplicaria o
    # resultado — antes a Activity executava uma cópia própria da função).
    watcher = Database(str(database_path())); watcher.setup()
    try:
        if watcher.cancel_clash_job(job_id):
            raise ValueError(
                "O bot não respondeu a tempo. Ele é quem resolve o combate; "
                "tente novamente em instantes."
            )
        job = watcher.get_clash_job(job_id)
        if job and job["status"] == "completed":
            return json.loads(job["result_json"] or "{}")
        if job and job["status"] in {"failed", "cancelled"}:
            raise ValueError(job["error"] or "O bot não conseguiu resolver este Clash.")
    finally:
        watcher.close()
    raise ValueError(
        "O bot assumiu este combate mas demorou mais que o esperado. "
        "O resultado será publicado no canal; atualize a tela em instantes."
    )


def encounter_overview(access_token: str, requested_guild_id: object, requested_channel_id: object = None) -> dict:
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    if not requested_guild_id or not str(requested_guild_id).isdigit():
        raise ValueError("Servidor inválido.")
    guild_id = int(requested_guild_id)
    guilds = discord_json("/users/@me/guilds", access_token)
    if str(guild_id) not in {str(item.get("id")) for item in guilds}:
        raise PermissionError("Você não pertence a este servidor.")
    is_master = is_activity_admin(user_id, guilds, guild_id)
    database = Database(str(database_path())); database.setup()
    try:
        character = database.get_character(guild_id, user_id)
        battles = database.connection.execute(
            "SELECT * FROM battle_sessions WHERE guild_id=? AND active=1 ORDER BY channel_id", (guild_id,),
        ).fetchall()
        if requested_channel_id and str(requested_channel_id).isdigit():
            battles = [row for row in battles if int(row["channel_id"]) == int(requested_channel_id)]
        encounters = []
        for battle in battles:
            channel_id = int(battle["channel_id"])
            participants = [dict(row) for row in database.list_battle_participants(guild_id, channel_id)]
            for item in participants:
                item["user_id"] = str(item["user_id"])
                item["is_self"] = item["user_id"] == str(user_id)
                item["ready"] = bool(item["ready"])
                item_skills = database.list_skills(guild_id, int(item["user_id"]))
                item["skills"] = [_skill_payload(s) for s in item_skills]
            actions = [dict(row) for row in database.list_field_actions(guild_id, channel_id)]
            for item in actions:
                item["id"] = str(item["id"])
                item["claimed_by"] = str(item["claimed_by"]) if item["claimed_by"] is not None else None
                item["target_user_id"] = str(item["target_user_id"]) if item.get("target_user_id") is not None else None
            player_actions = [dict(row) for row in database.list_player_actions(guild_id, channel_id)]
            for item in player_actions:
                item["id"] = str(item["id"]); item["user_id"] = str(item["user_id"])
            enemy_free_actions = [dict(row) for row in database.list_enemy_free_actions(guild_id, channel_id)]
            for item in enemy_free_actions:
                item["id"] = str(item["id"]); item["enemy_id"] = str(item["enemy_id"]); item["target_user_id"] = str(item["target_user_id"])
                item["enemy_group_member_id"] = str(item["enemy_group_member_id"]) if item.get("enemy_group_member_id") is not None else None
            info = dict(battle)
            info["channel_id"] = str(info["channel_id"])
            info["panel_message_id"] = str(info["panel_message_id"]) if info.get("panel_message_id") else None
            encounters.append({
                **info, "participants": participants, "actions": actions, "player_actions": player_actions, "enemy_free_actions": enemy_free_actions,
                "joined": any(item["is_self"] for item in participants),
            })
        enemies = []
        for enemy in database.list_enemies(guild_id):
            statuses = database.list_statuses(guild_id, "enemy", int(enemy["id"]))
            enemies.append({
                "id":str(enemy["id"]), "name":enemy["name"], "kind":"enemy", "template_enemy_id":str(enemy["id"]),
                "skills":[{"name":skill.name,"type":skill.skill_type} for skill in database.list_enemy_skills(enemy["id"])] if is_master else [],
                "statuses":[{"status_type":status.status_type,"potency":status.potency,"count":status.count,"tremor_type":status.tremor_type} for status in statuses if status.potency or status.count],
            })
        # Grupo não é um único alvo: cada integrante aparece como hostil próprio.
        for group in database.list_enemy_groups(guild_id):
            template_id = int(group["template_enemy_id"])
            skills_for_template = database.list_enemy_skills(template_id)
            for member in database.list_enemy_group_members(int(group["id"])):
                member_statuses = database.list_enemy_group_member_statuses(int(member["id"]))
                enemies.append({
                    "id": f"group:{member['id']}", "name": member["member_name"],
                    "kind": "enemy_group_member", "template_enemy_id": str(template_id),
                    "group_id": str(group["id"]), "group_name": group["name"],
                    "sp": int(member["sp"]), "hp": int(member["hp"]), "hp_max": int(member["hp_max"]),
                    "skills": [{"name": skill.name, "type": skill.skill_type} for skill in skills_for_template] if is_master else [],
                    "statuses": [{"status_type": status["status_type"], "potency": status["potency"], "count": status["count"], "tremor_type": status["tremor_type"]} for status in member_statuses if status["potency"] or status["count"]],
                })
        skills = [] if character is None else [_skill_payload(row) for row in database.connection.execute(
            "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name", (guild_id, user_id),
        ).fetchall()]
        return {"is_master":is_master, "character":dict(character) if character else None, "skills":skills, "enemies":enemies, "encounters":encounters}
    finally:
        database.close()


def notify_bot_outbox() -> None:
    """Acorda o publicador do bot; a fila no banco garante a entrega posterior."""
    port = int(config().get("BOT_INSTANCE_LOCK_PORT", "47653") or 47653)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.35) as connection:
            connection.sendall(b"OUTBOX_WAKE")
            connection.recv(64)
    except OSError:
        # O Encounter continua salvo; o painel do Discord poderá ser atualizado
        # manualmente quando o bot voltar.
        pass


def encounter_changed(guild_id: int, channel_id: int, result: dict) -> dict:
    # O painel do Encounter pertence exclusivamente à Activity. Mudanças ficam
    # no banco e a própria interface recarrega o estado.
    return result


def encounter_action(access_token: str, payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Ação de Encounter inválida.")
    user = discord_json("/users/@me", access_token)
    user_id = int(user["id"])
    guild_id = int(payload.get("guild_id", 0)); channel_id = int(payload.get("channel_id", 0))
    guilds = discord_json("/users/@me/guilds", access_token)
    if not guild_id or not channel_id or str(guild_id) not in {str(item.get("id")) for item in guilds}:
        raise PermissionError("Encounter inválido para este servidor.")
    operation = str(payload.get("operation", ""))
    unopposed = False
    action_id = 0
    action = None
    target_id = 0
    enemy = None
    player_skill = ""
    database = Database(str(database_path())); database.setup()
    try:
        battle = database.get_battle(guild_id, channel_id)
        if battle is None: raise ValueError("Este Encounter não está mais ativo.")
        character = database.get_character(guild_id, user_id)
        if operation == "join":
            if character is None: raise PermissionError("Crie sua ficha antes de entrar no Encounter.")
            database.join_battle(guild_id, channel_id, user_id, character["name"])
            return encounter_changed(guild_id, channel_id, {"ok":True})
        if operation == "leave":
            if battle["phase"] != "preparation": raise ValueError("Só é possível sair durante a Preparação.")
            database.leave_battle(guild_id, channel_id, user_id)
            return encounter_changed(guild_id, channel_id, {"ok":True})
        participant = database.get_battle_participant(guild_id, channel_id, user_id)
        if operation == "ready":
            if participant is None: raise PermissionError("Entre no Encounter antes de confirmar.")
            if battle["phase"] == "complete":
                raise ValueError("A rodada foi concluída. O mestre deve usar Próximo turno para continuar.")
            if battle["phase"] == "declaration" and participant["status"] == "clashing":
                raise ValueError("Conclua o Clash reservado antes de confirmar.")
            ready = not bool(participant["ready"])
            database.set_battle_participant_ready(guild_id, channel_id, user_id, ready)
            # Os gatilhos `session_*` dos E.G.O Gifts (Etapa 4) moram no objeto
            # `Database`, e a Activity cria o seu próprio — então, sem isto, o
            # gift dispararia pelo processo do bot e morreria aqui, que é onde o
            # encontro realmente anda. Import preguiçoso de propósito: no topo
            # criaria ciclo, e a Activity não calcula combate (P1.3) — só
            # reaproveita o motor de efeitos.
            database.session_hook = _session_hook
            advanced, message = advance_when_all_ready(database, guild_id, channel_id)
            return encounter_changed(guild_id, channel_id, {"ok":True,"ready":ready,"advanced":advanced,"message":message})
        if operation == "unopposed":
            if battle["phase"] != "declaration" or participant is None:
                raise PermissionError("Entre no Encounter e aguarde a fase de Declaração.")
            player_skill = str(payload.get("player_skill", "")); _raw_eid = str(payload.get("enemy_id", 0) or 0); target_id = int(_raw_eid.split(":")[-1] if ":" in _raw_eid else _raw_eid); member_id = int(payload.get("enemy_group_member_id", 0) or 0)
            skill = database.get_skill(guild_id, user_id, player_skill); enemy = database.get_enemy_group_member_combatant(guild_id, member_id) if member_id else database.get_enemy_by_id(target_id)
            if skill is None or skill.skill_type != "attack": raise ValueError("Escolha uma Skill de ataque para a ação sem oposição.")
            if enemy is None or int(enemy["guild_id"]) != guild_id: raise ValueError("Alvo hostil inválido.")
            if member_id:
                target_id = member_id
            database.set_battle_participant_status(guild_id, channel_id, user_id, "clashing")
            unopposed = True
        elif operation == "resolve":
            if battle["phase"] != "declaration" or participant is None:
                raise PermissionError("Entre no Encounter e aguarde a fase de Declaração.")
            action_id = int(payload.get("action_id", 0)); player_skill = str(payload.get("player_skill", ""))
            action = database.get_field_action(action_id)
            skill = database.get_skill(guild_id, user_id, player_skill)
            member_id = int(action["enemy_group_member_id"] or 0) if action is not None else 0
            enemy = None if action is None else (database.get_enemy_group_member_combatant(guild_id, member_id) if member_id else database.get_enemy(guild_id, action["enemy_name"]))
            enemy_skill = None if enemy is None or action is None else database.get_enemy_skill(enemy["id"], action["enemy_skill"])
            if action is None or int(action["guild_id"]) != guild_id or int(action["channel_id"]) != channel_id or action["status"] != "open":
                raise ValueError("A ação hostil já foi reservada ou não existe.")
            if skill is None or enemy_skill is None: raise ValueError("Uma das Skills não está mais disponível.")
            if not database.claim_field_action(action_id, user_id, skill.name): raise ValueError("Outro jogador reservou esta ação primeiro.")
            database.set_battle_participant_status(guild_id, channel_id, user_id, "clashing")
            target_id = member_id or int(enemy["id"])
        else:
            if not is_activity_admin(user_id, guilds, guild_id): raise PermissionError("Apenas o mestre pode controlar esta etapa.")
            if operation == "add_action":
                if battle["phase"] != "preparation": raise ValueError("Ações hostis são adicionadas durante a Preparação.")
                enemy_id = int(payload.get("enemy_id", 0)); member_id = int(payload.get("enemy_group_member_id", 0) or 0); target_user_id = int(payload.get("target_user_id", 0)); skill_name = str(payload.get("enemy_skill", ""))
                enemy = database.get_enemy_group_member_combatant(guild_id, member_id) if member_id else database.get_enemy_by_id(enemy_id)
                skill = database.get_enemy_skill(int(enemy["id"]), skill_name) if enemy is not None else None
                if enemy is None or int(enemy["guild_id"]) != guild_id or skill is None: raise ValueError("Hostil ou Skill inválida.")
                if skill.skill_type != "attack": raise ValueError("Ações no campo aceitam apenas Skills de ataque.")
                if not target_user_id:
                    participants = database.list_battle_participants(guild_id, channel_id)
                    target_user_id = int(participants[0]["user_id"]) if participants else 0
                if database.get_battle_participant(guild_id, channel_id, target_user_id) is None: raise ValueError("Escolha um participante do Encounter como alvo.")
                review = review_encounter_command("encounter.hostile_action_queued", enemy_id=enemy_id, skill_name=skill.name, target_user_id=target_user_id)
                quantity = max(1, min(10, int(payload.get("quantity", 1) or 1)))
                rows = [database.add_field_action(guild_id, channel_id, enemy["name"], skill.name, target_user_id, member_id or None) for _ in range(quantity)]
                with database.lock, database.connection:
                    core = commit_sqlite_event(database.connection, guild_id=guild_id, command=review["command"], source="activity", entity_kind="encounter", entity_id=channel_id, payload={**review, "action_ids":[int(row["id"]) for row in rows]})
                return encounter_changed(guild_id, channel_id, {"ok":True,"action_id":str(rows[0]["id"]),"quantity":quantity,"core":core})
            if operation == "add_enemy_free_attack":
                if battle["phase"] != "preparation": raise ValueError("Ataques livres do hostil são configurados durante a Preparação.")
                enemy_id, member_id, target_user_id = int(payload.get("enemy_id", 0)), int(payload.get("enemy_group_member_id", 0) or 0), int(payload.get("target_user_id", 0))
                skill_name, variant = str(payload.get("enemy_skill", "")), str(payload.get("variant", "unopposed"))
                enemy = database.get_enemy_group_member_combatant(guild_id, member_id) if member_id else database.get_enemy_by_id(enemy_id)
                skill = database.get_enemy_skill(int(enemy["id"]), skill_name) if enemy is not None else None
                target = database.get_battle_participant(guild_id, channel_id, target_user_id)
                if enemy is None or int(enemy["guild_id"]) != guild_id or skill is None or skill.skill_type != "attack": raise ValueError("Escolha um hostil e uma Skill de ataque válidos.")
                if target is None: raise ValueError("Escolha um participante do Encounter como alvo.")
                review = review_encounter_command("encounter.enemy_free_queued", enemy_id=enemy_id, skill_name=skill.name, target_user_id=target_user_id, variant=variant)
                action = database.add_enemy_free_action(guild_id, channel_id, int(enemy["id"]), skill.name, target_user_id, variant, member_id or None)
                with database.lock, database.connection:
                    core = commit_sqlite_event(database.connection, guild_id=guild_id, command=review["command"], source="activity", entity_kind="encounter", entity_id=channel_id, payload={**review, "action_id":int(action["id"])})
                return encounter_changed(guild_id, channel_id, {"ok":True,"enemy_free_action_id":str(action["id"]),"core":core})
            if operation == "remove_participant":
                if battle["phase"] != "preparation": raise ValueError("Participantes só podem ser removidos durante a Preparação.")
                target_user_id = int(payload.get("user_id", 0))
                if not database.leave_battle(guild_id, channel_id, target_user_id): raise ValueError("Participante não encontrado.")
                return encounter_changed(guild_id, channel_id, {"ok":True,"removed_user_id":str(target_user_id)})
            if operation == "set_participant_ready":
                target_user_id = int(payload.get("user_id", 0)); target = database.get_battle_participant(guild_id, channel_id, target_user_id)
                if target is None: raise ValueError("Participante não encontrado.")
                if target["status"] == "clashing": raise ValueError("Não altere a prontidão de alguém durante um Clash.")
                ready = bool(payload.get("ready", False))
                database.set_battle_participant_ready(guild_id, channel_id, target_user_id, ready)
                return encounter_changed(guild_id, channel_id, {"ok":True,"user_id":str(target_user_id),"ready":ready})
            if operation == "advance":
                transitions = {"preparation":"declaration","declaration":"resolution","resolution":"complete"}
                if battle["phase"] == "preparation" and (not database.list_battle_participants(guild_id, channel_id) or not database.list_field_actions(guild_id, channel_id)):
                    raise ValueError("Adicione participantes e ao menos uma ação hostil antes da Declaração.")
                if battle["phase"] == "declaration" and database.list_field_actions(guild_id, channel_id, "claimed"):
                    raise ValueError("Ainda existe um Clash reservado em andamento.")
                automatic_results = []
                if battle["phase"] == "declaration":
                    open_actions = database.list_field_actions(guild_id, channel_id, "open")
                    for field_action in open_actions:
                        target_user_id = field_action["target_user_id"]
                        member_id = int(field_action["enemy_group_member_id"] or 0)
                        enemy = database.get_enemy_group_member_combatant(guild_id, member_id) if member_id else database.get_enemy(guild_id, field_action["enemy_name"])
                        if target_user_id is None:
                            raise ValueError(f"Ação #{field_action['id']} ainda não tem alvo. Volte à Preparação e escolha um participante.")
                        if enemy is None:
                            raise ValueError(f"O hostil da ação #{field_action['id']} não existe mais.")
                        with database.lock, database.connection:
                            commit_sqlite_event(database.connection, guild_id=guild_id, command="encounter.hostile_action_dispatched", source="activity", entity_kind="field_action", entity_id=field_action["id"], payload={"enemy_id":int(enemy["id"]), "enemy_skill":field_action["enemy_skill"], "target_user_id":int(target_user_id), "turn":int(battle["turn"])})
                        result = request_bot_clash(access_token, str(guild_id), {
                            "target_kind":"player", "target_id":target_user_id,
                            "actor_enemy_id":enemy["id"], "actor_enemy_group_member_id":member_id, "enemy_skill":field_action["enemy_skill"],
                            "channel_id":channel_id, "source":"enemy_unopposed",
                            "encounter":battle["name"], "turn":battle["turn"],
                        })
                        database.resolve_field_action(int(field_action["id"]))
                        automatic_results.append(result)
                phase = transitions.get(battle["phase"])
                if phase is None: raise ValueError("Não há próxima fase.")
                database.set_battle_phase(guild_id, channel_id, phase); database.reset_battle_readiness(guild_id, channel_id)
                return encounter_changed(guild_id, channel_id, {"ok":True,"phase":phase,"automatic_results":automatic_results,"result":automatic_results[-1] if automatic_results else None})
            if operation == "previous":
                phase = {"declaration":"preparation","resolution":"declaration","complete":"resolution"}.get(battle["phase"])
                if phase is None: raise ValueError("Não há fase anterior.")
                database.set_battle_phase(guild_id, channel_id, phase); database.reset_battle_readiness(guild_id, channel_id)
                return encounter_changed(guild_id, channel_id, {"ok":True,"phase":phase})
            if operation == "next_turn":
                if battle["phase"] != "complete": raise ValueError("Conclua a rodada antes de iniciar o próximo turno.")
                free_results = []
                for free_action in database.list_enemy_free_actions(guild_id, channel_id, "pending"):
                    with database.lock, database.connection:
                        commit_sqlite_event(database.connection, guild_id=guild_id, command="encounter.enemy_free_dispatched", source="activity", entity_kind="enemy_free_action", entity_id=free_action["id"], payload={"enemy_id":int(free_action["enemy_id"]), "enemy_skill":free_action["enemy_skill"], "target_user_id":int(free_action["target_user_id"]), "turn":int(battle["turn"])})
                    result = request_bot_clash(access_token, str(guild_id), {"target_kind":"player","target_id":free_action["target_user_id"],"actor_enemy_id":free_action["enemy_id"],"actor_enemy_group_member_id":int(free_action["enemy_group_member_id"] or 0),"enemy_skill":free_action["enemy_skill"],"channel_id":channel_id,"source":"enemy_unopposed","encounter":battle["name"],"turn":battle["turn"]})
                    database.resolve_enemy_free_action(int(free_action["id"]), int(result.get("damage", 0)))
                    free_results.append(result)
                next_battle = database.next_battle_turn(guild_id, channel_id)
                return encounter_changed(guild_id, channel_id, {"ok":True,"turn":next_battle["turn"],"enemy_free_results":free_results,"result":free_results[-1] if free_results else None})
            raise ValueError("Ação de Encounter desconhecida.")
    finally:
        database.close()

    # O banco é reaberto pela resolução para manter a reserva curta e evitar
    try:
        battle_info = Database(str(database_path())); battle_info.setup()
        try:
            current_battle = battle_info.get_battle(guild_id, channel_id)
            encounter_name = current_battle["name"] if current_battle else "Encounter"
            encounter_turn = int(current_battle["turn"]) if current_battle else 0
        finally:
            battle_info.close()
        member_id_value = int(action["enemy_group_member_id"] or 0) if (action and action["enemy_group_member_id"]) else int(payload.get("enemy_group_member_id", 0) or 0)
        target_kind = "enemy_group_member" if member_id_value else ("player" if unopposed and payload.get("target_kind") == "player" else "enemy")
        target_id_value = member_id_value if member_id_value else (target_id if target_id else int(enemy["id"] if enemy else 0))
        result = request_bot_clash(access_token, str(guild_id), {
            "target_kind": target_kind,
            "target_id": target_id_value,
            "target_enemy_group_member_id": member_id_value,
            "left_skill": player_skill,
            "right_skill": "" if unopposed else (action["enemy_skill"] if action else ""),
            "channel_id": channel_id,
            "source": "unopposed" if unopposed else "encounter",
            "encounter": encounter_name,
            "turn": encounter_turn
        })
    except Exception:
        recovery = Database(str(database_path())); recovery.setup()
        try:
            if not unopposed: recovery.release_field_action(action_id)
            recovery.set_battle_participant_status(guild_id, channel_id, user_id, "waiting")
        finally: recovery.close()
        raise
    completed = Database(str(database_path())); completed.setup()
    try:
        if unopposed:
            completed.add_player_action(guild_id, channel_id, user_id, character["name"], enemy["name"], player_skill, "unopposed", int(result.get("damage", 0)))
        else:
            completed.resolve_field_action(action_id)
        completed.set_battle_participant_status(guild_id, channel_id, user_id, "done")
    finally: completed.close()
    return encounter_changed(guild_id, channel_id, {"ok":True,"result":result,"message_queued":bool(result.get("message_queued"))})


class ActivityHandler(BaseHTTPRequestHandler):
    server_version = "ClashRPGActivity/1.0"

    def log_message(self, format: str, *args) -> None:
        print(f"[activity] {self.address_string()} - {format % args}")

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' https://cdn.discordapp.com https://media.discordapp.net data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https://discord.com https://*.discord.com wss://*.discord.com https://*.discordsays.com wss://*.discordsays.com")

    def send_json(self, value, status: int = 200) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            raise ValueError("Requisição grande demais.")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def bearer(self) -> str:
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer ") or len(value) < 20:
            raise PermissionError("Autorização do Discord ausente.")
        return value[7:]

    def serve_file(self, target: Path, cache: str = "public, max-age=3600") -> None:
        if not target.is_file():
            self.send_error(404)
            return
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache)
        self._security_headers()
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        path = parse.urlparse(self.path).path.removeprefix("/.proxy")
        try:
            if path == "/api/token":
                code = str(self.read_json().get("code", ""))
                if not code or len(code) > 2048:
                    raise ValueError("Código de autorização inválido.")
                self.send_json(exchange_code(code))
            elif path == "/api/activity/profile":
                payload = self.read_json()
                self.send_json(save_own_profile(self.bearer(), payload.get("guild_id"), payload.get("profile")))
            elif path == "/api/activity/statuses/save":
                payload = self.read_json()
                self.send_json(save_own_statuses(self.bearer(), payload.get("guild_id"), payload.get("statuses")))
            elif path == "/api/activity/skills/save":
                payload = self.read_json()
                self.send_json(save_own_skill(self.bearer(), payload.get("guild_id"), payload.get("skill")))
            elif path == "/api/activity/skills/delete":
                payload = self.read_json()
                self.send_json(delete_own_skill(self.bearer(), payload.get("guild_id"), payload.get("name")))
            elif path == "/api/activity/clash":
                payload = self.read_json()
                self.send_json(request_bot_clash(self.bearer(), payload.get("guild_id"), payload))
            elif path == "/api/activity/encounter/action":
                self.send_json(encounter_action(self.bearer(), self.read_json()))
            elif path == "/api/activity/admin/entity/save":
                self.send_json(save_admin_entity(self.bearer(), self.read_json()))
            elif path == "/api/activity/admin/image":
                self.send_json(save_admin_image(self.bearer(), self.read_json()))
            elif path == "/api/activity/admin/skill":
                self.send_json(admin_skill_action(self.bearer(), self.read_json()))
            elif path == "/api/activity/admin/enemy":
                self.send_json(admin_enemy_action(self.bearer(), self.read_json()))
            elif path == "/api/activity/admin/battle":
                self.send_json(admin_battle_action(self.bearer(), self.read_json()))
            elif path == "/api/activity/admin/settings":
                self.send_json(save_admin_settings(self.bearer(), self.read_json()))
            else:
                self.send_json({"error": "Rota não encontrada."}, 404)
        except PermissionError as error:
            self.send_json({"error": str(error)}, 401)
        except (ValueError, RuntimeError) as error:
            self.send_json({"error": str(error)}, 400)
        except Exception as error:
            import traceback
            traceback.print_exc()
            print(f"[activity] erro interno em POST {path}: {type(error).__name__}: {error}")
            self.send_json({"error": f"Erro ({type(error).__name__}): {error}"}, 500)

    def do_GET(self) -> None:
        parsed = parse.urlparse(self.path)
        route_path = parsed.path.removeprefix("/.proxy")
        try:
            if route_path == "/health":
                self.send_json({"ok": True})
            elif route_path == "/api/activity/status":
                self.send_json(activity_status())
            elif route_path == "/api/activity/me":
                query = parse.parse_qs(parsed.query)
                self.send_json(own_sheet(self.bearer(), query.get("guild_id", [None])[0]))
            elif route_path == "/api/activity/admin":
                query = parse.parse_qs(parsed.query)
                self.send_json(admin_overview(self.bearer(), query.get("guild_id", [None])[0]))
            elif route_path == "/api/activity/combat/targets":
                query = parse.parse_qs(parsed.query)
                self.send_json(activity_combat_targets(self.bearer(), query.get("guild_id", [None])[0]))
            elif route_path == "/api/activity/encounters":
                query = parse.parse_qs(parsed.query)
                self.send_json(encounter_overview(self.bearer(), query.get("guild_id", [None])[0], query.get("channel_id", [None])[0]))
            elif route_path == "/api/activity/admin/entity":
                query = parse.parse_qs(parsed.query)
                self.send_json(admin_entity_detail(self.bearer(), query.get("guild_id", [None])[0], query.get("kind", [None])[0], query.get("owner_id", [None])[0]))
            elif route_path.startswith("/uploads/"):
                filename = Path(route_path).name
                target = UPLOAD_DIR / filename
                if target.parent.resolve() != UPLOAD_DIR.resolve():
                    raise PermissionError("Caminho inválido.")
                self.serve_file(target, "public, max-age=86400")
            else:
                relative = route_path.lstrip("/") or "index.html"
                target = (STATIC_DIR / relative).resolve()
                if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                    raise PermissionError("Caminho inválido.")
                if not target.is_file() and "." not in Path(relative).name:
                    target = STATIC_DIR / "index.html"
                # O Discord mantém o iframe vivo e pode reutilizar HTML em
                # cache. O índice precisa sempre apontar para o build atual;
                # assets com hash continuam seguros para cache prolongado.
                # Os dois arquivos de entrada têm nome estável para não quebrar
                # instâncias reabertas pelo Discord; eles precisam ser sempre
                # revalidados. Chunks com hash continuam imutáveis.
                cache = "no-store" if target.name == "index.html" or target.name.startswith("clashbot-app-v") or target.name in {"clashbot.js", "clashbot.css", "clashbot-app.js", "clashbot-app.css"} else "public, max-age=31536000, immutable"
                self.serve_file(target, cache)
        except PermissionError as error:
            self.send_json({"error": str(error)}, 401)
        except (ValueError, RuntimeError, sqlite3.Error) as error:
            self.send_json({"error": str(error)}, 400)
        except Exception as error:
            print(f"[activity] erro interno em GET {route_path}: {type(error).__name__}: {error}")
            self.send_json({"error": "A Activity encontrou um erro interno ao carregar estes dados."}, 500)


def main() -> None:
    global ACTIVITY_LOCK_SOCKET
    parser = argparse.ArgumentParser(description="Servidor público da Discord Activity do Clash RPG")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(config().get("ACTIVITY_PORT", "8780")))
    args = parser.parse_args()
    if not STATIC_DIR.joinpath("index.html").is_file():
        raise SystemExit("Frontend ausente. Execute npm run build em ui/discord-activity.")
    lock_port = int(config().get("ACTIVITY_INSTANCE_LOCK_PORT", "47880") or 47880)
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        lock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        lock.bind(("127.0.0.1", lock_port)); lock.listen(1)
    except OSError as error:
        lock.close()
        raise SystemExit("A Discord Activity já está ligada neste computador.") from error
    ACTIVITY_LOCK_SOCKET = lock
    server = ThreadingHTTPServer((args.host, args.port), ActivityHandler)
    print(f"Discord Activity disponível em http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lock.close()


if __name__ == "__main__":
    main()
