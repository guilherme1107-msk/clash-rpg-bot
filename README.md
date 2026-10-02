# Clash RPG Bot

Protótipo de bot para RPG no Discord baseado em disputas de moedas, sanidade, skills configuráveis e encontros controlados pelo mestre.

> Projeto comunitário, experimental e não oficial. Não possui vínculo ou aprovação da Project Moon. A versão pública deve usar identidade visual e arquivos com licença adequada.

## Estado do projeto

Esta versão está funcional para sessões locais e passa por uma migração gradual
para a arquitetura em `src/`, conforme descrito no [roadmap](ROADMAP.md).

O bot calcula Clash, dano e seus efeitos oficiais. HP, Vida Máxima, Stagger,
SP, Light e status são persistidos e sincronizados entre bot, Activity e Central.
O mestre mantém a decisão narrativa, mas não precisa replicar manualmente a
rolagem, a resolução ou as atualizações de recursos.

Na ficha, o editor visual de modificadores permite aplicar Paralisia, Base Power,
Coin Power, Clash Power, Offense Level e Defense Level. Valores positivos são
Up e valores negativos são Down; Defense Level modifica skills defensivas e o
cálculo de dano recebido.

Na branch de desenvolvimento, o motor já está separado em `src/domain`: modelos
ficam em `models` e regras de resolução em `combat`. O antigo `clash_engine.py`
permanece como compatibilidade temporária.

## Principais recursos

- Fichas separadas por servidor.
- Sanidade entre −45 e +45 SP.
- Skills positivas, negativas, defensivas e inquebráveis.
- Clash contra jogadores e contra inimigos cadastrados pelo mestre, feito na **Activity**.
- Previsão probabilística em 50 simulações, com a mesma regra de Paralisia em qualquer rota.
- Animação de moedas e registro de até dez rodadas.
- Base Power, Coin Power, Clash Power, Paralisia e Offense Level temporários.
- Dano final calculado depois do Clash.
- Efeitos por gatilho e por moeda.
- Oficina visual para criar e administrar skills.
- Sessões de batalha persistentes com fases, participantes e ações hostis.
- Log local decorado e persistência SQLite.
- App Composer na Central para formatar, visualizar e publicar mensagens pelo ClashBot.
- Tags permanentes e personalizadas para hostis, utilizáveis por condições de skills.

## Início rápido

### Requisitos

- Python 3.11 ou superior.
- Uma aplicação configurada no Discord Developer Portal.
- Permissão para adicionar o bot ao servidor de teste.

### Instalação no Windows

