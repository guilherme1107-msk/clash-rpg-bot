# E.G.O Gifts — Desenho do sistema (v2)

> **v1** 04:35 → ~05:00 · **v2** ~05:00 → ~05:15 · **v2.1** ~05:15 → **05:29**
> (mtime real do arquivo). As divisões internas são **aproximadas**; a âncora
> confiável é o mtime — os relógios intermediários desta linha já foram
> corrigidos uma vez por estarem inventados.
>
> A **v2** incorpora 3 informações do autor que mudaram o desenho:
>
> 1. **Keyword nas fichas** ("ficha de poise", "aliados da Middle",
>    `unique bleed`) é a **base que falta** — 2 gifts dependem dela.
> 2. **Gifts entram no DANO também**, não só no Clash → **resolve a P9**.
> 3. **HP/Stagger = resolução MANUAL** — o bot publica a linha, o autor aplica.
>
> Matéria-prima (os 8 exemplares): `EGO_GIFTS.md`. Pauta: `PENDENCIAS.md`.

---

## 0. Decisões do autor (com o porquê)

| # | Decisão | Porquê |
|---|---|---|
| 1 | **Desenhar o sistema inteiro primeiro**, não implementar por degraus | Evitar retrabalho de desenho — foi contra a minha recomendação de começar simples. |
| 2 | **Afinidade e escudo persistente ficam de fora** | Afinidade: o bot não tem Sin Affinity. Escudo que não expira não existe hoje. |
| 3 | **"Recurso novo" reaberto depois** | Eu tinha contado como caro e estava errado (§7.4). Sem isso, os 3 gifts dele ficariam inertes. |
| 4 | **Lista livre de gifts, sem teto** | Tira uma variável do caminho; limite é fácil de adicionar depois. |
| 5 | **Mestre equipa e troca a qualquer momento** | Coerente: o mestre já cria inimigos e coloca skills no campo. |
| 6 | **Keyword na ficha é a base a construir** *(v2)* | *Reminiscence* e *Livro da vingança: Annex* só funcionam com gate por keyword. Hoje só `charge` tem algo parecido. |
| 7 | **Gift entra no CLASH e no DANO** *(v2 — resolve P9)* | *"Tem ego gifts que mexem no dano também, então entra tanto no clash quanto no dano."* |
| 8 | **HP/Stagger = resolução manual** *(v2)* | *"Não é pro bot alterar o dano recebido ou stagger, porém eu como Rosemary sempre atualizo isso — a passiva do cure 5% eu conseguiria administrar olhando o role."* |
| 9 | **Teto de gifts vem do Uptie** *(v2.1)* | *"Tem a ver com o uptie… o uptie 5 da Rose deixa ela colocar de 10–12 ego gifts, pelo que eu me lembro. Nem todos estão na mesma pessoa."* **Os números ele não lembra** → fica configurável (§7.7). |
| 10 | **`false_hunger` continua "Falsa Fome" na tela; é o keyword que marca `unique_bloodfeast`** *(v2.1)* | *"A falsa fome deve aparecer só como falsa fome, mas ser marcada como unique bloodfeast pelo sistema de keyword, que vamos ter que mexer depois."* (§7.5) |
| 11 | **O mestre precisa criar gift SEM passar por IA** *(v2.1)* | *"Quem faz eles é o mestre da mesa; o problema é um método de incorporar eles no sistema sem ter que passar por IA."* → **o editor já existe, é o da skill** (§3.1). |

---

## 1. O que já existe

| Peça | Estado | Onde |
|---|---|---|
| Tabela de gifts (dono, tier, descrição, ativo) | ✅ existe | `database.py:281` |
| **Equipar** — mestre, sem limite (decisões 4 e 5) | ✅ já é assim | Control Center → `/api/ego_gifts/save` |
| 5 mods fixos (Base/Coin/Clash/Offense/Defense) | ✅ entram no **nível do Clash** | `clash_execution.py:78-83` |
| Coluna `effects_json` (as cláusulas) | ⚠️ **gravada e nunca lida** | `database.py:289` |
| Condição por limiar e escala | ✅ `condition_status` / `_min` / `_per` / `_max_stacks` | `combat.py:50-56` |
| Status genérico (nome + potency + count) | ✅ | `status.py:7` |
| Gatilhos de skill | ✅ 10 | `combat.py:11` |
| Efeitos | ✅ 24 | `combat.py:15` |
| Ponto único por onde todos os efeitos passam | ✅ **`apply_skill_trigger`** | `bot.py:660` |
| Relógio de rodada | ✅ `battle_sessions.turn` + `phase` | `database.py:1772/1923` |

### 1.1 O achado que simplifica tudo

O caminho da Activity (`activity_clash_effects`, `bot.py:4733`) chama
`apply_skill_trigger` para **todos** os gatilhos (`on_use`, `clash_win`,
`clash_lose`, `before_attack`, `after_attack`, e via helpers `on_hit`,
`on_crit`, `heads_hit`).

