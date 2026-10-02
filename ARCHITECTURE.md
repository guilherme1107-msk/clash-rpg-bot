# Arquitetura

## Arquitetura funcional

O protótipo separa o motor puro, a persistência e a integração com Discord em três arquivos principais:

```text
Discord Activity ─┐
Bot Discord ──────┼──> src/application/services ──> domínio ──> repositório
Central local ────┘
```

## Fluxo atual: Núcleo Geral

O **Núcleo Geral** é a fronteira compartilhada entre as interfaces. Ele não é
mais uma quarta regra de combate: ele recebe uma intenção, valida os dados,
registra um evento e persiste a alteração para que as outras interfaces possam
consultar o mesmo estado.

```text
Activity/Central/Discord
        │ pedido validado
        ▼
Núcleo Geral (core_gateway + serviços)
        │ evento, versão e estado
        ▼
SQLite ◄──────────── Bot autoritativo ────────────► embed/diagnóstico
```

- A **Activity** escolhe personagem, alvo, skill e ação de Encounter.
- A **Central** administra dados, hostis, grupos, Composer e manutenção.
- O **bot** é a autoridade para rolagem de moedas, Clash, dano, SP, escudo e
  aplicação de efeitos de combate.
- O **SQLite** é a fonte compartilhada de fichas, recursos, efeitos, sessões,
  ações em campo, eventos do núcleo e mensagens do Composer.
- A **Sentinela** consulta o diagnóstico que o núcleo expõe; ela não altera
  resultados de combate.

### Encounter e ataques hostis

Cada ação hostil criada para o campo registra uma skill e um alvo participante.
Na Declaração, um jogador pode reservá-la para Clash. Ao encerrar a Declaração,
ações ainda abertas são enviadas pelo bot como ataque sem oposição contra o alvo
registrado. Ataques livres de hostis são uma fila própria para fim de turno e
podem ser sem oposição ou follow-up.

Essa separação evita que uma seleção visual decida o resultado por conta própria:
a Activity só mostra o estado persistido; o bot executa e publica o desfecho.

### Composer rastreável

O Composer envia pelo bot e grava cada mensagem em `composer_messages` com
servidor, canal, ID da mensagem, conteúdo e estado. A Central lista esses
registros e permite editar ou apagar as mensagens ainda marcadas como enviadas.
O recurso começa a rastrear novas mensagens; não inventa histórico anterior.

### `bot.py`

Responsável pela integração com o Discord e pela execução autoritativa do combate: Gateway, slash commands,
permissões do servidor, mensagens, embeds, botões que precisam existir no canal,
auditoria, armazenamento permanente de anexos, rolagem de moedas e resolução de
Clash. As fórmulas continuam no domínio; somente o processo do bot pode executá-las
para alterar o estado oficial.

### `activity_server.py` e `ui/discord-activity`

O frontend renderiza a ficha, editores, Encounter, escolhas de Clash e visão do mestre. O
servidor é um adaptador HTTP: autentica o OAuth do Discord, valida a associação
ao servidor e enfileira a escolha. A Activity não rola moedas, não resolve o
resultado, não controla o Gateway e não envia embeds.

### `src/application/services`

É o núcleo coordenador usado pelas três interfaces. A progressão de ficha já
está em `profile_service.py`; novas extrações devem colocar aqui Skills,
Encounter e resolução completa antes de remover os caminhos antigos.

### `src/domain/combat`

Contém modelos e regras sem dependência direta do Discord:

- Skill e SkillEffect;
- moedas e sanidade;
- Clash e previsão;
- dano;
- defesa e Counter;
- seleção de gatilhos.

O arquivo `clash_engine.py` agora é apenas uma camada temporária de
compatibilidade para instalações e integrações que ainda usam o caminho antigo.

### `database.py`

Gerencia SQLite, criação de tabelas e migrações simples. Dados são separados por `guild_id` e, quando necessário, `channel_id`.

## Direção da branch séria

