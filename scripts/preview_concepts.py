"""Galeria de conceitos: decorações de embed que carregam informação.

Escopo acordado com o autor do projeto:

* A curva de prognóstico foi DESCARTADA. ``estimate_clash`` precisa ser
  barato; rodar milhares de simulações só para desenhar um histograma
  não compensa.
* O pulso de HP foi DESCARTADO. O HP é alterado por fora do bot, então
  qualquer número que o embed mostrasse ficaria desatualizado e
  mentindo para o mestre.

Ficam cinco conceitos, cada um ancorado numa lacuna real do embed atual.
Regra: se a decoração não muda a decisão do mestre, ela não entra.

Uso:  .venv\\Scripts\\python.exe scripts\\preview_concepts.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_concepts.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "concepts-only")

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import (  # noqa: E402
    Modifiers, Skill, SkillEffect, apply_damage_percentage, resolve_damage,
)
from src.domain.models import heads_chance  # noqa: E402

ACCENT, GOLD = B.ACCENT, B.GOLD
WIDTH = 12


# ═══════════════════════════════════════════════════════════════════
# 1. COMPOSIÇÃO DO DANO
#    Lacuna: damage_embed mostra subtotal → nível → % → escudo em
#    campos separados. O mestre não vê qual etapa COMEU o dano, e as
#    etapas intermediárias somem — 33 moedas + 6 de nível viram 39
#    num único número, sem rastro.
#    Fonte: percent_modifier e damage_before_percent do próprio engine.
# ═══════════════════════════════════════════════════════════════════
def damage_composition(embed: discord.Embed, result, *, shield: int = 0) -> discord.Embed:
    """Anexa a trilha de etapas ao embed de dano já existente."""
    # Etapa 1: as moedas. subtotal já é a soma das faces.
    coins = result.subtotal
    # Etapa 2: o ajuste de nível. O engine aplica o level_modifier como
    # dano direto, não como multiplicador.
    level = result.level_modifier
    after_level = result.damage_before_percent  # subtotal + level_modifier, já com piso 0
    # Etapa 3: o percentual. percent_modifier é o valor do engine.
    percent = result.percent_modifier
    after_percent = result.final_damage
    # Etapa 4: o escudo, que pertence ao turno da defesa, não ao golpe.
    shield_delta = -shield if shield else 0
    shown = max(0, after_percent - shield)

    steps = [
        ("Moedas", coins),
        ("Nível", after_level - coins),
        ("% Dano", after_percent - after_level),
        ("Escudo", shield_delta),
    ]
    span = max([abs(v) for _, v in steps] + [1])
    lines = []
    for label, delta in steps:
        sign = "+" if delta >= 0 else "−" if delta < 0 else "±"
        filled = round(abs(delta) / span * WIDTH)
        bar = "▰" * filled + "▱" * (WIDTH - filled)
        # Etapa neutra fica apagada: é melhor ver "não houve" do que um zero indistinto.
        tone = "**" if delta else "_"
        lines.append(f"`{bar}` {tone}{sign}{abs(delta)}{tone}  {label}")

    embed.add_field(name="◈ DE ONDE VEIO O DANO", value="\n".join(lines), inline=False)

    chain = " → ".join(f"`{v}`" for v in (coins, after_level, after_percent, shown))
    label = (
        f"**{result.damage_percent:+g}%** skill"
        if result.damage_percent else "`sem` modificador percentual"
    )
    embed.add_field(
        name="CADEIA",
        value=f"{chain}\n{label}",
        inline=False,
    )
    return embed


# ═══════════════════════════════════════════════════════════════════
# 2. ESCADA DE STATUS
#    Lacuna: "Potência 4 • Quantidade 3" em texto. Com quatro status
#    ativos o mestre perde a conta do que ainda resta, e não há
#    leitura de "quanto tempo isto ainda dura".
# ═══════════════════════════════════════════════════════════════════
def status_ladder(embed: discord.Embed, statuses) -> discord.Embed:
    """statuses: iterable de (tipo, potência, quantidade)."""
    for status_type, potency, count in statuses:
        icon = B.STATUS_ICONS.get(status_type, "❔")
        label = B.STATUS_LABELS.get(status_type, status_type.title())
        if potency <= 0 or count <= 0:
            # Expirado continua visível: some a pilha mas o mestre precisa
            # ver que ela existiu, senão parece bug.
            embed.add_field(
                name=f"{icon} {label}",
                value="`········` **expirado** — a pilha zerou neste turno",
                inline=False,
            )
            continue
        filled = min(8, potency)
        row = "▰" * filled + "·" * (8 - filled)
        plural = "aplicação" if count == 1 else "aplicações"
        turnos = "turno" if count == 1 else "turnos"
        embed.add_field(
            name=f"{icon} {label}",
            value=(
                f"`{row}` `potência {filled}` de 8\n"
                f"└ `{count}` {plural} • dura `{count}` {turnos} de status"
            ),
            inline=False,
        )
    return embed


# ═══════════════════════════════════════════════════════════════════
# 3. TERMÔMETRO DE SANIDADE
#    Lacuna: character_embed escreve "+20 SP / 70% HEADS" num code
#    block. Não dá para ver onde a ficha está no intervalo −45..+45,
#    nem comparar duas fichas de relance.
# ═══════════════════════════════════════════════════════════════════
HALF = 20  # largura de cada semi-eixo


def sanity_gauge(sp: int) -> str:
    """Barra ancorada no zero, escala −45..+45, agulha na posição."""
    span = HALF * 2 + 1
    # tons distintos por semi-eixo: ▁ é cauda, █ é head
    cells = ["▁" if i < HALF else "█" for i in range(span)]
    pos = max(-HALF, min(HALF, round(sp / 45 * HALF)))
    cells[HALF + pos] = "◀" if pos < 0 else "▶" if pos > 0 else "◆"
    return "".join(cells)


def sanity_scale() -> str:
    cells = ["▁"] * HALF + ["█"] * (HALF + 1)
    bar = "".join(cells)
    return (
        f"`{bar}`\n"
        "`−45` ◀ zero ▶ `+45`\n"
        "▁ cauda • █ head • a agulha é a ficha"
    )


# ═══════════════════════════════════════════════════════════════════
# 4. FITA DE FASES
#    Lacuna: o painel fixo mostra o turno, mas não a fase. Todo mundo
#    pergunta "agora é o quê?" — e o README já registra essa dúvida.
# ═══════════════════════════════════════════════════════════════════
PHASES = [
    ("preparation", "Preparação"),
    ("declaration", "Declaração"),
    ("resolution", "Resolução"),
    ("complete", "Completo"),
]
PHASE_HINT = {
    "preparation": "Os Sinner escolhem Skill e a ação hostil. Nada é rolado ainda.",
    "declaration": "Tudo declarado. Fecha quando o último confirmar a escolha.",
    "resolution": "O bot rola, resolve e persiste. O resultado vai para o canal.",
    "complete": "Turno fechado. Use /batalha iniciar para abrir outra operação.",
}


def phase_ribbon(current: str) -> str:
    """✓ feito • ◆ agora • ◇ pendente, com a fase atual destacada."""
    index = next((i for i, (key, _) in enumerate(PHASES) if key == current), 0)
    parts = []
    for i, (_, label) in enumerate(PHASES):
        if i < index:
            parts.append(f"`✓ {label}`")
        elif i == index:
            parts.append(f"**`◆ {label}`**")
        else:
            parts.append(f"`◇ {label}`")
    return "  →  ".join(parts)


def phase_turn_block(turn: int, current: str) -> tuple[str, str]:
    _, label = PHASES[index_of(current)]
    return f"`TURNO {turn:02} • {label.upper()}`", PHASE_HINT[current]


def index_of(current: str) -> int:
    return next((i for i, (key, _) in enumerate(PHASES) if key == current), 0)


# ═══════════════════════════════════════════════════════════════════
# 5. RASTREIO DE MOEDAS
#    Lacuna: o REGISTRO lista H/T por rodada mas não destaca a
#    rodada decisiva nem a distância entre os poderes. A leitura de
#    "por que perdi" fica por conta de quem conta moedas no olho.
# ═══════════════════════════════════════════════════════════════════
def coin_trace(embed: discord.Embed, rounds, winner: str) -> discord.Embed:
    final = rounds[-1]
    gap_final = abs(final["left_power"] - final["right_power"])
    embed.description = (
        f"## 🏆 {winner}\n"
        f"**{final['left_power']}** ⇠ decidiu por **{gap_final}** ⇢ **{final['right_power']}**"
    )
    lines = []
    for item in rounds:
        decisive = item is final
        mark = "◀◀◀" if decisive else "   "
        lf = "".join(B.COIN_HEADS if f else B.COIN_TAILS for f in item["left_faces"])
        rf = "".join(B.COIN_HEADS if f else B.COIN_TAILS for f in item["right_faces"])
        gap = abs(item["left_power"] - item["right_power"])
        # A barra é a distância, não a vitória: escala em passos de 5.
        dist = "▰" * min(6, gap // 5) if gap else "······"
        who = "◆" if item["left_power"] > item["right_power"] else "◇" if gap else "🔁"
        lines.append(
            f"{mark}`R{item['number']:02}` {lf} **{item['left_power']}** {who} "
            f"**{item['right_power']}** {dist} {rf}"
        )
    embed.add_field(name="◈ RASTREIO DAS MOEDAS", value="\n".join(lines), inline=False)
    embed.set_footer(text="◀◀◀ decidiu • barra central = diferença de poder • `🔁` empate")
    return embed


# ═══════════════════════════════════════════════════════════════════
#  Montagem dos exemplos
# ═══════════════════════════════════════════════════════════════════
def build_examples() -> list[tuple[str, str, discord.Embed]]:
    out: list[tuple[str, str, discord.Embed]] = []

    # --- 1. Composição: três situações reais ---------------------------
    slash = Skill("Corte Ascendente", 14, 6, 3, "", "attack")
    hit_list = resolve_damage(slash, -20, 3, 8, 2, faces=[True, False, True])

    e = discord.Embed(title="〔 DAMAGE RESOLUTION 〕", color=ACCENT)
    e.description = "## Yi Sang  ➜  Cavaleiro Aberrante\n`CORTE ASCENDENTE`"
    e.add_field(name="〔 DANO FINAL 〕", value=f"## {hit_list.final_damage}", inline=False)
    damage_composition(e, hit_list)
    out.append((
        "Composição do dano — só moedas, sem percentual nem escudo",
        "O caso mais simples. Repare que o escudo e o % aparecem como ±0: "
        "dizer 'não houve' é mais honesto que omitir a linha.",
        e,
    ))

    e2 = discord.Embed(title="〔 DAMAGE RESOLUTION 〕", color=ACCENT)
    e2.description = "## Yi Sang  ➜  Cavaleiro Aberrante\n`Corte Ascendente` + `Poço Sinuoso`"
    e2.add_field(name="〔 DANO FINAL 〕", value=f"## {max(0, hit_list.final_damage - 4)}", inline=False)
    damage_composition(e2, hit_list, shield=4)
    out.append((
        "Composição do dano — com escudo absorvendo 4",
        "Aqui a trilha é o que explica a conversa: o golpe valia "
        f"{hit_list.final_damage} e o escudo cobriu 4. É a pergunta mais comum em mesa.",
        e2,
    ))

    # --- 2. Escada de status: com expirado no meio ---------------------
    e3 = discord.Embed(title="【 PILHA DE EFEITOS 】", color=ACCENT)
    e3.description = "## Leitura de pilhas antes do Clash"
    status_ladder(e3, [
        ("bleed", 4, 3),
        ("burn", 2, 5),
        ("tremor", 6, 1),
        ("rupture", 1, 2),
        ("sinking", 0, 0),
    ])
    e3.set_footer(text="Largura = Potência (teto 8) • a linha de baixo é Quantidade")
    out.append((
        "Escada de status — pilha cheia, quase no teto e expirada",
        "O caso `sinking` expirado é o ponto: a pilha some mas continua "
        "visível. Se o campo simplesmente sumisse, o mestre leria bug.",
        e3,
    ))

    # --- 3. Termômetro: cinco fichas lado a lado ----------------------
    e4 = discord.Embed(title="〔 LCB // REGISTRO DE SINNER 〕", color=ACCENT)
    e4.description = "## Sanidade do grupo\n`" + sanity_scale() + "`"
    for name, sp in [("Yi Sang", -20), ("Faust", 15), ("Meursault", 0), ("Hong Lu", 45), ("Don Quixote", -45)]:
        e4.add_field(
            name=f"{name}  ·  `{sp:+d} SP`",
            value=f"`{sanity_gauge(sp)}`\n`{heads_chance(sp):.0%} HEADS`",
            inline=False,
        )
    e4.set_footer(text="A agulha é a ficha no intervalo −45..+45 • ◆ marca o zero exato")
    out.append((
        "Termômetro de sanidade — o grupo inteiro de uma vez",
        "O que o embed atual não mostra é a posição no intervalo. Com a "
        "escala, Don Quixote em −45 e Hong Lu em +45 ficam obviamente opostos, "
        "e o zero de Meursault é legível sem contas.",
        e4,
    ))

    # --- 4. Fita de fases: quatro estados -----------------------------
    for current, turn in [("preparation", 4), ("declaration", 4), ("resolution", 5), ("complete", 5)]:
        e5 = discord.Embed(title="〔 ⚔ COMBAT ENCOUNTER ⚠ 〕", color=GOLD)
        e5.description = f"# Portão Sul — Turno {turn:02}\n{phase_ribbon(current)}"
        state, hint = phase_turn_block(turn, current)
        e5.add_field(name="◇ ESTADO", value=f"{state}\n{hint}", inline=False)
        e5.set_footer(text="✓ feito • ◆ agora • ◇ pendente")
        out.append((
            f"Fita de fases — {PHASES[index_of(current)][1].lower()}",
            "Mesma função nos quatro estados. A fita não muda de forma, "
            "então o olho aprende a posição de cada fase uma vez só.",
            e5,
        ))

    # --- 5. Rastreio: vitória apertada e goleada ----------------------
    rounds_tight = [
        {"number": 1, "left_power": 26, "right_power": 19, "left_faces": [True, True, False], "right_faces": [False, False, True]},
        {"number": 2, "left_power": 21, "right_power": 24, "left_faces": [False, True, False], "right_faces": [True, True, True]},
        {"number": 3, "left_power": 30, "right_power": 22, "left_faces": [True, True, True], "right_faces": [False, True, False]},
    ]
    e6 = discord.Embed(title="〔 RESULTADO CONFIRMADO 〕", color=ACCENT)
    coin_trace(e6, rounds_tight, "Yi Sang")
    out.append((
        "Rastreio de moedas — perdeu a R02, decidiu na R03",
        "A R02 mostra quem estava ganhando antes de virar. A distância "
        "entre os poderes é o que permite ver *quando* o jogo virou.",
        e6,
    ))

    rounds_blowout = [
        {"number": 1, "left_power": 41, "right_power": 22, "left_faces": [True, True, True], "right_faces": [False, True, False]},
    ]
    e7 = discord.Embed(title="〔 RESULTADO CONFIRMADO 〕", color=ACCENT)
    coin_trace(e7, rounds_blowout, "Yi Sang")
    out.append((
        "Rastreio de moedas — goleada de uma rodada",
        "O extremo oposto: barra cheia e uma única linha. A leitura é "
        "instantânea e mostra que nem houve disputa.",
        e7,
    ))

    return out


# ═══════════════════════════════════════════════════════════════════
#  Renderização
# ═══════════════════════════════════════════════════════════════════
import html as _html  # noqa: E402
import re  # noqa: E402


def md(text: str) -> str:
    out = _html.escape(text or "")
    # Bloco de código: ``` no início da linha, com quebras internas.
    out = re.sub(
        r"^```\n?(.*?)^```",
        lambda m: '<span class="code">' + m.group(1).rstrip() + "</span>",
        out, flags=re.S | re.M,
    )
    # Crase simples vira <code> inline (o renderer anterior virava crase em texto).
    out = out.replace("`", "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"^#{1,3}\s*(.+)$", r'<div class="big">\1</div>', out, flags=re.M)
    return out.replace("\n", "<br>")


def to_html(embed: discord.Embed) -> str:
    color = f"#{embed.colour.value:06x}"
    p = [f'<div class="grid" style="border-left-color:{color}"><div class="body">']
    if embed.title:
        p.append(f'<div class="title">{md(embed.title)}</div>')
    if embed.description:
        p.append(f'<div class="desc">{md(embed.description)}</div>')
    for f in embed.fields:
        p.append(f'<div class="field"><div class="fname">{md(f.name)}</div>'
                 f'<div class="fval">{md(f.value)}</div></div>')
    if embed.footer and embed.footer.text:
        p.append(f'<div class="footer">{md(embed.footer.text)}</div>')
    p.append("</div></div>")
    return "\n".join(p)


def to_text(embed: discord.Embed) -> str:
    bar = "#" * 74
    out = [bar, f"TITLE : {embed.title}", f"COLOR : #{embed.colour.value:06x}"]
    if embed.description:
        out.append("DESCRIPTION:")
        out.append("\n".join("    " + l for l in embed.description.splitlines()))
    for f in embed.fields:
        out.append(f"  {f.name}")
        out.append("\n".join("      " + l for l in f.value.splitlines()))
    if embed.footer and embed.footer.text:
        out.append(f"FOOTER: {embed.footer.text}")
    out.append(f"[{len(embed)} chars / {len(embed.fields)} fields]")
    out.append(bar)
    return "\n".join(out)


CSS = """
:root { color-scheme: dark; }
body { background:#313338; color:#dbdee1; font:15px/1.5 "gg sans","Segoe UI",system-ui,sans-serif;
       margin:0; padding:32px 24px 80px; }
