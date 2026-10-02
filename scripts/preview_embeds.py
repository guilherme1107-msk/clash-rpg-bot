"""Renderiza os embeds reais do bot em HTML e texto, usando um banco temporário.

Uso:  .venv\\Scripts\\python.exe scripts\\preview_embeds.py

Nada aqui envia mensagem ao Discord: o script apenas instancia os mesmos
``discord.Embed`` que ``bot.py`` publica e desenha o resultado.
"""

from __future__ import annotations

import html
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Banco descartável: o preview nunca toca no clash_rpg.sqlite3 real.
_TMP_DB = Path(tempfile.gettempdir()) / "clashbot_embed_preview.sqlite3"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_PATH"] = str(_TMP_DB)
os.environ.setdefault("DISCORD_TOKEN", "preview-only-not-a-real-token")

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import (  # noqa: E402
    Modifiers, Skill, SkillEffect, estimate_clash, resolve_damage,
)

GUILD = 1_000_000_000_000_001
ME = 555_000_000_000_001
RIVAL = 555_000_000_000_002


class FakeUser:
    """Mock mínimo de discord.abc.User (mention + avatar)."""

    def __init__(self, uid: int, name: str) -> None:
        self.id = uid
        self.mention = f"<@{uid}>"
        self.display_name = name
        self.display_avatar = type(
            "A", (), {"url": "https://cdn.discordapp.com/embed/avatars/0.png"}
        )()

    def __str__(self) -> str:
        return self.display_name


# --------------------------------------------------------------------------
# Semente do banco
# --------------------------------------------------------------------------
def seed() -> tuple:
    db = B.db
    db.setup()

    db.create_character(GUILD, ME, "Yi Sang")
    db.connection.execute(
        "UPDATE characters SET sp=-20, offense_level=4, defense_level=3, "
        "paralysis=2, base_power_mod=3, clash_power_mod=-2 WHERE guild_id=? AND user_id=?",
        (GUILD, ME),
    )
    db.add_status(GUILD, "player", ME, "bleed", 4, 3)
    db.add_status(GUILD, "player", ME, "burn", 2, 2)
    db.add_status(GUILD, "player", ME, "tremor", 3, 1)
    db.save_appearance(
        GUILD, "player", ME, "https://example.invalid/ysang.png", "#2f6f5f",
        "Lótus do Corvo", footer_text="Lotus // turno 04",
    )

    db.create_character(GUILD, RIVAL, "Faust")
    db.connection.execute(
        "UPDATE characters SET sp=15, offense_level=2, defense_level=5 WHERE guild_id=? AND user_id=?",
        (GUILD, RIVAL),
    )

    enemy = db.save_enemy(GUILD, ME, "Cavaleiro Aberrante", -10, 3, 2)
    db.add_status(GUILD, "enemy", enemy["id"], "bleed", 2, 4)
    db.add_status(GUILD, "enemy", enemy["id"], "rupture", 5, 1)
    db.save_appearance(
        GUILD, "enemy", enemy["id"], "https://example.invalid/knight.png", "#6b3f2f",
        "Sentinela do Portão", footer_text="Bestiary // registro 12",
    )

    slash = Skill(
        "Corte Ascendente", 14, 6, 3, "Gola ascendente.", "attack",
        effects=(
            SkillEffect("on_hit", "bleed", 3, count=2),
            SkillEffect("heads_hit", "clash_power", 4),
        ),
    )
    backstep = Skill("Recuo Calculado", 9, -3, 2, "Afasta-se da lâmina.", "guard")
    db.save_enemy_skill(enemy["id"], slash)
    db.save_enemy_skill(enemy["id"], backstep)

    return db.get_character(GUILD, ME), db.get_enemy(GUILD, "Cavaleiro Aberrante")


