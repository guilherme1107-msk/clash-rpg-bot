from __future__ import annotations

import os
import asyncio
import io
import logging
import traceback
import random
from dataclasses import replace
import time
import uuid
import json
import socket
import threading
import re
from logging.handlers import RotatingFileHandler
from collections import deque
from pathlib import Path
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from src.domain.combat import DamageResult, Forecast, Modifiers, Skill, SkillEffect, apply_damage_percentage, clashable_guard_values, estimate_clash, format_skill_effects, heads_chance, parse_skill_effects, resolve_clash, resolve_damage, resolve_defense, triggered_skill_effects
from database import Database
from battle_flow import advance_when_all_ready
from src.domain.status import STATUS_TYPES, on_action, on_damage_taken, tremor_burst

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [item.strip() for item in os.getenv("DISCORD_GUILD_ID", "").split(",") if item.strip()]
db = Database(os.getenv("DATABASE_PATH", "clash_rpg.sqlite3"))
ACCENT = discord.Color.from_rgb(179, 24, 36)
GOLD = discord.Color.from_rgb(202, 164, 75)
SKILL_TYPE_LABELS = {
    "attack": "⚔️ Normal", "guard": "🛡️ Defesa", "counter": "↩️ Counter",
    "evade": "💨 Evasiva", "clashable_guard": "🔰 Defesa Clashable",
    "clashable_counter": "⚡ Counter Clashable", "assist_defense": "🤝 Assist Defense",
}
SKILL_TYPE_ALIASES = {
    "normal": "attack", "ataque": "attack", "attack": "attack",
    "defesa": "guard", "guard": "guard", "counter": "counter",
    "evasiva": "evade", "evade": "evade", "defesa clashable": "clashable_guard",
    "clashable guard": "clashable_guard", "counter clashable": "clashable_counter",
    "clashable counter": "clashable_counter", "assist defense": "assist_defense",
}
SKILL_TYPE_CHOICES = [app_commands.Choice(name=label, value=value) for value, label in SKILL_TYPE_LABELS.items()]
def env_value(name: str, default: str) -> str:
    return (os.getenv(name) or "").strip() or default


COIN_ACTIVE = env_value("EMOJI_COIN_ACTIVE", "<:ML:1534094500815831181>")
COIN_BROKEN = env_value("EMOJI_COIN_BROKEN", "<:SA:1538694912877269032>")
COIN_HEADS = env_value("EMOJI_COIN_HEADS", "<:CG:1534127740381302864>")
COIN_TAILS = env_value("EMOJI_COIN_NORMAL", "<:MN:1534094257915297954>")
COIN_UNBREAKABLE = env_value("EMOJI_COIN_UNBREAKABLE", "<:MI:1535257836966117376>")
COIN_UNBREAKABLE_HEADS = env_value("EMOJI_COIN_UNBREAKABLE_HEADS", "<:MIA:1535261448694145124>")
EFFECT_CLASH_UP = env_value("EMOJI_CLASH_UP", "<:ECU:1534104390896455740>")
EFFECT_CLASH_DOWN = env_value("EMOJI_CLASH_DOWN", "<:ECD:1534104363658641479>")
EFFECT_ATTACK_UP = env_value("EMOJI_ATTACK_UP", "<:EAU:1535263226936295565>")
EFFECT_ATTACK_DOWN = env_value("EMOJI_ATTACK_DOWN", "<:EAD:1534104291772469258>")
EFFECT_PARALYZE = env_value("EMOJI_PARALYZE", "<:EP:1534104414183493702>")
EFFECT_OFFENSE_UP = env_value("EMOJI_OFFENSE_UP", "<:OLU:1534122107716501534>")
EFFECT_OFFENSE_DOWN = env_value("EMOJI_OFFENSE_DOWN", "<:OLD:1534122151911751811>")
EFFECT_PLUS_COIN_DROP = env_value("EMOJI_PLUS_COIN_DROP", "<:PCD:1534122057187590344>")
EFFECT_PLUS_COIN_BOOST = env_value("EMOJI_PLUS_COIN_BOOST", "<:PCB:1534122027143921766>")
STATUS_ICONS = {
    "burn": env_value("EMOJI_STATUS_BURN", "<:EBu:1537502509168459896>"),
    "bleed": env_value("EMOJI_STATUS_BLEED", "<:EBl:1537502804820623432>"),
    "tremor": env_value("EMOJI_STATUS_TREMOR", "<:ETr:1537502576860332124>"),
    "rupture": env_value("EMOJI_STATUS_RUPTURE", "<:ERu:1537502748768075916>"),
    "sinking": env_value("EMOJI_STATUS_SINKING", "<:ESi:1537502845186875472>"),
    "poise": env_value("EMOJI_STATUS_POISE", "<:EPo:1537503433651785840>"),
    "charge": env_value("EMOJI_STATUS_CHARGE", "<:ECh:1537503388906954923>"),
    "special_condition": env_value("EMOJI_STATUS_SPECIAL_CONDITION", "<:PlH:1538709761757806813>"),
    "devotion_repressed": "🩸",
    "bloodfiend": "🧛",
    "bloodbag": "🩸",
}
TREMOR_BURST_ICON = env_value("EMOJI_TREMOR_BURST", "<:ETB:1537527981537231009>")
STATUS_LABELS = {key: key.title() for key in STATUS_TYPES}
STATUS_LABELS["special_condition"] = "Condição Especial"
STATUS_ICONS["special_condition_consumed"] = STATUS_ICONS["special_condition"]
STATUS_LABELS["special_condition_consumed"] = "Condição Especial consumida no Encounter"
STATUS_ICONS["bloodfiend_or_bloodbag"] = "🧛"
STATUS_LABELS["devotion_repressed"] = "Devoção Reprimida"
STATUS_LABELS["bloodfiend"] = "Bloodfiend"
STATUS_LABELS["bloodbag"] = "Bloodbag"
STATUS_LABELS["bloodfiend_or_bloodbag"] = "Bloodfiend ou Bloodbag"
OFFENSE_LEVEL_ICON = env_value("EMOJI_OFFENSE_LEVEL", EFFECT_OFFENSE_UP)
DEFENSE_LEVEL_ICON = env_value("EMOJI_DEFENSE_LEVEL", "🛡️")
UNBREAKABLE_FOLLOWUP_GIF = os.getenv(
    "UNBREAKABLE_FOLLOWUP_GIF", "",
)
DAMAGE_RESOLUTION_GIF = os.getenv(
    "DAMAGE_RESOLUTION_GIF", "",
)
CLASH_GUILD_ID = int(os.getenv("CLASH_GUILD_ID", "949911180841975849") or 0)
CLASH_CHANNEL_ID = int(os.getenv("CLASH_CHANNEL_ID", "1536852812623908874") or 0)


def parse_clash_channels(raw: str) -> dict[int, int]:
    channels: dict[int, int] = {}
    for entry in raw.split(","):
        if not entry.strip():
            continue
        try:
            guild_id, channel_id = entry.strip().split(":", 1)
            channels[int(guild_id)] = int(channel_id)
        except ValueError:
            continue
    return channels


CLASH_CHANNELS = parse_clash_channels(os.getenv("CLASH_CHANNELS", ""))
AUDIT_CHANNEL_ID = int(os.getenv("AUDIT_CHANNEL_ID", "1537565714356117565") or 0)
PRIVATE_SKILL_OWNER_ID = int(os.getenv("PRIVATE_SKILL_OWNER_ID", "1034518001535430777") or 0)
PUBLIC_STATUS_TYPES = STATUS_TYPES - {"devotion_repressed", "bloodfiend", "bloodbag"}
PRIVATE_SKILL_NAMES = {
    "eu posso ser útil.", "ajoelhe-se.", "aceite minha oferenda.",
    "você não merece esse sangue.",
}
APPEARANCE_CHANNEL_ID = int(os.getenv("APPEARANCE_CHANNEL_ID", "1537587461629280266") or 0)
INSTANCE_LOCK_PORT = int(os.getenv("BOT_INSTANCE_LOCK_PORT", "47653") or 47653)
INSTANCE_LOCK_SOCKET: socket.socket | None = None
CONTROL_STATE_PATH = Path(__file__).with_name("control_center_state.json")


def is_transient_discord_error(error: BaseException) -> bool:
    """Erros de transporte que podem desaparecer sem invalidar a interacao."""
    if isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError, OSError)):
        return True
    return isinstance(error, discord.HTTPException) and error.status in {429, 500, 502, 503, 504}


async def discord_request_with_retry(operation, *, label: str, attempts: int = 4):
    """Repete operacoes de rede do Discord com espera curta e progressiva."""
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as error:
            if not is_transient_discord_error(error):
                raise
            last_error = error
            audit_logger.warning(
                "[REDE DISCORD] %s falhou (%d/%d) | tipo=%s | detalhe=%s",
                label, attempt, attempts, type(error).__name__, error,
            )
            if attempt < attempts:
                await asyncio.sleep(0.65 * attempt)
    assert last_error is not None
    raise last_error


async def resilient_clash_edit(interaction, *, embed: discord.Embed, required: bool) -> bool:
    """Edita o painel; frames podem ser pulados, mas resultados geram alerta forte."""
    try:
        await discord_request_with_retry(
            lambda: interaction.edit_original_response(embed=embed),
            label="editar painel de Clash",
        )
        return True
    except Exception as error:
        if not is_transient_discord_error(error):
            raise
        level = audit_logger.error if required else audit_logger.warning
        level(
            "[CLASH / REDE] %s nao foi publicado apos novas tentativas | tipo=%s | detalhe=%s",
            "resultado final" if required else "frame de animacao", type(error).__name__, error,
        )
        return False


class RoutedClashResponse:
    def __init__(self, routed: "RoutedClashInteraction") -> None:
        self.routed = routed

    def is_done(self) -> bool:
        return self.routed.source.response.is_done()

    async def _acknowledge(self) -> None:
        if not self.routed.source.response.is_done():
            await discord_request_with_retry(
                lambda: self.routed.source.response.send_message(
                    f"⚔️ Clash enviado para {self.routed.output_channel.mention}.", ephemeral=True,
                ),
                label="confirmar roteamento do Clash",
            )

    async def defer(self, *, ephemeral: bool = False, **kwargs) -> None:
        await self._acknowledge()
        await self.routed.ensure_output_message()

    async def send_message(
        self, content=None, *, embed=None, ephemeral: bool = False, view=None,
        files=None, file=None, **kwargs,
    ) -> None:
        if ephemeral:
            sender = (
                self.routed.source.followup.send
                if self.routed.source.response.is_done()
                else self.routed.source.response.send_message
            )
            await sender(content, embed=embed, view=view, ephemeral=True, **kwargs)
            return
        await self._acknowledge()
        payload_files = list(files or [])
        if file is not None:
            payload_files.append(file)
        self.routed.output_message = await discord_request_with_retry(
            lambda: self.routed.output_channel.send(
                content=content, embed=embed, view=view, files=payload_files,
            ),
            label="enviar mensagem ao canal de Clash",
        )

    async def edit_message(self, **kwargs) -> None:
        await self._acknowledge()
        message = await self.routed.ensure_output_message()
        await discord_request_with_retry(
            lambda: message.edit(**kwargs), label="editar mensagem roteada de Clash",
        )


class RoutedClashFollowup:
    def __init__(self, routed: "RoutedClashInteraction") -> None:
        self.routed = routed

    async def send(self, content=None, *, ephemeral: bool = False, **kwargs):
        if ephemeral:
            return await self.routed.source.followup.send(content, ephemeral=True, **kwargs)
        kwargs.pop("wait", None)
        return await discord_request_with_retry(
            lambda: self.routed.output_channel.send(content=content, **kwargs),
            label="enviar resultado adicional do Clash",
        )


class RoutedClashInteraction:
    """Mantém o contexto do usuário, mas envia a luta para o canal de arena."""

    def __init__(self, source: discord.Interaction, output_channel) -> None:
        self.source = source
        self.output_channel = output_channel
        self.output_message = None
        self.response = RoutedClashResponse(self)
        self.followup = RoutedClashFollowup(self)

    def __getattr__(self, name):
        return getattr(self.source, name)

    async def ensure_output_message(self):
        if self.output_message is None:
            self.output_message = await discord_request_with_retry(
                lambda: self.output_channel.send("⚔️ **Preparando Clash…**"),
                label="abrir painel de Clash",
            )
        return self.output_message

    async def edit_original_response(self, **kwargs):
        message = await self.ensure_output_message()
        return await discord_request_with_retry(
            lambda: message.edit(**kwargs), label="atualizar painel de Clash",
        )


async def clash_output_channel(interaction: discord.Interaction):
    if interaction.guild is None:
        return interaction.channel
    channel_id = CLASH_CHANNELS.get(interaction.guild_id)
    if channel_id is None:
        if not CLASH_CHANNEL_ID or (CLASH_GUILD_ID and interaction.guild_id != CLASH_GUILD_ID):
            return interaction.channel
        channel_id = CLASH_CHANNEL_ID
    channel = interaction.guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await interaction.guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    member = interaction.guild.me
    if member is not None and hasattr(channel, "permissions_for"):
        permissions = channel.permissions_for(member)
        if not permissions.send_messages or not permissions.embed_links:
            return None
    return channel


async def routed_clash_interaction(interaction: discord.Interaction):
    channel = await clash_output_channel(interaction)
    if channel is None:
        return None
    if interaction.channel_id == channel.id:
        return interaction
    return RoutedClashInteraction(interaction, channel)


def coin_bar(remaining: int, total: int, broken_unbreakable: int = 0) -> str:
    destroyed = max(0, total - remaining - broken_unbreakable)
    if total > 5:
        parts = []
        if remaining:
            parts.append(f"{COIN_ACTIVE}×{remaining}")
        if broken_unbreakable:
            parts.append(f"{COIN_UNBREAKABLE}×{broken_unbreakable}")
        if destroyed:
            parts.append(f"{COIN_BROKEN}×{destroyed}")
        return " ".join(parts)
    return COIN_ACTIVE * remaining + COIN_UNBREAKABLE * broken_unbreakable + COIN_BROKEN * destroyed


def roll_icons(roll) -> str:
    disabled = roll.disabled or [False] * len(roll.faces)
    unbreakable = roll.unbreakable or [False] * len(roll.faces)
    icons = []
    for face, blocked, sturdy in zip(roll.faces, disabled, unbreakable):
        if blocked:
            icons.append(EFFECT_PARALYZE)
        elif sturdy:
            icons.append(COIN_UNBREAKABLE_HEADS if face else COIN_UNBREAKABLE)
        else:
            icons.append(COIN_HEADS if face else COIN_TAILS)
    return "".join(icons)


def compact_roll(roll) -> str:
    """Moedas compactadas por quantidade para respeitar os limites do Discord."""
    if len(roll.faces) <= 5:
        return roll_icons(roll)
    disabled = roll.disabled or [False] * len(roll.faces)
    unbreakable = roll.unbreakable or [False] * len(roll.faces)
    paralyzed = sum(disabled)
    sturdy_heads = sum(face and not blocked and sturdy for face, blocked, sturdy in zip(roll.faces, disabled, unbreakable))
    sturdy_tails = sum(not face and not blocked and sturdy for face, blocked, sturdy in zip(roll.faces, disabled, unbreakable))
    heads = sum(face and not blocked and not sturdy for face, blocked, sturdy in zip(roll.faces, disabled, unbreakable))
    tails = sum(not face and not blocked and not sturdy for face, blocked, sturdy in zip(roll.faces, disabled, unbreakable))
    parts = []
    if paralyzed:
        parts.append(f"{EFFECT_PARALYZE}×{paralyzed}")
    if sturdy_heads:
        parts.append(f"{COIN_UNBREAKABLE_HEADS}×{sturdy_heads}")
    if sturdy_tails:
        parts.append(f"{COIN_UNBREAKABLE}×{sturdy_tails}")
    if heads:
        parts.append(f"{COIN_HEADS}×{heads}")
    if tails:
        parts.append(f"{COIN_TAILS}×{tails}")
    return " ".join(parts) or "—"


def add_history_fields(embed: discord.Embed, history: list[str]) -> None:
    """Adiciona até 10 registros em campos que nunca excedem 1024 caracteres."""
    lines = history[-10:]
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 1000:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks, 1):
        suffix = f" • {index}/{len(chunks)}" if len(chunks) > 1 else ""
        embed.add_field(name=f"REGISTRO (MÁX. 10){suffix}", value=chunk, inline=False)


def effect_icon(value: int, positive: str, negative: str) -> str:
    if value > 0:
        return positive
    if value < 0:
        return negative
    return ""


def clash_effect_strip(guild_id: int, owner_kind: str, owner_id: int, row) -> str:
    """Resumo compacto dos efeitos que acompanham a faixa do Clash."""
    keys = set(row.keys())
    effects: list[str] = []
    if row["paralysis"]:
        effects.append(f"{EFFECT_PARALYZE}`{row['paralysis']}`")
    modifier_specs = (
        ("base_power_mod", EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN, "B"),
        ("coin_power_mod", EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP, "C"),
        ("clash_power_mod", EFFECT_CLASH_UP, EFFECT_CLASH_DOWN, "CL"),
        ("offense_level_mod", EFFECT_OFFENSE_UP, EFFECT_OFFENSE_DOWN, "OL"),
    )
    for key, positive, negative, label in modifier_specs:
        value = row[key] if key in keys else 0
        if value:
            effects.append(f"{effect_icon(value, positive, negative)}`{label}{value:+}`")
    defense_mod = row["defense_level_mod"] if "defense_level_mod" in keys else 0
    if defense_mod:
        effects.append(f"{DEFENSE_LEVEL_ICON}`DL{defense_mod:+}`")
    for status in db.list_statuses(guild_id, owner_kind, owner_id):
        if status.status_type in {"devotion_repressed", "bloodfiend", "bloodbag"}:
            continue
        effects.append(f"{STATUS_ICONS[status.status_type]}`{status.potency}×{status.count}`")
    return " ".join(effects) if effects else "`SEM EFEITOS`"


def skill_condition_value(
    guild_id: int, actor_kind: str, actor_id: int, target_kind: str, target_id: int,
    effect: SkillEffect,
) -> tuple[int, str, int]:
    """Retorna o valor e o rótulo usados pela condição de uma skill."""
    owner_kind, owner_id = (
        (actor_kind, actor_id) if effect.condition_owner == "user"
        else (target_kind, target_id)
    )
    if effect.condition_status == "special_condition_consumed":
        value = db.get_special_condition_consumed(guild_id, owner_kind, owner_id)
    elif effect.condition_status == "bloodfiend_or_bloodbag":
        tags = db.get_enemy_tags(owner_id) if owner_kind == "enemy" else []
        value = int(bool({tag.casefold() for tag in tags} & {"bloodfiend", "bloodbag"}))
    else:
        status = db.get_status(guild_id, owner_kind, owner_id, effect.condition_status)
        value = 0 if status is None else (
            status.count if effect.condition_value == "count" else status.potency
        )
    owner_label = "usuário" if effect.condition_owner == "user" else "alvo"
    value_label = "Quantidade" if effect.condition_value == "count" else "Potência"
    multiplier = effect.condition_multiplier(value)
    return value, f"{owner_label} • {value_label}", multiplier


def apply_skill_damage_percent(
    guild_id: int, actor_kind: str, actor_id: int, target_kind: str, target_id: int,
    skill: Skill, damage: DamageResult, *, clash_won: bool = False,
    consume_resources: bool = True,
) -> list[str]:
    """Resolve bônus/reduções percentuais uma vez, depois da rolagem das moedas."""
    total = 0.0
    logs: list[str] = []
    valid_triggers = {"on_use", "before_attack", "on_hit", "heads_hit"}
    if clash_won:
        valid_triggers.add("clash_win")
    for effect in skill.effects:
        if effect.effect_type != "damage_percent" or effect.trigger not in valid_triggers:
            continue
        if effect.coin is not None:
            hit = next((item for item in damage.hits if item.coin == effect.coin), None)
            if hit is None or (effect.trigger == "heads_hit" and (not hit.face or hit.paralyzed)):
                continue
        elif effect.trigger == "heads_hit" and not any(
            hit.face and not hit.paralyzed for hit in damage.hits
        ):
            continue
        multiplier = 1
        if effect.condition_status:
            current, condition_label, multiplier = skill_condition_value(
                guild_id, actor_kind, actor_id, target_kind, target_id, effect,
            )
            if multiplier <= 0:
                logs.append(
                    f"`{effect.trigger.upper()}` Dano % **INATIVO** • {condition_label} "
                    f"`{current}/{effect.condition_min}`"
                )
                continue
        resource_note = ""
        if effect.charge_cost:
            charge = db.get_status(guild_id, actor_kind, actor_id, "charge")
            available = 0 if charge is None else charge.count
            if available < effect.charge_cost:
                logs.append(
                    f"`{effect.trigger.upper()}` Dano % **INATIVO** • Charge "
                    f"`{available}/{effect.charge_cost}`"
                )
                continue
            if consume_resources:
                db.consume_charge(guild_id, actor_kind, actor_id, effect.charge_cost)
                resource_note = f" • Charge `−{effect.charge_cost}`"
            else:
                resource_note = f" • Charge necessária `{effect.charge_cost}` (simulação)"
        value = effect.value * multiplier
        if effect.coin is None:
            total += value
        else:
            # Efeito preso a uma moeda modifica apenas o dano dessa moeda.
            coin_bonus = int(hit.power * value / 100)
            damage.coin_percent_modifier += coin_bonus
            damage.coin_damage_percent.append((effect.coin, value))
        consumed_note = ""
        if consume_resources and effect.consume_condition and effect.condition_status:
            owner_kind, owner_id = (
                (actor_kind, actor_id) if effect.condition_owner == "user"
                else (target_kind, target_id)
            )
            status = db.get_status(guild_id, owner_kind, owner_id, effect.condition_status)
            if status is not None:
                amount = (
                    multiplier * effect.condition_per
                    if effect.condition_per > 0 else max(1, effect.condition_min)
                )
                if effect.condition_value == "count":
                    remaining = max(0, status.count - amount)
                    db.set_status(guild_id, owner_kind, owner_id, effect.condition_status, status.potency, remaining)
                else:
                    remaining = max(0, status.potency - amount)
                    db.set_status(guild_id, owner_kind, owner_id, effect.condition_status, remaining, status.count)
                consumed_note = f" • {STATUS_LABELS[effect.condition_status]} consumida `{amount}`"
        logs.append(
            f"`{effect.trigger.upper()}` Modificador de dano final `{value:+g}%`"
        )
    apply_damage_percentage(damage, total)
    damage.final_damage = max(0, damage.final_damage + damage.coin_percent_modifier)
    return logs


def apply_skill_trigger(
    guild_id: int, actor_kind: str, actor_id: int, target_kind: str, target_id: int,
    skill: Skill, trigger: str, *, remaining_coins: int | None = None, hits=None,
) -> list[str]:
    """Paralyze afeta o alvo; SP e modificadores afetam o usuário da skill."""
    effects = triggered_skill_effects(skill, trigger, remaining_coins=remaining_coins, hits=hits)
    applied = []
    values = {"base_power": 0, "coin_power": 0, "clash_power": 0, "offense_level": 0, "final_power": 0}
    target_paralysis = target_defense = sp_delta = 0
    for effect in effects:
        resource_note = ""
        multiplier = 1
        if effect.effect_type == "make_unbreakable":
            continue  # Resolvido antes da rolagem por prepare_charge_enhancements.
        if effect.effect_type == "damage_percent":
            continue  # Calculado uma única vez sobre o dano pós-nível.
        if effect.effect_type == "consume_special_condition":
            saved, consumed, encounter_total = db.consume_special_condition(
                guild_id, actor_kind, actor_id, int(effect.value),
            )
            applied.append(
                f"`{trigger.upper()}` {STATUS_ICONS['special_condition']} consumiu "
                f"`{consumed}` (até `{int(effect.value)}`) • saldo "
                f"`{saved.potency}×{saved.count}` • Encounter `{encounter_total}`"
            )
            continue
        if effect.effect_type == "self_bleed":
            saved = db.add_status(
                guild_id, actor_kind, actor_id, "bleed", int(effect.value), effect.count or 0,
            )
            applied.append(
                f"`{trigger.upper()}` {STATUS_ICONS['bleed']} Bleed em si mesma "
                f"`+{int(effect.value)} Pot. / +{effect.count or 0} Qtd.` → "
                f"`{saved.potency}×{saved.count}`"
            )
            continue
        if effect.effect_type == "consume_devotion_repressed":
            current = db.get_status(guild_id, actor_kind, actor_id, "devotion_repressed")
            consumed = min(int(effect.value), current.count if current else 0)
            if current and consumed:
                saved = db.set_status(
                    guild_id, actor_kind, actor_id, "devotion_repressed",
                    current.potency, current.count - consumed,
                )
            else:
                saved = current
            # O valor é propositalmente omitido dos embeds públicos.
            applied.append(f"`{trigger.upper()}` 🔒 recurso privado atualizado")
            continue
        if effect.condition_status:
            condition_value, condition_label, multiplier = skill_condition_value(
                guild_id, actor_kind, actor_id, target_kind, target_id, effect,
            )
            if condition_value < effect.condition_min or multiplier <= 0:
                applied.append(
                    f"`{trigger.upper()}` condição falhou • {condition_label} precisa de "
                    f"{STATUS_ICONS[effect.condition_status]} {STATUS_LABELS[effect.condition_status]} "
                    f"`{effect.condition_min}+` (atual `{condition_value}`)"
                )
                continue
        effective_value = effect.value * multiplier
        scale_note = f" ×{multiplier}" if multiplier != 1 else ""
        if effect.charge_cost:
            charge = db.get_status(guild_id, actor_kind, actor_id, "charge")
            available = 0 if charge is None else charge.count
            if available < effect.charge_cost:
                applied.append(
                    f"`{trigger.upper()}` melhoria de Charge **INATIVA** • "
                    f"a skill funciona normalmente • Charge `{available}/{effect.charge_cost}`"
                )
                continue
            saved_charge, potency_gain, charge_progress = db.consume_charge(
                guild_id, actor_kind, actor_id, effect.charge_cost,
            )
            progression = (
                f" • Potência **+{potency_gain}** • progresso `{charge_progress}/10`"
                if potency_gain else f" • progresso `{charge_progress}/10`"
            )
            resource_note = (
                f" • {STATUS_ICONS['charge']} Charge `{charge.potency}×{available}` → "
                f"`{saved_charge.potency}×{saved_charge.count}` "
                f"(consumido `{effect.charge_cost}`){progression}"
            )
        if effect.effect_type == "tremor_burst":
            tremor = db.get_status(guild_id, target_kind, target_id, "tremor")
            if tremor is None or tremor.potency <= 0 or tremor.count <= 0:
                applied.append(
                    f"`{trigger.upper()}` {TREMOR_BURST_ICON} Tremor Burst • "
                    "**0 Stagger Threshold** (alvo sem Tremor ativo)"
                )
            else:
                burst = tremor_burst(tremor)
                applied.append(
                    f"`{trigger.upper()}` {TREMOR_BURST_ICON} Tremor Burst • "
                    f"**+{burst.stagger_threshold} Stagger Threshold** • "
                    f"Tremor preservado `{tremor.potency}×{tremor.count}`"
                )
            continue
        if effect.effect_type in STATUS_TYPES:
            status_kind, status_id = (
                (actor_kind, actor_id) if effect.effect_type in {"poise", "charge", "special_condition"}
                else (target_kind, target_id)
            )
            saved = db.add_status(
                guild_id, status_kind, status_id, effect.effect_type,
                int(effective_value), effect.count or 0,
            )
            target_text = "usuário" if status_kind == actor_kind and status_id == actor_id else "alvo"
            coin_text = f" (moeda {effect.coin})" if effect.coin is not None else ""
            applied.append(
                f"`{trigger.upper()}` {STATUS_ICONS[effect.effect_type]} "
                f"{STATUS_LABELS[effect.effect_type]} no {target_text} "
                f"`+{effective_value} Pot. / +{effect.count or 0} Qtd.{scale_note}`{coin_text} "
                f"→ `{saved.potency}×{saved.count}`{resource_note}"
            )
            continue
        if effect.effect_type == "paralysis":
            target_paralysis += effective_value
        elif effect.effect_type == "defense_level":
            target_defense += effective_value
        elif effect.effect_type == "sp":
            sp_delta += effective_value
        else:
            values[effect.effect_type] += effective_value
        coin_text = f" (moeda {effect.coin})" if effect.coin is not None else ""
        applied.append(
            f"`{trigger.upper()}` {effect.effect_type} `{effective_value:+}`{scale_note}{coin_text}{resource_note}"
        )
    values["base_power"] += values["final_power"]
    if actor_kind == "player":
        if sp_delta:
            db.change_sp(guild_id, actor_id, sp_delta)
        if any(values.values()):
            db.add_effects(guild_id, actor_id, 0, values["base_power"], values["coin_power"], values["clash_power"], values["offense_level"])
    else:
        if sp_delta:
            db.change_enemy_sp(actor_id, sp_delta)
        if any(values.values()):
            db.add_enemy_effects(actor_id, 0, values["base_power"], values["coin_power"], values["clash_power"], values["offense_level"])
    if target_paralysis:
        if target_kind == "player":
            db.add_effects(guild_id, target_id, target_paralysis, 0, 0, 0, 0)
        else:
            db.add_enemy_effects(target_id, target_paralysis, 0, 0, 0, 0)
    if target_defense:
        if target_kind == "player":
            db.add_effects(guild_id, target_id, 0, 0, 0, 0, 0, int(target_defense))
        else:
            db.add_enemy_effects(target_id, 0, 0, 0, 0, 0, int(target_defense))
    return applied


def prepare_charge_enhancements(
    guild_id: int, actor_kind: str, actor_id: int, target_kind: str, target_id: int,
    skill: Skill,
) -> tuple[Skill, list[str]]:
    """Consome Charge para transformações estruturais; nunca impede o uso da skill."""
    layout = list(skill.coin_layout)
    logs: list[str] = []
    for effect in skill.effects:
        if effect.trigger != "on_use" or effect.effect_type != "make_unbreakable":
            continue
        if effect.condition_status:
            current, condition_label, multiplier = skill_condition_value(
                guild_id, actor_kind, actor_id, target_kind, target_id, effect,
            )
            if current < effect.condition_min or multiplier <= 0:
                logs.append(
                    f"{COIN_UNBREAKABLE} melhoria **INATIVA** • condição ({condition_label}) "
                    f"`{effect.condition_status} {current}/{effect.condition_min}` • skill mantida"
                )
                continue
        charge = db.get_status(guild_id, actor_kind, actor_id, "charge")
        available = 0 if charge is None else charge.count
        if effect.charge_cost and available < effect.charge_cost:
            logs.append(
                f"{COIN_UNBREAKABLE} melhoria **INATIVA** • Charge "
                f"`{available}/{effect.charge_cost}` • skill mantida"
            )
            continue
        saved_charge = charge
        potency_gain = charge_progress = 0
        if effect.charge_cost:
            saved_charge, potency_gain, charge_progress = db.consume_charge(
                guild_id, actor_kind, actor_id, effect.charge_cost,
            )
        positions = range(1, skill.coins + 1) if effect.coin is None else (effect.coin,)
        changed = []
        for position in positions:
            if 1 <= position <= skill.coins:
                layout[position - 1] = "unbreakable"
                changed.append(position)
        resource_text = ""
        if effect.charge_cost:
            gain_text = f" • Potência **+{potency_gain}**" if potency_gain else ""
            resource_text = (
                f"{STATUS_ICONS['charge']} Charge `{charge.potency}×{available}` → "
                f"`{saved_charge.potency}×{saved_charge.count}` (consumido `{effect.charge_cost}`)"
                f"{gain_text} • progresso `{charge_progress}/10` • "
            )
        logs.append(
            f"{resource_text}{COIN_UNBREAKABLE} moeda(s) "
            f"`{', '.join(map(str, changed))}` tornaram-se inquebráveis"
        )
    if tuple(layout) == skill.coin_layout:
        return skill, logs
    return replace(
        skill, coin_layout=tuple(layout), unbreakable_coins=layout.count("unbreakable"),
    ), logs


def add_trigger_log(embed: discord.Embed, applied: list[str]) -> None:
    if applied:
        embed.add_field(
            name="〔 EFEITOS ATIVADOS 〕",
            value="\n".join(f"◆ {line}" for line in applied)[:1024],
            inline=False,
        )


def add_status_impact(embed: discord.Embed, applied: list[str]) -> None:
    impacts = [
        line for line in applied
        if "dano" in line.casefold() or " sp" in line.casefold()
        or "stagger threshold" in line.casefold()
    ]
    if impacts:
        embed.add_field(
            name="【 IMPACTO DOS STATUS 】",
            value="\n".join(f"└ {line}" for line in impacts)[:1024],
            inline=False,
        )