Copie `.env.example` para `.env` e preencha pelo menos `DISCORD_TOKEN`:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe bot.py
```

Não é necessário ativar o ambiente virtual. Isso evita problemas com a política de execução do PowerShell.

### Configuração mínima

```env
DISCORD_TOKEN=cole_seu_token_aqui
DISCORD_GUILD_ID=123456789012345678
DATABASE_PATH=clash_rpg.sqlite3
CLASH_GUILD_ID=949911180841975849
CLASH_CHANNEL_ID=1536852812623908874
CLASH_CHANNELS=949911180841975849:1536852812623908874,1392000415108960426:1536852944518127748
```

Durante o desenvolvimento, `DISCORD_GUILD_ID` registra os comandos rapidamente nos servidores informados. Separe vários IDs com vírgula. Deixe vazio para sincronização global.

Nunca publique `.env`, token, banco SQLite ou arquivo de auditoria.

O **App Composer** da Central usa o token somente no backend local. Ele lista
emojis do aplicativo e do servidor, aceita textos de até 4.000 caracteres e
bloqueia menções automáticas. Textos longos são divididos em mensagens de até
2.000 caracteres antes do envio. Informe o servidor e o ID do canal na própria aba.
O Auditor de Emojis compara o app com todos os servidores registrados, permite
selecionar os emojis ausentes e importar até 50 por operação. A importação só é
executada depois da confirmação na própria Central.

Hostis aceitam até 12 tags personalizadas, editáveis na ficha da Central ou com
`/inimigo tags`. Bloodfiend e Bloodbag são tags, não status de combate.
`Devoção Reprimida` é um recurso privado da ficha definida por
`PRIVATE_SKILL_OWNER_ID` e é ocultado das fichas, Clashes e resultados públicos.

Quando `CLASH_GUILD_ID` e `CLASH_CHANNEL_ID` estão definidos, pedidos PvP,
previsões, animações, dano e follow-ups são enviados para a arena indicada. O
canal onde o comando foi usado recebe somente uma confirmação privada.

Para configurar arenas diferentes em vários servidores, use `CLASH_CHANNELS`
no formato `servidor:canal`, separando os pares por vírgula. Essa lista tem
prioridade sobre a configuração antiga de apenas um servidor.

## Uso básico

### Jogador

- `/personagem criar`: cria ou renomeia a ficha.
- `/personagem status`: exibe uma ficha.
- `/skill oficina`: abre a interface única de skills.
- `/painel`: abre a interface principal.

O combate (Clash e ataque sem oposição) acontece na **Activity**; ver a próxima
seção.

### Oficina de skills

A oficina concentra:

- criação visual;
- listagem;
- edição;
- exclusão;
- atualização da lista;
- criação da skill de teste.

O criador apresenta uma prévia e separa a configuração principal do editor de
efeitos. O jogador marca visualmente quais posições de moeda são inquebráveis;
ao editar uma skill existente, a mesma Oficina é reutilizada.

### Onde o combate acontece

O combate é feito **na Activity**. Em 2026-10-01 os comandos de combate do bot
foram desligados: `/clash` saiu da árvore de comandos e os botões **Ataque
livre**, **Follow-up** e **Puxar Clash** do painel de batalha passaram a avisar
para abrir a Activity. O código antigo continua no arquivo, sem quem o chame —
é uma entrada desligada, não código apagado.

O campo de alvo da Activity mistura:

- `👤` jogadores que possuem ficha;
- `👹` inimigos cadastrados pelo mestre.

A Activity envia um pedido persistente ao processo do bot. O bot rola as moedas,
resolve o Clash e publica o resultado no canal.

## Regras do motor

### Moedas e poder

- Cada skill possui Base Power, Coin Power e entre 1 e 10 moedas.
- Cada posição pode ser configurada individualmente como normal ou inquebrável.
- Em cada rodada do Clash, todas as moedas restantes são roladas.
- Poder: `Base Power + (Heads × Coin Power) + modificadores`.
- Quem perde a rodada perde uma moeda comum.
- Empates repetem a rodada sem remover moedas.
- Quem fica sem moedas perde o Clash.
- Coin Power negativo reduz o poder quando uma moeda cai em Heads.

Moedas inquebráveis não desaparecem ao perder uma rodada: ficam rachadas, deixam de participar das rodadas seguintes e podem executar um ataque separado conforme as regras atuais do protótipo.

### Sanidade

- SP varia de −45 a +45.
- Chance de Heads: `50% + SP`, limitada entre 5% e 95%.
- Vencedor de Clash recebe +5 SP.
- Perdedor recebe −5 SP.
- Inimigos com a sanidade inativa usam 50% de Heads e não alteram SP — eles
  também não têm SP para gastar.

### Tipos de skill

- **Normal:** Clash ofensivo com Offense Level.
- **Defesa:** sua moeda gera um escudo igual ao Final Power; o escudo é subtraído do dano recebido.
- **Evasiva:** testa cada moeda do ataque até falhar.
- **Counter:** rola sua ativação e calcula o contra-ataque sem Clash.
- **Defesa Clashable:** reage contra ataque, disputa usando Defense Level e seu Final Power defensivo.
- **Counter Clashable:** Clash ofensivo seguido de dano.
- **Assist Defense:** interceptação defensiva usando Defense Level.

Defesas podem ser escolhidas nos fluxos PvP, contra inimigos e nas ações do
campo. Para cada 3 pontos de Defense Level acima do Offense Level adversário, a
Guard recebe +1 Final Power. Se uma Defesa Clashable vencer, o resultado inclui
o ajuste de Stagger correspondente; se perder, seu Final Power funciona como
escudo e reduz o dano do ataque vencedor.

### Dano final

Depois do Clash, somente as moedas restantes da skill vencedora são roladas. Heads acrescentam Coin Power ao poder acumulado; os valores intermediários não são somados entre si.

O **dano final é um valor só** — não é um golpe por moeda. Já os **efeitos e
status disparam por moeda**: Bleed, Rupture e Sinking contam cada moeda da
resolução. É por isso que o Bleed **não é somado ao número do dano final**: ele
é dano do próprio portador, acontece à parte e aparece na lista de efeitos
(campo `RESOLUÇÃO DO DANO`). Somá-lo ao dano do golpe mudaria o balanceamento —
não é um esquecimento.

```text
Dano pós-nível = max(0, Poder após as Moedas + int((Offense Level - Defense Level) / 3))
Dano Final = max(0, Dano pós-nível × (100% + Modificador de Dano %))
```

A diferença de nível é aplicada uma vez e truncada em direção a zero. Bônus e
reduções percentuais configurados na skill são somados e aplicados em seguida;
reduções param em −100%. Condições por status, escalonamento e consumo de Charge
também podem controlar esse modificador. Escudos são descontados por último. O
resultado é persistido no estado do alvo quando existe coluna de HP — hoje só
`enemy_group_members` tem —, e a Activity mostra o valor sincronizado. Stagger
não é escrito em lugar nenhum. O mestre continua podendo fazer ajustes de mesa
pela ficha.

Condições podem consumir o próprio status consultado. **Efeito Trashholder** é um
contador genérico que pode representar Falsa Fome, cargas consumidas ou outro
recurso da mesa. Exemplo: `+0,2%` de dano por ativação, uma ativação para cada
`1 Quantidade`, consumindo o valor usado, com máximo de `200` ativações (`+40%`).
No resultado público, o bot oculta essa multiplicação e exibe somente o
percentual final aplicado, como `+40%`.

## Efeitos estruturados

A Oficina possui criação guiada no Discord e na Central. Dano percentual usa
campos separados para percentual por ativação, mínimo, intervalo, máximo e
consumo. A Central também oferece modelos rápidos, prévia do teto, duplicação,
reordenação e validação antes de salvar. Cada skill aceita até 20 efeitos.

O editor visual grava efeitos internamente neste formato:

```text
gatilho:efeito:valor:moeda_opcional
```

Exemplos:

```text
on_hit:paralysis:1:2
clash_win:sp:10
heads_hit:coin_power:1:3
```

Gatilhos disponíveis (10 — `EFFECT_TRIGGERS` em `src/domain/models/combat.py`):

- `on_use` — ao usar a skill
- `on_hit` — ao acertar
- `heads_hit` — ao acertar em Heads
- `clash_win` — ao vencer o Clash
- `clash_lose` — ao perder o Clash
- `before_attack` — antes do ataque
- `after_attack` — depois do ataque
- `on_kill` — ao derrotar o alvo
- `on_crit` — ao causar crítico
- `on_evade` — ao esquivar (só em skill Evasiva)

Efeitos disponíveis (26 — `EFFECT_TYPES`, mesmo arquivo):

- modificadores: `paralysis`, `sp`, `base_power`, `coin_power`, `clash_power`,
  `offense_level`, `defense_level`, `final_power`, `damage_percent`;
- status: `burn`, `bleed`, `tremor`, `tremor_burst`,
  `amplitude_conversion_scorch`, `rupture`, `sinking`, `poise`, `charge`,
  `haste`, `special_condition`, `self_bleed`, `glimpse_of_precognition`;
- estruturais: `make_unbreakable`, `consume_special_condition`,
  `consume_devotion_repressed`, `reuse_coin`.

Paralisia afeta o alvo; os modificadores temporários afetam o usuário, salvo
quando o efeito declara outro dono (`effect_owner`: `auto`, `target` ou `user`).
`on_hit` ativa por golpe e `heads_hit` exige Heads válido.

## Status principais

Fichas e inimigos podem guardar **Potência** e **Quantidade** separadas para:

- **Burn:** no fim da rodada causa dano igual à Potência e perde 1 Quantidade.
- **Bleed:** ao usar moedas ofensivas, causa dano igual à Potência por moeda
  gasta e perde 1 Quantidade.
- **Tremor:** Tremor Burst aplica o ajuste de Stagger a partir da Potência atual
  e gasta 1 Quantidade. Amplitude Conversion (`amplitude_conversion_scorch`)
  converte a mesma pilha em **Tremor - Scorch** preservando Potência e Count;
  o Burst do Scorch causa dano = (Tremor + Burn) ÷ 2 e gasta 1 Burn Count.
- **Rupture:** ao receber dano, causa dano adicional igual à Potência e perde 1 Quantidade.
- **Sinking:** ao receber dano, reduz SP pela Potência; em −45 SP vira dano. Alvo
  **sem Sanidade** não tem SP para perder, então o Sinking já vira dano direto.
- **Poise:** a **Potência é a chance de crítico por moeda** (Potência 5 = 5%).
  Um d20 por moeda; acende quando `d20 ≥ 21 − Potência÷5` (o d20 tem 20 faces,
  então a chance anda de 5% em 5%). Cada crítico dá `Potência × 2%` no dano só
  daquela moeda e consome 1 Quantidade. A rolagem aparece no embed.
- **Charge:** recurso para skills, Quantidade limitada a 20.
- **Haste:** registro visual e requisito de skill; a Quantidade cai 1 por rodada,
  sem o teto de 20 do Charge.
- **Efeito Trashholder (`special_condition`):** contador livre da ficha, com nome
  e ícone próprios; não tem regra automática além do que a skill configurar.

Existem ainda `devotion_repressed`, `bloodfiend` e `bloodbag`. Os três existem
como status no banco, mas ficam **ocultos do resumo público**
(`PUBLIC_STATUS_TYPES`). Bloodfiend e Bloodbag também existem como **tags** de
ficha, que é como as condições `bloodfiend_or_bloodbag` as consultam.

Burn, Tremor, Sinking, Haste, Poise e Charge perdem 1 Quantidade no encerramento
da rodada conforme as regras atuais. O resumo é enviado para a arena. O bot só
grava HP de `enemy_group_members`; nos demais alvos e no Stagger, esses valores
permanecem informativos ao mestre.

O jogador acessa o editor em **Minha ficha → Adicionar efeitos → Status
principais**. O mestre também pode usar `/personagem status_principal` e
`/inimigo status`.

## Sessões de batalha

Cada canal pode ter uma sessão ativa com fases persistentes dirigidas pelo mestre:

1. **Preparação:** participantes entram e o mestre monta o campo.
2. **Declaração:** jogadores puxam ações hostis; cada ação hostil já possui um alvo participante.
3. **Resolução:** novas declarações ficam bloqueadas e o mestre avança o turno quando quiser.

Ao terminar a Declaração, toda ação hostil que não foi puxada executa um ataque
sem oposição contra o alvo escolhido. Ataques livres hostis também podem ser
agendados para o fim do turno, em modo sem oposição ou follow-up. O painel
registra essas ações separadamente e o bot publica a resolução oficial.

Comandos do mestre:

- `/batalha iniciar`
- `/batalha colocar_skill`
- `/batalha avancar_fase`
- `/batalha reabrir_fase`
- `/batalha avancar_turno`
- `/batalha encerrar`

O Encounter visual, os participantes, a prontidão, os hostis e as escolhas de
Clash ficam somente na Activity. Ao confirmar uma disputa, a Activity envia um
pedido persistente ao processo do bot. O bot rola as moedas, resolve o Clash,
atualiza SP e modificadores e publica o resultado no canal. Reservas são
atômicas: dois jogadores não conseguem puxar a mesma ação.

## Inimigos e permissões

O mestre pode criar vários inimigos com skills e efeitos independentes. Operações administrativas exigem a permissão **Gerenciar servidor**.

Jogadores comuns podem editar somente suas próprias fichas e skills. O painel do mestre mantém criação, edição, efeitos e exclusão de inimigos em uma interface separada.

## Personalização

Emojis e GIFs são opcionais. Use URLs diretas para arquivos e emojis no formato `<:nome:ID>` ou `<a:nome:ID>`. Para animações por tipo, copie `clash_gifs.example.txt` para `clash_gifs.txt`; o arquivo local resultante é ignorado pelo Git.

Para uma distribuição pública ou comercial, utilize somente recursos originais, licenciados ou fornecidos pelo administrador do servidor.

## Dados e auditoria

- Dados persistem em SQLite.
- Servidores possuem dados isolados pelo ID do Discord.
- O terminal mostra comandos, botões, seleções, alterações, Clashes, dano e erros com usuário, servidor, canal e ID da interação.
- Formulários do RPG são registrados com os nomes dos campos e valores enviados para facilitar a reprodução de erros.
- Erros recebem um código curto visível ao usuário e traceback completo para diagnóstico.
- `clash_audit.log` mantém uma cópia sem cores e gira aos 5 MB, preservando cinco arquivos anteriores.
- Cada ação aparece como um bloco visual; Clashes e dano incluem faces das moedas e as fórmulas completas de Base, Coin Power, Heads válidos, níveis, Clash Power, escudo e resultado final.
- Quando `AUDIT_CHANNEL_ID` está configurado, todos os registros também são enviados para esse canal em lotes, sem menções, mantendo terminal e arquivo local ativos.
- Interações recebem nomes legíveis no relatório: comando completo, texto do botão, finalidade da lista de seleção ou título do formulário; o ID técnico continua disponível nos detalhes.

## Central de Controle local

Execute `start_control_center.bat` ou `python control_center.py`. A Central abre em `http://127.0.0.1:8765` e permite ligar, reiniciar e desligar o bot; acompanhar logs; consultar fichas e hostis; criar, editar e excluir skills de jogadores e inimigos; ativar ou desativar comandos; e editar configurações não secretas. O token permanece somente no `.env` e não é exibido na interface.

