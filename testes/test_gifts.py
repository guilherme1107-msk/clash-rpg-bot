"""Como estão os 8 E.G.O Gifts — medido no motor, não anotado à mão.

A versão anterior deste arquivo era um checklist com os motivos de bloqueio
escritos por extenso. Ele ficou desatualizado depois das Etapas 4/5/6 e do
bloco 4: dizia "falta o gatilho session_round_start", "falta all_allies",
"faltam duration_turns" — e tudo isso já existia.

Aqui cada linha é conferida **contra o motor**: a cláusula é montada de verdade
(volta do `effects_json`, passa pelo `SkillEffect`) e só conta como "funciona"
se passar. O que não passa mostra o motivo real, tirado da exceção — não do que
alguém lembrou de escrever.

    python testes/test_gifts.py
"""
import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from database import _effects_from_row  # noqa: E402
from src.domain.models.combat import (  # noqa: E402
    EFFECT_OWNERS,
    EFFECT_TRIGGERS,
    EFFECT_TYPES,
    SkillEffect,
)

GUILD = 1392000415108960426
DB = ROOT / "clash_rpg.sqlite3"

# O `SkillEffect` só diz "Status circunstencial inválido" e não diz **qual**
# status ele queria. Aqui cada recusa vira a pendência concreta, com a Etapa que
# a destrava. Sem esta tabela o relatório era inútil — a mesma frase aparecia
# para 7 exigências diferentes.
PENDENCIA = {
    # status circunstancial que a cláusula pede e o bot não tem
    "hp": "HP nao e status no bot — Etapa 7 (modo manual): o bot PUBLICA a linha",
    "enemies_alive": "nao da para ler 'quantos inimigos restam' como status",
    "la_manchaland": "La Manchaland nao e status — precisa virar keyword da ficha",
    "protection": "Protection 'e por fora' (autor 21:0x)",
    "skill_tag": "Skill nao tem tag de efeito (Etapa 8)",
    "inflicted_bleed": "precisa ler o que a SKILL aplicou, nao um status da ficha",
    # tipo de efeito inexistente
    "heal_from_damage": "cura sobre o dano da skill — Etapa 7 (modo manual HP)",
    "shield": "o escudo virou numero solto (autor 23:4x) — `allies_with_keyword` faz o 50 x N",
    "affinity": "afinidade = fora de escopo (o bot nao tem Sin Affinity)",
    # gatilho inexistente
    "on_clash_win": "nao existe 'vitoria de Clash' como gatilho (o certo e clash_win)",
    # regra do SkillEffect
    "tremor_burst#count": "Tremor Burst nao aceita Count negativo — so valor",
}