**Se os efeitos de gift entrarem dentro de `apply_skill_trigger`, eles
funcionam na Activity inteira sem tocar em mais nenhum lugar.**

---

## 2. Bugs (Etapa 0)

### 2.1 `db.heal_character` não existe — crash latente

`bot.py:566` chama `db.heal_character(...)`. **Esse método não existe**
(só existe `heal_rosemary_profile_hp`) → seria `AttributeError`.

Hoje não estoura porque no banco ativo o gift está salvo como
`"The Familys Resentment"` (sem apóstrofo) e o código compara com
`"The Family's Resentment"` → falso. No `clash.sqlite3` o nome **está certo**
→ trocar o `DATABASE_PATH` e quebra.

### 2.2 Comportamento decidido por nome de gift

`bot.py:557-558` usa `g["name"] == "..."`. Frágil — e já provou ser.

### 2.3 Código morto

`has_carousel` é lido e nunca usado.

### 2.4 Os 3 gifts dele estão vazios

`Imperfect Eye`, `Carousel Figurine`, `The Family's Resentment` — Tier 5,
ativos, **mods 0** e **`effects_json = []`**. Hoje não fazem nada.

### 2.5 Plano

Remover `bot.py:555-567` de uma vez: mata o crash, o `if` por nome e o
código morto. **Não perde nada** (o bloco não produz efeito nenhum hoje; o
que ele fazia — cura de HP — passa a ser cláusula no **modo manual**, §8).

### 2.6 Bug novo: as listas do editor são cópias endurecidas e já divergiram

O editor de efeitos do Control Center tem as listas **escritas à mão no
HTML** (`control_center.html:587`). Comparado com o domínio, **já faltou**:

| Domínio | O que o editor mostra |
|---|---|
| `EFFECT_TYPES` = **24** | 22 — **falta `haste` e `reuse_coin`** |
| `EFFECT_TRIGGERS` = **10** | 8 — **falta `on_crit`** (`on_evade` só aparece em skill de esquiva) |
| `valid_conditions` (`skill_service.py:27`) | falta `haste` e as condições escalares (`sp`, `base_power`…) |

**Consequência:** a skill salva com esses valores **funciona no motor** (o
backend aceita), mas **o mestre não consegue escolher** — não aparece no
dropdown.

**Correção:** as listas vêm **do backend** (ex.: `/api/meta/effects`
devolvendo `EFFECT_TRIGGERS` / `EFFECT_TYPES`), em vez de serem copiadas.
Assim **nunca mais divergem**. Vale para o editor de skill **e** o de gift.

#### ✅ Feito na Etapa 0b

- `VALID_CONDITIONS` **erguido para constante de módulo** em `skill_service.py`
  (estava dentro da função) e exportado pelo pacote.
- `control_center.py` ganhou **`/api/meta/effects`** com `_ordered_display()`:
  a lista `DISPLAY_*` é **só ordem de exibição** — qualquer membro novo do
  domínio entra sozinho, no final, em ordem alfabética. **Por construção não
  dá para perder ninguém.**
- `control_center.html` passou as três listas de `const` para `let` vazias, e
  `init()` as preenche **antes** de `newSkill()`.
- `availableTriggers()` agora **filtra** `on_evade` em vez de anexar (evita
  duplicar, já que ele vem do backend); o servidor continua exigindo
  `skill_type == "evade"` (`skill_service.py:35`).
- Rótulos que faltavam: `on_kill` → *Ao matar*, `on_crit` → *Ao Critar*,
  `haste` → *Haste*, `reuse_coin` → *Reutilizar moeda*. `haste` entrou no
  `statusKinds` (mostra Potência + Quantidade) e `reuse_coin` ganhou linha
  própria no resumo, senão sairia *"Ganhar +5 Reutilizar moeda"*.
- **4 testes novos** em `tests/unit/test_control_center_meta.py` — cobrem o
  endpoint **e** a ligação do HTML. **123 testes no total.**

#### ⏳ Mesma derivação, ainda pendente

O editor da **Activity** (`ui/discord-activity/src/components/sheet/SkillsTab.jsx:7`)
tem a **4ª cópia** dessas listas: 23 de 24 — falta `consume_devotion_repressed`.
Fica em outro servidor (`activity_server.py`), não no Control Center →
**fora da Etapa 0**, registrado para não sumir.

---

## 3. Princípio

> **Um gift não é um sistema novo. É uma skill que não pertence a nenhuma skill.**

`ego_gifts.effects_json` **já é a coluna certa.** `SkillEffect` já valida
gatilho/efeito/condição/valor/dono, e `apply_skill_trigger` já sabe aplicar.

```
effects_json  →  tuple[SkillEffect, ...]  →  apply_skill_trigger(...)
```

**Sem tabela nova para cláusulas. Sem motor novo.**

### 3.1 ★ O mestre cria gift sem passar por IA — e o editor JÁ EXISTE

**A questão do autor (decisão 11):** *"quem faz eles é o mestre da mesa; o
problema é um método de incorporar eles no sistema sem ter que passar por
IA."*

