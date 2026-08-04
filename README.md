# Clash RPG Bot — MVP

Bot de Discord para um RPG inspirado em Clash, moedas e sanidade. O projeto reproduz as ideias mecânicas gerais, mas usa nomes, conteúdo e balanceamento próprios.

## Regras do MVP

- SP vai de **−45 a +45**; chance de Heads = `50% + SP` (5% a 95%).
- Uma skill tem **Poder Base**, **Poder de Moeda** e **1–10 moedas**.
- Em cada rodada do Clash, todas as moedas restantes são roladas.
- Poder da rodada = `Base + (Heads × Poder de Moeda)`.
- Quem perde a rodada perde uma moeda; empate repete sem perda.
- Quem perder todas as moedas perde o Clash.
- O vencedor ataca com as moedas restantes. Cada moeda é um golpe e os modificadores de Heads se acumulam.
- Após o resultado, o vencedor recebe **+10 SP** e o perdedor **−5 SP**.
- Poder de Moeda negativo funciona naturalmente: Heads reduzem o poder, então SP baixo é vantajoso.

O bot não usa HP, dano ou Stagger. Toda a progressão mecânica fica concentrada no Clash.

### Efeitos e níveis

- **Paralisia:** cada carga faz uma das próximas moedas roladas ter Coin Power zero. A carga é consumida mesmo se a moeda cair Tails. Cargas não usadas permanecem na ficha.
- **Base Power Up/Down:** soma ou subtrai do Base Power durante o próximo Clash e depois volta a zero.
- **Coin Power Up/Down:** soma ou subtrai do Coin Power durante o próximo Clash e depois volta a zero.
- Cada skill usa o **Offense Level** ou o **Defense Level** de seu personagem, definido ao criar a skill.
- A skill com nível maior recebe **+1 Clash Power por cada 3 níveis completos de vantagem**.

## Arquitetura

- `clash_engine.py`: regras puras e testáveis; não conhece Discord nem banco.
- `database.py`: fichas e skills persistidas em SQLite, separadas por servidor.
- `bot.py`: comandos, permissões e apresentação dos resultados.
- `test_engine.py`: testes das probabilidades, faixas, Clash e ataque.

## Instalação

1. Instale Python 3.11 ou superior.
2. No Discord Developer Portal, crie uma aplicação e um Bot.
3. Convide-o com os escopos `bot` e `applications.commands`. Não é necessário ativar intents privilegiados.
4. Na pasta do projeto, execute:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

5. Edite `.env`, coloque o token e, durante testes, o ID do servidor em `DISCORD_GUILD_ID`.
6. Inicie:

```powershell
python bot.py
```

Nunca publique o arquivo `.env` nem o token. Com `DISCORD_GUILD_ID`, os comandos aparecem rapidamente no servidor indicado; sem ele, a sincronização global do Discord pode demorar.

## Comandos e primeiro combate

Cada participante executa:

```text
/personagem criar nome:Alice
/skill criar nome:Corte poder_base:4 poder_moeda:3 moedas:3
```

O outro jogador pode criar uma skill negativa:

```text
/personagem criar nome:Bruno
/skill criar nome:Ruína poder_base:30 poder_moeda:-10 moedas:2
```

Comandos disponíveis:

- `/personagem status [jogador]`: mostra SP e chance de Heads.
- `/personagem sanidade jogador alteração`: ajuste do mestre; exige “Gerenciar servidor”.
- `/personagem niveis jogador offense defense`: define os dois níveis.
- `/personagem efeitos jogador paralisia base_power coin_power`: aplica buffs ou debuffs.
- `/skill criar ...`: cria ou substitui uma skill de mesmo nome.
- `/skill listar [jogador]`: consulta skills e valores.
- `/clash oponente sua_skill skill_oponente`: resolve o Clash, mostra cada rodada, consome efeitos e atualiza SP.
- `/painel`: interface visual com ficha, skills, criação por formulário e resumo das regras.

Exemplo conceitual de saída:

```text
⚔️ Alice — Corte vs. Bruno — Ruína
R1: H H T 10 | 20 H T — vence →
R2: H H 10 | 30 T T — vence →
R3: H 7 | 20 H T — vence →
🏆 Bruno vence, fica com 2 moedas e ataca: 30 (T), 30 (T).
```

## Testes

```powershell
python -m unittest -v
```

## Próximas extensões recomendadas

1. Criar efeitos declarativos (`on_roll`, `clash_win`, `clash_lose`) em JSON.
2. Registrar Clashes e permitir replays/auditoria das rolagens.
3. Adicionar duração configurável para buffs e debuffs.
4. Migrar para PostgreSQL quando o bot estiver em muitos servidores.
5. Adicionar presets de balanceamento e exportação de fichas.

Para balancear, comece com Base 3–8, Coin Power +1 a +4 e 1–4 moedas. Skills negativas devem ter Base alto e receber custos ou condições, pois ficam muito consistentes em SP baixo.
