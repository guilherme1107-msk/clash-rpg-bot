"""Varredura de erro na simulação do Encounter.

Roda o mesmo cenário de `sim_encounter.py` e reporta **só** o que deu
errado: avisos do logger, exceções engolidas, embeds malformados
(title/description vazio, campo > 1024, anexo apontando para arquivo que
não existe), e a passagem de cada fase da máquina de estados.

    python testes/varre_encounter.py
"""
import asyncio
import json
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_TMP = Path(tempfile.gettempdir()) / "clashbot_varre_encounter.sqlite3"
for _s in ("", "-wal", "-shm"):
    _p = Path(str(_TMP) + _s)
    if _p.exists():
        _p.unlink()
os.environ["DATABASE_PATH"] = str(_TMP)
os.environ.setdefault("DISCORD_TOKEN", "varredura-only")
os.environ["DAMAGE_RESOLUTION_GIF"] = ""
os.environ["UNBREAKABLE_FOLLOWUP_GIF"] = ""

# --- captura tudo que o logger emitir --------------------------------------
avisos: list[str] = []


class Captura(logging.Handler):
    def emit(self, registro):
        if registro.levelno >= logging.WARNING:
            avisos.append(f"[{registro.levelname}] {registro.getMessage()}")


import bot as B  # noqa: E402
from src.domain.combat import Skill, SkillEffect  # noqa: E402

for _logger in ("bot", "audit", "root", ""):
    alvo = logging.getLogger(_logger)
    alvo.addHandler(Captura())
    alvo.setLevel(logging.DEBUG)

GUILD = 1_000_000_000_000_001
ME = 555_000_000_000_001
CHAN = 999_000_000_000_001
NOME_INIMIGO = "Cavaleiro Aberrante"

erros: list[str] = []
etapas: list[str] = []


def erro(msg):
    erros.append(msg)
    print(f"  ERRO: {msg}")


def etapa(msg):
    etapas.append(msg)
    print(f"  ok: {msg}")


class FakeMessage:
    def __init__(self, canal, n):
        self.canal, self.n = canal, n

    async def edit(self, embed=None, files=None, **_):
        self.canal.eventos.append(("edit", self.n, embed, files))


class FakeChannel:
    def __init__(self):
        self.eventos = []
        self._n = 0

    async def send(self, embed=None, files=None, content=None, **_):
        self._n += 1
        self.eventos.append(("send", self._n, embed, files))
        return FakeMessage(self, self._n)


def conferir_embeds(canal, rotulo):
    """Cada embed tem que ser publicável: title/description e limites."""
    if not canal.eventos:
        erro(f"{rotulo}: nenhuma mensagem publicada")
        return
    for tipo, n, embed, files in canal.eventos:
        onde = f"{rotulo} {'send' if tipo == 'send' else 'edit'}#{n}"
        if embed is None:
            erro(f"{onde}: sem embed")
            continue
        if not (embed.title or embed.description):
            erro(f"{onde}: nem title nem description")
        if embed.title and len(embed.title) > 256:
            erro(f"{onde}: title com {len(embed.title)} > 256")
        if embed.description and len(str(embed.description)) > 4096:
            erro(f"{onde}: description com {len(str(embed.description))} > 4096")
        for campo in embed.fields:
            if len(str(campo.value)) > 1024:
                erro(f"{onde}: campo '{campo.name}' com {len(str(campo.value))} > 1024")
            if len(str(campo.name)) > 256:
                erro(f"{onde}: nome de campo com {len(str(campo.name))} > 256")
        url = getattr(getattr(embed, "image", None), "url", "") or ""
        # Em `edit` o arquivo NÃO é reenviado de propósito: editar sem passar
        # files preserva os anexos que já estão na mensagem (bot.py:5314-5317),
        # então o attachment:// continua apontando para o mesmo GIF. Só um
        # `send` tem que carregar o arquivo junto.
        if url.startswith("attachment://") and tipo == "send":
            nome = url.split("://", 1)[1]
            if not any(getattr(f, "filename", "") == nome for f in (files or [])):
                erro(f"{onde}: attachment://{nome} sem o arquivo na mensagem")
    anexos = sum(len(f or []) for _t, _n, _e, f in canal.eventos)
    etapa(f"{rotulo}: {len(canal.eventos)} mensagem(ns), {anexos} anexo(s), embeds dentro dos limites")


def semear():
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
    sk = Skill("Lâmina Rasante", 14, 6, 3, "Corte.", "attack",
               effects=(SkillEffect("on_hit", "bleed", 3, count=2),))
    db.save_skill(GUILD, ME, sk)
    inimigo = db.save_enemy(GUILD, ME, NOME_INIMIGO, -10, 3, 2)
    db.add_status(GUILD, "enemy", inimigo["id"], "bleed", 5, 4)
    db.add_status(GUILD, "enemy", inimigo["id"], "tremor", 3, 1)
    db.save_enemy_skill(inimigo["id"], Skill(
        "Golpe do Portão", 11, 4, 2, "Investida.", "attack",
        effects=(SkillEffect("on_hit", "tremor", 2, count=1),),
    ))
    # gift com cláusula que DEVE disparar: bleed do alvo >= 3
    db.save_ego_gift(GUILD, "player", ME, {
        "name": "Imperfect Eye of Precognition", "tier": 5, "gift_class": "ALEPH",
        "description": "x", "base_power_mod": 2, "clash_power_mod": 3,
        "crit_damage_mod": 10,
        "effects": [{
            "trigger": "after_attack", "effect_type": "base_power", "value": 2,
            "condition_status": "bleed", "condition_operator": "at_least",
            "condition_owner": "target", "condition_value": "potency",
            "condition_min": 3, "max_per_round": 1,
        }],
    })
    db.start_battle(GUILD, CHAN, "Operação // Portão Leste", ME)
    db.join_battle(GUILD, CHAN, ME, "Arcana")
    db.add_field_action(GUILD, CHAN, NOME_INIMIGO, "Golpe do Portão", ME, None)
    return inimigo, sk


