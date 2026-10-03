"""Prova do editor de cláusulas de gift no Control Center.

O editor novo manda ``effects`` para o ``/api/ego_gifts/save``. Esta prova
faz o caminho inteiro, no banco real, para os 8 gifts:

  1. backup pela API do SQLite (WAL) — nunca ``shutil.copy``;
  2. lê as cláusulas gravadas;
  3. valida com o mesmo ``_validate_gift_effects`` que a tela usa;
  4. salva de volta **só** a chave ``effects`` (payload mínimo da tela);
  5. lê de novo e compara item a item.

Depois confere as duas regras que sustentam o editor:

  * payload **sem** ``effects`` não mexe em nada (o bug do "Salvar" da Central);
  * payload com cláusula inválida é recusado **antes** de escrever, e o que
    estava gravado continua lá.

    python testes/verify_editor_clausulas.py
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import control_center as cc  # noqa: E402

DB = ROOT / "clash_rpg.sqlite3"
BACKUPS = ROOT / "backups"


def backup() -> Path:
    """Backup pela API do SQLite. Em WAL, cópia de arquivo perde o que está
    no journal — é por isso que nunca se usa ``shutil.copy`` aqui."""
    BACKUPS.mkdir(exist_ok=True)
    alvo = BACKUPS / f"clash_rpg-antes-prova-editor-{time.strftime('%Y%m%d-%H%M%S')}.sqlite3"
    origem = sqlite3.connect(str(DB))
    copia = sqlite3.connect(str(alvo))
    origem.backup(copia)
    copia.close()
    origem.close()
    return alvo


def ler_tudo() -> dict[int, dict]:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        "SELECT id, guild_id, owner_kind, owner_id, name, tier, description,"
        " effects_json FROM ego_gifts ORDER BY id"
    ).fetchall()
    con.close()
    return {r["id"]: dict(r) for r in linhas}


def clausulas(row: dict) -> list:
    return json.loads(row["effects_json"] or "[]")


def main() -> int:
    problema = 0
    antes = backup()
    print(f"backup: {antes.name}\n")

    dados = ler_tudo()
    print(f"gifts no banco: {len(dados)}")
    total = 0

    for gid, row in dados.items():
        original = clausulas(row)
        total += len(original)

        # 3. a validação não pode recusar o que já está gravado
        try:
            cc._validate_gift_effects(original)
        except ValueError as exc:
            print(f"  id={gid} {row['name']}: RECUSADO pela tela -> {exc}")
            problema += 1
            continue

        # 4. payload da tela: nome/tier/descrição ecoados + effects
        cc.save_ego_gift({
            "guild_id": row["guild_id"], "kind": row["owner_kind"],
            "owner_id": row["owner_id"], "id": gid,
            "name": row["name"], "tier": row["tier"],
            "description": row["description"], "effects": original,
        })

        # 5. volta igual?
        regravado = clausulas(ler_tudo()[gid])
        if regravado != original:
            print(f"  id={gid} {row['name']}: MUDOU! {original} -> {regravado}")
            problema += 1
            continue
        print(f"  id={gid:>2} {row['name'][:34]:<36} "
              f"{len(original)} cláusula(s) -> ida e volta idêntica")

    print(f"\n{len(dados)} gifts, {total} cláusulas: "
          f"{'OK' if problema == 0 else f'{problema} PROBLEMA(S)'}")

    # --- regra 1: sem a chave, não mexe ----------------------------------
    # `name`/`tier`/`description` são ecoados com o valor real: a validação
    # da Central exige nome, e o UPDATE escreve tudo que estiver no payload.
    alvo = next(iter(dados))
    intacto = {
        "guild_id": dados[alvo]["guild_id"], "kind": dados[alvo]["owner_kind"],
        "owner_id": dados[alvo]["owner_id"], "id": alvo,
        "name": dados[alvo]["name"], "tier": dados[alvo]["tier"],
        "description": dados[alvo]["description"],
        # intencionalmente SEM "effects"
    }
    cc.save_ego_gift(intacto)
    depois = ler_tudo()[alvo]
    if (clausulas(depois) == clausulas(dados[alvo])
            and depois["tier"] == dados[alvo]["tier"]
            and depois["description"] == dados[alvo]["description"]):
        print("payload sem `effects`: cláusulas, tier e descrição intactos  OK")
    else:
        print("payload sem `effects` APAGOU alguma coisa  FALHOU")
        problema += 1

    # --- regra 2: cláusula ruim não entra --------------------------------
    quebrada = [{"trigger": "on_hit", "effect_type": "isso_nao_existe", "value": 1}]
    try:
        cc.save_ego_gift({**intacto, "effects": quebrada})
        print("cláusula inválida ACEITA  FALHOU")
        problema += 1
    except ValueError as exc:
        if clausulas(ler_tudo()[alvo]) == clausulas(dados[alvo]):
            print(f"cláusula inválida recusada e nada mudou  OK  -> {exc}")
        else:
            print("recusou, mas mudou o banco  FALHOU")
            problema += 1

    print("\nbackup de segurança:", antes.name)
    return 1 if problema else 0


if __name__ == "__main__":
    sys.exit(main())
