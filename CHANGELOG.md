# Histórico de versões

Todas as mudanças relevantes do projeto serão registradas neste arquivo.

## [Não publicado]

### Alterado

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
