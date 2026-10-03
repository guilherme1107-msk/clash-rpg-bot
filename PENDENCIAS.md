# Pendências de combate

> Anotado em 2026-09-29 a partir da análise comparativa com a Limbus Company.
> **Nada aqui foi corrigido ainda.** Itens 🔒 estão congelados por decisão do autor.

---

## 🟢 P7 — Etapas 2 e 3 CONCLUÍDAS (2026-10-01, 09:53 → 10:03)

**Por que essa ordem:** o autor escolheu *"Bloodfeast + keywords"* porque é o
que **destrava 3 gifts de uma vez** (The Family's Resentment, Carousel
Figurine e Livro da vingança). Antes, `bloodfeast` nem existia como nome.

**Horários reais (mtime):** domínio `09:53` · bot `09:54` · banco `09:59` ·
teste `09:59` · API `10:00` · HTML `10:01` · desenho `10:02` · este registro `10:03`.

### Etapa 2 — 3 status novos (§7.4)

`bloodfeast`, `unique_bloodfeast`, `unique_bleed` — **~12 pontos cada**, exatamente
o que o desenho estimou. São **recurso, não DoT**: ficam em `STATUS_TYPES` mas
`on_round_end` não os conhece, então **não decaem sozinhos**. Se um gift exigir
decaimento, é adicionar a regra deles à mão ali.

| Ponto | Onde |
|---|---|
| `STATUS_TYPES` + comentário do porquê de não decair | `src/domain/status.py` |
| `EFFECT_TYPES` (sem isso o ramo de status nem liga) | `src/domain/models/combat.py` |
| ícone 🍷 `bloodfeast` · 🥸 `unique_bleed` · 🍷 `unique_bloodfeast` | `bot.py` `STATUS_ICONS` |
| `STATUS_LABELS` / `STATUS_DESCRIPTIONS` | `bot.py` |
| `BUILDER_EFFECT_LABELS` + `BUILDER_EFFECT_ICONS` | `bot.py` |
| `DISPLAY_EFFECT_TYPES` (lista do editor) | `control_center.py` |

**Decisão de texto do log:** recurso **não** mostra "Pot. / Qtd." — aparece
`+300 Bloodfeast → 300`. `RESOURCE_STATUS_TYPES` cuida disso. Mostrar
*"+300 Pot. / +1 Qtd."* para Bloodfeast confundiria quem lê o combate.

**Ícones seguem o que o Control Center já usava** (`control_center.html:410` 🍷 e
`:415` 🥸), para bot e tela não brigarem. São **Unicode de reserva** — se o autor
mandar os custom, é `EMOJI_STATUS_BLOODFEAST` / `EMOJI_STATUS_UNIQUE_BLEED` no `.env`.

### Etapa 3 — keywords da ficha (§7.3) + gate do gift (bloco 7) + teto (§7.7)

**Colunas novas:** `characters.keywords` e `enemies.keywords` (JSON list) ·
`ego_gifts.active_status` / `active_tag` / `active_scope` / `active_min`.
Todas com **migração idempotente** e valor default que reproduz o comportamento
antigo (lista livre, gift sempre ativo) — **nada quebra para quem já tem dado**.

**Helpers** (`database.py`):
- `normalize_keywords()` — minúsculas, sem vazios, alias aplicado, **nunca lança**
  (ficha mal gravada não pode derrubar o meio do combate);
- `get_keywords()` / `set_keywords()`;
- `count_allies_with(guild, kind, id, keyword)` — quantos **aliados** (fora do
  próprio) marcaram a keyword → é o *"3 ou mais aliados da Middle/Poise"*;
- `character_uptie()` + `ego_gift_limit_warning()` — **não bloqueante**.

**Gate (bloco 7)** — `_gift_gate_ok()`, filtrado **dentro de
`list_active_ego_gift_effects`**: nenhum call site muda, o gift que a ficha não
habilitou simplesmente não aparece. Gift sem gate continua sempre ativo.

| Coluna | Significado |
|---|---|
| `active_status` | keyword que a **própria ficha** precisa declarar |
| `active_tag` + `active_scope='allies'` | quantos **aliados** precisam declarar |
| `active_min` | mínimo desses aliados (`0` → `1`) |

**Alias (§7.5, decisão 10):** `KEYWORD_ALIASES = {"false_hunger": "unique_bloodfeast"}`
— a tela continua **"Falsa Fome"**, o sistema é que rotula. Mesma preocupação do
`false_hunger → special_condition` que já existia, agora no mesmo arquivo.

**Teto por Uptie (§7.7, decisão 9):** `EGO_GIFT_MAX_BY_UPTIE = {}` **vazio de
propósito**. Enquanto estiver vazio, **nada muda**; preenche quando o autor tiver
os números. Quando houver, `save_ego_gift` já devolve `limit_warning`.

**UI (o ponto que o autor apontou):** `registerSheetKeyword({key, icon, name,
desc, html})` em `control_center.html` — os 7 cards entram na aba **〔 KEYWORDS 〕**
da ficha, cada um com checkbox que grava em `/api/entity/keywords`. O estado é
recarregado em **toda** abertura (o painel é montado 1x só).

**Verificação:** `py_compile` OK · `node --check` nos blocos `<script>` do HTML OK ·
**109 testes OK** = `test_database` 40 + `test_engine` 38 + `test_tremor` 15 +
**`test_keywords` 16 (novo)**.

### ⚠️ Estado depois das respostas do autor

**Respondido na mesma rodada:**

1. ~~**Aliado = mesma ficha e mesmo servidor, menos o próprio**~~ →
   **RESOLVIDO:** o autor esclareceu que aliado é **todos os sinners do
   encontro, o próprio incluído** — *"só o modo de escrever do Limbus, que tem
   uma visão mais geral de time"*. `"3 ou mais aliados da Middle"` = **3 no
   total**. E "encontro" agora tem nome: `Database.encounter_member_ids()`
   devolve o **painel da batalha ativa** quando existe, senão o grupo do
   servidor. Testado nos dois sentidos.
2. ~~**§15 pergunta 7 — quem marca as keywords?**~~ → **RESOLVIDO:** **mestre**,
   pelo Control Center, igual equipar gift. É como está implementado.
3. ~~**Emojis faltando**~~ → **RESOLVIDO:** o autor mandou o catálogo inteiro
   (base effects, uniques e as 11 variações de Tremor). Rastreados abaixo.

**Continua em aberto:**

4. **`EGO_GIFT_MAX_BY_UPTIE` vazia** — continua precisando dos números do autor.
5. **Os 3 status são inertes** — gravam e são lidos como condição, mas não têm
   regra própria (não decaem, não consomem). Correto para os gates de hoje.
