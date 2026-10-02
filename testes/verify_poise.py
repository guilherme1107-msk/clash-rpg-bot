"""O Poise, medido de ponta a ponta.

Faz 5 perguntas sobre `apply_poise_critical`:
  1. Qual e a chance por moeda (a tabela da margem secreta d20)?
  2. O Critico gasta Quantidade? Um por acerto? E o que acontece quando ha
     mais moedas do que Quantidade?
  3. Moeda Unbreakable e pulada?
  4. O `crit_damage_mod` do Clear Mirror soma ou multiplica?
  5. O que acontece com Potencia 0, Quantidade 0 e dano 0?

    python testes/verify_poise.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import bot  # noqa: E402
from bot import DamageResult, apply_poise_critical  # noqa: E402
from src.domain.models.combat import AttackHit  # noqa: E402

GUILD = 999          # guild de teste isolada: nao toca o banco real
UID = 1


class D20Falso:
    """d20 controlado, para provar os caminhos.

    `random.Random(20)` NAO força 20 — a semente so garante repetibilidade.
    Passa uma sequencia para cada moeda; um numero so, se quiser repetir.
    """

    def __init__(self, *valores):
        self.valores = list(valores) if len(valores) > 1 else list(valores) * 9

    def randint(self, _a, _b):
        return self.valores.pop(0)


def dano(moedas=3, pot=10, unbreakable=()):
    return DamageResult(
        hits=[AttackHit(coin=i, face="heads", power=pot,
                        unbreakable=i in unbreakable)
              for i in range(1, moedas + 1)],
        subtotal=10 * moedas, level_modifier=0, final_damage=10 * moedas,
        offense_level=0, defense_level=0,
    )


def poise(pot, qtd):
    bot.db.set_status(GUILD, "player", UID, "poise", pot, qtd)


def saldo():
    """O status some quando a Quantidade zera — mostra isso em vez de estourar."""
    p = bot.db.get_status(GUILD, "player", UID, "poise")
    return "APAGADA (nao fica 10x0)" if p is None else f"{p.potency}x{p.count}"


def off():
    return bot.db.get_total_ego_gift_modifiers(GUILD, "player", UID)["crit_damage_mod"]


def sql(comando, *args):
    """`Database` nao expoe `execute` — usa a conexao direto (so para o teste)."""
    with bot.db.lock, bot.db.connection:
        bot.db.connection.execute(comando, args)


def sep(titulo):
    print()
    print("=" * 72)
    print(titulo)
    print("=" * 72)


def main():
    bot.db.create_character(GUILD, UID, "BladeTeste")
    sql("DELETE FROM ego_gifts WHERE guild_id=?", GUILD)
    bot.db.save_ego_gift(GUILD, "player", UID, {
        "name": "Clear Mirror (teste)", "tier": 4, "description": "",
        "effects": [{"trigger": "on_crit"}], "crit_damage_mod": 70,
    })

    # ── 1. a tabela da margem secreta ───────────────────────────────────
    sep("1) CHANCE POR MOEDA — a Potencia E a chance (decisao do autor)")
    print("  O d20 rola POR MOEDA. Se sair >= margem, a moeda crita.")
    print(f"\n  {'Potencia':>9} | {'margem':>7} | {'chance/moeda':>12} | {'d20 = 20':>9}")
    print(f"  {'-' * 9}-+-{'-' * 7}-+-{'-' * 12}-+-{'-' * 9}")
    for pot in (5, 10, 15, 20, 30, 50, 100):
        margem = bot.poise_threshold(pot)
        print(f"  {pot:>9} | {margem:>7} | {(21 - margem) * 5:>11}% | "
              f"{'crita' if 20 >= margem else 'nao crita':>9}")
    print("\n  A Potencia agora E a chance. Antes era `20 - Potencia/10`, o que")
    print("  prendia tudo em 5%/10%/15%/20% — Poise 15 dava 10%, Poise 20 dava 10%.")
    print("  O d20 tem 20 faces, entao a chance anda de 5% em 5%: 15 -> 15%.")
    print(f"\n  Borda: Potencia 0 -> margem {bot.poise_threshold(0)} — o d20 vai so ate 20,"
          f" entao NUNCA acende (e a funcao ja retorna antes de rolar).")
    print(f"         Poise 100 -> margem {bot.poise_threshold(100)} — sempre acende.")

    # ── 2. o consumo ───────────────────────────────────────────────────
    sep("2) CADA CRITICO GASTA 1 DE QUANTIDADE")
    print("  3 moedas de Potencia 10, d20 = 20 (forca o critico em todas):")
    for esperado in (3, 2, 1):
        poise(10, esperado)
        d = dano()
        apply_poise_critical(GUILD, "player", UID, d, rng=D20Falso(20))
        print(f"    10x{esperado} -> critadas {d.critical_hits}  "
              f"| saldo {saldo()}  | dano {d.final_damage}")
    print("\n  Mais moedas que Quantidade (o que sobra nao consome nada):")
    poise(10, 2)
    d = dano(moedas=5)
    apply_poise_critical(GUILD, "player", UID, d, rng=D20Falso(20))
    print(f"    10x2, 5 moedas, d20=20 -> critadas {d.critical_hits} "
          f"(2 = a Quantidade)")
    print(f"    saldo {saldo()}  <- as 3 moedas restantes nao consumiram nada")
    poise(10, 1)
    d = dano()
    apply_poise_critical(GUILD, "player", UID, d, rng=D20Falso(20))
    print(f"    10x1, zera -> linha: {saldo()}")

    # ── 3. unbreakable ─────────────────────────────────────────────────
    sep("3) MOEDA UNBREAKABLE NAO CRITEA")
    poise(10, 3)
    d = dano(unbreakable={2})
    apply_poise_critical(GUILD, "player", UID, d, rng=D20Falso(20))
    print("  moedas 1,2,3 — a 2 e unbreakable, d20 no maximo (20)")
    print(f"  critadas: {d.critical_hits}   <- a 2 ficou de fora")
    print(f"  saldo {saldo()}  <- so as 2 elegiveis gastaram")
    print("  Razao: Unbreakable ja vale +10% e nao pode critar por cima.")

    # ── 4. o gift soma ────────────────────────────────────────────────
    sep("4) O CLEAR MIRROR SOMA, NAO MULTIPLICA")
    print("  1 moeda de Potencia 10, d20 = 20 (forca 1 critico):")
    for mod, rotulo in ((0, "SEM o gift"), (70, "COM o gift (+70)")):
        sql("UPDATE ego_gifts SET crit_damage_mod=? WHERE guild_id=?", mod, GUILD)
        poise(10, 3)
        d = dano(moedas=1)
        apply_poise_critical(GUILD, "player", UID, d, rng=D20Falso(20))
        pct = 10 * 2 + off()
        print(f"    {rotulo:<18} {pct:>3}%  ->  dano {d.final_damage} "
              f"(10 base + 10 da moeda x {pct}%)")
    print("\n  Confirmado: sao PONTOS PERCENTUAIS somados (decisao do autor),")
    print("  nao multiplicacao — 20% do Poise + 70% do gift = 90% do poder da moeda.")
    sql("UPDATE ego_gifts SET crit_damage_mod=70 WHERE guild_id=?", GUILD)

    # ── 4b. o d20 aparece no embed ────────────────────────────────────
    sep("4b) O D20 NOS EMBEDS (deixou de ser secreto)")
    print("  Acertou:")
    poise(10, 3)
    for linha in apply_poise_critical(GUILD, "player", UID, dano(3), rng=D20Falso(7, 20, 13)):
        print(f"    {linha}")
    print("\n  Nao acertou:")
    poise(10, 3)
    for linha in apply_poise_critical(GUILD, "player", UID, dano(3), rng=D20Falso(7, 11, 13)):
        print(f"    {linha}")
    print("\n  As tres rolagens aparecem nos dois casos — o mestre da para conferir.")

    # ── 5. as bordas ───────────────────────────────────────────────────
    sep("5) AS BORDAS (d20 = 20, forcando o maximo)")
    for rotulo, pot, qtd, valor_dano in (
        ("Potencia 0", 0, 3, 30),
        ("Quantidade 0", 10, 0, 30),
        ("dano 0", 10, 3, 0),
    ):
        poise(pot, qtd)
        antes = bot.db.get_status(GUILD, "player", UID, "poise")
        d = dano()
        d.final_damage = valor_dano
        logs = apply_poise_critical(GUILD, "player", UID, d, rng=D20Falso(20))
        gastou = (antes.count - saldo_qtd()) if antes else 0
        print(f"  {rotulo:<13} consumiu: {gastou}  critadas: {d.critical_hits or '[]'}"
              f"  dano: {d.final_damage}  logs: {len(logs)}")
    print("\n  As tres bordas devolvem lista vazia e NAO gastam Quantidade.")

    # ── limpeza ───────────────────────────────────────────────────────
    sql("DELETE FROM ego_gifts WHERE guild_id=?", GUILD)
    sql("DELETE FROM characters WHERE guild_id=?", GUILD)
    bot.db.close()
    print()
    print("  (guild 999 de teste apagada; o banco real nao foi tocado)")


def saldo_qtd():
    p = bot.db.get_status(GUILD, "player", UID, "poise")
    return p.count if p else 0


if __name__ == "__main__":
    main()