# Cada gift: o que a print pede e o `effects_json` que tenta implementar.
REQUISITOS = {
    # Imperfect Eye: o mesmo spec v2 que está gravado no banco (6 cláusulas).
    "Imperfect Eye of Precognition": [
        ("apos vitoria: +1 Glimpse de Precognition",
         [{"trigger": "clash_win", "effect_type": "glimpse_of_precognition",
           "value": 1, "count": 1, "effect_owner": "user"}]),
        ("apos vitoria: Tremor 2x por Glimpse (ate 5x)",
         [{"trigger": "clash_win", "effect_type": "tremor", "value": 2, "count": 0,
           "condition_status": "glimpse_of_precognition", "condition_owner": "user",
           "condition_operator": "at_least", "condition_min": 1, "condition_per": 1,
           "condition_max_stacks": 5}]),
        ("apos vitoria: Burn 2x por Glimpse (ate 5x)",
         [{"trigger": "clash_win", "effect_type": "burn", "value": 2, "count": 0,
           "condition_status": "glimpse_of_precognition", "condition_owner": "user",
           "condition_operator": "at_least", "condition_min": 1, "condition_per": 1,
           "condition_max_stacks": 5}]),
        ("Amplitude Conversion no clash_win",
         [{"trigger": "clash_win", "effect_type": "amplitude_conversion_scorch",
           "value": 0}]),
        ("Tremor Burst no clash_win",
         [{"trigger": "clash_win", "effect_type": "tremor_burst", "value": 1}]),
        ("Tremor Burst no crit, no maximo 2x por rodada",
         [{"trigger": "on_crit", "effect_type": "tremor_burst", "value": 1,
           "max_per_round": 2}]),
    ],
    "The Familys Resentment": [
        ("cada 50 Bloodfeast CONSUMIDO (COMPARTILHADO): todos +1 Offense (max 6)",
         [{"trigger": "session_round_start", "effect_type": "offense_level", "value": 1,
           "condition_status": "shared_bloodfeast_consumed", "condition_owner": "user",
           "condition_operator": "at_least", "condition_min": 50, "condition_per": 50,
           "condition_max_stacks": 6, "effect_owner": "all_allies"}]),
        # Autor 21:0x: "curar com base no dano da skill causado" — a cura sai
        # do DANO da skill, nao do HP maximo. E o gift NAO da Bleed: ele
        # observa se a skill INFLINGIU Bleed. Por isso `condition_status` tem
        # que ler o resultado da skill (novo), nao um status qualquer.
        ("skill que inflngiu Bleed/Unique Bleed: cura 30% do dano (max 20)",
         [{"trigger": "after_attack", "effect_type": "heal_from_damage",
           "value": 30, "condition_status": "inflicted_bleed",
           "condition_max_stacks": 20}]),
        ("se curou: +1 Final Power no inicio da proxima rodada (max 3/rodada)",
         [{"trigger": "session_round_start", "effect_type": "base_power", "value": 1,
           "max_activations": 3, "activation_window": "round"}]),
        ("La Manchaland: +2 Offense por 30 Bloodfeast consumido (max 6)",
         [{"trigger": "session_round_start", "effect_type": "offense_level", "value": 2,
           "condition_status": "bloodfeast_consumed", "condition_min": 30,
           "condition_per": 30, "condition_max_stacks": 6}]),
        ("Dobre todo Bloodfeast gerado",
         [{"trigger": "after_attack", "effect_type": "bloodfeast", "value": 0,
           "count": 0}]),
    ],
    "Carousel Figurine": [
        ("+300 Bloodfeast na proxima rodada, 1x por encontro",
         [{"trigger": "session_round_start", "effect_type": "bloodfeast",
           "value": 300, "count": 1, "effect_owner": "user", "condition_turn": 1}]),
    ],
    "Dreaming Electric Sheep": [
        ("botao pra ativar na area de passivas",
         [{"trigger": "on_use", "effect_type": "base_power", "value": 1}]),
        ("por 2 rodadas",
         [{"trigger": "on_use", "effect_type": "base_power", "value": 1,
           "duration_turns": 2}]),
        # Autor 21:5x: "envy n precisa colocar" — tira do checklist tambem, nao
        # e so "nao implementar". Envy morre aqui como exigencia.
    ],
    "Livro da vingança: Annex": [
        # Autor 21:0x: "deixe sem os envy e deixe para quando tiver aliados no
        # encounter com o keyword de middle". As 3 cláusulas de Envy saem do
        # escopo — e Envy não é produzido por NENHUMA skill da Arcana, então
        # construir o recurso agora seria construir coisa morta.
        # Autor 21:5x: o escudo "quebra e na próxima rodada ele volta em 50,
        # caso não quebre ele volta pra 50. E fica nisso."
        # Autor 23:4x: "deixa só um número solto" — o escudo JÁ é um número
        # solto (`clashable_guard_values`); o gift só soma nele no embed. Por
        # isso "renova em 50" sai de graça: sem estado guardado, recalcula-se.
        ("[Inicio do Encontro] 50 de escudo POR ALIADO da Middle",
         [{"trigger": "session_encounter_start", "effect_type": "shield", "value": 50,
           "condition_status": "allies_with_keyword", "condition_keyword": "middle",
           "condition_min": 1, "effect_owner": "all_allies"}]),
    ],
    "Clear Mirror, Calm Water": [
        ("se um critico consumiu Poise Count: +10 Offense na proxima (1x por rodada)",
         [{"trigger": "on_crit", "effect_type": "offense_level", "value": 10,
           "effect_owner": "user", "condition_status": "poise", "condition_owner": "user",
           "condition_operator": "at_least", "condition_min": 1,
           "consume_condition": True, "duration_turns": 1, "max_activations": 1,
           "activation_window": "round"}]),
    ],
    "Reminiscence": [
        ("+(4 / #Moedas) conforme os inimigos morrem",
         [{"trigger": "on_kill", "effect_type": "base_power", "value": 4,
           "condition_status": "enemies_alive", "condition_min": 1}]),
        ("afinidade",
         [{"trigger": "on_use", "effect_type": "affinity", "value": 1}]),
    ],
    "Volatile's earring": [
        ("[Inicio da Rodada] +3 Sanidade",
         [{"trigger": "session_round_start", "effect_type": "sp", "value": 3}]),
        # Autor 21:0x: "protection é por fora". Protection não é gravado em
        # lugar nenhum ainda — nem aqui nem no Livro.
        ("skill de +5 moedas: -4 Coin Power na proxima",
         [{"trigger": "after_attack", "effect_type": "coin_power", "value": -4,
           "duration_turns": 1, "condition_status": "sp", "condition_min": 5}]),
    ],
}


