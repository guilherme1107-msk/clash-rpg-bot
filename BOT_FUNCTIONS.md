# Funções do ClashBot

Este documento é o catálogo operacional da versão atual. Os comandos de mestre
exigem a permissão **Gerenciar servidor** no Discord. A Activity e a Central
oferecem as mesmas operações em telas visuais quando apropriado.

## O que cada parte faz

| Parte | Responsabilidade |
| --- | --- |
| Bot do Discord | Autoridade da sessão: rola moedas, resolve Clash/dano/efeitos, atualiza recursos e envia embeds. |
| Activity | Ficha, escolhas de Clash, Encounter e visão do mestre. Não calcula o resultado oficial. |
| Central de Controle | Administração local, hostis/grupos, Composer, logs e manutenção. |
| Núcleo Geral | Serviços e eventos comuns que registram a intenção, validam e persistem o estado no SQLite. |
| Sentinela | Consulta de diagnóstico e acompanhamento dos núcleos no Discord. |

## Comandos do Discord

### Qualquer jogador

| Comando | Função |
| --- | --- |
| `/painel` | Abre a porta de entrada para ficha, Activity, combate e regras. |
| `/personagem criar` | Cria ou renomeia a própria ficha; aceita imagem anexada. |
| `/personagem remover` | Remove a própria ficha, skills e status após confirmação. |
| `/personagem imagem` | Troca a imagem da própria ficha. |
| `/personagem status` | Mostra a própria ficha ou a ficha de outro jogador. |
| `/skill oficina` | Abre a oficina visual de skills. |
| `/clash` | Inicia Clash contra jogador ou inimigo; aceita skills ofensivas e defensivas válidas. |
| `/sentinela perguntar` | Pergunta sobre Clash, sanidade, efeitos, embeds, banco ou comunicação entre núcleos. |
| `/sentinela status` | Exibe a saúde resumida dos serviços e do banco. |

### Mestre: personagens

| Comando | Função |
| --- | --- |
| `/personagem niveis` | Define Offense Level e Defense Level. |
| `/personagem sanidade` | Ajusta SP em valor positivo ou negativo. |
| `/personagem efeitos` | Aplica Paralisia e modificadores temporários de poder. |
| `/personagem status_principal` | Define Potência e Quantidade de Burn, Bleed, Tremor, Rupture, Sinking, Poise ou Charge. |

### Mestre: inimigos

| Comando | Função |
| --- | --- |
| `/inimigo criar` | Cria ou atualiza uma ficha-base hostil. |
| `/inimigo skill` | Cria ou atualiza uma skill do hostil. |
| `/inimigo editar_skill` | Edita uma skill hostil existente. |
| `/inimigo remover_skill` | Exclui uma skill hostil. |
| `/inimigo efeitos` | Aplica modificadores temporários ao hostil. |
| `/inimigo status` | Define os status principais do hostil. |
| `/inimigo tags` | Define tags permanentes usadas por condições de skills. |
| `/inimigo listar` | Lista hostis e seus ataques. |
| `/inimigo remover` | Remove a ficha-base e suas skills. |

### Mestre: Encounter

| Comando | Função |
| --- | --- |
| `/batalha iniciar` | Cria a sessão persistente no canal atual. |
| `/batalha painel` | Exibe as ações hostis presentes no campo. |
| `/batalha colocar_skill` | Coloca uma skill de inimigo no campo, com alvo participante. |
| `/batalha avancar_fase` | Avança Preparação → Declaração → Resolução. |
| `/batalha reabrir_fase` | Volta à fase anterior quando o mestre precisa corrigir uma decisão. |
| `/batalha avancar_turno` | Limpa o campo, processa fim de turno e inicia o próximo turno. |
| `/batalha encerrar` | Fecha a sessão do canal. |

## Fluxos de combate

### Clash e dano