6. **"Habilidades que infligem Bleed / Unique Bleed"** (Family's) é **tag de
   skill**, não status → fica na **Etapa 8**. O autor confirmou que pode ser
   assim por enquanto.
7. **Facções ainda sem emoji:** `middle` e `la_manchaland` estão com Unicode
   provisório (🎭 / 🎠) — o autor disse que manda depois.
8. **`unique_bloodfeast` reusa o emoji do Bloodfeast** — ainda não existe um
   `Efeito_Bloodfeast_Unique`; quando vier, é uma linha.

### 🎨 Catálogo de emojis (rastreado em 2026-10-01)

O autor enviou os emojis. Ficaram num **lugar só**, para não se perderem em
defaults espalhados por vários arquivos:

| Onde | O que |
|---|---|
| `bot.py` `EGO_EMOJI` | 8 **base effects** + 5 **variantes únicas** |
| `bot.py` `TREATMENT_VARIANT_EMOJI` | **11 variações de Tremor** — tipos de pilha, **não** keywords |
| `bot.py` `STATUS_ICONS` | defaults passam a vir do catálogo; o `.env` continua mandando |
| `control_center.py` / `activity_server.py` | mesmo catálogo, para tela e bot não divergirem |
| `control_center.html` `kwStyles` | sublinha as palavras nos textos das fichas |

**Só o Tremor base é keyword** — as variações ficam no catálogo de emojis, não
na listinha. A listinha da ficha ficou com **8 base effects + 5 uniques + 2 facções**.

---

## ✅ P7 — Item 4 CONCLUÍDO: gifts gravados no banco real (2026-10-01, 17:40 → 17:50)

**Por que o banco ainda não tinha sido tocado:** a regra era medir a capacidade
programática **sem mexer no que o codex e o antigravity fizeram**. O autor liberou
às 17:36 — *"pode começar a mudar o banco real"*.

**Ordem real (mtime):** backup + migrações `17:40:49` · gravação `17:45` ·
fábrica de gifts reescrita `17:47` · guarda da do Imperfect Eye `17:50`.

### 1. Backup antes de qualquer escrita

`backups/clash_rpg-20261001-174049.sqlite3` — **2.609.152 bytes**, conferido
(29 tabelas · 17 fichas · 92 skills · 3 gifts). Feito com a **API de backup do
SQLite**, não `shutil.copy`: o banco está em WAL, e copiar o arquivo cru deixaria
de fora o que ainda estivesse no `-wal` — o "backup" nasceria incompleto.

Depois do backup, `Database.setup()` rodou as migrações (o `setup_hook()` do bot
é quem normalmente faz isso, e o bot não tinha subido desde a Etapa 3).

### 2. Os 8 gifts

| Dono | Gift | Tier | Cláusulas | Gate |
|---|---|---|---|---|
| **Rosemary Véspera** | Imperfect Eye of Precognition | 5 | **6** (spec v2) | — |
| Rosemary Véspera | Carousel Figurine | 5 | 0 | `la_manchaland` |
| Rosemary Véspera | The Familys Resentment | 5 | 0 | — |
| **Pablo Suindara** | Dreaming Electric Sheep | 5 | 0 | — |
| Pablo Suindara | Livro da vingança: Annex | 5 | 0 | `middle` ×3 no encontro |
| **Blade** | Clear Mirror, Calm Water | **4** | 0 | — |
| Blade | Reminiscence | 5 | 0 | `poise` ×3 no encontro |
| **Zote** | Volatile's earring | 5 | 0 | — |

**Correção de dono:** o registro antigo dizia que **Zote** tinha E.G.O *skill*,
não gift. O autor corrigiu: **Volatile's earring é do Zote**. E
`Pingente: Presente da Rebeca` (do Pablo) **continua fora**, como combinado.

**Tier do Clear Mirror** é **4** porque a ficha marca `IV`; os dois `[?]` dos
prints (Reminiscence e Livro) foram para 5 e precisam de confirmação.

**`description` dos 5 novos ficou vazio** de propósito — o texto é do autor e o
Control Center tem campo pra isso.

### 3. Por que só o Imperfect Eye tem cláusulas

As **6 cláusulas da spec v2** foram gravadas **verbatim** do teste de fábrica, e
antes de gravar eu validei cada uma: `_effects_from_row` descarta cláusula
inválida **em silêncio**, então uma chave errada faria o gift parecer gravado e
não funcionar. As 6 passaram (incluindo `condition_operator`, que existe).

**Prova de que funciona** numa cópia do banco real, sem injetar nada:
```
Potência ganha por vitória : [2, 4, 6, 8, 10]   (2 × Glimpse)   BATEU
Tremor final               : 30x1   (alvo começou com 6 Count)     BATEU
Glimpse final              : 5x5
Mods do gift               : clash_power +5 · coin_power +2
[Ao Critar] #1 e #2 passam, #3 e #4 bloqueiam por "limite de 2× por rodada"
```
> A tabela `2/4/6/8/10` da spec é o **valor por vitória**, não o estado final: a
> Potência **acumula** no alvo enquanto o Tremor Burst vai tirando 1 Count.

**As outras 21 cláusulas seguem de fora**, cada uma com o motivo (o
`testes/test_gifts.py` imprime a lista completa). As três que mais destravam:
`[Início da Rodada]` e `[Início do Encontro]` → **Etapa 4** · escudo que não
expira → Etapa 8 · "todos os aliados" (`all_allies`) → bloco 4.

### 4. O que mudou nos testes de fábrica

Os dois abortavam com *"cópia veio suja"* quando o `effects_json` não estava
vazio — deixa de valer agora que o banco **tem** a spec gravada:

- `testes/test_gifts.py` — virou **somente leitura**. Antes injetava a spec **v1**
  por cima do que estava no banco (duas cópias da spec, prone a divergir);
  agora imprime o que está gravado e o que ainda não dá.
- `testes/test_imperfect_eye.py` — a guarda virou **comparação**: se o banco
  divergir da `SPEC_V2` de referência, avisa em voz alta e grava a de referência
  na cópia. Hoje: *"spec v2 JÁ GRAVADA no banco bate com a de referência."*

### 5. O que ainda depende do autor

- **Nenhuma ficha tem keyword marcada** (`keywords=[]` em todas). Os 3 gates
  gravados estão **inertes** de propósito — é o mestre quem marca, na aba
  〔 KEYWORDS 〕. Nada quebra: gift sem gate nenhum já valia antes.
- **Tiers** de Reminiscence e Livro (prints com `[?]`).
- **`description`** dos 5 gifts novos.

---

## ✅ P7 — Etapa 6 CONCLUÍDA: **P9 fechada** (2026-10-01, 17:57 → 18:03)

**O que era:** pela decisão 7 (*"entra tanto no clash quanto no dano"*) o gift
contava em `resolve_clash` e ficava **de fora de `resolve_damage`**. Um
E.G.O Gift com Base Power, Offense Level ou Defense Level **não mudava dano
nenhum**.

**Onde faltava (4 pontos, mais 2 que o desenho não tinha contado):**

| Onde | Antes |
|---|---|
| `clash_execution.py` — dano do vencedor | `offense_level` + `offense_level_mod` **sem** `winner_ego` |
| `clash_execution.py` — `Modifiers` | `base_power_mod` / `coin_power_mod` **sem** `winner_ego` |
| `clash_execution.py` — follow-up do perdedor | os 4, **sem** `loser_ego` / `winner_ego` |
| `bot.py` `execute_unopposed_job` | **nada** — o ataque sem Clash ignorava o gift por inteiro |
| `bot.py` `execute_enemy_unopposed_job` | **nada** — idem |

**Não é dupla contagem:** o Clash zera `base_power_mod`, `coin_power_mod`,
`offense_level_mod` e `defense_level_mod` da ficha (`clash_execution.py:103`).
Os mods do gift vivem em `ego_gifts` (persistentes) mais o que
`get_total_ego_gift_modifiers` tira do Glimpse — outro lugar, outra vida.

**Incluí o Defense Level do alvo**, que o desenho não listava: sem ele um gift
que dá defesa não reduzia dano nenhum, e a decisão 7 seria verdadeira só pela
metade.

**A armadilha do teste (vale registrar):** a primeira versão media **sorte, não
gift**. Duas rodadas "idênticas" deram 4 e 8 de dano. Causa: `engine.py` faz
`rng = rng or random.Random()` — um `Random` **novo**, semeado pelo SO — então
`random.seed()` de fora não tem efeito nenhum. A semente tem que entrar por
`mock.patch` na fábrica `random.Random`. E o **SP precisa ser zerado** entre
corridas, porque o Clash confirma ±5 e a Sanidade move a chance de Heads.

**O que ficou fora do alcance do teste:** `Offense Level` não tem teste de "mesmo
vencedor, dano maior" — e não tem como ter. Ele já contava no Clash, então dar 3
dele **vira quem ganha**; comparar dano entre lados diferentes não mede nada. O
teste dele afirma o que é verdade: o gift muda o resultado. O efeito no dano
isolado fica coberto pelos testes de Base Power e Defense Level.

**Verificação:** `py_compile` OK em 5 arquivos · **118 testes OK**
(`test_database` 40 + `test_engine` 38 + `test_keywords` 18 + **`test_ego_damage` 7 (novo)** + `test_tremor` 15) · as 2 fábricas rodam.

---

## 🔧 Tier corrigido (17:57)

O autor corrigiu dois tiers que eu tinha chutado a partir dos prints:

| Gift | Estava | Agora | Classe |
|---|---|---|---|
| Reminiscence | T5 | **T3** | HE |
| Livro da vingança: Annex | T5 | T5 | WAW |

**`classe` não tinha onde morar.** A tabela `ego_gifts` não tem essa coluna e o
`description` é texto do autor — não inventei campo nem escrevi por cima.

**RESOLVIDO (18:10 → 18:11), com o aval do autor:**

- Coluna `gift_class` em `ego_gifts` (migração idempotente, default `''`),
  gravada por `save_ego_gift` e **normalizada para MAIÚSCULA**;
- Campo **Classe** nos **4 formulários** do editor (2 da ficha, 2 da página de
  E.G.O Gifts), com `ZAYIN / TETH / HE / WAW / ALEPH` + "sem classe";
- O badge do card era `TIER V [ℵ]` **fixo** — classe derivada do tier. Teria
  chumbado: o Livro é **T5 WAW** e a Reminiscence **T3 HE**. Agora é
  `TIER III [HE]`, com o tier em numeral romano e a classe **gravada**;
- **As 8 descrições** preenchidas com o texto das prints (`EGO_GIFTS.md`
  §1.1–1.8), usando o emoji custom que o bot tem e deixando em Unicode o que ele
  não tem (Sanidade 🪙, Protection 🛡️, Slash 🗡️, Envy 💜, Gloom ❄️, as setas).

---

## ✅ P7 — Etapa 4 CONCLUÍDA: os 4 gatilhos `session_*` (2026-10-01, 18:15 → 18:19)

Entraram `session_encounter_start`, `session_combat_start`, `session_round_start`
e `session_round_end` no `EFFECT_TRIGGERS`, mais o `SkillEffect.condition_turn`
dos prints (*"[Primeira Rodada]"*).

### Onde dispara — e um desvio do desenho, de propósito

O desenho (§5.3) punha `[Início do Encontro]` em `Database.start_battle()`. Mas
**nesse código os participantes ainda não existem naquele instante** (o
`join_battle` vem depois), então o gift dispararia para uma lista vazia. Movido
para `set_battle_phase(..., "declaration")`, que é quando a rodada realmente
começa e o painel já tem gente. Bônus: só **2 pontos de gancho**, e
`battle_flow.py` não encostou.

| Momento | Gancho |
|---|---|
| Rodada 1 abrindo | `encounter_start` → `combat_start` → `round_start` |
| Rodada 2 em diante | só `round_start` |
| Virando a rodada | `round_end` em `next_battle_turn()`, **antes** do decaimento e antes do turno virar |

O `round_end` vem antes de propósito: o gift precisa ver a rodada que está
**acabando**, não a próxima.

### Onde mora o motor

- `Database.session_hook` — o banco é puro e não importa o bot; enquanto ninguém
  ligar, nada acontece e o fluxo antigo continua igual. `fire_session` **nunca
  levanta erro**: gift mal escrito não pode derrubar a virada de rodada do grupo
  (mesmo espírito do `_effects_from_row`).
- `bot.apply_session_trigger` — aplica para cada participante. Gatilho de sessão
  **não tem alvo**, então o usuário é passado como ator **e** como alvo; é isso
  que faz `+3 Sanidade` e `+Offense Level` caírem na ficha de quem tem o gift.
- `apply_skill_trigger` passou a aceitar `skill=None` (gatilho de sessão não tem
  Skill nenhuma) e `turn`.
- **`activity_server.py` também liga o gancho.** Sem isso o gift disparava pelo
  processo do bot e **morria na Activity** — que é onde o encontro anda de fato.
  Import preguiçoso dentro do hook: no topo criaria ciclo.

### `condition_turn` falha fechada

Cláusula com `condition_turn` e **sem turno conhecido não dispara**. Se o chamador
esquecer de informar o turno, é melhor não dar nada do que o gift virar "vale em
toda rodada" sem ninguém pedir.

### 🐛 Bug meu da Etapa 2, encontrado aqui

`bloodfeast` estava em `STATUS_TYPES` e `EFFECT_TYPES`, mas **fora da lista de
`__post_init__`** que libera `count`. Então `SkillEffect("…", "bloodfeast", 300,
count=1)` levantava `ValueError` e o `_effects_from_row` **descartava a cláusula
em silêncio** — o gift ficava gravado no banco e nunca fazia nada. Só apareceu
porque a Etapa 4 gravou um `[Primeira Rodada] Bloodfeast +300` de verdade e ele
simplesmente não aconteceu. Corrigido, com 3 testes de regressão.

### Prova ponta a ponta (cópia do banco real)

```
〔Início do Encontro〕 rodada 1 · Rosemary Véspera   → offense_level +2
〔Início da Rodada〕    rodada 1 · Rosemary Véspera   → sp +3 · Bloodfeast 300
〔Fim da Rodada〕       rodada 1 · Rosemary Véspera   → coin_power +1
〔Início da Rodada〕    rodada 2 · Rosemary Véspera   → sp +3  (Bloodfeast NÃO repetiu)
Blade (sem gift) ficou em zero
```

**Verificação:** `py_compile` OK em 4 arquivos · **134 testes OK**
(40 + 38 + 18 + 7 + **16 (novo)** + 15) · HTML válido · as 2 fábricas rodam.

---

## ✅ P7 — Bloco 4: `all_allies` e `faction` (2026-10-01, 18:38 → 18:51)

*"Para quem" a cláusula vale*. Entraram dois `effect_owner` além de
`auto`/`target`/`user`:

| Valor | Quem recebe |
|---|---|
| `all_allies` | **todos** do encounter, **inclusive quem usa** (o time do Limbus inclui quem joga) |
| `faction` | só os do encounter que declaram a **`active_tag` do próprio gift** |

`faction` não ganhou campo novo: reaproveita a `active_tag` que o gate já usa
(*"3+ aliados da Middle"* → `active_tag='middle'`). **Sem tag, não aplica a
ninguém** — falha fechada, melhor que aplicar no time errado.

**Quem são os aliados:** `Database.encounter_member_ids()` — o painel da batalha
ativa, senão o grupo do servidor. O mesmo que o `count_allies_with` usa.

**A implementação** particiona as cláusulas antes do laço: as de alvo único
seguem o caminho de sempre, e as de multi-alvo viram uma chamada por aliado
(com o dono da cláusula como ator **e** alvo). Sem motor novo.

**`apply_session_trigger` roda em 2 passadas** — uma só pelas de multi-alvo e uma
só pelas de alvo único. Sem isso, com 3 participantes, cada um processando
tudo, uma cláusula de time sairia **9 vezes** em vez de 3.

### 🐛 Dois bugs que a prova pegou

1. **N vezes N.** Na passada `"single"` eu não tinha filtrado as cláusulas de
   multi-alvo — elas rodavam **duas vezes** (uma na expansão, outra no alvo
   único). Agora `single` filtra sempre.
2. **`skill_service.py` descartava campos em silêncio.** A lista `allowed`
   não tinha `max_per_round` nem `condition_turn`: uma skill com *"2 vezes por
   rodada"* salva pela UI perdia o limite. Corrigido.

O cabeçalho `◆ NOME DO GIFT` também só entra quando há o que aplicar — senão a
passada de multi-alvo imprimia o nome e nada depois.

### Prova (cópia do banco real, `testes/verify_bloco4.py`)

```
all_allies +2          → Rosemary 2 · Blade 2 · Zero 2     (3, inclusive a dona)
gift desativado        → 0 · 0 · 0
faction=middle (+3)    → Rosemary 3 · Blade 3 · Zero 0     (só os 2 marcados)
faction sem active_tag → 0 · 0 · 0                          (falha fechada)
```

**Verificação:** 8 arquivos compilam · **134 testes OK** · HTML válido ·
**`npm run build` da Activity passa** (SkillsTab 15,83 kB) · as 4 fábricas/provas
rodam.

---

## 🎨 Emojis reais nas descrições (2026-10-01, 18:20 → 18:37)

O autor aviso que **todos os emojis já existem no App**, e que Sanidade está
como **SP**. O catálogo não vive no código — é buscado do Discord em tempo
real —, então fui na API (`/applications/{id}/emojis` + `/guilds/{id}/emojis`):
**105 no App + 96 no servidor**, salvos em `backups/emoji_catalogo.json`.

**Nomes reais:** `Atributo_Sanity` (a Sanidade/SP) · `Atributo_HP` ·
`Moeda_Normal` / `Moeda_Inquebravel` · `Protection` · `Dano_Slash` ·
`Sin_Envy` / `Sin_Gloom` · `Efeito_Attack_Up` / `Efeito_Attack_Down` ·
`Efeito_Offense_Up` · `Efeito_Defense_Up` / `_Down` · `Efeito_Clash_Up` ·
`Efeito_Coin_Boost` / `Efeito_Coin_Down`.

**As 8 descrições** foram reescritas com esses emojis + os que o autor mandou.
**Zero Unicode remanescente** (nem mais 🪙, nem as setas ⬆️⬇️).

⚠️ **`Efeito_Bleed_Unique` existe com o mesmo nome no App e no servidor, com IDs
diferentes.** Mantive o **do App** (que foi o que ele mandou) — o do servidor é
outro emoji.

**Bônus:** o App tem `Zayin`/`Teth`/`He`/`Waw`/`Aleph`, então o card do editor
agora mostra o **emoji da classe** junto do tier (`TIER III [HE]`).

---

## 📌 Decisões do autor sobre o Clear Mirror (2026-10-01)

1. **Crítico do Poise +70 pontos percentuais** — `Dano Crítico = (Potência × 2%) + 70%`.
   Confirmado: *"é o crit do poise +70% como no exemplo dos pontos percentuais"*.
2. **Volatile's earring é do Zote** — reconfirmado.
3. *"Se um acerto crítico consumiu Poise Count"* = **um consumo**, o mesmo
   mecanismo de `condition_status` + `consume_condition`, que **o motor já tem**
   (§6: *"status consumido no crítico"*). Não precisa de campo novo.

**O que ainda falta pro Clear Mirror funcionar:** só o **gancho de Dano Crítico**
(hoje só o Poise calcula `(X×2%)`). O `all_allies` já existe. E a parte
*"na próxima rodada"* precisa de um efeito **pendente** (o `+10 Offense Level`
entrega uma rodada depois do crítico) — que é o `ego_gift_state` da Etapa 5.

---

## ✅ P7 — Etapa 5 + Clear Mirror FECHADO (2026-10-01, 18:52 → 19:11)

### A pergunta do autor: o gift alimenta a Falsa Fome?

**Resposta honesta: não.** O gift gravava em
`combat_statuses.status_type='bloodfeast'` e a Falsa Fome é o
`special_condition` — dois status separados, sem ligação nenhuma nos dois
sentidos. Corrigido:

1. **`Database.total_bloodfeast()`** — os dois somam no mesmo total.
2. **Quem é "a Falsa Fome" sai da keyword** (`false_hunger` → `unique_bloodfeast`
   pelo alias), **não** do status: `special_condition` também é o "Efeito
   Trashholder" de outras fichas, e somar um no Bloodfeast da outra seria errado.
   A keyword da Rosemary foi marcada.

**Bloodfeast passou a guardar no Count**, não na Potência — é assim que a Falsa
Fome já guardava, e os dois precisam ler o mesmo lugar.

Prova: Falsa Fome 60 + Bloodfeast 40 = **100** no total do gift.

### Etapa 5 — duração e limite

Tabela `ego_gift_state` (§9.3): uma linha = um efeito **pendente**. Um mecanismo
só para *"por 2 Rodadas"* e *"na próxima rodada"*:

| `SkillEffect` | O que faz |
|---|---|
| `duration_turns=N` | não aplica na hora: fica pendente e entra em cada início de rodada de `turn+1` até `turn+N`, e sai da fila depois |
| `max_activations` + `activation_window` | *"1x por rodada"* — o contador zera no início da rodada seguinte |

`take_gift_effects()` **seleciona antes de apagar**: é isso que faz "por 2
Rodadas" aplicar **duas** vezes e na terceira sair da fila. Limpa tudo no Encontro
novo (`clear_gift_state` no `session_encounter_start`).

### Clear Mirror, Calm Water — as 2 linhas do print

| Linha | Como ficou |
|---|---|
| *"Dano Crítico +70% de todos os aliados"* | coluna nova `ego_gifts.crit_damage_mod` (gravado **70**), somada em `get_total_ego_gift_modifiers` e somada ao `Potência × 2%` do Poise em `apply_poise_critical` |
| *"se um crítico consumiu Poise Count → +10 Offense na próxima rodada, 1× por personagem por rodada"* | 1 cláusula `on_crit` com `consume_condition` + `duration_turns=1` + `max_activations=1`/`round` |

`consume_condition` existia **só** em `apply_skill_damage_percent`; agora também
em `apply_skill_trigger` — sem isso o Poise contaria para sempre e o +10
dispararia a cada crítico.

**Prova** (`testes/verify_clear_mirror.py`):
```
ACERTO CRÍTICO • +20% do Poise **+70%** do gift = +90%  → +9 dano
[Ao Critar] consumiu 1 Count de Poise (2 → 1)
+10 Offense ficou PENDENTE por 1 rodada
2º crítico na MESMA rodada → "limite de 1x por rodada atingido"
rodada 2 → 〔PENDENTE〕 +10 caiu, limite zerou, crítico novo funciona
```

### 🐛 Três coisas que a prova pegou

1. **`on_crit` chega sem rodada**, e a Etapa 5 precisa dela (janela `round:N` e
   `expires_turn`). Sem isso o limite virava "por encontro" e nunca reiniciava.
   Agora `db.active_turn(guild_id)` completa.
2. **O `+10` é "o aliado" que critou**, não todos — eu tinha gravado
   `all_allies`. O "todos os aliados" da primeira linha é o `crit_damage_mod`.
3. **O `expires_turn` era somado duas vezes** (o bot passava `turn+N` e a função
   somava de novo) → o pendente durava uma rodada a mais e não saía da fila.

**Verificação:** 6 arquivos compilam · **134 testes OK** · as 5 fábricas/provas
rodando (`test_imperfect_eye`, `test_gifts`, `verify_session`, `verify_bloco4`,
`verify_clear_mirror`) · **20 cláusulas ainda bloqueadas** (era 21).

---

## ✅ Falsa Fome passou a SER Bloodfeast (2026-10-01, 19:23 → 19:33)

**O pedido:** "marque a falsa fome de rosemary como um unique bloodfeast e altere
em suas habilidades deixando ela sem special condition e então fazendo o ego gift
funcionar normal afinal as skills dela n consomem bloodfeast mas consomem falsa
fome, e o ego gift precisa funcionar pra isso".

**O problema que ele viu:** antes as duas coisas moravam em status diferentes. As
skills dela consumiam `special_condition` (a Falsa Fome), o E.G.O Gift lia
`bloodfeast.count`. Enquanto isso, o gift **não enxergava** o recurso que as
skills dela usavam — e as duas não somavam no mesmo total.

**A decisão:** a Falsa Fome **é** um Unique Bloodfeast. Então as skills dela
passaram a falar `bloodfeast` direto, e `special_condition` sobrou só como o
**Efeito Trashholder** das outras fichas.

| Antes (só nas skills dela) | Agora |
|---|---|
| `effect_type: "special_condition"` | `"bloodfeast"` |
| `effect_type: "consume_special_condition"` | `"consume_bloodfeast"` |
| `condition_status: "special_condition_consumed"` | `"bloodfeast_consumed"` |
| keyword `false_hunger` | `unique_bloodfeast` (o alias continua) |

**As outras fichas NÃO foram tocadas** — `special_condition` delas é o
Trashholder (Big three, Pablo Suindara, Raei) e segue funcionando igual.

**O que mudou no código:**
1. `Database.get_resource_consumed` / `consume_resource` — o `consume_special_condition`
   virou um caso particular de um par genérico (`<status>_consumed`). `consume_bloodfeast`
   e `get_bloodfeast_consumed` são só o outro caso. Coluna nova `bloodfeast_consumed`
   em `characters` e `enemies` (mesmo molde da `special_condition_consumed`).
2. `SkillEffect` ganhou `consume_bloodfeast` em `EFFECT_TYPES`; `bot.py` trata os
   dois consumos no mesmo `if`.
3. Alias `false_hunger` → `bloodfeast` em `_effects_from_row` e em `skill_service`.
4. `total_bloodfeast()` **deixou de somar** `special_condition`. Com a Falsa Fome
   no status certo, somar o Trashholder das outras fichas seria ler errado.
5. `rosemary_panel.py`: medidor, `_status`, draft skills e fonte do campo apontam
   para `bloodfeast`. O nome na tela continua "Falsa Fome".

**Os 2 bugs que apareceram no caminho (e como a battery os pegou):**
- **`bloodfeast` e `bloodfeast_consumed` não estavam na lista de `condition_status`
  válidos** do `SkillEffect.__post_init__` nem do `VALID_CONDITIONS` do
  `skill_service`. As 20 condições de escala dela (que leem o "já consumido")
  estavam sendo **descartadas em silêncio** pelo `_effects_from_row` — a skill
  continuava no banco, só que pela metade. Isso é o bug antigo de "cláusula
  inválida some sem avisar" voltando por outra porta.
- **`record_rosemary_consumption` é código morto** (nada chama desde a Activity).
  O painel lia `rosemary_states.false_hunger_consumed_total`, que nunca mais
  era atualizado; como `get_rosemary_state` cria a linha, o fallback para a
  coluna da ficha nunca disparava. Agora o painel pega o **máximo** entre o
  contador real e o legado.

**No banco:** 53 trocas em 8 skills da Rosemary (guild real `1392000415108960426`).
`special_condition_consumed=320` migrou para `bloodfeast_consumed=320`.
Keywords = `["unique_bloodfeast"]`. Backup em
`backups/clash_rpg-antes-bloodfeast-20261001-192820.sqlite3`.

⚠️ **A guild `949911180841975849` tinha 4 skills da Rosemary no vocabulary
antigo** → resolvido às 19:57, o autor pediu para ficar só com as 9 da Arcana.

**Verificação:** **85/85 cláusulas sobreviveram** o `_effects_from_row` (nada
descartado) · as **20 condições de escala** dela vivas em `bloodfeast_consumed` ·
**141 testes OK** (era 134; +7 em `test_bloodfeast_compartilhado.py`) · 7 arquivos
compilam · prova em `testes/verify_bloodfeast.py`.

---

## ✅ Rosemary só na Arcana (2026-10-01, 19:55 → 19:57)

A guild `949911180841975849` tinha uma **cópia parcial** da Rosemary: 4 skills no
vocabulary antigo (`keywords=[]`), a ficha, `devotion_repressed 1x1` e um
`special_condition 1x20` **órfão** — nenhuma skill naquela guild consumia Falsa
Fome, então o número não fazia sentido nenhum. O autor pediu: ficar só com as 9
da Arcana.

**Apagado (só da Rosemary, só naquela guild):** 4 skills · a ficha em
`characters` · `devotion_repressed 1x1` · `special_condition 1x20` · 1 linha em
`rosemary_states` (0 `rosemary_events`).

**Intacto:** as 9 skills da Arcana (`d1`, `d1-2`, `s1`, `s1-10`, `s1-2`, `s2`,
`s2-2`, `s3`, `s3-2`) com `keywords=["unique_bloodfeast"]` · as outras 4 fichas
da 9499 (Nolan 5, Raei 5, Razor 4, Xavier 6) e seus status · os 3 inimigos da
9499 · os 10 da Arcana.

Backup: `backups/clash_rpg-antes-apagar-rosemary-9499-20261001-195712.sqlite3`.

⚠️ **Não mexido (pedir quando for):** the guild `1039334356445036594` tem um
**Mestre** com o *mesmo* `user_id` da Rosemary (`1034518001535430777`) e 0 skills.
Duas fichas com o mesmo usuário em guilds diferentes é normal (o usuário entrou
em outro servidor), mas vale saber que existe.

**Verificação:** 141 testes OK · 8 arquivos compilam · `verify_bloodfeast.py`
confere 85/85 cláusulas.

---

## ✅ `test_gifts.py` virou medidor de verdade (2026-10-01, 20:10 → 20:24)

**O problema:** o `test_gifts.py` era um checklist com os motivos de bloqueio
escritos à mão. Ele ficou **desatualizado** depois das Etapas 4/5/6 e do bloco 4:
dizia "falta o gatilho `session_round_start`", "falta `effect_owner: all_allies`",
"faltam `duration_turns`" — e **tudo isso já existia**. Pior: contava 20
bloqueadas quando o número real era outro, e a mesma frase ("Etapa 4") aparecia
para casos que já estavam fechados.

**A virada:** cada exigência agora é montada **de verdade** — passa pelo
`effects_json` → `_effects_from_row` → `SkillEffect` — e só conta como
"funciona" se o motor engolir. Quando não engole, o motivo sai da **exceção**,
traduzida pela tabela `PENDENCIA` para a pendência concreta com a Etapa que a
destrava (o `SkillEffect` só diz "Status circunstancial inválido", sem dizer
**qual** status ele queria).

**O que a medição revelou (o número real):** **13/24** exigências legíveis,
**11 bloqueadas** (o checklist antigo dizia 20). As 6 do Imperfect Eye estão
**todas** funcionando — o checklist as dava como bloqueadas.

**As 11 bloqueadas, por causa:**

| Gift | Bloqueio |
|---|---|
| Family's Resentment | HP (Etapa 7) ×2 · La Manchaland como status · tag de skill (Etapa 8) |
| Dreaming Electric Sheep | Envy não existe |
| Livro da vingança | Envy ×2 · Protection não existe · escudo persistente (Etapa 8) |
| Reminiscence | "inimigos restantes" como status · afinidade (fora de escopo) |

**3 erros meus achados no caminho** (o checklist antigo nunca pegaria, porque
"Status exige Potência e Quantidade" era lido como bloqueio do motor):
1. `tremor`/`burn` **exigem `count`** — sem ele a cláusula morre. As 6 do
   Imperfect Eye no banco passam porque têm `count: 0` gravado.
2. `amplitude_conversion_scorch` **exige `value`** (posicional, sem default).
3. `tremor_burst` **não aceita `count` negativo** — o "−1 Count" da print vira
   só `value`.

**Testes novos:** `test_01` relatório · `test_02` 8 gifts no banco · `test_03`
nenhuma cláusula gravada é descartada em silêncio · `test_04` mods de coluna são
int · `test_05` Clear Mirror = 70 · `test_06` **trava de regressão** (13 é o
piso — se cair, o motor quebrou).

**Verificação:** **147 testes OK** (era 141; +6 do `test_gifts.py`).

---

## ✅ Poise arrumado: a Potência virou a chance + d20 visível (2026-10-01, 20:40 → 20:58)

**O pedido:** *"o d20 é só pra margem crítica (ver se a MOEDA crita e não o ataque
inteiro com base no count), o poise precisa funcionar, tente arrumar o poise
primeiro, e coloque nos embeds o número que cair no d20, fazendo ele deixar de
ser secreto"*.