def main() -> int:
    print("Varredura de erro — modo Encounter (banco temporário, sem Discord)\n")
    inimigo, sk = semear()

    # --- fases -----------------------------------------------------------
    fase = B.db.get_battle(GUILD, CHAN)
    if fase["phase"] != "preparation":
        erro(f"fase inicial era {fase['phase']}, esperado preparation")
    else:
        etapa("start_battle -> phase=preparation")

    B.db.set_battle_phase(GUILD, CHAN, "declaration")
    fase = B.db.get_battle(GUILD, CHAN)
    if fase["phase"] != "declaration":
        erro(f"nao avancou para declaration (ficou {fase['phase']})")
    else:
        etapa("set_battle_phase -> declaration (dispara session_encounter_start)")

    # --- clash -----------------------------------------------------------
    try:
        resultado = B.execute_clash_job(B.db, {
            "guild_id": GUILD, "user_id": ME, "channel_id": CHAN,
            "target_kind": "enemy", "target_id": inimigo["id"],
            "left_skill": sk.name, "right_skill": "Golpe do Portão",
            "source": "encounter", "turn": fase["turn"],
        }, effects=B.activity_clash_effects(GUILD))
        etapa(f"execute_clash_job -> vencedor={resultado['winner']} dano={resultado['damage']}")
    except Exception:
        erro("execute_clash_job lancou excecao:\n" + traceback.format_exc())
        return 1

    if "forecast_chance" not in resultado:
        erro("resultado sem forecast_chance (a embed de predicao falharia)")
    if not resultado.get("rounds"):
        erro("resultado sem rounds")

    # O E.G.O Gift tem que aparecer: sem o `owner_kind` certo (`player`) o
    # motor não acha a ficha e a cláusula some em silêncio.
    dbg = B.triggered_gift_effects(GUILD, "player", ME, "after_attack")
    if len(dbg) != 1:
        erro(f"gift: triggered_gift_effects(after_attack) devolveu {len(dbg)}, esperado 1")
    linhas_gift = [str(x) for x in (resultado.get("effects") or [])]
    if not any("base_power" in x for x in linhas_gift):
        erro(f"gift: cláusula after_attack não apareceu em effects -> {linhas_gift}")
    else:
        etapa("cláusula do E.G.O Gift disparou: " + " | ".join(linhas_gift))

    canal = FakeChannel()
    asyncio.run(B.publish_queued_clash(canal, resultado))
    conferir_embeds(canal, "clash")

    # --- ataque livre ----------------------------------------------------
    try:
        livre = B.execute_enemy_unopposed_job(B.db, {
            "guild_id": GUILD, "actor_enemy_id": inimigo["id"], "target_id": ME,
            "enemy_skill": "Golpe do Portão", "source": "encounter",
        })
        etapa(f"execute_enemy_unopposed_job -> dano={livre.get('damage')}")
    except Exception:
        erro("execute_enemy_unopposed_job lancou excecao:\n" + traceback.format_exc())
        return 1

    canal2 = FakeChannel()
    asyncio.run(B.publish_unopposed_attack(canal2, livre))
    conferir_embeds(canal2, "sem-oposicao")

    # --- virada de turno --------------------------------------------------
    try:
        B.db.set_battle_phase(GUILD, CHAN, "resolution")
        B.db.set_battle_phase(GUILD, CHAN, "complete")
        depois = B.db.next_battle_turn(GUILD, CHAN)
        if depois["phase"] != "preparation" or int(depois["turn"]) != 2:
            erro(f"virada de turno errada: phase={depois['phase']} turn={depois['turn']}")
        else:
            etapa("resolution -> complete -> next_turn: phase=preparation, turn=2")
    except Exception:
        erro("virada de turno lancou excecao:\n" + traceback.format_exc())

    eventos = B.db.last_round_status_events or []
    etapa(f"eventos de status do fim de rodada: {len(eventos)}")
    if eventos:
        try:
            embed = B.round_status_embed(GUILD, eventos)
            if embed is None:
                erro("round_status_embed devolveu None com 3 eventos")
            else:
                canal3 = FakeChannel()
                canal3.eventos.append(("send", 1, embed, []))
                conferir_embeds(canal3, "status-fim-de-rodada")
        except Exception:
            erro("round_status_embed lancou excecao:\n" + traceback.format_exc())

    # --- relatório ---------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"ETAPAS OK: {len(etapas)}")
    print(f"ERROS    : {len(erros)}")
    print(f"LOG >= WARNING: {len(avisos)}")
    for a in avisos:
        print("   ", a)
    for e in erros:
        print("   ", e)
    print("=" * 70)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
