"""Mostra cada GIF dentro do embed real que ele alimenta.

Um GIF solto nao diz muito. O que importa e ver a imagem na posicao exata
que o Discord vai renderizar: abaixo dos campos, na largura do embed.

Uso:  .venv\\Scripts\\python.exe scripts\\preview_gif_context.py
"""

from __future__ import annotations

import base64
import html
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "clashbot_gifctx.sqlite3")
os.environ.setdefault("DISCORD_TOKEN", "gifctx-only")

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import Modifiers, Skill, resolve_damage  # noqa: E402
from src.domain.models import Forecast  # noqa: E402

GIFS = ROOT / "assets" / "gifs"


def data_uri(name: str) -> str:
    raw = (GIFS / name).read_bytes()
    return f"data:image/gif;base64,{base64.b64encode(raw).decode()}"


def md(text: str) -> str:
    out = html.escape(text or "")
    out = out.replace("`", "")
    out = __import__("re").sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = __import__("re").sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = __import__("re").sub(r"^#{1,3}\s*(.+)$", r'<div class="big">\1</div>', out, flags=__import__("re").M)
    return out.replace("\n", "<br>")


def card(label: str, note: str, embed: discord.Embed, gif: str | None) -> str:
    color = f"#{embed.colour.value:06x}"
    p = [f'<div class="embed" style="border-left-color:{color}">']
    if embed.title:
        p.append(f'<div class="title">{md(embed.title)}</div>')
    if embed.description:
        p.append(f'<div class="desc">{md(embed.description)}</div>')
    for f in embed.fields:
        p.append(f'<div class="field"><div class="fname">{md(f.name)}</div>'
                 f'<div class="fval">{md(f.value)}</div></div>')
    if gif:
        p.append(f'<img class="art" src="{data_uri(gif)}">')
    if embed.footer and embed.footer.text:
        p.append(f'<div class="footer">{md(embed.footer.text)}</div>')
    p.append("</div>")
    return (f'<h2>{html.escape(label)}</h2><p class="note">{note}</p>' + "\n".join(p))


def main() -> None:
    slash = Skill("Corte Ascendente", 14, 6, 3, "", "attack",
                  effects=())
    riposte = Skill("Riposte Punida", 11, 4, 2, "", "counter")
    result = resolve_damage(slash, -20, 3, 8, 2, faces=[True, False, True])
    forecast = Forecast(0.62, "FAVORED", "Favorecido")

    cards = []

    # 1. Previsao
    e = B.prediction_embed("Yi Sang", slash, "Cavaleiro Aberrante", riposte, forecast, None)
    cards.append(card(
        "prediction_embed  <-  coin_flip.gif",
        "A imagem que faltava. Hoje clash_gifs.txt nao existe, entao este "
        "embed nunca recebeu imagem nenhuma. A moeda e o tema do jogo inteiro.",
        e, "coin_flip.gif"))

    # 2. Dano
    e2 = B.damage_embed("Yi Sang", "Cavaleiro Aberrante", slash, result, shield=4)
    cards.append(card(
        "damage_embed  <-  damage_resolution.gif",
        "DAMAGE_RESOLUTION_GIF esta vazio no .env, entao attach_damage_gif() "
        "retorna None no primeiro if. O embed mais usado do bot nunca teve imagem.",
        e2, "damage_resolution.gif"))

    # 3. Clash
    e3 = discord.Embed(
        title="〔 ⚠ CLASH ENGAGED ⚠ 〕", color=B.GOLD,
        description="## Yi Sang  ⟷  Cavaleiro Aberrante",
    )
    e3.add_field(name="MOEDAS // RODADA 02", value="**Yi Sang**  ▰▰▰\n**Cavaleiro**  ▱▱", inline=False)
    e3.set_footer(text="PROCESSANDO ROLAGENS E QUEBRA DE MOEDAS…")
    cards.append(card(
        "queued_clash_embed / animated_embed  <-  clash_impact.gif",
        "O painel que se re-edita a cada rodada. Uma imagem so aqui da o peso "
        "do momento sem poluir o texto, que precisa ser relido a cada update.",
        e3, "clash_impact.gif"))

    # 4. Escudo
    e4 = discord.Embed(title="〔 ESCUDO DEFENSIVO 〕", color=B.ACCENT)
    e4.description = f"## {max(0, result.final_damage - 4)} absorvido"
    e4.add_field(
        name="🛡️ ESCUDO DEFENSIVO",
        value=f"Dano `{result.final_damage}` − Escudo `4` = **{max(0, result.final_damage - 4)}**",
        inline=False,
    )
    e4.set_footer(text="O escudo é a única etapa do dano que não pertence ao atacante")
    cards.append(card(
        "etapa de escudo do damage_embed  <-  shield_absorb.gif",
        "Vale uma imagem propria porque o escudo e a unica etapa que o "
        "atacador nao produziu: o mestre precisa ver que aquilo foi barrado.",
        e4, "shield_absorb.gif"))

    sizes = "\n".join(
        f'<li><code>{n}</code> — {(GIFS / n).stat().st_size / 1024:.0f} KB</li>'
        for n in ("coin_flip.gif", "damage_resolution.gif", "clash_impact.gif", "shield_absorb.gif")
    )

    page = (
        "<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>"
        "<title>GIF nos embeds</title><style>"
        "body{background:#313338;color:#dbdee1;font:15px/1.5 'Segoe UI',system-ui,sans-serif;"
        "margin:0;padding:28px}"
        "h1{color:#f2f3f5;font-size:22px;margin:0 0 4px}"
        "h2{color:#f2f3f5;font-size:15px;margin:26px 0 4px}"
        "p.sub,p.note{color:#949ba4;font-size:13px;margin:0 0 10px;max-width:640px}"
        "p.note{color:#e6a23c}"
        ".embed{background:#2b2d31;border-radius:8px;border-left:4px solid #888;"
        "padding:12px 16px;max-width:520px;margin-bottom:8px}"
        ".title{color:#fff;font-weight:700;font-size:16px;margin-bottom:6px}"
        ".desc{color:#dbdee1;margin:4px 0 8px}"
        ".big{font-size:20px;font-weight:700;color:#fff;margin:6px 0}"
        ".field{margin:6px 0}"
        ".fname{color:#fff;font-weight:600;font-size:14px;margin-bottom:2px}"
        ".fval{color:#dbdee1;font-size:14px}"
        ".art{display:block;width:100%;margin-top:10px;border-radius:4px}"
        ".footer{color:#949ba4;font-size:12px;margin-top:10px}"
        "code{background:#1e1f22;padding:1px 5px;border-radius:3px}"
        "</style></head><body>"
        "<h1>Os quatro GIFs no lugar onde cada um entra</h1>"
        "<p class=sub>As animações estao embutidas abaixo de cada embed, na "
        "mesma posicao em que o Discord as renderiza. Passe o mouse para animar.</p>"
        + "".join(cards)
        + "<h2>Tamanhos</h2><ul class=sub>" + sizes + "</ul>"
        "</body></html>"
    )
    out = ROOT / "scripts" / "preview_gif_context.html"
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
