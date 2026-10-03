"""Simulação de um combate no **modo Encounter**, com os embeds reais.

Nada aqui toca o Discord nem o ``clash_rpg.sqlite3``: o banco é temporário e
o canal é um objeto falso que grava o que ``send``/``edit`` receberia. É o
mesmo caminho do jogo — ``execute_clash_job`` do motor, depois
``publish_queued_clash``/``publish_unopposed_attack`` do ``bot.py``, que são
os pontos onde o Encounter publica (bot.py:5303 e bot.py:5483).

    python testes/sim_encounter.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- ambiente ANTES de importar bot --------------------------------------
# O `bot.py` lê o DATABASE_PATH no import, então tem que estar setado antes.
# Os GIFs são forçados para o caminho local: sem URL não há `aiohttp`, e a
# simulação não pode depender de rede.
_TMP = Path(tempfile.gettempdir()) / "clashbot_sim_encounter.sqlite3"
for _sufixo in ("", "-wal", "-shm"):
    _p = Path(str(_TMP) + _sufixo)
    if _p.exists():
        _p.unlink()
os.environ["DATABASE_PATH"] = str(_TMP)
os.environ.setdefault("DISCORD_TOKEN", "sim-only-not-a-real-token")
os.environ["DAMAGE_RESOLUTION_GIF"] = ""
os.environ["UNBREAKABLE_FOLLOWUP_GIF"] = ""

import discord  # noqa: E402

import bot as B  # noqa: E402
from src.domain.combat import Skill, SkillEffect  # noqa: E402

GUILD = 1_000_000_000_000_001
ME = 555_000_000_000_001
CHAN = 999_000_000_000_001
ENEMY_NAME = "Cavaleiro Aberrante"


# --- captura: o que o Discord receberia ------------------------------------
class FakeMessage:
    def __init__(self, canal, numero):
        self.canal, self.numero = canal, numero

    async def edit(self, embed=None, files=None, **_):
        self.canal.eventos.append(("edit", self.numero, embed, files))


class FakeChannel:
    """Grava cada `send`/`edit` em vez de falar com o Discord."""

    def __init__(self):
        self.eventos: list = []
        self._n = 0

    async def send(self, embed=None, files=None, content=None, **_):
        self._n += 1
        self.eventos.append(("send", self._n, embed, files))
        return FakeMessage(self, self._n)

    async def fetch_message(self, _id):
        raise AssertionError("na simulacao nao ha mensagem remota")


def anexos(files) -> str:
    nomes = [getattr(f, "filename", "?") for f in (files or [])]
    return ", ".join(nomes) if nomes else "(sem anexo)"


def como_texto(embed: discord.Embed) -> str:
    linhas = []
    if embed.title:
        linhas.append(embed.title)
    if embed.description:
        linhas.append("")
        linhas.append(str(embed.description))
    for campo in embed.fields:
        linhas.append("")
        linhas.append(f"  {campo.name}")
        for linha in str(campo.value).split("\n"):
            linhas.append(f"    {linha}")
    if embed.footer and embed.footer.text:
        linhas.append("")
        linhas.append(f"  ⌄ {embed.footer.text}")
    if getattr(embed, "image", None) and embed.image.url:
        linhas.append(f"  [imagem] {embed.image.url}")
    return "\n".join(linhas)


def mostrar(canal, rotulo):
    print("\n" + "=" * 78)
    print(f"  {rotulo}  —  {len(canal.eventos)} mensagem(ns) para o Discord")
    print("=" * 78)
    for tipo, numero, embed, files in canal.eventos:
        tag = "ENVIAR" if tipo == "send" else f"EDIT#{numero}"
        if embed is None:
            print(f"\n[{tag}] (sem embed) anexos: {anexos(files)}")
            continue
        print(f"\n[{tag}] anexos: {anexos(files)}")
        print("-" * 78)
        print(como_texto(embed))
        print("-" * 78)
    # devolve quantos anexos de verdade foram pedidos
    return sum(len(f or []) for _t, _n, _e, f in canal.eventos)


# --- banco temporário ------------------------------------------------------
def semear() -> dict:
    db = B.db
    db.setup()

    db.create_character(GUILD, ME, "Arcana")
    db.connection.execute(
        "UPDATE characters SET sp=-12, offense_level=4, defense_level=3, "
        "paralysis=1, base_power_mod=2, clash_power_mod=-1 WHERE guild_id=? AND user_id=?",
        (GUILD, ME),
    )
    db.add_status(GUILD, "player", ME, "bleed", 4, 3)
    db.add_status(GUILD, "player", ME, "poise", 6, 2)

    # skill do jogador — a da Arcana, com Efeito de Bleed
    skill_jogador = Skill(
        "Lâmina Rasante", 14, 6, 3, "Corte horizontal que abre a guarda.", "attack",
        effects=(SkillEffect("on_hit", "bleed", 3, count=2),),
    )
    db.save_skill(GUILD, ME, skill_jogador)

    enemy = db.save_enemy(GUILD, ME, ENEMY_NAME, -10, 3, 2)
    db.add_status(GUILD, "enemy", enemy["id"], "bleed", 2, 4)
    db.add_status(GUILD, "enemy", enemy["id"], "tremor", 3, 1)
    db.save_enemy_skill(enemy["id"], Skill(
        "Golpe do Portão", 11, 4, 2, "Investida pesada.", "attack",
        effects=(SkillEffect("on_hit", "tremor", 2, count=1),),
    ))

    # um E.G.O Gift com cláusula de verdade (o escudo do Livro é o mesmo formato)
    db.save_ego_gift(GUILD, "player", ME, {
        "name": "Imperfect Eye of Precognition", "tier": 5, "gift_class": "ALEPH",
        "description": "Cláusula de exemplo para a simulação.",
        "base_power_mod": 2, "clash_power_mod": 3, "crit_damage_mod": 10,
        "effects": [{
            "trigger": "after_attack", "effect_type": "base_power", "value": 2,
            "condition_status": "bleed", "condition_operator": "at_least",
            "condition_owner": "target", "condition_value": "potency",
            "condition_min": 3, "max_per_round": 1,
        }],
    })

    # o encontro em si
    db.start_battle(GUILD, CHAN, "Operação // Portão Leste", ME)
    db.join_battle(GUILD, CHAN, ME, "Arcana")
    db.add_field_action(GUILD, CHAN, ENEMY_NAME, "Golpe do Portão", ME, None)

    return {"enemy": enemy, "skill": skill_jogador}


# --- as duas publicações do Encounter --------------------------------------
async def publicar_clash(result: dict) -> None:
    """O caminho do Clash (bot.py:5303 publish_queued_clash)."""
    canal = FakeChannel()
    await B.publish_queued_clash(canal, result)
    mostrar(canal, "CLASH — publish_queued_clash (bot.py:5303)")
    print(f"\n  -> total de anexos: {sum(len(f or []) for _t,_n,_e,f in canal.eventos)}")


async def publicar_sem_oposicao(result: dict) -> None:
    """O caminho do ataque livre (bot.py:5483 publish_unopposed_attack)."""
    canal = FakeChannel()
    await B.publish_unopposed_attack(canal, result)
    mostrar(canal, "SEM OPOSIÇÃO — publish_unopposed_attack (bot.py:5483)")


def resumo(result: dict) -> None:
    print("\n" + "-" * 78)
    print("  RESULTADO DO MOTOR (execute_clash_job)")
    print("-" * 78)
    for chave in ("left_name", "right_name", "winner", "winner_name",
                  "damage", "left_sp", "right_sp", "followup_coins",
                  "followup_damage", "left_power", "right_power"):
        if chave in result:
            print(f"  {chave:<16} = {result[chave]}")
    rodadas = result.get("rounds") or []
    print(f"  rounds           = {len(rodadas)}")
    for i, r in enumerate(rodadas, 1):
        if isinstance(r, dict):
            print(f"    rodada {i}: " + json.dumps(r, ensure_ascii=False)[:150])
    for chave in ("effects", "damage_effects"):
        if result.get(chave):
            print(f"  {chave}:")
            for item in result[chave]:
                print(f"    - {item}")


def main() -> int:
    print("Simulação de combate — modo Encounter (banco temporário, sem Discord)")
    print(f"banco: {_TMP}")

    dados = semear()
    enemy = dados["enemy"]

    # ---- fase 1: o hostil entra em campo, declara -----------------------
    fase = B.db.get_battle(GUILD, CHAN)
    print(f"\n1) encontro criado: '{fase['name']}' | fase={fase['phase']} | turno={fase['turn']}")

    B.db.set_battle_phase(GUILD, CHAN, "declaration")
    print("2) phase -> declaration (dispara session_encounter_start/session_combat_start)")

    # ---- o combate: clash jogador x hostil ------------------------------
    request = {
        "guild_id": GUILD, "user_id": ME, "channel_id": CHAN,
        "target_kind": "enemy", "target_id": enemy["id"],
        "left_skill": dados["skill"].name, "right_skill": "Golpe do Portão",
        "source": "encounter", "turn": fase["turn"],
    }
    result = B.execute_clash_job(B.db, request, effects=B.activity_clash_effects(GUILD))
    resumo(result)

    # ---- o que o Discord receberia --------------------------------------
    asyncio.run(publicar_clash(result))

    # ---- e o ataque livre do hostil (sem oposição) -----------------------
    livre = B.execute_enemy_unopposed_job(B.db, {
        "guild_id": GUILD, "actor_enemy_id": enemy["id"], "target_id": ME,
        "enemy_skill": "Golpe do Portão", "source": "encounter",
    })
    resumo(livre)
    asyncio.run(publicar_sem_oposicao(livre))

    # ---- virada de turno --------------------------------------------------
    B.db.set_battle_phase(GUILD, CHAN, "resolution")
    B.db.set_battle_phase(GUILD, CHAN, "complete")
    depois = B.db.next_battle_turn(GUILD, CHAN)
    print(f"\n3) resolution -> complete -> next_turn: fase={depois['phase']} turno={depois['turn']}")

    status = B.db.last_round_status_events
    print(f"   eventos de status do fim de rodada: {len(status or [])}")
    if status:
        embed = B.round_status_embed(GUILD, status)
        canal = FakeChannel()
        print(como_texto(embed) if embed else "(sem embed de status)")

    print("\nOK — simulação completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