**Resposta: o editor é o mesmo da skill, e ele já está pronto.**
`control_center.html` já tem o painel **"EFEITOS & CONDIÇÕES"** com o lema:

> *"Monte cada linha como no jogo: **quando ativa → o que faz → condição
> opcional**. Campos irrelevantes somem automaticamente."*

| O que já tem | Onde |
|---|---|
| Card por efeito, com resumo em português antes de salvar | `effectSummary()` (linha 601) |
| Dropdowns de gatilho, efeito, condição, dono, valor | `addEffect()` (603) |
| Campos que somem quando não fazem sentido | `refreshEffectCard()` (602) |
| **Validação** com mensagens claras | `skillValidationIssues()` (598) |
| **Presets** prontos (`Dano % escalável`, `Status On Hit`, `Buff por Charge`) | `addEffectPreset()` (596) |
| **Templates completos** — skills inteiras de um clique | `applySkillTemplate()` (597) |
| Limite de 20 efeitos por skill | mesmo `addEffectPreset()` |
| Serializa em `effects` → grava em `effects_json` | `effectData()` (604) |

**E o backend do gift já aceita:** `save_ego_gift` faz
`json.dumps(payload.get("effects", []))` (`database.py:2056`) — **a coluna
já espera essa lista.**

#### O que falta (é montar, não inventar)

1. **Montar o mesmo editor na ficha do gift** (hoje só tem nome, tier,
   descrição e 5 mods).
2. **Listas vindo do backend** (§2.6) — senão o editor de gift já nasce
   divergente.
3. **Campos novos** nos cards: `duration_turns`, `max_activations`,
   `activation_window`, `effect_owner` expandido, `condition_turn`.
4. **Os 4 gatilhos `session_*`** no dropdown de "Quando ativa".
5. **Templates dos 8 exemplares** — botões como os da skill
   (*"🩸 Bleed no hit"*), para o mestre partir de um pronto e só trocar
   números. **É isso que tira a IA do caminho.**
6. **Aviso de equilíbrio** (não bloqueante): linha no rodapé quando o gift
   *"só soma, sem custo"* — mesmo aviso do `preview_gifts.py`, mostrado a
   quem cria.

---

## 4. Os 7 blocos → campos

| # | Bloco | Campo | Estado |
|---|---|---|---|
| 1 | **Quando** | `trigger` | ✅ 10 · ❌ faltam 4 de sessão |
| 2 | **Se** | `condition_status` / `_min` / `_per` / `_owner` / `_operator` | ✅ existe · ❌ faltam 2 (§6) |
| 3 | **O quê** | `effect_type` + `value` / `count` / `coin` | ✅ 24 · sub-regra e multiplicador ficam para depois |
| 4 | **Para quem** | `effect_owner` | ✅ `auto`/`target`/`user`/`all_allies`/`faction` · ❌ falta `ally` (*"**um** aliado ganha 3 Poise Potency"* do Reminiscence precisa de regra de prioridade) |
| 5 | **Quanto dura** | **`duration_turns`** (novo) | ❌ |
| 6 | **Limite** | **`max_activations` + `activation_window`** (novos) | ❌ |
| 7 | **Ativação do gift** | colunas novas em `ego_gifts` + **keywords da ficha** | ❌ |

### 4.1 Campos novos em `SkillEffect`

`SkillEffect` é `@dataclass(frozen=True)` — campos **com default** não
quebram nada existente:

```python
duration_turns: int = 0
max_activations: int | None = None
activation_window: str = "combat"     # combat | round | skill
replace_of: str = ""                  # sub-regra: "em vez de <replace_of>"
condition_turn: int | None = None     # None = qualquer rodada
condition_min_coins: int = 0          # skill com ≥ N moedas
```

---

## 5. Gatilhos e o relógio

### 5.1 Os 10 existentes — reusam direto

`on_use` `on_hit` `heads_hit` `clash_win` `clash_lose` `before_attack`
`after_attack` `on_kill` `on_crit` `on_evade`.

Cobrem `[Clash Win]`, `[Ao Critar]`, "ao matar", "ao usar uma habilidade".

### 5.2 Quatro novos — `session_*`

```
session_encounter_start   session_combat_start
session_round_start       session_round_end
```

Prefixo `session_` para não confundir com o estágio `on_round_start` que
`execute_clash_job` já usa para injetar efeitos (é outra coisa).

### 5.3 Onde dispara

| Momento nos prints | Gatilho | Ponto |
|---|---|---|
| `[Início do Encontro]` | `session_encounter_start` | `Database.start_battle()` (`database.py:1772`) |
| `[Início de Combate]` | `session_combat_start` | `advance_when_all_ready`: `preparation → declaration` com `turn == 1` |
| `[Início da Rodada]` | `session_round_start` | `start_battle` (turno 1) + logo após `next_battle_turn()` (`database.py:1923`) |
| `[Primeira Rodada]` | `session_round_start` + `condition_turn == 1` | idem |
| `[Fim da Rodada]` | `session_round_end` | `advance_when_all_ready`: `resolution → preparation` |