O antigo frontend isolado da Rosemary foi incorporado ao estilo e aos recursos
da Discord Activity. O adaptador `rosemary_panel.py` continua apenas enquanto a
Central utiliza os dados especiais já existentes; ele não inicia outra tela.

O painel Electron independente da Rosemary **saiu deste repositório**: hoje ele
fica em `Documents\Rosemary game\rosemary-panel`, junto com os outros projetos
dela. Nada aqui referencia essa pasta. Se você quiser que o painel suba a
Central sozinho, aponte `CLASH_BOT_DIR` para a raiz deste projeto — o atalho
`Abrir Painel Rosemary.cmd` já faz isso automaticamente.

- `.env`, bancos e logs são ignorados pelo Git.

## Estrutura atual

```text
bot.py                          Discord: comandos, embeds e combate oficial
activity_server.py               API/OAuth e ponte HTTP da Activity
control_center.py/.html          Central local: administração e Composer
database.py                      SQLite, migrações, Encounter e auditoria
battle_flow.py                   fases, prontidão e avanço da batalha
src/domain/                      modelos e fórmulas puras de combate
src/application/services/        Núcleo Geral e serviços compartilhados
src/infrastructure/              contratos de repositório e evolução futura
src/bot/                         cogs e views (migração em andamento)
ui/discord-activity/             React: ficha, Encounter e Mestre
ui/discord-activity/public/      logo, placeholders e recursos públicos
assets/                          imagens usadas pelo launcher e interfaces
tests/ e test_*.py               testes unitários, integração e compatibilidade
start_*.bat / stop_all.bat       inicialização e parada local
BOT_FUNCTIONS.md                 catálogo de funções, fluxos e comandos
LICENSE                          GNU GPL v3.0 — texto completo e oficial
```

