from __future__ import annotations

import os
import asyncio
import io
import logging
import traceback
from pathlib import Path
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from clash_engine import DamageResult, Forecast, Modifiers, Skill, SkillEffect, estimate_clash, format_skill_effects, heads_chance, parse_skill_effects, resolve_clash, resolve_damage, resolve_defense, triggered_skill_effects
from database import Database

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
COIN_ACTIVE = os.getenv("EMOJI_COIN_ACTIVE", "<:ML:1534094500815831181>")
COIN_BROKEN = os.getenv("EMOJI_COIN_BROKEN", "<:SA:1534127780977971270>")
COIN_HEADS = os.getenv("EMOJI_COIN_HEADS", "<:CG:1534127740381302864>")
COIN_TAILS = os.getenv("EMOJI_COIN_NORMAL", "<:MN:1534094257915297954>")
COIN_UNBREAKABLE = os.getenv("EMOJI_COIN_UNBREAKABLE", "<:MI:1535257836966117376>")
COIN_UNBREAKABLE_HEADS = os.getenv("EMOJI_COIN_UNBREAKABLE_HEADS", "<:MIA:1535261448694145124>")
EFFECT_CLASH_UP = os.getenv("EMOJI_CLASH_UP", "<:ECU:1534104390896455740>")
EFFECT_CLASH_DOWN = os.getenv("EMOJI_CLASH_DOWN", "<:ECD:1534104363658641479>")
EFFECT_ATTACK_UP = os.getenv("EMOJI_ATTACK_UP", "<:EAU:1535263226936295565>")
EFFECT_ATTACK_DOWN = os.getenv("EMOJI_ATTACK_DOWN", "<:EAD:11535263277574131722>")
EFFECT_PARALYZE = os.getenv("EMOJI_PARALYZE", "<:EP:1534104414183493702>")
EFFECT_OFFENSE_UP = os.getenv("EMOJI_OFFENSE_UP", "<:OLU:1534122107716501534>")
EFFECT_OFFENSE_DOWN = os.getenv("EMOJI_OFFENSE_DOWN", "<:OLD:1534122151911751811>")
EFFECT_PLUS_COIN_DROP = os.getenv("EMOJI_PLUS_COIN_DROP", "<:PCD:1534122057187590344>")
EFFECT_PLUS_COIN_BOOST = os.getenv("EMOJI_PLUS_COIN_BOOST", "<:PCB:1534122027143921766>")
OFFENSE_LEVEL_ICON = os.getenv("EMOJI_OFFENSE_LEVEL", EFFECT_OFFENSE_UP)
DEFENSE_LEVEL_ICON = os.getenv("EMOJI_DEFENSE_LEVEL", "🛡️")
UNBREAKABLE_FOLLOWUP_GIF = os.getenv(
    "UNBREAKABLE_FOLLOWUP_GIF", "",
)
DAMAGE_RESOLUTION_GIF = os.getenv(
    "DAMAGE_RESOLUTION_GIF", "",
)


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


def apply_skill_trigger(
    guild_id: int, actor_kind: str, actor_id: int, target_kind: str, target_id: int,
    skill: Skill, trigger: str, *, remaining_coins: int | None = None, hits=None,
) -> list[str]:
    """Paralyze afeta o alvo; SP e modificadores afetam o usuário da skill."""
    effects = triggered_skill_effects(skill, trigger, remaining_coins=remaining_coins, hits=hits)
    applied = []
    values = {"base_power": 0, "coin_power": 0, "clash_power": 0, "offense_level": 0}
    target_paralysis = sp_delta = 0
    for effect in effects:
        if effect.effect_type == "paralysis":
            target_paralysis += effect.value
        elif effect.effect_type == "sp":
            sp_delta += effect.value
        else:
            values[effect.effect_type] += effect.value
        coin_text = f" (moeda {effect.coin})" if effect.coin is not None else ""
        applied.append(f"`{trigger.upper()}` {effect.effect_type} `{effect.value:+}`{coin_text}")
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
    return applied


def add_trigger_log(embed: discord.Embed, applied: list[str]) -> None:
    if applied:
        embed.add_field(
            name="〔 EFEITOS ATIVADOS 〕",
            value="\n".join(f"◆ {line}" for line in applied)[:1024],
            inline=False,
        )


def revert_temporary_self_trigger(
    guild_id: int, actor_kind: str, actor_id: int, skill: Skill, trigger: str,
    *, remaining_coins: int | None = None,
) -> None:
    values = {"base_power": 0, "coin_power": 0, "clash_power": 0, "offense_level": 0}
    for effect in triggered_skill_effects(skill, trigger, remaining_coins=remaining_coins):
        if effect.effect_type in values:
            values[effect.effect_type] -= effect.value
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
    unbreakable_followup: bool = False,
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
    embed.add_field(name="〔 DANO FINAL 〕", value=f"## {result.final_damage}", inline=False)
    embed.set_footer(text="As moedas acumulam Coin Power; Offense − Defense é aplicado uma vez no final.")
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


