# Clash RPG Bot

Protótipo de bot para RPG no Discord baseado em disputas de moedas, sanidade, skills configuráveis e encontros controlados pelo mestre.

> Projeto comunitário, experimental e não oficial. Não possui vínculo ou aprovação da Project Moon. A versão pública deve usar identidade visual e arquivos com licença adequada.

## Estado do projeto

Esta versão representa o marco **Prototype v1**. Ela está funcional para sessões locais e será preservada como referência enquanto uma nova branch recebe a evolução estrutural descrita no [roadmap](ROADMAP.md).

O bot calcula Clash e dano, mas ainda não administra HP, Stagger ou resistência a dano.

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
```

Durante o desenvolvimento, `DISCORD_GUILD_ID` registra os comandos rapidamente nos servidores informados. Separe vários IDs com vírgula. Deixe vazio para sincronização global.

Nunca publique `.env`, token, banco SQLite ou arquivo de auditoria.

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

O criador apresenta uma prévia e listas para tipo, gatilho e efeito. O jogador só precisa digitar nome e valores numéricos.

### Clash unificado

O campo `alvo` de `/clash` mistura:

- `👤` jogadores que possuem ficha;
- `👹` inimigos cadastrados pelo mestre.

Contra jogadores, o bot publica um pedido. Somente o alvo pode aceitar ou recusar. Ao aceitar, ele escolhe sua skill e a mensagem se transforma na previsão e animação do Clash.

Contra inimigos, o jogador escolhe sua skill e também a skill hostil.

## Regras do motor

### Moedas e poder

- Cada skill possui Base Power, Coin Power e entre 1 e 10 moedas.
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
- Vencedor de Clash recebe +10 SP.
- Perdedor recebe −5 SP.
- Inimigos sem sanidade usam 50% de Heads e não alteram SP.

### Tipos de skill

- **Normal:** Clash ofensivo com Offense Level.
- **Defesa:** rolagem defensiva interpretada pelo mestre.
- **Evasiva:** testa cada moeda do ataque até falhar.
- **Counter:** rola sua ativação e calcula o contra-ataque sem Clash.
- **Defesa Clashable:** Clash usando Defense Level.
- **Counter Clashable:** Clash ofensivo seguido de dano.
- **Assist Defense:** interceptação defensiva usando Defense Level.

### Dano final

Depois do Clash, somente as moedas restantes da skill vencedora são roladas. Heads acrescentam Coin Power ao poder acumulado; os valores intermediários não são somados entre si.

```text
Dano Final = max(0, Poder após as Moedas + int((Offense Level - Defense Level) / 3))
```

A diferença de nível é aplicada uma vez e truncada em direção a zero. O resultado é informativo: HP e Stagger continuam sob controle do mestre.

## Efeitos estruturados

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

## Sessões de batalha

Cada canal pode ter uma sessão ativa com quatro fases persistentes:

1. **Preparação:** participantes entram e o mestre monta o campo.
2. **Declaração:** jogadores puxam ações hostis.
3. **Resolução:** novas declarações ficam bloqueadas e participantes confirmam prontidão.
4. **Encerrado:** libera o próximo turno.

Comandos do mestre:

- `/batalha iniciar`
- `/batalha colocar_skill`
- `/batalha painel`
- `/batalha avancar_fase`
- `/batalha reabrir_fase`
- `/batalha avancar_turno`
- `/batalha encerrar`

O painel fixo mostra participantes, SP, estado, hostis, ações e progresso. Reservas são atômicas: dois jogadores não conseguem puxar a mesma ação.

## Inimigos e permissões

O mestre pode criar vários inimigos com skills e efeitos independentes. Operações administrativas exigem a permissão **Gerenciar servidor**.

Jogadores comuns podem editar somente suas próprias fichas e skills. O painel do mestre mantém criação, edição, efeitos e exclusão de inimigos em uma interface separada.

## Personalização

Emojis e GIFs são opcionais. Use URLs diretas para arquivos e emojis no formato `<:nome:ID>` ou `<a:nome:ID>`. Para animações por tipo, copie `clash_gifs.example.txt` para `clash_gifs.txt`; o arquivo local resultante é ignorado pelo Git.

Para uma distribuição pública ou comercial, utilize somente recursos originais, licenciados ou fornecidos pelo administrador do servidor.

## Dados e auditoria

- Dados persistem em SQLite.
- Servidores possuem dados isolados pelo ID do Discord.
- O terminal mostra comandos, botões, alterações, Clashes, dano e erros.
- `clash_audit.log` mantém uma cópia sem cores.
- `.env`, bancos e logs são ignorados pelo Git.

## Estrutura atual

```text
bot.py             comandos, embeds, componentes e auditoria
clash_engine.py    regras puras de moedas, Clash, dano e efeitos
database.py        persistência SQLite e migrações compatíveis
test_engine.py     testes do motor
test_database.py   testes de persistência
clash_gifs.example.txt  modelo seguro do mapeamento local de animações
```

A arquitetura planejada para a branch séria está em [ARCHITECTURE.md](ARCHITECTURE.md).

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

O marco atual possui 32 testes automatizados.

## Documentação

- [Arquitetura atual e planejada](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Como contribuir](CONTRIBUTING.md)
- [Histórico](CHANGELOG.md)
- [Publicação no GitHub e branches](GITHUB_SETUP.md)

## Licença e propriedade intelectual

Nenhuma licença foi escolhida ainda. Até que um arquivo `LICENSE` seja adicionado, o código permanece com todos os direitos reservados ao autor do repositório.

Não inclua no repositório recursos oficiais de jogos, músicas, vozes, imagens, GIFs ou emojis sem autorização adequada.