A lista detalhada de responsabilidades e comandos está em
[BOT_FUNCTIONS.md](BOT_FUNCTIONS.md); a comunicação entre essas partes está em
[ARCHITECTURE.md](ARCHITECTURE.md).

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

A suíte atual tem **119 testes automatizados**, descobertos com
`python -m unittest discover`. Os testes de contrato acompanham a extração da
arquitetura descrita no roadmap.

## Documentação

- [Arquitetura atual e planejada](ARCHITECTURE.md)
- [Funções do bot, comandos e responsabilidades](BOT_FUNCTIONS.md)
- [Roadmap](ROADMAP.md)
- [Como contribuir](CONTRIBUTING.md)
- [Histórico](CHANGELOG.md)
- [Decisões e tempos da organização de 2026-09-29](MUDANCAS-2026-09-29.md)
- [Publicação no GitHub e branches](GITHUB_SETUP.md)

## Licença e propriedade intelectual

Este projeto está licenciado sob a **GNU General Public License v3.0 (GPL-3.0)**.
O texto completo e oficial está em [`LICENSE`](LICENSE).

### O que isso significa, em português

**Qualquer pessoa pode:**

- usar, copiar e distribuir o bot;
- ler, estudar e modificar o código;
- até usar comercialmente, sem precisar pedir permissão.