1. A Activity ou o Discord coleta alvo e skill.
2. O pedido passa pelo Núcleo Geral e é gravado no SQLite.
3. O bot é a única parte que rola moedas, aplica sanidade, escudos, dano e efeitos.
4. O resultado e os embeds são publicados no canal de arena configurado.
5. A Activity consulta o estado já resolvido para atualizar HP, SP, Light, Stagger e efeitos.

### Ataques no Encounter

- Na **Declaração**, o jogador pode puxar uma ação hostil para Clash.
- Toda ação hostil no campo recebe um alvo participante.
- Uma ação hostil que permanecer aberta quando a Declaração termina é despachada como **ataque sem oposição** contra o alvo selecionado.
- O mestre pode agendar ataque livre de hostil para o fim do turno, escolhendo hostil, skill, alvo e modo (sem oposição ou follow-up).
- Skills defensivas aparecem como opção de resposta para Clash, mas não recebem ganhos/perdas de sanidade disparados por efeitos de terceiros.

### Recursos e efeitos

- HP cresce automaticamente com o nível; a ficha permite também definir Vida Máxima.
- Dano recebido fica na Visão Geral; o alvo informa o número e o núcleo atualiza HP e Stagger.
- Há duas barras de Stagger, calculadas a 20% e 50% da Vida Máxima.
- Light tem controles de aumentar e reduzir na ficha.
- Efeitos utilizam Potência e Quantidade, são validados antes de salvar e efeitos iguais enviados juntos são consolidados em vez de duplicados.
- Aplicações de efeitos geram mensagem de diagnóstico/combate para que a trilha possa ser auditada.

## Central de Controle local

Execute `start_control_center.bat` ou `python control_center.py`; a Central fica em `http://127.0.0.1:8765`.

Ela oferece:

- iniciar, reiniciar e parar serviços; acompanhar logs e configurações não secretas;
- administrar fichas, imagens, skills, passivas, recursos e status;
- criar hostis e **grupos de inimigos iguais**, com uma ficha-base herdando imagem e skills; cada integrante mantém HP, SP, Light e status próprios;
- colocar cada integrante de um grupo no Encounter como um hostil individual; uma ação e um Clash apontam para o integrante, nunca para o grupo inteiro;
- montar e dirigir Encounters; agendar e revisar ações hostis;
  com alvo fixo, quantidade e ataques livres (sem oposição / follow-up);
- criar e gerenciar **grupos de inimigos iguais** (molde + integrantes com HP/SP próprios);
- usar o **Clash Manual** para enfileirar um Clash como a Activity faz
  (a Central não rola moedas; o bot resolve e a Central exibe o job);
- abrir a **Sentinela** local (paridade com `/sentinela status`):
  bot, fila de Clash, outbox, Encounters ativos e últimos TRACE do núcleo;
- configurar o **canal de auditoria por servidor** (fallback do Clash manual);
- usar o **App Composer** para montar, pré-visualizar e enviar mensagens;
- consultar mensagens já enviadas pelo Composer, incluindo servidor, canal, data e conteúdo, e então editar ou apagar as mensagens rastreadas;
- auditar/importar emojis e consultar o diagnóstico dos núcleos.

> O histórico do Composer só inclui mensagens enviadas depois que o rastreamento foi adicionado. Mensagens antigas não podem ser reconstruídas automaticamente.

## Arquivos principais

| Local | Conteúdo |
| --- | --- |
| `bot.py` | Comandos, embeds, workers e resolução autoritativa. |
| `activity_server.py` | API/OAuth da Activity e ponte para o núcleo. |
| `control_center.py` e `control_center.html` | Backend e tela da Central. |
| `database.py` | SQLite, tabelas, migrações e registros de eventos. |
| `battle_flow.py` | Fases e regras de avanço do Encounter. |
| `src/application/services/core_gateway.py` | Comunicação e auditoria pelo Núcleo Geral. |
| `ui/discord-activity/src/` | Interface React da ficha, Encounter e mestre. |
| `assets/` e `ui/discord-activity/public/` | Logo, imagens e outros recursos visuais. |

Consulte também [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md) e [CHANGELOG.md](CHANGELOG.md).
