# Arquitetura

## Situação do protótipo

O protótipo separa o motor puro, a persistência e a integração com Discord em três arquivos principais:

```text
Discord
  ↓
bot.py
  ├── clash_engine.py
  └── database.py
```

### `bot.py`

Responsável por comandos, autocompletes, embeds, botões, seletores, modais, animações, permissões e auditoria. É funcional, mas concentra responsabilidades demais para a futura versão hospedada.

### `clash_engine.py`

Contém modelos e regras sem dependência direta do Discord:

- Skill e SkillEffect;
- moedas e sanidade;
- Clash e previsão;
- dano;
- defesa e Counter;
- seleção de gatilhos.

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

## Princípios

1. O motor não importa `discord.py`.
2. Componentes do Discord não acessam SQL diretamente.
3. Regras são testadas sem iniciar o bot.
4. Mudanças de banco possuem migração versionada.
5. Sessões e desafios têm estados persistentes.
6. Operações concorrentes usam transações ou atualizações atômicas.
7. Textos e identidade visual ficam fora das regras do motor.
8. Recursos externos devem possuir licença ou ser fornecidos pelo servidor.

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