**Desde que:**

- mantenha o aviso de copyright e o arquivo `LICENSE` junto com o código;
- toda versão modificada que for distribuída seja publicada **também sob a
  GPL-3.0**, com o código-fonte disponível. Esse é o efeito *copyleft*: o código
  continua livre mesmo depois de alterado.

**O que a licença não cobre:**

- imagens, GIFs, sprites, emojis, músicas ou vozes de terceiros — em especial
  qualquer material ligado a Project Moon / Limbus Company. Eles continuam
  pertencendo aos seus detentores originais e **não** podem ser redistribuídos
  por causa desta licença. A GPL só vale para o código escrito neste repositório.
- a identidade visual e o nome "ClashBot".

Por isso, antes de qualquer distribuição pública, substitua ou remova recursos
que você não tenha licença para repassar — já é o que o aviso no topo deste
arquivo pede.

### Sobre cabeçalhos por arquivo

A GPL permite licenciar o projeto pelo par `LICENSE` + esta declaração, sem
precisar colar o texto nas 42 fontes Python. Optamos por não inserir cabeçalhos
SPDX em cada arquivo para manter o `git diff` limpo durante a migração da
arquitetura; se o projeto for publicar uma release, aí sim vale adicionar
`# SPDX-License-Identifier: GPL-3.0-only` no topo dos módulos.