if not audit_logger.handlers:
    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%d/%m/%Y %H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(AnsiAuditFormatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    file_handler = logging.FileHandler(AUDIT_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    audit_logger.addHandler(console)
    audit_logger.addHandler(file_handler)


def audit(interaction: discord.Interaction, action: str, details: str = "") -> None:
    guild = interaction.guild.name if interaction.guild else "DM"
    channel = getattr(interaction.channel, "name", "sem-canal")
    user = f"{interaction.user} ({interaction.user.id})"
    clean = details.replace("\n", " ")[:500]
    suffix = f" | {clean}" if clean else ""
    audit_logger.info("[%s] servidor=%s | canal=%s | usuário=%s%s", action, guild, channel, user, suffix)


def terminal_roll(roll) -> str:
    disabled = roll.disabled or [False] * len(roll.faces)
    return "".join("P" if blocked else ("H" if face else "T") for face, blocked in zip(roll.faces, disabled))


def audit_clash_rounds(
    interaction: discord.Interaction, title: str,
    left_name: str, right_name: str, result,
) -> None:
    guild = interaction.guild.name if interaction.guild else "DM"
    audit_logger.info("╔══════════════ %s ══════════════╗", title)
    audit_logger.info("║ %s  VS  %s | servidor=%s", left_name, right_name, guild)
    for rd in result.rounds[-10:]:
        arrow = {"left": "◀", "right": "▶", "tie": "="}[rd.result]
        audit_logger.info(
            "║ R%02d  %-12s %4d%s  %s  %-4d%s %s",
            rd.number, terminal_roll(rd.left), rd.left.power,
            " [MI]" if rd.left_unbreakable_broken else "",
            arrow, rd.right.power,
            " [MI]" if rd.right_unbreakable_broken else "",
            terminal_roll(rd.right),
        )
    if len(result.rounds) > 10:
        audit_logger.info("║ … %d rodada(s) anterior(es) omitida(s)", len(result.rounds) - 10)
    audit_logger.info(
        "║ VENCEDOR: %s | moedas finais: %d × %d",
        result.winner.upper(), result.left_coins, result.right_coins,
    )
    audit_logger.info("╚════════════════════════════════════════╝")


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


def character_embed(row, member: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title=f"〔 LCB // REGISTRO DE SINNER 〕",
        description=f"## {row['name']}\n`IDENTIDADE VINCULADA: {member.display_name}`",
        color=ACCENT,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="◈ SANIDADE", value=f"```{row['sp']:+d} SP\n{heads_chance(row['sp']):.0%} HEADS```")
    embed.add_field(name="◆ OFFENSE LEVEL", value=f"```{row['offense_level']}```")
    embed.add_field(name="◇ DEFENSE LEVEL", value=f"```{row['defense_level']}```")
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
    embed.add_field(name="▰ MODIFICADORES DO PRÓXIMO CLASH", value="\n".join(effects) or "`NENHUMA ANOMALIA DETECTADA`", inline=False)
    embed.set_footer(text="LIMBUS // Base e Coin expiram após o Clash • Paralisia é consumida por moeda")
    return embed


def skills_embed(skills: list[Skill], title: str = "Skills") -> discord.Embed:
    embed = discord.Embed(title=f"🪙 {title}", color=discord.Color.gold())
    if not skills:
        embed.description = "Nenhuma skill cadastrada ainda."
    for skill in skills[:20]:
        low, high = skill.range_with()
        unbreakable = f"  //  {skill.unbreakable_coins} INQUEBRÁVEL(IS)" if skill.unbreakable_coins else ""
        value = f"**{SKILL_TYPE_LABELS[skill.skill_type]}**\n`BASE {skill.base_power}  //  COIN {skill.coin_power:+d}  //  {skill.coins} MOEDAS{unbreakable}`\nFaixa natural: **{low}–{high}**"
        if skill.description:
            value += f"\n{skill.description}"
        if skill.effects:
            effect_lines = []
            for effect in skill.effects:
                target = f" • MOEDA {effect.coin}" if effect.coin is not None else ""
                effect_lines.append(
                    f"`{effect.trigger.upper()}` → **{effect.effect_type} {effect.value:+}**{target}"
                )
            value += "\n**EFEITOS CONFIGURADOS**\n" + "\n".join(effect_lines)
        embed.add_field(name=skill.name, value=value, inline=False)
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
        embed.add_field(name="RESULTADO", value="🛡️ **Moeda rolada; não há sucesso ou falha automática.**", inline=False)
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
    if result.kind == "counter" and result.counter_roll is not None:
        await asyncio.sleep(1.25)
        counter_damage = resolve_damage(
            defense, defense_sp, 1, defense_mod.level, attacker_defense_level,
            modifiers=defense_mod, faces=result.counter_roll.faces,
        )
        audit(interaction, "DANO DE COUNTER", f"{defender_name} -> {attacker_name}; dano={counter_damage.final_damage}")
        counter_embed = damage_embed(defender_name, attacker_name, defense, counter_damage)
        counter_gif = await attach_damage_gif(counter_embed)
        await interaction.followup.send(embed=counter_embed, files=[counter_gif] if counter_gif else [])


async def report_component_error(interaction: discord.Interaction, error: Exception, component: str) -> None:
    audit_logger.error(
        "[ERRO DE INTERFACE] componente=%s | usuário=%s (%s) | tipo=%s | detalhe=%s\n%s",
        component, interaction.user, interaction.user.id, type(error).__name__, error,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    try:
        await sender("Essa ação falhou. O erro detalhado foi salvo no log do bot.", ephemeral=True)
    except discord.HTTPException as send_error:
        audit_logger.error("[ERRO AO AVISAR FALHA DE INTERFACE] %s", send_error)


class LoggedView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        await report_component_error(interaction, error, getattr(item, "custom_id", type(item).__name__))


class LoggedModal(discord.ui.Modal):
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
        await interaction.response.send_modal(EditSkillModal(skill))


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


class EffectsModal(LoggedModal, title="Adicionar efeitos"):
    paralysis = discord.ui.TextInput(label="Paralisia", placeholder="Exemplo: 2", default="0", max_length=4)
    base = discord.ui.TextInput(label="Base Power Up/Down", placeholder="Exemplo: -1 ou 2", default="0", max_length=4)
    coin = discord.ui.TextInput(label="Coin Power Up/Down", placeholder="Exemplo: -1 ou 2", default="0", max_length=4)
    clash = discord.ui.TextInput(label="Clash Power Up/Down", placeholder="Exemplo: -1 ou 2", default="0", max_length=4)
    offense = discord.ui.TextInput(label="Offense Level Up/Down", placeholder="Exemplo: -3 ou 3", default="0", max_length=4)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            paralysis = int(str(self.paralysis))
            base, coin = int(str(self.base)), int(str(self.coin))
            clash, offense = int(str(self.clash)), int(str(self.offense))
        except ValueError:
            await interaction.response.send_message("Todos os campos precisam ser números inteiros.", ephemeral=True)
            return
        server = gid(interaction)
        if db.get_character(server, interaction.user.id) is None:
            await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
            return
        row = db.add_effects(server, interaction.user.id, paralysis, base, coin, clash, offense)
        audit(interaction, "EFEITOS EDITADOS", f"Paralisia+={paralysis}, Base+={base}, Coin+={coin}, Clash+={clash}, OL+={offense}")
        await interaction.response.edit_message(
            embed=character_embed(row, interaction.user), view=CharacterView()
        )


class CharacterView(LoggedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Editar níveis", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def levels(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(LevelsModal())

    @discord.ui.button(label="Adicionar efeitos", emoji="✨", style=discord.ButtonStyle.danger)
    async def effects(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(EffectsModal())

    @discord.ui.button(label="Atualizar ficha", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        if row is None:
            await interaction.response.send_message("Ficha não encontrada.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=character_embed(row, interaction.user), view=self)


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
        skills = db.list_enemy_skills(enemy["id"])
        if not skills:
            await interaction.response.send_message("Esse inimigo não possui skills.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=skills_embed(skills, f"Skills de {enemy['name']}"),
            view=EnemySkillActionView(enemy, skills, self.action),
        )


class EnemyActionView(LoggedView):
    def __init__(self, enemies, action: str) -> None:
        super().__init__(timeout=600)
        self.add_item(EnemyActionSelect(enemies, action))


def enemy_manager_embed(server: int) -> discord.Embed:
    enemies = db.list_enemies(server)
    embed = discord.Embed(title="〔 PAINEL DO MESTRE // HOSTIS 〕", color=ACCENT)
    embed.description = "Use os botões para gerenciar efeitos e skills inimigas."
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
        embed = damage_embed(character["name"], "ALVO DE TESTE", self.skill, result)
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
    participants = db.list_battle_participants(interaction.guild_id, interaction.channel_id)
    phase_labels = {
        "preparation": "PREPARAÇÃO",
        "declaration": "DECLARAÇÃO",
        "resolution": "RESOLUÇÃO",
        "complete": "ENCERRADO",
    }
    phase_help = {
        "preparation": "O mestre está montando o campo. Jogadores podem entrar na operação.",
        "declaration": "Escolha uma ação hostil e responda com uma de suas skills.",
        "resolution": "Novas declarações estão bloqueadas. Conclua sua ação e confirme **Pronto**.",
        "complete": "O turno foi concluído. O mestre pode avançar para o próximo.",
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
        participant_lines.append(
            f"{participant_icons.get(status, '•')} <@{participant['user_id']}> • "
            f"**{participant['character_name']}** • `{sp:+} SP` • "
            f"{participant_labels.get(status, status.upper())}"
            f"{' • **PRONTO**' if participant['ready'] else ''}"
        )
    embed.add_field(
        name="〔 EQUIPE EM CAMPO 〕",
        value="\n".join(participant_lines) if participant_lines else (
            "Nenhum Sinner entrou na operação. Use **Entrar na batalha** para ocupar uma posição."
        ),
        inline=False,
    )
    if phase == "resolution":
        pending = [
            f"<@{participant['user_id']}>"
            for participant in participants if not participant["ready"]
        ]
        embed.add_field(
            name="〔 PENDÊNCIAS DA RESOLUÇÃO 〕",
            value="Aguardando " + ", ".join(pending) if pending else "✅ Todos confirmaram prontidão.",
            inline=False,
        )

    enemies = {}
    for action in actions:
        summary = enemies.setdefault(action["enemy_name"], {"total": 0, "resolved": 0})
        summary["total"] += 1
        summary["resolved"] += action["status"] == "resolved"
    if enemies:
        enemy_lines = [
            f"◆ **{name}** • ações `{data['resolved']}/{data['total']}` resolvidas"
            for name, data in list(enemies.items())[:15]
        ]
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
            f"Ações disponíveis **{open_count}**  •  Resolvidas **{resolved_count}/{len(actions)}**\n"
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
        if skill is None or enemy_skill is None or not skill.is_clashable or not enemy_skill.is_clashable:
            await interaction.response.send_message("Uma das skills não está mais disponível para Clash.", ephemeral=True)
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
            await clash_inimigo_impl(
                interaction, action["enemy_name"], skill.name, action["enemy_skill"],
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
        skills = [
            skill for skill in db.list_skills(gid(interaction), interaction.user.id)
            if skill.is_clashable
        ]
        if not skills:
            await interaction.response.send_message("Você não possui uma skill capaz de disputar Clash.", ephemeral=True)
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
        if battle is None or battle["phase"] != "resolution":
            await interaction.response.send_message(
                "A prontidão só pode ser confirmada durante a fase de **Resolução**.", ephemeral=True,
            )
            return
        participant = db.get_battle_participant(gid(interaction), interaction.channel_id, interaction.user.id)
        if participant is None:
            await interaction.response.send_message("Entre na batalha antes de confirmar prontidão.", ephemeral=True)
            return
        if participant["status"] != "done":
            await interaction.response.send_message(
                "Você precisa concluir sua ação antes de marcar **Pronto**.", ephemeral=True,
            )
            return
        new_ready = not bool(participant["ready"])
        db.set_battle_participant_ready(
            gid(interaction), interaction.channel_id, interaction.user.id, new_ready,
        )
        participants = db.list_battle_participants(gid(interaction), interaction.channel_id)
        completed = bool(participants) and all(bool(row["ready"]) for row in participants)
        if completed:
            db.set_battle_phase(gid(interaction), interaction.channel_id, "complete")
        audit(interaction, "PRONTIDÃO ALTERADA", f"pronto={new_ready}")
        await interaction.response.defer(ephemeral=True)
        await update_fixed_battle_panel(interaction)
        message = "✅ Você está pronto para o próximo turno." if new_ready else "↩️ Sua prontidão foi removida."
        if completed:
            message += " Todos confirmaram; o turno foi encerrado automaticamente."
        await interaction.followup.send(message, ephemeral=True)

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
}
BUILDER_EFFECT_LABELS = {
    "paralysis": "Paralisia no alvo", "sp": "Sanidade própria",
    "base_power": "Base Power próprio", "coin_power": "Coin Power próprio",
    "clash_power": "Clash Power próprio", "offense_level": "Offense Level próprio",
}


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
            label="Moedas, Inquebráveis", default=f"{builder.coins}, {builder.unbreakable_coins}",
            placeholder="Exemplo: 3, 1", max_length=20,
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
            coins, unbreakable = [int(value.strip()) for value in str(self.coins_input).split(",")]
            if not 1 <= coins <= 10 or not 0 <= unbreakable <= coins:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Use dois números separados por vírgula. Moedas: 1–10; inquebráveis: 0 até o total.", ephemeral=True,
            )
            return
        self.builder.name = str(self.name_input).strip()
        self.builder.base_power, self.builder.coin_power = base, coin
        self.builder.coins, self.builder.unbreakable_coins = coins, unbreakable
        self.builder.description = str(self.description_input)
        self.builder.trim_invalid_effects()
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderEffectModal(LoggedModal, title="Adicionar efeito"):
    def __init__(self, builder: "SkillBuilderView") -> None:
        super().__init__()
        self.builder = builder
        self.value_input = discord.ui.TextInput(
            label="Valor do efeito", placeholder="Exemplo: 2 ou -2", max_length=8,
        )
        self.coin_input = discord.ui.TextInput(
            label="Moeda específica (opcional)", placeholder="Vazio = todas / automático",
            required=False, max_length=2,
        )
        self.add_item(self.value_input)
        self.add_item(self.coin_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(str(self.value_input))
            raw_coin = str(self.coin_input).strip()
            coin = int(raw_coin) if raw_coin else None
            effect = SkillEffect(self.builder.selected_trigger, self.builder.selected_effect, value, coin)
            if coin is not None and coin > self.builder.coins:
                raise ValueError("Essa moeda não existe na skill.")
        except ValueError as error:
            await interaction.response.send_message(f"Efeito inválido: {error}", ephemeral=True)
            return
        self.builder.effects.append(effect)
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


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
            placeholder="2. Escolha quando o efeito ativa", row=1,
            options=[discord.SelectOption(label=label, value=value) for value, label in TRIGGER_LABELS.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            return
        self.builder.selected_trigger = self.values[0]
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderEffectSelect(discord.ui.Select):
    def __init__(self, builder: "SkillBuilderView") -> None:
        self.builder = builder
        super().__init__(
            placeholder="3. Escolha qual efeito será aplicado", row=2,
            options=[discord.SelectOption(label=label, value=value) for value, label in BUILDER_EFFECT_LABELS.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.builder.owned_by(interaction):
            return
        self.builder.selected_effect = self.values[0]
        await interaction.response.edit_message(embed=self.builder.build_embed(), view=self.builder)


class SkillBuilderView(LoggedView):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.name, self.description = "Nova Skill", ""
        self.base_power, self.coin_power = 4, 2
        self.coins, self.unbreakable_coins = 2, 0
        self.skill_type = "attack"
        self.selected_trigger, self.selected_effect = "on_hit", "paralysis"
        self.effects: list[SkillEffect] = []
        self.add_item(SkillBuilderTypeSelect(self))
        self.add_item(SkillBuilderTriggerSelect(self))
        self.add_item(SkillBuilderEffectSelect(self))

    def owned_by(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    def trim_invalid_effects(self) -> None:
        self.effects = [effect for effect in self.effects if effect.coin is None or effect.coin <= self.coins]

    def skill(self) -> Skill:
        return Skill(
            self.name, self.base_power, self.coin_power, self.coins, self.description,
            self.skill_type, self.unbreakable_coins, tuple(self.effects),
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
                f"**Faixa:** `{low}–{high}`"
            ), inline=False,
        )
        if self.description:
            embed.add_field(name="◇ DESCRIÇÃO", value=self.description, inline=False)
        effect_lines = [
            f"`{index:02}` **{TRIGGER_LABELS[effect.trigger]}** → "
            f"{BUILDER_EFFECT_LABELS[effect.effect_type]} `{effect.value:+}`"
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
        embed.set_footer(text="Defina os dados • escolha gatilho e efeito • adicione • salve")
        return embed

    @discord.ui.button(label="Definir dados", emoji="✏️", style=discord.ButtonStyle.secondary, row=3)
    async def basics(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        await interaction.response.send_modal(SkillBuilderBasicsModal(self))

    @discord.ui.button(label="Adicionar efeito", emoji="➕", style=discord.ButtonStyle.primary, row=3)
    async def add_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        await interaction.response.send_modal(SkillBuilderEffectModal(self))

    @discord.ui.button(label="Remover último", emoji="↩️", style=discord.ButtonStyle.secondary, row=3)
    async def remove_effect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if self.effects:
            self.effects.pop()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Salvar skill", emoji="💾", style=discord.ButtonStyle.success, row=4)
    async def save(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message("Este editor pertence a outro jogador.", ephemeral=True)
            return
        if db.get_character(gid(interaction), interaction.user.id) is None:
            await interaction.response.send_message("Crie sua ficha antes de salvar uma skill.", ephemeral=True)
            return
        try:
            skill = self.skill()
        except ValueError as error:
            await interaction.response.send_message(f"Não foi possível salvar: {error}", ephemeral=True)
            return
        db.save_skill(gid(interaction), interaction.user.id, skill)
        audit(interaction, "SKILL CRIADA NO WORKSHOP", skill.name)
        await interaction.response.edit_message(
            embed=skills_embed([skill], "✅ Skill criada"), view=SkillsView(),
        )


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
        embed.description = (
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
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Mestre • Inimigos", emoji="👁️", style=discord.ButtonStyle.danger)
    async def enemies(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not master_allowed(interaction):
            await interaction.response.send_message("Você precisa de Gerenciar servidor.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=enemy_manager_embed(gid(interaction)), view=EnemyManagerView(), ephemeral=True
        )


class ClashBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self) -> None:
        db.setup()
        self.add_view(BattlePanelView())
        if GUILD_IDS:
            for guild_id in GUILD_IDS:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        audit_logger.info("[ONLINE] %s | servidores=%d | auditoria=%s", self.user, len(self.guilds), AUDIT_PATH)


bot = ClashBot()
personagem = app_commands.Group(name="personagem", description="Ficha, níveis e efeitos")
skill_group = app_commands.Group(name="skill", description="Crie e consulte skills")
inimigo_group = app_commands.Group(name="inimigo", description="Mestre: gerencie inimigos")
batalha_group = app_commands.Group(name="batalha", description="Sessão e skills presentes no campo")


@bot.listen("on_interaction")
async def interaction_audit(interaction: discord.Interaction) -> None:
    data = interaction.data or {}
    if interaction.type is discord.InteractionType.application_command:
        name = str(data.get("name", "comando"))
        options = data.get("options", [])
        if options and isinstance(options, list) and isinstance(options[0], dict) and "name" in options[0]:
            name += f" {options[0]['name']}"
        audit(interaction, "COMANDO", f"/{name}")
    elif interaction.type is discord.InteractionType.component:
        audit(interaction, "BOTÃO", str(data.get("custom_id", "componente")))
    elif interaction.type is discord.InteractionType.modal_submit:
        audit(interaction, "FORMULÁRIO", str(data.get("custom_id", "modal")))


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
    audit(interaction, "SKILL COLOCADA NO CAMPO", f"ação=#{action['id']}; {enemy['name']} / {skill.name}")
    await interaction.response.defer(ephemeral=True)
    updated = await update_fixed_battle_panel(interaction)
    await interaction.followup.send(
        f"✅ **{enemy['name']}** colocou `{skill.name}` no campo como ação `#{action['id']}`."
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


@personagem.command(name="criar", description="Cria ou renomeia sua ficha")
async def personagem_criar(interaction: discord.Interaction, nome: str) -> None:
    db.create_character(gid(interaction), interaction.user.id, nome[:50])
    row = db.get_character(interaction.guild_id, interaction.user.id)
    await interaction.response.send_message(embed=character_embed(row, interaction.user))


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
    clash_power: int = 0, offense_level: int = 0,
) -> None:
    row = db.add_effects(gid(interaction), jogador.id, paralisia, base_power, coin_power, clash_power, offense_level)
    if row is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    audit(interaction, "EFEITOS", f"alvo={jogador} Paralisia+={paralisia}, Base+={base_power}, Coin+={coin_power}, Clash+={clash_power}, OL+={offense_level}")
    await interaction.response.send_message(embed=character_embed(row, jogador))


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
        attacks = db.list_enemy_skills(enemy["id"])
        names = ", ".join(s.name for s in attacks) or "Sem ataques"
        effects = []
        if enemy["paralysis"]: effects.append(f"Paralisia {enemy['paralysis']}")
        if enemy["base_power_mod"]: effects.append(f"Base {enemy['base_power_mod']:+d}")
        if enemy["coin_power_mod"]: effects.append(f"Coin {enemy['coin_power_mod']:+d}")
        if enemy["clash_power_mod"]: effects.append(f"Clash {enemy['clash_power_mod']:+d}")
        if enemy["offense_level_mod"]: effects.append(f"OL {enemy['offense_level_mod']:+d}")
        effect_text = " • ".join(effects) or "Sem efeitos"
        embed.add_field(
            name=enemy["name"],
            value=f"SP `{'%+d' % enemy['sp'] if enemy['uses_sanity'] else 'INATIVA (50% Heads)'}` • OL `{enemy['offense_level']}` • DL `{enemy['defense_level']}`\n**Skills:** {names}\n**Efeitos:** {effect_text}",
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
    apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "on_use")
    apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "on_use")
    lc, rc = db.get_character(server, interaction.user.id), db.get_character(server, oponente.id)
    left_level = lc["defense_level"] if left.uses_defense_level else lc["offense_level"] + lc["offense_level_mod"]
    right_level = rc["defense_level"] if right.uses_defense_level else rc["offense_level"] + rc["offense_level_mod"]
    lm = Modifiers(lc["base_power_mod"], lc["coin_power_mod"], lc["paralysis"], left_level, lc["clash_power_mod"])
    rm = Modifiers(rc["base_power_mod"], rc["coin_power_mod"], rc["paralysis"], right_level, rc["clash_power_mod"])
    if not left.is_clashable and not right.is_clashable:
        await interaction.response.send_message("As duas defesas comuns se anulam (**Offset**); nenhuma é ativada.")
        return
    if not left.is_clashable:
        await show_defense_resolution(interaction, rc["name"], right, rc["sp"], rm, lc["name"], left, lc["sp"], lm, rc["defense_level"])
        return
    if not right.is_clashable:
        await show_defense_resolution(interaction, lc["name"], left, lc["sp"], lm, rc["name"], right, rc["sp"], rm, lc["defense_level"])
        return
    await interaction.response.defer()
    audit(
        interaction, "CLASH INICIADO",
        f"{lc['name']} ({left.name}, {left.coins} moedas) vs {rc['name']} ({right.name}, {right.coins} moedas)",
    )
    forecast = prediction_with_paralysis(left, lc["sp"], right, rc["sp"], lm, rm)
    audit(interaction, "PREVISÃO CALCULADA", f"5 projeções; chance esquerda={forecast.win_chance:.0%}; classe={forecast.label}")
    result = resolve_clash(left, lc["sp"], right, rc["sp"], left_modifiers=lm, right_modifiers=rm)
    audit(interaction, "CLASH RESOLVIDO", f"vencedor={result.winner}; rodadas={len(result.rounds)}; moedas={result.left_coins}x{result.right_coins}")
    audit_clash_rounds(interaction, "REGISTRO DE CLASH", lc["name"], rc["name"], result)
    left_min, left_max = left.range_with()
    right_min, right_max = right.range_with()
    clash_gif = clash_gif_for(left, right)

    def animated_embed(round_index: int = 0, finished: bool = False) -> discord.Embed:
        current = discord.Embed(title="〔 ⚠ CLASH ENGAGED ⚠ 〕", color=GOLD if not finished else ACCENT)
        current.description = f"## {lc['name']}  ⟷  {rc['name']}\n`{left.name.upper()}`  **VS**  `{right.name.upper()}`"
        current.add_field(
            name="◀ PARÂMETROS",
            value=f"{effect_icon(lc['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base `{left.base_power} {lc['base_power_mod']:+d}`\n{effect_icon(lc['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Coin `{left.coin_power} {lc['coin_power_mod']:+d}`\n{effect_icon(lc['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash `{lc['clash_power_mod']:+d}`\nFaixa `{left_min}–{left_max}` • {level_symbol(left)} `{left_level}`",
            inline=True,
        )
        current.add_field(
            name="PARÂMETROS ▶",
            value=f"{effect_icon(rc['base_power_mod'], EFFECT_ATTACK_UP, EFFECT_ATTACK_DOWN)} Base `{right.base_power} {rc['base_power_mod']:+d}`\n{effect_icon(rc['coin_power_mod'], EFFECT_PLUS_COIN_BOOST, EFFECT_PLUS_COIN_DROP)} Coin `{right.coin_power} {rc['coin_power_mod']:+d}`\n{effect_icon(rc['clash_power_mod'], EFFECT_CLASH_UP, EFFECT_CLASH_DOWN)} Clash `{rc['clash_power_mod']:+d}`\nFaixa `{right_min}–{right_max}` • {level_symbol(right)} `{right_level}`",
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
            current.add_field(name="〔 RESULTADO CONFIRMADO 〕", value=f"🏆 **{winner}** venceu com **{remaining}** moeda(s) ativa(s){mi_text}.\nSanidade: vencedor **+10** • perdedor **−5**", inline=False)
        else:
            current.set_footer(text="PROCESSANDO PROBABILIDADES E QUEBRA DE MOEDAS…")
        return current

    await interaction.edit_original_response(
        embed=prediction_embed(lc["name"], left, rc["name"], right, forecast, clash_gif)
    )
    await asyncio.sleep(2.5)
    await interaction.edit_original_response(embed=animated_embed())
    await asyncio.sleep(1.0)
    animation_rounds = min(len(result.rounds), 10)
    for index in range(1, animation_rounds + 1):
        await interaction.edit_original_response(embed=animated_embed(index))
        await asyncio.sleep(0.85)

    db.consume_clash_effects(server, interaction.user.id, result.left_paralysis)
    db.consume_clash_effects(server, oponente.id, result.right_paralysis)
    winner_id, loser_id = ((interaction.user.id, oponente.id) if result.winner == "left" else (oponente.id, interaction.user.id))
    db.change_sp(server, winner_id, 10)
    db.change_sp(server, loser_id, -5)
    if result.winner == "left":
        effect_log = apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "clash_win", remaining_coins=result.left_coins)
        effect_log += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "clash_lose", remaining_coins=result.right_coins)
    else:
        effect_log = apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "clash_win", remaining_coins=result.right_coins)
        effect_log += apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "clash_lose", remaining_coins=result.left_coins)
    if effect_log:
        audit(interaction, "EFEITOS DE SKILL", "; ".join(effect_log))
    winner = lc["name"] if result.winner == "left" else rc["name"]
    audit(
        interaction,
        "CLASH FINALIZADO",
        f"{lc['name']} ({left.name}) vs {rc['name']} ({right.name}); vencedor={winner}; rodadas={len(result.rounds)}",
    )
    await interaction.edit_original_response(embed=animated_embed(len(result.rounds), finished=True))
    winning_skill = left if result.winner == "left" else right
    if winning_skill.deals_damage:
        if result.winner == "left":
            apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "before_attack", remaining_coins=result.left_coins)
            lc = db.get_character(server, interaction.user.id)
        else:
            apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "before_attack", remaining_coins=result.right_coins)
            rc = db.get_character(server, oponente.id)
        await asyncio.sleep(1.25)
        if result.winner == "left":
            damage = resolve_damage(
                left, lc["sp"], result.left_coins,
                lc["offense_level"] + lc["offense_level_mod"], rc["defense_level"],
                modifiers=Modifiers(lc["base_power_mod"], lc["coin_power_mod"], result.left_paralysis),
                broken_unbreakable=result.left_broken_unbreakable,
            )
            attacker_name, target_name = lc["name"], rc["name"]
        else:
            damage = resolve_damage(
                right, rc["sp"], result.right_coins,
                rc["offense_level"] + rc["offense_level_mod"], lc["defense_level"],
                modifiers=Modifiers(rc["base_power_mod"], rc["coin_power_mod"], result.right_paralysis),
                broken_unbreakable=result.right_broken_unbreakable,
            )
            attacker_name, target_name = rc["name"], lc["name"]
        if result.winner == "left":
            revert_temporary_self_trigger(server, "player", interaction.user.id, left, "before_attack", remaining_coins=result.left_coins)
        else:
            revert_temporary_self_trigger(server, "player", oponente.id, right, "before_attack", remaining_coins=result.right_coins)
        audit(interaction, "DANO FINAL", f"{attacker_name} -> {target_name}; dano={damage.final_damage}")
        final_embed = damage_embed(attacker_name, target_name, winning_skill, damage)
        if result.winner == "left":
            damage_effects = apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "on_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "heads_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "player", interaction.user.id, "player", oponente.id, left, "after_attack", remaining_coins=result.left_coins)
        else:
            damage_effects = apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "on_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "heads_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "player", oponente.id, "player", interaction.user.id, right, "after_attack", remaining_coins=result.right_coins)
        if damage_effects:
            audit(interaction, "EFEITOS DE ACERTO", "; ".join(damage_effects))
        add_trigger_log(final_embed, damage_effects)
        final_gif = await attach_damage_gif(final_embed)
        await interaction.followup.send(embed=final_embed, files=[final_gif] if final_gif else [])
    losing_skill = right if result.winner == "left" else left
    cracked = result.right_broken_unbreakable if result.winner == "left" else result.left_broken_unbreakable
    if winning_skill.deals_damage and losing_skill.deals_damage and cracked > 0:
        await asyncio.sleep(1.25)
        if result.winner == "left":
            follow_skill, follow_damage = resolve_unbreakable_followup(
                right, rc["sp"], cracked,
                rc["offense_level"] + rc["offense_level_mod"], lc["defense_level"],
                Modifiers(rc["base_power_mod"], rc["coin_power_mod"], result.right_paralysis),
            )
            follow_attacker, follow_target = rc["name"], lc["name"]
        else:
            follow_skill, follow_damage = resolve_unbreakable_followup(
                left, lc["sp"], cracked,
                lc["offense_level"] + lc["offense_level_mod"], rc["defense_level"],
                Modifiers(lc["base_power_mod"], lc["coin_power_mod"], result.left_paralysis),
            )
            follow_attacker, follow_target = lc["name"], rc["name"]
        audit(interaction, "ATAQUE INQUEBRÁVEL", f"{follow_attacker} -> {follow_target}; moedas={cracked}; dano={follow_damage.final_damage}")
        follow_embed = damage_embed(
            follow_attacker, follow_target, follow_skill, follow_damage,
            unbreakable_followup=True,
        )
        follow_gif = await attach_damage_gif(follow_embed, unbreakable_followup=True)
        await interaction.followup.send(embed=follow_embed, files=[follow_gif] if follow_gif else [])


async def clash_inimigo_impl(
    interaction: discord.Interaction, inimigo: str, sua_skill: str, skill_inimiga: str,
) -> None:
    server = gid(interaction)
    player = db.get_character(server, interaction.user.id)
    enemy = db.get_enemy(server, inimigo)
    left = db.get_skill(server, interaction.user.id, sua_skill)
    right = None if enemy is None else db.get_enemy_skill(enemy["id"], skill_inimiga)
    if not all((player, enemy, left, right)):
        await interaction.response.send_message(
            "Não encontrei a ficha, o inimigo ou uma das skills. Use `/skill listar` e `/inimigo listar`.",
            ephemeral=True,
        )
        return
    apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "on_use")
    apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "on_use")
    player = db.get_character(server, interaction.user.id)
    enemy = db.get_enemy(server, inimigo)
    left_level = player["defense_level"] if left.uses_defense_level else player["offense_level"] + player["offense_level_mod"]
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
        await show_defense_resolution(interaction, player["name"], left, player["sp"], lm, enemy["name"], right, enemy_sp, rm, player["defense_level"])
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
    audit(interaction, "CLASH INIMIGO RESOLVIDO", f"vencedor={result.winner}; rodadas={len(result.rounds)}; moedas={result.left_coins}x{result.right_coins}")
    audit_clash_rounds(interaction, "REGISTRO DE CLASH HOSTIL", player["name"], enemy["name"], result)
    gif = clash_gif_for(left, right)
    left_min, left_max = left.range_with()
    right_min, right_max = right.range_with()

    def enemy_embed(round_index: int, finished: bool = False) -> discord.Embed:
        embed = discord.Embed(title="〔 ⚠ HOSTILE CLASH ⚠ 〕", color=ACCENT if finished else GOLD)
        embed.description = f"## {player['name']}  ⟷  {enemy['name']}\n`{left.name.upper()}` **VS** `{right.name.upper()}`"
        embed.add_field(
            name="◀ PARÂMETROS",
            value=f"Base `{left.base_power} {player['base_power_mod']:+d}`\nCoin `{left.coin_power} {player['coin_power_mod']:+d}`\nFaixa `{left_min}–{left_max}` • {level_symbol(left)} `{left_level}`",
            inline=True,
        )
        embed.add_field(
            name="PARÂMETROS ▶",
            value=f"Base `{right.base_power} {enemy['base_power_mod']:+d}`\nCoin `{right.coin_power} {enemy['coin_power_mod']:+d}`\nFaixa `{right_min}–{right_max}` • {level_symbol(right)} `{right_level}`",
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
            player_sp_change = "+10" if result.winner == "left" else "−5"
            if enemy["uses_sanity"]:
                enemy_sp_change = "−5" if result.winner == "left" else "+10"
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

    await interaction.edit_original_response(
        embed=prediction_embed(player["name"], left, enemy["name"], right, forecast, gif)
    )
    await asyncio.sleep(2.5)
    await interaction.edit_original_response(embed=enemy_embed(0))
    await asyncio.sleep(1.0)
    for index in range(1, min(len(result.rounds), 10) + 1):
        await interaction.edit_original_response(embed=enemy_embed(index))
        await asyncio.sleep(0.85)

    db.consume_clash_effects(server, interaction.user.id, result.left_paralysis)
    db.consume_enemy_effects(enemy["id"], result.right_paralysis)
    if result.winner == "left":
        db.change_sp(server, interaction.user.id, 10)
        if enemy["uses_sanity"]:
            db.change_enemy_sp(enemy["id"], -5)
    else:
        db.change_sp(server, interaction.user.id, -5)
        if enemy["uses_sanity"]:
            db.change_enemy_sp(enemy["id"], 10)
    if result.winner == "left":
        effect_log = apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "clash_win", remaining_coins=result.left_coins)
        effect_log += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "clash_lose", remaining_coins=result.right_coins)
    else:
        effect_log = apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "clash_win", remaining_coins=result.right_coins)
        effect_log += apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "clash_lose", remaining_coins=result.left_coins)
    if effect_log:
        audit(interaction, "EFEITOS DE SKILL", "; ".join(effect_log))
    winner = player["name"] if result.winner == "left" else enemy["name"]
    audit(interaction, "CLASH VS INIMIGO", f"{player['name']} vs {enemy['name']}; vencedor={winner}; rodadas={len(result.rounds)}")
    await interaction.edit_original_response(embed=enemy_embed(len(result.rounds), finished=True))
    winning_skill = left if result.winner == "left" else right
    if winning_skill.deals_damage:
        if result.winner == "left":
            apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "before_attack", remaining_coins=result.left_coins)
            player = db.get_character(server, interaction.user.id)
        else:
            apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "before_attack", remaining_coins=result.right_coins)
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
        else:
            damage = resolve_damage(
                right, enemy_sp, result.right_coins,
                enemy["offense_level"] + enemy["offense_level_mod"], player["defense_level"],
                modifiers=Modifiers(enemy["base_power_mod"], enemy["coin_power_mod"], result.right_paralysis),
                broken_unbreakable=result.right_broken_unbreakable,
            )
            attacker_name, target_name = enemy["name"], player["name"]
        if result.winner == "left":
            revert_temporary_self_trigger(server, "player", interaction.user.id, left, "before_attack", remaining_coins=result.left_coins)
        else:
            revert_temporary_self_trigger(server, "enemy", enemy["id"], right, "before_attack", remaining_coins=result.right_coins)
        audit(interaction, "DANO FINAL", f"{attacker_name} -> {target_name}; dano={damage.final_damage}")
        final_embed = damage_embed(attacker_name, target_name, winning_skill, damage)
        if result.winner == "left":
            damage_effects = apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "on_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "heads_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "player", interaction.user.id, "enemy", enemy["id"], left, "after_attack", remaining_coins=result.left_coins)
        else:
            damage_effects = apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "on_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "heads_hit", hits=damage.hits)
            damage_effects += apply_skill_trigger(server, "enemy", enemy["id"], "player", interaction.user.id, right, "after_attack", remaining_coins=result.right_coins)
        if damage_effects:
            audit(interaction, "EFEITOS DE ACERTO", "; ".join(damage_effects))
        add_trigger_log(final_embed, damage_effects)
        final_gif = await attach_damage_gif(final_embed)
        await interaction.followup.send(embed=final_embed, files=[final_gif] if final_gif else [])
    losing_skill = right if result.winner == "left" else left
    cracked = result.right_broken_unbreakable if result.winner == "left" else result.left_broken_unbreakable
    if winning_skill.deals_damage and losing_skill.deals_damage and cracked > 0:
        await asyncio.sleep(1.25)
        if result.winner == "left":
            follow_skill, follow_damage = resolve_unbreakable_followup(
                right, enemy_sp, cracked,
                enemy["offense_level"] + enemy["offense_level_mod"], player["defense_level"],
                Modifiers(enemy["base_power_mod"], enemy["coin_power_mod"], result.right_paralysis),
            )
            follow_attacker, follow_target = enemy["name"], player["name"]
        else:
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
        skills = [
            skill for skill in db.list_skills(gid(interaction), self.target_id) if skill.is_clashable
        ]
        if not skills:
            await interaction.response.send_message("Você não possui uma skill capaz de disputar Clash.", ephemeral=True)
            return
        challenger_skill = db.get_skill(gid(interaction), self.challenger_id, self.challenger_skill)
        if challenger_skill is None or not challenger_skill.is_clashable:
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
        if challenger_skill is None or not challenger_skill.is_clashable:
            await interaction.response.send_message("Escolha uma skill capaz de disputar Clash.", ephemeral=True)
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
        await interaction.response.send_message(
            embed=embed,
            view=PvPChallengeView(interaction.user.id, opponent.id, challenger_skill.name),
        )
        return
    if alvo.startswith("enemy:"):
        if not skill_alvo:
            await interaction.response.send_message(
                "Escolha a skill do inimigo no campo `skill_alvo`.", ephemeral=True,
            )
            return
        await clash_inimigo_impl(interaction, alvo.split(":", 1)[1], sua_skill, skill_alvo)
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
    audit_logger.error(
        "[ERRO] comando=/%s | usuário=%s (%s) | tipo=%s | detalhe=%s\n%s",
        command_name, interaction.user, interaction.user.id, type(original).__name__, original,
        "".join(traceback.format_exception(type(original), original, original.__traceback__)),
    )
    message = "O comando falhou. Confira os valores informados."
    if isinstance(error, app_commands.MissingPermissions):
        message = "Apenas alguém com permissão de gerenciar o servidor pode fazer isso."
    elif isinstance(error, app_commands.CheckFailure):
        message = str(error)
    elif isinstance(original, discord.HTTPException):
        message = "O Discord recusou uma das telas do combate. O erro detalhado foi salvo no log."
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    try:
        await sender(message, ephemeral=True)
    except discord.HTTPException as send_error:
        audit_logger.error("[ERRO AO AVISAR USUÁRIO] %s", send_error)


bot.tree.add_command(personagem)
bot.tree.add_command(skill_group)
bot.tree.add_command(inimigo_group)
bot.tree.add_command(batalha_group)

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env.")
    bot.run(TOKEN)
