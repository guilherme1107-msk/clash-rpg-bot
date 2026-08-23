# Clash RPG Bot

> A reconstrução independente está em [`v2/`](v2/README.md). O código da raiz
> permanece como protótipo e referência de comportamento durante a transição.

Protótipo de bot para RPG no Discord baseado em disputas de moedas, sanidade, skills configuráveis e encontros controlados pelo mestre.

> Projeto comunitário, experimental e não oficial. Não possui vínculo ou aprovação da Project Moon. A versão pública deve usar identidade visual e arquivos com licença adequada.

## Estado do projeto

Esta versão representa o marco **Prototype v1**. Ela está funcional para sessões locais e será preservada como referência enquanto uma nova branch recebe a evolução estrutural descrita no [roadmap](ROADMAP.md).

O bot calcula Clash e dano, mas ainda não administra HP, Stagger ou resistência a dano.

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
- Clash jogador contra jogador por pedido, aceitação e escolha de resposta.
- Clash contra inimigos cadastrados pelo mestre.
- Previsão probabilística em cinco simulações.
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
- `/clash`: inicia um confronto contra jogador ou inimigo.
- `/painel`: abre a interface principal.

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

### Clash unificado

O campo `alvo` de `/clash` mistura:

- `👤` jogadores que possuem ficha;
- `👹` inimigos cadastrados pelo mestre.

Contra jogadores, o bot publica um pedido. Somente o alvo pode aceitar ou recusar. Ao aceitar, ele escolhe sua skill e a mensagem se transforma na previsão e animação do Clash.

Contra inimigos, o jogador escolhe sua skill e também a skill hostil.

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
- Inimigos sem sanidade usam 50% de Heads e não alteram SP.

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
Guard recebe +1 Final Power. Se uma Defesa Clashable vencer, o bot informa o
aumento manual de Stagger Threshold igual ao seu Final Clash Power. Se perder,
seu Final Power funciona como escudo e reduz o dano do ataque vencedor.

### Dano final

Depois do Clash, somente as moedas restantes da skill vencedora são roladas. Heads acrescentam Coin Power ao poder acumulado; os valores intermediários não são somados entre si.

```text
Dano pós-nível = max(0, Poder após as Moedas + int((Offense Level - Defense Level) / 3))
Dano Final = max(0, Dano pós-nível × (100% + Modificador de Dano %))
```

A diferença de nível é aplicada uma vez e truncada em direção a zero. Bônus e
reduções percentuais configurados na skill são somados e aplicados em seguida;
reduções param em −100%. Condições por status, escalonamento e consumo de Charge
também podem controlar esse modificador. Escudos são descontados por último. O
resultado é informativo: HP e Stagger continuam sob controle do mestre.

Condições podem consumir o próprio status consultado. **Condição Especial** é um
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

Gatilhos disponíveis:

- `on_use`
- `on_hit`
- `heads_hit`
- `clash_win`
- `clash_lose`
- `before_attack`
- `after_attack`

Efeitos disponíveis:

- `paralysis`
- `sp`
- `base_power`
- `coin_power`
- `clash_power`
- `offense_level`

Paralisia afeta o alvo; os outros efeitos afetam o usuário. `on_hit` ativa por golpe e `heads_hit` exige Heads válido.

## Status principais

Fichas e inimigos podem guardar **Potência** e **Quantidade** separadas para:

- Burn: causa dano igual à Potência no fim da rodada e perde 1 Quantidade.
- Bleed: causa dano informativo quando o portador age e perde 1 Quantidade.
- Tremor: Tremor Burst informa aumento manual de Stagger Threshold igual à Potência.
- Rupture: ao receber dano, causa dano adicional igual à Potência e perde 1 Quantidade.
- Sinking: ao receber dano, reduz SP pela Potência; em −45 SP vira dano.
- Poise: bônus crítico de `Potência × 2%` e margem de ameaça `Potência ÷ 10`.
- Charge: recurso para skills, limitado a 20 Quantidade.

Burn, Tremor, Sinking, Poise e Charge perdem 1 Quantidade no encerramento da
rodada conforme as regras atuais. O resumo é enviado para a arena. Como o bot
não controla HP ou Stagger, esses valores permanecem informativos ao mestre.

O jogador acessa o editor em **Minha ficha → Adicionar efeitos → Status
principais**. O mestre também pode usar `/personagem status_principal` e
`/inimigo status`.

## Sessões de batalha

Cada canal pode ter uma sessão ativa com fases persistentes e avanço cooperativo:

1. **Preparação:** participantes entram, o mestre monta o campo e todos confirmam **Pronto**.
2. **Declaração:** jogadores puxam ações hostis, usam ataques livres/follow-ups ou passam com **Pronto**.
3. **Resolução:** novas declarações ficam bloqueadas; quando todos confirmam **Pronto**, o próximo turno começa automaticamente.

Ataques livres e follow-ups escolhem uma skill de dano e um inimigo presente no
campo, mas não disputam nem reservam uma ação hostil. O painel registra esses
ataques separadamente e mostra seu dano informativo.

Comandos do mestre:

- `/batalha iniciar`
- `/batalha colocar_skill`
- `/batalha painel`
- `/batalha avancar_fase`
- `/batalha reabrir_fase`
- `/batalha avancar_turno`
- `/batalha encerrar`

O painel fixo mostra participantes, SP, prontidão por fase, hostis, Clashes,
ataques unilaterais e progresso. Reservas são atômicas: dois jogadores não
conseguem puxar a mesma ação. Os comandos de avanço do mestre permanecem como
controle manual e recuperação.

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
- `.env`, bancos e logs são ignorados pelo Git.

## Estrutura atual

```text
src/domain/             nova API pública do domínio
src/application/        espaço para casos de uso e serviços
src/infrastructure/     espaço para persistência e migrações
src/bot/                espaço para comandos e interfaces do Discord
bot.py                  integração legada em migração
clash_engine.py         implementação legada do motor
database.py             persistência SQLite legada
tests/                  nova suíte estruturada
test_engine.py          testes de caracterização do motor
test_database.py        testes de caracterização da persistência
clash_gifs.example.txt  modelo seguro de animações locais
```

A arquitetura planejada para a branch séria está em [ARCHITECTURE.md](ARCHITECTURE.md).

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

O protótipo possuía 32 testes automatizados. A branch séria adiciona testes de contrato conforme a arquitetura é extraída.

## Documentação

- [Arquitetura atual e planejada](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Como contribuir](CONTRIBUTING.md)
- [Histórico](CHANGELOG.md)
- [Publicação no GitHub e branches](GITHUB_SETUP.md)

## Licença e propriedade intelectual

Nenhuma licença foi escolhida ainda. Até que um arquivo `LICENSE` seja adicionado, o código permanece com todos os direitos reservados ao autor do repositório.

Não inclua no repositório recursos oficiais de jogos, músicas, vozes, imagens, GIFs ou emojis sem autorização adequada.