def _motivo(erro, alvo):
    """Exceção do motor + a cláusula recusada -> pendência concreta."""
    texto = str(erro)
    if "circunstancial" in texto:
        return PENDENCIA.get(str(alvo.get("condition_status")), texto)
    if "Tipo de efeito inválido" in texto:
        tipo = str(alvo.get("effect_type"))
        return PENDENCIA.get(tipo, texto)
    if "Gatilho de efeito inválido" in texto:
        return PENDENCIA.get(str(alvo.get("trigger")), texto)
    if "Quantidade só pode ser usada" in texto:
        return PENDENCIA.get(f"{alvo.get('effect_type')}#count", texto)
    return texto


def carregar():
    if not DB.exists():
        raise unittest.SkipTest(f"banco ausente: {DB}")
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    gifts = {r["name"]: r for r in con.execute(
        "SELECT * FROM ego_gifts WHERE guild_id=?", (GUILD,))}
    con.close()
    return gifts


def julgar(itens):
    """Monta a cláusula de verdade e vê se o motor engole."""
    try:
        efeitos = _effects_from_row({"effects_json": json.dumps(itens)})
    except Exception as erro:                        # pragma: no cover
        return "falhou", f"{type(erro).__name__}: {erro}"
    if efeitos:
        e = efeitos[0]
        for campo, lista in (("trigger", EFFECT_TRIGGERS),
                             ("effect_type", EFFECT_TYPES)):
            if getattr(e, campo) not in lista:
                return "falhou", f"{campo} `{getattr(e, campo)}` nao existe"
        if e.effect_owner not in EFFECT_OWNERS:
            return "falhou", f"effect_owner `{e.effect_owner}` nao existe"
        return "ok", ""
    # `_effects_from_row` descarta em silencio. Levanta a excecao de novo para o
    # relatorio mostrar o motivo real, e nao "algo deu errado".
    try:
        SkillEffect(**itens[0])
    except Exception as erro:
        return "falhou", _motivo(erro, itens[0])
    return "falhou", "clausula descartada em silencio"


class EstadoDosGifts(unittest.TestCase):
    """Relatorio + trava: o numero de 'funciona' nao pode andar para tras."""

    @classmethod
    def setUpClass(cls):
        cls.gifts = carregar()
        cls.resultado = {
            nome: [(texto, julgar(itens)) for texto, itens in linhas]
            for nome, linhas in REQUISITOS.items()
        }
        cls.resumo = (
            sum(1 for linhas in cls.resultado.values() for _, (e, _) in linhas if e == "ok"),
            sum(len(v) for v in cls.resultado.values()),
        )

    def test_01_relatorio(self):
        print()
        print("=" * 78)
        print("OS 8 E.G.O GIFTS — cada linha testada contra o motor")
        print("=" * 78)
        for nome, linhas in self.resultado.items():
            gift = self.gifts.get(nome)
            gravado = "?" if gift is None else str(
                len(json.loads(gift["effects_json"] or "[]")))
            print(f"\n  {nome}")
            print(f"      gravado no banco: {gravado} clausula(s)")
            for texto, (estado, motivo) in linhas:
                if estado == "ok":
                    print(f"    [x] {texto}")
                else:
                    print(f"    [ ] {texto}")
                    print(f"         -> {motivo}")
        ok, total = self.resumo
        print()
        print(f"  {ok}/{total} exigencias que o motor consegue ler")
        print(f"  {total - ok} ainda bloqueadas")

    def test_02_gifts_no_banco(self):
        self.assertEqual(len(self.gifts), 8, "esperados 8 gifts gravados")

    def test_03_nenhuma_clausula_do_banco_e_descartada(self):
        """O que esta gravado tem que voltar inteiro — senao esta meio escrito."""
        for nome, gift in self.gifts.items():
            bruto = json.loads(gift["effects_json"] or "[]")
            lido = _effects_from_row(gift)
            self.assertEqual(
                len(bruto), len(lido),
                f"{nome}: {len(bruto)} gravado / {len(lido)} lido — "
                "descartou clausula em silencio")

    def test_04_modificadores_de_coluna(self):
        """Os mods de coluna nao sao clausula: vao direto no dano."""
        for nome, gift in self.gifts.items():
            for coluna in ("base_power_mod", "coin_power_mod", "clash_power_mod",
                           "offense_level_mod", "defense_level_mod", "crit_damage_mod"):
                self.assertIsInstance(gift[coluna], int, f"{nome}.{coluna}")

    def test_05_clear_mirror_70(self):
        """O +70 de crit do Poise e coluna permanente (decisao do autor)."""
        self.assertEqual(self.gifts["Clear Mirror, Calm Water"]["crit_damage_mod"], 70)

    def test_06_sem_regressao(self):
        """Trava o numero. Se cair, alguem quebrou o motor."""
        self.assertGreaterEqual(
            self.resumo[0], 13,
            f"so {self.resumo[0]}/{self.resumo[1]} — o motor le menos do que antes")


if __name__ == "__main__":
    unittest.main(verbosity=2)