Não inclua no repositório recursos oficiais de jogos, músicas, vozes, imagens, GIFs ou emojis sem autorização adequada.

## Discord Activity local pública

A Activity pública fica em `ui/discord-activity`. Ela é separada da Central local:
cada jogador recebe e edita somente a própria ficha, validada pelo OAuth2 do
Discord. Administradores autorizados recebem também a Central do Mestre, com
fichas, hostis, status, modificadores, Skills e controle das fases de batalha.

O botão de espadas abre o Clash na Activity. Ele usa as fichas e Skills reais do
banco, resolve moedas positivas e negativas, níveis, Paralisia, Sanidade e dano,
e sincroniza o SP resultante com o bot.

O botão de antena abre o **Encounter** compartilhado com o bot. Jogadores podem
entrar, confirmar prontidão e reservar uma ação hostil durante a Declaração. O
mestre adiciona as Skills dos hostis e controla as fases. A reserva é atômica:
uma ação não pode ser puxada por dois jogadores, e falhas liberam a ação
automaticamente. As fases usam as tabelas `battle_sessions`,
`battle_participants`, `battle_field_actions` e `battle_player_actions`.

### Configuração no Discord

No [Discord Developer Portal](https://discord.com/developers/applications):

1. Abra a mesma aplicação usada pelo bot.
2. Em **OAuth2**, adicione `https://127.0.0.1` em **Redirects**.
3. Copie o **Application ID** e gere e copie o **Client Secret**.
4. Em **Activities > Settings**, habilite **Enable Activities**.
5. Marque as plataformas suportadas desejadas.

Execute `configure_discord_activity.bat` e informe os dois valores. O Application
ID normalmente já aparecerá sugerido a partir do bot. O configurador grava, sem
exibir o segredo, o equivalente a:

```env
DISCORD_CLIENT_ID=seu_application_id
DISCORD_CLIENT_SECRET=seu_client_secret
ACTIVITY_PORT=8780
```

O mesmo configurador também cria `ui/discord-activity/.env` com:

```env
VITE_DISCORD_CLIENT_ID=seu_application_id
```

### Execução e endereço público

Para o uso normal, abra `ClashBot.exe` e escolha **Ligar Tudo**. O iniciador abre
a Activity, a Central com o bot e o endereço público. Os arquivos `.bat` continuam
disponíveis apenas para iniciar cada parte separadamente durante manutenção.

O launcher não inicia mais nenhum túnel público. Ele liga somente a Activity e
o bot local, evitando que o Tailscale interfira na inicialização. Uma publicação
externa deverá ser configurada separadamente quando a hospedagem for definida.

Durante o teste local do Discord, use o modo de teste apontando para a porta
`8780`. A porta `8765` continua exclusiva da Central administrativa.

### O que usar em cada lugar

- **Activity:** ficha completa, atributos, status, Skills, passivas, registros,
  Encounter, escolhas de Clash, resultado visual e visão do mestre.
- **Bot:** criação inicial, moedas, rolagem e resolução oficial do Clash,
  mensagens no canal, permissões, auditoria e hospedagem permanente das imagens.
- **Central local:** ligar/desligar os serviços, configuração, diagnóstico e
  manutenção administrativa fora da sessão.
- **Núcleo compartilhado:** progressão, validação, combate, fases e persistência.

O comando `/painel` mostra essa divisão dentro do Discord. A regra para o
desenvolvimento é simples: **Activity escolhe; bot rola, resolve, salva e
comunica; núcleo fornece as fórmulas**. Uma fórmula ou transição de batalha não
deve ser recriada em React nem em um embed.

### Otimizações de estabilidade

- O banco usa WAL, espera controlada e leituras concorrentes para reduzir erros
  quando bot, Activity e Central trabalham ao mesmo tempo.
- A Activity reutiliza por poucos segundos a validação de identidade do Discord,
  evitando várias chamadas iguais durante a abertura das abas.
- Telas grandes são carregadas sob demanda; bundles antigos com hash são
  preservados para instâncias do Discord que ainda estejam abertas.
- O bot reutiliza uma sessão de rede no trabalhador de imagens, em vez de abrir
  uma conexão nova para cada arquivo.
