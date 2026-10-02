"""P9 — o E.G.O Gift tem que entrar **no Clash E no dano** (decisão 7).

Antes o gift contava em `resolve_clash` (`clash_execution.py:80-83`) e ficava de
fora de `resolve_damage`: um gift com Base Power / Offense Level / Defense Level
não mudava o dano em nada. Estes testes comparam **a mesma rolagem** (mesma
semente) com o gift desligado e ligado, então a única diferença é o gift.
"""
import os
import random
import tempfile
import unittest
from unittest import mock

from src.domain.combat import Skill
from src.application.services.clash_execution import execute_clash_job
from database import Database

GUILD = 1
LEFT, RIGHT = 100, 101
SEMENTE = 20261001
# A classe real, capturada ANTES de qualquer patch. Se a lambda do patch
# chamasse `random.Random`, ela chamaria a si mesma e o teste explodiria com
# RecursionError (o `mock.patch` mexe no módulo `random` inteiro).
_RandomReal = random.Random


def _rodada_com_gift(db, *, left_gift=None, right_gift=None):
    """Roda UM clash com semente fixa e devolve (dano, vencedor).

    Duas coisas são obrigatórias para a comparação valer:

    1. **A semente vai por dentro do motor.** `engine.py` faz
       ``rng = rng or random.Random()`` — um ``Random`` NOVO, semeado pelo SO.
       Chamar ``random.seed()`` de fora não muda nada (foi exatamente por isso
       que a primeira versão deste teste media sorte). O patch intercepta a
       fábrica e devolve um ``Random`` já semeado a cada chamada.
    2. **O SP é zerado antes de cada corrida.** O Clash confirma SP (±5) e a
       Sanidade move a chance de Heads, então sem isso a semente não repetiria
       a rolagem.
    """
    with db.connection:
        db.connection.execute(
            """UPDATE characters SET sp=0,paralysis=0,coin_power_mod=0,clash_power_mod=0,
               offense_level_mod=0,defense_level_mod=0 WHERE guild_id=?""",
            (GUILD,),
        )
    for nome, uid, gift in (("Esq", LEFT, left_gift), ("Dir", RIGHT, right_gift)):
        if gift is None:
            continue
        db.save_ego_gift(GUILD, "player", uid, {
            "name": f"Gift {nome}", "tier": 5, "description": "", "effects": [],
            **gift,
        })
    pedido = {
        "guild_id": GUILD, "user_id": LEFT, "target_kind": "player", "target_id": RIGHT,
        "left_skill": "Golpe", "right_skill": "Rajada",
    }
    with mock.patch("src.domain.combat.engine.random.Random",
                    lambda *a, **k: _RandomReal(SEMENTE)):
        out = execute_clash_job(db, pedido)
    # Sem o gift de novo: o teste seguinte precisa partir do zero.
    for uid in (LEFT, RIGHT):
        for g in db.list_ego_gifts(GUILD, "player", uid):
            db.delete_ego_gift(GUILD, "player", uid, g["id"])
    return int(out["damage"]), out["winner"]


class EgoGiftNoDanoTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.db = Database(self.path)
        self.db.setup()
        self.db.create_character(GUILD, LEFT, "Esquerda")
        self.db.create_character(GUILD, RIGHT, "Direita")
        self.db.save_skill(GUILD, LEFT, Skill("Golpe", 4, 2, 2, "", "attack", 0, (), ("normal", "normal")))
        self.db.save_skill(GUILD, RIGHT, Skill("Rajada", 4, 2, 2, "", "attack", 0, (), ("normal", "normal")))

    def tearDown(self):
        self.db.close()
        os.remove(self.path)

    # ------------------------------------------------------------- a base
    def test_same_seed_really_repeats_the_same_roll(self):
        # Guarda: se a rolagem não fosse determinística, os deltas abaixo
        # mediriam sorte, não o gift.
        a_dano, a_vencedor = _rodada_com_gift(self.db)
        b_dano, b_vencedor = _rodada_com_gift(self.db)
        self.assertEqual(a_dano, b_dano)
        self.assertEqual(a_vencedor, b_vencedor)

    def test_sem_gift_o_clash_produz_dano(self):
        dano, vencedor = _rodada_com_gift(self.db)
        self.assertGreater(dano, 0, "o clash precisa ter produzido dano para o teste valer")
        self.assertIn(vencedor, {"left", "right"})

    # ------------------------------------------------- o gift no ATACANTE
    def test_base_power_do_gift_aumenta_o_dano(self):
        base, vb = _rodada_com_gift(self.db)
        com, vc = _rodada_com_gift(self.db, left_gift={"base_power_mod": 5})
        self.assertEqual(vc, vb, "a rolagem mudou de lado — o teste mediria outra coisa")
        self.assertGreater(com, base, "Base Power do gift precisa entrar no dano")

    def test_offense_level_do_gift_altera_o_resultado_inteiro(self):
        """Offense Level entra nos **dois** lugares — e isso é o certo.

        Ele já contava no Clash (`clash_execution.py:80-83`) e agora também no
        dano, então dar 3 de Offense pode **virar quem vence**. Aqui não dá para
        exigir "mesmo vencedor" como nos outros testes: se o Clash virou, a
        comparação de dano perde sentido. O que fica garantido é que o gift muda
        o resultado; o efeito no dano isolado está nos testes de Base e Defense.
        """
        base, vb = _rodada_com_gift(self.db)
        com, vc = _rodada_com_gift(self.db, left_gift={"offense_level_mod": 3})
        self.assertNotEqual(
            (com, vc), (base, vb),
            "Offense Level do gift precisa mudar o resultado (no Clash ou no dano)",
        )

    # ------------------------------------------------- o gift na DEFESA
    def test_defense_level_do_gift_no_alvo_reduz_o_dano(self):
        base, vb = _rodada_com_gift(self.db)
        com, vc = _rodada_com_gift(self.db, right_gift={"defense_level_mod": 4})
        self.assertEqual(vc, vb, "a rolagem mudou de lado")
        self.assertLess(com, base, "Defense Level do gift do alvo precisa entrar no dano")

    # ---------------------------------------------- não pode contar duas vezes
    def test_mods_da_ficha_zerados_no_clash_nao_somam_com_o_gift(self):
        # O Clash zera base_power_mod/coin_power_mod/offense_level_mod/defense_level_mod
        # da ficha (clash_execution.py:103). O gift vive em outro lugar, então
        # somar os dois não pode acontecer — e aqui só existe o gift mesmo.
        com_base, vb = _rodada_com_gift(self.db, left_gift={"base_power_mod": 5})
        com_base_e_off, vc = _rodada_com_gift(
            self.db, left_gift={"base_power_mod": 5, "offense_level_mod": 3},
        )
        self.assertEqual(vc, vb, "a rolagem mudou de lado")
        self.assertGreater(com_base_e_off, com_base,
                           "Base e Offense do gift precisam ser independentes")

    def test_gift_do_alvo_e_do_atacante_sao_independentes(self):
        so_esq, vb = _rodada_com_gift(self.db, left_gift={"base_power_mod": 5})
        os_dois, vc = _rodada_com_gift(
            self.db, left_gift={"base_power_mod": 5}, right_gift={"defense_level_mod": 4},
        )
        self.assertEqual(vc, vb, "a rolagem mudou de lado")
        self.assertLess(os_dois, so_esq, "Defense do alvo tem que reduzir o dano")
        self.assertLess(os_dois, so_esq, "Defense do alvo tem que reducir o dano")


if __name__ == "__main__":
    unittest.main(verbosity=2)
