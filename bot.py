from __future__ import annotations

import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from clash_engine import Modifiers, Skill, heads_chance, resolve_clash
from database import Database

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
db = Database(os.getenv("DATABASE_PATH", "clash_rpg.sqlite3"))
ACCENT = discord.Color.from_rgb(238, 74, 84)


def gid(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise app_commands.CheckFailure("Use este comando dentro de um servidor.")
    return interaction.guild_id


def character_embed(row, member: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(title=f"Ficha • {row['name']}", color=ACCENT)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🧠 Sanidade", value=f"**{row['sp']:+d} SP**\n{heads_chance(row['sp']):.0%} Heads")
    embed.add_field(name="⚔️ Nível ofensivo", value=f"**{row['offense_level']}**")
    embed.add_field(name="🛡️ Nível defensivo", value=f"**{row['defense_level']}**")
    effects = []
    if row["paralysis"]:
        effects.append(f"⚡ Paralisia **{row['paralysis']}**")
    if row["base_power_mod"]:
        effects.append(f"🔹 Base Power **{row['base_power_mod']:+d}**")
    if row["coin_power_mod"]:
        effects.append(f"🪙 Coin Power **{row['coin_power_mod']:+d}**")
    embed.add_field(name="Efeitos do próximo Clash", value="\n".join(effects) or "Nenhum", inline=False)
    embed.set_footer(text="Base/Coin são consumidos no próximo Clash • Paralisia é consumida por moeda")
    return embed


def skills_embed(skills: list[Skill], title: str = "Skills") -> discord.Embed:
    embed = discord.Embed(title=f"🪙 {title}", color=discord.Color.gold())
    if not skills:
        embed.description = "Nenhuma skill cadastrada ainda."
    for skill in skills[:20]:
        low, high = skill.range_with()
        icon = "⚔️" if skill.level_type == "offense" else "🛡️"
        value = f"`{skill.base_power} {skill.coin_power:+d} × {skill.coins}` • faixa **{low}–{high}** • {icon} {skill.level_type.title()}"
        if skill.description:
            value += f"\n{skill.description}"
        embed.add_field(name=skill.name, value=value, inline=False)
    return embed


class SkillModal(discord.ui.Modal, title="Criar ou editar skill"):
    name = discord.ui.TextInput(label="Nome", max_length=50)
    values = discord.ui.TextInput(label="Base, Coin Power, Moedas", placeholder="Exemplo: 4, 3, 3", max_length=30)
    level_type = discord.ui.TextInput(label="Tipo de nível", placeholder="offense ou defense", default="offense", max_length=7)
    description = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False, max_length=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            base, coin, coins = (int(item.strip()) for item in str(self.values).split(","))
            kind = str(self.level_type).strip().lower()
            skill = Skill(str(self.name), base, coin, coins, str(self.description), kind)
        except (ValueError, TypeError):
            await interaction.response.send_message("Use três números separados por vírgula e `offense` ou `defense`.", ephemeral=True)
            return
        if db.get_character(gid(interaction), interaction.user.id) is None:
            await interaction.response.send_message("Crie uma ficha primeiro com `/personagem criar`.", ephemeral=True)
            return
        db.save_skill(interaction.guild_id, interaction.user.id, skill)
        await interaction.response.send_message(embed=skills_embed([skill], "Skill salva"), ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Minha ficha", emoji="🧠", style=discord.ButtonStyle.primary)
    async def sheet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        row = db.get_character(gid(interaction), interaction.user.id)
        if row is None:
            await interaction.response.send_message("Crie sua ficha com `/personagem criar`.", ephemeral=True)
            return
        await interaction.response.send_message(embed=character_embed(row, interaction.user), ephemeral=True)

    @discord.ui.button(label="Minhas skills", emoji="🪙", style=discord.ButtonStyle.secondary)
    async def skills(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=skills_embed(db.list_skills(gid(interaction), interaction.user.id)), ephemeral=True
        )

    @discord.ui.button(label="Criar skill", emoji="✨", style=discord.ButtonStyle.success)
    async def create(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(SkillModal())

    @discord.ui.button(label="Regras", emoji="📖", style=discord.ButtonStyle.secondary)
    async def rules(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        embed = discord.Embed(title="Regras rápidas", color=ACCENT)
        embed.description = (
            "**SP:** chance de Heads = 50% + SP.\n"
            "**Clash:** quem perde uma rodada perde uma moeda.\n"
            "**Paralisia:** zera o Coin Power das próximas moedas.\n"
            "**Base/Coin Up ou Down:** altera o próximo Clash.\n"
            "**Níveis:** +1 de Clash Power por 3 níveis de vantagem."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ClashBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self) -> None:
        db.setup()
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = ClashBot()
personagem = app_commands.Group(name="personagem", description="Ficha, níveis e efeitos")
skill_group = app_commands.Group(name="skill", description="Crie e consulte skills")


@bot.tree.command(name="painel", description="Abre o painel interativo do RPG")
async def painel(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="⚔️ Clash RPG",
        description="Gerencie sua ficha e suas skills pelos botões abaixo.\nPara lutar, use `/clash`.",
        color=ACCENT,
    )
    embed.set_footer(text="Clash • Sanidade • Moedas • Efeitos")
    await interaction.response.send_message(embed=embed, view=PanelView())


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
    await interaction.response.send_message(embed=character_embed(row, jogador))


@personagem.command(name="niveis", description="Mestre: define Offense e Defense Level")
@app_commands.checks.has_permissions(manage_guild=True)
async def personagem_niveis(interaction: discord.Interaction, jogador: discord.Member, offense: int, defense: int) -> None:
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
    await interaction.response.send_message(embed=character_embed(row, jogador))


@personagem.command(name="efeitos", description="Mestre: adiciona Paralisia e Power Up/Down")
@app_commands.checks.has_permissions(manage_guild=True)
async def personagem_efeitos(
    interaction: discord.Interaction, jogador: discord.Member,
    paralisia: int = 0, base_power: int = 0, coin_power: int = 0,
) -> None:
    row = db.add_effects(gid(interaction), jogador.id, paralisia, base_power, coin_power)
    if row is None:
        await interaction.response.send_message("Esse jogador ainda não criou uma ficha.", ephemeral=True)
        return
    await interaction.response.send_message(embed=character_embed(row, jogador))


@skill_group.command(name="criar", description="Cria ou substitui uma skill")
@app_commands.choices(tipo_nivel=[app_commands.Choice(name="Ofensivo", value="offense"), app_commands.Choice(name="Defensivo", value="defense")])
async def skill_criar(
    interaction: discord.Interaction, nome: str, poder_base: int, poder_moeda: int,
    moedas: app_commands.Range[int, 1, 10], tipo_nivel: app_commands.Choice[str], descricao: str = "",
) -> None:
    if db.get_character(gid(interaction), interaction.user.id) is None:
        await interaction.response.send_message("Crie sua ficha primeiro.", ephemeral=True)
        return
    skill = Skill(nome[:50], poder_base, poder_moeda, moedas, descricao[:300], tipo_nivel.value)
    db.save_skill(interaction.guild_id, interaction.user.id, skill)
    await interaction.response.send_message(embed=skills_embed([skill], "Skill salva"))


@skill_group.command(name="listar", description="Lista as skills de um jogador")
async def skill_listar(interaction: discord.Interaction, jogador: discord.Member | None = None) -> None:
    jogador = jogador or interaction.user
    await interaction.response.send_message(embed=skills_embed(db.list_skills(gid(interaction), jogador.id), f"Skills de {jogador.display_name}"))


@bot.tree.command(name="clash", description="Resolve um Clash entre dois jogadores")
async def clash(interaction: discord.Interaction, oponente: discord.Member, sua_skill: str, skill_oponente: str) -> None:
    server = gid(interaction)
    lc, rc = db.get_character(server, interaction.user.id), db.get_character(server, oponente.id)
    left = db.get_skill(server, interaction.user.id, sua_skill)
    right = db.get_skill(server, oponente.id, skill_oponente)
    if not all((lc, rc, left, right)):
        await interaction.response.send_message("Não encontrei uma ficha ou skill. Confira `/skill listar`.", ephemeral=True)
        return
    left_level = lc["offense_level"] if left.level_type == "offense" else lc["defense_level"]
    right_level = rc["offense_level"] if right.level_type == "offense" else rc["defense_level"]
    lm = Modifiers(lc["base_power_mod"], lc["coin_power_mod"], lc["paralysis"], left_level)
    rm = Modifiers(rc["base_power_mod"], rc["coin_power_mod"], rc["paralysis"], right_level)
    result = resolve_clash(left, lc["sp"], right, rc["sp"], left_modifiers=lm, right_modifiers=rm)
    db.consume_clash_effects(server, interaction.user.id, result.left_paralysis)
    db.consume_clash_effects(server, oponente.id, result.right_paralysis)
    winner = lc["name"] if result.winner == "left" else rc["name"]
    winner_id, loser_id = ((interaction.user.id, oponente.id) if result.winner == "left" else (oponente.id, interaction.user.id))
    db.change_sp(server, winner_id, 10)
    db.change_sp(server, loser_id, -5)

    embed = discord.Embed(title="⚔️ Resultado do Clash", color=discord.Color.gold())
    embed.description = f"**{lc['name']}** • {left.name}  **VS**  **{rc['name']}** • {right.name}"
    lines = []
    for rd in result.rounds[:15]:
        arrow = {"left": "⬅️", "right": "➡️", "tie": "🔁"}[rd.result]
        lines.append(f"`R{rd.number:02}`  `{rd.left.face_text}` **{rd.left.power}**  {arrow}  **{rd.right.power}** `{rd.right.face_text}`")
    if len(result.rounds) > 15:
        lines.append(f"… mais {len(result.rounds) - 15} rodadas")
    embed.add_field(name="Rolagens", value="\n".join(lines), inline=False)
    embed.add_field(name="🏆 Vencedor", value=f"**{winner}**", inline=True)
    embed.add_field(name="Moedas restantes", value=str(result.left_coins if result.winner == "left" else result.right_coins), inline=True)
    embed.add_field(name="Sanidade", value="Vencedor **+10** • Perdedor **−5**", inline=False)
    embed.set_footer(text=f"Níveis usados: {left_level} vs {right_level} • efeitos temporários consumidos")
    await interaction.response.send_message(embed=embed)


@bot.tree.error
async def tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    message = "O comando falhou. Confira os valores informados."
    if isinstance(error, app_commands.MissingPermissions):
        message = "Apenas alguém com permissão de gerenciar o servidor pode fazer isso."
    elif isinstance(error, app_commands.CheckFailure):
        message = str(error)
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    await sender(message, ephemeral=True)


bot.tree.add_command(personagem)
bot.tree.add_command(skill_group)

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env.")
    bot.run(TOKEN)