**1. O d20 sempre foi por moeda** — nenhuma mudança, só confirmação. `Count`
não decide o ataque inteiro; ele é quantos críticos o encontro ainda pode ter.

**2. A fórmula estava quebrada em 3 lugares.** Era `max(1, 20 − Potência÷10)`,
e isso prendia a chance em **5% / 10% / 15% / 20%**: Poise 15 dava 10% e Poise
20 dava **10%** — a Potência da ficha quase não importava. Pior: a mesma
expressão estava copiada em 3 lugares (a previsão da ficha em `render_statuses`,
o crítico em `apply_poise_critical`, a cadeia de reutilização de moeda em
`apply_critical_coin_reuse`). Mudar uma e esquecer das outras é exatamente o
jeito de a regra virar inconsistente.

**Decisão do autor (20:52): a Potência É a chance de crítico.** O d20 tem 20
faces, então a chance anda de 5% em 5%:

| Potência | 5 | 10 | 15 | 20 | 30 | 50 | 100 |
|---|---|---|---|---|---|---|---|
| chance/moeda | 5% | 10% | 15% | 20% | 30% | 50% | 100% |
| margem `d20 ≥` | 20 | 19 | 18 | 17 | 15 | 11 | 1 |

O dano do crítico **não mudou**: continua `Potência × 2%` (decisão do autor na
mesma pergunta). E o Clear Mirror continua somando em pontos percentuais.

**3. O d20 deixou de ser secreto.** Antes o embed só dizia "margem secreta
`d20 ≥ 19`" — impossível conferir. Agora mostra a rolagem de **cada** moeda,
com ✅/❌, nos dois casos (acertou e não acertou):

- `moedas 1/2/3: `7`❌ `20`✅ `13`❌`
- sem rolagem: `moeda 4 (sem Quantidade)`, `moeda 2 (Unbreakable)`

Mostrar as moedas **puladas** também importa: sem isso o mestre vê a moeda 3 sem
crítico e não sabe se foi Unbreakable, se acabou a Quantidade, ou se o d20 foi
baixo.

**4. Bug de verdade encontrado no caminho:** `damage.critical_hits = critical_hits`
**sobrescrevia** a lista. Se o dano já tivesse críticos de outra origem, eles
sumiam do embed (o dano continuava certo, a lista não). Agora é `sorted({*...})`.

**Arquivos:** `bot.poise_threshold()` (a função única) · `apply_poise_critical`
(revela o d20) · `render_statuses` (mostra a chance, não só a margem) ·
`apply_critical_coin_reuse` · texto de ajuda do Poise · `README.md` ·
`testes/verify_poise.py` (prova de 6 blocos, com `D20Falso`controlado).

**Nota:** `random.Random(20)` **não** força 20 — a semente só dá repetibilidade.
O primeiro teste "provou" o caminho feliz sem critar nada. Foi preciso um d20 de
mentira para exercitar os dois lados.

