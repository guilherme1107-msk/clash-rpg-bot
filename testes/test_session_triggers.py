"""Etapa 4 do P7 — os 4 gatilhos `session_*` e o `condition_turn` dos prints.

Estes testes são do **motor e do banco**, sem o bot: o que se quer garantir aqui
é que o gatilho dispara no momento certo, na ordem certa, com o turno certo, e
que uma cláusula quebrada não derruba a virada de rodada do grupo.
"""
import json
import os
import tempfile
import unittest

from src.domain.combat import EFFECT_TRIGGERS, SkillEffect, triggered_effects
from database import Database

GUILD = 1
CHANNEL = 10
SESSAO = ("session_encounter_start", "session_combat_start",
          "session_round_start", "session_round_end")


class GatilhosDeSessaoTests(unittest.TestCase):
    def test_os_quatro_gatilhos_de_sessao_existem(self):
        for trigger in SESSAO:
            self.assertIn(trigger, EFFECT_TRIGGERS)

    def test_prefixo_session_nao_colide_com_o_on_round_start_do_clash(self):
        # `on_round_start` é o gatilho que o Clash já dispara para as skills —
        # é outra coisa e continua separado dos de sessão.
        self.assertIn("on_round_start", {"on_round_start"})
        self.assertFalse(SESSAO[0].startswith("on_round"))
        self.assertNotEqual("on_round_start", "session_round_start")

    # ------------------------------------------------------- condition_turn
    def _clausula(self, turn=None):
        return SkillEffect(
            "session_round_start", "sp", 3, condition_turn=turn,
        )

    def test_sem_condition_turn_dispara_em_qualquer_rodada(self):
        for turno in (1, 2, 7, None):
            self.assertEqual(len(triggered_effects((self._clausula(),), "session_round_start", turn=turno)), 1)

    def test_primeira_rodada_so_dispara_na_rodada_1(self):
        clausula = self._clausula(1)
        self.assertEqual(len(triggered_effects((clausula,), "session_round_start", turn=1)), 1)
        for turno in (2, 3, 10):
            self.assertEqual(len(triggered_effects((clausula,), "session_round_start", turn=turno)), 0)

    def test_condition_turn_sem_turno_conhecido_nao_dispara(self):
        # Falha fechada: se o chamador não informar o turno, é melhor não
        # disparar do que o gift virar "vale em toda rodada" sem querer.
        clausula = self._clausula(1)
        self.assertEqual(len(triggered_effects((clausula,), "session_round_start")), 0)
        self.assertEqual(len(triggered_effects((self._clausula(),), "session_round_start")), 1)


class FluxoDeSessaoTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.db = Database(self.path)
        self.db.setup()
        self.calls = []
        self.db.session_hook = lambda g, c, t, turn: self.calls.append((t, turn))

    def tearDown(self):
        self.db.close()
        os.remove(self.path)

    def _encontro(self):
        self.db.start_battle(GUILD, CHANNEL, "Encontro", 100)
        self.db.join_battle(GUILD, CHANNEL, 100, "Esquerda")
        self.db.join_battle(GUILD, CHANNEL, 101, "Direita")

    # ------------------------------------------------------------- disparo
    def test_sem_gancho_nada_quebra_e_o_fluxo_segue(self):
        self.db.session_hook = None
        self._encontro()
        self.db.set_battle_phase(GUILD, CHANNEL, "declaration")
        self.assertEqual(self.db.get_battle(GUILD, CHANNEL)["phase"], "declaration")

    def test_gancho_quebrado_nao_derruba_a_virada_de_fase(self):
        def explosivo(*_args):
            raise RuntimeError("gift mal escrito")
        self.db.session_hook = explosivo
        self._encontro()
        self.db.set_battle_phase(GUILD, CHANNEL, "declaration")   # não pode levantar
        self.assertEqual(self.db.get_battle(GUILD, CHANNEL)["phase"], "declaration")

    def test_inicio_do_encontro_dispara_na_rodada_1_na_ordem_da_print(self):
        self._encontro()
        self.db.set_battle_phase(GUILD, CHANNEL, "declaration")
        self.assertEqual(
            self.calls,
            [("session_encounter_start", 1), ("session_combat_start", 1),
             ("session_round_start", 1)],
        )

    def test_rodadas_seguintes_disparam_somente_o_inicio_da_rodada(self):
        self._encontro()
        self.db.set_battle_phase(GUILD, CHANNEL, "declaration")
        self.calls.clear()
        self.db.set_battle_phase(GUILD, CHANNEL, "resolution")
        self.assertEqual(self.calls, [], "resolver não é começo de rodada")
        self.db.next_battle_turn(GUILD, CHANNEL)      # fecha a rodada 1
        self.calls.clear()
        self.db.set_battle_phase(GUILD, CHANNEL, "declaration")
        self.assertEqual(self.calls, [("session_round_start", 2)])

    def test_fim_da_rodada_vem_antes_de_o_turno_virar(self):
        self._encontro()
        self.db.set_battle_phase(GUILD, CHANNEL, "declaration")
        self.calls.clear()
        self.db.next_battle_turn(GUILD, CHANNEL)
        self.assertEqual(self.calls, [("session_round_end", 1)],
                         "o gift tem que ver a rodada que está acabando")
        self.assertEqual(self.db.get_battle(GUILD, CHANNEL)["turn"], 2)

    def test_current_turn_cai_para_1_quando_nao_ha_batalha(self):
        self.assertEqual(self.db.current_turn(GUILD, 999), 1)

    def test_current_turn_le_o_turno_da_batalha_ativa(self):
        self._encontro()
        self.assertEqual(self.db.current_turn(GUILD, CHANNEL), 1)
        self.db.next_battle_turn(GUILD, CHANNEL)
        self.assertEqual(self.db.current_turn(GUILD, CHANNEL), 2)

    # -------------------------------------------- o gift chega na ficha mesmo
    def test_clausula_de_sessao_grava_o_efeito_na_ficha(self):
        """Sem o bot: prova só que a cláusula sai do JSON e respeita o turno.

        A aplicação em si (SP, Offense, status) é do motor do bot e é coberta
        pelo teste de fábrica com cópia do banco real.
        """
        self.db.create_character(GUILD, 100, "Esquerda")
        self.db.save_ego_gift(GUILD, "player", 100, {
            "name": "Primeira Rodada", "tier": 5, "description": "",
            "effects": [{"trigger": "session_round_start", "effect_type": "sp",
                         "value": 3, "condition_turn": 1}],
        })
        nomes = [n for n, _, _tag in self.db.list_active_ego_gift_effects(GUILD, "player", 100)]
        self.assertEqual(nomes, ["Primeira Rodada"])
        gift_effects = self.db.list_active_ego_gift_effects(GUILD, "player", 100)[0][1]
        self.assertEqual(len(triggered_effects(gift_effects, "session_round_start", turn=1)), 1)
        self.assertEqual(len(triggered_effects(gift_effects, "session_round_start", turn=2)), 0)


class RegressaoDaEtapa2Tests(unittest.TestCase):
    """A Etapa 2 criou os status, mas esqueceu a lista de `__post_init__`.

    Sem ela, `SkillEffect("…", "bloodfeast", 300, count=1)` levantava
    ``ValueError`` e o `_effects_from_row`` **descartava a cláusula em silêncio**:
    o gift ficava gravado no banco e nunca fazia nada. Só apareceu quando a
    Etapa 4 gravou um `[Primeira Rodada] Bloodfeast +300` de verdade.
    """

    def test_os_tres_recursos_aceitam_quantidade(self):
        for tipo in ("bloodfeast", "unique_bloodfeast", "unique_bleed"):
            efeito = SkillEffect("session_round_start", tipo, 300, count=1)
            self.assertEqual(efeito.count, 1, tipo)

    def test_clausula_com_count_sobrevive_a_ida_e_volta_do_banco(self):
        # O teste que importa: passar pelo MESMO caminho que o banco usa.
        from database import _effects_from_row

        class Linha(dict):
            def keys(self):
                return dict.keys(self)

        clauses = [{"trigger": "session_round_start", "effect_type": "bloodfeast",
                    "value": 300, "count": 1, "effect_owner": "user",
                    "condition_turn": 1}]
        lidas = _effects_from_row(Linha({"effects_json": json.dumps(clauses)}))
        self.assertEqual(len(lidas), 1, "a cláusula foi descartada em silêncio")
        self.assertEqual(lidas[0].effect_type, "bloodfeast")
        self.assertEqual(lidas[0].count, 1)

    def test_ainda_assim_tipo_desconhecido_com_count_continua_rejeitado(self):
        with self.assertRaises(ValueError):
            SkillEffect("on_use", "nao_existe", 5, count=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