def status_summary(guild_id: int, owner_kind: str, owner_id: int, *, compact: bool = False) -> str:
    """Shared status display used by sheets, enemies and the battlefield."""
    statuses = db.list_statuses(guild_id, owner_kind, owner_id)
    if not statuses:
        return "" if compact else "`SEM STATUS`"
    separator = "  •  " if compact else "\n"
    rendered = []
    for item in statuses:
        if item.status_type in {"devotion_repressed", "bloodfiend", "bloodbag"}:
            continue
        if item.status_type == "charge":
            filled = min(10, round(item.count / 2))
            bar = "▰" * filled + "▱" * (10 - filled)
            value = f"`{item.potency}×{item.count}` [{bar}] `{item.count}/20`"
        elif item.status_type == "poise":
            margin = max(1, 20 - item.potency // 10)
            value = f"`{item.potency}×{item.count}` • margem `d20 ≥ {margin}`"
        else:
            value = f"`{item.potency}×{item.count}`"
        rendered.append(
            f"{STATUS_ICONS[item.status_type]} {value}" if compact else
            f"{STATUS_ICONS[item.status_type]} **{STATUS_LABELS[item.status_type]}** {value}"
        )
    return separator.join(rendered) or ("" if compact else "`SEM STATUS`")


def trigger_damage_statuses(
    guild_id: int, target_kind: str, target_id: int, sanity: int | None,
) -> list[str]:
    lines = []
    for status_type in ("rupture", "sinking"):
        status = db.get_status(guild_id, target_kind, target_id, status_type)
        event = None if status is None else on_damage_taken(status, sanity=sanity)
        if event is None:
            continue
        db.set_status(guild_id, target_kind, target_id, status_type,
                      event.potency_after, event.count_after)
        if event.sanity_loss:
            if target_kind == "player":
                db.change_sp(guild_id, target_id, -event.sanity_loss)
            else:
                db.change_enemy_sp(target_id, -event.sanity_loss)
            lines.append(f"{STATUS_ICONS['sinking']} Sinking: **−{event.sanity_loss} SP** • Count `{event.count_after}`")
        elif event.damage:
            lines.append(f"{STATUS_ICONS[status_type]} {STATUS_LABELS[status_type]}: **+{event.damage} dano** • Count `{event.count_after}`")
    return lines


def resolve_hit_status_sequence(
    guild_id: int, actor_kind: str, actor_id: int,
    target_kind: str, target_id: int, target_sanity: int | None,
    skill: Skill, hits,
) -> tuple[list[str], list[str]]:
    """Resolve dano/status por moeda na ordem correta.

    Rupture e Sinking já presentes ativam antes dos efeitos On Hit da moeda.
    Logo, um status aplicado por uma moeda só poderá ativar na moeda seguinte.
    """
    effect_lines: list[str] = []
    status_lines: list[str] = []
    for hit in hits:
        if hit.power > 0:
            triggered = trigger_damage_statuses(
                guild_id, target_kind, target_id, target_sanity,
            )
            status_lines.extend(f"`MOEDA {hit.coin:02}` • {line}" for line in triggered)
            if target_sanity is not None and triggered:
                target_row = (
                    db.get_enemy_by_id(target_id)
                    if target_kind == "enemy"
                    else db.get_character(guild_id, target_id)
                )
                if target_row is not None:
                    target_sanity = target_row["sp"]
        coin_hits = [hit]
        applied = apply_skill_trigger(
            guild_id, actor_kind, actor_id, target_kind, target_id,
            skill, "on_hit", hits=coin_hits,
        )
        applied += apply_skill_trigger(
            guild_id, actor_kind, actor_id, target_kind, target_id,
            skill, "heads_hit", hits=coin_hits,
        )
        effect_lines.extend(f"`MOEDA {hit.coin:02}` • {line}" for line in applied)
    return effect_lines, status_lines


def trigger_bleed_action(
    guild_id: int, actor_kind: str, actor_id: int, actor_name: str,
    skill: Skill, coins: int | None = None,
) -> list[str]:
    if not skill.deals_damage:
        return []
    status = db.get_status(guild_id, actor_kind, actor_id, "bleed")
    rolled_coins = skill.coins if coins is None else coins
    event = None if status is None else on_action(status, rolled_coins)
    if event is None:
        return []
    db.set_status(guild_id, actor_kind, actor_id, "bleed",
                  event.potency_after, event.count_after)
    spent = status.count - event.count_after
    return [
        f"{STATUS_ICONS['bleed']} **{actor_name} sofreu {event.damage} de dano do próprio Bleed** • "
        f"{spent} moeda(s) ofensiva(s) • Quantidade `{event.count_after}`"
    ]


def clash_rolled_coins(result: ClashResult, side: str) -> int:
    """Conta cada moeda ofensiva efetivamente rolada em todas as rodadas do Clash."""
    if side not in {"left", "right"}:
        raise ValueError("O lado do Clash deve ser left ou right.")
    return sum(len(getattr(round_result, side).faces) for round_result in result.rounds)


def apply_poise_critical(
    guild_id: int, actor_kind: str, actor_id: int, damage: DamageResult,
    *, rng: random.Random | None = None,
) -> list[str]:
    poise = db.get_status(guild_id, actor_kind, actor_id, "poise")
    if poise is None or poise.potency <= 0 or poise.count <= 0 or damage.final_damage <= 0:
        return []
    rng = rng or random.Random()
    threat_margin = max(1, 20 - poise.potency // 10)
    eligible_hits = [hit for hit in damage.hits if not hit.unbreakable]
    critical_hits = []
    remaining_count = poise.count
    bonus_percent = poise.potency * 2
    bonus = 0
    for hit in eligible_hits:
        if remaining_count <= 0:
            break
        secret_roll = rng.randint(1, 20)
        if secret_roll >= threat_margin:
            critical_hits.append(hit.coin)
            bonus += round(hit.power * bonus_percent / 100)
            remaining_count -= 1
    if not critical_hits:
        return [
            f"{STATUS_ICONS['poise']} Poise: crítico não ativou • "
            f"margem secreta `d20 ≥ {threat_margin}` • Quantidade `{poise.count}` preservada"
        ]
    damage.final_damage += bonus
    db.set_status(guild_id, actor_kind, actor_id, "poise", poise.potency, remaining_count)
    return [
        f"{STATUS_ICONS['poise']} **ACERTO CRÍTICO** • moeda(s) "
        f"`{', '.join(map(str, critical_hits))}` • +{bonus_percent}% por crítico = "
        f"**+{bonus} dano apenas das moedas** • margem `d20 ≥ {threat_margin}` • "
        f"Quantidade `{remaining_count}`"
    ]


def round_status_embed(guild_id: int, events) -> discord.Embed | None:
    if not events:
        return None
    lines = []
    for owner_kind, owner_id, event in events:
        if owner_kind == "player":
            character = db.get_character(guild_id, owner_id)
            owner = f"<@{owner_id}> • **{character['name']}**" if character else f"<@{owner_id}>"
        else:
            enemy = db.get_enemy_by_id(owner_id)
            owner = f"**{enemy['name']}**" if enemy else f"Inimigo `#{owner_id}`"
        detail = f"**{event.damage} DE DANO RECEBIDO**" if event.damage else "Quantidade reduzida"
        lines.append(
            f"{STATUS_ICONS[event.status_type]} {owner}\n"
            f"└ **{STATUS_LABELS[event.status_type]}** • {detail} • Quantidade restante `{event.count_after}`"
        )
    embed = discord.Embed(
        title="〔 END OF ROUND // STATUS 〕",
        description="\n".join(lines)[:4000],
        color=ACCENT,
    )
    total_damage = sum(event.damage for _, _, event in events)
    if total_damage:
        embed.add_field(
            name="【 DANO DE STATUS NO FIM DO TURNO 】",
            value=f"## {total_damage}\nNeste turno, este total veio de Burn.",
            inline=False,
        )
    embed.set_footer(text="Potência × Quantidade restante também aparece no painel da batalha.")
    return embed


def revert_temporary_self_trigger(
    guild_id: int, actor_kind: str, actor_id: int, skill: Skill, trigger: str,
    *, remaining_coins: int | None = None,
) -> None:
    values = {"base_power": 0, "coin_power": 0, "clash_power": 0, "offense_level": 0, "final_power": 0}
    for effect in triggered_skill_effects(skill, trigger, remaining_coins=remaining_coins):
        if effect.effect_type in values:
            values[effect.effect_type] -= effect.value
    values["base_power"] += values["final_power"]
    if not any(values.values()):
        return
    if actor_kind == "player":
        db.add_effects(guild_id, actor_id, 0, values["base_power"], values["coin_power"], values["clash_power"], values["offense_level"])
    else:
        db.add_enemy_effects(actor_id, 0, values["base_power"], values["coin_power"], values["clash_power"], values["offense_level"])


def level_symbol(skill: Skill) -> str:
    return DEFENSE_LEVEL_ICON if skill.uses_defense_level else OFFENSE_LEVEL_ICON


def damage_embed(
    attacker_name: str, target_name: str, skill: Skill, result: DamageResult, *,
    unbreakable_followup: bool = False, shield: int = 0,
) -> discord.Embed:
    title = "〔 UNBREAKABLE FOLLOW-UP 〕" if unbreakable_followup else "〔 DAMAGE RESOLUTION 〕"
    embed = discord.Embed(title=title, color=ACCENT)
    embed.description = f"## {attacker_name}  ➜  {target_name}\n`{skill.name.upper()}`"
    lines = []
    for hit in result.hits:
        if hit.paralyzed:
            face = f"{EFFECT_PARALYZE} ~~{'HEADS' if hit.face else 'TAILS'}~~"
            note = " • Coin Power desativado"
        elif hit.active_unbreakable:
            face = COIN_UNBREAKABLE_HEADS if hit.face else COIN_UNBREAKABLE
            note = " • moeda inquebrável"
        elif hit.unbreakable:
            face = COIN_UNBREAKABLE
            note = " • moeda inquebrável rachada: valor 1"
        else:
            face = COIN_HEADS if hit.face else COIN_TAILS
            note = ""
        lines.append(f"`MOEDA {hit.coin:02}` {face} **{hit.power}**{note}")
    embed.add_field(name="ROLAGEM DAS MOEDAS RESTANTES", value="\n".join(lines), inline=False)
    embed.add_field(name="PODER APÓS AS MOEDAS", value=f"`{result.subtotal}`", inline=True)
    embed.add_field(
        name="AJUSTE DE NÍVEL",
        value=(f"{OFFENSE_LEVEL_ICON} `{result.offense_level}` − {DEFENSE_LEVEL_ICON} `{result.defense_level}`\n"
               f"`({result.offense_level} − {result.defense_level}) ÷ 3 = {result.level_modifier:+d}`"),
        inline=True,
    )
    if result.damage_percent or result.coin_damage_percent:
        percent_lines = []
        if result.damage_percent:
            percent_lines.append(f"**Skill inteira:** `{result.damage_percent:+g}%`")
        percent_lines.extend(
            f"**Moeda {coin:02}:** `{percent:+g}%`"
            for coin, percent in result.coin_damage_percent
        )
        embed.add_field(
            name="◇ MODIFICADOR DE DANO",
            value="\n".join(percent_lines),
            inline=False,
        )
    displayed_damage = max(0, result.final_damage - max(0, shield))
    if shield:
        embed.add_field(
            name="🛡️ ESCUDO DEFENSIVO",
            value=f"Dano `{result.final_damage}` − Escudo `{shield}` = **{displayed_damage}**",
            inline=False,
        )
    embed.add_field(name="〔 DANO FINAL 〕", value=f"## {displayed_damage}", inline=False)
    embed.set_footer(text="Moedas → ajuste de nível → porcentagem de dano → escudo.")
    return embed


def clashable_guard_win_embed(defender_name: str, target_name: str, final_power: int) -> discord.Embed:
    embed = discord.Embed(
        title="〔 CLASHABLE GUARD // VITÓRIA 〕",
        description=f"## 🛡️ {defender_name}\nA defesa venceu o Clash com Final Power **{final_power}**.",
        color=GOLD,
    )
    embed.add_field(
        name="◇ AJUSTE MANUAL DE STAGGER",
        value=f"Aumente o **Stagger Threshold** de **{target_name}** em **{final_power}**.",
        inline=False,
    )
    embed.set_footer(text="O bot apenas informa o valor; HP e Stagger permanecem sob controle do mestre.")
    return embed


async def attach_damage_gif(
    embed: discord.Embed, *, unbreakable_followup: bool = False,
) -> discord.File | None:
    url = UNBREAKABLE_FOLLOWUP_GIF if unbreakable_followup else DAMAGE_RESOLUTION_GIF
    if not url:
        return None
    filename = "unbreakable_followup.gif" if unbreakable_followup else "damage_resolution.gif"
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.read()
                content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                # Links compartilháveis do Tenor apontam para uma página. O bot
                # encontra o arquivo animado dentro dela antes de anexá-lo.
                page = data.decode("utf-8", errors="replace")
                page = page.replace(r"\u002F", "/").replace(r"\/", "/").replace(r"\u0026", "&")
                matches = re.findall(
                    r'https://media(?:1)?\.tenor\.com/[^"\'<> ]+?\.gif(?:\?[^"\'<> ]*)?',
                    page,
                )
                if not matches:
                    raise ValueError("A página do Tenor não informou um arquivo GIF direto")
                direct_url = matches[0]
                async with session.get(direct_url) as media_response:
                    media_response.raise_for_status()
                    data = await media_response.read()
                    media_type = media_response.headers.get("Content-Type", "").lower()
                if "image/" not in media_type:
                    raise ValueError(f"Tenor devolveu conteúdo inválido: {media_type or 'desconhecido'}")
                audit_logger.info("[GIF TENOR RESOLVIDO] página=%s | mídia=%s", url, direct_url)
            elif "image/" not in content_type:
                raise ValueError(f"URL não devolveu uma imagem: {content_type or 'tipo desconhecido'}")
        if len(data) > 10 * 1024 * 1024:
            raise ValueError(f"GIF excede 10 MB ({len(data)} bytes)")
        embed.set_image(url=f"attachment://{filename}")
        audit_logger.info("[GIF ANEXADO] arquivo=%s | tamanho=%d bytes", filename, len(data))
        return discord.File(io.BytesIO(data), filename=filename)
    except Exception as error:
        audit_logger.error("[ERRO AO CARREGAR GIF] url=%s | %s: %s", url, type(error).__name__, error)
        embed.set_image(url=url)
        return None


def resolve_unbreakable_followup(
    skill: Skill, sp: int, cracked_coins: int, offense_level: int,
    defense_level: int, modifiers: Modifiers,
) -> tuple[Skill, DamageResult]:
    fixed_coin_power = -1 if skill.coin_power < 0 else 1
    cracked_skill = Skill(
        skill.name, skill.base_power, fixed_coin_power, cracked_coins,
        skill.description, skill.skill_type, cracked_coins,
    )
    result = resolve_damage(
        cracked_skill, sp, cracked_coins, offense_level, defense_level,
        modifiers=modifiers,
    )
    return cracked_skill, result


def prediction_with_paralysis(
    left: Skill, left_sp: int, right: Skill, right_sp: int,
    left_mod: Modifiers, right_mod: Modifiers,
) -> Forecast:
    if left_mod.paralysis > 0 and right_mod.paralysis == 0:
        return Forecast(0.0, "HOPELESS", "Sem esperança — Paralisia detectada")
    if right_mod.paralysis > 0 and left_mod.paralysis == 0:
        return Forecast(1.0, "DOMINATING", "Dominante — alvo com Paralisia")
    return estimate_clash(
        left, left_sp, right, right_sp,
        left_modifiers=left_mod, right_modifiers=right_mod,
        simulations=5,
    )


def prediction_embed(
    left_name: str, left: Skill, right_name: str, right: Skill,
    forecast: Forecast, gif: str | None,
) -> discord.Embed:
    bars = max(0, min(10, round(forecast.win_chance * 10)))
    meter = "▰" * bars + "▱" * (10 - bars)
    embed = discord.Embed(title="〔 CLASH PREDICTION 〕", color=GOLD)
    embed.description = f"## {left_name}  ⟷  {right_name}\n`{left.name.upper()}` **VS** `{right.name.upper()}`"
    embed.add_field(
        name=f"⌁ {forecast.label}",
        value=f"`{meter}` **{forecast.win_chance:.0%}**\n*{forecast.label_pt}*",
        inline=False,
    )
    embed.set_footer(text="PREVISÃO VISUAL // não garante o resultado real")
    if gif:
        embed.set_image(url=gif)
    return embed

AUDIT_PATH = Path(__file__).with_name("clash_audit.log")
audit_logger = logging.getLogger("clash.audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False
INTERACTION_STARTED: dict[int, float] = {}
DISCORD_AUDIT_QUEUE: deque[str] = deque(maxlen=5000)
AUDIT_WORKER_TASK: asyncio.Task | None = None
MEDIA_WORKER_TASK: asyncio.Task | None = None


class AnsiAuditFormatter(logging.Formatter):
    RESET = "\033[0m"
    COLORS = {
        "ERROR": "\033[91m",
        "CLASH": "\033[93m",
        "DANO": "\033[95m",
        "ONLINE": "\033[92m",
        "PREVISÃO": "\033[96m",
        "COMANDO": "\033[94m",
        "BOTÃO": "\033[94m",
    }

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        if record.levelno >= logging.ERROR:
            color = self.COLORS["ERROR"]
        else:
            upper = record.getMessage().upper()
            color = next((value for key, value in self.COLORS.items() if key in upper), "\033[90m")
        return f"{color}{rendered}{self.RESET}"


class DiscordAuditQueueHandler(logging.Handler):
    """Copia cada registro para uma fila enviada ao canal de auditoria."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            DISCORD_AUDIT_QUEUE.append(self.format(record))
        except Exception:
            self.handleError(record)


if not audit_logger.handlers:
    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%d/%m/%Y %H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(AnsiAuditFormatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    file_handler = RotatingFileHandler(
        AUDIT_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    discord_handler = DiscordAuditQueueHandler()
    discord_handler.setFormatter(formatter)
    audit_logger.addHandler(console)
    audit_logger.addHandler(file_handler)
    audit_logger.addHandler(discord_handler)


def interaction_name(interaction: discord.Interaction) -> str:
    """Retorna um nome legível para comandos, botões, listas e formulários."""
    data = interaction.data or {}
    if interaction.type is discord.InteractionType.application_command:
        names = [str(data.get("name", "comando"))]
        options = data.get("options", [])
        while options and isinstance(options, list) and isinstance(options[0], dict):
            option = options[0]
            if "options" not in option:
                break
            names.append(str(option.get("name", "ação")))
            options = option.get("options", [])
        return "/" + " ".join(names)
    custom_id = str(data.get("custom_id", "componente"))
    if interaction.type is discord.InteractionType.modal_submit:
        return f"Formulário: {custom_id}"
    if interaction.type is discord.InteractionType.component:
        for row in getattr(interaction.message, "components", []) if interaction.message else []:
            for component in getattr(row, "children", []):
                if str(getattr(component, "custom_id", "")) != custom_id:
                    continue
                label = getattr(component, "label", None)
                placeholder = getattr(component, "placeholder", None)
                if label:
                    return f"Botão: {label}"
                if placeholder:
                    return f"Seleção: {placeholder}"
        readable = custom_id.replace(":", " › ").replace("_", " ").strip()
        return f"Interação: {readable}"
    return str(interaction.type).replace("InteractionType.", "").replace("_", " ").title()


def audit(
    interaction: discord.Interaction, action: str, details: str = "", *,
    display_name: str | None = None,
) -> None:
    guild = interaction.guild.name if interaction.guild else "DM"
    guild_id = interaction.guild_id or "DM"
    channel = getattr(interaction.channel, "name", "sem-canal")
    channel_id = interaction.channel_id or "DM"
    user = f"{interaction.user} ({interaction.user.id})"
    clean = details.replace("\n", " ")[:2000]
    started = INTERACTION_STARTED.get(interaction.id)
    elapsed = ""
    if started is not None and "RECEBID" not in action and "ENVIADO" not in action:
        elapsed = f" | duração_até_evento={(time.monotonic() - started) * 1000:.0f}ms"
    detail_lines = [line.strip() for line in clean.split(" | ") if line.strip()] or ["sem detalhes adicionais"]
    block = [
        f"╔════════════════════  {action}  ════════════════════╗",
        f"║ USUÁRIO    │ {user}",
        f"║ SERVIDOR   │ {guild} ({guild_id})",
        f"║ CANAL      │ {channel} ({channel_id})",
        f"║ AÇÃO       │ {display_name or interaction_name(interaction)}",
        f"║ INTERAÇÃO  │ {interaction.id}{elapsed}",
        "╟────────────────────────────────────────────────────────────",
    ]
    block.extend(f"║ DETALHE    │ {line}" for line in detail_lines)
    block.append("╚════════════════════════════════════════════════════════════")
    audit_logger.info("\n".join(block))


def error_code() -> str:
    return uuid.uuid4().hex[:8].upper()


def safe_interaction_data(interaction: discord.Interaction) -> str:
    """Resume nomes, opções e os valores informados nos formulários do RPG."""
    data = interaction.data or {}
    protected = {"token", "password", "senha", "secret", "segredo"}

    def option_text(options) -> list[str]:
        rendered = []
        for option in options if isinstance(options, list) else []:
            name = str(option.get("name", "opção"))
            if "options" in option:
                rendered.append(name)
                rendered.extend(option_text(option.get("options")))
                continue
            value = "[OCULTO]" if any(word in name.casefold() for word in protected) else option.get("value", "")
            rendered.append(f"{name}={str(value)[:80]}")
        return rendered

    if interaction.type is discord.InteractionType.application_command:
        return " ".join([str(data.get("name", "comando")), *option_text(data.get("options", []))])[:500]
    if interaction.type is discord.InteractionType.component:
        values = data.get("values", [])
        return f"id={data.get('custom_id', 'componente')} valores={str(values)[:160]}"
    if interaction.type is discord.InteractionType.modal_submit:
        fields = []
        for row in data.get("components", []):
            for component in row.get("components", []):
                field_id = str(component.get("custom_id", "campo"))
                value = str(component.get("value", "")).replace("\r", " ").replace("\n", " ↵ ")
                fields.append(f"{field_id}={value[:300]}")
        return f"id={data.get('custom_id', 'modal')} | " + " | ".join(fields)[:1500]
    return f"tipo={interaction.type}"


def disabled_commands() -> set[str]:
    if not CONTROL_STATE_PATH.exists():
        return set()
    try:
        raw = json.loads(CONTROL_STATE_PATH.read_text(encoding="utf-8"))
        return set(raw.get("disabled_commands", []))
    except (OSError, ValueError, TypeError):
        return set()


def terminal_roll(roll) -> str:
    disabled = roll.disabled or [False] * len(roll.faces)
    return "".join("P" if blocked else ("H" if face else "T") for face, blocked in zip(roll.faces, disabled))


def audit_clash_rounds(
    interaction: discord.Interaction, title: str,
    left_name: str, right_name: str, result,
    left_skill: Skill | None = None, right_skill: Skill | None = None,
    left_mod: Modifiers | None = None, right_mod: Modifiers | None = None,
) -> None:
    guild = interaction.guild.name if interaction.guild else "DM"
    lm, rm = left_mod or Modifiers(), right_mod or Modifiers()
    level_difference = lm.level - rm.level
    left_level_bonus = max(0, level_difference // 3)
    right_level_bonus = max(0, (-level_difference) // 3)
    audit_logger.info("╔══════════════════════ %s ══════════════════════╗", title)
    audit_logger.info("║ INTERAÇÃO %s | SERVIDOR %s", interaction.id, guild)
    audit_logger.info("║ %s  VS  %s", left_name, right_name)
    if left_skill and right_skill:
        audit_logger.info(
            "║ ESQUERDA: %s | Base %d%+d | Coin %d%+d | Clash %+d | Nível %d (%+d)",
            left_skill.name, left_skill.base_power, lm.base_power, left_skill.coin_power,
            lm.coin_power if left_skill.coin_power > 0 else 0, lm.clash_power, lm.level, left_level_bonus,
        )
        audit_logger.info(
            "║ DIREITA : %s | Base %d%+d | Coin %d%+d | Clash %+d | Nível %d (%+d)",
            right_skill.name, right_skill.base_power, rm.base_power, right_skill.coin_power,
            rm.coin_power if right_skill.coin_power > 0 else 0, rm.clash_power, rm.level, right_level_bonus,
        )
        audit_logger.info("╟──────────────────── CONTAS POR RODADA ────────────────────")
    for rd in result.rounds[-10:]:
        arrow = {"left": "◀", "right": "▶", "tie": "="}[rd.result]
        if left_skill and right_skill:
            left_heads = sum(face and not blocked for face, blocked in zip(rd.left.faces, rd.left.disabled))
            right_heads = sum(face and not blocked for face, blocked in zip(rd.right.faces, rd.right.disabled))
            left_coin = left_skill.coin_power + (lm.coin_power if left_skill.coin_power > 0 else 0)
            right_coin = right_skill.coin_power + (rm.coin_power if right_skill.coin_power > 0 else 0)
            audit_logger.info("║ R%02d │ %s %s %s", rd.number, left_name, arrow, right_name)
            audit_logger.info(
                "║     │ %s: (%d %+d) + %d×(%d %+d) + nível %+d + clash %+d = %d | moedas=%s%s",
                left_name, left_skill.base_power, lm.base_power, left_heads,
                left_skill.coin_power, lm.coin_power if left_skill.coin_power > 0 else 0,
                left_level_bonus, lm.clash_power, rd.left.power, terminal_roll(rd.left),
                " | INQUEBRÁVEL ATINGIDA" if rd.left_unbreakable_broken else "",
            )
            audit_logger.info(
                "║     │ %s: (%d %+d) + %d×(%d %+d) + nível %+d + clash %+d = %d | moedas=%s%s",
                right_name, right_skill.base_power, rm.base_power, right_heads,
                right_skill.coin_power, rm.coin_power if right_skill.coin_power > 0 else 0,
                right_level_bonus, rm.clash_power, rd.right.power, terminal_roll(rd.right),
                " | INQUEBRÁVEL ATINGIDA" if rd.right_unbreakable_broken else "",
            )
        else:
            audit_logger.info(
                "║ R%02d  %-12s %4d  %s  %-4d %s",
                rd.number, terminal_roll(rd.left), rd.left.power, arrow,
                rd.right.power, terminal_roll(rd.right),
            )
    if len(result.rounds) > 10:
        audit_logger.info("║ … %d rodada(s) anterior(es) omitida(s)", len(result.rounds) - 10)
    audit_logger.info(
        "║ VENCEDOR: %s | moedas finais: %d × %d",
        result.winner.upper(), result.left_coins, result.right_coins,
    )
    audit_logger.info("╚════════════════════════════════════════════════════════════")


def audit_damage_calculation(
    interaction: discord.Interaction, attacker: str, target: str,
    skill: Skill, result: DamageResult, *, shield: int = 0,
) -> None:
    audit_logger.info("╔════════════════════ DAMAGE RESOLUTION ════════════════════╗")
    audit_logger.info("║ INTERAÇÃO %s | %s → %s | SKILL %s", interaction.id, attacker, target, skill.name)
    audit_logger.info("╟──────────────────── ROLAGEM DAS MOEDAS ───────────────────")
    previous = skill.base_power
    for hit in result.hits:
        face = "HEADS" if hit.face else "TAILS"
        flags = []
        if hit.paralyzed: flags.append("PARALISADA")
        if hit.unbreakable: flags.append("INQUEBRÁVEL RACHADA")
        if hit.active_unbreakable: flags.append("INQUEBRÁVEL")
        delta = hit.power - previous
        audit_logger.info(
            "║ MOEDA %02d │ %-5s | anterior %d %+d = %d%s",
            hit.coin, face, previous, delta, hit.power,
            f" | {', '.join(flags)}" if flags else "",
        )
        previous = hit.power
    after_shield = max(0, result.final_damage - max(0, shield))
    audit_logger.info("╟────────────────────── CONTA FINAL ────────────────────────")
    audit_logger.info("║ PODER FINAL DAS MOEDAS │ %d", result.subtotal)
    audit_logger.info(
        "║ AJUSTE DE NÍVEL        │ (%d − %d) ÷ 3 = %+d",
        result.offense_level, result.defense_level, result.level_modifier,
    )
    audit_logger.info(
        "║ MODIFICADOR INTERNO    │ %d × (100%% %+g%%) = %d",
        result.damage_before_percent, result.damage_percent,
        result.damage_before_percent + result.percent_modifier,
    )
    if result.coin_damage_percent:
        audit_logger.info(
            "║ BÔNUS POR MOEDA        │ %s = %+d dano",
            ", ".join(f"moeda {coin:02} {percent:+g}%" for coin, percent in result.coin_damage_percent),
            result.coin_percent_modifier,
        )
    audit_logger.info("║ ANTES DO ESCUDO        │ %d", result.final_damage)
    audit_logger.info("║ ESCUDO                 │ %d", shield)
    audit_logger.info("║ DANO EXIBIDO           │ max(0, %d − %d) = %d", result.final_damage, shield, after_shield)
    audit_logger.info("╚════════════════════════════════════════════════════════════")


def clash_gif_for(*skills: Skill) -> str | None:
    path = Path(__file__).with_name("clash_gifs.txt")
    if not path.exists():
        return None
    mapping: dict[str, str] = {}
    fallback: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            kind, url = line.split("=", 1)
            mapping.setdefault(kind.strip(), url.strip())
        else:
            fallback.append(line)
    priority = ("clashable_guard", "clashable_counter", "assist_defense", "guard", "evade", "counter", "attack")
    present = {skill.skill_type for skill in skills}
    for kind in priority:
        if kind in present and mapping.get(kind):
            return mapping[kind]
    return fallback[0] if fallback else None


def gid(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise app_commands.CheckFailure("Use este comando dentro de um servidor.")
    return interaction.guild_id


def render_custom_emojis(interaction: discord.Interaction, text: str) -> str:
    """Mantém emojis acessíveis e troca externos bloqueados por símbolos legíveis."""
    fallback = {
        "EP": "⚡", "EAU": "🔺", "EAD": "🔻", "PCB": "🟡", "PCD": "⚫",
        "ECU": "🔼", "ECD": "🔽", "OLU": "⬆️", "OLD": "⬇️",
        "EBu": "🔥", "EBl": "🩸", "ETr": "🟨", "ERu": "💥",
        "ESi": "🌊", "EPo": "🎯", "ECh": "🔋", "ETB": "💢",
    }
    guild = interaction.guild
    member = guild.me if guild else None
    can_external = bool(
        guild and member and interaction.channel
        and interaction.channel.permissions_for(member).external_emojis
    )

    def replace_emoji(match: re.Match[str]) -> str:
        name, emoji_id = match.group(1), int(match.group(2))
        emoji = interaction.client.get_emoji(emoji_id)
        if emoji is not None and (guild is None or emoji.guild_id == guild.id or can_external):
            return str(emoji)
        return fallback.get(name, "◆")

    return re.sub(r"<a?:([A-Za-z0-9_]+):(\d+)>", replace_emoji, text)


async def store_character_image(
    interaction: discord.Interaction, attachment: discord.Attachment, owner_id: int, name: str,
) -> str:
    """Copia um anexo para o canal permanente de mídia e retorna sua URL."""
    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        raise ValueError("O anexo precisa ser uma imagem.")
    if attachment.size > 8 * 1024 * 1024:
        raise ValueError("A imagem deve ter no máximo 8 MB.")
    channel = interaction.client.get_channel(APPEARANCE_CHANNEL_ID)
    if channel is None:
        channel = await interaction.client.fetch_channel(APPEARANCE_CHANNEL_ID)
    data = await attachment.read()
    message = await channel.send(
        content=(
            f"🖼️ **ARQUIVO DE APARÊNCIA**\nTipo: `player` • Servidor: `{gid(interaction)}` "
            f"• Registro: `{owner_id}` • Nome: **{name}**"
        ),
        file=discord.File(io.BytesIO(data), filename=attachment.filename),
    )
    if not message.attachments:
        raise RuntimeError("O canal de mídia não devolveu o anexo enviado.")
    return message.attachments[0].url


def appearance_embed_color(appearance) -> discord.Color:
    if appearance is None:
        return ACCENT
    try:
        value = str(appearance["accent_color"] or "").strip().lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            return ACCENT
        return discord.Color(int(value, 16))
    except (KeyError, TypeError, ValueError):
        return ACCENT


def character_embed(row, member: discord.abc.User) -> discord.Embed:
    appearance = db.get_appearance(row["guild_id"], "player", row["user_id"])
    subtitle = f"\n*{appearance['subtitle']}*" if appearance and appearance["subtitle"] else ""
    embed = discord.Embed(
        title=f"〔 LCB // REGISTRO DE SINNER 〕",
        description=f"## {row['name']}{subtitle}\n`IDENTIDADE VINCULADA: {member.display_name}`",
        color=appearance_embed_color(appearance),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if appearance and appearance["image_url"].startswith(("http://", "https://")):
        if appearance["image_mode"] == "thumbnail":
            embed.set_thumbnail(url=appearance["image_url"])
        elif appearance["image_mode"] == "banner":
            embed.set_image(url=appearance["image_url"])
    if appearance and appearance["footer_text"]:
        embed.set_footer(text=appearance["footer_text"])
    embed.add_field(name="◈ SANIDADE", value=f"```{row['sp']:+d} SP\n{heads_chance(row['sp']):.0%} HEADS```")
    embed.add_field(name="◆ OFFENSE LEVEL", value=f"```{row['offense_level']}```")
    embed.add_field(name="◇ DEFENSE LEVEL", value=f"```{row['defense_level']}```")
    if row["charge_potency_enabled"]:
        embed.add_field(
            name=f"{STATUS_ICONS['charge']} CHARGE POTENCY",
            value=f"```ATIVA • CONSUMO {row['charge_spent']}/10```",
            inline=False,
        )
    effects = []
    if row["paralysis"]:
        effects.append(f"{EFFECT_PARALYZE} Paralisia **{row['paralysis']}**")
    if row["base_power_mod"]:
        icon = effect_icon(row["base_power_mod"], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)
        effects.append(f"{icon} Base Power **{row['base_power_mod']:+d}**")
    if row["coin_power_mod"]:
        icon = effect_icon(row["coin_power_mod"], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)
        effects.append(f"{icon} Coin Power **{row['coin_power_mod']:+d}**")
    if row["clash_power_mod"]:
        icon = effect_icon(row["clash_power_mod"], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)
        effects.append(f"{icon} Clash Power **{row['clash_power_mod']:+d}**")
    if row["offense_level_mod"]:
        icon = effect_icon(row["offense_level_mod"], EFFECT_OFFENSE_UP, EFFECT_OFFENSE_DOWN)
        effects.append(f"{icon} Offense Level **{row['offense_level_mod']:+d}**")
    if row["defense_level_mod"]:
        direction = "🔺" if row["defense_level_mod"] > 0 else "🔻"
        effects.append(f"{DEFENSE_LEVEL_ICON}{direction} Defense Level **{row['defense_level_mod']:+d}**")
    embed.add_field(name="▰ MODIFICADORES DO PRÓXIMO CLASH", value="\n".join(effects) or "`NENHUMA ANOMALIA DETECTADA`", inline=False)
    statuses = [
        status for status in db.list_statuses(row["guild_id"], "player", row["user_id"])
        if status.status_type not in {"devotion_repressed", "bloodfiend", "bloodbag"}
    ]
    if statuses:
        embed.add_field(
            name="〔 STATUS // POTÊNCIA × QUANTIDADE 〕",
            value="\n".join(
                f"{STATUS_ICONS[status.status_type]} **{STATUS_LABELS[status.status_type]}** "
                f"• Potência `{status.potency}` • Quantidade `{status.count}`"
                for status in statuses
            ),
            inline=False,
        )
    embed.set_footer(text="LIMBUS // Base e Coin expiram após o Clash • Paralisia é consumida por moeda")
    return embed


def skills_embed(skills: list[Skill], title: str = "Skills") -> discord.Embed:
    embed = discord.Embed(title=f"🪙 {title}", color=discord.Color.gold())
    if not skills:
        embed.description = "Nenhuma skill cadastrada ainda."
    for skill in skills[:20]:
        low, high = skill.range_with()
        layout = "".join(
            COIN_UNBREAKABLE if kind == "unbreakable" else COIN_ACTIVE
            for kind in skill.coin_layout
        )
        value = (
            f"{layout} **Moedas [{skill.coin_power:+d}]**\n"
            f"`[{skill.base_power}]` ⚔️ **{skill.name}**\n"
            f"`{SKILL_TYPE_LABELS[skill.skill_type].upper()}` • Faixa `{low}–{high}`"
        )
        if skill.description:
            value += f"\n{skill.description}"
        if skill.effects:
            effect_lines = [
                f"{'`'+str(effect.coin).zfill(2)+'` › ' if effect.coin else ''}"
                f"**[{TRIGGER_LABELS[effect.trigger]}]** {builder_effect_text(effect)}"
                for effect in skill.effects
            ]
            value += "\n**◇ EFEITOS**\n" + "\n".join(effect_lines)
        chunks, current = [], ""
        for line in value.splitlines():
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > 1000 and current:
                chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        for index, chunk in enumerate(chunks):
            if len(embed.fields) >= 25:
                break
            field_name = f"〔 {skill.name} 〕" if index == 0 else "◇ EFEITOS // CONTINUAÇÃO"
            embed.add_field(name=field_name, value=chunk[:1024], inline=False)
    return embed


async def show_defense_resolution(
    interaction: discord.Interaction,
    attacker_name: str, attack: Skill, attack_sp: int, attack_mod: Modifiers,
    defender_name: str, defense: Skill, defense_sp: int, defense_mod: Modifiers,
    attacker_defense_level: int,
) -> None:
    await interaction.response.defer()
    result = resolve_defense(
        attack, attack_sp, defense, defense_sp,
        attack_modifiers=attack_mod, defense_modifiers=defense_mod,
    )
    embed = discord.Embed(title="〔 DEFENSIVE MANEUVER 〕", color=GOLD)
    embed.description = (
        f"## {attacker_name}  ⟷  {defender_name}\n"
        f"`{attack.name.upper()}` **VS** `{defense.name.upper()}`\n"
        f"**{SKILL_TYPE_LABELS[defense.skill_type]}**"
    )
    if result.kind == "guard":
        ar, dr = result.attack_rolls[0], result.defense_rolls[0]
        face = "HEADS" if dr.faces[0] else "TAILS"
        embed.add_field(name="TESTE DE DEFESA", value=f"Moeda defensiva: **{face}** {roll_icons(dr)}", inline=False)
        embed.add_field(
            name="RESULTADO",
            value=f"🛡️ **Escudo gerado: {dr.power}**\nO valor será subtraído do dano do ataque.",
            inline=False,
        )
    elif result.kind == "evade":
        lines = []
        for index, (ar, dr) in enumerate(zip(result.attack_rolls, result.defense_rolls), 1):
            icon = "✅" if dr.power >= ar.power else "❌"
            lines.append(f"`MOEDA {index}` {roll_icons(ar)} **{ar.power}** vs {roll_icons(dr)} **{dr.power}** {icon}")
        embed.add_field(name="SEQUÊNCIA DE EVASÃO", value="\n".join(lines), inline=False)
        embed.add_field(name="RESULTADO", value=f"💨 **{result.summary}**", inline=False)
    else:
        ar, cr = result.attack_rolls[0], result.counter_roll
        embed.add_field(name="ATAQUE RECEBIDO", value=f"**{ar.power}** {roll_icons(ar)}", inline=True)
        face = "HEADS" if cr.faces[0] else "TAILS"
        embed.add_field(name="MOEDA DE COUNTER", value=f"**{face}** {roll_icons(cr)}", inline=True)
        embed.add_field(name="RESULTADO", value="↩️ **Moeda rolada; não há sucesso ou falha automática.**\nNão houve Clash nem alteração de SP.", inline=False)
    gif = clash_gif_for(attack, defense)
    if gif:
        embed.set_image(url=gif)
    embed.set_footer(text="Defesas comuns não quebram moedas de Clash e não alteram sanidade.")
    audit(interaction, "DEFESA RESOLVIDA", f"{attacker_name} vs {defender_name}; tipo={defense.skill_type}; resultado={result.summary}")
    await interaction.edit_original_response(embed=embed)
    if result.kind == "guard":
        await asyncio.sleep(1.0)
        attack_damage = resolve_damage(
            attack, attack_sp, attack.coins, attack_mod.level, defense_mod.level,
            modifiers=attack_mod, faces=result.attack_rolls[0].faces,
        )
        shield = result.defense_rolls[0].power
        reduced_damage = max(0, attack_damage.final_damage - shield)
        audit(
            interaction, "ESCUDO DE GUARD",
            f"{defender_name}; escudo={shield}; dano={attack_damage.final_damage}->{reduced_damage}",
        )
        audit_damage_calculation(
            interaction, attacker_name, defender_name, attack, attack_damage, shield=shield,
        )
        guard_embed = damage_embed(
            attacker_name, defender_name, attack, attack_damage, shield=shield,
        )
        guard_gif = await attach_damage_gif(guard_embed)
        await interaction.followup.send(
            embed=guard_embed, files=[guard_gif] if guard_gif else [],
        )
    if result.kind == "counter" and result.counter_roll is not None:
        await asyncio.sleep(1.25)
        counter_damage = resolve_damage(
            defense, defense_sp, 1, defense_mod.level, attacker_defense_level,
            modifiers=defense_mod, faces=result.counter_roll.faces,
        )
        audit(interaction, "DANO DE COUNTER", f"{defender_name} -> {attacker_name}; dano={counter_damage.final_damage}")
        audit_damage_calculation(
            interaction, defender_name, attacker_name, defense, counter_damage,
        )
        counter_embed = damage_embed(defender_name, attacker_name, defense, counter_damage)
        counter_gif = await attach_damage_gif(counter_embed)
        await interaction.followup.send(embed=counter_embed, files=[counter_gif] if counter_gif else [])


async def report_component_error(interaction: discord.Interaction, error: Exception, component: str) -> None:
    code = error_code()
    audit_logger.error(
        "[ERRO DE INTERFACE %s] interação=%s | componente=%s | servidor=%s | canal=%s | "
        "usuário=%s (%s) | dados=%s | tipo=%s | detalhe=%s\n%s",
        code, interaction.id, component, interaction.guild_id, interaction.channel_id,
        interaction.user, interaction.user.id, safe_interaction_data(interaction),
        type(error).__name__, error,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    try:
        await sender(
            f"Essa ação falhou. Informe o código `{code}` ao mestre; os detalhes estão no log.",
            ephemeral=True,
        )
    except (discord.HTTPException, aiohttp.ClientError, OSError, asyncio.TimeoutError) as send_error:
        audit_logger.error("[ERRO AO AVISAR FALHA DE INTERFACE] %s", send_error)


class LoggedView(discord.ui.View):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        audit(interaction, "INTERFACE RECEBIDA", safe_interaction_data(interaction))
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        await report_component_error(interaction, error, getattr(item, "custom_id", type(item).__name__))


class LoggedModal(discord.ui.Modal):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        audit(
            interaction, "FORMULÁRIO RECEBIDO",
            f"título={self.title} | {safe_interaction_data(interaction)}",
            display_name=f"Formulário: {self.title}",
        )
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await report_component_error(interaction, error, self.title)


def parse_skill_values(raw: str) -> tuple[int, int, int, int]:
    values = [int(item.strip()) for item in raw.split(",")]
    if len(values) == 3:
        values.append(0)
    if len(values) != 4:
        raise ValueError("quantidade de campos")
    return values[0], values[1], values[2], values[3]


class SkillModal(LoggedModal, title="Criar ou editar skill"):
    name = discord.ui.TextInput(label="Nome", max_length=50)
    values = discord.ui.TextInput(label="Base, Coin, Moedas, Inquebráveis", placeholder="Exemplo: 4, 3, 3, 1", max_length=40)
    skill_type = discord.ui.TextInput(label="Tipo", placeholder="normal, defesa, counter, evasiva...", default="normal", max_length=30)
    description = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False, max_length=300)
    effects = discord.ui.TextInput(
        label="Efeitos (gatilho:efeito:valor:moeda)", required=False,
        placeholder="on_hit:paralysis:1:2", style=discord.TextStyle.paragraph, max_length=600,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            base, coin, coins, unbreakable = parse_skill_values(str(self.values))
            kind = SKILL_TYPE_ALIASES.get(str(self.skill_type).strip().lower())
            if kind is None:
                raise ValueError("tipo")
            effects = parse_skill_effects(str(self.effects))
            skill = Skill(str(self.name), base, coin, coins, str(self.description), kind, unbreakable, effects)
        except (ValueError, TypeError):
            await interaction.response.send_message("Use: Base, Coin Power, Moedas, Inquebráveis. Exemplo: `4, 3, 3, 1`.", ephemeral=True)
            return
        if db.get_character(gid(interaction), interaction.user.id) is None:
            await interaction.response.send_message("Crie uma ficha primeiro com `/personagem criar`.", ephemeral=True)
            return
        db.save_skill(interaction.guild_id, interaction.user.id, skill)
        await interaction.response.send_message(embed=skills_embed([skill], "Skill salva"), ephemeral=True)


class EditSkillModal(LoggedModal):
    def __init__(self, skill: Skill) -> None:
        super().__init__(title=f"Editar: {skill.name[:35]}")
        self.old_name = skill.name
        self.name_input = discord.ui.TextInput(label="Nome", default=skill.name, max_length=50)
        self.values_input = discord.ui.TextInput(
            label="Base, Coin, Moedas, Inquebráveis",
            default=f"{skill.base_power}, {skill.coin_power}, {skill.coins}, {skill.unbreakable_coins}", max_length=40,
        )
        self.type_input = discord.ui.TextInput(
            label="Tipo", default=skill.skill_type, max_length=30,
            placeholder="normal, defesa, counter, evasiva...",
        )
        self.description_input = discord.ui.TextInput(
            label="Descrição", default=skill.description, required=False,
            style=discord.TextStyle.paragraph, max_length=300,
        )
        self.effects_input = discord.ui.TextInput(
            label="Efeitos (gatilho:efeito:valor:moeda)",
            default=format_skill_effects(skill.effects), required=False,
            placeholder="on_hit:paralysis:1:2", style=discord.TextStyle.paragraph, max_length=600,
        )
        for item in (self.name_input, self.values_input, self.type_input, self.description_input, self.effects_input):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            base, coin, coins, unbreakable = parse_skill_values(str(self.values_input))
            raw_type = str(self.type_input).strip().lower()
            kind = SKILL_TYPE_ALIASES.get(raw_type, raw_type if raw_type in SKILL_TYPE_LABELS else None)
            if kind is None:
                raise ValueError("tipo")
            effects = parse_skill_effects(str(self.effects_input))
            skill = Skill(str(self.name_input), base, coin, coins, str(self.description_input), kind, unbreakable, effects)
        except (ValueError, TypeError):
            await interaction.response.send_message("Confira Base, Coin, Moedas, Inquebráveis e o tipo da skill.", ephemeral=True)
            return
        server = gid(interaction)
        if skill.name.casefold() != self.old_name.casefold():
            db.delete_skill(server, interaction.user.id, self.old_name)
        db.save_skill(server, interaction.user.id, skill)
        audit(interaction, "SKILL EDITADA", f"{self.old_name} -> {skill.name}; tipo={kind}")
        await interaction.response.edit_message(
            embed=skills_embed(db.list_skills(server, interaction.user.id), "Skills atualizadas"),
            view=SkillsView(),
        )


class SkillEditSelect(discord.ui.Select):
    def __init__(self, skills: list[Skill]) -> None:
        options = [discord.SelectOption(
            label=s.name[:100], value=s.name,
            description=SKILL_TYPE_LABELS[s.skill_type][:100],
        ) for s in skills[:25]]
        super().__init__(placeholder="Escolha uma skill para editar", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        skill = db.get_skill(gid(interaction), interaction.user.id, self.values[0])
        if skill is None:
            await interaction.response.send_message("Skill não encontrada.", ephemeral=True)
            return
        builder = SkillBuilderView(interaction.user.id, skill)
        await interaction.response.edit_message(embed=builder.build_embed(), view=builder)


class SkillEditView(LoggedView):
    def __init__(self, skills: list[Skill]) -> None:
        super().__init__(timeout=600)
        self.add_item(SkillEditSelect(skills))


class SkillDeleteSelect(discord.ui.Select):
    def __init__(self, skills: list[Skill]) -> None:
        super().__init__(
            placeholder="Escolha a skill que será excluída",
            options=[discord.SelectOption(label=s.name[:100], value=s.name, description=SKILL_TYPE_LABELS[s.skill_type][:100]) for s in skills[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        removed = db.delete_skill(gid(interaction), interaction.user.id, name)
        audit(interaction, "SKILL EXCLUÍDA", name if removed else f"não encontrada: {name}")
        await interaction.response.edit_message(
            embed=skills_embed(db.list_skills(gid(interaction), interaction.user.id), "Skills atualizadas"),
            view=SkillsView(),
        )


class SkillDeleteView(LoggedView):
    def __init__(self, skills: list[Skill]) -> None:
        super().__init__(timeout=600)
        self.add_item(SkillDeleteSelect(skills))


class SkillsView(LoggedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Criar skill", emoji="✨", style=discord.ButtonStyle.success)
    async def create_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        builder = SkillBuilderView(interaction.user.id)
        await interaction.response.edit_message(embed=builder.build_embed(), view=builder)

    @discord.ui.button(label="Editar skill", emoji="✏️", style=discord.ButtonStyle.primary)
    async def edit_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        skills = db.list_skills(gid(interaction), interaction.user.id)
        if not skills:
            await interaction.response.send_message("Você ainda não possui skills.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=skills_embed(skills, "Escolha uma skill"), view=SkillEditView(skills)
        )

    @discord.ui.button(label="Excluir skill", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        skills = db.list_skills(gid(interaction), interaction.user.id)
        if not skills:
            await interaction.response.send_message("Você ainda não possui skills.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=skills_embed(skills, "Escolha a skill que será excluída"), view=SkillDeleteView(skills)
        )

    @discord.ui.button(label="Skill de teste", emoji="🧪", style=discord.ButtonStyle.secondary)
    async def test_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if db.get_character(gid(interaction), interaction.user.id) is None:
            await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
            return
        skill = Skill(
            "Golpe de Teste", 4, 3, 3,
            "Skill padrão para testar rolagens, previsões e Clashes.", "attack",
        )
        db.save_skill(gid(interaction), interaction.user.id, skill)
        audit(interaction, "SKILL TESTE", "Golpe de Teste adicionado pela oficina")
        await interaction.response.edit_message(
            embed=skills_embed(db.list_skills(gid(interaction), interaction.user.id), "〔 SKILL WORKSHOP 〕"),
            view=SkillsView(),
        )

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh_skills(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=skills_embed(db.list_skills(gid(interaction), interaction.user.id), "〔 SKILL WORKSHOP 〕"),
            view=self,
        )


class LevelsModal(LoggedModal, title="Editar níveis"):
    offense = discord.ui.TextInput(label="Offense Level", placeholder="Exemplo: 12", max_length=6)
    defense = discord.ui.TextInput(label="Defense Level", placeholder="Exemplo: 12", max_length=6)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            offense, defense = int(str(self.offense)), int(str(self.defense))
        except ValueError:
            await interaction.response.send_message("Os níveis precisam ser números inteiros.", ephemeral=True)
            return
        server = gid(interaction)
        row = db.set_levels(server, interaction.user.id, offense, defense)
        if row is None:
            await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
            return
        audit(interaction, "NÍVEIS EDITADOS", f"OL={offense}, DL={defense}")
        await interaction.response.edit_message(embed=character_embed(row, interaction.user), view=CharacterView())


CHARACTER_EFFECTS = {
    "paralysis": ("Paralisia", EFFECT_PARALYZE, "Somente valores positivos; consumida por moeda."),
    "base": ("Base Power Up/Down", EFFECT_ATTACK_UP, "Altera a Base no próximo Clash."),
    "coin": ("Coin Power Up/Down", EFFECT_PLUS_COIN_BOOST, "Altera Plus Coins no próximo Clash."),
    "clash": ("Clash Power Up/Down", EFFECT_CLASH_UP, "Altera apenas o poder de Clash."),
    "offense": ("Offense Level Up/Down", EFFECT_OFFENSE_UP, "Use positivo para Up e negativo para Down."),
    "defense": ("Defense Level Up/Down", DEFENSE_LEVEL_ICON, "Afeta defesa, evasão e dano recebido."),
}


class CharacterEffectValueModal(LoggedModal, title="Aplicar efeito à ficha"):
    def __init__(self, editor: "CharacterEffectsView") -> None:
        super().__init__()
        self.editor = editor
        label = CHARACTER_EFFECTS[editor.selected_effect][0]
        self.value_input = discord.ui.TextInput(
            label=label[:45], placeholder="Exemplo: 3 para Up ou -3 para Down",
            max_length=5,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(str(self.value_input).strip())
            if self.editor.selected_effect == "paralysis" and value < 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Informe um número inteiro. Paralisia não aceita valor negativo.", ephemeral=True,
            )
            return
        values = {key: 0 for key in CHARACTER_EFFECTS}
        values[self.editor.selected_effect] = value
        row = db.add_effects(
            gid(interaction), interaction.user.id,
            values["paralysis"], values["base"], values["coin"],
            values["clash"], values["offense"], values["defense"],
        )
        if row is None:
            await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
            return
        label = CHARACTER_EFFECTS[self.editor.selected_effect][0]
        audit(interaction, "EFEITO DE FICHA", f"{label} {value:+d}")
        await interaction.response.edit_message(
            embed=self.editor.build_embed(interaction, row), view=self.editor,
        )


class CharacterEffectSelect(discord.ui.Select):
    def __init__(self, editor: "CharacterEffectsView") -> None:
        self.editor = editor
        super().__init__(
            placeholder="Escolha o modificador que será aplicado",
            options=[discord.SelectOption(
                label=label, value=key, emoji=icon, description=description[:100],
                default=key == editor.selected_effect,
            ) for key, (label, icon, description) in CHARACTER_EFFECTS.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.editor.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        self.editor.selected_effect = self.values[0]
        self.editor.refresh_select()
        row = db.get_character(gid(interaction), interaction.user.id)
        await interaction.response.edit_message(
            embed=self.editor.build_embed(interaction, row), view=self.editor,
        )


class CharacterEffectsView(LoggedView):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=600)
        self.owner_id = owner_id
        self.selected_effect = "paralysis"
        self.refresh_select()

    def refresh_select(self) -> None:
        buttons = [item for item in self.children if isinstance(item, discord.ui.Button)]
        self.clear_items()
        self.add_item(CharacterEffectSelect(self))
        for button in buttons:
            self.add_item(button)

    def build_embed(self, interaction: discord.Interaction, row) -> discord.Embed:
        embed = character_embed(row, interaction.user)
        label, icon, description = CHARACTER_EFFECTS[self.selected_effect]
        embed.title = "〔 LCB // EDITOR DE EFEITOS 〕"
        embed.add_field(
            name="◆ EFEITO SELECIONADO",
            value=f"{icon} **{label}**\n{description}\n\n`POSITIVO = UP` • `NEGATIVO = DOWN`",
            inline=False,
        )
        embed.set_footer(text="Escolha o efeito • informe somente o valor • aplique • volte à ficha")
        return embed

    @discord.ui.button(label="Aplicar efeito", emoji="➕", style=discord.ButtonStyle.danger, row=1)
    async def apply(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        await interaction.response.send_modal(CharacterEffectValueModal(self))

    @discord.ui.button(label="Voltar à ficha", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        await interaction.response.edit_message(embed=character_embed(row, interaction.user), view=CharacterView())

    @discord.ui.button(label="Status principais", emoji="🧪", style=discord.ButtonStyle.primary, row=1)
    async def statuses(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        editor = CharacterStatusView(self.owner_id)
        await interaction.response.edit_message(embed=editor.build_embed(interaction), view=editor)


STATUS_DESCRIPTIONS = {
    "burn": "Fim da rodada: dano = Potência; Quantidade −1.",
    "bleed": "Por moeda ofensiva rolada pelo portador: sofre dano = Potência e gasta 1 Quantidade.",
    "tremor": "Tremor Burst: Stagger Threshold manual += Potência; Quantidade −1/rodada.",
    "rupture": "Ao receber dano: dano adicional = Potência; Quantidade −1.",
    "sinking": "Ao receber dano: perde SP = Potência; em −45 vira dano; Quantidade −1.",
    "poise": "Margem padrão 20 no d20; Potência÷10 reduz a margem. Cada crítico ganha Potência×2% somente no dano da moeda e gasta 1 Quantidade.",
    "charge": "Recurso de skills; efeitos podem exigir e consumir Quantidade (máximo 20).",
    "special_condition": "Contador genérico para passivas e recursos personalizados; pode escalar ou ser consumido por skills.",
    "devotion_repressed": "Recurso privado da ficha autorizada.",
}


class CharacterStatusModal(LoggedModal, title="Aplicar status principal"):
    def __init__(self, editor: "CharacterStatusView") -> None:
        super().__init__()
        self.editor = editor
        self.potency = discord.ui.TextInput(label="Potência", default="1", max_length=4)
        self.count = discord.ui.TextInput(label="Quantidade", default="1", max_length=4)
        self.add_item(self.potency)
        self.add_item(self.count)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            potency, count = int(str(self.potency)), int(str(self.count))
            if potency < 0 or count < 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Potência e Quantidade devem ser inteiros não negativos.", ephemeral=True)
            return
        status = db.set_status(
            gid(interaction), "player", interaction.user.id,
            self.editor.selected_status, potency, count,
        )
        audit(interaction, "STATUS DE FICHA", f"{status.status_type}; P={status.potency}; C={status.count}")
        await interaction.response.edit_message(embed=self.editor.build_embed(interaction), view=self.editor)


class CharacterStatusSelect(discord.ui.Select):
    def __init__(self, editor: "CharacterStatusView") -> None:
        self.editor = editor
        super().__init__(
            placeholder="Escolha Burn, Bleed, Tremor, Rupture…",
            options=[discord.SelectOption(
                label=STATUS_LABELS[key], value=key, emoji=STATUS_ICONS[key],
                description=STATUS_DESCRIPTIONS[key][:100], default=key == editor.selected_status,
            ) for key in sorted(
                PUBLIC_STATUS_TYPES | ({"devotion_repressed"} if editor.owner_id == PRIVATE_SKILL_OWNER_ID else set())
            )],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.editor.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        self.editor.selected_status = self.values[0]
        self.editor.refresh_select()
        await interaction.response.edit_message(embed=self.editor.build_embed(interaction), view=self.editor)


class CharacterStatusView(LoggedView):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=600)
        self.owner_id = owner_id
        self.selected_status = "burn"
        self.refresh_select()

    def refresh_select(self) -> None:
        buttons = [item for item in self.children if isinstance(item, discord.ui.Button)]
        self.clear_items()
        self.add_item(CharacterStatusSelect(self))
        for button in buttons:
            self.add_item(button)

    def build_embed(self, interaction: discord.Interaction) -> discord.Embed:
        current = db.get_status(gid(interaction), "player", interaction.user.id, self.selected_status)
        icon, label = STATUS_ICONS[self.selected_status], STATUS_LABELS[self.selected_status]
        embed = discord.Embed(
            title="〔 STATUS WORKSHOP 〕",
            description=f"## {icon} {label}\n{STATUS_DESCRIPTIONS[self.selected_status]}",
            color=ACCENT,
        )
        embed.add_field(
            name="◆ VALORES ATUAIS",
            value=(f"Potência `{current.potency}` • Quantidade `{current.count}`" if current else
                   "Potência `0` • Quantidade `0`"),
            inline=False,
        )
        embed.set_footer(text="Escolha o status • defina Potência e Quantidade • aplique")
        return embed

    @discord.ui.button(label="Definir valores", emoji="✏️", style=discord.ButtonStyle.danger, row=1)
    async def apply(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CharacterStatusModal(self))

    @discord.ui.button(label="Voltar aos efeitos", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        editor = CharacterEffectsView(self.owner_id)
        row = db.get_character(gid(interaction), interaction.user.id)
        await interaction.response.edit_message(embed=editor.build_embed(interaction, row), view=editor)


class CharacterView(LoggedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Editar níveis", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def levels(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(LevelsModal())

    @discord.ui.button(label="Adicionar efeitos", emoji="✨", style=discord.ButtonStyle.danger)
    async def effects(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        editor = CharacterEffectsView(interaction.user.id)
        await interaction.response.edit_message(embed=editor.build_embed(interaction, row), view=editor)

    @discord.ui.button(label="Atualizar ficha", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        if row is None:
            await interaction.response.send_message("Ficha não encontrada.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=character_embed(row, interaction.user), view=self)

    @discord.ui.button(label="Trocar imagem", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def image_shortcut(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        command_mention = "`/personagem imagem`"
        try:
            commands_in_guild = await interaction.client.tree.fetch_commands(guild=interaction.guild)
            root = next((command for command in commands_in_guild if command.name == "personagem"), None)
            if root is not None:
                command_mention = f"</personagem imagem:{root.id}>"
        except discord.HTTPException:
            pass
        await interaction.response.send_message(
            f"Clique em {command_mention} e anexe a nova imagem. Depois use **Atualizar ficha**.",
            ephemeral=True,
        )


def master_allowed(interaction: discord.Interaction) -> bool:
    return bool(getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.manage_guild)


class EnemyEffectsModal(LoggedModal, title="Efeitos do inimigo"):
    paralysis = discord.ui.TextInput(label="Paralisia", default="0", max_length=4)
    base = discord.ui.TextInput(label="Base Power Up/Down", default="0", max_length=4)
    coin = discord.ui.TextInput(label="Plus Coin Boost/Drop", default="0", max_length=4)
    clash = discord.ui.TextInput(label="Clash Power Up/Down", default="0", max_length=4)
    offense = discord.ui.TextInput(label="Offense Level Up/Down", default="0", max_length=4)

    def __init__(self, enemy_id: int, enemy_name: str) -> None:
        super().__init__()
        self.enemy_id, self.enemy_name = enemy_id, enemy_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        try:
            values = [int(str(x)) for x in (self.paralysis, self.base, self.coin, self.clash, self.offense)]
        except ValueError:
            await interaction.response.send_message("Todos os efeitos precisam ser números inteiros.", ephemeral=True)
            return
        db.add_enemy_effects(self.enemy_id, *values)
        audit(interaction, "EFEITOS DE INIMIGO", f"{self.enemy_name}: {values}")
        await interaction.response.edit_message(
            embed=enemy_manager_embed(gid(interaction)), view=EnemyManagerView()
        )


class EnemyEditSkillModal(LoggedModal):
    def __init__(self, enemy_id: int, enemy_name: str, skill: Skill) -> None:
        super().__init__(title=f"Editar: {skill.name[:35]}")
        self.enemy_id, self.enemy_name, self.old_name = enemy_id, enemy_name, skill.name
        self.name_input = discord.ui.TextInput(label="Nome", default=skill.name, max_length=50)
        self.values_input = discord.ui.TextInput(label="Base, Coin, Moedas, Inquebráveis", default=f"{skill.base_power}, {skill.coin_power}, {skill.coins}, {skill.unbreakable_coins}")
        self.type_input = discord.ui.TextInput(label="Tipo", default=skill.skill_type, max_length=30)
        self.description_input = discord.ui.TextInput(label="Descrição", default=skill.description, required=False, style=discord.TextStyle.paragraph, max_length=300)
        self.effects_input = discord.ui.TextInput(
            label="Efeitos (gatilho:efeito:valor:moeda)", default=format_skill_effects(skill.effects),
            required=False, placeholder="on_hit:paralysis:1:2", style=discord.TextStyle.paragraph, max_length=600,
        )
        for item in (self.name_input, self.values_input, self.type_input, self.description_input, self.effects_input):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        try:
            base, coin, coins, unbreakable = parse_skill_values(str(self.values_input))
            raw = str(self.type_input).strip().lower()
            kind = SKILL_TYPE_ALIASES.get(raw, raw if raw in SKILL_TYPE_LABELS else None)
            if kind is None: raise ValueError("tipo")
            effects = parse_skill_effects(str(self.effects_input))
            skill = Skill(str(self.name_input), base, coin, coins, str(self.description_input), kind, unbreakable, effects)
        except (ValueError, TypeError):
            await interaction.response.send_message("Confira Base, Coin, Moedas, Inquebráveis e tipo.", ephemeral=True)
            return
        if skill.name.casefold() != self.old_name.casefold():
            db.delete_enemy_skill(self.enemy_id, self.old_name)
        db.save_enemy_skill(self.enemy_id, skill)
        audit(interaction, "SKILL INIMIGA EDITADA", f"{self.enemy_name}: {self.old_name} -> {skill.name}")
        await interaction.response.edit_message(embed=enemy_manager_embed(gid(interaction)), view=EnemyManagerView())


class EnemySkillActionSelect(discord.ui.Select):
    def __init__(self, enemy, skills: list[Skill], action: str) -> None:
        self.enemy, self.action = enemy, action
        super().__init__(
            placeholder="Escolha uma skill inimiga",
            options=[discord.SelectOption(label=s.name[:100], value=s.name, description=SKILL_TYPE_LABELS[s.skill_type][:100]) for s in skills[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        skill = db.get_enemy_skill(self.enemy["id"], self.values[0])
        if skill is None:
            await interaction.response.send_message("Skill não encontrada.", ephemeral=True)
            return
        if self.action == "edit":
            await interaction.response.send_modal(EnemyEditSkillModal(self.enemy["id"], self.enemy["name"], skill))
        else:
            db.delete_enemy_skill(self.enemy["id"], skill.name)
            audit(interaction, "SKILL INIMIGA EXCLUÍDA", f"{self.enemy['name']}: {skill.name}")
            await interaction.response.edit_message(embed=enemy_manager_embed(gid(interaction)), view=EnemyManagerView())


class EnemySkillActionView(LoggedView):
    def __init__(self, enemy, skills: list[Skill], action: str) -> None:
        super().__init__(timeout=600)
        self.add_item(EnemySkillActionSelect(enemy, skills, action))


class EnemyActionSelect(discord.ui.Select):
    def __init__(self, enemies, action: str) -> None:
        self.action = action
        super().__init__(placeholder="Escolha um inimigo", options=[discord.SelectOption(label=e["name"][:100], value=e["name"]) for e in enemies[:25]])

    async def callback(self, interaction: discord.Interaction) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        enemy = db.get_enemy(gid(interaction), self.values[0])
        if enemy is None:
            await interaction.response.send_message("Inimigo não encontrado.", ephemeral=True)
            return
        if self.action == "effects":
            await interaction.response.send_modal(EnemyEffectsModal(enemy["id"], enemy["name"]))
            return
        if self.action == "sheet":
            await interaction.response.edit_message(
                embed=enemy_sheet_embed(gid(interaction), enemy), view=EnemyManagerView(),
            )
            return
        if self.action == "create":
            builder = SkillBuilderView(
                interaction.user.id, enemy_id=enemy["id"], enemy_name=enemy["name"],
            )
            await interaction.response.edit_message(embed=builder.build_embed(), view=builder)
            return
        skills = db.list_enemy_skills(enemy["id"])
        if not skills:
            await interaction.response.send_message("Esse inimigo não possui skills.", ephemeral=True)
            return
        if self.action == "edit":
            await interaction.response.edit_message(
                embed=skills_embed(skills, f"Escolha a skill de {enemy['name']}"),
                view=EnemyWorkshopSkillView(interaction.user.id, enemy, skills),
            )
            return
        await interaction.response.edit_message(
            embed=skills_embed(skills, f"Skills de {enemy['name']}"),
            view=EnemySkillActionView(enemy, skills, self.action),
        )


class EnemyActionView(LoggedView):
    def __init__(self, enemies, action: str) -> None:
        super().__init__(timeout=600)
        self.add_item(EnemyActionSelect(enemies, action))


class EnemyWorkshopSkillSelect(discord.ui.Select):
    def __init__(self, owner_id: int, enemy, skills: list[Skill]) -> None:
        self.owner_id, self.enemy = owner_id, enemy
        super().__init__(
            placeholder="Escolha a skill para abrir no Lab",
            options=[discord.SelectOption(label=skill.name[:100], value=skill.name) for skill in skills[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id or not master_allowed(interaction):
            await interaction.response.send_message("Este Lab pertence ao mestre que o abriu.", ephemeral=True)
            return
        skill = db.get_enemy_skill(self.enemy["id"], self.values[0])
        if skill is None:
            await interaction.response.send_message("Skill não encontrada.", ephemeral=True)
            return
        builder = SkillBuilderView(
            self.owner_id, skill, enemy_id=self.enemy["id"], enemy_name=self.enemy["name"],
        )
        await interaction.response.edit_message(embed=builder.build_embed(), view=builder)


class EnemyWorkshopSkillView(LoggedView):
    def __init__(self, owner_id: int, enemy, skills: list[Skill]) -> None:
        super().__init__(timeout=600)
        self.add_item(EnemyWorkshopSkillSelect(owner_id, enemy, skills))


def enemy_sheet_embed(server: int, enemy) -> discord.Embed:
    appearance = db.get_appearance(server, "enemy", enemy["id"])
    subtitle = f"\n*{appearance['subtitle']}*" if appearance and appearance["subtitle"] else ""
    embed = discord.Embed(
        title="【 LCB // REGISTRO DE HOSTIL 】",
        description=f"## {enemy['name']}{subtitle}", color=appearance_embed_color(appearance),
    )
    if appearance and appearance["image_url"].startswith(("http://", "https://")):
        if appearance["image_mode"] == "thumbnail":
            embed.set_thumbnail(url=appearance["image_url"])
        elif appearance["image_mode"] == "banner":
            embed.set_image(url=appearance["image_url"])
    if appearance and appearance["footer_text"]:
        embed.set_footer(text=appearance["footer_text"])
    sanity = (
        f"```{enemy['sp']:+d} SP\n{heads_chance(enemy['sp']):.0%} HEADS```"
        if enemy["uses_sanity"] else "```SANIDADE INATIVA\n50% HEADS```"
    )
    embed.add_field(name="◈ SANIDADE", value=sanity)
    embed.add_field(name="◆ OFFENSE LEVEL", value=f"```{enemy['offense_level']}```")
    embed.add_field(name="◇ DEFENSE LEVEL", value=f"```{enemy['defense_level']}```")
    tags = db.get_enemy_tags(enemy["id"])
    embed.add_field(
        name="〔 TAGS DO HOSTIL 〕",
        value=" ".join(f"`{tag}`" for tag in tags) or "`SEM TAGS`",
        inline=False,
    )
    if enemy["charge_potency_enabled"]:
        embed.add_field(
            name=f"{STATUS_ICONS['charge']} CHARGE POTENCY",
            value=f"```ATIVA • CONSUMO {enemy['charge_spent']}/10```",
            inline=False,
        )
    embed.add_field(
        name="【 STATUS // POTÊNCIA × QUANTIDADE 】",
        value=status_summary(server, "enemy", enemy["id"]), inline=False,
    )
    skills = db.list_enemy_skills(enemy["id"])
    embed.add_field(
        name=f"【 SKILLS // {len(skills)} 】",
        value="\n".join(f"{COIN_ACTIVE} **{skill.name}** • {SKILL_TYPE_LABELS[skill.skill_type]}" for skill in skills[:15]) or "`SEM SKILLS`",
        inline=False,
    )
    return embed


def enemy_manager_embed(server: int) -> discord.Embed:
    enemies = db.list_enemies(server)
    embed = discord.Embed(title="【 ENEMY HUB // PAINEL DO MESTRE 】", color=ACCENT)
    embed.description = "Fichas, status e Skill Lab dos hostis em um único lugar."
    for enemy in enemies[:15]:
        skills = db.list_enemy_skills(enemy["id"])
        embed.add_field(name=enemy["name"], value=f"OL `{enemy['offense_level']}` • DL `{enemy['defense_level']}` • **{len(skills)} skill(s)**", inline=False)
    if not enemies:
        embed.add_field(name="Nenhum inimigo", value="Crie o primeiro com `/inimigo criar`.", inline=False)
    return embed


class EnemyManagerView(LoggedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    async def open_action(self, interaction: discord.Interaction, action: str) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        enemies = db.list_enemies(gid(interaction))
        if not enemies:
            await interaction.response.send_message("Crie um inimigo com `/inimigo criar` primeiro.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=enemy_manager_embed(gid(interaction)), view=EnemyActionView(enemies, action))

    @discord.ui.button(label="Ficha", emoji="📋", style=discord.ButtonStyle.primary)
    async def sheet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_action(interaction, "sheet")

    @discord.ui.button(label="Criar skill", emoji="➕", style=discord.ButtonStyle.success)
    async def create_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_action(interaction, "create")

    @discord.ui.button(label="Efeitos", emoji="✨", style=discord.ButtonStyle.primary)
    async def effects(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_action(interaction, "effects")

    @discord.ui.button(label="Editar skill", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def edit_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_action(interaction, "edit")

    @discord.ui.button(label="Excluir skill", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_skill(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_action(interaction, "delete")


class DamageRollModal(LoggedModal):
    def __init__(self, skill: Skill) -> None:
        super().__init__(title=f"Rolar dano: {skill.name[:30]}")
        self.skill = skill
        self.target_defense = discord.ui.TextInput(
            label="Defense Level do alvo", placeholder="Exemplo: 12", max_length=6,
        )
        self.test_paralysis = discord.ui.TextInput(
            label="Paralisia de teste", placeholder="0 a 10", default="0", max_length=2,
        )
        self.add_item(self.target_defense)
        self.add_item(self.test_paralysis)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            target_defense = int(str(self.target_defense))
            test_paralysis = int(str(self.test_paralysis))
            if not 0 <= test_paralysis <= 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Defense Level precisa ser inteiro e a Paralisia deve ficar entre 0 e 10.", ephemeral=True,
            )
            return
        character = db.get_character(gid(interaction), interaction.user.id)
        if character is None:
            await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
            return
        await interaction.response.defer()
        remaining_coins = 1 if self.skill.skill_type == "counter" else self.skill.coins
        offense = character["offense_level"] + character["offense_level_mod"]
        modifiers = Modifiers(
            character["base_power_mod"], character["coin_power_mod"], test_paralysis,
        )
        audit(
            interaction, "CALCULADORA DE DANO",
            f"início; skill={self.skill.name}; moedas={remaining_coins}; offense={offense}; defense={target_defense}; paralisia_teste={test_paralysis}",
        )
        result = resolve_damage(
            self.skill, character["sp"], remaining_coins, offense, target_defense,
            modifiers=modifiers,
        )
        percent_log = apply_skill_damage_percent(
            gid(interaction), "player", interaction.user.id, "enemy", 0,
            self.skill, result, consume_resources=False,
        )
        audit_damage_calculation(
            interaction, character["name"], "ALVO DE TESTE", self.skill, result,
        )
        embed = damage_embed(character["name"], "ALVO DE TESTE", self.skill, result)
        add_trigger_log(embed, percent_log)
        embed.set_footer(text="Simulação: não consome efeitos, não altera SP e não registra HP.")
        gif_file = await attach_damage_gif(embed)
        audit(
            interaction, "CALCULADORA DE DANO",
            f"concluída; skill={self.skill.name}; subtotal={result.subtotal}; ajuste={result.level_modifier:+d}; dano={result.final_damage}",
        )
        await interaction.followup.send(embed=embed, files=[gif_file] if gif_file else [])


class DamageSkillSelect(discord.ui.Select):
    def __init__(self, skills: list[Skill]) -> None:
        super().__init__(
            placeholder="Escolha a skill que terá o dano rolado",
            options=[
                discord.SelectOption(
                    label=skill.name[:100], value=skill.name,
                    description=f"{SKILL_TYPE_LABELS[skill.skill_type]} • {skill.coins} moeda(s)"[:100],
                )
                for skill in skills[:25]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        skill = db.get_skill(gid(interaction), interaction.user.id, self.values[0])
        if skill is None or not skill.deals_damage:
            await interaction.response.send_message("Essa skill não está disponível para dano.", ephemeral=True)
            return
        await interaction.response.send_modal(DamageRollModal(skill))


class DamageSkillView(LoggedView):
    def __init__(self, skills: list[Skill]) -> None:
        super().__init__(timeout=600)
        self.add_item(DamageSkillSelect(skills))


def battle_embed(interaction: discord.Interaction) -> discord.Embed:
    battle = db.get_battle(gid(interaction), interaction.channel_id)
    if battle is None:
        return discord.Embed(
            title="〔 BATTLEFIELD CONTROL 〕",
            description="Nenhuma sessão ativa neste canal.\nO mestre pode usar `/batalha iniciar`.",
            color=ACCENT,
        )
    actions = db.list_field_actions(interaction.guild_id, interaction.channel_id)
    player_actions = db.list_player_actions(interaction.guild_id, interaction.channel_id)
    participants = db.list_battle_participants(interaction.guild_id, interaction.channel_id)
    phase_labels = {
        "preparation": "PREPARAÇÃO",
        "declaration": "DECLARAÇÃO",
        "resolution": "RESOLUÇÃO",
        "complete": "ENCERRADO",
    }
    phase_help = {
        "preparation": "Entre na operação. Quando equipe e campo estiverem prontos, todos confirmam **Pronto**.",
        "declaration": "Puxe um Clash, use um ataque livre/follow-up ou confirme **Pronto** para passar.",
        "resolution": "Revise o resultado e confirme **Pronto**; todos prontos iniciam o próximo turno.",
        "complete": "O turno foi concluído e pode avançar.",
    }
    phase = battle["phase"]
    embed = discord.Embed(
        title="〔 ⚠ BATTLEFIELD CONTROL ⚠ 〕",
        description=(
            f"## {battle['name']}\n"
            f"### TURNO {battle['turn']:02}  ━━━  FASE DE {phase_labels.get(phase, phase.upper())}\n"
            f"{phase_help.get(phase, '')}"
        ),
        color=ACCENT,
    )
    participant_icons = {"waiting": "⏳", "clashing": "⚔️", "done": "✅"}
    participant_labels = {"waiting": "AGUARDANDO", "clashing": "EM CLASH", "done": "AÇÃO CONCLUÍDA"}
    participant_lines = []
    for participant in participants[:20]:
        character = db.get_character(interaction.guild_id, participant["user_id"])
        sp = character["sp"] if character is not None else 0
        status = participant["status"]
        combat_statuses = status_summary(
            interaction.guild_id, "player", participant["user_id"], compact=True,
        )
        status_suffix = f"\n└ {combat_statuses}" if combat_statuses else ""
        participant_lines.append(
            f"{participant_icons.get(status, '•')} <@{participant['user_id']}> • "
            f"**{participant['character_name']}** • `{sp:+} SP` • "
            f"{participant_labels.get(status, status.upper())}"
            f"{' • **PRONTO**' if participant['ready'] else ''}"
            f"{status_suffix}"
        )
    embed.add_field(
        name="〔 EQUIPE EM CAMPO 〕",
        value="\n".join(participant_lines) if participant_lines else (
            "Nenhum Sinner entrou na operação. Use **Entrar na batalha** para ocupar uma posição."
        ),
        inline=False,
    )
    if phase in {"preparation", "declaration", "resolution"}:
        pending = [
            f"<@{participant['user_id']}>"
            for participant in participants if not participant["ready"]
        ]
        embed.add_field(
            name=f"〔 PENDÊNCIAS // {phase_labels.get(phase, phase.upper())} 〕",
            value="Aguardando " + ", ".join(pending) if pending else "✅ Todos confirmaram prontidão.",
            inline=False,
        )

    enemies = {}
    for action in actions:
        summary = enemies.setdefault(action["enemy_name"], {"total": 0, "resolved": 0})
        summary["total"] += 1
        summary["resolved"] += action["status"] == "resolved"
    if enemies:
        enemy_lines = []
        for name, data in list(enemies.items())[:15]:
            enemy = db.get_enemy(interaction.guild_id, name)
            combat_statuses = (
                status_summary(interaction.guild_id, "enemy", enemy["id"], compact=True)
                if enemy else ""
            )
            status_suffix = f"\n└ {combat_statuses}" if combat_statuses else ""
            enemy_lines.append(
                f"◆ **{name}** • ações `{data['resolved']}/{data['total']}` resolvidas"
                f"{status_suffix}"
            )
        embed.add_field(name="〔 HOSTIS DETECTADOS 〕", value="\n".join(enemy_lines), inline=False)

    status_icons = {"open": "🟢", "claimed": "🟡", "resolved": "⚫"}
    grouped = {"open": [], "claimed": [], "resolved": []}
    for action in actions[:20]:
        claimant = f" → <@{action['claimed_by']}> (`{action['player_skill']}`)" if action["claimed_by"] else ""
        grouped.setdefault(action["status"], []).append(
            f"{status_icons.get(action['status'], '•')} `#{action['id']:02}` **{action['enemy_name']}**\n"
            f"└ `{action['enemy_skill'].upper()}`{claimant}"
        )
    field_titles = {
        "open": "▰ AÇÕES HOSTIS DISPONÍVEIS",
        "claimed": "▰ CLASHES EM RESOLUÇÃO",
        "resolved": "▰ AÇÕES FINALIZADAS",
    }
    for status in ("open", "claimed", "resolved"):
        if grouped.get(status):
            embed.add_field(name=field_titles[status], value="\n".join(grouped[status]), inline=False)
    if player_actions:
        action_labels = {"unopposed": "ATAQUE LIVRE", "follow_up": "FOLLOW-UP"}
        lines = [
            f"🔸 `#{action['id']:02}` <@{action['user_id']}> → **{action['target_enemy']}**\n"
            f"└ `{action['player_skill'].upper()}` • {action_labels.get(action['action_type'], action['action_type'].upper())} • dano `{action['final_damage']}`"
            for action in player_actions[-7:]
        ]
        embed.add_field(name="▰ AÇÕES UNILATERAIS / FOLLOW-UPS", value="\n".join(lines), inline=False)
    if not actions:
        embed.add_field(
            name="◇ CAMPO SEM AÇÕES",
            value="O mestre adiciona uma skill hostil com `/batalha colocar_skill`.",
            inline=False,
        )
    open_count = sum(action["status"] == "open" for action in actions)
    resolved_count = sum(action["status"] == "resolved" for action in actions)
    done_count = sum(participant["status"] == "done" for participant in participants)
    ready_count = sum(bool(participant["ready"]) for participant in participants)
    embed.add_field(
        name="〔 PROGRESSO DO TURNO 〕",
        value=(
            f"Ações disponíveis **{open_count}**  •  Resolvidas **{resolved_count}/{len(actions)}**  •  Livres **{len(player_actions)}**\n"
            f"Sinners concluídos **{done_count}/{len(participants)}**  •  Prontos **{ready_count}/{len(participants)}**"
        ),
        inline=False,
    )
    embed.set_footer(text="BATTLEFIELD LINK // este painel é fixo e se atualiza durante a sessão")
    return embed


def combat_encounter_embed(name: str, master: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title="〔 ⚔ COMBAT ENCOUNTER ⚔ 〕",
        description=(
            f"# {name}\n"
            "Uma nova operação de combate foi iniciada.\n\n"
            "`SINNERS, PREPAREM SUAS SKILLS.`"
        ),
        color=GOLD,
    )
    embed.add_field(name="◆ DIRETOR DA OPERAÇÃO", value=master.mention, inline=True)
    embed.add_field(name="◇ ESTADO", value="`TURNO 01 • PREPARAÇÃO`", inline=True)
    embed.add_field(
        name="COMO PARTICIPAR",
        value="Use o painel fixo abaixo e pressione **Puxar Clash** quando uma ação hostil aparecer.",
        inline=False,
    )
    embed.set_footer(text="LIMBUS RPG // a sessão permanece salva mesmo se o bot reiniciar")
    return embed


def combat_ended_embed(name: str, turn: int) -> discord.Embed:
    embed = discord.Embed(
        title="〔 COMBAT SESSION CLOSED 〕",
        description=f"## {name}\nA operação foi encerrada no turno **{turn}**.",
        color=discord.Color.dark_grey(),
    )
    embed.add_field(
        name="◇ CAMPO DESATIVADO",
        value="As ações restantes não podem mais ser puxadas. O histórico permanece no canal e no log local.",
        inline=False,
    )
    embed.set_footer(text="Use /batalha iniciar para abrir uma nova operação neste canal")
    return embed


async def update_fixed_battle_panel(interaction: discord.Interaction) -> bool:
    battle = db.get_battle(gid(interaction), interaction.channel_id)
    if battle is None or not battle["panel_message_id"]:
        return False
    try:
        message = await interaction.channel.fetch_message(battle["panel_message_id"])
        await message.edit(embed=battle_embed(interaction), view=BattlePanelView())
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
        audit_logger.error("[PAINEL FIXO] falha ao atualizar mensagem=%s | %s", battle["panel_message_id"], error)
        return False


class BattleChannelInteraction:
    def __init__(self, source: discord.Interaction, channel) -> None:
        self.source, self.channel = source, channel
        self.channel_id = channel.id

    def __getattr__(self, name):
        return getattr(self.source, name)


async def update_fixed_battle_panel_at(
    interaction: discord.Interaction, battle_channel_id: int,
) -> bool:
    if interaction.guild is None:
        return False
    channel = interaction.guild.get_channel(battle_channel_id)
    if channel is None:
        try:
            channel = await interaction.guild.fetch_channel(battle_channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
    return await update_fixed_battle_panel(BattleChannelInteraction(interaction, channel))


class ControlBattleInteraction:
    """Contexto mínimo para a Central atualizar o painel persistente no Discord."""
    def __init__(self, guild: discord.Guild, channel) -> None:
        self.guild = guild
        self.guild_id = guild.id
        self.channel = channel
        self.channel_id = channel.id


async def refresh_battle_panel_from_control(guild_id: int, channel_id: int) -> bool:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return False
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
    interaction = ControlBattleInteraction(guild, channel)
    battle = db.get_battle(guild_id, channel_id)
    if battle is None:
        with db.lock:
            ended = db.connection.execute(
                "SELECT * FROM battle_sessions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            ).fetchone()
        if ended is None or not ended["panel_message_id"]:
            return False
        try:
            message = await channel.fetch_message(ended["panel_message_id"])
            await message.edit(embed=combat_ended_embed(ended["name"], ended["turn"]), view=None)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
    if not battle["panel_message_id"]:
        try:
            message = await channel.send(embed=battle_embed(interaction), view=BattlePanelView())
            db.set_battle_panel_message(guild_id, channel_id, message.id)
            return True
        except (discord.Forbidden, discord.HTTPException) as error:
            audit_logger.error("[CENTRAL DE BATALHA] falha ao publicar painel | %s", error)
            return False
    try:
        message = await channel.fetch_message(battle["panel_message_id"])
        await message.edit(embed=battle_embed(interaction), view=BattlePanelView())
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
        audit_logger.error("[CENTRAL DE BATALHA] falha ao sincronizar painel=%s | %s", battle["panel_message_id"], error)
        return False


class BattlePlayerSkillSelect(discord.ui.Select):
    def __init__(self, action_id: int, owner_id: int, skills: list[Skill]) -> None:
        self.action_id, self.owner_id = action_id, owner_id
        super().__init__(
            placeholder="Escolha sua skill para puxar o Clash",
            options=[discord.SelectOption(
                label=skill.name[:100], value=skill.name,
                description=f"{SKILL_TYPE_LABELS[skill.skill_type]} • {skill.range_with()[0]}–{skill.range_with()[1]}"[:100],
            ) for skill in skills[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente quem abriu este seletor pode usá-lo.", ephemeral=True)
            return
        action = db.get_field_action(self.action_id)
        battle = db.get_battle(gid(interaction), interaction.channel_id)
        skill = db.get_skill(interaction.guild_id, interaction.user.id, self.values[0])
        enemy = None if action is None else db.get_enemy(interaction.guild_id, action["enemy_name"])
        enemy_skill = None if enemy is None or action is None else db.get_enemy_skill(enemy["id"], action["enemy_skill"])
        if battle is None or action is None or action["status"] != "open":
            await interaction.response.send_message("Essa ação já foi puxada ou a batalha terminou.", ephemeral=True)
            return
        if skill is None or enemy_skill is None:
            await interaction.response.send_message("Uma das skills não está mais disponível.", ephemeral=True)
            return
        if not db.claim_field_action(self.action_id, interaction.user.id, skill.name):
            await interaction.response.send_message("Outro jogador puxou essa ação primeiro.", ephemeral=True)
            return
        character = db.get_character(interaction.guild_id, interaction.user.id)
        if character is not None:
            db.join_battle(interaction.guild_id, interaction.channel_id, interaction.user.id, character["name"])
            db.set_battle_participant_status(
                interaction.guild_id, interaction.channel_id, interaction.user.id, "clashing",
            )
        audit(
            interaction, "CLASH PUXADO DO CAMPO",
            f"ação=#{self.action_id}; jogador={interaction.user}; skill={skill.name}; inimigo={action['enemy_name']}; skill_inimiga={action['enemy_skill']}",
        )
        await update_fixed_battle_panel(interaction)
        try:
            clash_interaction = await routed_clash_interaction(interaction)
            if clash_interaction is None:
                raise RuntimeError("Canal de Clash configurado não foi encontrado ou está inacessível.")
            await clash_inimigo_impl(
                clash_interaction, action["enemy_name"], skill.name, action["enemy_skill"],
            )
        except Exception:
            db.release_field_action(self.action_id)
            db.set_battle_participant_status(
                interaction.guild_id, interaction.channel_id, interaction.user.id, "waiting",
            )
            await update_fixed_battle_panel(interaction)
            raise
        else:
            db.resolve_field_action(self.action_id)
            db.set_battle_participant_status(
                interaction.guild_id, interaction.channel_id, interaction.user.id, "done",
            )
            await update_fixed_battle_panel(interaction)


class BattlePlayerSkillView(LoggedView):
    def __init__(self, action_id: int, owner_id: int, skills: list[Skill]) -> None:
        super().__init__(timeout=600)
        self.add_item(BattlePlayerSkillSelect(action_id, owner_id, skills))


class BattleActionSelect(discord.ui.Select):
    def __init__(self, owner_id: int, actions) -> None:
        self.owner_id = owner_id
        super().__init__(
            placeholder="Escolha a skill inimiga que você enfrentará",
            options=[discord.SelectOption(
                label=f"#{action['id']} • {action['enemy_name']}"[:100],
                value=str(action["id"]), description=action["enemy_skill"][:100],
            ) for action in actions[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente quem abriu este seletor pode usá-lo.", ephemeral=True)
            return
        action = db.get_field_action(int(self.values[0]))
        if action is None or action["status"] != "open":
            await interaction.response.send_message("Essa ação já não está disponível.", ephemeral=True)
            return
        skills = db.list_skills(gid(interaction), interaction.user.id)
        if not skills:
            await interaction.response.send_message("Você não possui skills para responder.", ephemeral=True)
            return
        embed = discord.Embed(
            title="〔 DECLARE YOUR SKILL 〕",
            description=f"## {action['enemy_name']}\n`{action['enemy_skill'].upper()}`\n\nEscolha a skill que enfrentará esta ação.",
            color=GOLD,
        )
        await interaction.response.edit_message(
            embed=embed,
            view=BattlePlayerSkillView(action["id"], self.owner_id, skills),
        )


class BattleActionView(LoggedView):
    def __init__(self, owner_id: int, actions) -> None:
        super().__init__(timeout=600)
        self.add_item(BattleActionSelect(owner_id, actions))


def advance_battle_when_ready(guild_id: int, channel_id: int) -> tuple[str | None, str]:
    """Avança a máquina de fases quando todos os participantes confirmam."""
    return advance_when_all_ready(db, guild_id, channel_id)


class BattleFreeSkillSelect(discord.ui.Select):
    def __init__(self, owner_id: int, battle_channel_id: int, enemy_name: str, action_type: str, skills: list[Skill]) -> None:
        self.owner_id, self.battle_channel_id = owner_id, battle_channel_id
        self.enemy_name, self.action_type = enemy_name, action_type
        super().__init__(
            placeholder="Escolha a skill do ataque unilateral",
            options=[discord.SelectOption(
                label=skill.name[:100], value=skill.name,
                description=f"{SKILL_TYPE_LABELS[skill.skill_type]} • dano com {skill.coins} moeda(s)"[:100],
            ) for skill in skills[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente quem abriu esta ação pode usá-la.", ephemeral=True)
            return
        battle = db.get_battle(gid(interaction), self.battle_channel_id)
        character = db.get_character(gid(interaction), interaction.user.id)
        enemy = db.get_enemy(gid(interaction), self.enemy_name)
        skill = db.get_skill(gid(interaction), interaction.user.id, self.values[0])
        if battle is None or battle["phase"] != "declaration":
            await interaction.response.send_message("Ataques livres só podem ser usados na Declaração.", ephemeral=True)
            return
        if character is None or enemy is None or skill is None or not skill.deals_damage:
            await interaction.response.send_message("Combatente, alvo ou skill não está mais disponível.", ephemeral=True)
            return
        participant = db.get_battle_participant(gid(interaction), self.battle_channel_id, interaction.user.id)
        if participant is None:
            await interaction.response.send_message("Entre na batalha antes de atacar.", ephemeral=True)
            return
        server = gid(interaction)
        remaining = 1 if skill.skill_type == "counter" else skill.coins
        skill, charge_log = prepare_charge_enhancements(
            server, "player", interaction.user.id, "enemy", enemy["id"], skill,
        )
        effect_log = apply_skill_trigger(
            server, "player", interaction.user.id, "enemy", enemy["id"], skill, "on_use",
        )
        status_log = charge_log + trigger_bleed_action(
            server, "player", interaction.user.id, character["name"], skill, remaining,
        )
        effect_log += apply_skill_trigger(
            server, "player", interaction.user.id, "enemy", enemy["id"], skill,
            "before_attack", remaining_coins=remaining,
        )
        character = db.get_character(server, interaction.user.id)
        enemy = db.get_enemy(server, self.enemy_name)
        offense = character["offense_level"] + character["offense_level_mod"]
        modifiers = Modifiers(
            character["base_power_mod"], character["coin_power_mod"], character["paralysis"],
        )
        result = resolve_damage(
            skill, character["sp"], remaining, offense, enemy["defense_level"],
            modifiers=modifiers,
        )
        status_log += apply_skill_damage_percent(
            server, "player", interaction.user.id, "enemy", enemy["id"], skill, result,
        )
        status_log += apply_poise_critical(server, "player", interaction.user.id, result)
        revert_temporary_self_trigger(
            server, "player", interaction.user.id, skill,
            "before_attack", remaining_coins=remaining,
        )
        db.consume_clash_effects(
            server, interaction.user.id, max(0, character["paralysis"] - remaining),
        )
        hit_effects, hit_statuses = resolve_hit_status_sequence(
            server, "player", interaction.user.id, "enemy", enemy["id"],
            enemy["sp"] if enemy["uses_sanity"] else None, skill, result.hits,
        )
        effect_log += hit_effects
        status_log += hit_statuses
        effect_log += apply_skill_trigger(
            server, "player", interaction.user.id, "enemy", enemy["id"], skill,
            "after_attack", remaining_coins=remaining,
        )
        db.add_player_action(
            gid(interaction), self.battle_channel_id, interaction.user.id, character["name"],
            enemy["name"], skill.name, self.action_type, result.final_damage,
        )
        db.set_battle_participant_status(
            gid(interaction), self.battle_channel_id, interaction.user.id, "done",
        )
        embed = damage_embed(character["name"], enemy["name"], skill, result)
        audit_damage_calculation(
            interaction, character["name"], enemy["name"], skill, result,
        )
        label = "FOLLOW-UP" if self.action_type == "follow_up" else "ATAQUE LIVRE"
        embed.title = f"〔 {label} // DAMAGE RESOLUTION 〕"
        embed.add_field(
            name="◇ TIPO DE AÇÃO",
            value="Ataque unilateral: não disputa nem reserva uma skill hostil do campo.",
            inline=False,
        )
        add_trigger_log(embed, effect_log + status_log)
        add_status_impact(embed, effect_log + status_log)
        audit(
            interaction, label,
            f"{character['name']} -> {enemy['name']}; skill={skill.name}; dano={result.final_damage}",
        )
        await interaction.response.defer()
        gif_file = await attach_damage_gif(embed)
        await interaction.edit_original_response(
            embed=embed, view=None, attachments=[gif_file] if gif_file else [],
        )
        await update_fixed_battle_panel_at(interaction, self.battle_channel_id)


class BattleFreeSkillView(LoggedView):
    def __init__(self, owner_id: int, battle_channel_id: int, enemy_name: str, action_type: str, skills: list[Skill]) -> None:
        super().__init__(timeout=600)
        self.add_item(BattleFreeSkillSelect(owner_id, battle_channel_id, enemy_name, action_type, skills))


class BattleFreeTargetSelect(discord.ui.Select):
    def __init__(self, owner_id: int, battle_channel_id: int, action_type: str, enemy_names: list[str]) -> None:
        self.owner_id, self.battle_channel_id = owner_id, battle_channel_id
        self.action_type = action_type
        super().__init__(
            placeholder="Escolha o alvo presente no campo",
            options=[discord.SelectOption(label=name[:100], value=name) for name in enemy_names[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente quem abriu esta ação pode usá-la.", ephemeral=True)
            return
        skills = [
            skill for skill in db.list_skills(gid(interaction), interaction.user.id)
            if skill.deals_damage
        ]
        if not skills:
            await interaction.response.send_message("Você não possui uma skill que cause dano.", ephemeral=True)
            return
        enemy_name = self.values[0]
        embed = discord.Embed(
            title="〔 DECLARE UNOPPOSED ATTACK 〕",
            description=f"## {enemy_name}\nEscolha a skill que será usada sem Clash.",
            color=GOLD,
        )
        await interaction.response.edit_message(
            embed=embed,
            view=BattleFreeSkillView(self.owner_id, self.battle_channel_id, enemy_name, self.action_type, skills),
        )


class BattleFreeTargetView(LoggedView):
    def __init__(self, owner_id: int, battle_channel_id: int, action_type: str, enemy_names: list[str]) -> None:
        super().__init__(timeout=600)
        self.add_item(BattleFreeTargetSelect(owner_id, battle_channel_id, action_type, enemy_names))


class BattlePanelView(LoggedView):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar na batalha", emoji="👤", style=discord.ButtonStyle.success, custom_id="battle:join")
    async def join(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        battle = db.get_battle(gid(interaction), interaction.channel_id)
        if battle is None:
            await interaction.response.send_message("Não existe uma batalha ativa neste canal.", ephemeral=True)
            return
        character = db.get_character(gid(interaction), interaction.user.id)
        if character is None:
            await interaction.response.send_message("Crie sua ficha antes de entrar em combate.", ephemeral=True)
            return
        db.join_battle(gid(interaction), interaction.channel_id, interaction.user.id, character["name"])
        audit(interaction, "ENTROU NA BATALHA", f"personagem={character['name']}")
        await interaction.response.defer(ephemeral=True)
        await update_fixed_battle_panel(interaction)
        await interaction.followup.send(f"**{character['name']}** entrou na operação.", ephemeral=True)

    @discord.ui.button(label="Pronto", emoji="✅", style=discord.ButtonStyle.primary, custom_id="battle:ready")
    async def ready(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        battle = db.get_battle(gid(interaction), interaction.channel_id)
        if battle is None:
            await interaction.response.send_message("Não existe uma batalha ativa neste canal.", ephemeral=True)
            return
        participant = db.get_battle_participant(gid(interaction), interaction.channel_id, interaction.user.id)
        if participant is None:
            await interaction.response.send_message("Entre na batalha antes de confirmar prontidão.", ephemeral=True)
            return
        if battle["phase"] == "declaration" and participant["status"] == "clashing":
            await interaction.response.send_message(
                "Conclua o Clash em andamento antes de marcar **Pronto**.", ephemeral=True,
            )
            return
        new_ready = not bool(participant["ready"])
        db.set_battle_participant_ready(
            gid(interaction), interaction.channel_id, interaction.user.id, new_ready,
        )
        advanced, transition_message = advance_battle_when_ready(gid(interaction), interaction.channel_id)
        audit(
            interaction, "PRONTIDÃO ALTERADA",
            f"fase={battle['phase']}; pronto={new_ready}; avanço={advanced or 'não'}",
        )
        await interaction.response.defer(ephemeral=True)
        await update_fixed_battle_panel(interaction)
        if advanced == "preparation":
            status_embed = round_status_embed(gid(interaction), db.last_round_status_events)
            output_channel = await clash_output_channel(interaction)
            if status_embed is not None and output_channel is not None:
                await output_channel.send(embed=status_embed)
        message = "✅ Prontidão confirmada nesta fase." if new_ready else "↩️ Sua prontidão foi removida."
        if transition_message:
            message += f" {transition_message}"
        await interaction.followup.send(message, ephemeral=True)

    async def open_free_attack(self, interaction: discord.Interaction, action_type: str) -> None:
        battle_channel_id = interaction.channel_id
        battle = db.get_battle(gid(interaction), interaction.channel_id)
        participant = db.get_battle_participant(gid(interaction), interaction.channel_id, interaction.user.id)
        if battle is None or battle["phase"] != "declaration":
            await interaction.response.send_message(
                "Ataques livres e follow-ups só podem ser declarados na fase de **Declaração**.",
                ephemeral=True,
            )
            return
        if participant is None:
            await interaction.response.send_message("Entre na batalha antes de declarar um ataque.", ephemeral=True)
            return
        enemy_names = list(dict.fromkeys(
            action["enemy_name"]
            for action in db.list_field_actions(gid(interaction), interaction.channel_id)
        ))
        if not enemy_names:
            await interaction.response.send_message("Não há inimigos no campo para selecionar.", ephemeral=True)
            return
        title = "FOLLOW-UP" if action_type == "follow_up" else "UNOPPOSED ATTACK"
        embed = discord.Embed(
            title=f"〔 {title} 〕",
            description="Escolha um inimigo do campo. Esta ação não puxará Clash.",
            color=GOLD,
        )
        output_channel = await clash_output_channel(interaction)
        if output_channel is None:
            await interaction.response.send_message(
                "Não consegui acessar o canal da arena. Confira minhas permissões.", ephemeral=True,
            )
            return
        target_view = BattleFreeTargetView(
            interaction.user.id, battle_channel_id, action_type, enemy_names,
        )
        if output_channel.id == interaction.channel_id:
            await interaction.response.send_message(embed=embed, view=target_view)
        else:
            await interaction.response.send_message(
                f"🎯 Ação enviada para {output_channel.mention}.", ephemeral=True,
            )
            await output_channel.send(embed=embed, view=target_view)

    @discord.ui.button(label="Ataque livre", emoji="🎯", style=discord.ButtonStyle.danger, custom_id="battle:unopposed")
    async def unopposed(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_free_attack(interaction, "unopposed")

    @discord.ui.button(label="Follow-up", emoji="➕", style=discord.ButtonStyle.secondary, custom_id="battle:follow_up")
    async def follow_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_free_attack(interaction, "follow_up")

    @discord.ui.button(label="Puxar Clash", emoji="⚔️", style=discord.ButtonStyle.danger, custom_id="battle:pull_clash")
    async def pull_clash(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        character = db.get_character(gid(interaction), interaction.user.id)
        if character is None:
            await interaction.response.send_message("Crie sua ficha antes de entrar em combate.", ephemeral=True)
            return
        battle = db.get_battle(gid(interaction), interaction.channel_id)
        if battle is None:
            await interaction.response.send_message("Não existe uma batalha ativa neste canal.", ephemeral=True)
            return
        if battle["phase"] != "declaration":
            await interaction.response.send_message(
                "Novos Clashes só podem ser puxados durante a fase de **Declaração**.", ephemeral=True,
            )
            return
        if db.get_battle_participant(gid(interaction), interaction.channel_id, interaction.user.id) is None:
            db.join_battle(gid(interaction), interaction.channel_id, interaction.user.id, character["name"])
            await update_fixed_battle_panel(interaction)
        actions = db.list_field_actions(interaction.guild_id, interaction.channel_id, "open")
        if not actions:
            await interaction.response.send_message("Não existe nenhuma skill inimiga disponível no campo.", ephemeral=True)
            return
        embed = discord.Embed(
            title="〔 SELECT HOSTILE ACTION 〕",
            description=f"<@{interaction.user.id}>, escolha a skill inimiga que você vai enfrentar.",
            color=GOLD,
        )
        # A seleção é pública para que a mesma mensagem se transforme na animação do Clash.
        await interaction.response.send_message(
            embed=embed, view=BattleActionView(interaction.user.id, actions)
        )

    @discord.ui.button(label="Atualizar campo", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="battle:refresh")
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=battle_embed(interaction), view=self)


TRIGGER_LABELS = {
    "on_use": "Ao usar", "on_hit": "Ao acertar", "heads_hit": "Heads ao acertar",
    "clash_win": "Ao vencer Clash", "clash_lose": "Ao perder Clash",
    "before_attack": "Antes do ataque", "after_attack": "Depois do ataque",
    "on_kill": "Ao derrotar",
}
BUILDER_EFFECT_LABELS = {
    "paralysis": "Paralisia no alvo", "sp": "Sanidade própria",
    "base_power": "Base Power próprio", "coin_power": "Coin Power próprio",
    "clash_power": "Clash Power próprio", "offense_level": "Offense Level próprio",
    "defense_level": "Defense Level no alvo",
    "burn": "Burn no alvo", "bleed": "Bleed no alvo",
    "tremor": "Tremor no alvo", "rupture": "Rupture no alvo",
    "sinking": "Sinking no alvo", "poise": "Poise próprio", "charge": "Charge própria",
    "special_condition": "Condição Especial própria",
    "tremor_burst": "Tremor Burst no alvo",
    "final_power": "Final Power próprio",
    "damage_percent": "Dano percentual",
    "make_unbreakable": "Tornar moeda(s) inquebráveis",
    "consume_special_condition": "Consumir Condição Especial (até X)",
    "self_bleed": "Aplicar Bleed em si mesma",
    "consume_devotion_repressed": "Atualizar recurso privado",
}

BUILDER_EFFECT_ICONS = {
    "paralysis": EFFECT_PARALYZE,
    "base_power": EFFECT_ATTACK_UP, "final_power": EFFECT_ATTACK_UP,
    "coin_power": EFFECT_PLUS_COIN_BOOST,
    "clash_power": EFFECT_CLASH_UP, "offense_level": EFFECT_OFFENSE_UP,
    "defense_level": DEFENSE_LEVEL_ICON,
    "damage_percent": EFFECT_ATTACK_UP,
    "tremor_burst": TREMOR_BURST_ICON, "make_unbreakable": COIN_UNBREAKABLE,
    "consume_special_condition": STATUS_ICONS["special_condition"],
    "self_bleed": STATUS_ICONS["bleed"],
    "consume_devotion_repressed": "🩸",
    **STATUS_ICONS,
}


def skill_template(template: str) -> Skill:
    """Modelos completos que podem ser carregados e ajustados na Oficina."""
    if template == "please_a_little":
        return Skill(
            "Por Favor... Só um Pouco.", 4, 3, 2,
            "[3 / 2 / 1 Selos] • Lust • Perfuração • Attack Weight 1\n"
            "Geração: 10–20 • Consumo: até 10\n"
            "“Por favor... só um pouco. Eu prometo que saberei apreciar.”",
            effects=(
                SkillEffect("on_use", "consume_special_condition", 10),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=5),
                SkillEffect("before_attack", "damage_percent", 5,
                            condition_status="special_condition_consumed", condition_min=20,
                            condition_owner="user", condition_value="count",
                            condition_per=20, condition_max_stacks=4),
                SkillEffect("clash_win", "special_condition", 0, count=10),
                SkillEffect("on_hit", "bleed", 3, coin=1, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=1, count=5),
                SkillEffect("on_hit", "bleed", 0, coin=2, count=1),
                SkillEffect("on_hit", "special_condition", 0, coin=2, count=5,
                            condition_status="bleed", condition_min=5),
            ),
        )
    if template == "do_not_deny":
        return Skill(
            "Não Ouse Me Negar.", 4, 4, 2,
            "[0 Selos] • Wrath • Perfuração • Attack Weight 1\n"
            "Geração: 20 • Consumo: até 15\n"
            "“Eu pedi tão gentilmente...” • “Não me faça pedir outra vez.”",
            effects=(
                SkillEffect("on_use", "consume_special_condition", 15),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=5),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=10),
                SkillEffect("before_attack", "damage_percent", 5,
                            condition_status="special_condition_consumed", condition_min=20,
                            condition_owner="user", condition_value="count",
                            condition_per=20, condition_max_stacks=6),
                SkillEffect("clash_win", "special_condition", 0, count=10),
                SkillEffect("on_hit", "bleed", 4, coin=1, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=1, count=5),
                SkillEffect("on_hit", "bleed", 0, coin=2, count=2),
                SkillEffect("on_hit", "special_condition", 0, coin=2, count=5),
                SkillEffect("on_hit", "damage_percent", 20, coin=2,
                            condition_status="special_condition_consumed", condition_min=60,
                            condition_owner="user", condition_value="count"),
                SkillEffect("heads_hit", "bleed", 0, coin=2, count=1,
                            condition_status="special_condition_consumed", condition_min=100,
                            condition_owner="user", condition_value="count"),
            ),
        )
    if template == "i_can_be_useful":
        return Skill(
            "Eu Posso Ser Útil.", 5, 3, 3,
            "[3 / 2 / 1 Selos] • Gloom • Corte • Attack Weight 1\n"
            "“Eu consigo ajudar... veja. Só me diga o que devo fazer.”",
            effects=(
                SkillEffect("on_use", "consume_special_condition", 20),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=5),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=10),
                SkillEffect("before_attack", "damage_percent", 5,
                            condition_status="special_condition_consumed", condition_min=20,
                            condition_owner="user", condition_value="count",
                            condition_per=20, condition_max_stacks=5),
                SkillEffect("clash_win", "special_condition", 0, count=10),
                SkillEffect("on_hit", "bleed", 3, coin=1, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=1, count=5),
                SkillEffect("on_hit", "bleed", 0, coin=2, count=2),
                SkillEffect("on_hit", "special_condition", 0, coin=2, count=5),
                SkillEffect("on_hit", "bleed", 3, coin=3, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=3, count=5),
                SkillEffect("on_hit", "damage_percent", 20, coin=3,
                            condition_status="special_condition_consumed", condition_min=40,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "bleed", 0, coin=3, count=1,
                            condition_status="special_condition_consumed", condition_min=80,
                            condition_owner="user", condition_value="count"),
            ),
        )
    if template == "kneel":
        return Skill(
            "Ajoelhe-se.", 5, 4, 3,
            "[0 Selos] • Pride • Corte • Attack Weight 1\n"
            "“Eu já observei o bastante.” • “Ajoelhe-se. Eu lhe mostrarei como deveria ser feito.”",
            effects=(
                SkillEffect("on_use", "consume_special_condition", 30),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=5),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=10),
                SkillEffect("before_attack", "damage_percent", 5,
                            condition_status="special_condition_consumed", condition_min=20,
                            condition_owner="user", condition_value="count",
                            condition_per=20, condition_max_stacks=8),
                SkillEffect("clash_win", "special_condition", 0, count=10),
                SkillEffect("on_hit", "bleed", 4, coin=1, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=1, count=5),
                SkillEffect("on_hit", "bleed", 0, coin=2, count=2),
                SkillEffect("on_hit", "special_condition", 0, coin=2, count=5),
                SkillEffect("on_hit", "defense_level", -3, coin=2,
                            condition_status="special_condition_consumed", condition_min=60,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "bleed", 5, coin=3, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=3, count=5),
                SkillEffect("on_hit", "damage_percent", 25, coin=3,
                            condition_status="special_condition_consumed", condition_min=80,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "bleed", 0, coin=3, count=1,
                            condition_status="special_condition_consumed", condition_min=120,
                            condition_owner="user", condition_value="count"),
                SkillEffect("heads_hit", "damage_percent", 20, coin=3,
                            condition_status="bleed", condition_min=15),
            ),
        )
    if template == "accept_my_offering":
        return Skill(
            "Aceite Minha Oferenda.", 6, 4, 3,
            "[3 / 2 / 1 Selos] • Lust • Perfuração • Attack Weight 1\n"
            "Geração: 35–50 • Consumo: até 30\n"
            "“Se ainda não sou digna... tome o meu sangue também.” • "
            "“Por favor... deixe-me provar que consigo.”",
            effects=(
                SkillEffect("on_use", "consume_special_condition", 30),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=5),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=15),
                SkillEffect("before_attack", "damage_percent", 5,
                            condition_status="special_condition_consumed", condition_min=20,
                            condition_owner="user", condition_value="count",
                            condition_per=20, condition_max_stacks=6),
                SkillEffect("on_use", "self_bleed", 5, count=2),
                SkillEffect("clash_win", "special_condition", 0, count=15),
                SkillEffect("on_hit", "bleed", 5, coin=1, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=1, count=10),
                SkillEffect("on_hit", "bleed", 0, coin=2, count=2),
                SkillEffect("on_hit", "special_condition", 0, coin=2, count=10),
                SkillEffect("on_hit", "bleed", 2, coin=2, count=0,
                            condition_status="special_condition_consumed", condition_min=40,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "special_condition", 0, coin=3, count=15),
                SkillEffect("on_hit", "damage_percent", 25, coin=3,
                            condition_status="special_condition_consumed", condition_min=60,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "bleed", 0, coin=3, count=1,
                            condition_status="special_condition_consumed", condition_min=100,
                            condition_owner="user", condition_value="count"),
                SkillEffect("after_attack", "consume_devotion_repressed", 1),
            ),
        )
    if template == "you_do_not_deserve_blood":
        return Skill(
            "Você Não Merece Esse Sangue.", 7, 4, 4,
            "[0 Selos] • Wrath • Corte • Attack Weight 1\n"
            "Geração: 10–50 • Consumo: até 50\n"
            "[On Kill] Recuperação de 5% do HP Máximo contra Bloodfiend/Bloodbag é manual.\n"
            "“Eu teria venerado esse sangue. Eu teria dado tudo por ele. E você o desperdiçou.”",
            effects=(
                SkillEffect("on_use", "consume_special_condition", 50),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=5),
                SkillEffect("on_use", "clash_power", 1, condition_status="bleed", condition_min=15),
                SkillEffect("before_attack", "damage_percent", 5,
                            condition_status="special_condition_consumed", condition_min=20,
                            condition_owner="user", condition_value="count",
                            condition_per=20, condition_max_stacks=10),
                SkillEffect("clash_win", "special_condition", 0, count=10),
                SkillEffect("clash_win", "special_condition", 0, count=10,
                            condition_status="bloodfiend_or_bloodbag", condition_min=1),
                SkillEffect("on_hit", "bleed", 6, coin=1, count=0),
                SkillEffect("on_hit", "special_condition", 0, coin=1, count=5),
                SkillEffect("on_hit", "bleed", 0, coin=2, count=3),
                SkillEffect("on_hit", "special_condition", 0, coin=2, count=5),
                SkillEffect("on_hit", "bleed", 2, coin=2, count=0,
                            condition_status="special_condition_consumed", condition_min=60,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "damage_percent", 30, coin=3,
                            condition_status="special_condition_consumed", condition_min=80,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "damage_percent", 20, coin=3,
                            condition_status="bleed", condition_min=15),
                SkillEffect("on_hit", "damage_percent", 40, coin=4,
                            condition_status="special_condition_consumed", condition_min=100,
                            condition_owner="user", condition_value="count"),
                SkillEffect("on_hit", "bleed", 0, coin=4, count=2,
                            condition_status="special_condition_consumed", condition_min=140,
                            condition_owner="user", condition_value="count"),
                SkillEffect("heads_hit", "damage_percent", 30, coin=4,
                            condition_status="bloodfiend_or_bloodbag", condition_min=1),
                SkillEffect("on_kill", "special_condition", 0, count=20),
                SkillEffect("on_kill", "sp", 5),
                SkillEffect("on_kill", "special_condition", 0, count=20,
                            condition_status="bloodfiend_or_bloodbag", condition_min=1),
            ),
        )
    raise ValueError("Modelo de skill desconhecido.")


def builder_effect_icon(effect_type: str, value: int = 0) -> str:
    pairs = {
        "base_power": (EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN),
        "final_power": (EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN),
        "coin_power": (EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP),
        "clash_power": (EFFECT_CLASH_UP, EFFECT_CLASH_DOWN),
        "offense_level": (EFFECT_OFFENSE_UP, EFFECT_OFFENSE_DOWN),
        "defense_level": (DEFENSE_LEVEL_ICON, DEFENSE_LEVEL_ICON),
        "damage_percent": (EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN),
    }
    if effect_type in pairs:
        return effect_icon(value, *pairs[effect_type])
    return BUILDER_EFFECT_ICONS.get(effect_type, "")


def builder_effect_text(effect: SkillEffect) -> str:
    icon = builder_effect_icon(effect.effect_type, effect.value)
    label = BUILDER_EFFECT_LABELS.get(effect.effect_type, effect.effect_type)
    extras = ""
    if effect.charge_cost:
        extras += f" • Charge `−{effect.charge_cost}`"
    if effect.condition_status:
        owner = "usuário" if effect.condition_owner == "user" else "alvo"
        metric = "Quantidade" if effect.condition_value == "count" else "Potência"
        extras += (
            f" • se {owner} tiver {STATUS_ICONS[effect.condition_status]} "
            f"`{effect.condition_status} {metric} {effect.condition_min}+`"
        )
        if effect.condition_per:
            maximum = f" (máx. {effect.condition_max_stacks})" if effect.condition_max_stacks else ""
            extras += f" • `×1 a cada {effect.condition_per}{maximum}`"
        if effect.consume_condition:
            extras += " • `CONSOME O STATUS USADO`"
    if effect.effect_type == "tremor_burst":
        return f"{icon} {label} `usa a Potência atual de Tremor`{extras}"
    if effect.effect_type == "make_unbreakable":
        scope = f"moeda {effect.coin}" if effect.coin is not None else "todas as moedas"
        return f"{COIN_UNBREAKABLE} {label} `{scope}`{extras}"
    if effect.effect_type == "consume_special_condition":
        return f"{STATUS_ICONS['special_condition']} {label} `até {int(effect.value)}`{extras}"
    if effect.effect_type == "self_bleed":
        return f"{STATUS_ICONS['bleed']} {label} `Pot. +{int(effect.value)} / Qtd. +{effect.count or 0}`{extras}"
    if effect.effect_type == "consume_devotion_repressed":
        return f"🔒 {label}{extras}"
    if effect.effect_type in STATUS_TYPES:
        return f"{icon} {label} `Pot. +{effect.value} / Qtd. +{effect.count or 0}`{extras}"
    if effect.effect_type == "damage_percent":
        maximum = (
            f" • teto `{effect.value * effect.condition_max_stacks:+g}%`"
            if effect.condition_per and effect.condition_max_stacks else ""
        )
        return f"{icon} {label} `{effect.value:+g}% por ativação`{maximum}{extras}"
    suffix = "%" if effect.effect_type == "damage_percent" else ""
    return f"{icon} {label} `{effect.value:+}{suffix}`{extras}"


class SkillBuilderBasicsModal(LoggedModal, title="Dados principais da skill"):
    def __init__(self, builder: "SkillBuilderView") -> None:
        super().__init__()
        self.builder = builder
        self.name_input = discord.ui.TextInput(label="Nome", default=builder.name, max_length=50)
        self.power_input = discord.ui.TextInput(
            label="Base Power, Coin Power", default=f"{builder.base_power}, {builder.coin_power}",
            placeholder="Exemplo: 4, 3", max_length=30,
        )
        self.coins_input = discord.ui.TextInput(
            label="Quantidade de moedas", default=str(builder.coins),
            placeholder="De 1 até 10", max_length=2,
        )
        self.description_input = discord.ui.TextInput(
            label="Descrição", default=builder.description, required=False,
            style=discord.TextStyle.paragraph, max_length=300,
        )
        for item in (self.name_input, self.power_input, self.coins_input, self.description_input):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            base, coin = [int(value.strip()) for value in str(self.power_input).split(",")]
            coins = int(str(self.coins_input).strip())
            if not 1 <= coins <= 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Base e Coin usam dois números separados por vírgula. A quantidade de moedas deve ser de 1 a 10.", ephemeral=True,
            )
            return
        self.builder.name = str(self.name_input).strip()
        self.builder.base_power, self.builder.coin_power = base, coin
        self.builder.resize_coins(coins)
        self.builder.description = str(self.description_input)
        self.builder.trim_invalid_effects()
        self.builder.refresh_components()
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderEffectModal(LoggedModal, title="Adicionar efeito"):
    def __init__(self, builder: "SkillBuilderView", editor: "SkillEffectsView") -> None:
        super().__init__()
        self.builder = builder
        self.editor = editor
        self.value_input = discord.ui.TextInput(
            label="Valor / Potência",
            placeholder=("Não usado por esta melhoria" if builder.selected_effect in {"tremor_burst", "make_unbreakable"} else "Exemplo: 2 ou -2"),
            required=builder.selected_effect not in {"tremor_burst", "make_unbreakable"}, max_length=8,
        )
        self.count_input = discord.ui.TextInput(
            label="Quantidade (somente para status)", placeholder="Exemplo: 3",
            required=False, max_length=8,
        )
        self.coin_input = discord.ui.TextInput(
            label="Moeda específica (opcional)", placeholder="Vazio = todas / automático",
            required=False, max_length=2,
        )
        self.charge_input = discord.ui.TextInput(
            label="Charge consumida na melhoria", placeholder="Exemplo: 5; sem Charge a skill continua", required=False, max_length=2,
        )
        self.condition_input = discord.ui.TextInput(
            label="Condição: mínimo, a cada, máximo", placeholder="Ex.: 1,1,200,!  (! = consumir)",
            required=False, max_length=20,
        )
        self.add_item(self.value_input)
        self.add_item(self.count_input)
        self.add_item(self.coin_input)
        self.add_item(self.charge_input)
        self.add_item(self.condition_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            raw_value = str(self.value_input).strip()
            value = 0 if self.builder.selected_effect in {"tremor_burst", "make_unbreakable"} else float(raw_value.replace(",", "."))
            raw_count = str(self.count_input).strip()
            count = int(raw_count) if raw_count else None
            raw_coin = str(self.coin_input).strip()
            coin = int(raw_coin) if raw_coin else None
            raw_charge = str(self.charge_input).strip()
            charge_cost = int(raw_charge) if raw_charge else 0
            raw_condition = str(self.condition_input).strip().lower()
            consume_condition = raw_condition.endswith("!")
            raw_condition = raw_condition.removesuffix("!").strip()
            condition_status = self.builder.selected_condition
            condition_parts = [int(part.strip()) for part in raw_condition.split(",") if part.strip()]
            if len(condition_parts) > 3:
                raise ValueError("Use mínimo, a cada, máximo.")
            condition_min, condition_per, condition_max = (condition_parts + [0, 0, 0])[:3]
            if not condition_status:
                condition_min = condition_per = condition_max = 0
            effect = SkillEffect(
                self.builder.selected_trigger, self.builder.selected_effect, value, coin, count,
                charge_cost, condition_status, condition_min,
                self.builder.selected_condition_owner, self.builder.selected_condition_value,
                condition_per, condition_max, consume_condition,
            )
            if coin is not None and coin > self.builder.coins:
                raise ValueError("Essa moeda não existe na skill.")
        except ValueError as error:
            await interaction.response.send_message(f"Efeito inválido: {error}", ephemeral=True)
            return
        self.builder.effects.append(effect)
        await interaction.response.edit_message(embed=self.editor.build_embed(), view=self.editor)


class SkillDamagePercentModal(LoggedModal, title="Dano percentual escalável"):
    """Formulário dedicado para evitar a sintaxe compacta do editor genérico."""
    def __init__(self, builder: "SkillBuilderView", editor: "SkillEffectsView") -> None:
        super().__init__()
        self.builder, self.editor = builder, editor
        self.percent = discord.ui.TextInput(
            label="Percentual por ativação", default="0.2",
            placeholder="Ex.: 0.2 ou -10", max_length=10,
        )
        self.minimum = discord.ui.TextInput(
            label="Valor mínimo para ativar", default="1", max_length=8,
        )
        self.every = discord.ui.TextInput(
            label="Uma ativação a cada X pontos", default="1", max_length=8,
        )
        self.maximum = discord.ui.TextInput(
            label="Máximo de ativações", default="200",
            placeholder="0 = sem limite", max_length=8,
        )
        self.consume = discord.ui.TextInput(
            label="Consumir a condição?", default="sim",
            placeholder="sim ou não", max_length=5,
        )
        for item in (self.percent, self.minimum, self.every, self.maximum, self.consume):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = float(str(self.percent).strip().replace(",", "."))
            minimum = int(str(self.minimum).strip() or "0")
            every = int(str(self.every).strip() or "0")
            maximum = int(str(self.maximum).strip() or "0")
            consume_text = str(self.consume).strip().casefold()
            if min(minimum, every, maximum) < 0 or consume_text not in {"sim", "s", "não", "nao", "n"}:
                raise ValueError
            condition = self.builder.selected_condition
            if condition is None:
                minimum = every = maximum = 0
            effect = SkillEffect(
                self.builder.selected_trigger, "damage_percent", value,
                condition_status=condition, condition_min=minimum,
                condition_owner=self.builder.selected_condition_owner,
                condition_value=self.builder.selected_condition_value,
                condition_per=every, condition_max_stacks=maximum,
                consume_condition=bool(condition) and consume_text in {"sim", "s"},
            )
        except ValueError:
            await interaction.response.send_message(
                "Use percentual decimal, números inteiros não negativos e `sim` ou `não` para consumo.",
                ephemeral=True,
            )
            return
        self.builder.effects.append(effect)
        await interaction.response.edit_message(embed=self.editor.build_embed(), view=self.editor)


class SkillRemoveEffectModal(LoggedModal, title="Remover efeito"):
    def __init__(self, builder: "SkillBuilderView", editor: "SkillEffectsView") -> None:
        super().__init__()
        self.builder, self.editor = builder, editor
        self.number = discord.ui.TextInput(
            label="Número do efeito", placeholder="Ex.: 2", max_length=2,
        )
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            index = int(str(self.number).strip()) - 1
            if not 0 <= index < len(self.builder.effects):
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Informe um número existente na lista de efeitos.", ephemeral=True)
            return
        self.builder.effects.pop(index)
        await interaction.response.edit_message(embed=self.editor.build_embed(), view=self.editor)


class SkillBuilderTypeSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        super().__init__(
            placeholder="1. Escolha o tipo da skill", row=0,
            options=[discord.SelectOption(label=label, value=value, default=value == builder.skill_type)
                     for value, label in SKILL_TYPE_LABELS.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            return
        self.builder.skill_type = self.values[0]
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderTriggerSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        super().__init__(
            placeholder="Quando o efeito ativa?", row=0,
            options=[discord.SelectOption(label=label, value=value) for value, label in TRIGGER_LABELS.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            return
        self.builder.selected_trigger = self.values[0]
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class SkillBuilderEffectSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        super().__init__(
            placeholder="Qual efeito será aplicado?", row=1,
            options=[
                discord.SelectOption(
                    label=label, value=value,
                    emoji=BUILDER_EFFECT_ICONS.get(value),
                    description=(
                        "Informe Potência e Quantidade" if value in STATUS_TYPES
                        else "Usa a Potência de Tremor do alvo" if value == "tremor_burst"
                        else "Consome Charge e transforma as moedas" if value == "make_unbreakable"
                        else "Informe o valor do modificador"
                    ),
                )
                for value, label in BUILDER_EFFECT_LABELS.items()
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            return
        self.builder.selected_effect = self.values[0]
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class SkillBuilderConditionSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        negative = ("burn", "bleed", "tremor", "rupture", "sinking")
        current = (
            "none" if builder.selected_condition is None else
            f"{builder.selected_condition_owner}:{builder.selected_condition}:"
            f"{builder.selected_condition_value}"
        )
        options = [discord.SelectOption(label="Sem condição", value="none", default=current == "none")]
        options.extend(
            discord.SelectOption(
                label=f"Alvo: {STATUS_LABELS[key]} Potência", value=f"target:{key}:potency",
                emoji=STATUS_ICONS[key], default=current == f"target:{key}:potency",
            ) for key in negative
        )
        for status in ("charge", "poise"):
            for metric, metric_label in (("count", "Quantidade"), ("potency", "Potência")):
                value = f"user:{status}:{metric}"
                options.append(discord.SelectOption(
                    label=f"Usuário: {STATUS_LABELS[status]} {metric_label}", value=value,
                    emoji=STATUS_ICONS[status], default=current == value,
                ))
        for status in ("burn", "bleed", "tremor", "rupture", "sinking"):
            options.extend(discord.SelectOption(
                label=f"Usuário: {STATUS_LABELS[status]} {metric_label}",
                value=f"user:{status}:{metric}", emoji=STATUS_ICONS[status],
                default=current == f"user:{status}:{metric}",
            ) for metric, metric_label in (("potency", "Potência"), ("count", "Quantidade")))
        for status in ("charge",):
            options.extend(discord.SelectOption(
                label=f"Alvo: {STATUS_LABELS[status]} {metric_label}",
                value=f"target:{status}:{metric}", emoji=STATUS_ICONS[status],
                default=current == f"target:{status}:{metric}",
            ) for metric, metric_label in (("potency", "Potência"), ("count", "Quantidade")))
        options.append(discord.SelectOption(
            label="Usuário: Condição Especial", value="user:special_condition:count",
            emoji=STATUS_ICONS["special_condition"], default=current == "user:special_condition:count",
        ))
        options.append(discord.SelectOption(
            label="Usuário: Condição consumida no Encounter",
            value="user:special_condition_consumed:count",
            emoji=STATUS_ICONS["special_condition"],
            default=current == "user:special_condition_consumed:count",
        ))
        options.append(discord.SelectOption(
            label="Alvo: Bloodfiend ou Bloodbag",
            value="target:bloodfiend_or_bloodbag:count",
            emoji="🧛", default=current == "target:bloodfiend_or_bloodbag:count",
        ))
        super().__init__(
            placeholder="Condição: quem possui e qual status?", row=2, options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            return
        if self.values[0] == "none":
            self.builder.selected_condition = None
            self.builder.selected_condition_owner = "target"
            self.builder.selected_condition_value = "potency"
        else:
            owner, status, metric = self.values[0].split(":")
            self.builder.selected_condition = status
            self.builder.selected_condition_owner = owner
            self.builder.selected_condition_value = metric
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class SkillBuilderCoinSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        options = [
            discord.SelectOption(
                label=f"Moeda {index}", value=str(index),
                description=(
                    f"{'Inquebrável' if kind == 'unbreakable' else 'Normal'}"
                    f" • Coin {builder.coin_power:+}"
                    f" • {sum(effect.coin == index for effect in builder.effects)} efeito(s)"
                )[:100],
                emoji=COIN_UNBREAKABLE if kind == "unbreakable" else COIN_ACTIVE,
                default=kind == "unbreakable",
            )
            for index, kind in enumerate(builder.coin_layout, 1)
        ]
        super().__init__(
            placeholder="Selecione as moedas inquebráveis", options=options,
            min_values=0, max_values=builder.coins, row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        selected = {int(value) for value in self.values}
        self.builder.coin_layout = [
            "unbreakable" if index in selected else "normal"
            for index in range(1, self.builder.coins + 1)
        ]
        self.builder.refresh_components()
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderTemplateSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        options = [
            discord.SelectOption(
                label="Por Favor... Só um Pouco.", value="please_a_little",
                description="Lust • 4 +3 • 2 moedas • Falsa Fome e Bleed",
                emoji=STATUS_ICONS["special_condition"],
            ),
            discord.SelectOption(
                label="Não Ouse Me Negar.", value="do_not_deny",
                description="Wrath • 4 +4 • 2 moedas • Falsa Fome e Bleed",
                emoji=STATUS_ICONS["bleed"],
            ),
        ]
        if builder.owner_id == PRIVATE_SKILL_OWNER_ID:
            options.extend([
                discord.SelectOption(
                    label="Eu Posso Ser Útil. 🔒", value="i_can_be_useful",
                    description="PRIVADA • Gloom • 5 +3 • 3 moedas",
                    emoji=STATUS_ICONS["special_condition"],
                ),
                discord.SelectOption(
                    label="Ajoelhe-se. 🔒", value="kneel",
                    description="PRIVADA • Pride • 5 +4 • 3 moedas",
                    emoji=STATUS_ICONS["bleed"],
                ),
                discord.SelectOption(
                    label="Aceite Minha Oferenda. 🔒", value="accept_my_offering",
                    description="PRIVADA • Lust • 6 +4 • 3 moedas",
                    emoji=STATUS_ICONS["special_condition"],
                ),
                discord.SelectOption(
                    label="Você Não Merece Esse Sangue. 🔒", value="you_do_not_deserve_blood",
                    description="PRIVADA • Wrath • 7 +4 • 4 moedas",
                    emoji=STATUS_ICONS["bleed"],
                ),
            ])
        super().__init__(
            placeholder="Carregar um modelo completo de skill", row=2,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if self.values[0] in {
            "i_can_be_useful", "kneel", "accept_my_offering", "you_do_not_deserve_blood",
        } and interaction.user.id != PRIVATE_SKILL_OWNER_ID:
            await interaction.response.send_message("Este modelo é privado e pertence a outro usuário.", ephemeral=True)
            return
        self.builder.load_template(self.values[0])
        self.builder.refresh_components()
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillEffectsView(LoggedView):
    def __init__(self, builder: "SkillBuilderView") -> None:
        super().__init__(timeout=900)
        self.builder = builder
        self.owner_id = builder.owner_id
        self.add_item(SkillBuilderTriggerSelect(builder))
        self.add_item(SkillBuilderEffectSelect(builder))
        self.add_item(SkillBuilderConditionSelect(builder))

    def build_embed(self) -> discord.Embed:
        embed = self.builder.build_embed()
        embed.title = "〔 SKILL WORKSHOP // EFEITOS 〕"
        condition = (
            "Sem condição"
            if self.builder.selected_condition is None else
            f"{self.builder.selected_condition_owner.title()} • "
            f"{STATUS_LABELS[self.builder.selected_condition]} • "
            f"{self.builder.selected_condition_value.title()}"
        )
        embed.description = (
            "## CONFIGURAÇÃO GUIADA\n"
            "Escolha **quando ativa**, **o resultado** e a **condição**. Depois use Adicionar.\n"
            f"`GATILHO` {TRIGGER_LABELS[self.builder.selected_trigger]}\n"
            f"`EFEITO` {BUILDER_EFFECT_LABELS[self.builder.selected_effect]}\n"
            f"`CONDIÇÃO` {condition}"
        )
        if self.builder.selected_effect == "damage_percent":
            embed.add_field(
                name="◇ FORMULÁRIO INTELIGENTE",
                value=(
                    "O próximo formulário pedirá separadamente: **% por ativação**, "
                    "**mínimo**, **a cada X**, **máximo** e **consumo**."
                ),
                inline=False,
            )
        return embed

    @discord.ui.button(label="Adicionar", emoji="➕", style=discord.ButtonStyle.primary, row=3)
    async def add_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if len(self.builder.effects) >= 20:
            await interaction.response.send_message("A skill já atingiu o limite de 20 efeitos.", ephemeral=True)
            return
        modal = (
            SkillDamagePercentModal(self.builder, self)
            if self.builder.selected_effect == "damage_percent"
            else SkillBuilderEffectModal(self.builder, self)
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remover por nº", emoji="🗑️", style=discord.ButtonStyle.secondary, row=3)
    async def remove_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if not self.builder.effects:
            await interaction.response.send_message("Ainda não há efeitos para remover.", ephemeral=True)
            return
        await interaction.response.send_modal(SkillRemoveEffectModal(self.builder, self))

    @discord.ui.button(label="Duplicar último", emoji="📑", style=discord.ButtonStyle.secondary, row=3)
    async def duplicate_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if not self.builder.effects:
            await interaction.response.send_message("Adicione um efeito antes de duplicar.", ephemeral=True)
            return
        if len(self.builder.effects) >= 20:
            await interaction.response.send_message("A skill já atingiu o limite de 20 efeitos.", ephemeral=True)
            return
        self.builder.effects.append(self.builder.effects[-1])
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Voltar à skill", emoji="⬅️", style=discord.ButtonStyle.success, row=4)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        self.builder.refresh_components()
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderView(LoggedView):
    def __init__(
        self, owner_id: int, existing: Skill | None = None, *,
        enemy_id: int | None = None, enemy_name: str | None = None,
    ) -> None:
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.enemy_id, self.enemy_name = enemy_id, enemy_name
        self.old_name = existing.name if existing else None
        self.name, self.description = ((existing.name, existing.description) if existing else ("Nova Skill", ""))
        self.base_power, self.coin_power = ((existing.base_power, existing.coin_power) if existing else (4, 2))
        self.coins = existing.coins if existing else 2
        self.coin_layout = list(existing.coin_layout) if existing else ["normal"] * self.coins
        self.skill_type = existing.skill_type if existing else "attack"
        self.selected_trigger, self.selected_effect = "on_hit", "paralysis"
        self.selected_condition: str | None = None
        self.selected_condition_owner = "target"
        self.selected_condition_value = "potency"
        self.effects: list[SkillEffect] = list(existing.effects) if existing else []
        self.refresh_components()

    @property
    def unbreakable_coins(self) -> int:
        return self.coin_layout.count("unbreakable")

    def resize_coins(self, coins: int) -> None:
        self.coin_layout = (self.coin_layout[:coins] + ["normal"] * coins)[:coins]
        self.coins = coins

    def refresh_components(self) -> None:
        buttons = [item for item in self.children if isinstance(item, discord.ui.Button)]
        self.clear_items()
        self.add_item(SkillBuilderTypeSelect(self))
        self.add_item(SkillBuilderCoinSelect(self))
        self.add_item(SkillBuilderTemplateSelect(self))
        for button in buttons:
            self.add_item(button)

    def owned_by(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    def trim_invalid_effects(self) -> None:
        self.effects = [effect for effect in self.effects if effect.coin is None or effect.coin <= self.coins]

    def load_template(self, template: str) -> None:
        model = skill_template(template)
        self.name, self.description = model.name, model.description
        self.base_power, self.coin_power, self.coins = model.base_power, model.coin_power, model.coins
        self.coin_layout = list(model.coin_layout)
        self.skill_type = model.skill_type
        self.effects = list(model.effects)

    def skill(self) -> Skill:
        return Skill(
            self.name, self.base_power, self.coin_power, self.coins, self.description,
            self.skill_type, self.unbreakable_coins, tuple(self.effects), tuple(self.coin_layout),
        )

    def build_embed(self) -> discord.Embed:
        low, high = self.skill().range_with()
        embed = discord.Embed(
            title="〔 SKILL WORKSHOP 〕",
            description=(
                f"## {self.name}\n"
                "Monte a skill usando as listas e botões abaixo. Você não precisa escrever códigos."
            ),
            color=GOLD,
        )
        embed.add_field(
            name="◆ NÚCLEO DA SKILL",
            value=(
                f"**Tipo:** {SKILL_TYPE_LABELS[self.skill_type]}\n"
                f"**Base:** `{self.base_power}` • **Coin:** `{self.coin_power:+}`\n"
                f"**Moedas:** `{self.coins}` • **Inquebráveis:** `{self.unbreakable_coins}`\n"
                f"**Ordem:** {''.join(COIN_UNBREAKABLE if kind == 'unbreakable' else COIN_ACTIVE for kind in self.coin_layout)}\n"
                f"**Faixa:** `{low}–{high}`"
            ), inline=False,
        )
        coin_lines = []
        for position, kind in enumerate(self.coin_layout, 1):
            sturdy = kind == "unbreakable"
            linked = [effect for effect in self.effects if effect.coin == position]
            effect_summary = ""
            if linked:
                first = linked[0]
                effect_summary = (
                    f" • `{TRIGGER_LABELS[first.trigger]}` {builder_effect_text(first)}"
                )
                if len(linked) > 1:
                    effect_summary += f" `+{len(linked) - 1}`"
            coin_lines.append(
                f"`{position:02}` "
                f"{COIN_UNBREAKABLE if sturdy else COIN_ACTIVE} "
                f"**{'INQUEBRÁVEL' if sturdy else 'NORMAL'}** "
                f"• Coin `{self.coin_power:+}`{effect_summary}"
            )
        for page, start in enumerate(range(0, len(coin_lines), 5)):
            embed.add_field(
                name="◆ MAPA DAS MOEDAS" if page == 0 else "◆ MAPA DAS MOEDAS // CONTINUAÇÃO",
                value="\n".join(coin_lines[start:start + 5]),
                inline=False,
            )
        embed.add_field(
            name="◇ LEGENDA DAS VARIÁVEIS",
            value=(
                f"{COIN_ACTIVE} **Normal** • desaparece ao ser quebrada\n"
                f"{COIN_UNBREAKABLE} **Inquebrável** • fratura e prepara follow-up\n"
                "`Coin` • poder somado quando a moeda consegue Heads\n"
                "`Efeito por moeda` • ativa somente na posição indicada"
            ),
            inline=False,
        )
        if self.description:
            embed.add_field(name="◇ DESCRIÇÃO", value=self.description, inline=False)
        effect_lines = [
            f"`{index:02}` **{TRIGGER_LABELS[effect.trigger]}** → "
            f"{builder_effect_text(effect)}"
            + (f" • moeda `{effect.coin}`" if effect.coin is not None else "")
            for index, effect in enumerate(self.effects, 1)
        ]
        embed.add_field(
            name="◆ EFEITOS",
            value="\n".join(effect_lines) if effect_lines else "Nenhum efeito adicionado.", inline=False,
        )
        embed.add_field(
            name="◇ PRÓXIMO EFEITO",
            value=f"**{TRIGGER_LABELS[self.selected_trigger]}** → {BUILDER_EFFECT_LABELS[self.selected_effect]}",
            inline=False,
        )
        embed.set_footer(text="Defina dados • selecione as inquebráveis • configure efeitos • salve")
        return embed

    @discord.ui.button(label="Definir dados", emoji="✏️", style=discord.ButtonStyle.secondary, row=3)
    async def basics(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        await interaction.response.send_modal(SkillBuilderBasicsModal(self))

    @discord.ui.button(label="Configurar efeitos", emoji="✨", style=discord.ButtonStyle.primary, row=3)
    async def add_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        editor = SkillEffectsView(self)
        await interaction.response.edit_message(embed=editor.build_embed(), view=editor)

    @discord.ui.button(label="Normalizar moedas", emoji="↩️", style=discord.ButtonStyle.secondary, row=3)
    async def remove_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        self.coin_layout = ["normal"] * self.coins
        self.refresh_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Salvar skill", emoji="💾", style=discord.ButtonStyle.success, row=4)
    async def save(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if self.enemy_id is None and db.get_character(gid(interaction), interaction.user.id) is None:
            await interaction.response.send_message("Crie sua ficha antes de salvar uma skill.", ephemeral=True)
            return
        try:
            skill = self.skill()
        except ValueError as error:
            await interaction.response.send_message(f"Não foi possível salvar: {error}", ephemeral=True)
            return
        if skill.name.casefold() in PRIVATE_SKILL_NAMES and interaction.user.id != PRIVATE_SKILL_OWNER_ID:
            await interaction.response.send_message(
                "Esta skill é privada e somente o proprietário configurado pode salvá-la.",
                ephemeral=True,
            )
            return
        if self.enemy_id is not None:
            if self.old_name and self.old_name.casefold() != skill.name.casefold():
                db.delete_enemy_skill(self.enemy_id, self.old_name)
            db.save_enemy_skill(self.enemy_id, skill)
            audit(interaction, "SKILL INIMIGA SALVA NO LAB", f"{self.enemy_name}: {skill.name}")
        else:
            if self.old_name and self.old_name.casefold() != skill.name.casefold():
                db.delete_skill(gid(interaction), interaction.user.id, self.old_name)
            db.save_skill(gid(interaction), interaction.user.id, skill)
            audit(interaction, "SKILL SALVA NO WORKSHOP", skill.name)
        await interaction.response.edit_message(
            embed=skills_embed([skill], "✅ Skill inimiga salva" if self.enemy_id else "✅ Skill criada"),
            view=EnemyManagerView() if self.enemy_id else SkillsView(),
        )


class DeleteCharacterConfirmView(LoggedView):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=60)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Esta confirmação não pertence a você.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar remoção", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        removed = db.delete_character(gid(interaction), interaction.user.id)
        audit(interaction, "FICHA REMOVIDA PELO PAINEL", f"removida={removed}")
        await interaction.response.edit_message(
            content="✅ Sua ficha, skills, status e aparência foram removidos." if removed else "Você não possui ficha.",
            embed=None, view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Remoção cancelada.", embed=None, view=None)


class PanelView(LoggedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Minha ficha", emoji="🧠", style=discord.ButtonStyle.primary)
    async def sheet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        if row is None:
            await interaction.response.send_message("Crie sua ficha com `/personagem criar`.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=character_embed(row, interaction.user), view=CharacterView(), ephemeral=True
        )

    @discord.ui.button(label="Criar ficha", emoji="➕", style=discord.ButtonStyle.success, row=2)
    async def create_sheet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        command_mention = "`/personagem criar`"
        try:
            commands_in_guild = await interaction.client.tree.fetch_commands(guild=interaction.guild)
            root = next((command for command in commands_in_guild if command.name == "personagem"), None)
            if root is not None:
                command_mention = f"</personagem criar:{root.id}>"
        except discord.HTTPException as error:
            audit(interaction, "ATALHO DE COMANDO INDISPONÍVEL", str(error))
        embed = discord.Embed(
            title="【 CRIAR FICHA 】",
            description=(
                f"Clique em {command_mention} para abrir o comando.\n\n"
                "Preencha **nome** e use o campo **imagem** para anexar o arquivo. "
                "A imagem será guardada automaticamente no canal de mídia do bot."
            ),
            color=ACCENT,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Remover ficha", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def remove_sheet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        if row is None:
            await interaction.response.send_message("Você ainda não possui ficha.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Remover permanentemente **{row['name']}** e todas as skills/status dessa ficha?",
            view=DeleteCharacterConfirmView(interaction.user.id), ephemeral=True,
        )

    @discord.ui.button(label="Oficina de skills", emoji="🪙", style=discord.ButtonStyle.secondary)
    async def skills(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=skills_embed(db.list_skills(gid(interaction), interaction.user.id), "〔 SKILL WORKSHOP 〕"),
            view=SkillsView(), ephemeral=True
        )

    @discord.ui.button(label="Rolar dano", emoji="🎲", style=discord.ButtonStyle.primary, row=1)
    async def roll_damage(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        skills = [
            skill for skill in db.list_skills(gid(interaction), interaction.user.id)
            if skill.deals_damage
        ]
        if not skills:
            await interaction.response.send_message(
                "Crie uma skill Normal, Counter ou Counter Clashable primeiro.", ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="〔 DAMAGE CALCULATOR 〕",
            description="Escolha uma skill. Depois, informe o Defense Level do alvo.",
            color=GOLD,
        )
        await interaction.response.send_message(
            embed=embed, view=DamageSkillView(skills), ephemeral=True,
        )

    @discord.ui.button(label="Batalha", emoji="⚔️", style=discord.ButtonStyle.danger, row=1)
    async def battle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if db.get_battle(gid(interaction), interaction.channel_id) is None:
            await interaction.response.send_message(
                "Não existe batalha ativa neste canal. O mestre pode usar `/batalha iniciar`.", ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        updated = await update_fixed_battle_panel(interaction)
        await interaction.followup.send(
            "✅ Painel fixo atualizado." if updated else "Não encontrei o painel fixo; use `/batalha painel` para recriá-lo.",
            ephemeral=True,
        )

    @discord.ui.button(label="Regras", emoji="📖", style=discord.ButtonStyle.secondary)
    async def rules(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        embed = discord.Embed(title="Regras rápidas", color=ACCENT)
        embed.description = render_custom_emojis(interaction, (
            "### 〔 SISTEMA DE CLASH 〕\n"
            "**Sanidade:** Heads = 50% + SP, limitada entre 5% e 95%.\n"
            "**Rodada:** todas as moedas restantes são roladas; o perdedor quebra uma moeda.\n"
            "**Empate:** ninguém perde moeda e a rodada é repetida.\n"
            f"{EFFECT_PARALYZE} **Paralisia:** zera o Coin Power das próximas moedas roladas.\n"
            f"{EFFECT_ATTACK_UP}{EFFECT_ATTACK_DOWN} **Base Power:** vale durante o próximo Clash.\n"
            f"{EFFECT_PLUS_COIN_BOOST}{EFFECT_PLUS_COIN_DROP} **Coin Power:** altera Plus Coins.\n"
            f"{EFFECT_CLASH_UP}{EFFECT_CLASH_DOWN} **Clash Power:** soma diretamente ao Clash.\n"
            f"{EFFECT_OFFENSE_UP}{EFFECT_OFFENSE_DOWN} **Offense Level:** altera o nível ofensivo temporariamente.\n"
            "**Níveis:** Normal/Counter usam Offense; Defesa/Evasiva usam Defense.\n"
            "**Defesa:** apenas rola e mostra uma moeda; o mestre interpreta.\n"
            "**Evasiva:** testa separadamente contra cada moeda ofensiva.\n"
            "**Counter:** rola uma moeda sem Clash ou mudança de SP e calcula seu dano.\n"
            "**Counter Clashable:** disputa normalmente e causa dano com as moedas restantes.\n"
            "**Dano:** cada Heads aumenta o poder anterior; só o último valor recebe `(Offense − Defense) ÷ 3`.\n"
            "**Clashable:** disputa moedas normalmente; Assist Defense intercepta como Guard Clashable.\n"
            "**Inimigo sem sanidade:** usa sempre 50% de Heads e não altera SP.\n"
            "**Previsão:** projeta 5 Clashes; indica tendência, nunca certeza."
        ))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Mestre • Inimigos", emoji="👁️", style=discord.ButtonStyle.danger)
    async def enemies(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=enemy_manager_embed(gid(interaction)), view=EnemyManagerView(), ephemeral=True
        )


def audit_discord_chunks(records: list[str], limit: int = 1850) -> list[str]:
    """Agrupa registros preservando os blocos dentro do limite de mensagem."""
    chunks: list[str] = []
    current = ""
    for record in records:
        clean = record.replace("```", "'''" ).strip()
        while len(clean) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(clean[:limit])
            clean = clean[limit:]
        candidate = f"{current}\n{clean}".strip() if current else clean
        if len(candidate) > limit:
            chunks.append(current)
            current = clean
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def discord_audit_worker(bot_instance: commands.Bot) -> None:
    """Envia a fila em lotes para reduzir spam e respeitar os limites do Discord."""
    await bot_instance.wait_until_ready()
    channel = bot_instance.get_channel(AUDIT_CHANNEL_ID) if AUDIT_CHANNEL_ID else None
    if channel is None and AUDIT_CHANNEL_ID:
        try:
            channel = await bot_instance.fetch_channel(AUDIT_CHANNEL_ID)
        except (discord.HTTPException, discord.InvalidData, discord.NotFound, discord.Forbidden) as error:
            print(f"[AUDITORIA DISCORD INDISPONÍVEL] canal={AUDIT_CHANNEL_ID} | {type(error).__name__}: {error}")
    while not bot_instance.is_closed():
        await asyncio.sleep(0.8)
        if channel is None or not DISCORD_AUDIT_QUEUE:
            continue
        records = []
        while DISCORD_AUDIT_QUEUE and len(records) < 30:
            records.append(DISCORD_AUDIT_QUEUE.popleft())
        try:
            for chunk in audit_discord_chunks(records):
                await channel.send(f"```text\n{chunk}\n```", allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, discord.Forbidden) as error:
            for record in reversed(records):
                DISCORD_AUDIT_QUEUE.appendleft(record)
            print(f"[ERRO AO ENVIAR AUDITORIA] canal={AUDIT_CHANNEL_ID} | {type(error).__name__}: {error}")
            await asyncio.sleep(5)


class ControlCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command = interaction.command
        if command and command.qualified_name in disabled_commands():
            audit(
                interaction, "COMANDO BLOQUEADO PELA CENTRAL",
                f"/{command.qualified_name}",
            )
            await interaction.response.send_message(
                "Este comando foi temporariamente desativado na Central do bot.", ephemeral=True,
            )
            return False
        return True


async def media_upload_worker(bot_instance: commands.Bot) -> None:
    """Publica no Discord as imagens enfileiradas pela Central local."""
    await bot_instance.wait_until_ready()
    upload_dir = Path(__file__).with_name("control_center_uploads")
    while not bot_instance.is_closed():
        for job in db.pending_media_uploads():
            try:
                source = job["source_url"]
                if source.startswith("/uploads/"):
                    target = upload_dir / Path(source).name
                    if not target.is_file() or target.parent.resolve() != upload_dir.resolve():
                        raise FileNotFoundError("arquivo local da Central não encontrado")
                    data = target.read_bytes()
                    filename = target.name
                else:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(source, timeout=aiohttp.ClientTimeout(total=25)) as response:
                            if response.status >= 400:
                                raise RuntimeError(f"download respondeu HTTP {response.status}")
                            data = await response.read()
                            content_type = response.headers.get("Content-Type", "image/png").split(";", 1)[0]
                            extension = {"image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(content_type, ".png")
                            filename = f"appearance-{job['id']}{extension}"
                if len(data) > 8 * 1024 * 1024:
                    raise ValueError("imagem maior que 8 MB")
                channel = bot_instance.get_channel(APPEARANCE_CHANNEL_ID)
                if channel is None:
                    channel = await bot_instance.fetch_channel(APPEARANCE_CHANNEL_ID)
                message = await channel.send(
                    content=(
                        f"🖼️ **ARQUIVO DE APARÊNCIA**\nTipo: `{job['owner_kind']}` • "
                        f"Servidor: `{job['guild_id']}` • Registro: `{job['owner_id']}`"
                    ),
                    file=discord.File(io.BytesIO(data), filename=filename),
                )
                if not message.attachments:
                    raise RuntimeError("Discord não devolveu o anexo")
                result_url = message.attachments[0].url
                db.finish_media_upload(job["id"], result_url)
                audit_logger.info("[MÍDIA SINCRONIZADA] job=%s | url=%s", job["id"], result_url)
            except Exception as error:
                db.fail_media_upload(job["id"], f"{type(error).__name__}: {error}")
                audit_logger.error("[FALHA AO SINCRONIZAR MÍDIA] job=%s | %s: %s", job["id"], type(error).__name__, error)
        await asyncio.sleep(2)


class ClashBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!", intents=discord.Intents.default(), tree_cls=ControlCommandTree,
        )

    async def setup_hook(self) -> None:
        global AUDIT_WORKER_TASK, MEDIA_WORKER_TASK
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(self.async_exception_handler)
        if AUDIT_CHANNEL_ID and (AUDIT_WORKER_TASK is None or AUDIT_WORKER_TASK.done()):
            AUDIT_WORKER_TASK = asyncio.create_task(
                discord_audit_worker(self), name="discord-audit-worker",
            )
        db.setup()
        if MEDIA_WORKER_TASK is None or MEDIA_WORKER_TASK.done():
            MEDIA_WORKER_TASK = asyncio.create_task(
                media_upload_worker(self), name="media-upload-worker",
            )
        self.add_view(BattlePanelView())
        if GUILD_IDS:
            for guild_id in GUILD_IDS:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        for guild in self.guilds:
            db.save_guild(guild.id, guild.name)
        audit_logger.info(
            "[ONLINE] %s | servidores=%d | arquivo=%s | canal_auditoria=%s",
            self.user, len(self.guilds), AUDIT_PATH, AUDIT_CHANNEL_ID or "DESATIVADO",
        )

    @staticmethod
    def async_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        code = error_code()
        error = context.get("exception")
        message = context.get("message", "erro assíncrono sem mensagem")
        if error is None:
            audit_logger.error("[ERRO ASSÍNCRONO %s] %s | contexto=%s", code, message, context)
            return
        audit_logger.error(
            "[ERRO ASSÍNCRONO %s] %s | tipo=%s | detalhe=%s\n%s",
            code, message, type(error).__name__, error,
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        )

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        code = error_code()
        audit_logger.exception(
            "[ERRO DE EVENTO %s] evento=%s | args=%s | kwargs=%s",
            code, event_method, str(args)[:300], str(kwargs)[:300],
        )


bot = ClashBot()
personagem = app_commands.Group(name="personagem", description="Ficha, níveis e efeitos")
skill_group = app_commands.Group(name="skill", description="Crie e consulte skills")
inimigo_group = app_commands.Group(name="inimigo", description="Mestre: gerencie inimigos")
batalha_group = app_commands.Group(name="batalha", description="Sessão e skills presentes no campo")


@bot.listen("on_interaction")
async def interaction_audit(interaction: discord.Interaction) -> None:
    if len(INTERACTION_STARTED) >= 2000:
        for old_id in list(INTERACTION_STARTED)[:1000]:
            INTERACTION_STARTED.pop(old_id, None)
    INTERACTION_STARTED[interaction.id] = time.monotonic()
    labels = {
        discord.InteractionType.application_command: "COMANDO RECEBIDO",
        discord.InteractionType.component: "BOTÃO/SELEÇÃO RECEBIDO",
        discord.InteractionType.modal_submit: "FORMULÁRIO ENVIADO",
    }
    audit(interaction, labels.get(interaction.type, "INTERAÇÃO RECEBIDA"), safe_interaction_data(interaction))


@bot.tree.command(name="painel", description="Abre o painel interativo do RPG")
async def painel(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="⚔️ Clash RPG",
        description="Gerencie sua ficha e suas skills pelos botões abaixo.\nPara lutar, use `/clash`.",
        color=ACCENT,
    )
    embed.set_footer(text="Clash • Sanidade • Moedas • Efeitos")
    await interaction.response.send_message(embed=embed, view=PanelView())


@batalha_group.command(name="iniciar", description="Mestre: inicia uma sessão de batalha neste canal")
@app_commands.checks.has_permissions(manage_guild=True)
async def batalha_iniciar(interaction: discord.Interaction, nome: str) -> None:
    battle = db.start_battle(gid(interaction), interaction.channel_id, nome[:80], interaction.user.id)
    audit(interaction, "BATALHA INICIADA", f"nome={battle['name']}; turno=1")
    await interaction.response.send_message(embed=combat_encounter_embed(battle["name"], interaction.user))
    panel_message = await interaction.followup.send(
        embed=battle_embed(interaction), view=BattlePanelView(), wait=True,
    )
    db.set_battle_panel_message(interaction.guild_id, interaction.channel_id, panel_message.id)
    audit(interaction, "PAINEL FIXO CRIADO", f"mensagem={panel_message.id}")


@batalha_group.command(name="painel", description="Mostra as skills inimigas presentes no campo")
async def batalha_painel(interaction: discord.Interaction) -> None:
    if db.get_battle(gid(interaction), interaction.channel_id) is None:
        await interaction.response.send_message("Não existe batalha ativa neste canal.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    if await update_fixed_battle_panel(interaction):
        await interaction.followup.send("✅ Painel fixo atualizado.", ephemeral=True)
        return
    panel_message = await interaction.channel.send(embed=battle_embed(interaction), view=BattlePanelView())
    db.set_battle_panel_message(interaction.guild_id, interaction.channel_id, panel_message.id)
    await interaction.followup.send("✅ Um novo painel fixo foi criado.", ephemeral=True)


@batalha_group.command(name="colocar_skill", description="Mestre: coloca uma skill inimiga no campo")
@app_commands.checks.has_permissions(manage_guild=True)
async def batalha_colocar_skill(
    interaction: discord.Interaction, inimigo: str, skill_inimiga: str,
) -> None:
    battle = db.get_battle(gid(interaction), interaction.channel_id)
    enemy = db.get_enemy(interaction.guild_id, inimigo)
    skill = None if enemy is None else db.get_enemy_skill(enemy["id"], skill_inimiga)
    if battle is None:
        await interaction.response.send_message("Inicie uma batalha neste canal primeiro.", ephemeral=True)
        return
    if battle["phase"] != "preparation":
        await interaction.response.send_message(
            "O campo só pode ser montado durante a fase de **Preparação**. Use `/batalha reabrir_fase` se precisar corrigir algo.",
            ephemeral=True,
        )
        return
    if enemy is None or skill is None:
        await interaction.response.send_message("Inimigo ou skill não encontrada.", ephemeral=True)
        return
    if not skill.is_clashable:
        await interaction.response.send_message(
            "Neste primeiro MVP, coloque apenas skills capazes de disputar Clash.", ephemeral=True,
        )
        return
    action = db.add_field_action(interaction.guild_id, interaction.channel_id, enemy["name"], skill.name)
    advanced, transition_message = advance_battle_when_ready(gid(interaction), interaction.channel_id)
    audit(interaction, "SKILL COLOCADA NO CAMPO", f"ação=#{action['id']}; {enemy['name']} / {skill.name}")
    await interaction.response.defer(ephemeral=True)
    updated = await update_fixed_battle_panel(interaction)
    await interaction.followup.send(
        f"✅ **{enemy['name']}** colocou `{skill.name}` no campo como ação `#{action['id']}`."
        + (f" {transition_message}" if advanced else "")
        + ("" if updated else " O painel fixo não foi encontrado; use `/batalha painel`."),
        ephemeral=True,
    )


@batalha_group.command(name="avancar_fase", description="Mestre: avança a fase atual da batalha")
@app_commands.checks.has_permissions(manage_guild=True)
async def batalha_avancar_fase(interaction: discord.Interaction) -> None:
    battle = db.get_battle(gid(interaction), interaction.channel_id)
    if battle is None:
        await interaction.response.send_message("Não existe batalha ativa neste canal.", ephemeral=True)
        return
    transitions = {
        "preparation": "declaration",
        "declaration": "resolution",
        "resolution": "complete",
    }
    next_phase = transitions.get(battle["phase"])
    if next_phase is None:
        await interaction.response.send_message(
            "O turno já está encerrado. Use `/batalha avancar_turno`.", ephemeral=True,
        )
        return
    if battle["phase"] == "preparation":
        actions = db.list_field_actions(gid(interaction), interaction.channel_id)
        participants = db.list_battle_participants(gid(interaction), interaction.channel_id)
        if not actions or not participants:
            await interaction.response.send_message(
                "Para abrir as declarações, é necessário ter pelo menos um participante e uma ação hostil no campo.",
                ephemeral=True,
            )
            return
    if battle["phase"] == "declaration":
        claimed = db.list_field_actions(gid(interaction), interaction.channel_id, "claimed")
        if claimed:
            await interaction.response.send_message(
                "Ainda existe um Clash em resolução. Aguarde sua conclusão antes de bloquear as declarações.",
                ephemeral=True,
            )
            return
    db.set_battle_phase(gid(interaction), interaction.channel_id, next_phase)
    db.reset_battle_readiness(gid(interaction), interaction.channel_id)
    audit(interaction, "FASE AVANÇADA", f"{battle['phase']} -> {next_phase}")
    await interaction.response.defer(ephemeral=True)
    await update_fixed_battle_panel(interaction)
    await interaction.followup.send(f"Fase alterada para **{next_phase.upper()}**.", ephemeral=True)


@batalha_group.command(name="reabrir_fase", description="Mestre: retorna a batalha para a fase anterior")
@app_commands.checks.has_permissions(manage_guild=True)
async def batalha_reabrir_fase(interaction: discord.Interaction) -> None:
    battle = db.get_battle(gid(interaction), interaction.channel_id)
    if battle is None:
        await interaction.response.send_message("Não existe batalha ativa neste canal.", ephemeral=True)
        return
    transitions = {
        "declaration": "preparation",
        "resolution": "declaration",
        "complete": "resolution",
    }
    previous_phase = transitions.get(battle["phase"])
    if previous_phase is None:
        await interaction.response.send_message("A batalha já está na fase inicial.", ephemeral=True)
        return
    db.set_battle_phase(gid(interaction), interaction.channel_id, previous_phase)
    if battle["phase"] == "complete":
        db.reset_battle_readiness(gid(interaction), interaction.channel_id)
    audit(interaction, "FASE REABERTA", f"{battle['phase']} -> {previous_phase}")
    await interaction.response.defer(ephemeral=True)
    await update_fixed_battle_panel(interaction)
    await interaction.followup.send(f"Fase reaberta em **{previous_phase.upper()}**.", ephemeral=True)


@batalha_group.command(name="avancar_turno", description="Mestre: avança o turno e limpa o campo")
@app_commands.checks.has_permissions(manage_guild=True)
async def batalha_avancar_turno(interaction: discord.Interaction) -> None:
    current = db.get_battle(gid(interaction), interaction.channel_id)
    if current is None:
        await interaction.response.send_message("Não existe batalha ativa neste canal.", ephemeral=True)
        return
    if current["phase"] != "complete":
        await interaction.response.send_message(
            "Encerre a fase atual antes de avançar o turno. Use `/batalha avancar_fase`.", ephemeral=True,
        )
        return
    battle = db.next_battle_turn(gid(interaction), interaction.channel_id)
    audit(interaction, "TURNO AVANÇADO", f"turno={battle['turn']}; campo limpo")
    await interaction.response.defer(ephemeral=True)
    updated = await update_fixed_battle_panel(interaction)
    status_embed = round_status_embed(gid(interaction), db.last_round_status_events)
    output_channel = await clash_output_channel(interaction)
    if status_embed is not None and output_channel is not None:
        await output_channel.send(embed=status_embed)
    await interaction.followup.send(
        f"⏭️ Turno **{battle['turn']}** iniciado; o campo foi limpo."
        + ("" if updated else " O painel fixo não foi encontrado; use `/batalha painel`."),
        ephemeral=True,
    )


@batalha_group.command(name="encerrar", description="Mestre: encerra a batalha deste canal")
@app_commands.checks.has_permissions(manage_guild=True)
async def batalha_encerrar(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    battle = db.get_battle(gid(interaction), interaction.channel_id)
    ended = db.end_battle(interaction.guild_id, interaction.channel_id)
    audit(interaction, "BATALHA ENCERRADA", f"encerrada={ended}")
    if ended and battle is not None and battle["panel_message_id"]:
        try:
            panel = await interaction.channel.fetch_message(battle["panel_message_id"])
            await panel.edit(embed=combat_ended_embed(battle["name"], battle["turn"]), view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
            audit_logger.error("[PAINEL FIXO] falha ao encerrar visualmente | %s", error)
    await interaction.followup.send(
        "🏁 Batalha encerrada." if ended else "Não existe batalha ativa neste canal.", ephemeral=True,
    )


@batalha_colocar_skill.autocomplete("inimigo")
async def batalha_enemy_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild_id is None:
        return []
    return [app_commands.Choice(name=enemy["name"], value=enemy["name"])
            for enemy in db.list_enemies(interaction.guild_id)
            if current.lower() in enemy["name"].lower()][:25]


@batalha_colocar_skill.autocomplete("skill_inimiga")
async def batalha_enemy_skill_autocomplete(interaction: discord.Interaction, current: str):
    enemy_name = getattr(interaction.namespace, "inimigo", None)
    if interaction.guild_id is None or not enemy_name:
        return []
    enemy = db.get_enemy(interaction.guild_id, enemy_name)
    if enemy is None:
        return []
    return [app_commands.Choice(name=skill.name, value=skill.name)
            for skill in db.list_enemy_skills(enemy["id"])
            if skill.is_clashable and current.lower() in skill.name.lower()][:25]


@personagem.command(name="criar", description="Cria/renomeia sua ficha e aceita uma imagem anexada")
async def personagem_criar(
    interaction: discord.Interaction, nome: str, imagem: discord.Attachment | None = None,
) -> None:
    await interaction.response.defer()
    db.create_character(gid(interaction), interaction.user.id, nome[:50])
    row = db.get_character(interaction.guild_id, interaction.user.id)
    if imagem is not None:
        try:
            image_url = await store_character_image(interaction, imagem, interaction.user.id, row["name"])
            db.save_appearance(
                gid(interaction), "player", interaction.user.id, image_url, "#b31824", "",
            )
        except (ValueError, discord.HTTPException, discord.Forbidden) as error:
            image_url = imagem.url
            db.save_appearance(
                gid(interaction), "player", interaction.user.id, image_url, "#b31824", "",
            )
            audit(
                interaction, "COFRE DE IMAGEM INDISPONÍVEL",
                f"fallback={image_url}; {type(error).__name__}: {error}",
            )
            await interaction.followup.send(
                "⚠️ A imagem foi aplicada usando o anexo original, mas não consegui criar uma "
                "cópia no canal-cofre. Confira as permissões desse canal.", ephemeral=True,
            )
    audit(interaction, "FICHA CRIADA POR COMANDO", f"nome={row['name']}; imagem={imagem is not None}")
    await interaction.followup.send(embed=character_embed(row, interaction.user))


@personagem.command(name="remover", description="Remove permanentemente sua ficha, skills e status")
async def personagem_remover(interaction: discord.Interaction, confirmar: bool) -> None:
    if not confirmar:
        await interaction.response.send_message("Remoção cancelada.", ephemeral=True)
        return
    removed = db.delete_character(gid(interaction), interaction.user.id)
    audit(interaction, "FICHA REMOVIDA POR COMANDO", f"removida={removed}")
    await interaction.response.send_message(
        "✅ Sua ficha, skills, status e aparência foram removidos." if removed else "Você não possui ficha.",
        ephemeral=True,
    )


@personagem.command(name="imagem", description="Troca a imagem da sua ficha usando um anexo")
async def personagem_imagem(interaction: discord.Interaction, imagem: discord.Attachment) -> None:
    row = db.get_character(gid(interaction), interaction.user.id)
    if row is None:
        await interaction.response.send_message("Crie sua ficha primeiro com `/personagem criar`.", ephemeral=True)
        return
    if not imagem.content_type or not imagem.content_type.startswith("image/"):
        await interaction.response.send_message("O anexo precisa ser uma imagem PNG, JPG, GIF ou WEBP.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    warning = ""
    try:
        image_url = await store_character_image(interaction, imagem, interaction.user.id, row["name"])
    except (ValueError, discord.HTTPException, discord.Forbidden) as error:
        image_url = imagem.url
        warning = "\n⚠️ O canal-cofre recusou a cópia; usei o anexo original."
        audit(interaction, "COFRE DE IMAGEM INDISPONÍVEL", f"fallback={image_url}; {error}")
    current = db.get_appearance(gid(interaction), "player", interaction.user.id)
    db.save_appearance(
        gid(interaction), "player", interaction.user.id, image_url,
        current["accent_color"] if current else "#b31824",
        current["subtitle"] if current else "",
    )
    audit(interaction, "IMAGEM DE FICHA ATUALIZADA", f"url={image_url}")
    row = db.get_character(gid(interaction), interaction.user.id)
    await interaction.followup.send(
        content=f"✅ Imagem atualizada.{warning}",
        embed=character_embed(row, interaction.user), ephemeral=True,
    )


@personagem.command(name="status", description="Exibe uma ficha")
async def personagem_status(interaction: discord.Interaction, jogador: discord.Member | None = None) -> None:
    jogador = jogador or interaction.user
    row = db.get_character(gid(interaction), jogador.id)
    if row is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    view = CharacterView() if jogador.id == interaction.user.id else None
    await interaction.response.send_message(embed=character_embed(row, jogador), view=view)


@personagem.command(name="niveis", description="Mestre: define Offense e Defense Level")
@app_commands.checks.has_permissions(manage_guild=True)
async def personagem_nivel(interaction: discord.Interaction, jogador: discord.Member, offense: int, defense: int) -> None:
    row = db.set_levels(gid(interaction), jogador.id, offense, defense)
    if row is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    await interaction.response.send_message(embed=character_embed(row, jogador))


@personagem.command(name="sanidade", description="Mestre: altera SP (valor positivo ou negativo)")
@app_commands.checks.has_permissions(manage_guild=True)
async def personagem_sanidade(interaction: discord.Interaction, jogador: discord.Member, alteracao: int) -> None:
    row = db.change_sp(gid(interaction), jogador.id, alteracao)
    if row is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    audit(interaction, "SANIDADE", f"alvo={jogador} alteração={alteracao:+d} resultado={row['sp']:+d} SP")
    await interaction.response.send_message(
        f"🧠 Sanidade de **{row['name']}** alterada para **{row['sp']:+d} SP**.",
        ephemeral=True,
    )


@personagem.command(name="efeitos", description="Mestre: adiciona Paralisia e Power Up/Down")
@app_commands.checks.has_permissions(manage_guild=True)
async def personagem_efeitos(
    interaction: discord.Interaction, jogador: discord.Member,
    paralisia: int = 0, base_power: int = 0, coin_power: int = 0,
    clash_power: int = 0, offense_level: int = 0, defense_level: int = 0,
) -> None:
    row = db.add_effects(
        gid(interaction), jogador.id, paralisia, base_power, coin_power,
        clash_power, offense_level, defense_level,
    )
    if row is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    audit(interaction, "EFEITOS", f"alvo={jogador} Paralisia+={paralisia}, Base+={base_power}, Coin+={coin_power}, Clash+={clash_power}, OL+={offense_level}, DL+={defense_level}")
    await interaction.response.send_message(embed=character_embed(row, jogador))


@personagem.command(name="status_principal", description="Mestre: define Potência e Quantidade de um status")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(status=[app_commands.Choice(name=STATUS_LABELS[name], value=name) for name in sorted(PUBLIC_STATUS_TYPES)])
async def personagem_status_principal(
    interaction: discord.Interaction, jogador: discord.Member,
    status: app_commands.Choice[str], potencia: int, quantidade: int,
) -> None:
    if db.get_character(gid(interaction), jogador.id) is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    try:
        saved = db.set_status(gid(interaction), "player", jogador.id, status.value, potencia, quantidade)
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    audit(interaction, "STATUS PRINCIPAL", f"alvo={jogador}; {saved.status_type}; P={saved.potency}; C={saved.count}")
    await interaction.response.send_message(
        f"{STATUS_ICONS[saved.status_type]} **{saved.status_type.title()}** de {jogador.mention}: "
        f"Potência **{saved.potency}** • Quantidade **{saved.count}**.", ephemeral=True,
    )


async def skill_criar(
    interaction: discord.Interaction, nome: str, poder_base: int, poder_moeda: int,
    moedas: app_commands.Range[int, 1, 10], tipo: app_commands.Choice[str], descricao: str = "",
    moedas_inquebraveis: app_commands.Range[int, 0, 10] = 0,
    efeitos: str = "",
) -> None:
    if db.get_character(gid(interaction), interaction.user.id) is None:
        await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
        return
    try:
        parsed_effects = parse_skill_effects(efeitos)
        skill = Skill(nome[:50], poder_base, poder_moeda, moedas, descricao[:300], tipo.value, moedas_inquebraveis, parsed_effects)
    except ValueError as error:
        await interaction.response.send_message(f"Efeitos inválidos: {error}", ephemeral=True)
        return
    db.save_skill(interaction.guild_id, interaction.user.id, skill)
    audit(interaction, "SKILL SALVA", f"{skill.name}: Base={poder_base}, Coin={poder_moeda:+d}, Moedas={moedas}, MI={moedas_inquebraveis}")
    await interaction.response.send_message(embed=skills_embed([skill], "Skill salva"))


@skill_group.command(name="oficina", description="Abre o criador visual de skills")
async def skill_oficina(interaction: discord.Interaction) -> None:
    if db.get_character(gid(interaction), interaction.user.id) is None:
        await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=skills_embed(db.list_skills(gid(interaction), interaction.user.id), "〔 SKILL WORKSHOP 〕"),
        view=SkillsView(), ephemeral=True,
    )


async def skill_listar(interaction: discord.Interaction, jogador: discord.Member | None = None) -> None:
    jogador = jogador or interaction.user
    view = SkillsView() if jogador.id == interaction.user.id else None
    await interaction.response.send_message(
        embed=skills_embed(db.list_skills(gid(interaction), jogador.id), f"Skills de {jogador.display_name}"),
        view=view,
    )


async def skill_teste(interaction: discord.Interaction) -> None:
    server = gid(interaction)
    if db.get_character(server, interaction.user.id) is None:
        await interaction.response.send_message(
            "Crie sua ficha primeiro com `/personagem criar`.", ephemeral=True
        )
        return
    skill = Skill(
        "Golpe de Teste",
        base_power=4,
        coin_power=3,
        coins=3,
        description="Skill padrão para testar rolagens, previsões e Clashes.",
        skill_type="attack",
    )
    db.save_skill(server, interaction.user.id, skill)
    audit(interaction, "SKILL TESTE", "Golpe de Teste adicionado")
    await interaction.response.send_message(
        embed=skills_embed([skill], "Skill de teste adicionada"), ephemeral=True
    )


@inimigo_group.command(name="criar", description="Mestre: cria ou atualiza um inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
async def inimigo_criar(
    interaction: discord.Interaction, nome: str,
    offense_level: int = 0, defense_level: int = 0,
    sanidade: app_commands.Range[int, -45, 45] = 0,
    usa_sanidade: bool = True,
) -> None:
    enemy = db.save_enemy(gid(interaction), interaction.user.id, nome[:50], sanidade, offense_level, defense_level, usa_sanidade)
    embed = discord.Embed(title="〔 REGISTRO DE HOSTIL 〕", description=f"## {enemy['name']}", color=ACCENT)
    sanity_text = f"`{enemy['sp']:+d} SP` • `{heads_chance(enemy['sp']):.0%} HEADS`" if enemy["uses_sanity"] else "`INATIVA` • `50% HEADS`"
    embed.add_field(name="◈ SANIDADE", value=sanity_text)
    embed.add_field(name="◆ OFFENSE LEVEL", value=f"`{enemy['offense_level']}`")
    embed.add_field(name="◇ DEFENSE LEVEL", value=f"`{enemy['defense_level']}`")
    embed.set_footer(text="Use /inimigo skill para cadastrar ataques")
    audit(interaction, "INIMIGO SALVO", f"{enemy['name']}; Sanidade={'ativa' if enemy['uses_sanity'] else 'inativa'}; SP={enemy['sp']:+d}; OL={enemy['offense_level']}")
    await interaction.response.send_message(embed=embed)


@inimigo_group.command(name="skill", description="Mestre: cria ou atualiza um ataque do inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(tipo=SKILL_TYPE_CHOICES)
async def inimigo_skill(
    interaction: discord.Interaction, inimigo: str, nome: str, poder_base: int,
    poder_moeda: int, moedas: app_commands.Range[int, 1, 10], tipo: app_commands.Choice[str], descricao: str = "",
    moedas_inquebraveis: app_commands.Range[int, 0, 10] = 0,
    efeitos: str = "",
) -> None:
    enemy = db.get_enemy(gid(interaction), inimigo)
    if enemy is None:
        await interaction.response.send_message("Inimigo não encontrado. Confira `/inimigo listar`.", ephemeral=True)
        return
    try:
        parsed_effects = parse_skill_effects(efeitos)
        skill = Skill(nome[:50], poder_base, poder_moeda, moedas, descricao[:300], tipo.value, moedas_inquebraveis, parsed_effects)
    except ValueError as error:
        await interaction.response.send_message(f"Efeitos inválidos: {error}", ephemeral=True)
        return
    db.save_enemy_skill(enemy["id"], skill)
    audit(interaction, "SKILL DE INIMIGO", f"{enemy['name']} / {skill.name}: Base={poder_base}, Coin={poder_moeda:+d}, Moedas={moedas}, MI={moedas_inquebraveis}")
    await interaction.response.send_message(embed=skills_embed([skill], f"Ataque de {enemy['name']}"))


@inimigo_group.command(name="efeitos", description="Mestre: adiciona efeitos temporários a um inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
async def inimigo_efeitos(
    interaction: discord.Interaction, inimigo: str, paralisia: int = 0,
    base_power: int = 0, coin_power: int = 0, clash_power: int = 0,
    offense_level: int = 0,
) -> None:
    enemy = db.get_enemy(gid(interaction), inimigo)
    if enemy is None:
        await interaction.response.send_message("Inimigo não encontrado.", ephemeral=True)
        return
    enemy = db.add_enemy_effects(enemy["id"], paralisia, base_power, coin_power, clash_power, offense_level)
    effects = []
    if enemy["paralysis"]:
        effects.append(f"{EFFECT_PARALYZE} Paralisia **{enemy['paralysis']}**")
    if enemy["base_power_mod"]:
        effects.append(f"{effect_icon(enemy['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base **{enemy['base_power_mod']:+d}**")
    if enemy["coin_power_mod"]:
        effects.append(f"{effect_icon(enemy['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Plus Coin **{enemy['coin_power_mod']:+d}**")
    if enemy["clash_power_mod"]:
        effects.append(f"{effect_icon(enemy['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash **{enemy['clash_power_mod']:+d}**")
    if enemy["offense_level_mod"]:
        effects.append(f"{effect_icon(enemy['offense_level_mod'], EFFECT_OFFENSE_UP, EFFECT_OFFENSE_DOWN)} Offense **{enemy['offense_level_mod']:+d}**")
    embed = discord.Embed(title="〔 EFEITOS DO HOSTIL 〕", description=f"## {enemy['name']}\n" + ("\n".join(effects) or "Nenhum efeito"), color=ACCENT)
    audit(interaction, "EFEITOS DE INIMIGO", f"{enemy['name']}; P={paralisia}, Base={base_power}, Coin={coin_power}, Clash={clash_power}, OL={offense_level}")
    await interaction.response.send_message(embed=embed)


@inimigo_group.command(name="status", description="Mestre: define Potência e Quantidade de um status do inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(status=[app_commands.Choice(name=STATUS_LABELS[name], value=name) for name in sorted(PUBLIC_STATUS_TYPES)])
async def inimigo_status(
    interaction: discord.Interaction, inimigo: str, status: app_commands.Choice[str],
    potencia: int, quantidade: int,
) -> None:
    enemy = db.get_enemy(gid(interaction), inimigo)
    if enemy is None:
        await interaction.response.send_message("Inimigo não encontrado.", ephemeral=True)
        return
    try:
        saved = db.set_status(gid(interaction), "enemy", enemy["id"], status.value, potencia, quantidade)
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    audit(interaction, "STATUS DE INIMIGO", f"{enemy['name']}; {saved.status_type}; P={saved.potency}; C={saved.count}")
    await interaction.response.send_message(
        f"{STATUS_ICONS[saved.status_type]} **{saved.status_type.title()}** de **{enemy['name']}**: "
        f"Potência **{saved.potency}** • Quantidade **{saved.count}**.", ephemeral=True,
    )


@inimigo_group.command(name="tags", description="Mestre: define tags permanentes de um inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
async def inimigo_tags(interaction: discord.Interaction, inimigo: str, tags: str = "") -> None:
    """Tags separadas por vírgula; vazio remove todas."""
    enemy = db.get_enemy(gid(interaction), inimigo)
    if enemy is None:
        await interaction.response.send_message("Inimigo não encontrado.", ephemeral=True)
        return
    saved = db.set_enemy_tags(gid(interaction), enemy["id"], tags)
    audit(interaction, "TAGS DE INIMIGO", f"{enemy['name']}; tags={saved}")
    rendered = " ".join(f"`{tag}`" for tag in saved) or "`SEM TAGS`"
    await interaction.response.send_message(
        f"🏷️ Tags de **{enemy['name']}** atualizadas: {rendered}", ephemeral=True,
    )


@inimigo_group.command(name="editar_skill", description="Mestre: edita uma skill já existente do inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(tipo=SKILL_TYPE_CHOICES)
async def inimigo_editar_skill(
    interaction: discord.Interaction, inimigo: str, skill_existente: str,
    poder_base: int, poder_moeda: int, moedas: app_commands.Range[int, 1, 10],
    tipo: app_commands.Choice[str], novo_nome: str = "", descricao: str = "",
    moedas_inquebraveis: app_commands.Range[int, 0, 10] = 0,
) -> None:
    enemy = db.get_enemy(gid(interaction), inimigo)
    old = None if enemy is None else db.get_enemy_skill(enemy["id"], skill_existente)
    if enemy is None or old is None:
        await interaction.response.send_message("Inimigo ou skill não encontrada.", ephemeral=True)
        return
    name = novo_nome[:50] if novo_nome.strip() else old.name
    edited = Skill(name, poder_base, poder_moeda, moedas, descricao[:300], tipo.value, moedas_inquebraveis)
    if name.casefold() != old.name.casefold():
        db.delete_enemy_skill(enemy["id"], old.name)
    db.save_enemy_skill(enemy["id"], edited)
    audit(interaction, "SKILL INIMIGA EDITADA", f"{enemy['name']}: {old.name} -> {edited.name}")
    await interaction.response.send_message(embed=skills_embed([edited], f"Skill de {enemy['name']} atualizada"))


@inimigo_group.command(name="remover_skill", description="Mestre: exclui uma skill de um inimigo")
@app_commands.checks.has_permissions(manage_guild=True)
async def inimigo_remover_skill(interaction: discord.Interaction, inimigo: str, skill: str) -> None:
    enemy = db.get_enemy(gid(interaction), inimigo)
    removed = False if enemy is None else db.delete_enemy_skill(enemy["id"], skill)
    audit(interaction, "SKILL INIMIGA EXCLUÍDA", f"{inimigo}: {skill}; removida={removed}")
    await interaction.response.send_message(
        f"{'🗑️ Skill excluída' if removed else 'Inimigo ou skill não encontrada'}: **{skill}**.", ephemeral=True
    )


@inimigo_skill.autocomplete("inimigo")
@inimigo_efeitos.autocomplete("inimigo")
@inimigo_status.autocomplete("inimigo")
@inimigo_tags.autocomplete("inimigo")
@inimigo_editar_skill.autocomplete("inimigo")
@inimigo_remover_skill.autocomplete("inimigo")
async def managed_enemy_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild_id is None:
        return []
    return [app_commands.Choice(name=e["name"], value=e["name"])
            for e in db.list_enemies(interaction.guild_id) if current.lower() in e["name"].lower()][:25]


@inimigo_editar_skill.autocomplete("skill_existente")
async def managed_enemy_edit_skill_autocomplete(interaction: discord.Interaction, current: str):
    enemy_name = getattr(interaction.namespace, "inimigo", None)
    enemy = None if interaction.guild_id is None or not enemy_name else db.get_enemy(interaction.guild_id, enemy_name)
    skills = [] if enemy is None else db.list_enemy_skills(enemy["id"])
    return [app_commands.Choice(name=f"{s.name} • {SKILL_TYPE_LABELS[s.skill_type]}", value=s.name)
            for s in skills if current.lower() in s.name.lower()][:25]


@inimigo_remover_skill.autocomplete("skill")
async def managed_enemy_delete_skill_autocomplete(interaction: discord.Interaction, current: str):
    enemy_name = getattr(interaction.namespace, "inimigo", None)
    enemy = None if interaction.guild_id is None or not enemy_name else db.get_enemy(interaction.guild_id, enemy_name)
    skills = [] if enemy is None else db.list_enemy_skills(enemy["id"])
    return [app_commands.Choice(name=f"{s.name} • {SKILL_TYPE_LABELS[s.skill_type]}", value=s.name)
            for s in skills if current.lower() in s.name.lower()][:25]


@inimigo_group.command(name="listar", description="Lista inimigos e seus ataques")
async def inimigo_listar(interaction: discord.Interaction) -> None:
    enemies = db.list_enemies(gid(interaction))
    embed = discord.Embed(title="〔 ARQUIVO DE HOSTIS 〕", color=ACCENT)
    if not enemies:
        embed.description = "Nenhum inimigo registrado."
    for enemy in enemies[:20]:
        tags = db.get_enemy_tags(enemy["id"])
        embed.add_field(
            name=enemy["name"],
            value=(f"Sanidade `{'%+d SP' % enemy['sp'] if enemy['uses_sanity'] else 'INATIVA'}`"
                   + (f"\nTags: {' '.join(f'`{tag}`' for tag in tags)}" if tags else "")),
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


@inimigo_group.command(name="remover", description="Mestre: remove um inimigo e seus ataques")
@app_commands.checks.has_permissions(manage_guild=True)
async def inimigo_remover(interaction: discord.Interaction, nome: str) -> None:
    removed = db.delete_enemy(gid(interaction), nome)
    audit(interaction, "INIMIGO REMOVIDO", nome if removed else f"não encontrado: {nome}")
    await interaction.response.send_message(
        f"{'🗑️ Inimigo removido' if removed else 'Inimigo não encontrado'}: **{nome}**.", ephemeral=True
    )


async def clash_jogador_impl(interaction: discord.Interaction, oponente: discord.Member, sua_skill: str, skill_oponente: str) -> None:
    server = gid(interaction)
    lc, rc = db.get_character(server, interaction.user.id), db.get_character(server, oponente.id)
    left = db.get_skill(server, interaction.user.id, sua_skill)
    right = db.get_skill(server, oponente.id, skill_oponente)
    if not all((lc, rc, left, right)):
        await interaction.response.send_message("Não encontrei uma ficha ou skill. Confira `/skill listar`.", ephemeral=True)
        return
    left, left_charge_log = prepare_charge_enhancements(
        server, "player", interaction.user.id, "player", oponente.id, left,
    )
    right, right_charge_log = prepare_charge_enhancements(
        server, "player", oponente.id, "player", interaction.user.id, right,
    )
    status_log = left_charge_log + right_charge_log
    initial_effect_log = apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "on_use")
    initial_effect_log += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "on_use")
    lc, rc = db.get_character(server, interaction.user.id), db.get_character(server, oponente.id)
    left_effects = clash_effect_strip(server, "player", interaction.user.id, lc)
    right_effects = clash_effect_strip(server, "player", oponente.id, rc)
    left_level = lc["defense_level"] + lc["defense_level_mod"] if left.uses_defense_level else lc["offense_level"] + lc["offense_level_mod"]
    right_level = rc["defense_level"] + rc["defense_level_mod"] if right.uses_defense_level else rc["offense_level"] + rc["offense_level_mod"]
    lm = Modifiers(lc["base_power_mod"], lc["coin_power_mod"], lc["paralysis"], left_level, lc["clash_power_mod"])
    rm = Modifiers(rc["base_power_mod"], rc["coin_power_mod"], rc["paralysis"], right_level, rc["clash_power_mod"])
    if not left.is_clashable and not right.is_clashable:
        await interaction.response.send_message("As duas defesas comuns se anulam (**Offset**); nenhuma é ativada.")
        return
    if not left.is_clashable:
        await show_defense_resolution(interaction, rc["name"], right, rc["sp"], rm, lc["name"], left, lc["sp"], lm, rc["defense_level"] + rc["defense_level_mod"])
        return
    if not right.is_clashable:
        await show_defense_resolution(interaction, lc["name"], left, lc["sp"], lm, rc["name"], right, rc["sp"], rm, lc["defense_level"] + lc["defense_level_mod"])
        return
    await interaction.response.defer()
    audit(
        interaction, "CLASH INICIADO",
        f"{lc['name']} ({left.name}, {left.coins} moedas) vs {rc['name']} ({right.name}, {right.coins} moedas)",
    )
    forecast = prediction_with_paralysis(left, lc["sp"], right, rc["sp"], lm, rm)
    audit(interaction, "PREVISÃO CALCULADA", f"5 projeções; chance esquerda={forecast.win_chance:.0%}; classe={forecast.label}")
    result = resolve_clash(left, lc["sp"], right, rc["sp"], left_modifiers=lm, right_modifiers=rm)
    status_log += trigger_bleed_action(
        server, "player", interaction.user.id, lc["name"], left,
        clash_rolled_coins(result, "left"),
    )
    status_log += trigger_bleed_action(
        server, "player", oponente.id, rc["name"], right,
        clash_rolled_coins(result, "right"),
    )
    audit(interaction, "CLASH RESOLVIDO", f"vencedor={result.winner}; rodadas={len(result.rounds)}; moedas={result.left_coins}x{result.right_coins}")
    audit_clash_rounds(
        interaction, "REGISTRO DE CLASH", lc["name"], rc["name"], result,
        left, right, lm, rm,
    )
    left_min, left_max = left.range_with()
    right_min, right_max = right.range_with()
    clash_gif = clash_gif_for(left, right)

    def animated_embed(round_index: int = 0, finished: bool = False) -> discord.Embed:
        current = discord.Embed(title="〔 ⚠ CLASH ENGAGED ⚠ 〕", color=GOLD if not finished else ACCENT)
        current.description = f"## {lc['name']}  ⟷  {rc['name']}\n`{left.name.upper()}`  **VS**  `{right.name.upper()}`"
        current.add_field(
            name="◀ PARÂMETROS",
            value=f"{effect_icon(lc['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base `{left.base_power} {lc['base_power_mod']:+d}`\n{effect_icon(lc['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Coin `{left.coin_power} {lc['coin_power_mod']:+d}`\n{effect_icon(lc['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash `{lc['clash_power_mod']:+d}`\nFaixa `{left_min}–{left_max}` • {level_symbol(left)} `{left_level}`\n▰ {left_effects}",
            inline=True,
        )
        current.add_field(
            name="PARÂMETROS ▶",
            value=f"{effect_icon(rc['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base `{right.base_power} {rc['base_power_mod']:+d}`\n{effect_icon(rc['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Coin `{right.coin_power} {rc['coin_power_mod']:+d}`\n{effect_icon(rc['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash `{rc['clash_power_mod']:+d}`\nFaixa `{right_min}–{right_max}` • {level_symbol(right)} `{right_level}`\n▰ {right_effects}",
            inline=True,
        )
        if clash_gif:
            current.set_image(url=clash_gif)
        left_coins, right_coins = left.coins, right.coins
        left_unbreakable = right_unbreakable = 0
        history = []
        for rd in result.rounds[:round_index]:
            if rd.result == "left":
                right_coins -= 1
            elif rd.result == "right":
                left_coins -= 1
            left_unbreakable += int(rd.left_unbreakable_broken)
            right_unbreakable += int(rd.right_unbreakable_broken)
            arrow = {"left": "⬅️", "right": "➡️", "tie": "🔁"}[rd.result]
            left_mi = f" {COIN_UNBREAKABLE}" if rd.left_unbreakable_broken else ""
            right_mi = f" {COIN_UNBREAKABLE}" if rd.right_unbreakable_broken else ""
            history.append(f"`R{rd.number:02}` {compact_roll(rd.left)} **{rd.left.power}**{left_mi} {arrow} {right_mi}**{rd.right.power}** {compact_roll(rd.right)}")
        left_bar = coin_bar(left_coins, left.coins, left_unbreakable)
        right_bar = coin_bar(right_coins, right.coins, right_unbreakable)
        current.add_field(
            name=f"MOEDAS // RODADA {round_index:02}",
            value=f"**{lc['name']}**  {left_bar}\n**{rc['name']}**  {right_bar}",
            inline=False,
        )
        if history:
            add_history_fields(current, history)
        if finished:
            winner = lc["name"] if result.winner == "left" else rc["name"]
            remaining = result.left_coins if result.winner == "left" else result.right_coins
            broken_mi = result.left_broken_unbreakable if result.winner == "left" else result.right_broken_unbreakable
            mi_text = f" + **{broken_mi}** {COIN_UNBREAKABLE}" if broken_mi else ""
            current.add_field(name="〔 RESULTADO CONFIRMADO 〕", value=f"🏆 **{winner}** venceu com **{remaining}** moeda(s) ativa(s){mi_text}.\nSanidade: vencedor **+5** • perdedor **−5**", inline=False)
        else:
            current.set_footer(text="PROCESSANDO PROBABILIDADES E QUEBRA DE MOEDAS…")
        return current

    await resilient_clash_edit(
        interaction,
        embed=prediction_embed(lc["name"], left, rc["name"], right, forecast, clash_gif),
        required=False,
    )
    await asyncio.sleep(2.5)
    animation_available = await resilient_clash_edit(
        interaction, embed=animated_embed(), required=False,
    )
    await asyncio.sleep(1.0)
    animation_rounds = min(len(result.rounds), 10)
    if animation_available:
        for index in range(1, animation_rounds + 1):
            if not await resilient_clash_edit(
                interaction, embed=animated_embed(index), required=False,
            ):
                break
            await asyncio.sleep(0.85)

    db.consume_clash_effects(server, interaction.user.id, result.left_paralysis)
    db.consume_clash_effects(server, oponente.id, result.right_paralysis)
    winner_id, loser_id = ((interaction.user.id, oponente.id) if result.winner == "left" else (oponente.id, interaction.user.id))
    db.change_sp(server, winner_id, 5)
    db.change_sp(server, loser_id, -5)
    if result.winner == "left":
        effect_log = apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "clash_win", remaining_coins=result.left_coins)
        effect_log += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "clash_lose", remaining_coins=result.right_coins)
    else:
        effect_log = apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "clash_win", remaining_coins=result.right_coins)
        effect_log += apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "clash_lose", remaining_coins=result.left_coins)
    effect_log = initial_effect_log + effect_log
    if effect_log:
        audit(interaction, "EFEITOS DE SKILL", "; ".join(effect_log))
    winner = lc["name"] if result.winner == "left" else rc["name"]
    audit(
        interaction,
        "CLASH FINALIZADO",
        f"{lc['name']} ({left.name}) vs {rc['name']} ({right.name}); vencedor={winner}; rodadas={len(result.rounds)}",
    )
    final_embed = animated_embed(len(result.rounds), finished=True)
    if not await resilient_clash_edit(interaction, embed=final_embed, required=True):
        try:
            await discord_request_with_retry(
                lambda: interaction.followup.send(embed=final_embed),
                label="publicar resultado final alternativo do Clash",
            )
        except Exception as error:
            if not is_transient_discord_error(error):
                raise
            audit_logger.error(
                "[CLASH / REDE] resultado calculado, mas o Discord continuou indisponivel | %s",
                error,
            )
    winning_skill = left if result.winner == "left" else right
    stagger_value, guard_shield = clashable_guard_values(result, left, right)
    if stagger_value:
        guard_winner = lc["name"] if result.winner == "left" else rc["name"]
        guard_target = rc["name"] if result.winner == "left" else lc["name"]
        await interaction.followup.send(
            embed=clashable_guard_win_embed(guard_winner, guard_target, stagger_value),
        )
    if winning_skill.deals_damage:
        if result.winner == "left":
            status_log += trigger_bleed_action(
                server, "player", interaction.user.id, lc["name"], left, result.left_coins,
            )
            effect_log += apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "before_attack", remaining_coins=result.left_coins)
            lc = db.get_character(server, interaction.user.id)
        else:
            status_log += trigger_bleed_action(
                server, "player", oponente.id, rc["name"], right, result.right_coins,
            )
            effect_log += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "before_attack", remaining_coins=result.right_coins)
            rc = db.get_character(server, oponente.id)
        await asyncio.sleep(1.25)
        if result.winner == "left":
            damage = resolve_damage(
                left, lc["sp"], result.left_coins,
                lc["offense_level"] + lc["offense_level_mod"], rc["defense_level"] + rc["defense_level_mod"],
                modifiers=Modifiers(lc["base_power_mod"], lc["coin_power_mod"], result.left_paralysis),
                broken_unbreakable=result.left_broken_unbreakable,
            )
            attacker_name, target_name = lc["name"], rc["name"]
            status_log += apply_skill_damage_percent(
                server, "player", interaction.user.id, "player", oponente.id,
                left, damage, clash_won=True,
            )
            status_log += apply_poise_critical(server, "player", interaction.user.id, damage)
        else:
            damage = resolve_damage(
                right, rc["sp"], result.right_coins,
                rc["offense_level"] + rc["offense_level_mod"], lc["defense_level"] + lc["defense_level_mod"],
                modifiers=Modifiers(rc["base_power_mod"], rc["coin_power_mod"], result.right_paralysis),
                broken_unbreakable=result.right_broken_unbreakable,
            )
            attacker_name, target_name = rc["name"], lc["name"]
            status_log += apply_skill_damage_percent(
                server, "player", oponente.id, "player", interaction.user.id,
                right, damage, clash_won=True,
            )
            status_log += apply_poise_critical(server, "player", oponente.id, damage)
        if result.winner == "left":
            revert_temporary_self_trigger(server, "player", interaction.user.id, left, "before_attack", remaining_coins=result.left_coins)
        else:
            revert_temporary_self_trigger(server, "player", oponente.id, right, "before_attack", remaining_coins=result.right_coins)
        adjusted_damage = max(0, damage.final_damage - guard_shield)
        audit(interaction, "DANO FINAL", f"{attacker_name} -> {target_name}; dano={damage.final_damage}; escudo_clashable={guard_shield}; final={adjusted_damage}")
        audit_damage_calculation(
            interaction, attacker_name, target_name, winning_skill, damage, shield=guard_shield,
        )
        final_embed = damage_embed(
            attacker_name, target_name, winning_skill, damage, shield=guard_shield,
        )
        if result.winner == "left":
            damage_effects, hit_statuses = resolve_hit_status_sequence(
                server, "player", interaction.user.id, "player", oponente.id,
                rc["sp"], left, damage.hits,
            )
            status_log += hit_statuses
            damage_effects += apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "after_attack", remaining_coins=result.left_coins)
        else:
            damage_effects, hit_statuses = resolve_hit_status_sequence(
                server, "player", oponente.id, "player", interaction.user.id,
                lc["sp"], right, damage.hits,
            )
            status_log += hit_statuses
            damage_effects += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "after_attack", remaining_coins=result.right_coins)
        if damage_effects:
            audit(interaction, "EFEITOS DE ACERTO", "; ".join(damage_effects))
        all_effects = effect_log + damage_effects + status_log
        add_trigger_log(final_embed, all_effects)
        add_status_impact(final_embed, all_effects)
        final_gif = await attach_damage_gif(final_embed)
        await interaction.followup.send(embed=final_embed, files=[final_gif] if final_gif else [])
    losing_skill = right if result.winner == "left" else left
    cracked = result.right_broken_unbreakable if result.winner == "left" else result.left_broken_unbreakable
    if winning_skill.deals_damage and losing_skill.deals_damage and cracked > 0:
        await asyncio.sleep(1.25)
        if result.winner == "left":
            follow_status_log = trigger_bleed_action(
                server, "player", oponente.id, rc["name"], right, cracked,
            )
            follow_skill, follow_damage = resolve_unbreakable_followup(
                right, rc["sp"], cracked,
                rc["offense_level"] + rc["offense_level_mod"], lc["defense_level"] + lc["defense_level_mod"],
                Modifiers(rc["base_power_mod"], rc["coin_power_mod"], result.right_paralysis),
            )
            follow_attacker, follow_target = rc["name"], lc["name"]
        else:
            follow_status_log = trigger_bleed_action(
                server, "player", interaction.user.id, lc["name"], left, cracked,
            )
            follow_skill, follow_damage = resolve_unbreakable_followup(
                left, lc["sp"], cracked,
                lc["offense_level"] + lc["offense_level_mod"], rc["defense_level"] + rc["defense_level_mod"],
                Modifiers(lc["base_power_mod"], lc["coin_power_mod"], result.left_paralysis),
            )
            follow_attacker, follow_target = lc["name"], rc["name"]
        audit(interaction, "ATAQUE INQUEBRÁVEL", f"{follow_attacker} -> {follow_target}; moedas={cracked}; dano={follow_damage.final_damage}")
        follow_embed = damage_embed(
            follow_attacker, follow_target, follow_skill, follow_damage,
            unbreakable_followup=True,
        )
        add_trigger_log(follow_embed, follow_status_log)
        add_status_impact(follow_embed, follow_status_log)
        follow_gif = await attach_damage_gif(follow_embed, unbreakable_followup=True)
        await interaction.followup.send(embed=follow_embed, files=[follow_gif] if follow_gif else [])


async def clash_inimigo_impl(
    interaction: discord.Interaction, inimigo: str, sua_skill: str, skill_inimiga: str,
) -> None:
    server = gid(interaction)
    player = db.get_character(server, interaction.user.id)
    enemy = db.get_enemy(server, inimigo)
    player_effects = clash_effect_strip(server, "player", interaction.user.id, player)
    enemy_effects = clash_effect_strip(server, "enemy", enemy["id"], enemy)
    left = db.get_skill(server, interaction.user.id, sua_skill)
    right = None if enemy is None else db.get_enemy_skill(enemy["id"], skill_inimiga)
    if not all((player, enemy, left, right)):
        await interaction.response.send_message(
            "Não encontrei a ficha, o inimigo ou uma das skills. Use `/skill listar` e `/inimigo listar`.",
            ephemeral=True,
        )
        return
    left, left_charge_log = prepare_charge_enhancements(
        server, "player", interaction.user.id, "enemy", enemy["id"], left,
    )
    right, right_charge_log = prepare_charge_enhancements(
        server, "enemy", enemy["id"], "player", interaction.user.id, right,
    )
    status_log = left_charge_log + right_charge_log
    initial_effect_log = apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "on_use")
    initial_effect_log += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "on_use")
    player = db.get_character(server, interaction.user.id)
    enemy = db.get_enemy(server, inimigo)
    left_level = player["defense_level"] + player["defense_level_mod"] if left.uses_defense_level else player["offense_level"] + player["offense_level_mod"]
    right_level = enemy["defense_level"] if right.uses_defense_level else enemy["offense_level"] + enemy["offense_level_mod"]
    lm = Modifiers(
        player["base_power_mod"], player["coin_power_mod"],
        player["paralysis"], left_level, player["clash_power_mod"],
    )
    rm = Modifiers(
        enemy["base_power_mod"], enemy["coin_power_mod"], enemy["paralysis"],
        right_level, enemy["clash_power_mod"],
    )
    enemy_sp = enemy["sp"] if enemy["uses_sanity"] else 0
    if not left.is_clashable and not right.is_clashable:
        await interaction.response.send_message("As duas defesas comuns se anulam (**Offset**); nenhuma é ativada.")
        return
    if not left.is_clashable:
        await show_defense_resolution(interaction, enemy["name"], right, enemy_sp, rm, player["name"], left, player["sp"], lm, enemy["defense_level"])
        return
    if not right.is_clashable:
        await show_defense_resolution(interaction, player["name"], left, player["sp"], lm, enemy["name"], right, enemy_sp, rm, player["defense_level"] + player["defense_level_mod"])
        return
    await interaction.response.defer()
    audit(
        interaction, "CLASH INIMIGO INICIADO",
        f"{player['name']} ({left.name}, {left.coins} moedas) vs {enemy['name']} ({right.name}, {right.coins} moedas)",
    )
    forecast = prediction_with_paralysis(left, player["sp"], right, enemy_sp, lm, rm)
    audit(interaction, "PREVISÃO CALCULADA", f"5 projeções; chance jogador={forecast.win_chance:.0%}; classe={forecast.label}")
    result = resolve_clash(
        left, player["sp"], right, enemy_sp, left_modifiers=lm, right_modifiers=rm
    )
    status_log += trigger_bleed_action(
        server, "player", interaction.user.id, player["name"], left,
        clash_rolled_coins(result, "left"),
    )
    status_log += trigger_bleed_action(
        server, "enemy", enemy["id"], enemy["name"], right,
        clash_rolled_coins(result, "right"),
    )
    audit(interaction, "CLASH INIMIGO RESOLVIDO", f"vencedor={result.winner}; rodadas={len(result.rounds)}; moedas={result.left_coins}x{result.right_coins}")
    audit_clash_rounds(
        interaction, "REGISTRO DE CLASH HOSTIL", player["name"], enemy["name"], result,
        left, right, lm, rm,
    )
    gif = clash_gif_for(left, right)
    left_min, left_max = left.range_with()
    right_min, right_max = right.range_with()

    def enemy_embed(round_index: int, finished: bool = False) -> discord.Embed:
        embed = discord.Embed(title="〔 ⚠ HOSTILE CLASH ⚠ 〕", color=ACCENT if finished else GOLD)
        embed.description = f"## {player['name']}  ⟷  {enemy['name']}\n`{left.name.upper()}` **VS** `{right.name.upper()}`"
        embed.add_field(
            name="◀ PARÂMETROS",
            value=f"{effect_icon(player['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base `{left.base_power} {player['base_power_mod']:+d}`\n{effect_icon(player['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Coin `{left.coin_power} {player['coin_power_mod']:+d}`\n{effect_icon(player['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash `{player['clash_power_mod']:+d}`\nFaixa `{left_min}–{left_max}` • {level_symbol(left)} `{left_level}`\n▰ {player_effects}",
            inline=True,
        )
        embed.add_field(
            name="PARÂMETROS ▶",
            value=f"{effect_icon(enemy['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base `{right.base_power} {enemy['base_power_mod']:+d}`\n{effect_icon(enemy['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Coin `{right.coin_power} {enemy['coin_power_mod']:+d}`\n{effect_icon(enemy['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash `{enemy['clash_power_mod']:+d}`\nFaixa `{right_min}–{right_max}` • {level_symbol(right)} `{right_level}`\n▰ {enemy_effects}",
            inline=True,
        )
        left_coins, right_coins = left.coins, right.coins
        left_unbreakable = right_unbreakable = 0
        history = []
        for rd in result.rounds[:round_index]:
            if rd.result == "left":
                right_coins -= 1
            elif rd.result == "right":
                left_coins -= 1
            left_unbreakable += int(rd.left_unbreakable_broken)
            right_unbreakable += int(rd.right_unbreakable_broken)
            arrow = {"left": "⬅️", "right": "➡️", "tie": "🔁"}[rd.result]
            left_mi = f" {COIN_UNBREAKABLE}" if rd.left_unbreakable_broken else ""
            right_mi = f" {COIN_UNBREAKABLE}" if rd.right_unbreakable_broken else ""
            history.append(f"`R{rd.number:02}` {compact_roll(rd.left)} **{rd.left.power}**{left_mi} {arrow} {right_mi}**{rd.right.power}** {compact_roll(rd.right)}")
        embed.add_field(
            name=f"MOEDAS // RODADA {round_index:02}",
            value=(f"**{player['name']}**  {coin_bar(left_coins, left.coins, left_unbreakable)}\n"
                   f"**{enemy['name']}**  {coin_bar(right_coins, right.coins, right_unbreakable)}"),
            inline=False,
        )
        if history:
            add_history_fields(embed, history)
        if finished:
            winner = player["name"] if result.winner == "left" else enemy["name"]
            remaining = result.left_coins if result.winner == "left" else result.right_coins
            broken_mi = result.left_broken_unbreakable if result.winner == "left" else result.right_broken_unbreakable
            mi_text = f" + **{broken_mi}** {COIN_UNBREAKABLE}" if broken_mi else ""
            player_sp_change = "+5" if result.winner == "left" else "−5"
            if enemy["uses_sanity"]:
                enemy_sp_change = "−5" if result.winner == "left" else "+5"
            else:
                enemy_sp_change = "INATIVA"
            embed.add_field(
                name="〔 RESULTADO CONFIRMADO 〕",
                value=(
                    f"🏆 **{winner}** venceu com **{remaining}** moeda(s) ativa(s){mi_text}.\n"
                    f"◈ **SANIDADE** • {player['name']} `{player_sp_change} SP` • "
                    f"{enemy['name']} `{enemy_sp_change}`"
                ),
                inline=False,
            )
        if gif:
            embed.set_image(url=gif)
        return embed

    await resilient_clash_edit(
        interaction,
        embed=prediction_embed(player["name"], left, enemy["name"], right, forecast, gif),
        required=False,
    )
    await asyncio.sleep(2.5)
    animation_available = await resilient_clash_edit(
        interaction, embed=enemy_embed(0), required=False,
    )
    await asyncio.sleep(1.0)
    if animation_available:
        for index in range(1, min(len(result.rounds), 10) + 1):
            if not await resilient_clash_edit(
                interaction, embed=enemy_embed(index), required=False,
            ):
                break
            await asyncio.sleep(0.85)

    db.consume_clash_effects(server, interaction.user.id, result.left_paralysis)
    db.consume_enemy_effects(enemy["id"], result.right_paralysis)
    if result.winner == "left":
        db.change_sp(server, interaction.user.id, 5)
        if enemy["uses_sanity"]:
            db.change_enemy_sp(enemy["id"], -5)
    else:
        db.change_sp(server, interaction.user.id, -5)
        if enemy["uses_sanity"]:
            db.change_enemy_sp(enemy["id"], 5)
    if result.winner == "left":
        effect_log = apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "clash_win", remaining_coins=result.left_coins)
        effect_log += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "clash_lose", remaining_coins=result.right_coins)
    else:
        effect_log = apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "clash_win", remaining_coins=result.right_coins)
        effect_log += apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "clash_lose", remaining_coins=result.left_coins)
    effect_log = initial_effect_log + effect_log
    if effect_log:
        audit(interaction, "EFEITOS DE SKILL", "; ".join(effect_log))
    winner = player["name"] if result.winner == "left" else enemy["name"]
    audit(interaction, "CLASH VS INIMIGO", f"{player['name']} vs {enemy['name']}; vencedor={winner}; rodadas={len(result.rounds)}")
    final_embed = enemy_embed(len(result.rounds), finished=True)
    if not await resilient_clash_edit(interaction, embed=final_embed, required=True):
        try:
            await discord_request_with_retry(
                lambda: interaction.followup.send(embed=final_embed),
                label="publicar resultado final alternativo contra inimigo",
            )
        except Exception as error:
            if not is_transient_discord_error(error):
                raise
            audit_logger.error(
                "[CLASH / REDE] resultado hostil calculado, mas o Discord continuou indisponivel | %s",
                error,
            )
    winning_skill = left if result.winner == "left" else right
    stagger_value, guard_shield = clashable_guard_values(result, left, right)
    if stagger_value:
        guard_winner = player["name"] if result.winner == "left" else enemy["name"]
        guard_target = enemy["name"] if result.winner == "left" else player["name"]
        await interaction.followup.send(
            embed=clashable_guard_win_embed(guard_winner, guard_target, stagger_value),
        )
    if winning_skill.deals_damage:
        if result.winner == "left":
            status_log += trigger_bleed_action(
                server, "player", interaction.user.id, player["name"], left, result.left_coins,
            )
            effect_log += apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "before_attack", remaining_coins=result.left_coins)
            player = db.get_character(server, interaction.user.id)
        else:
            status_log += trigger_bleed_action(
                server, "enemy", enemy["id"], enemy["name"], right, result.right_coins,
            )
            effect_log += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "before_attack", remaining_coins=result.right_coins)
            enemy = db.get_enemy(server, inimigo)
        await asyncio.sleep(1.25)
        if result.winner == "left":
            damage = resolve_damage(
                left, player["sp"], result.left_coins,
                player["offense_level"] + player["offense_level_mod"], enemy["defense_level"],
                modifiers=Modifiers(player["base_power_mod"], player["coin_power_mod"], result.left_paralysis),
                broken_unbreakable=result.left_broken_unbreakable,
            )
            attacker_name, target_name = player["name"], enemy["name"]
            status_log += apply_skill_damage_percent(
                server, "player", interaction.user.id, "enemy", enemy["id"],
                left, damage, clash_won=True,
            )
            status_log += apply_poise_critical(server, "player", interaction.user.id, damage)
        else:
            damage = resolve_damage(
                right, enemy_sp, result.right_coins,
                enemy["offense_level"] + enemy["offense_level_mod"], player["defense_level"] + player["defense_level_mod"],
                modifiers=Modifiers(enemy["base_power_mod"], enemy["coin_power_mod"], result.right_paralysis),
                broken_unbreakable=result.right_broken_unbreakable,
            )
            attacker_name, target_name = enemy["name"], player["name"]
            status_log += apply_skill_damage_percent(
                server, "enemy", enemy["id"], "player", interaction.user.id,
                right, damage, clash_won=True,
            )
            status_log += apply_poise_critical(server, "enemy", enemy["id"], damage)
        if result.winner == "left":
            revert_temporary_self_trigger(server, "player", interaction.user.id, left, "before_attack", remaining_coins=result.left_coins)
        else:
            revert_temporary_self_trigger(server, "enemy", enemy["id"], right, "before_attack", remaining_coins=result.right_coins)
        adjusted_damage = max(0, damage.final_damage - guard_shield)
        audit(interaction, "DANO FINAL", f"{attacker_name} -> {target_name}; dano={damage.final_damage}; escudo_clashable={guard_shield}; final={adjusted_damage}")
        audit_damage_calculation(
            interaction, attacker_name, target_name, winning_skill, damage, shield=guard_shield,
        )
        final_embed = damage_embed(
            attacker_name, target_name, winning_skill, damage, shield=guard_shield,
        )
        if result.winner == "left":
            damage_effects, hit_statuses = resolve_hit_status_sequence(
                server, "player", interaction.user.id, "enemy", enemy["id"],
                enemy["sp"] if enemy["uses_sanity"] else None, left, damage.hits,
            )
            status_log += hit_statuses
            damage_effects += apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "after_attack", remaining_coins=result.left_coins)
        else:
            damage_effects, hit_statuses = resolve_hit_status_sequence(
                server, "enemy", enemy["id"], "player", interaction.user.id,
                player["sp"], right, damage.hits,
            )
            status_log += hit_statuses
            damage_effects += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "after_attack", remaining_coins=result.right_coins)
        if damage_effects:
            audit(interaction, "EFEITOS DE ACERTO", "; ".join(damage_effects))
        all_effects = effect_log + damage_effects + status_log
        add_trigger_log(final_embed, all_effects)
        add_status_impact(final_embed, all_effects)
        final_gif = await attach_damage_gif(final_embed)
        await interaction.followup.send(embed=final_embed, files=[final_gif] if final_gif else [])
    losing_skill = right if result.winner == "left" else left
    cracked = result.right_broken_unbreakable if result.winner == "left" else result.left_broken_unbreakable
    if winning_skill.deals_damage and losing_skill.deals_damage and cracked > 0:
        await asyncio.sleep(1.25)
        if result.winner == "left":
            follow_status_log = trigger_bleed_action(
                server, "enemy", enemy["id"], enemy["name"], right, cracked,
            )
            follow_skill, follow_damage = resolve_unbreakable_followup(
                right, enemy_sp, cracked,
                enemy["offense_level"] + enemy["offense_level_mod"], player["defense_level"] + player["defense_level_mod"],
                Modifiers(enemy["base_power_mod"], enemy["coin_power_mod"], result.right_paralysis),
            )
            follow_attacker, follow_target = enemy["name"], player["name"]
        else:
            follow_status_log = trigger_bleed_action(
                server, "player", interaction.user.id, player["name"], left, cracked,
            )
            follow_skill, follow_damage = resolve_unbreakable_followup(
                left, player["sp"], cracked,
                player["offense_level"] + player["offense_level_mod"], enemy["defense_level"],
                Modifiers(player["base_power_mod"], player["coin_power_mod"], result.left_paralysis),
            )
            follow_attacker, follow_target = player["name"], enemy["name"]
        audit(interaction, "ATAQUE INQUEBRÁVEL", f"{follow_attacker} -> {follow_target}; moedas={cracked}; dano={follow_damage.final_damage}")
        follow_embed = damage_embed(
            follow_attacker, follow_target, follow_skill, follow_damage,
            unbreakable_followup=True,
        )
        add_trigger_log(follow_embed, follow_status_log)
        add_status_impact(follow_embed, follow_status_log)
        follow_gif = await attach_damage_gif(follow_embed, unbreakable_followup=True)
        await interaction.followup.send(embed=follow_embed, files=[follow_gif] if follow_gif else [])


class PvPDefenderSkillSelect(discord.ui.Select):
    def __init__(
        self, challenger_id: int, target_id: int, challenger_skill: str, skills: list[Skill],
    ) -> None:
        self.challenger_id = challenger_id
        self.target_id = target_id
        self.challenger_skill = challenger_skill
        super().__init__(
            placeholder="Escolha sua skill para responder ao desafio",
            options=[discord.SelectOption(
                label=skill.name[:100], value=skill.name,
                description=f"{SKILL_TYPE_LABELS[skill.skill_type]} • {skill.range_with()[0]}–{skill.range_with()[1]}"[:100],
            ) for skill in skills[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("Somente o jogador desafiado pode escolher esta skill.", ephemeral=True)
            return
        challenger = interaction.guild.get_member(self.challenger_id) if interaction.guild else None
        if challenger is None and interaction.guild is not None:
            try:
                challenger = await interaction.guild.fetch_member(self.challenger_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                challenger = None
        if challenger is None:
            await interaction.response.send_message("O desafiante não está mais disponível.", ephemeral=True)
            return
        audit(
            interaction, "DESAFIO PVP ACEITO",
            f"desafiante={challenger}; skill={self.challenger_skill}; resposta={self.values[0]}",
        )
        await clash_jogador_impl(interaction, challenger, self.values[0], self.challenger_skill)


class PvPDefenderSkillView(LoggedView):
    def __init__(
        self, challenger_id: int, target_id: int, challenger_skill: str, skills: list[Skill],
    ) -> None:
        super().__init__(timeout=300)
        self.add_item(PvPDefenderSkillSelect(challenger_id, target_id, challenger_skill, skills))


class PvPChallengeView(LoggedView):
    def __init__(self, challenger_id: int, target_id: int, challenger_skill: str) -> None:
        super().__init__(timeout=300)
        self.challenger_id = challenger_id
        self.target_id = target_id
        self.challenger_skill = challenger_skill

    @discord.ui.button(label="Aceitar Clash", emoji="⚔️", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("Somente o jogador desafiado pode aceitar.", ephemeral=True)
            return
        skills = db.list_skills(gid(interaction), self.target_id)
        if not skills:
            await interaction.response.send_message("Você não possui uma skill para responder.", ephemeral=True)
            return
        challenger_skill = db.get_skill(gid(interaction), self.challenger_id, self.challenger_skill)
        if challenger_skill is None:
            await interaction.response.send_message("A skill do desafiante não está mais disponível.", ephemeral=True)
            return
        embed = discord.Embed(
            title="〔 CLASH REQUEST ACCEPTED 〕",
            description=(
                f"## <@{self.challenger_id}>  ⟷  <@{self.target_id}>\n"
                f"O desafiante declarou `{self.challenger_skill.upper()}`.\n\n"
                "Escolha sua resposta para iniciar o Clash."
            ),
            color=GOLD,
        )
        await interaction.response.edit_message(
            embed=embed,
            view=PvPDefenderSkillView(
                self.challenger_id, self.target_id, self.challenger_skill, skills,
            ),
        )

    @discord.ui.button(label="Recusar", emoji="✖️", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("Somente o jogador desafiado pode recusar.", ephemeral=True)
            return
        audit(interaction, "DESAFIO PVP RECUSADO", f"desafiante={self.challenger_id}")
        embed = discord.Embed(
            title="〔 CLASH REQUEST DECLINED 〕",
            description=f"<@{self.target_id}> recusou o desafio de <@{self.challenger_id}>.",
            color=discord.Color.dark_grey(),
        )
        await interaction.response.edit_message(embed=embed, view=None)


@bot.tree.command(name="clash", description="Inicia um Clash contra qualquer jogador ou inimigo")
@app_commands.describe(
    alvo="Jogador ou inimigo que será enfrentado",
    sua_skill="Sua skill para o Clash",
    skill_alvo="Obrigatória apenas contra inimigos; jogadores escolhem ao aceitar",
)
async def clash_unificado(
    interaction: discord.Interaction, alvo: str, sua_skill: str, skill_alvo: str = "",
) -> None:
    if alvo.startswith("player:"):
        try:
            user_id = int(alvo.split(":", 1)[1])
        except ValueError:
            await interaction.response.send_message("Alvo de jogador inválido.", ephemeral=True)
            return
        opponent = interaction.guild.get_member(user_id) if interaction.guild else None
        if opponent is None and interaction.guild is not None:
            try:
                opponent = await interaction.guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                opponent = None
        if opponent is None:
            await interaction.response.send_message("Esse jogador não está disponível no servidor.", ephemeral=True)
            return
        challenger_skill = db.get_skill(gid(interaction), interaction.user.id, sua_skill)
        if challenger_skill is None:
            await interaction.response.send_message("Escolha uma skill disponível.", ephemeral=True)
            return
        if db.get_character(gid(interaction), opponent.id) is None:
            await interaction.response.send_message("Esse jogador não possui uma ficha.", ephemeral=True)
            return
        embed = discord.Embed(
            title="〔 ⚔ CLASH REQUEST ⚔ 〕",
            description=(
                f"## <@{interaction.user.id}>  ➜  <@{opponent.id}>\n"
                f"`{challenger_skill.name.upper()}`\n\n"
                f"<@{opponent.id}>, você aceita este Clash?"
            ),
            color=ACCENT,
        )
        low, high = challenger_skill.range_with()
        embed.add_field(
            name="◆ SKILL DECLARADA",
            value=(
                f"**{SKILL_TYPE_LABELS[challenger_skill.skill_type]}**\n"
                f"Base `{challenger_skill.base_power}` • Coin `{challenger_skill.coin_power:+}` • "
                f"Moedas `{challenger_skill.coins}` • Faixa `{low}–{high}`"
            ),
            inline=False,
        )
        embed.set_footer(text="O pedido expira quando os botões deixarem de responder")
        audit(interaction, "DESAFIO PVP ENVIADO", f"alvo={opponent}; skill={challenger_skill.name}")
        output_channel = await clash_output_channel(interaction)
        if output_channel is None:
            await interaction.response.send_message(
                "Não consegui acessar o canal configurado para Clashes. Confira minhas permissões.",
                ephemeral=True,
            )
            return
        challenge_view = PvPChallengeView(interaction.user.id, opponent.id, challenger_skill.name)
        if output_channel.id == interaction.channel_id:
            await interaction.response.send_message(embed=embed, view=challenge_view)
        else:
            await interaction.response.send_message(
                f"⚔️ Pedido de Clash enviado para {output_channel.mention}.", ephemeral=True,
            )
            await output_channel.send(embed=embed, view=challenge_view)
        return
    if alvo.startswith("enemy:"):
        if not skill_alvo:
            await interaction.response.send_message(
                "Escolha a skill do inimigo no campo `skill_alvo`.", ephemeral=True,
            )
            return
        clash_interaction = await routed_clash_interaction(interaction)
        if clash_interaction is None:
            await interaction.response.send_message(
                "Não consegui acessar o canal configurado para Clashes. Confira minhas permissões.",
                ephemeral=True,
            )
            return
        await clash_inimigo_impl(clash_interaction, alvo.split(":", 1)[1], sua_skill, skill_alvo)
        return
    await interaction.response.send_message("Escolha um alvo oferecido pela lista do comando.", ephemeral=True)


@clash_unificado.autocomplete("alvo")
async def clash_target_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild_id is None:
        return []
    query = current.casefold()
    choices = []
    for character in db.list_characters(interaction.guild_id):
        if character["user_id"] == interaction.user.id:
            continue
        member = interaction.guild.get_member(character["user_id"]) if interaction.guild else None
        discord_name = member.display_name if member is not None else f"ID {character['user_id']}"
        label = f"👤 {character['name']} • {discord_name}"
        if query in label.casefold():
            choices.append(app_commands.Choice(name=label[:100], value=f"player:{character['user_id']}"))
    for enemy in db.list_enemies(interaction.guild_id):
        label = f"👹 {enemy['name']} • Inimigo"
        if query in label.casefold():
            choices.append(app_commands.Choice(name=label[:100], value=f"enemy:{enemy['name']}"))
    return choices[:25]


@clash_unificado.autocomplete("sua_skill")
async def unified_player_skill_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild_id is None:
        return []
    skills = db.list_skills(interaction.guild_id, interaction.user.id)
    return [app_commands.Choice(name=f"{s.name} • {SKILL_TYPE_LABELS[s.skill_type]}"[:100], value=s.name)
            for s in skills if current.casefold() in s.name.casefold()][:25]


@clash_unificado.autocomplete("skill_alvo")
async def unified_target_skill_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild_id is None:
        return []
    target = getattr(interaction.namespace, "alvo", "") or ""
    if target.startswith("player:"):
        try:
            skills = db.list_skills(interaction.guild_id, int(target.split(":", 1)[1]))
        except ValueError:
            skills = []
    elif target.startswith("enemy:"):
        enemy = db.get_enemy(interaction.guild_id, target.split(":", 1)[1])
        skills = [] if enemy is None else db.list_enemy_skills(enemy["id"])
    else:
        skills = []
    return [app_commands.Choice(name=f"{s.name} • {SKILL_TYPE_LABELS[s.skill_type]}"[:100], value=s.name)
            for s in skills if current.casefold() in s.name.casefold()][:25]


@bot.tree.error
async def tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    original = getattr(error, "original", error)
    command_name = interaction.command.qualified_name if interaction.command else "desconhecido"
    code = error_code()
    started = INTERACTION_STARTED.pop(interaction.id, None)
    elapsed = f"{(time.monotonic() - started) * 1000:.0f}ms" if started is not None else "desconhecida"
    audit_logger.error(
        "[ERRO DE COMANDO %s] interação=%s | comando=/%s | duração=%s | servidor=%s | "
        "canal=%s | usuário=%s (%s) | dados=%s | resposta_iniciada=%s | tipo=%s | detalhe=%s\n%s",
        code, interaction.id, command_name, elapsed, interaction.guild_id, interaction.channel_id,
        interaction.user, interaction.user.id, safe_interaction_data(interaction),
        interaction.response.is_done(), type(original).__name__, original,
        "".join(traceback.format_exception(type(original), original, original.__traceback__)),
    )
    if isinstance(original, discord.NotFound) and original.code == 10062:
        audit_logger.error(
            "[INTERAÇÃO EXPIRADA %s] nenhuma nova resposta será tentada; verifique instâncias duplicadas",
            code,
        )
        return
    message = "O comando falhou. Confira os valores informados."
    if isinstance(error, app_commands.MissingPermissions):
        message = "Apenas alguém com permissão de gerenciar o servidor pode fazer isso."
    elif isinstance(error, app_commands.CheckFailure):
        message = str(error)
    elif isinstance(original, discord.HTTPException):
        message = "O Discord recusou uma das telas do combate. O erro detalhado foi salvo no log."
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    try:
        await sender(f"{message}\nCódigo do erro: `{code}`", ephemeral=True)
    except discord.HTTPException as send_error:
        audit_logger.error("[ERRO AO AVISAR USUÁRIO] %s", send_error)


bot.tree.add_command(personagem)
bot.tree.add_command(skill_group)
bot.tree.add_command(inimigo_group)
bot.tree.add_command(batalha_group)


def acquire_instance_lock() -> None:
    """Impede duas instâncias locais de consumirem a mesma interação do Discord."""
    global INSTANCE_LOCK_SOCKET
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        lock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        lock.bind(("127.0.0.1", INSTANCE_LOCK_PORT))
        lock.listen(1)
    except OSError as error:
        lock.close()
        raise SystemExit(
            "Já existe outra instância do Clash RPG Bot ligada neste computador. "
            "Feche o outro terminal/processo antes de iniciar novamente. "
            f"Trava local: porta {INSTANCE_LOCK_PORT}."
        ) from error
    INSTANCE_LOCK_SOCKET = lock
    threading.Thread(target=instance_control_loop, name="bot-local-control", daemon=True).start()


def instance_control_loop() -> None:
    """Recebe PING/STOP da Central, inclusive quando o bot foi iniciado por outro terminal."""
    lock = INSTANCE_LOCK_SOCKET
    if lock is None:
        return
    while True:
        try:
            connection, _ = lock.accept()
            with connection:
                command = connection.recv(64).decode("ascii", errors="ignore").strip().upper()
                if command == "PING":
                    connection.sendall(f"PONG {os.getpid()}".encode("ascii"))
                elif command == "STOP":
                    connection.sendall(b"STOPPING")
                    audit_logger.info("[CONTROLE LOCAL] desligamento solicitado pela Central")
                    loop = getattr(bot, "loop", None)
                    if loop is not None and loop.is_running():
                        asyncio.run_coroutine_threadsafe(bot.close(), loop)
                    else:
                        os._exit(0)
                elif command.startswith("BATTLE_REFRESH "):
                    try:
                        _, guild_id, channel_id = command.split()
                        loop = getattr(bot, "loop", None)
                        if loop is None or not loop.is_running():
                            raise RuntimeError("loop indisponível")
                        asyncio.run_coroutine_threadsafe(
                            refresh_battle_panel_from_control(int(guild_id), int(channel_id)), loop,
                        )
                        connection.sendall(b"REFRESHING")
                    except (ValueError, RuntimeError):
                        connection.sendall(b"REFRESH_FAILED")
                else:
                    connection.sendall(b"UNKNOWN")
        except OSError:
            return


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env.")
    acquire_instance_lock()
    try:
        audit_logger.info("[INICIALIZAÇÃO] abrindo conexão com o Discord | banco=%s", db.path if hasattr(db, "path") else "configurado")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        audit_logger.info("[DESLIGADO] interrupção manual recebida")
    except Exception as error:
        code = error_code()
        audit_logger.critical(
            "[FALHA AO INICIAR %s] tipo=%s | detalhe=%s\n%s",
            code, type(error).__name__, error,
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        )
        raise