**Verificação:** **147 testes OK** · `bot.py` compila · `verify_poise.py` roda
os 6 blocos · a busca por `potency // 10` no `bot.py` devolve **só** a
`poise_threshold` e o comentário que explica a regra velha.

---

## 🔶 The Family's Resentment — o autor explica (2026-10-01, 21:0x)

**"a ideia do family resentment é curar com base no dano da skill causado. o ego
gift n da bleed ele faz essas coisas aqui"**

Duas coisas que eu tinha entendido errado:

1. **O gift NÃO dá Bleed — ele *observa* Bleed.** A cláusula é "habilidadess
   que **inflingirem** Bleed Potency / Bleed Count / Unique Bleed". Ou seja, é
   um gatilho sobre *o que a skill causou*, não um efeito que produz Bleed.
   (Eu tinha escrito "habilidade que inflige Bleed" como se precisasse de tag
   de skill — não precisa: o bot já sabe quais status a skill aplicou.)

2. **A cura é sobre o DANO da skill, não sobre o HP máximo.** *"curar com base
   no dano da skill causado"* — o valor é 30% do dano que aquela skill
   causou, com teto de 20. (O texto da print diz "30% do HP como dano
   causado", que é ambíguo; o autor desambiguou.)

**E o HP continua modo manual** (§8 do desenho): o bot **publica a linha** de
cura e o autor aplica. Nada de alterar HP no banco.

## 🔶 Livro da vingança — Envy fica de fora (2026-10-01, 21:0x)

**"do livro da vingança deixe sem os envy e deixe para quando tiver aliados no
encounter com o keyword de middle, e protection é por fora"**

- **As 3 cláusulas de Envy saem do escopo agora:** "+3 Attack Power por 12 Envy",
  "+3 Protection por 12 Envy" e "converte moedas em Unbreakable". Envy não é
  produto por nenhuma skill da Arcana — um recurso que nasce vazio nunca sai
  do zero, então construí-lo agora seria construir coisa morta.
- **Protection é "por fora"** — vale para o Volatile's earring também (que tem
  "5 Protection"), não só para o Livro.
- **O que fica do Livro é só o escudo:** "[Início do Encontro] todos os aliados
  da Middle ganham 50 de escudo **para cada aliado da Middle**". Precisa de
  (a) keyword `middle` — que **já existe** como alias — e (b) um status de
  escudo que **não expira** (Etapa 8).

**Nada foi apagado do banco:** o Livro já tinha **0 cláusulas** gravadas e o
Volatile's tem só a de `+3 SP`. As cláusulas de Envy/Protection nunca chegaram
a ser gravadas — a instrução foi só **não implementar**.

---

## 🟡 The Family's Resentment — a cura por dano (2026-10-01, 21:0x → 21:3x)

**Escolhas do autor:** a cura sai de **30% do `final_damage`** da skill (não do
HP máximo) e a skill é detectada **comparando o Bleed do alvo antes e depois** da
resolução.

**O que foi feito:**

1. **`heal_from_damage`** — novo `effect_type`. `value` = a porcentagem,
   `condition_max_stacks` = o teto. O HP é **modo manual** (§8): o bot
   **publica** a linha e o autor aplica; nada é gravado no HP.
2. **`inflicted_bleed`** — nova condição. Não é um status da ficha: é uma
   pergunta sobre o **resultado** da skill. `_bleed_snapshot()` tira
   `(bleed_p, bleed_c, unique_p, unique_c)` do alvo antes e depois, e se
   **subiu** em qualquer campo, a skill infligiu. Pega qualquer skill,
   inclusive as que aplicam status por moeda dentro de
   `resolve_hit_status_sequence` — sem a skill precisar declarar nada.
3. **O gancho ficou dentro de `resolve_hit_status_sequence`** (não nos 8
   chamadores) — que é quem aplica os status por moeda. Um lugar, 8
   chamadores cobertos, e a cura sai **ao final da habilidade**, que é onde a
   print pede. `damage` entrou como parâmetro **opcional** nos 8 chamadores
   (sem ele a cura é pulada, e nada quebra quem não usa gift).
4. **"se curou → +1 Final Power na próxima rodada"** via `queue_gift_effect`,
   que já é o mecanismo único de "na próxima rodada".

**Prova** (`testes/verify_family_resentment.py`, 5 blocos):

| dano | 30% | cura |
|---|---|---|
| 10 | 3 | **3** |
| 30 | 9 | **9** |
| 50 | 15 | **15** |
| 67 | 20 | **20** ← teto |
| 100 | 30 | **20** ← teto |
| 500 | 150 | **20** ← teto |

Sem Bleed infligido → **0 linhas**. Com → a linha da cura + a do Final Power
pendente. A ficha não muda.

**2 erros meus no caminho (o mesmo tipo de sempre):**
1. `db.current_turn(guild_id)` — a assinatura é `current_turn(guild_id,
   channel_id)`; o certo aqui é `active_turn(guild_id)`.
2. A cláusula do Final Power é `session_round_start`, então ela **não está** na
   lista de `after_attack` que eu já tinha filtrado. Filtrar de novo.

**Ainda falta:** nada do núcleo — o `max 3` e o Compartilhado foram fechados
abaixo.

---

## 🟡 The Family's Resentment — max 3 e "Consumido (Compartilhado)" (21:3x → 21:5x)

**1. `max 3` do "se curou: +1 Final Power".** `queue_gift_effect` **acumula**:
sem teto, 5 curas na mesma rodada empilhavam +5 Final Power. Agora o caminho da
cura chama `reserve_gift_activation` — o mesmo mecanismo do bloco 6, com a
mesma janela `round:{turno}`. A cláusula ficou `max_activations=3` +
`activation_window="round"` (a print diz "max 3" sem dizer por quê; "por rodada"
é o que bate com o resto dos prints).

Prova: 5 curas na mesma rodada → **3 pendentes, 2 barradas**; virando a rodada,
outras 3 passam. O teto é **por rodada**, não por encontro.

**2. `shared_bloodfeast_consumed`.** A print diz *"cada 50 **Bloodfeast
Consumido (Compartilhado)**"*. O `(Compartilhado)` é o que faz a diferença:
`bloodfeast_consumed` sozinho é **por ficha**, e dois aliados consumindo 30 cada
dariam 30 quando a regra é 50.

`Database.shared_bloodfeast_consumed()` soma a coluna de todos os
`encounter_member_ids` — o próprio incluído, mesma definição de "aliado" do resto
do sistema. Nova condição em `skill_condition_value`, em `SkillEffect`, em
`VALID_CONDITIONS` e em `STATUS_ICONS`.

Prova com 3 aliadas consumindo 20/30/30:

| por ficha | compartilhado |
|---|---|
| 20 | **80** |

E a escala da cláusula:

| total do time | +Offense |
|---|---|
| 0 | 0 |
| 30 | 0 |
| 50 | **1** |
| 80 | 1 |
| 100 | **2** |
| 320 | **6** (teto) |

**Verificação:** **147 testes OK** · 5 arquivos compilam · `test_gifts.py` agora
dá **17/21** com **4 bloqueadas** (era 16/21 / 5) · provas em
`testes/verify_family_resentment.py` e `testes/verify_family_limites.py`.

---

## ✅ A cura virou "uma notinha" (2026-10-01, 21:5x)

**Pedido do autor:** *"a cura deixa só uma notinha no dano final dos ataques da
rose já que só funciona pra ela"*.

Duas linhas longas viraram **uma** linha:

```
🩸 The Family's Resentment: devolve **`20` HP** • *aplique no HP* • `+1` Base Power na próxima rodada
```

Saiu o "inflingiu Bleed", a porcentagem e o teto — a conta fica no
`verify_family_resentment.py`, não no embed. E o "se curou → +1 Final Power"
virou **sufixo** da mesma linha em vez de uma segunda linha, senão o embed
enchia de repetição do nome do gift.

⚠️ O embed de dano (`damage_embed`) é montado **antes** de
`resolve_hit_status_sequence` rodar, então a nota entra na lista de efeitos que
vem depois — não no campo `〔 DANO FINAL 〕`. Para mudar isso teria que remontar
o embed em 8 lugares.

## ✅ Confirmado: a Falsa Fome conta no Bloodfeast Consumido (Compartilhado)

O autor perguntou. **Sim**, nos três pontos — e medido, não deduzido:

1. **A Falsa Fome conta.** Depois da migração, as 7 skills da Rosemary usam
   `consume_bloodfeast` (e 0 usam `special_condition`), então o consumo dela
   sobe `bloodfeast_consumed` — que é exatamente a coluna que a print lê.
   O contador dela está em **320**.
2. **Ela própria conta no compartilhado.** `encounter_member_ids` inclui o dono
   (mesma definição de "aliado" do resto do sistema). Consumiu 60, o
   compartilhado devolveu 60.
3. **O aliado dela é buffado.** Rose 60 + Aliado 20 = 80 no time → a cláusula
   concedeu **1** Offense Level (a regra é "cada 50").

---

## 🔶 Escudo do Livro — NÃO é persistente (2026-10-01, 21:5x)

**Autor:** *"sobre o shield do escudo de livro ele quebra e na proxima rodada ele
volta em 50, caso não quebre ele volta pra 50. e fica nisso"*.

Eu tinha entendido "escudos não expiram no fim da rodada" (o texto da print) como
**mecânica de escudo persistente** — que era a razão de o Livro estar travado na
Etapa 8. **Não é.** O escudo **renova em 50 a cada rodada**, quebrado ou não.
Então é o escudo normal com reposição por rodada: bem mais simples, e **não**
precisa de "não expira".

Fica assim:
- `[Início do Encontro]` → 50 de escudo **por aliado da Middle** na área.
- `[Início da Rodada]` → volta a 50, **se quebrou ou não**.

Ainda falta: um status de escudo que o gift consiga **renovar** (o bot hoje tem
escudo como número solto no embed, não como status). É bem menor que a Etapa 8
inteira.

## ✅ Envy sai do checklist (2026-10-01, 21:5x)

**Autor:** *"envy não precisa colocar. pode tirar isso dos pratos tbm"* (pratos =
listas/checklist). Saiu de `testes/test_gifts.py` por completo — não é mais
"exigência não implementada", é exigência **inexistente**. Envy morre aqui como
regra.

**Contagem:** o `test_gifts.py` segue em **17/21** com **4 bloqueadas**, mas as 4
são agora todas reais: as **2** do escudo do Livro, "inimigos restantes" do
Reminiscence, e a afinidade (fora de escopo).

---

## ✅ Git instalado e o trabalho versionado (2026-10-01, 22:0x)

**Git 2.55.0.5** instalado via `winget install --id Git.Git`. O projeto **nunca
tinha sido commitado** — o `origin` estava parado em 23/08/2026 e 205 arquivos
ficaram fora.

**3 commits no branch `feature/refactor-architecture`** (o `main` do remoto
continua intocado em `f081634`):

| | |
|---|---|
| `53b3635` | `.gitignore`: `tmp_*.txt`, `*.tmp`, `*.bak`, `*.orig` |
| `7a1bf89` | 205 arquivos — E.G.O Gifts, refactor, Activity, launcher, docs, LICENSE |
| `51b252d` | `.gitattributes` — fixa a quebra de linha no repositório |

**Push feito** (`4e32acb..51b252d`), **fast-forward** — o remoto já tinha esse
branch em `4e32acb`, que é onde o primeiro commit foi aplicado. Sem force.

### O que teve de resolver

1. **`safe.directory`** — a pasta é de `CodexSandboxOnline` (sandbox efêmero,
   o perfil nem existe mais em `C:\Users`) e eu rodo como `Usuário`, então o
   git recusava com *"dubious ownership"*. Entrou no `.gitconfig` do perfil
   `Usuário`. Como o perfil do sandbox não existe mais, essa mesma linha serve
   para as duas pontas.
2. **Identidade** — não havia `user.name`/`user.email`. O autor confirmou que
   `guilherme1107-msk <guilherme231907@gmail.com>` é dele.
3. **`core.autocrlf=true`** avisava *"LF will be replaced by CRLF"* em ~110
   arquivos. Isso é config de máquina, não do projeto: duas pessoas com
   `autocrlf` diferente veem diffs que não existem. O `.gitattributes` fixa LF
   no índice e na pasta, com exceção de `.bat`/`.cmd`/`.ps1`/`.psm1` (CRLF),
   e declara os binários para o git nunca normalizá-los.
   **O índice já estava todo em LF**, então isso não mudou uma linha do
   conteúdo versionado.

### Conhecido, deixado de fora de propósito

**7 arquivos com quebra de linha misturada na pasta de trabalho** (índice ok):
`.env.example` · `ARCHITECTURE.md` · `CHANGELOG.md` · `README.md` ·
`src/domain/models/combat.py` · `start_control_center.bat` ·
`testes/test_database.py` · `testes/test_engine.py`.

Não foram normalizados porque `src/domain/models/combat.py` e
`testes/test_database.py` **estão sendo editados por outra sessão** — reescrever
o arquivo inteiro por causa de EOL colidiria com o trabalho dela. Se
normalizados sozinhos no próximo checkout de cada um.

---

## ✅ The Family's Resentment LIGADO no banco real (2026-10-01, 23:37)

O código da cura, do `max 3` e do `(Compartilhado)` estava pronto desde 21:3x,
mas o gift estava com **0 cláusulas** no banco — nada disparava. Agora tem as
**3**, validadas uma a uma contra o motor **antes** de gravar (é que
`_effects_from_row` descarta cláusula inválida em silêncio, e um gift
"gravado mas meio escrito" é o pior estado possível):

```
after_attack         heal_from_damage  v=30  cond=inflicted_bleed            max=20
session_round_start  base_power        v=1                                     (max 3/rodada)
session_round_start  offense_level     v=1   cond=shared_bloodfeast_consumed  max=6
```

**Conferência depois de gravar:** 3 gravadas / 3 lidas — nada descartado.

