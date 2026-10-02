"""E.G.O Gifts: candidatos que são REAIS no engine e legíveis no embed.

O que a inspeção mostrou sobre o estado atual:

* As 5 colunas numéricas (base/coin/clash/offense/defense_level_mod) já estão
  ligadas ao combate em ``clash_execution.py:80-83``. Ou seja, um gift com
  números funciona hoje, sem tocar no motor.
* Os 3 gifts da Rosemary (Tier V) foram criados com **todos os mods zerados**
  e ``effects_json = '[]'``. Eles não alteram nada.
* ``ego_gifts.effects_json`` é gravado por ``save_ego_gift`` mas nunca lido
  por nenhum cálculo: gift condicional exigiria código.
* ``has_carousel`` (bot.py:558) é lido e nunca usado: código morto.
* Só "The Family's Resentment" tem mecânica, via comparação de NOME em
  bot.py:562-567.

E o problema de design que isso expõe: ``get_total_ego_gift_modifiers`` SOMA
todos os gifts ativos, sem teto e sem orçamento. Se os gifts só somam, o
jogador toma +5 em tudo e a escolha não existe. O espaço interessante só
aparece com trade-off dentro do próprio gift.

Uso:  .venv\\Scripts\\python.exe scripts\\preview_gifts.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_gifts.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "gifts-only")

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import Modifiers, Skill, SkillEffect, prediction_with_paralysis  # noqa: E402
from src.domain.models import Forecast  # noqa: E402

ACCENT, GOLD = B.ACCENT, B.GOLD

# As 5 colunas numéricas, com o ícone que o bot.py já usa na ficha.
AXES = [
    ("bpm", "Base Power", B.EFFECT_ATTACK_UP, B.EFFECT_ATTACK_DOWN),
    ("cpm", "Coin Power", B.EFFECT_PLUS_COIN_BOOST, B.EFFECT_PLUS_COIN_DROP),
    ("clpm", "Clash Power", B.EFFECT_CLASH_UP, B.EFFECT_CLASH_DOWN),
    ("olm", "Offense Level", B.EFFECT_OFFENSE_UP, B.EFFECT_OFFENSE_DOWN),
    ("dlm", "Defense Level", None, None),  # Defense usa 🔺/🔻 no bot.py
]


# ═══════════════════════════════════════════════════════════════════
#  Candidatos
# ═══════════════════════════════════════════════════════════════════
GIFTS = [
    {
        "name": "Cornerstone of Quiet",
        "tier": 1,
        "mods": {"dlm": 1},
        "desc": "Uma pedra que não pede nada. Quem a carrega aguenta mais um golpe.",
        "papel": "Eixo único de defesa. O gift que todo mundo aceita sem pensar.",
    },
    {
        "name": "Second-Hand Harmonium",
        "tier": 3,
        "mods": {"clpm": 3, "cpm": -1},
        "desc": "Afinação imperfeita: ganha na disputa direta, perde na escala das moedas.",
        "papel": "A diagonal ⚡+3 / 💰−1. Compensa Clash, não vai bem com Coin.",
    },
    {
        "name": "Widow's Lace",
        "tier": 4,
        "mods": {"dlm": 2, "bpm": 1},
        "desc": "Fita que aperta antes de proteger. O escudo vem com um preço pequeno.",
        "papel": "Quase positiva, mas paga em Base Power. Bom para quem defende e revida.",
    },
    {
        "name": "Ahab's Blind Rage",
        "tier": 5,
        "mods": {"olm": 3, "dlm": -2},
        "desc": "Persegue até o fim. Não sabe recuar.",
        "papel": "O mais legível do lote: 🔺+3 e 🔻−2 no MESMO par de ícones.",
    },
    {
        "name": "The Weight of a Promise",
        "tier": 5,
        "mods": {"cpm": 4},
        "desc": "Cada moeda pesa mais. Número grande, previsível, fácil de planejar.",
        "papel": "O oposto do Ahab: um número só, grande. Bom para quem quer saber o valor antes.",
    },
    {
        "name": "Sleeve of the Second Hand",
        "tier": 2,
        "mods": {"bpm": 2, "clpm": 1},
        "desc": "Punho colado, timing torto. Garante a base e ajuda a fechar a rodada.",
        "papel": "A dobradiça ⚔+2 / ⚡+1. Sustenta o começo e o fim da rolagem.",
    },
]


# ═══════════════════════════════════════════════════════════════════
#  Renderização no embed
# ═══════════════════════════════════════════════════════════════════
def mod_icons(mods: dict) -> str:
    """Usa exatamente os ícones que o bot.py já aplica na ficha."""
    parts = []
    for key, label, up, down in AXES:
        value = int(mods.get(key, 0))
        if not value:
            continue
        if key == "dlm":
            # O bot.py usa 🔺/🔻 colado no ícone de Defense; aqui o texto
            # impede que a linha vire um ícone solto sem legenda.
            arrow = "🔺" if value > 0 else "🔻"
            parts.append(f"{B.DEFENSE_LEVEL_ICON}{arrow} **{value:+d}** {label}")
            continue
        icon = B.effect_icon(value, up, down)
        parts.append(f"{icon} **{value:+d}** {label}")
    return "  ".join(parts) or "`NENHUM MODIFICADOR`"


def total_mods(gifts: list[dict]) -> dict:
    total = {key: 0 for key, _, _, _ in AXES}
    for gift in gifts:
        for key, value in gift["mods"].items():
            total[key] += value
    return total


def gift_block(embed: discord.Embed, gifts: list[dict]) -> discord.Embed:
    """Bloco de gifts: uma linha por gift, com a contributions individual."""
    lines = []
    for gift in sorted(gifts, key=lambda g: (-g["tier"], g["name"])):
        stars = "★" * gift["tier"]
        lines.append(
            f"`T{gift['tier']}` **{gift['name']}** {stars}\n"
            f"　{mod_icons(gift['mods'])}"
        )
    embed.add_field(
        name=f"◈ E.G.O GIFTS // {len(gifts)} ATIVO(S)",
        value="\n".join(lines),
        inline=False,
    )
    total = total_mods(gifts)
    embed.add_field(
        name="◈ SOMA QUE ENTRA NO CLASH",
        value=f"{mod_icons(total)}",
        inline=False,
    )
    return embed


# ═══════════════════════════════════════════════════════════════════
#  Prova de que o trade-off importa
# ═══════════════════════════════════════════════════════════════════
def forecast_with(attacker_gifts, defender_gifts, attacker: Skill, defender: Skill) -> Forecast:
    a, d = total_mods(attacker_gifts), total_mods(defender_gifts)
    am = Modifiers(a["bpm"], a["cpm"], 0, a["olm"], a["clpm"])
    dm = Modifiers(d["bpm"], d["cpm"], 0, d["olm"], d["clpm"])
    return prediction_with_paralysis(attacker, 0, defender, 0, am, dm)


def build_loadouts() -> list[tuple[str, str, list[dict]]]:
    by_name = {g["name"]: g for g in GIFTS}
    return [
        (
            "Loadout 1 — só positivos",
            "Se os gifts só somam e não há teto, este é o dominante: pega tudo. "
            "Nenhum downside, nenhuma decisão.",
            [by_name[n] for n in ("Cornerstone of Quiet", "Sleeve of the Second Hand",
                                  "The Weight of a Promise")],
        ),
        (
            "Loadout 2 — Clash + casca",
            "Troca Coin Power por Clash Power e aceita um pouco de Base. "
            "Ganha a disputa, perde na escala.",
            [by_name[n] for n in ("Second-Hand Harmonium", "Widow's Lace",
                                  "Cornerstone of Quiet")],
        ),
        (
            "Loadout 3 — canhão de vidro",
            "Abaixa a própria defesa em troca de Offense Level. Só faz sentido "
            "se o alvo não sobreviver ao primeiro golpe.",
            [by_name[n] for n in ("Ahab's Blind Rage", "The Weight of a Promise")],
        ),
    ]


def main() -> None:
    attacker = Skill("Corte Ascendente", 14, 6, 3, "", "attack")
    defender = Skill("Riposte Punida", 11, 4, 2, "", "counter")

    catalog: list[tuple[str, str, discord.Embed]] = []

    # 1. O bloco de gifts como apareceria na ficha.
    e = discord.Embed(title="〔 LCB // REGISTRO DE SINNER 〕", color=ACCENT)
    e.description = "## Fiore\n`IDENTIDADE VINCULADA: Fiore`"
    e.add_field(name="◈ SANIDADE", value="```+0 SP\n50% HEADS```")
    e.add_field(name="◆ OFFENSE LEVEL", value="```0```")
    e.add_field(name="◇ DEFENSE LEVEL", value="```0```")
    gift_block(e, [g for g in GIFTS if g["name"] in (
        "Ahab's Blind Rage", "Second-Hand Harmonium", "Cornerstone of Quiet")])
    e.set_footer(text="LIMBUS // gift soma com status e efeitos temporários no mesmo Clash")
    catalog.append((
        "Bloco de E.G.O Gifts na ficha",
        "A ficha já soma gift + status no mesmo campo de modificadores, e o "
        "mestre não consegue dizer de onde veio cada ponto. O gift é a única "
        "fonte permanente: vale mostrar separado.",
        e,
    ))

    # 2. O catálogo de candidatos, um campo por gift.
    e2 = discord.Embed(title="【 CATÁLOGO // E.G.O GIFTS 】", color=GOLD)
    e2.description = "## Candidatos para o roster\nCada linha é a silhueta que o olho lê"
    for gift in sorted(GIFTS, key=lambda g: -g["tier"]):
        e2.add_field(
            name=f"`T{gift['tier']}` {'★' * gift['tier']} {gift['name']}",
            value=f"{mod_icons(gift['mods'])}\n*{gift['papel']}*",
            inline=False,
        )
    e2.set_footer(text="T rola, ★ é a legenda; mods somam sem teto — por isso o trade-off está dentro de cada gift")
    catalog.append((
        "Catálogo: a silhueta de cada gift",
        "Nada aqui precisa de código novo: as 5 colunas já entram no Clash. "
        "O que muda é a leitura — o par de ícones já diz o que o gift faz.",
        e2,
    ))

    # 3. Três loadouts lado a lado, com a consequência no forecast.
    for label, why, gifts in build_loadouts():
        e3 = discord.Embed(title="〔 PROVA DE TRADE-OFF 〕", color=ACCENT)
        e3.description = f"## {label}"
        gift_block(e3, gifts)
        mine = forecast_with(gifts, [], attacker, defender)
        theirs = forecast_with([], gifts, attacker, defender)
        e3.add_field(
            name="◈ CONSEQUÊNCIA NO PRONÓSTICO",
            value=(
                f"Com estes gifts: **{mine.win_chance:.0%}** `{mine.label}`\n"
                f"Contra estes gifts: **{theirs.win_chance:.0%}** `{theirs.label}`\n"
                f"Mesma skill, mesmo par: o equipment decide a previsão."
            ),
            inline=False,
        )
        e3.set_footer(text=why)
        catalog.append((f"Loadout — {label.lower()}", why, e3))

    # 4. O caso que o motor ainda não cobre.
    e4 = discord.Embed(title="〔 O QUE PRECISA DE CÓDIGO 〕", color=discord.Color.orange())
    e4.description = (
        "## Conditional gift\n"
        "`ego_gifts.effects_json` já existe no schema e é gravado por "
        "`save_ego_gift`, mas nenhum cálculo o lê."
    )
    e4.add_field(
        name="EXEMPLO",
        value=(
            "**Wound That Remembers**\n"
            "`Ao vencer Clash: +1 Coin Power permanente para o resto do turno`\n\n"
            "Não cabe em coluna numérica porque depende do resultado. "
            "Precisaria de um hook como o de `The Family's Resentment` "
            "(bot.py:562), e esse hook hoje é uma comparação de nome."
        ),
        inline=False,
    )
    e4.add_field(
        name="◇ O QUE JÁ EXISTE PARA COPIAR",
        value=(
            "`The Family's Resentment` — cura 30% do dano, máx 20 (bot.py:562-567)\n"
            "`has_carousel` — lido em bot.py:558 e nunca usado: código morto"
        ),
        inline=False,
    )
    e4.set_footer(text="Trace DIAG // o que o motor não faz ainda")
    catalog.append((
        "O limite: gift condicional",
        "Vale registrar porque é o gift mais interessante da lista e também o "
        "único que o schema sozinho não entrega. Ele já tem coluna, falta leitura.",
        e4,
    ))

    # render
    sys.path.insert(0, str(ROOT / "scripts"))
    from preview_concepts import CSS, to_html, to_text  # reusa o renderizador

    blocks = [f"{label}\n{why}\n\n{to_text(embed)}\n" for label, why, embed in catalog]
    (ROOT / "scripts" / "preview_gifts.txt").write_text("\n".join(blocks), encoding="utf-8")
    import html as _html
    cards = "".join(
        f'<div class="card"><h2>{_html.escape(label)}</h2>'
        f'<p class="gap">{_html.escape(why)}</p>{to_html(embed)}</div>'
        for label, why, embed in catalog
    )
    (ROOT / "scripts" / "preview_gifts.html").write_text(
        "<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>"
        "<title>E.G.O Gifts</title><style>" + CSS + "</style></head><body>"
        "<h1>E.G.O Gifts: candidatos reais</h1>"
        "<p class=sub>As 5 colunas numéricas já entram no Clash em "
        "<code>clash_execution.py:80-83</code>. Estes candidatos não exigem "
        "motor novo — só números, que o bot.py já soma na ficha.</p>"
        + cards + "</body></html>",
        encoding="utf-8",
    )
    print(f"{len(catalog)} exemplos de gifts")
    print(ROOT / "scripts" / "preview_gifts.html")


if __name__ == "__main__":
    main()