# --------------------------------------------------------------------------
# Renderização
# --------------------------------------------------------------------------
def md_to_html(text: str) -> str:
    """Conversão mínima da marcação que o projeto usa nos embeds."""
    out = html.escape(text or "")
    out = out.replace("&amp;lt;", "&lt;").replace("&amp;gt;", "&gt;")
    out = out.replace("&lt;@", "").replace("&gt;", "")
    out = out.replace("", '<span class="mention">@user</span>')
    out = out.replace("", "</span>")
    out = out.replace("`", "")
    # ```\n ... ```  -> bloco de código
    out = out.replace("``````", "")
    out = out.replace("``````", "")
    import re
    out = re.sub(
        r"```\n?(.*?)```",
        lambda m: '<span class="code">' + m.group(1) + "</span>",
        out,
        flags=re.S,
    )
    out = re.sub(r"~~(.+?)~~", r'<s>\1</s>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"^#{1,3}\s*(.+)$", r'<div class="big">\1</div>', out, flags=re.M)
    return out.replace("\n", "<br>")


def embed_to_html(embed: discord.Embed) -> str:
    color = f"#{embed.colour.value:06x}"
    parts = [
        f'<div class="grid" style="border-left-color:{color}">',
        f'<div class="accent" style="background:{color}"></div>',
        '<div class="body">',
    ]
    if embed.author:
        parts.append(f'<div class="author">{md_to_html(embed.author.name)}</div>')
    if embed.title:
        parts.append(f'<div class="title">{md_to_html(embed.title)}</div>')
    if embed.thumbnail:
        url = embed.thumbnail.url or "(sem URL)"
        parts.append(f'<img class="thumb" src="{html.escape(url)}">')
    if embed.description:
        parts.append(f'<div class="desc">{md_to_html(embed.description)}</div>')

    if embed.fields:
        parts.append('<div class="fields">')
        for f in embed.fields:
            if f.inline:
                parts.append(
                    f'<div class="field inline"><div class="fname">{md_to_html(f.name)}</div>'
                    f'<div class="fval">{md_to_html(f.value)}</div></div>'
                )
            else:
                parts.append(
                    f'<div class="field"><div class="fname">{md_to_html(f.name)}</div>'
                    f'<div class="fval">{md_to_html(f.value)}</div></div>'
                )
        parts.append("</div>")

    if embed.image:
        parts.append(
            f'<div class="imgnote">🖼 imagem: {html.escape(embed.image.url or "(sem URL)")}</div>'
        )
    if embed.footer and embed.footer.text:
        parts.append(f'<div class="footer">{md_to_html(embed.footer.text)}</div>')
    parts.append("</div></div>")
    return "\n".join(parts)


def embed_to_text(embed: discord.Embed) -> str:
    bar = "#" * 74
    out = [bar, f"TITLE    : {embed.title}", f"COLOR    : #{embed.colour.value:06x}"]
    if embed.author:
        out.append(f"AUTHOR   : {embed.author.name}")
    if embed.description:
        out.append(f"DESCRIPTION:\n{indent(embed.description)}")
    if embed.fields:
        out.append("FIELDS:")
        for f in embed.fields:
            tag = "inline" if f.inline else "block "
            out.append(f"  [{tag}] {f.name}")
            out.append(indent(f.value, 6))
    if embed.image:
        out.append(f"IMAGE    : {embed.image.url}")
    if embed.thumbnail:
        out.append(f"THUMBNAIL: {embed.thumbnail.url}")
    if embed.footer and embed.footer.text:
        out.append(f"FOOTER   : {embed.footer.text}")
    out.append(f"[{len(embed)} chars / {len(embed.fields)} fields]")
    out.append(bar)
    return "\n".join(out)


def indent(text: str, size: int = 4) -> str:
    pad = " " * size
    return "\n".join(pad + line for line in (text or "").splitlines())


# --------------------------------------------------------------------------
# Catálogo
# --------------------------------------------------------------------------
def build_catalog(character, enemy) -> list[tuple[str, str, discord.Embed]]:
    """Devolve (rótulo, origem no bot.py, embed)."""
    me = FakeUser(ME, "Yi Sang")
    rng = random.Random(7)
    items: list[tuple[str, str, discord.Embed]] = []

    slash = Skill(
        "Corte Ascendente", 14, 6, 3, "Gola ascendente.", "attack",
        effects=(SkillEffect("on_hit", "bleed", 3, count=2),),
    )
    riposte = Skill("Riposte Punida", 11, 4, 2, "", "counter")
    armor = Skill("Guarda de Aço", 12, 0, 2, "", "clashable_guard")

    # --- combate ---
    result = resolve_damage(
        slash, -20, 3, 4, 3,
        modifiers=Modifiers(base_power=3, coin_power=2, level=0, clash_power=-2),
        faces=[True, False, True],
    )
    items.append((
        "Dano — clash_guild / damage_embed",
        "bot.py:1285",
        B.damage_embed("Yi Sang", "Cavaleiro Aberrante", slash, result, shield=4),
    ))
    items.append((
        "Dano — sem escudo, follow-up inquebrável",
        "bot.py:1285",
        B.damage_embed("Yi Sang", "Cavaleiro Aberrante", slash, result, unbreakable_followup=True),
    ))
    items.append((
        "Clashable Guard — vitória",
        "bot.py:1340",
        B.clashable_guard_win_embed("Faust", "Yi Sang", 27),
    ))

    forecast = estimate_clash(slash, -20, riposte, 15, rng=rng, simulations=400)
    items.append((
        "Previsão — prediction_embed",
        "bot.py:1417",
        B.prediction_embed("Yi Sang", slash, "Cavaleiro Aberrante", riposte, forecast, None),
    ))

    from src.domain.models import AttackHit, DamageResult
    burn_events = [
        ("player", ME, B.CombatStatusLike("bleed", 4, 3, 6)) if hasattr(B, "CombatStatusLike")
        else ("enemy", enemy["id"], type("E", (), {"status_type": "bleed", "damage": 6, "count_after": 3})()),
        ("player", ME, type("E", (), {"status_type": "burn", "damage": 9, "count_after": 1})()),
    ]
    status_embed = B.round_status_embed(GUILD, burn_events)
    if status_embed is not None:
        items.append(("Status — round_status_embed", "bot.py:1226", status_embed))

    # --- clash em fila ---
    rounds = [
        {"number": 1, "left_power": 26, "right_power": 19, "result": "left",
         "left_faces": [True, True, False], "right_faces": [False, False, True]},
        {"number": 2, "left_power": 21, "right_power": 24, "result": "right",
         "left_faces": [False, True, False], "right_faces": [True, True, True]},
        {"number": 3, "left_power": 30, "right_power": 22, "result": "left",
         "left_faces": [True, True, True], "right_faces": [False, True, False]},
    ]
    queued = {
        "left_name": "Yi Sang", "right_name": "Cavaleiro Aberrante",
        "left_skill": "Corte Ascendente", "right_skill": "Riposte Punida",
        "left_base": 14, "left_base_mod": 3, "left_coin_power": 6, "left_coin_mod": 2,
        "left_clash_mod": -2, "left_range": [14, 32], "left_level": 1, "left_total": 3,
        "right_base": 11, "right_base_mod": 0, "right_coin_power": 4, "right_coin_mod": 0,
        "right_clash_mod": 0, "right_range": [11, 19], "right_level": -1, "right_total": 2,
        "rounds": rounds, "winner_name": "Yi Sang", "damage": 41,
        "left_sp": -15, "right_sp": -5,
        "damage_effects": ["Bleed 2 aplicado • Potência 3 × Quantidade 2",
                           "Shielded 4 absorvidos do valor final"],
        "effects": ["paralysis:1", "clash_power:+4"],
        "forecast_chance": 0.62, "forecast_label": "FAVORED", "forecast_label_pt": "Favorecido",
        "clash_gif": "https://example.invalid/clash.gif",
    }
    items.append((
        "Previsão enfileirada — queued_prediction_embed",
        "bot.py:4712",
        B.queued_prediction_embed(queued),
    ))
    items.append((
        "Clash animando (rodada 2) — queued_clash_embed",
        "bot.py:4733",
        B.queued_clash_embed(queued, 2, finished=False),
    ))
    items.append((
        "Clash concluído — queued_clash_embed",
        "bot.py:4733",
        B.queued_clash_embed(queued, 3, finished=True),
    ))
    items.append((
        "Clash resolvido — clash_result_embed",
        "bot.py:4685",
        B.clash_result_embed({**queued, "turn": 4, "encounter": "Portão Sul", "source": "encounter"}),
    ))
    items.append((
        "Ataque sem opposition — publish_unopposed_attack",
        "bot.py:4960",
        discord.Embed(
            title="〔 ⚔ RESOLUÇÃO DE DANO 〕",
            description="**Yi Sang** concluiu o ataque.",
            color=B.ACCENT,
        ),
    ))

    # --- fichas ---
    items.append(("Ficha do jogador — character_embed", "bot.py:1805", B.character_embed(character, me)))
    items.append((
        "Skills — skills_embed",
        "bot.py:1868",
        B.skills_embed([slash, riposte, armor], "Skills de Yi Sang"),
    ))

    # --- sessão ---
    items.append((
        "Encounter iniciado — combat_encounter_embed",
        "bot.py:2979",
        B.combat_encounter_embed("Portão Sul — Turno 04", me),
    ))

    # --- sentinela / diagnóstico ---
    items.append((
        "Sentinela — resposta de erro",
        "bot.py:4984",
        discord.Embed(
            title="◈ SENTINELA // Trace de Clash",
            description="O autor do painel detectou 2 eventos fora do esperado.",
            color=discord.Color.orange(),
        ),
    ))
    items.append((
        "Sentinela — pergunta",
        "bot.py:5407",
        discord.Embed(
            title="◈ SENTINELA // Consulta",
            description="3 embeds publicaram, 1 foi truncado por limite de 6000 caracteres.",
            color=discord.Color.teal(),
        ),
    ))

    # --- menu ---
    items.append((
        "Menu /painel",
        "bot.py:5438",
        discord.Embed(
            title="⚔️ CLASHBOT // CENTRAL DO DISCORD",
            description=(
                "Este menu cuida das ações que pertencem ao **Discord**. A ficha "
                "completa, os editores, o Encounter visual e o painel do mestre "
                "ficam na **Activity**.\n\n"
                "Use os botões abaixo para consultas rápidas, mensagens de batalha "
                "e recursos que precisam aparecer no canal."
            ),
            color=B.ACCENT,
        ),
    ))

    # --- demonstração da sanificação ---
    giant = discord.Embed(title="T" * 400, description="D" * 5000, color=B.ACCENT)
    for i in range(12):
        giant.add_field(name=f"CAMPO {i}", value="X" * 1500)
    giant.set_footer(text="F" * 3000)
    clean = discord.Embed(title=giant.title, description=giant.description, color=B.ACCENT)
    for f in giant.fields:
        clean.add_field(name=f.name, value=f.value, inline=f.inline)
    clean.set_footer(text=giant.footer.text)

    items.append((
        "sanitize_embed — entrada crua (26486 chars, estourando todos os limites)",
        "bot.py:173",
        giant,
    ))
    items.append((
        "sanitize_embed — depois de sanitize_embed()",
        "bot.py:173",
        B.sanitize_embed(clean),
    ))

    return items


CSS = """
:root { color-scheme: dark; }
body { background:#313338; color:#dbdee1; font:15px/1.5 "gg sans","Segoe UI",system-ui,sans-serif;
       margin:0; padding:32px 24px 80px; }
h1 { color:#f2f3f5; font-size:24px; margin:0 0 4px; }
p.sub { color:#949ba4; margin:0 0 28px; }
h2 { color:#f2f3f5; font-size:16px; margin:0 0 10px; }
.src { color:#949ba4; font:12px ui-monospace,Consolas,monospace; margin:0 0 8px; }
.card { max-width:560px; margin:0 0 30px; }
.grid { display:flex; gap:12px; background:#2b2d31; border-radius:8px; padding:12px 0;
        border-left:4px solid #888; overflow:hidden; }
.grid > .accent { display:none; }
.body { padding:2px 16px 2px 12px; min-width:0; flex:1; }
.title { color:#fff; font-weight:700; font-size:16px; margin-bottom:6px; }
.author { color:#b5bac1; font-size:12px; margin-bottom:4px; }
.desc { color:#dbdee1; font-size:15px; margin:4px 0 8px; }
.big { font-size:20px; font-weight:700; color:#fff; margin:6px 0; }
.fields { display:flex; flex-wrap:wrap; gap:8px 8px; margin:6px 0; }
.field { box-sizing:border-box; width:100%; min-width:0; }
.field.inline { width:calc(50% - 4px); }
.field.inline:nth-child(odd):only-child { width:100%; }
.fname { color:#fff; font-weight:600; font-size:14px; margin-bottom:2px; }
.fval { color:#dbdee1; font-size:14px; }
.code { display:block; background:#1e1f22; border:1px solid #2b2d31; border-radius:4px;
        padding:2px 6px; margin:2px 0; font:13px ui-monospace,Consolas,monospace;
        color:#b5bac1; white-space:pre-wrap; }
.footer { color:#949ba4; font-size:12px; margin-top:10px; }
.imgnote { color:#6d6f78; font-size:12px; margin-top:8px; }
.mention { background:#5865f2; color:#fff; border-radius:4px; padding:0 3px; font-size:13px; }
.text { white-space:pre; color:#c9d1d9; font:12px ui-monospace,Consolas,monospace;
        background:#1e1f22; padding:14px; border-radius:6px; overflow:auto; }
.text h2 { margin-top:0; }
"""


def main() -> None:
    character, enemy = seed()
    catalog = build_catalog(character, enemy)

    out_dir = ROOT / "scripts"
    html_path = out_dir / "preview_embeds.html"
    txt_path = out_dir / "preview_embeds.txt"

    cards = [
        f'<div class="card"><h2>{html.escape(label)}</h2>'
        f'<p class="src">{html.escape(source)}</p>{embed_to_html(embed)}</div>'
        for label, source, embed in catalog
    ]
    html_path.write_text(
        "<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>"
        "<title>Preview dos embeds do ClashBot</title>"
        f"<style>{CSS}</style></head><body>"
        "<h1>Embeds do ClashBot</h1>"
        "<p class=sub>Instanciados a partir de <code>bot.py</code> com discord.py 2.5.2 "
        "e um banco temporário. Nada foi enviado ao Discord.</p>"
        + "\n".join(cards)
        + "</body></html>",
        encoding="utf-8",
    )

    blocks = []
    for label, source, embed in catalog:
        blocks.append(f"{label}\n({source})\n\n{embed_to_text(embed)}\n")
    txt_path.write_text("\n".join(blocks), encoding="utf-8")

    print(f"{len(catalog)} embeds renderizados")
    print(html_path)
    print(txt_path)


if __name__ == "__main__":
    main()