`advance_when_all_ready` (`battle_flow.py:18`) é **uma função chamada pelos
dois lados** (bot `bot.py:2894` e Activity `activity_server.py:1027`) —
mais um ponto único. Como `battle_flow` é puro e não depende do Discord, o
disparo entra como **parâmetro opcional com callback** (`on_event=None`).

### 5.4 Limitação honesta

**Gatilhos de sessão só existem dentro de uma sessão de batalha.** Clash
avulso não tem turno. Os 10 de skill continuam valendo em qualquer lugar.

---

## 6. Condições — o que ainda falta

| Condição dos prints | Existe? |
|---|---|
| limiar de recurso (`≥ 6`, `≥ 50 Bloodfeast`) | ✅ `condition_status` + `condition_min` |
| escala (`para cada 12`, `para cada 50`) | ✅ `condition_per` |
| status consumido no crítico | ✅ `condition_status` + `consume_condition` |
| skill com **+5 moedas** | ❌ → `condition_min_coins` |
| **3 ou mais aliados com keyword** (Poise) | ❌ → **§7** `count_allies_with(keyword)` |
| **facção** (Middle, La Manchaland) | ❌ → **§7** keyword na ficha |
| **afinidade** (Gloom, Envy) | ❌ → **fora** (decisão 2) |
| **tag da skill** (Slash, Envy) | ❌ → `Skill` não tem `tags` → **fora** |

---

## 7. ★ A base que faltava: keyword, recursos e o teto do Uptie

**O que o autor apontou:** muitos gifts funcionam com coisas que **não
existem hoje** — "ficha de poise", "aliados da Middle", `unique bleed` ×
`bleed`. Só existe um caso parecido: `charge`.

### 7.1 O padrão `charge` (o único que existe)

`charge` tem **4 camadas** — e só ele tem:

| Camada | Onde |
|---|---|
| é um **status** com Potência + Quantidade | `STATUS_TYPES` |
| tem **teto** (20) | `status.py:24` |
| a ficha **declara** que a mecânica vale: `charge_potency_enabled` | coluna em `characters` / `enemies` |
| tem **função própria** — cada 10 gastos vira 1 Potência | `consume_charge()` (`database.py:825`) |

Rosemary tem a versão feita à mão: `false_hunger` + colunas próprias
(`false_hunger_max`, `false_hunger_consumed_total`) +
`character_rosemary_states` + `record_rosemary_consumption()`.

**Problema:** cada recurso virou código novo. Não escala.

### 7.2 Dois gifts dependem disso

| Gift | O que precisa |
|---|---|
| **Reminiscence** | *"3 ou mais aliados com habilidades de **Poise**"* → gate por keyword |
| **Livro da vingança: Annex** | *"todos os aliados da **Middle**"* + *"3 ou mais aliados da Middle"* |

E `unique_bleed` × `bleed` e o `unique_bloodfeast` da Rosemary **não existem
como status** — só como ideia.

### 7.3 Camada 1 — `characters.keywords`

**Uma lista de strings na ficha, marcada pelo mestre no Control Center.**

```json
["poise", "middle", "bleed", "unique_bleed", "unique_bloodfeast"]
```

Serve para **três coisas ao mesmo tempo**:

1. **Gate de gift** (bloco 7): `active_scope='faction'` +
   `active_tag='middle'` → *"todos os aliados da Middle"*.
2. **Gate por build**: `count_allies_with(keyword='poise') >= 3` →
   *"3 aliados de Poise"*.
3. **Declaração de recurso/único**: a ficha diz quais recursos ela usa e
   quais são **variantes únicas**. Rosemary marca `unique_bloodfeast`.

**Deliberadamente uma lista só** — não separar "keywords de build" de
"recursos". Se um dia precisar separar, é dividir a lista; não é retrabalho.

### 7.4 Variantes únicas = nomes de status comuns

`bleed` e `unique_bleed` são **dois status**, não uma família com regra.
Os prints já os listam separado (*"Bleed Potency, Bleed Count, ou Unique
Bleed"*) — o gift nomeia cada um. **Não precisa de mecanismo de família.**

Custa o mesmo que o "recurso novo": **~12 pontos do tipo "adicionar nome em
conjunto"** (`STATUS_TYPES`, `EFFECT_TYPES`, validação, ícone, texto de
ajuda). Nominais previstos: `unique_bleed`, `bloodfeast`,
`unique_bloodfeast`, `glimpse_of_precognition`.

### 7.5 ★ Rótulo de sistema × exibição (o caso Falsa Fome)

**Decisão 10 do autor:** *"a Falsa Fome deve aparecer só como Falsa Fome, mas
ser marcada como `unique_bloodfeast` pelo sistema de keyword."*

Ou seja: **a keyword é rótulo de sistema; a tela continua com o nome próprio.**

Hoje já existem 3 aliases espalhados, cada um no seu canto:

| Onde | O que faz |
|---|---|
| `skill_service.py:51` | `condition == "false_hunger"` → `special_condition` |
| `activityData.jsx:12` | `aliases = {…, false_hunger: …}` |
| `profile.special_effect_name` | nome de exibição **por ficha** (UI já existe) |

**Por baixo, `false_hunger` JÁ É `special_condition`** — `rosemary_panel.py:303`
(`"false_hunger": "combat_statuses.special_condition"`).

**Desenho:** o sistema de keyword vira **o lugar único** desses aliases:

```python
KEYWORD_ALIASES = {"false_hunger": "unique_bloodfeast"}
```

- **exibição**: continua *"Falsa Fome"* — nada muda em lugar nenhum;
- **gate de gift**: a ficha marca `unique_bloodfeast` e o gift que pede isso
  encontra;
- hoje existe **1 caso**; se aparecer mais, vira dado em tabela (não código).

### 7.6 Camada 2 — mecânica por recurso (depois)

`charge_potency_enabled` + `charge_spent` são coluna e código **por recurso**.
Generalizar isso (uma tabela de mecânicas ou equivalente) **não trava nenhum
gift** — nenhum dos 8 exemplos exige converter recurso em Potência.

→ **Fora da 1ª leva.** Registrado aqui para não sumir.

### 7.7 ★ Teto de gifts por Uptie

**Decisão 9 do autor:** o limite de quantos gifts a ficha carrega vem do
**Uptie** — *"o uptie 5 da Rose deixa ela colocar de 10–12 ego gifts, pelo que
eu me lembro, mas nem todos estão na mesma pessoa."*

**O que já existe:** Uptie **1–5** está em `character_profiles.profile_json`
(`profile_service.py:51` → `max(1, min(5, …))`) e tem UI completa
(`UptieDisplay.jsx`, `progression.js` → `UPTIE_COSTS`/`UPTIE_UNLOCKS`, com
cerimônia). O `uptie_levels` do `rosemary_content.json` já traz
`uptie_required` por skill e passiva.

**O que falta:** só a regra **Uptie → teto de gifts**. E **os números o autor
não lembra** → fica configurável:

```python
# vazio = sem teto  →  é exatamente o comportamento de hoje
EGO_GIFT_MAX_BY_UPTIE = {}   # ex.: {1: 2, 2: 4, 3: 6, 4: 8, 5: 12}
```

- Enquanto estiver vazio, **nada muda** — a "lista livre, sem teto"
  (decisão 4) continua valendo;
- preenche quando ele tiver os números;
- o aviso de limite aparece no Control Center, junto do gift.

**Por que não é coluna na ficha:** a regra é **global** (vale para toda
ficha), não é atributo de uma ficha. Se um dia quiser teto por ficha, aí sim
vira coluna.

### 7.8 Gift de time × gift pessoal — já está coberto

O autor separou: *"tem gifts que funcionam pro time que tiver no encounter, e
os da Rose só 1 funciona em time e outros 2 é só dela."*

Isso **não é um campo novo do gift** — é o **bloco 4 (escopo)**, `effect_owner`:

| Como está escrito no print | `effect_owner` |
|---|---|
| *"Aumenta o Dano Crítico de **todos os aliados**"* | `all_allies` |
| *"[Efeito se aplica ao **usuário**]"* (Imperfect Eye) | `user` |

Ou seja: é o **mesmo gift** com cláusulas de escopos diferentes. Não precisa
de uma flag "gift de time".

---

## 8. ★ 3 modos de resolução (resolve o 🔒 de HP)

**O autor:** *"não é pro bot alterar o dano recebido ou stagger nas fichas,
porém eu como Rosemary sempre atualizo isso, então a passiva do cure 5% da
vida eu conseguiria administrar olhando o role."*

Ou seja: **a regra 🔒 não é "não pode aparecer" — é "o bot não aplica sozinho".**

| Modo | Exemplos | O que o bot faz |
|---|---|---|
| **Mecânico** | SP, status, mods, nível, dano | aplica sozinho |
| **Informativo** | Bleed, Sinking (P5) | linha em `RESOLUÇÃO DO DANO`; **nenhum número muda** |
| **Manual 🔒** | **HP**, Stagger | calcula e **publica a linha com o valor**; **quem joga aplica** |