**7 das 9 skills dela já podem disparar a cura** (têm cláusula de Bleed):
`Aceite Minha Oferenda.` · `Ajoelhe-se.` · `Eu Posso Ser Útil.` · `Mordida` ·
`Não Ouse Me Negar.` · `Por Favor... Só um Pouco.` ·
`Você Não Merece Esse Sangue.`

As 2 que não (`Por Favor... Não me Machuque Muito.` e `desviar`) são evasivas
e não aplicam Bleed — como esperado.

**Compartilhado no banco real:** `bloodfeast_consumed` da Rose = 320, e o
compartilhado = **320** (ela é a única da Arcana com consumo registrado).

Backup: `backups/clash_rpg-antes-family-20261001-233738.sqlite3`.

⚠️ **`gift_class` do Family's está vazio** (`classe=-`). Os outros dois que o
autor classificou são HE (Reminiscence) e WAW (Livro). Falta decidir o
deste.

---

## 🔶 Escudo do Livro — "só um número solto" (2026-10-01, 23:4x)

**Autor:** *"deixa só um número solto"* — não criar status de escudo. Bom: o
escudo **já é** um número solto hoje. `clashable_guard_values()` devolve
`(stagger_manual, escudo)` e o `escudo` é só `loser_power` quando o perdedor é
`clashable_guard` — nunca foi gravado no banco. Então o gift só precisa
**somar** nesse número na hora do embed. Nada de status novo, nada de migração.

**Regra (autor 21:5x):** quebra e volta a 50 na próxima rodada; não quebra e
volta a 50. Ou seja, **renova em 50 por rodada**, não é "não expira".

**O que ainda NÃO fecha:** o *"50 de escudo **para cada aliado da Middle**"* é
um **multiplicador por contagem**, e nenhum mecanismo existente faz isso:

- `condition_min`/`condition_per` escalam por um **status** (Poise, Bloodfeast),
  não por uma **contagem de aliados com keyword**.
- `effect_owner` tem `all_allies` (todos) e `faction` (quem declara a
  `active_tag` do gift), mas não "todos os aliados **da keyword X**" com
  multiplicador `N`.

Falta decidir uma de três:
1. `all_allies` + um gate novo por keyword, e o `50 × N` calculado à parte
   (provavelmente um `condition` do tipo "conte os aliados com keyword `middle`").
2. Tratar `N` como `value × N` dentro do próprio efeito — exige o mesmo
   condicional, só que embutido.
3. Deixar o `N` fora do motor: o gift entrega **50**, e o **mestre** multiplica
   pelo número de aliados da Middle (o HP/Stagger já é assim — o bot publica a
   linha).

