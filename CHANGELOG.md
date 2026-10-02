# Histórico de versões

Todas as mudanças relevantes do projeto serão registradas neste arquivo.

## [Não publicado]

### Amplitude Conversion → Tremor - Scorch — 2026-10-01

- Novo efeito de skill `amplitude_conversion_scorch` (gatilho + valor flat,
  como o Tremor Burst): converte o Tremor do alvo em **Tremor - Scorch**
  preservando Potência e Count, fiel à regra de Amplitude Conversion do Limbus.
  Sem Tremor ativo no alvo o efeito informa "sem efeito".
- A variante mora na coluna `tremor_type` da própria linha de `tremor`
  (migração automática nas duas tabelas de status), e não em status separado —
  a pilha continua sendo a mesma. Editores da Activity e da Central de
  Controle preservam o tipo salvo quando o payload não envia outro válido.
- Burst em Tremor - Scorch (regra da wiki): dano = (Potência de Tremor + Burn)
  ÷ 2, arredondado para baixo, depois −1 Burn Count; sem Burn ativo o dano é
  Tremor ÷ 2. Sem Sin Affinity no bot, é dano normal aplicado pelo mestre.
- Exibição: o painel de status, a ficha e o log da rodada passam a rotular a
  pilha como **Tremor - Scorch** (ícone do Tremor Burst), inclusive no
  decaimento do fim da rodada.
- Testes novos em `testes/test_tremor.py` (domínio + sintaxe) e
  `testes/test_database.py` (round-trip, upsert, fim de rodada e grupo hostil).

### Organização do repositório e licença — 2026-09-29

- Projeto movido de `Documents\Codex\2026-08-23\...\clash-rpg-bot` para
  `Documents\clash-rpg-bot`. Como é o mesmo disco, o move virou um rename de
  0,05 s; `.venv`, `discord.py` e os 117 testes foram validados logo em seguida.