h1 { color:#f2f3f5; font-size:24px; margin:0 0 4px; }
p.sub { color:#949ba4; margin:0 0 10px; max-width:760px; }
p.disc { color:#949ba4; font-size:12px; margin:0 0 30px; }
h2 { color:#f2f3f5; font-size:16px; margin:0 0 4px; }
p.gap { color:#e6a23c; font-size:13px; margin:0 0 10px; max-width:600px; }
.card { max-width:600px; margin:0 0 34px; }
.grid { background:#2b2d31; border-radius:8px; padding:12px 0; border-left:4px solid #888; }
.body { padding:2px 16px 2px 12px; }
.title { color:#fff; font-weight:700; font-size:16px; margin-bottom:6px; }
.desc { color:#dbdee1; font-size:15px; margin:4px 0 8px; }
.big { font-size:20px; font-weight:700; color:#fff; margin:6px 0; }
.field { margin:6px 0; }
.fname { color:#fff; font-weight:600; font-size:14px; margin-bottom:2px; }
.fval { color:#dbdee1; font-size:14px; }
.code { display:block; background:#1e1f22; border:1px solid #2b2d31; border-radius:4px;
        padding:2px 6px; margin:2px 0; font:13px ui-monospace,Consolas,monospace;
        color:#b5bac1; white-space:pre-wrap; }
.footer { color:#949ba4; font-size:12px; margin-top:10px; }
"""


def main() -> None:
    examples = build_examples()
    blocks = [f"{label}\n{why}\n\n{to_text(embed)}\n" for label, why, embed in examples]
    (ROOT / "scripts" / "preview_concepts.txt").write_text("\n".join(blocks), encoding="utf-8")

    cards = "".join(
        f'<div class="card"><h2>{_html.escape(label)}</h2>'
        f'<p class="gap">{_html.escape(why)}</p>{to_html(embed)}</div>'
        for label, why, embed in examples
    )
    (ROOT / "scripts" / "preview_concepts.html").write_text(
        "<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>"
        "<title>Conceitos de embed</title><style>" + CSS + "</style></head><body>"
        "<h1>Conceitos: decoração que carrega informação</h1>"
        "<p class=sub>Cada bloco começa pelo que falta no embed atual. "
        "Se a decoração não muda a decisão do mestre, ela não entra.</p>"
        "<p class=sub><b>Fora de escopo por decisão do autor:</b> "
        "a curva de prognóstico (estimate_clash precisa ser barato) e "
        "o pulso de HP (o HP muda por fora do bot, então o embed mentiria).</p>"
        + cards + "</body></html>",
        encoding="utf-8",
    )
    print(f"{len(examples)} exemplos")
    print(ROOT / "scripts" / "preview_concepts.html")


if __name__ == "__main__":
    main()