→ Gift que cura HP (**Family's Resentment**, passiva de 5%) vira **modo
manual**: o embed diz *"Family's Resentment — curaria `12` de HP"* e o autor
aplica.

**Mantém o 🔒 intacto** — o bot continua sem alterar HP/Stagger no banco —
**e** faz o gift valer alguma coisa.

---

## 9. Tabelas

### 9.1 `ego_gifts` — estender (não substituir)

Já tem dono, tier, descrição, `effects_json` e os 5 mods. Falta o **bloco 7**:

```sql
ALTER TABLE ego_gifts ADD COLUMN active_status TEXT NOT NULL DEFAULT '';
ALTER TABLE ego_gifts ADD COLUMN active_min    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ego_gifts ADD COLUMN active_scope  TEXT NOT NULL DEFAULT 'self';
ALTER TABLE ego_gifts ADD COLUMN active_tag    TEXT NOT NULL DEFAULT '';
```

`active_*` = *"o gift só vale quando..."*. Vazio = sempre vale.

### 9.2 `characters.keywords` e `enemies.keywords` — nova

```sql
ALTER TABLE characters ADD COLUMN keywords TEXT NOT NULL DEFAULT '[]';
ALTER TABLE enemies    ADD COLUMN keywords TEXT NOT NULL DEFAULT '[]';
```

JSON list de strings (§7.3).

### 9.3 `ego_gift_state` — nova (duração + limite)

```sql
CREATE TABLE IF NOT EXISTS ego_gift_state (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id         INTEGER NOT NULL,
    owner_kind       TEXT NOT NULL,
    owner_id         INTEGER NOT NULL,
    gift_id          INTEGER NOT NULL,
    clause_idx       INTEGER NOT NULL,
    effect_type      TEXT NOT NULL,
    value            REAL NOT NULL DEFAULT 0,
    count            INTEGER,
    expires_turn     INTEGER,        -- NULL = não expira sozinho
    window_key       TEXT,           -- 'round:7' | 'combat' | 'skill:123'
    activations_left INTEGER,        -- NULL = sem limite
    UNIQUE (guild_id, owner_kind, owner_id, gift_id, clause_idx, effect_type)
);
```

- **Duração** (bloco 5) = `expires_turn`, limpo quando `battle.turn` passa.
- **Limite** (bloco 6) = `window_key` + `activations_left`.
- `get_total_ego_gift_modifiers()` (`database.py:2082`) passa a somar
  **colunas fixas + linhas ativas** — mesma assinatura, ninguém muda.

---

## 10. Onde dispara — 3 pontos no código inteiro

| Tipo de gatilho | Ponto único |
|---|---|
| 10 de skill | **`apply_skill_trigger`** — `effects = triggered_skill_effects(...) + triggered_gift_effects(...)`. O log marca a origem com `` `GIFT` 🎁 <nome> `` para o gift não se passar por efeito de skill. |
| `damage_percent` | **`apply_skill_damage_percent`** — entra como `(*skill.effects, *gift_effects)`. Nenhum dos 8 exemplares usa; ligado mesmo assim para não deixar armadilha silenciosa. |
| 4 de sessão | **`advance_when_all_ready`** (`battle_flow.py:18`) + **`start_battle`** (`database.py:1772`), via callback |
| Expiração de duração | junto do `round_start` — limpa `ego_gift_state` |

---

## 11. ★ P9 resolvido — gift entra no DANO

**Decisão 7:** *"entra tanto no clash quanto no dano."*

Hoje (verificado):

| Onde | Gift conta? |
|---|---|
| **Clash** — `clash_execution.py:80-83` (`left_ego`/`right_ego`) | ✅ sim |
| **Dano** — `clash_execution.py:136` | ❌ `winner_row["offense_level"] + winner_row["offense_level_mod"]` **sem ego** |
| **Dano (Modos)** — `clash_execution.py:138` | ❌ `Modifiers(winner_row["base_power_mod"], winner_row["coin_power_mod"], …)` **sem ego** |
| **Follow-up** — `clash_execution.py:156` e `158-160` | ❌ idem |

**Correção = 4 lugares**, e `left_ego`/`right_ego` já estão no escopo
(calculados nas linhas 78-79):

```python
winner_ego = left_ego if result.winner == "left" else right_ego
# 136:  + winner_ego["offense_level_mod"]
# 138:  + winner_ego["base_power_mod"], + winner_ego["coin_power_mod"]
# 156/158: idem para followup_ego
```

**Mexe em balanceamento** → é decisão do autor (já tomada) e vai com teste.

---

## 12. As 9 peças → como cada uma é feita

| # | Peça | Como |
|---|---|---|
| 1 | Onde guardar o gift | ✅ **já existe** — `ego_gifts` + `effects_json` |
| 2 | Disparo fora da skill | 4 gatilhos `session_*` + callback em 2 funções |
| 3 | Escopo de alvo | `effect_owner` += `all_allies` \| `faction` \| `ally` |
| 4 | Duração em rodadas | `duration_turns` + `ego_gift_state.expires_turn` |
| 5 | Contador de ativação | `max_activations` + `window_key` / `activations_left` |
| 6 | Recurso novo / único | nomes em `STATUS_TYPES` + `EFFECT_TYPES` (§7.4) |
| 7 | Regra de substituição | `replace_of` + hook antes de gravar · **fora da 1ª leva** |
| 8 | Multiplicador de ganho | hook na função que soma o recurso · **fora da 1ª leva** |
| 9 | Condição por aliados / keyword | **`characters.keywords`** + `count_allies_with(keyword)` (§7) |

---

## 13. Escopo da 1ª leva

### 📦 Estado no banco real (2026-10-01, 17:45)

Os **8 exemplares estão gravados**, um dono cada. Backup antes de escrever:
`backups/clash_rpg-20261001-174049.sqlite3`.

| Dono | Gift | Cláusulas |
|---|---|---|
| Rosemary Véspera | Imperfect Eye of Precognition | **6 (spec v2)** |
| Rosemary Véspera | Carousel Figurine | 0 · gate `la_manchaland` |
| Rosemary Véspera | The Familys Resentment | 0 |
| Pablo Suindara | Dreaming Electric Sheep | 0 |
| Pablo Suindara | Livro da vingança: Annex | 0 · gate `middle` ×3 |
| Blade | Clear Mirror, Calm Water | 0 |
| Blade | Reminiscence | 0 · gate `poise` ×3 |
| Zote | Volatile's earring | 0 |

**Só o Imperfect Eye funciona hoje** — as outras **21 cláusulas** dependem de
`session_*` (Etapa 4), `all_allies` (bloco 4), duração (Etapa 5) ou de recursos
que não existem (Protection, Envy). A lista com o motivo de cada uma é impressa
por `testes/test_gifts.py`. **Nenhuma ficha tem keyword marcada**, então os 3
gates estão inertes até o mestre marcar.

### ✅ Entra

- Conserto dos bugs (§2.5)
- **Listas do editor vindas do backend** — `haste`, `reuse_coin` e `on_crit`
  hoje não aparecem no dropdown (§2.6)
- `effects_json` → `SkillEffect` → `apply_skill_trigger`
- **Editor de cláusulas no Control Center** — o mesmo da skill, montado no
  gift + **templates dos 8 exemplares** (§3.1) ★
- Status novos (`bloodfeast`, `unique_bleed`, `glimpse_of_precognition`…)
- 4 gatilhos `session_*`
- Duração e limite (`ego_gift_state`)
- Escopo `all_allies` / `faction` / `ally`
- Gate de ativação do gift (§9.1)
- **`characters.keywords` + `count_allies_with`** (§7.3)
- **Alias de keyword** — `false_hunger` → `unique_bloodfeast`, com exibição
  intacta ("Falsa Fome") (§7.5)
- **Teto por Uptie** — mecanismo pronto (`EGO_GIFT_MAX_BY_UPTIE`),
  **números pendentes** (§7.7)
- `condition_min_coins`
- **Modo manual para HP/Stagger** (§8)
- **Gift no dano — P9** (§11, 4 lugares)

### ❌ Não entra

| Item | Porquê |
|---|---|
| **Afinidade** (Gloom, Envy…) | o bot não tem Sin Affinity (decisão 2) |
| **Escudo persistente** | escudo hoje só existe dentro de uma defesa |
| **Tag da skill** (Slash, Envy) | `Skill` não tem `tags` — e nenhum dos 3 gifts ativos depende |
| **Sub-regra** (`replace_of`) | hook no meio da lógica normal |
| **Multiplicador de ganho** (dobrar Bloodfeast) | hook na função de ganho |
| **Camada 2 — mecânica por recurso** (§7.6) | não trava nenhum gift |

### Consequência honesta

| Gift | O que roda na 1ª leva | O que não roda |
|---|---|---|
| **Imperfect Eye** | `clash_win` → `glimpse_of_precognition` ✅ · **entra no dano** ✅ | escalonamento por stack depende da Etapa 4 |
| **Carousel Figurine** | `bloodfeast` existe ✅ · dano ✅ | `[Primeira Rodada]` depende do relógio · "dobrar" fica de fora |
| **Family's Resentment** | "para cada 50 Bloodfeast → +1 Offense" ✅ · dano ✅ | **cura de HP → modo manual** (linha, aplica você) · "dobrar" fica de fora |

---

## 14. Plano de implementação

Cada etapa deixa o sistema funcionando e os testes verdes.

| Etapa | Entrega | Construir |
|---|---|---|
| **0 ✅** | Conserto dos bugs | remover `bot.py:555-567` · `/api/meta/effects` + listas no backend (§2.6) · 4 testes |
| **1 🟡** | Gift com efeito **nos 10 gatilhos de skill** + **mestre cria sem IA** | ✅ **back feito** — `_effects_from_row` → `triggered_effects` (extraído de `triggered_skill_effects`, 40 call sites intactos) → `db.list_active_ego_gift_effects` → `triggered_gift_effects` → 2 pontos (`apply_skill_trigger` + `apply_skill_damage_percent`) · ⏳ **UI**: montar o editor da skill no gift + templates (§3.1) |
| **2 ✅** | Status novos (`bloodfeast`, `unique_bloodfeast`, `unique_bleed`) | **feito (2026-10-01)** — `STATUS_TYPES` (fora do decaimento: são recurso, não DoT) · `EFFECT_TYPES` · ícones 🍷/🥸 (batem com `control_center.html`) · label/descrição do editor · `DISPLAY_EFFECT_TYPES` · `BUILDER_EFFECT_LABELS`/`_ICONS` · log própria (`+300 Bloodfeast`, sem "Pot./Qtd.") · **16 testes** em `testes/test_keywords.py` |
| **3 ✅** | **`characters.keywords`** + `count_allies_with` + gate do gift + **alias** (`false_hunger`→`unique_bloodfeast`) + **teto por Uptie** | **feito (2026-10-01)** — `keywords` em `characters` **e** `enemies` · `normalize_keywords`/`get_keywords`/`set_keywords`/`count_allies_with` · `active_status`/`active_tag`/`active_scope`/`active_min` em `ego_gifts`, filtrado dentro de `list_active_ego_gift_effects` (nenhum call site muda) · `KEYWORD_ALIASES` · `EGO_GIFT_MAX_BY_UPTIE = {}` (vazio = nada muda) + `ego_gift_limit_warning` **não bloqueante** no retorno de `save_ego_gift` · **UI**: `registerSheetKeyword()` com checkbox que grava via `/api/entity/keywords` |
| **4 ✅** | `[Início da Rodada]` e cia. | **feito (2026-10-01, 18:15 → 18:19)** — 4 gatilhos `session_*` · `Database.session_hook` (2 pontos: `set_battle_phase` e `next_battle_turn`) · `bot.apply_session_trigger` · `condition_turn` com **falha fechada** · `activity_server.py` liga o gancho · **16 testes** em `testes/test_session_triggers.py` |
| **5** | Duração (`por 2 rodadas`) e limite (`1× por rodada`) | `ego_gift_state` · expiração · somatório |
| **6 ✅** | **P9 — gift no dano** (§11) | **feito (2026-10-01, 17:57 → 18:03)** — 2 lugares em `clash_execution.py` (dano do vencedor **e** follow-up do perdedor) + os **2 caminhos unopposed** do `bot.py`, que ignoravam o gift por inteiro · **7 testes** em `testes/test_ego_damage.py` |
| **7** | **Modo manual** para HP/Stagger (§8) | texto de gift vira linha publicada, sem tocar em banco |
| **8** | Mecânica nova | sub-regra · multiplicador · tags de skill · afinidade 🔒 · escudo persistente · camada 2 |

---

## 15. Perguntas abertas

### ✅ Resolvidas nesta rodada

1. **P9 — gift no dano?** → **RESOLVIDO (decisão 7):** entra no Clash **e**
   no dano — 4 lugares em `clash_execution.py` (§11).
2. **`unique_bloodfeast` × `false_hunger`?** → **RESOLVIDO (decisão 10):**
   mantém *"Falsa Fome"* na tela; é a **keyword** que rotula
   `unique_bloodfeast` (§7.5). Nenhum rename.
3. **Teto de gifts?** → **RESOLVIDO PARCIALMENTE (decisão 9):** o teto vem do
   **Uptie** (§7.7) — faltam só os **números** (ver 4).
7. **Quem marca as keywords?** → **RESOLVIDO (2026-10-01):** o **mestre**, pelo
   Control Center, na aba 〔 KEYWORDS 〕 da ficha (`registerSheetKeyword()` →
   `/api/entity/keywords`). É assim que está implementado.
8. **"Aliado" inclui o próprio?** → **RESOLVIDO (2026-10-01): inclui.**
   O autor esclareceu que é *"só o modo de escrever do Limbus, que tem uma
   visão mais geral de time"*. Então `count_allies_with()` conta **todos os
   sinners do encontro, o dono contando** — *"3 ou mais aliados da Middle"*
   quer dizer **3 no total**. O que é "encontro" está em
   `Database.encounter_member_ids()`: com batalha ativa, o painel dela; sem
   batalha, o grupo do servidor.
9. **O que é uma keyword?** → **RESOLVIDO (2026-10-01):** *"os uniques e os
   base effects, não as variações de tremor — só o tremor base"*. As
   variações (Scorch, Reverb, Fracture, Clockwinding…) são **tipos de pilha**,
   não rótulos de ficha, e ficam só no catálogo de emojis.

### ⏳ Ainda abertas

4. **Números do Uptie → teto de gifts.** O autor lembra que Uptie 5 dá
   *"10–12"*, mas não os dos níveis 1 a 4. Preencher
   `EGO_GIFT_MAX_BY_UPTIE` quando ele tiver — **enquanto estiver vazio,
   nada muda**.
5. **Preço próprio de cada gift.** Mesmo com teto por Uptie,
   `scripts/preview_gifts.py` avisou que somar tudo sem custo faz virar
   dominante equipar todos. A defesa é que **cada gift traga o próprio
   preço** (condição, `max N`, `1× por rodada`) — que é como os 8
   exemplares do RPG já funcionam. Confirma?
6. **Gatilhos de sessão em Clash avulso** (sem sessão): aceitar que não
   disparam (§5.4), ou criar sessão implícita?

---

*Documento de desenho. Pauta em `PENDENCIAS.md`; exemplares em `EGO_GIFTS.md`.*