- A UI Electron da Rosemary saiu de `ui/rosemary-panel` e agora vive **fora do
  repositório**, em `Documents\Rosemary game\rosemary-panel`. Os backups
  `rosemary-panel.rar` e `rosemary-panel.zip` (469 MB) foram para
  `Documents\Rosemary game\_backup-archives\`. Nenhum código do bot referenciava
  essa pasta — `rosemary_panel.py` e `rosemary_content.json` seguem na raiz.
- `electron/main.cjs` do painel agora resolve o caminho do bot por
  `CLASH_BOT_DIR`, com fallback para o caminho relativo legado; sem bot
  encontrado ele simplesmente não tenta subir a Central.
- Adicionado `LICENSE` com a **GNU GPL v3.0**, mais uma seção no README
  explicando o que a licença cobre e, principalmente, o que ela **não** cobre
  (GIFs, emojis e demais materiais de terceiros).
- `.gitignore` completado e reorganizado por seções. Antes, `clash_rpg.sqlite3-wal`
  (4,1 MB), `clash_rpg.sqlite3-shm` e `ClashBot.exe` (1,9 MB) **não** eram
  cobertos por nenhuma regra. Agora valem curingas genéricos para
  `node_modules/`, `dist/`, `*.exe`, `*.sqlite3-*`, `*.rar`/`*.zip` e `backups/`.
  Validação por matcher próprio: **0 vazamentos** em 156 caminhos versionados.
- O registro completo das decisões, com tempos de execução, está em
  [MUDANCAS-2026-09-29.md](MUDANCAS-2026-09-29.md).

### Atualização operacional — 2026-08-31

- Integrantes de grupos hostis agora entram no Encounter individualmente, usando Skills da ficha-base e mantendo SP, HP, modificadores e status próprios. Uma derrota no Clash reduz somente a Sanidade do integrante envolvido.
- O painel de ação hostil foi ajustado para colunas flexíveis, preparado para novos controles sem sobrepor a ficha.
- Consolidada a divisão: Activity escolhe e exibe; bot resolve rolagens,
  dano, efeitos e embeds; Núcleo Geral valida, registra e persiste.
- Adicionados eventos/auditoria do Núcleo Geral e comandos da Sentinela para
  consulta de diagnóstico e perguntas operacionais.
- A Activity passou a exibir tela de carregamento, logo do ClashBot, layout de
  ficha revisado, controles de dano recebido, Vida Máxima, Light e Stagger.
- Vida cresce automaticamente com nível; os dois limites de Stagger são
  calculados a 20% e 50% da Vida Máxima.
- Skills são organizadas como S1, S2, S3, variações S3-x e defensivas; o
  seletor de Clash inclui skills defensivas compatíveis.
- Efeitos foram reforçados: seletores começam vazios, validação tolera dados
  ausentes, efeitos iguais são consolidados e aplicações são registradas.
- Sanidade, efeitos e recursos de combate passaram a circular pelo fluxo
  autoritativo do bot antes de refletirem no Encounter.
- Hostis ganharam ficha visual, imagem por colar/anexar, grupos de inimigos
  iguais que herdam a ficha-base e recursos individuais por integrante.
- Ações hostis no campo exigem alvo participante; ações abertas ao final da
  Declaração viram ataque sem oposição contra esse alvo.
- Adicionada fila de ataques livres hostis para fim de turno, em modo sem
  oposição ou follow-up.
- Corrigidos bloqueios de avanço causados por status inválidos e removido o
  controle redundante que conflitaria com o fluxo de fases.
- App Composer agora rastreia mensagem, servidor e canal; mensagens rastreadas
  podem ser listadas, editadas e apagadas na Central.

### Alterado

- Os botões antigos de ficha e Oficina de Skills do `/painel` agora direcionam para a Activity e não carregam mais os editores em embeds.

- Removidos os frontends antigos Rosemary, Character Panel e Configurable Panel, já substituídos pela Discord Activity.
- Removidos pacotes de handoff, staging temporário e o esqueleto `v2` duplicado após sua arquitetura ser incorporada em `src/`.

- Iniciada a separação funcional entre Activity, bot, núcleo de aplicação e persistência.
- Cálculos de nível, atributos, HP, Stagger, Light, Offense e Defense foram movidos para um serviço compartilhado e testável.
- SQLite passou a usar WAL, espera de contenção e sincronização adequada para o uso simultâneo pela Activity, bot e Central.
- A Activity ganhou cache curto e limitado para validações repetidas do Discord durante a abertura das telas.
- O trabalhador de mídia do bot passou a reutilizar a conexão HTTP, reduzindo custo e criação de recursos.
- O `/painel` agora explica claramente o que pertence à Activity, ao bot e ao núcleo.

- O Discord App Composer foi integrado à Central de Controle, com formatação, prévia, emojis do app/servidor e envio pelo próprio ClashBot.
- O Composer ganhou auditoria de emojis em todos os servidores registrados, seleção dos ausentes e importação confirmada para os emojis próprios do aplicativo.
- Hostis agora possuem tags permanentes e personalizadas; marcadores antigos Bloodfiend/Bloodbag são migrados automaticamente para tags.
- Devoção Reprimida foi restrita à ficha configurada por `PRIVATE_SKILL_OWNER_ID` e ocultada de interfaces e resultados públicos.

- Reformulada a criação de skills: o Discord ganhou formulário dedicado para dano percentual, remoção por número e duplicação; a Central ganhou modelos rápidos, reordenação, duplicação, validação e prévia do teto percentual.
- Skills agora aceitam no máximo 20 efeitos, com validação igual no domínio, no bot e na Central.
- Adicionado modificador percentual de dano positivo ou negativo às skills, com condições por status, escalonamento e consumo opcional de Charge; o cálculo aparece no Damage Resolution.
- Adicionada a Condição Especial genérica e a opção de consumir o status usado por uma condição; valores percentuais aceitam decimais como `0,2%` e limite configurável de ativações.
- A resolução pública de dano mostra somente a porcentagem final; a multiplicação por stacks e o limite permanecem internos.
- Criada a estrutura inicial em `src/` para a versão séria.
- Adicionada API pública de combate em `src.domain.combat`.
- Bot, banco e testes passaram a importar o domínio pelo novo caminho.
- Adicionado teste de contrato da API pública.
- Extraídos Skill, SkillEffect, Roll, resultados e modificadores para `src.domain.models`.
- Extraídas as resoluções de Clash, dano e defesa para `src.domain.combat.engine`.
- Transformado `clash_engine.py` em adaptador compatível com imports antigos.
- Adicionado teste de contrato para a camada de compatibilidade.
- Criados contratos iniciais de repositório, já atendidos pelo banco SQLite atual.
- Adicionada configuração individual de moedas normais e inquebráveis no protótipo.
- Simplificada a Oficina, separando dados/moedas do editor de efeitos.
- Edição de skills de jogadores passou a reutilizar a Oficina visual.
- Banco SQLite migra automaticamente e preserva o layout individual das moedas.
- Oficina ganhou mapa decorado com posição, tipo, Coin Power, efeitos vinculados e legenda.
- Moedas normais da Oficina passaram a usar o emoji ligado `ML`.
- Adicionados ataques livres e follow-ups contra inimigos do campo, sem Clash.
- Painel registra ações unilaterais e o dano informativo correspondente.
- Botão Pronto agora coordena Preparação, Declaração, Resolução e início automático do próximo turno.
- Editor de efeitos da ficha passou a usar lista, prévia e modal de valor como a Oficina.
- Adicionados Defense Level Up/Down e seu uso nas defesas e no dano recebido.
- Adicionado roteamento de pedidos e animações de Clash para um canal de arena configurável.
- Ataques livres e follow-ups do painel também são enviados para a arena configurada.
- Guard comum agora gera escudo igual ao Final Power e reduz o dano recebido.
- Clashable Guard informa Stagger manual ao vencer e reduz dano com seu Final Power ao perder.
- Skills defensivas passaram a ser aceitas em PvP, inimigos e ações do campo.
- Adicionado sistema persistente de Potência e Quantidade para sete status principais.
- Burn, Bleed, Rupture e Sinking foram ligados aos eventos de rodada, ação e dano.
- Tremor Burst, Poise e Charge expõem cálculos e limites para uso do mestre e skills futuras.
- Ficha recebeu uma oficina visual de status; mestre recebeu comandos para jogadores e inimigos.
- Status ativos agora aparecem nas fichas, no arquivo de hostis e sob cada alvo do painel de batalha.
- A passagem de turno aplica Burn apenas aos participantes e inimigos daquela batalha e publica o dano recebido na arena.
- Damage Resolution destaca separadamente dano, perda de SP e dano autoinfligido causados por status.
- A Oficina de skills agora configura Burn, Bleed, Tremor, Rupture, Sinking, Poise e Charge com Potência, Quantidade, gatilho e moeda condicional.
- Skills aplicam status persistentes ao alvo; Poise e Charge são aplicados ao próprio usuário.
- Tremor Burst foi adicionado à Oficina com gatilho e moeda condicional; ele usa a Potência atual de Tremor, preserva seus stacks e informa o ajuste manual de Stagger Threshold no resultado de dano.
- Bleed agora causa dano e consome Quantidade por moeda ofensiva do portador; não ativa no fim da rodada nem em skills defensivas.
- Poise agora realiza a checagem de crítico, aumenta o dano em `Potência × 2%` e só consome Quantidade quando o crítico ativa.
- Efeitos da Oficina podem consumir Charge e exigir status mínimo no alvo; Final Power foi adicionado como efeito configurável.
- Inimigos receberam ficha completa, Enemy Hub e o Skill Lab visual; `/inimigo listar` mostra somente nome e sanidade.
- Charge passou a habilitar melhorias sem bloquear a skill: com recurso suficiente, consome a quantidade e ativa bônus; sem recurso, apenas a melhoria fica inativa. A Oficina agora pode tornar uma moeda específica ou todas as moedas inquebráveis durante aquele uso.
- Auditoria ampliada com IDs de interação e erro, contexto de servidor/canal/usuário, opções seguras, duração, traceback, captura de erros assíncronos e rotação automática dos logs.
- Auditoria de formulários passou a registrar os campos e valores enviados, com normalização de linhas e limite de tamanho para manter o terminal legível.
- Logs foram ampliados em blocos visuais e agora detalham as contas de cada rodada do Clash e da Damage Resolution.
- Bleed passou a identificar explicitamente o portador que sofreu dano e não é confundido com o aplicador; Poise agora usa d20 secreto com margem padrão 20 e aplica crítico somente ao dano das moedas.
- Oficina ganhou uma lista visual de condições negativas do alvo; melhorias inquebráveis podem depender de Burn, Bleed, Tremor, Rupture ou Sinking, com Charge opcional.
- Charge exibe barra `atual/20`, Potência×Quantidade e saldo antes/depois de cada melhoria consumida.
- Todos os logs podem ser espelhados em um canal privado do Discord por `AUDIT_CHANNEL_ID`; mensagens são agrupadas, divididas conforme o limite do Discord e não geram menções.
- Interações passaram a exibir nomes humanos nos logs, incluindo comando completo, rótulo de botão, objetivo da seleção e título do formulário.
- Adicionada Central de Controle local com gerenciamento do processo, logs ao vivo, fichas, hostis, Skill Lab compartilhado, ativação de comandos e configuração não secreta.

## [Prototype v1] — 2026-08-10

### Adicionado

- Motor de Clash com sanidade, moedas positivas e negativas.
- Limite de dez moedas e dez rodadas exibidas.
- Moedas inquebráveis e follow-up separado.
- Skills ofensivas e defensivas.
- Offense Level, Defense Level e modificadores temporários.
- Paralisia e previsão probabilística.
- Resolução de dano sem HP, resistência ou Stagger.
- Fichas, inimigos e skills persistidos em SQLite.
- Inimigos com sanidade ativa ou inativa.
- Efeitos estruturados por gatilho e moeda.
- Oficina visual unificada de skills.
- Comando único de Clash para jogadores e inimigos.
- Pedido público de PvP com aceitação, recusa e escolha da skill defensora.
- Sessões de batalha com fases, participantes, prontidão e painel fixo.
- Auditoria local decorada e tratamento de erros.
- Testes automatizados do motor e banco.

### Limitações conhecidas

- HP, Stagger e resistência não são administrados.
- Configuração de moedas ainda não é individual por posição.
- `bot.py` concentra grande parte da aplicação.
- SQLite é adequado ao protótipo local, mas exigirá estratégia de concorrência e backup para hospedagem maior.
- GIFs e emojis dependem da configuração de cada instalação.
- A identidade visual ainda precisa ser substituída por recursos originais antes de uma distribuição comercial.

## Próxima versão

Consulte [ROADMAP.md](ROADMAP.md) e [ARCHITECTURE.md](ARCHITECTURE.md).