```text
src/
  bot/
    cogs/             comandos agrupados por domínio
    views/            embeds, botões, seletores e modais
    autocomplete/     pesquisa de alvos, skills e encontros
  domain/
    models/           entidades e tipos de valor
    combat/           Clash, dano, defesa e targeting
    effects/          gatilhos, condições, duração e consumo
  application/
    services/         casos de uso e coordenação
    dto/              dados de entrada e saída
  infrastructure/
    repositories/     implementação da persistência
    migrations/       versões explícitas do banco
    logging/          auditoria e diagnóstico
tests/
  unit/
  integration/
```

## Progresso da migração

- [x] Estrutura inicial de pacotes criada.
- [x] API pública disponível em `src.domain.combat`.
- [x] Bot, banco e testes usam o novo caminho de importação.
- [x] Teste de contrato protege a API pública.
- [x] Mover modelos e tipos de valor para `src.domain.models`.
- [x] Mover as funções de resolução de `clash_engine.py` para os módulos do domínio.
- [x] Transformar `clash_engine.py` em um adaptador de compatibilidade.
- [x] Criar contratos iniciais para personagens, skills e inimigos.
- [x] Extrair e compartilhar o cálculo de progressão da ficha.
- [x] Preparar SQLite para leitores concorrentes com WAL e espera controlada.
- [x] Extrair validação e construção compartilhadas de Skills da Activity e Central.
- [ ] Fazer todos os formulários antigos do bot consumirem o serviço único de Skills.
- [ ] Extrair o serviço único de Encounter.
- [x] Tornar o bot a autoridade de rolagem e resolução pedida pela Activity.
- [ ] Extrair serviços restantes do `bot.py`.
- [ ] Extrair repositórios e migrações de `database.py`.

Os modelos oficiais pertencem a `src.domain.models` e as resoluções a
`src.domain.combat.engine`. A API pública `src.domain.combat` reúne os dois sem
expor a organização interna. O módulo antigo somente reexporta essa API, mantendo
identidade de tipos e comportamento estável durante a migração.

## Princípios

1. O motor não importa `discord.py`.
2. Componentes do Discord não acessam SQL diretamente.
3. Regras são testadas sem iniciar o bot.
4. Mudanças de banco possuem migração versionada.
5. Sessões e desafios têm estados persistentes.
6. Operações concorrentes usam transações ou atualizações atômicas.
7. Textos e identidade visual ficam fora das regras do motor.
8. Recursos externos devem possuir licença ou ser fornecidos pelo servidor.
9. Activity monta o Encounter e escolhe; bot rola, resolve, grava e comunica.

## Divisão definitiva de responsabilidades

| Recurso | Activity | Bot | Núcleo |
|---|---|---|---|
| Ficha completa e editores | renderiza | resumo opcional | valida e salva |
| Skill Workshop | renderiza | atalho/consulta | valida e salva |
| Encounter | campo visual e escolhas | nenhum painel duplicado | fases e reservas |
| Clash | solicita e anima resultado | rola, resolve, grava e publica | fórmulas puras de moedas, SP, efeitos e dano |
| Administração | telas e formulários | permissões Discord | autorização e operações |
| Imagens | exibe CDN | publica anexo permanente | guarda somente a URL |
| Banco | nunca acessa do navegador | por serviço | repositório é o único escritor |

## Domínios planejados

- Personagens e campanhas.
- Skills, moedas e efeitos.
- Inimigos e modelos.
- Encontros e turnos.
- Clash, targeting e velocidade.
- Histórico, replay e exportação.
- Permissões, configuração e auditoria.

## Migração gradual

A branch séria deve preservar o comportamento validado pelo protótipo. Cada extração seguirá esta ordem:

1. Criar testes de caracterização.
2. Extrair modelos e regras.
3. Criar interfaces de repositório.
4. Mover componentes do Discord para views/cogs.
5. Comparar resultados com o protótipo.
6. Remover o código antigo somente após equivalência.

Não é necessário reescrever tudo de uma vez.