**A 3 é a mais barata e combina com a regra do projeto** ("o bot não controla HP
ou Stagger realmente"), mas tira do bot a contagem. **A 1 é a correta** se a
contagem for importa

**Contagem recalculada:** o `test_gifts.py` mede agora **16/21** exigências
(era 13/24) com **5 bloqueadas** (era 11). As 6 que saíram foram as de Envy e
Protection, que o autor tirou de escopo.

⚠️ **O checklist diz "OK" onde ainda falta regra.** "cada 50 Bloodfeast
Consumido (**Compartilhado**)" e a linha da La Manchaland passam porque a
cláusula *carrega* — mas `bloodfeast_consumed` é **por ficha**, e o print pede o
total **do time**. Esse lado ainda não existe, e o teste não pega (ele valida que
o motor engole a cláusula, não que ela signifique a coisa certa).

---

## ✅ Escudo do Livro: a opção 1 (2026-10-02, 00:0x → 00:15)

O autor escolheu a **1**: o bot conta os aliados com a keyword e multiplica.

**1. `condition_keyword`** — novo campo do `SkillEffect`. Os `condition_per` que
existiam escalam por um **status** (Poise, Bloodfeast); este conta **pessoas**.
Sem o campo, `condition_status="allies_with_keyword"` sem keyword levanta
`ValueError` — falha fechada na validação, não em silêncio depois.

**2. `allies_with_keyword`** — nova condição, resolvida por
`db.count_allies_with` (que já existia desde a Etapa 3). O próprio entra na
conta, como em todo o resto.

**3. `shield`** — novo `effect_type`, e ele **não é status**. `gift_shield()` soma
no `guard_shield` dos dois pontos de Clash, do lado de quem **perdeu**. Três
decisões dentro disso:
- **Só a defusa ganha.** Quem não tem `clashable_guard` recebe 0 — o gift não
  inventa uma defusa que não existe.
- **Nada é gravado** (0 linhas de status `shield` no banco). É por isso que
  *"quebrou ou não, volta a 50 na próxima rodada"* sai de graça: sem estado
  guardado, o número é recalculado a cada Clash.
- **O gift é procurado do lado do perdedor**, que pode ser ficha ou inimigo
  (os dois pontos de Clash tratam os casos diferentes).

**Prova** (`testes/verify_escudo_livro.py`): `50 × N` bateu de N=2 a N=6; quem
marcou `blitz` não contou; sem defusa deu 0; 0 linhas gravadas.

⚠️ **`gift_shield()` foi colocado no `bot.py`, não no `engine.py`** — a primeira
tentativa foi no `src/domain/combat/engine.py`, que é a camada de domínio e não
pode importar de `bot.py` nem de `database.py` (inverte a camada e cria ciclo).

**Gravado no banco real:** 1 cláusula no Livro (id=5, T5, classe WAW), validada
antes. Backup `backups/clash_rpg-antes-escudo-20261002-000240.sqlite3`.

⚠️ **NENHUMA ficha da Arcana tem a keyword `middle`** — o escudo dá **0** até
alguém marcar as aliadas da Middle pelo Control Center. A cláusula está correta
e acorda sozinha quando as keywords existirem, mas hoje está inerte. É a única
coisa que falta para o Livro funcionar de verdade.

**Contagem:** o `test_gifts.py` vai a **18/20** com **2 bloqueadas** — "inimigos
restantes" do Reminiscence e a afinidade (fora de escopo).

---

## ✅ Escudo do Livro ACORDOU + classe ALEPH (2026-10-02, 00:11)

**1. O autor marcou `Pablo Suindara` com `middle`.** O escudo do Livro, que
dava **0**, agora dá **50** (1 aliado da Middle × 50). A cláusula estava
correta o tempo todo — só não tinha ninguém com a keyword para contar.

Keywords da Arcana agora:

| ficha | keywords |
|---|---|
| Pablo Suindara | `charge`, **`middle`** |
| Rosemary Véspera | `bleed`, `bloodfeast`, `unique_bloodfeast` |
| Blade | `poise` |
| Elizabeth | `burn`, `tremor` |
| Bernd Klaus | `tremor` |
| Zote | `bleed` |

**2. Os 3 gifts da Rosemary são `T5 / ALEPH`** (autor: *"todos os ego gifts da
rose são tier V classe aleph"*). O Tier já estava T5 nos três — a **classe** é
que estava vazia. Gravado `gift_class='ALEPH'` (a coluna é lida pelo badge do
Control Center, e `save_ego_gift` sobe para maiúsculo). Backup
`backups/clash_rpg-antes-aleph-20261002-001106.sqlite3`.

**Os 8 gifts agora:**

| dono | gift | tier | classe | cláusulas |
|---|---|---|---|---|
| Rosemary | Imperfect Eye of Precognition | T5 | **ALEPH** | 6 |
| Rosemary | The Familys Resentment | T5 | **ALEPH** | 3 |
| Rosemary | Carousel Figurine | T5 | **ALEPH** | 1 |
| Pablo Suindara | Livro da vingança: Annex | T5 | WAW | 1 |
| Pablo Suindara | Dreaming Electric Sheep | T5 | *(vazio)* | 0 |
| Blade | Clear Mirror, Calm Water | T4 | *(vazio)* | 1 |
| Blade | Reminiscence | T3 | HE | 0 |
| Zote | Volatile's earring | T5 | *(vazio)* | 1 |

✅ **Os 3 gifts sem classe não precisam de classe** — o autor: *"esses 3 nem
existem em limbus"*. `Dreaming Electric Sheep`, `Clear Mirror, Calm Water` e
`Volatile's earring` são invention dele, então não têm classe de Identity.
**Item encerrado**, não é pendência.

**Verificação:** **147 testes OK** · as 5 provas rodam · 3 backups novos hoje.

---

## 📍 Ponto de parada (2026-10-02, 00:15)

O autor: *"está ótimo por hoje, aguarde segunda ordens"*. Os gifts ele mesmo
ajusta depois.

**Estado dos 8 gifts:** todos com tier e classe certos (os 3 sem classe são de
invenção dele, sem classe de Identity). **12 cláusulas** gravadas no total:

| gift | cláusulas |
|---|---|
| Imperfect Eye of Precognition | 6 |
| The Family's Resentment | 3 |
| Clear Mirror, Calm Water | 1 |
| Livro da vingança: Annex | 1 |
| Volatile's earring | 1 |
| Carousel Figurine | 1 |
| Dreaming Electric Sheep | 0 |
| Reminiscence | 0 |

`test_gifts.py`: **18/20** legíveis. As 2 restantes são "inimigos restantes"
(Reminiscence) e afinidade (fora de escopo, decisão 2).

**Pendências pequenas que sobraram:**
- ~~`EGO_GIFT_MAX_BY_UPTIE` vazia~~ → **preenchida** `{1:8, 2:8, 3:8, 4:8, 5:10}`.
- ~~`crit_damage_mod` no formulário do editor de gifts~~ → **nos 4
  formulários e nos 4 payloads**. `gift_class` já estava. Duration/limite
  agora **sobrevivem** ao salvar (via `dataset.original`), mas ainda não
  têm input — dá pra mexer pelo payload.
- ~~UI dos gifts na Activity (falta `consume_devotion_repressed`)~~ →
  **não falta, está escondida de propósito** (recurso privado, filtrado no
  `activity_server.py`). O que faltava mesmo eram 6 tipos e 6 condições —
  **entram agora**. Editor de cláusulas de gift na Activity continua sendo
  o item 3 do autor.
- **P8 (embeds dos gifts)** continua pendente.
- 7 arquivos com EOL misturado, esperando a outra sessão largar `combat.py` e
  `testes/test_database.py`.
- Vulnerabilidades: `discord.py`, e `react`/`vite` com `"latest"`.

**Git:** branch `feature/refactor-architecture`, 7 commits, tudo no ar.
`main` do remoto intocado.

---

## 🐛 O "Salvar" da Central apagava os gifts (2026-10-03, 04:4x) — CORRIGIDO

Bug encontrado quando o autor pediu *"arrume tudo possível sobre os ego
gifts"*, e ele era **silencioso e destrutivo**.

**O caminho:** o `saveEgoGiftItem`/`addEgoGiftItem` do `control_center.html`
monta o payload com nome/tier/classe/mods — **sem a chave `effects`** (a
Central não tem editor de cláusulas de gift; é o item 3, que o autor faz
outro dia). O `db.save_ego_gift` fazia `json.dumps(payload.get("effects",
[]))`, ou seja `[]`, e escrevia no `UPDATE`.

**Resultado medido:** um gift com **1 cláusula** ficava com **0** depois de
clicar em "Salvar". No banco real eram **13 cláusulas** e **3 gates** em
risco.

**O mesmo `payload.get(..., default)` existia no gate do Bloco 7**
(`active_status`, `active_tag`, `active_scope`, `active_min`) — que
Carousel (`la_manchaland`), Livro (`middle`/`allies`/3) e Reminiscence
(`poise`/`allies`/3) dependem para valer.

**A regra nova, uniforme:** ***ausente = não mexe; presente = manda (mesmo
vazio)***. O `UPDATE` agora só escreve as colunas cuja chave veio no
payload, a partir de uma **lista literal** — os nomes de coluna nunca vêm
de fora, então não há SQL dinâmico vindo do usuário.

Duas decisões dentro disso:

- **`INSERT` continua com os defaults** (gift novo não tem gate nem
  cláusulas), via `COALESCE(?, '[]')` para o `effects_json`.
- **Para limpar, tem de mandar a chave.** O teste
  `test_save_returns_the_warning_and_persists_the_gate` passou a enviar
  `"active_status": "", "active_tag": "", "active_min": 0` explicitamente —
  a asserção (`("", "", "self", 0)`) **não mudou**, só ficou explícito o
  que antes era implícito.

**Provas:**
- `test_payload_without_effects_never_erases_the_clauses`
  (novo, em `test_keywords.py`) — cláusula, gate, e o `[]` explícito
  limpando de propósito.
- **No banco real**, com backup antes
  (`backups/clash_rpg-antes-prova-cc-20261003-044815.sqlite3`): payload do
  Control Center aplicado nos **8 gifts** → `13 → 13` cláusulas e os 3
  gates idênticos.

**Contagem corrigida:** são **13 cláusulas**, não 12 — a tabela da seção
acima tinha contado errado.

### Outros 3 achados do mesmo levantamento

| Achado | O que era |
|---|---|
| **`EGO_GIFT_MAX_BY_UPTIE`** | Preenchida: `{1:8, 2:8, 3:8, 4:8, 5:10}` — **degrau único**, o autor: *"só o Uptie 5 muda"*. Teste novo + o teste antigo de "tabela vazia" agora esvazia a tabela só durante ele, para o mecanismo não sumir. |
| **`effect_owner` não existia no editor da Central** | O card só tinha 13 campos, e `effectData()` serializava **só esses 13**. `effect_owner`, `condition_operator`, `max_per_round`, `condition_turn`, `duration_turns`, `max_activations`, `activation_window` **nunca eram enviados** — ou seja, salvava e viravam `auto`/`0`/`None`. Agora: `addEffect` guarda a cláusula original em `dataset.original` e `effectOf()` **mescla** original + formulário; **duplicar efeitos** também passou a usar `effectOf` (antes usava `rowValues`, que perdia tudo). E `effect_owner` ganhou select ("Quem recebe"). |
| **`condition_keyword` não tinha campo** | Sem input, o `allies_with_keyword` do escudo do Livro **não dava pra montar** — e um payload sem ele fazia `SkillEffect` levantar `ValueError`, que o `_effects_from_row` descarta **em silêncio**: salvar o Livro pela Central apagaria o escudo. Ganhou input (só aparece quando a condição é `allies_with_keyword`), mais a validação no `skillValidationIssues`. |

E o `crit_damage_mod` (o `+70` do Clear Mirror) entrou nos **4
formulários** de gift da Central e nos **4 payloads** — antes só existia no
banco, sem jeito de editar.

**149 testes OK** (eram 147) · HTML checado com `vm.Script` · 8 provas
`verify_*` rodam.

---

## ✅ P6 — CONCLUÍDO (2026-10-01, 03:52 → 04:06) — só docs, nenhuma regra mexida

| O que o README dizia | O que é na verdade |
|---|---|
| 7 gatilhos | **10** (`on_kill`, `on_crit`, `on_evade` faltavam) |
| previsão em 5 simulações | **50**, com Paralisia em qualquer rota |
| sem falar de dano × efeitos | **dano é 1 valor só**; efeitos/status disparam **por moeda** |
| 7 status | **12** (`haste`, `special_condition` + os 3 ocultos) |
| Bleed "informativo" | explicado **por que** não soma no dano final |
| `/clash` como forma de lutar | combate **só na Activity** (seção reescrita) |
| Sinking: só "em −45 vira dano" | + **alvo sem Sanidade já vira dano** (P5) |
| "o núcleo atualiza HP e Stagger" | HP só em `enemy_group_members`; **Stagger nunca** |
| "32 testes automatizados" | **119** |

**Extras encontrados e corrigidos junto (mesmo sendo docs):**
- O texto de ajuda do **Sinking** dentro do bot estava descrevendo a regra antiga.
  Corrigido. *(Obs.: a Sentinela é recurso **privado do autor**, para ele conferir
  se está tudo funcionando — não é texto de jogador. De qualquer forma o texto
  estava errado.)*
- A seção de **efeitos** listava 6; são **24** (`EFFECT_TYPES`).

**Confirmado pelo autor nesta rodada:** *"o bot não controla HP ou Stagger
realmente"* — ou seja, a frase antiga do README era invenção. Ficou corrigido
nas duas menções.

**Verificação:** `py_compile` OK · **117 → 119 testes OK** · único `/clash`
restante no README é o que explica que ele **saiu**.

---

## ✅ P5 — CONCLUÍDO (2026-10-01, 03:26 → 03:43)

**O que era:** `on_damage_taken()` só convertia Sinking em dano quando a Sanidade
estava em −45. Unidade com `uses_sanity = 0` chegava como `sanity=None`, caía no
ramo "perde SP" e o SP era baixado **num atributo que ninguém lê** — ou seja,
nada acontecia de fato.

**Regra nova** (`src/domain/status.py`):

| Sanidade do alvo | O que o Sinking faz |
|---|---|
| `None` → **não usa Sanidade** | **dano direto** ← novo |
| ≤ −45 | dano (já existia) |
| normal | perde SP (já existia) |

**Decisão do autor sobre o HP:** *"só aparece junto dos outros efeitos como bleed
e burn e não deve descontar dano real das fichas."*
→ **nenhum HP é descontado.** A linha entra na lista `damage_effects` (mesma do
Bleed), que a Activity publica em `RESOLUÇÃO DO DANO`, e agora diz o porquê:
`Unidade sem Sanidade; Sinking convertido em dano.`

**Caminho:** `trigger_damage_statuses()` → `resolve_hit_status_sequence()` →
`damage_effects` → `RESOLUÇÃO DO DANO`.

**Verificação:** `py_compile` OK · **119 testes OK** (2 novos em
`test_status_engine.py`) · smoke `smoke_sinking_no_sanity.py` **8 OK** ·
smokes anteriores 9/7/7 OK.

⚠️ **Para ninguém "consertar" depois:** esse dano virar HP real exige coluna de
HP — só `enemy_group_members` tem (P4). Como HP está 🔒, o dano de status fica
**visual por decisão**, não por esquecimento.

---

## ✅ P10 — CONCLUÍDO (2026-10-01, 02:30 → 02:43)

**Decisão do autor:** *"só alinhar as 2 regras"* — os dois caminhos continuam
separados, mas param de dar resultado diferente. Fundir fica para depois.

**O que foi alinhado:**

1. **Modificador de defesa no dano** — três pontos do comando do Discord liam
   `enemy["defense_level"]` **sem** `+ enemy["defense_level_mod"]`, enquanto o
   pipeline da Activity usava o mod. Corrigidos:
   - `clash` vs inimigo, quando o jogador vence;
   - ataque sem oposição vs inimigo;
   - follow-up de moeda inquebrável.
   (O PvP já usava o mod — só o lado do inimigo estava errado.)
2. **Sanidade protegida** — a regra era `defender's skill ∈ {guard, evade, ...}`
   nos 4 comandos do Discord, mas `not winner_skill.deals_damage` na Activity.
   A da Activity era **código morto**: quando a skill do vencedor não causa dano,
   `damage_hits` vem vazio e o `resolve_hit_status_sequence` nem roda — ou seja,
   **nunca protegia ninguém**. Adotou-se a regra do Discord em todos os lugares.
3. Criada a constante **`DEFENSIVE_SKILL_TYPES`** — o conjunto estava escrito à
   mão 4 vezes; agora é uma fonte só (menos drift).
4. Removido `defender_protected` do contexto do núcleo (morreu com a regra antiga)
   e `AttackHit` do import do `bot.py` (ficou sem uso no pipeline).

**Verificação:** `py_compile` OK · **117 testes OK** · smoke da injeção **9 OK** ·
smoke de grupo **7 OK**.

**Continua em aberto (não resolvido por aqui):** E.G.O Gifts (P9) e HP de grupo
nos comandos do Discord (🔒 congelado) — os dois caminhos ainda diferem nisso.

---

## ✅ Combate saiu do bot — só a Activity (2026-10-01, 03:00 → 03:22)

**Decisão do autor:** *"os comandos do Discord devem apenas funcionar na
Activity e não por comando no bot"* + *"Desligar a entrada, manter código"*.

Ou seja: **parou de existir luta por comando do bot**. O que ficou no lugar:

| Entrada de combate | O que aconteceu |
|---|---|
| `/clash` (comando slash) | **saiu da árvore** de comandos — não aparece mais no Discord |
| Botão **Ataque livre** | responde com o aviso para abrir a Activity |
| Botão **Follow-up** | idem |
| Botão **Puxar Clash** | idem |

* Aprimores do `/clash` (alvo / sua skill / skill do alvo) foram desligados junto,
  senão o Python quebrava — a função `clash_unificado` continua no arquivo.
* Texto do `/painel` deixou de anunciar o `/clash`.
* **Nada foi apagado:** `clash_unificado`, `clash_jogador_impl`,
  `clash_inimigo_impl`, `BattleActionView`, `PvPChallengeView` e
  `open_free_attack` continuam no `bot.py`. Só ficaram sem quem os chame — se um
  dia precisar voltar, é só religar os botões e o decorator.

**Consequência:** o **P10** perdeu boa parte do motivo. Os dois caminhos de Clash
agora existem, mas **só um é alcançável** (o da Activity). O outro virou código
reserva — alinhar regra dele passou a ser opcional.

**Verificação:** `py_compile` OK · **117 testes OK** · smoke
`smoke_no_combat_entry.py` **7 OK** (comandos = `batalha, inimigo, painel,
personagem, sentinela, skill`; nenhum deles faz combate).

---

## 🟢 Rodada "mesma base de efeitos" — CONCLUÍDA (2026-09-29 → 2026-10-01)

**Pedido do autor:** os dois Clashes da Activity (Encounter e Resolver) precisam
seguir a mesma base, **principalmente nos efeitos**. Decisão tomada:
*"dá pra injetar no núcleo, mas os efeitos precisam mostrar não no mesmo lugar
do dano — deve ser uma espécie de cálculo separado para colocarmos abaixo do
dano final, na resolução de dano."*

### Feito e verificado nesta rodada

1. **`execute_unopposed_job` passou a respeitar `target_kind`** — a Activity lista
   **SINNER como alvo** (`activity_server.py:784`), então o botão *"TESTAR ATAQUE —
   SÓ DANO"* contra um jogador quebrava (lia como inimigo e dava erro, ou pegava um
   inimigo com o mesmo id). Agora trata `player` / `enemy` / `enemy_group_member`
   com a mesma regra de sanidade do Clash (`characters` **não** tem `uses_sanity`).
2. **Injeção no núcleo** — `clash_execution.execute_clash_job(..., effects=dict)`
   aceita 3 gatilhos, cada um devolvendo `(efeitos_de_skill, efeitos_de_dano)`:
   - `on_round_start(esquerda, direita)` — **antes das moedas** (é o `on_use`;
     antes rodava depois do dano e era só registro);
   - `on_before_damage(ctx)` — com o vencedor já sabido, **antes do dano**
     (`clash_win`/`clash_lose`, `before_attack`, Bleed);
   - `on_after_damage(ctx)` — **na resolução**: dano %, Poise, críticos, status do
     acerto e `after_attack`.
   O SP/paralisia/mods do Clash são confirmados **antes** de `on_before_damage`,
   para o que os efeitos escreverem sobreviver (mesma ordem do comando do Discord).
   `effects=None` ⇒ comportamento antigo (é o que os testes usam).
3. **`activity_clash_effects(guild_id)`** novo em `bot.py` — a sequência de efeitos
   do Clash da Activity, a mesma do comando do Discord.
4. **Pipeline reestruturado** (`process_clash_pipeline`): as Skills agora são lidas
   **antes** de executar (o núcleo precisa delas para injetar), e o bloco de efeitos
   duplicado (~40 linhas que rodavam só pós-dano) foi removido.
5. **Split `effects` / `damage_effects`** nos três caminhos: clash, unopposed e
   enemy_unopposed. `effects` = o que a Skill faz antes da moeda;
   `damage_effects` = o cálculo da resolução (Bleed, dano %, Poise, críticos,
   status do acerto, `after_attack`).
6. **Embeds**: campo **`RESOLUÇÃO DO DANO`** logo abaixo do número, em
   `publish_queued_clash` e `publish_unopposed_attack`. Nada se perdeu — o que era
   uma lista só virou duas, ambas renderizadas.

**Verificação:** `py_compile` OK · **117 testes OK** · smoke da injeção **9 OK**
(`Temp\opencode\smoke_effects_injection.py`) · smoke de grupo **7 OK**.

### Próximo passo (de onde parar)

- [x] **P10** — as 2 regras foram alinhadas (ver seção P10 acima). Os caminhos
      **não** foram fundidos: E.G.O Gifts e HP de grupo nos comandos do Discord
      continuam diferentes de propósito (P9 / 🔒).
- [x] `AttackHit` estava sem uso no pipeline → removido do import.
- [x] **Combate tirado do bot** — `/clash` fora da árvore e os 3 botões de combate
      do painel avisando para abrir a Activity. Código antigo preservado.
- [x] **P3** (Bleed no embed) → **encerrado**: autor confirmou que os embeds
      estão funcionando direito. Ganhou `RESOLUÇÃO DO DANO` logo abaixo do número.
- [x] **P5** (Sinking × inimigo sem sanidade) → corrigido. O dano fica
      **visual**, junto de Bleed/Burn, **sem descontar HP** (decisão do autor).
- [x] **P6** (README) → reescrito. 10 gatilhos, 50 simulações, dano único ×
      efeitos por moeda, 12 status, Bleed explicado, combate só na Activity.
- [x] **P7 — desenho do sistema de E.G.O Gifts** → `EGO_GIFTS_DESENHO.md`,
      hoje em **v2.1** (04:35 → **05:29**, mtime real). Autor pediu *"desenhar o sistema
      inteiro primeiro"*. Investigação mostrou que **já existe** tabela,
      editor no Control Center e equipar sem limite — o que falta é **ler** a
      `effects_json`.
      A **v2** trouxe: **keyword na ficha** como base (`characters.keywords`),
      **gift também no dano** e **HP como modo manual**.
- [x] **P9 (gift no dano)** → **fechado**: entra no Clash **e** no dano.
      Correção = 4 lugares em `clash_execution.py` (136/138/156/158).
- [x] **P7 — Etapa 0 CONCLUÍDA** (05:41 → 05:47): (a) bloco de gifts
      hardcoded no `bot.py` **removido** (`db.heal_character` inexistente,
      comparação por nome, `has_carousel` morto — não perdia efeito nenhum);
      (b) listas do editor agora vêm de **`/api/meta/effects`** — `on_crit`,
      `haste`, `reuse_coin` e 8 condições voltaram a aparecer no dropdown.
      **123 testes** (4 novos em `tests/unit/test_control_center_meta.py`).
- [x] **P7 — Etapa 1a (back) CONCLUÍDA** (05:50 → 05:56): `effects_json` →
      `SkillEffect` → `apply_skill_trigger`. Filtro genérico
      **`triggered_effects`** extraído de `triggered_skill_effects` (40 call
      sites intactos), **`db.list_active_ego_gift_effects`** (reusa
      `_effects_from_row`, falha devolvendo `()`) e **`triggered_gift_effects`**.
      Log marca a origem com ``◆ <NOME EM CAIXA ALTA>``.
- [x] **BUG CORRIGIDO — cláusula ruim apagava o gift inteiro** (~06:40):
      `_effects_from_row` embrulhava a lista num `try` só, então **uma**
      cláusula inválida devolvia `()` e silenciava as outras (um `tremor_burst`
      com `count` derrubou 4 cláusulas do teste de fábrica). Agora cada item
      cai sozinho. JSON não-lista e item não-dict também são ignorados.
- [x] **Teste de fábrica real (Arcana) PASSOU** (~06:47): na cópia do banco,
      Imperfect Eye dispara em `clash_win` (Tremor 2×2, Burn 2×2, Tremor Burst)
      e em `on_crit` (Tremor Burst). **135 testes.**
- [x] **BLOQUEIO RESOLVIDO — donos dos gifts encontrados** (~07:0x): autor ligou
      "Message Content Intent" → conteúdo legível. Categoria `⩺Fichas⩹`
      (`1405724102819582085`, Arcana) = 10 canais-fórum, um por player.
      **7 dos 8 exemplares existem**; só falta `Volatile's earring`, e apareceu
      um **fora da lista**: `Pingente: Presente da Rebeca` (karlos).
      **Donos** (autor das msgs → `characters.name`):
      `mask`→_mask351→**Rosemary Véspera** (3 gifts, **já no banco**),
      `karlos`→kkralos→**Pablo Suindara** (3 gifts, **faltam**),
      `bento`→gps___→**Blade** (2 gifts, **faltam**),
      `raul`→**Lucy Galore**, `cris`→**Zote**, `fernando`→**Zero**,
      `arthur`→**Bernd Klaus**, `nk`→**Elizabeth** (esses 5 têm E.G.O
      *skill*, não gift), `gamerol`→**Big three**, `cesar` (682216211420807205)
      e `thiago` sem ficha. **→ 5 gifts ainda não existem no banco.**
- [ ] **Próximo: P7 — Etapa 1b (UI)** — montar o editor de efeitos da skill na
      ficha do gift + templates dos 8 exemplares (desenho §3.1) → depois
      Etapas 2–7. P8 (embeds) fica para depois.

### 🎯 SPEC FECHADA — Imperfect Eye (07:55 → 08:05) · autor: *"podemos colocar ele no bot"*

O que travava e foi decidido (9 decisões):

| # | Decisão | Por quê |
|---|---|---|
| 1 | Gatilho = **vitória no clash inteiro**, não moeda-a-moeda | *"colocamos ao ganhar o clash por inteiro"* — moeda-a-moeda seria complicado |
| 2 | **O Glimpse carrega o escalamento**, não o Tremor | assim o `0×0` do burst deixa de ser bug e vira **intencional** |
| 3 | Gift **não dá count extra**; count do alvo **não é sobrescrito** | só o `1` que `database.py:835` força na criação; `add_status` soma, não troca |
| 4 | **Tremor Burst tira 1 Count — motor, pra todo mundo** | `status.py:94` preserva hoje (`count_after = count`); autor: *"tem que ser pra todo mundo"* |
| 5 | **Sem piso de count** (não é pra "zerar não") | morrer é o plano — o teto fica guardado no Glimpse |
| 6 | Limite **5 clash wins** → **10 Tremor/Burn ↔ 5 Glimpse**, alinhados | troca o "10 vezes por habilidade" por teto de **usuário** |
| 7 | Glimpse **só zera na troca de rodada depois de chegar em 5** | *"impede o glimpse de chegar a 5 e zerar de uma vez"* |
| 8 | **Bônus do Glimpse entram agora** | +1 Clash Power por stack; a cada 2 stacks +1 Coin Power / +2 Final Power |
| 9 | **Amplitude Conversion → Tremor-Scorch fica de fora** | ~~autor vai fazer noutro chat~~ — **feito em 2026-10-01**: efeito `amplitude_conversion_scorch` + coluna `tremor_type` (ver CHANGELOG) |

**Fórmula final** — a cada `clash_win`, nesta ordem:

1. Glimpse **+1** (max 5)
2. Tremor **`2 × Glimpse`** e Burn **`2 × Glimpse`** no alvo (potência só)
3. Tremor Burst → −1 Count → count 0 apaga a linha (`database.py:790`) ✅ **esperado**

```
clash win   glimpse   tremor/burn   após burst
    1         1           2           0×0
    2         2           4           0×0
    3         3           6           0×0
    4         4           8           0×0
    5         5          10           0×0   ← limite
   ── troca de rodada ──  glimpse → 0, recomeça
```

> ⚠️ **`"(10 vezes por habilidade)"` (EGO_GIFTS.md:58) deixou de valer** — o teto
> agora é do usuário (Glimpse 5 × 2 = 10), não da habilidade.

**Ordem de construção:** ① Glimpse como recurso novo (Etapa 2, stack 5,
expiração por rodada) → ② valor condicional `2 × Glimpse` via `condition_status`
(motor já calcula multiplicador em `bot.py:784`) → ③ `status.py:94` consumir
1 Count → ④ bônus do Glimpse no Clash/Coin Power → ⑤ limite `2×/rodada` do
`[Ao Critar]`.

---

### 🔍 Varredura dos outros 7 — quem precisa da mesma atenção

| Gift | O que trava | Veredito |
|---|---|---|
| **1.8 Carousel Figurine** | **PRINT TRUNCADO** — a última linha é *"o personagem ganha seu respectivo efeito: (???)"* | 🔴 **PRECISA DO PRINT COMPLETO** |
| **1.6 The Family's Resentment** | **HP 🔒** (modo manual) é o *núcleo* — *"cura 30% do HP como dano"*; + Bloodfeast | 🔴 **BLOQUEADO**: sem HP não faz nada |
| **1.3 Clear Mirror, Calm Water** | *"Dano Crítico +70%"* — **não existe stat de Dano Crítico**; condição "crítico consumiu Poise Count" | 🟠 **que stat é esse?** |
| **1.4 Reminiscence** | **Afinidade Gloom 🔒** (autor: bot não tem Sin Affinity); fórmula **`+(4 / #Moedas)` dinâmica**; varre fichas de 3+ aliados | 🟠 afinidade + fórmula |
| **1.1 Volatile's earring** | `Protection` **não está** nos 24 `effect_type`; sub-regra *"em vez de ganhar X"* (Etapa 8); condição "habilidade com +5 Moedas" | 🟠 **parece penalidade** — confirmar que ganhar −4 Coin Power por skill boa é intencional |
| **1.7 Livro da vingança: Annex** | **Escudo persistente 🔒** (decisão 2) = metade do gift; Envy Resource; gate 3+ da Middle | 🟠 metade bloqueada, metade dá |
| **1.2 Dreaming Electric Sheep** | Envy Resource; tag Slash/Envy; "por 2 rodadas"; escopo `todos_os_aliados` | 🟠 **contradição de tempo**: gate = *"quando possuir +6 Envy Resource"*, mas efeito = *"no início do combate"* — 1× ou sempre? |
- [ ] `git` **não está instalado** → nada commitado, inclusive LICENSE.

---

## Contexto de design (NÃO é bug — não "consertar")

Adaptações para RPG, decididas pelo autor:

- **O dano final é um valor só.** Não é N hits de 1 dano por moeda como na Limbus.
- **Os efeitos/status, porém, disparam por moeda.** Bleed, Rupture, Sinking contam cada moeda
  rolada. Coerente: efeito conta por moeda, Vida desconta o total.
- **Escala de Offense/Defense Level é própria** (`nível × (3 + atributo/2)`), não a da Limbus.
- **SP `+5 / −5`** com perda ao perder Clash — punição de RPG.
- **Paralyze está correto** (Coin Power → 0 por moeda, sem mexer na chance de Heads).
  A fórmula triangular da wiki `P = (N²+N)/2` **não se aplica** — manter linear.
- 🔒 **HP e Stagger não serão automatizados por enquanto** — fichas externas (passivas,
  E.G.O Gifts) e ainda não existe um método bom de integrar essas regras ao sistema.

---

## ✅ P1 — CONCLUÍDO (2026-09-29, 05:16 → 05:23 · 6 min 57 s)

**O que mudou:**

1. **Previsão de Clash unificada.** `prediction_with_paralysis` foi movida para
   `src/domain/combat/engine.py` e exportada pelo pacote — bot e Activity passam
   a chamar **a mesma**. Padrão: **50 simulações + regra de Paralisia**.
   Removidas a cópia do `bot.py` (5 simulações) e a chamada direta de
   `clash_execution` (50 sem regra).
2. **A Activity parou de calcular combate.** `execute_clash_job` e
   `execute_unopposed_job` **não são mais importados** por `activity_server.py`.
   O fallback de 300 ms virou espera de **10 s** (ajustável pelo env
   `ACTIVITY_CLASH_TIMEOUT`) e, ao estourar, o job é **cancelado** — quem resolve
   é só o bot, e nunca mais há resultado duplicado.
   *Consequência:* se o bot estiver fora, o Encounter/Activity espera os 10 s e
   devolve erro claro em vez de responder com uma conta diferente.
3. **`clash_execution.execute_unopposed_job` foi deletada** (2 102 bytes).
   Resta **uma única** implementação de ataque unilateral: a de `bot.py`.
4. Teste `test_clash_execution.py` ajustado para o novo nome da função.

**Verificado:** `py_compile` OK nos 6 arquivos · **117 testes OK**.

---

### Diagnóstico original (histórico)

**Isso era a causa raiz de "algo que ocorreu na produção".**

### 1. Dois `execute_unopposed_job` com o mesmo nome, em arquivos diferentes

| | `bot.py:4832` | `clash_execution.py:142` |
|---|---|---|
| Chamado por | **Discord bot** (`bot.py:4993`) | **Activity/Encounter, só como fallback** (`activity_server.py:843`) |
| E.G.O Gift mods | ❌ não | ❌ não |
| Bleed / gatilhos / status de hit | ✅ | ❌ devolve `"effects":[]` |
| Charge | ✅ | ❌ |
| Críticos | ✅ | ❌ |
| HP | ❌ | ❌ |
| Core trace | ❌ | ❌ |

### 2. O roteador é um **race condition de 0,3 s**

`request_bot_clash()` (`activity_server.py:783`):

```python
job_id = database.enqueue_clash_job(...)   # manda pro bot processar
notify_bot_outbox()
# espera ATÉ 0.3 s (deadline de 300 ms, checando a cada 50 ms)
if job["status"] == "completed": return ...   # ✅ caminho rico (bot.py)
# estourou? → roda AQUI, localmente, com a função pobre
runner = ...; execute_unopposed_job(runner, request_data)   # ❌ caminho pobre
```

> **Sob carga, o mesmo comando dá resultado diferente.** Às vezes roda pelo bot
> (efeitos, Bleed, Charge, críticos), às vezes roda na Activity (nada disso).

### 3. `prediction_with_paralysis` vs `clash_execution` — mesmo problema

| | `bot.py:1393` | `clash_execution.py:38` |
|---|---|---|
| Simulações | **5** | **50** |
| Regra de Paralisia | hardcode `0%` / `100%` | não tem |

**Ação:** definir **uma** implementação canônica e eliminar a duplicata. A Activity não deveria
resolver combate sozinha — ou, se resolver, deve chamar **exatamente** a mesma função.

---

## ✅ P2 — CONCLUÍDO (back) — 2026-09-29, 05:24 → 05:47 · ~23 min

**Decisão do autor:** *"o ataque unilateral deve ter todas as funcionalidades do clash normal,
e o do encounter também."* — **só o back**; embeds ficam para depois (P8).

**Decisões de escopo:** E.G.O Gifts **não** entram agora → viram pauta separada (P9).
HP/Stagger continuam congelados (🔒).

### Fila de Clash (pedido do autor)

- `claim_clash_jobs(5)` → **`claim_clash_jobs(1)`**: um Clash por vez, ordem garantida,
  saída do Discord nunca se mistura (o worker já roda a cada 1,5 s).
- Espera da Activity passou a ser **dinâmica**: `10 s + 5 s` por Clash na frente
  (teto de 60 s), ajustável por `ACTIVITY_CLASH_TIMEOUT` e `ACTIVITY_CLASH_QUEUE_TIMEOUT`.
  Quem chega na fila não vê aviso de timeout mesmo com o bot funcionando.
  Jobs órfãos (parados há mais de 1 h) não contam.

### Paridade implementada

- [x] Removida a chamada **duplicada** de `prepare_charge_enhancements` — a 1ª passava
      `("enemy", enemy_id)` mesmo quando o alvo era `enemy_group_member`, e o 2º
      `charge_log` sobrescrevia o 1º log.
- [x] Removidos os gates `if not member_id` → integrante de grupo agora recebe
      `apply_skill_damage_percent`, `apply_critical_triggers`,
      `revert_temporary_self_trigger`, `resolve_hit_status_sequence` e `after_attack`.
- [x] `execute_enemy_unopposed_job` ganhou `trigger_bleed_action`, `apply_skill_damage_percent`,
      `apply_poise_critical`, `apply_critical_triggers` e `revert_temporary_self_trigger`
      — a mesma sequência do Clash normal. Regra de críticos passou a ser idêntica.
- [x] `core_trace` retornado também pelo ataque unilateral do jogador
      (`combat.unopposed_resolved`).
- [x] **Suporte a `enemy_group_member` em 4 pontos** que o un-gate passou a alcançar
      (antes escreviam no `enemies` com o id do integrante, ou não rodavam):
      `apply_skill_trigger` (paralisia no alvo), `trigger_damage_statuses` (SP do alvo,
      clamping ±45), `resolve_hit_status_sequence` (ficha do alvo) e
      `revert_temporary_self_trigger` (ator integrante).
      *Schema confirmado: `enemy_group_members` tem `paralysis`, `sp`, `hp`, `hp_max`
      e todas as colunas `*_mod`.*

**Verificado:** `py_compile` OK · **117 testes OK** · smoke de 7 verificações no banco real
(`smoke_group_member.py`) — todas OK.

### O que ficou em aberto no P2

- **HP não aplicado** no ataque unilateral (o Clash aplica p/ integrante de grupo).
  **Proposital:** HP/Stagger congelados (🔒).
- **E.G.O Gifts** fora → **P9 (pauta nova)**.
- **Embed** do unilateral simplificado e footer errado → **P8**.
- `round_status_embed` trata todo não-jogador como `db.get_enemy_by_id` → com integrante
  de grupo exibe o nome errado. É exibição → **P8**.

---

## ✅ P3 — ENCERRADO (2026-10-01) — autor confirmou que os embeds estão ok

> *"os embeds aparentemente estão funcionando direito"* — não foi achado cenário
> em que a linha não apareça. **Fechado.** Se um dia aparecer de novo, o texto
> técnico abaixo serve de mapa.

- **Especificação (decisão do autor):** Bleed fica **fora** do dano final. Deve aparecer
  **logo abaixo de `〔 DANO FINAL 〕`**, no campo de efeitos do `damage_embed`.
- **Estado atual:** `damage_embed()` (`bot.py:1261`) é construído **sem** os logs;
  os campos `〔 EFEITOS ATIVADOS 〕` e `【 IMPACTO DOS STATUS 〕` são anexados depois
  (`bot.py:3255-3256`, `6230-6231`, `6525-6526`), **já depois de "TIPO DE AÇÃO"**.
  `add_status_impact()` (`bot.py:971`) ainda filtra por palavra-chave — duplicando a linha
  nos dois campos.
- **Cálculo está certo:** `on_action()` (`status.py:53`) → `damage = potency × min(count, coins)`.
- **Falta:** descobrir em qual cenário a linha não chega a aparecer.

---

## P4 — HP: correção e bug latente

**HP *é* alterado pelo combate — parcialmente.**

| Alvo | HP aplicado? | Onde |
|---|---|---|
| `enemy_group_members` (inimigo em grupo) | ✅ **sim** | `clash_execution.py:84-87`, sem guarda |
| `enemies` (inimigo único) | ❌ não | tabela **não tem coluna `hp`** (`database.py:108`) |
| `characters` (jogador) | ❌ não | sem coluna; vive em `character_profiles.profile_json` |
| Stagger | ❌ **nunca** | não existe escrita em lugar nenhum |

- 🔴 **Bug latente:** `if ... and "hp" in loser_row` (`clash_execution.py:92`)
  — em `sqlite3.Row`, `in` testa **valores**, não chaves. **Confirmado em Python 3.13:
  dá sempre `False`.** Hoje inofensico (nenhuma tabela tem `hp`), mas **se existir `hp`
  em `enemies` no futuro, o UPDATE nunca roda.** Trocar por `.keys()` / checar a tabela.

---

## ✅ P5 — RESOLVIDO (2026-10-01) — ver seção P5 no topo

> Regra corrigida e **HP decidido**: o dano fica **visual**, na lista de
> efeitos junto com Bleed/Burn, e **não desconta ficha**. Texto original abaixo.

- **Local:** `on_damage_taken()` (`status.py:39-50`) — só virava dano quando `sanity <= -45`.
- **Problema:** unidade com `uses_sanity = 0` tem o SP reduzido e **nada acontece**.
- **Regra da Limbus:** unidade **sem SP leva dano direto**. *(A chamada "dano de
  Gloom" é terminologia da Limbus — o bot **não tem Sin Affinity**, então o texto
  e o código ficam neutros.)*
- **Confirmado pelo autor como bug real — tem que ser resolvido.**

---

## ✅ P6 — RESOLVIDO (2026-10-01) — ver seção P6 no topo

O README foi reescrito. Lista original abaixo, para histórico:

- Diz **7 gatilhos**; o código tem **10** (`on_kill`, `on_crit`, `on_evade` em uso).
- Diz previsão em **5 simulações** — ver P1.3.
- Não documenta que **dano é consolidado (1 valor)** e que **efeitos são por moeda**.
- Não documenta `haste`, `bloodfiend`, `bloodbag`, `special_condition`.
- Não explica por que **Bleed é cálculo por moeda mas não é somado ao dano** —
  para ninguém "consertar" pra pior.

---

## 🟡 P7 — E.G.O Gifts: DESENHO v2.1 (2026-10-01, 04:35 → 05:29)

> **Desenho completo em `EGO_GIFTS_DESENHO.md` (v2.1).**
> **v1** ~04:35→~05:00 · **v2** ~05:00→~05:15 · **v2.1** ~05:15→**05:29** — incorporaram informações
> do autor que mudaram o desenho:
>
> 1. **Keyword nas fichas** ("ficha de poise", "aliados da Middle",
>    `unique bleed` × `bleed`) é a **base que falta** — `Reminiscence` e
>    `Livro da vingança: Annex` dependem dela. Só `charge` tem algo parecido
>    hoje (`charge_potency_enabled` + `consume_charge`).
> 2. **Gift entra no DANO também** → **fecha a P9** (ver seção P9).
> 3. **HP/Stagger = resolução MANUAL** — o bot publica a linha com o valor e
>    o autor aplica. Mantém o 🔒 intacto e faz o gift valer alguma coisa.
> 4. **Teto de gifts = Uptie** e **`false_hunger` fica "Falsa Fome" na tela**,
>    marcado `unique_bloodfeast` pelo keyword.

> **Decisões do autor:**
> 1. *"desenhar o sistema inteiro primeiro"* (foi contra a minha recomendação
>    de começar simples — registrado aqui).
> 2. **Afinidade e escudo persistente fora**; **HP vira modo manual**.
> 3. **"Recurso novo" reaberto** — eu tinha contado como caro e estava errado:
>    são ~12 pontos do tipo "adicionar nome em conjunto". Sem isso, os 3
>    gifts equipados dele ficariam inertes.
> 4. ~~Lista livre, sem teto~~ → **teto vem do Uptie** (9). Enquanto os
>    números não existirem, segue sem teto.
> 5. Mestre equipa e troca a qualquer momento.
> 6. **Keyword na ficha é a base a construir** (`characters.keywords`).
> 7. **Gift entra no clash e no dano** (fecha P9).
> 8. **HP/Stagger = modo manual.**
> 9. **Teto de gifts = Uptie** — *"o uptie 5 da Rose deixa ela colocar de
>    10–12"*, mas **os números ele não lembra** → `EGO_GIFT_MAX_BY_UPTIE`
>    configurável, **vazio por enquanto** (nada muda).
> 10. **`false_hunger` continua "Falsa Fome" na tela**; a **keyword** é que
>    rotula `unique_bloodfeast`. Nenhum rename (§7.5 do desenho).
> 11. **O mestre precisa criar gift SEM passar por IA** — *"quem faz eles é o
>    mestre da mesa; o problema é um método de incorporar eles no sistema sem
>    ter que passar por IA."* → **o editor já existe** e é o da skill
>    (§3.1 do desenho): cards, dropdowns, resumo em português, validação,
>    presets e templates. Falta montar no gift.

**O que a investigação achou** (muda o diagnóstico antigo):

- Já existe `ego_gifts` (`database.py:281`) + editor no Control Center +
  `get_total_ego_gift_modifiers` ligado ao Clash. **Equipar já funciona.**
- `effects_json` (`database.py:289`) é **gravada e nunca lida** — é a coluna
  certa, só falta ler.
- O caminho da Activity passa **tudo** por `apply_skill_trigger`
  (`bot.py:660`) → **1 ponto de injeção cobre os 10 gatilhos**.
- Seus 3 gifts (Tier 5, ativos) estão com **mods 0 e `effects_json = []`** —
  hoje não fazem nada.
- **O editor de efeitos já existe** para skill (`control_center.html:596-605`)
  e `save_ego_gift` **já grava** `payload["effects"]`. Só falta montar.
- **Bug novo — CORRIGIDO na Etapa 0b:** as listas do editor eram cópias
  **escritas à mão no HTML** e **já tinham divergido** — `haste`,
  `reuse_coin` e `on_crit` não apareciam, nem 8 condições. O motor aceitava,
  mas **o mestre não conseguia escolher**. Agora vêm de
  **`/api/meta/effects`** (§2.6 do desenho) + 4 testes.
  **Pendente:** a Activity tem a **4ª cópia** dessas listas
  (`SkillsTab.jsx:7`, falta `consume_devotion_repressed`) — outro servidor.

**2 bugs que bloqueiam — ✅ RESOLVIDOS na Etapa 0:**
- ~~`bot.py:566` chama `db.heal_character` que não existe~~ → **bloco inteiro
  removido** (`bot.py:555-567`), junto com o `if` por nome que decidia
  comportamento pelo nome do gift. Não perdia efeito nenhum: a cura de HP
  passa a ser cláusula no **modo manual** (desenho §8).
- ~~Código morto: `has_carousel` lido e nunca usado~~ → **removido** com o
  mesmo bloco.

---

### Diagnóstico original do autor (mantido como histórico)

O problema não é a variável, é o **gatilho**.

- O que existe hoje: `get_total_ego_gift_modifiers()` — um **somador genérico** de
  `{base, coin, clash, offense_level, defense_level}_mod`.
- Isso só serve para gift que é **"sempre +X num stat"**.
- Gift com condição (**"ao matar"**, "a cada N turnos", "se alvo tiver Y") precisa de:
  um **evento** no qual ele dispare + um **lugar** para ativá-lo. Esses eventos
  (`on_kill`, fim de turno, etc.) não estão ligados a nenhuma lista de gifts.
- Gift que **adiciona mecânica nova** (tipo os da Rosemary, que o autor apagou do código)
  não resolve com modificador — exige implementar a mecânica em si.

**Conclusão:** não é pendência de correção, é um **sistema a construir** —
desenhado no topo desta pauta e em `EGO_GIFTS_DESENHO.md`.

---

## P8 — Embeds são da versão antiga 🔒

**Diagnóstico do autor:** os embeds vêm da versão antiga do bot, quando **não existia Activity** —
era só o bot. Agora que há dois front-ends, eles **precisam ser recalibrados e refinados depois**.

Sintomas já vistos (não atacar agora, só marcar):

- `publish_unopposed_attack` (`bot.py:4910`) não mostra escudo, ajuste de nível nem
  modificador percentual — o `damage_embed` mostra. **Mesmo dado, dois formatos.**
- Footer *"sem ganho ou perda de Sanidade"* — regra de uma versão que talvez não valha mais.
- Bleed entra em campos anexados fora do `damage_embed`, depois de "TIPO DE AÇÃO" (ver P3).
- `add_status_impact()` filtra por palavra-chave e **duplica** a linha em dois campos.

---

## ✅ P9 — RESOLVIDO (2026-10-01, na v2 do desenho) — gift entra no CLASH **e no DANO**

**Decisão do autor (v2 do desenho):** *"tem ego gifts que mexem no dano
também, então entra tanto no clash quanto no dano."*

Onde eles contam hoje:

| Caminho | `get_total_ego_gift_modifiers()` |
|---|---|
| `execute_clash_job` (fila — Activity/Encounter) | ✅ **previsão e nível do Clash** (`clash_execution.py:80-83`) |
| **Dano final** (`clash_execution.py:136` e `138`) | ❌ **falta** |
| **Follow-up** (`clash_execution.py:156` e `158-160`) | ❌ **falta** |
| Comandos interativos do `bot.py` (PvP e vs inimigo) | ❌ (entrada desligada no combate-do-bot) |
| Ataque unilateral (`execute_*_unopposed_job`) | ❌ (decidido no P2) |

**A correção são 4 lugares**, todos em `clash_execution.py`, e `left_ego` /
`right_ego` já estão no escopo (calculados nas linhas 78-79):

```python
winner_ego = left_ego if result.winner == "left" else right_ego
# 136 → + winner_ego["offense_level_mod"]
# 138 → + winner_ego["base_power_mod"] / + winner_ego["coin_power_mod"]
# 156 e 158-160 → idem, com followup_ego
```

**Mexe em balanceamento** → é o **Etapa 6** do desenho
(`EGO_GIFTS_DESENHO.md` §11 e §14), com teste.

P7 continua com o lado **sistema** (gatilhos, duração, keyword); esta P9 era
o lado **combate** (quem entra em qual fórmula) — **fechada**.

---

## ✅ P10 — RESOLVIDO (2026-10-01) — ver seções do topo

> **Como acabou:** (1) as 2 regras de cálculo foram alinhadas; (2) **o caminho da
> direita saiu de circulação** — os comandos/botões de combate do bot foram
> desligados e só a Activity combate. O código de lá continua no arquivo como
> reserva, então a tabela abaixo só importa se alguém religar esse caminho.

Descoberto ao fazer a paridade: **"o Clash normal" também tem duas implementações**,
e elas divergiam:

| | `execute_clash_job` (fila) | Comandos interativos do `bot.py` |
|---|---|---|
| E.G.O Gifts no stat | ✅ | ❌ |
| HP aplicado (grupo) | ✅ | ❌ |
| Status / Bleed / críticos | só quando o chamador faz | ✅ |
| `core_trace` | ✅ | PvP ❌ / vs inimigo ✅ |

Hoje o **Activity/Encounter + pipeline do bot** é o único caminho alcançável.

**Referência: o pipeline da Activity.** O caminho dos comandos virou código reserva
(entrada desligada em 2026-10-01).

---

## 🔒 Fora de escopo por enquanto

Exigem **criar** mecânica, não corrigir:

- **E.G.O Gifts com mecânica própria** — *só as partes de baixo* (ver P7 e
  `EGO_GIFTS_DESENHO.md` §13): **afinidade** (o bot não tem Sin Affinity),
  **escudo persistente**, **tag de skill** (Slash/Envy — `Skill` não tem
  `tags`), **sub-regra** ("em vez de X, ganhe Y"), **multiplicador de ganho**
  ("dobre todo Bloodfeast") e a **camada 2** de mecânica por recurso (§7.5).
  O resto do sistema foi desenhado e está **dentro** do escopo (Etapas 0–7).
  ***HP mudou de status:** não está mais "fora" — virou **modo manual**
  (`EGO_GIFTS_DESENHO.md` §8): o bot **publica a linha** com o valor e o autor
  aplica. Continua sem alterar HP/Stagger no banco.*
- Low Morale (≤ −30 SP) e Panic (−45 SP) — não existem.
- Stagger de verdade (multiplicadores ×2 / ×2,5 / ×3, inatividade por turno).
- Stagger: 2 thresholds fixos `[20%, 50%]` para todo mundo (Limbus varia 1 a 3 por Identity).
- Sin Resonance / Absolute Resonance.
- `Clash Count × 0,03` como modificador estático de dano.
- Faixas da previsão de Clash (bot `20/40/60/80`, jogo `10/40/60/90`).
