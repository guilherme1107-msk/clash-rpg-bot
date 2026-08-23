# Arquitetura da V2

## Regra de dependência

```text
presentation ─┐
              ├──> application ───> domain
infrastructure┘
```

O domínio não importa nenhuma das outras camadas. A aplicação descreve os casos
de uso e as portas necessárias. Discord e SQLite são adaptadores substituíveis.

## Modelo inicial

- `Combatant`: estado necessário para resolver uma ação, sem vínculo com Discord.
- `Skill`: definição imutável com uma lista individual de moedas.
- `CoinSpec`: configuração persistente de cada posição da skill.
- `CoinState`: estado transitório de uma moeda durante o Clash.
- `ClashRound`: fotografia completa de uma rodada para log, embed e replay.
- `ClashResult`: resultado final sem efeitos colaterais ocultos.

## Ordem de implementação

1. Motor de Clash e testes de invariantes.
2. Resolução de ataque, dano e follow-up inquebrável.
3. Efeitos, condições, Potency/Count e ciclo de vida.
4. Casos de uso de personagens, skills e inimigos.
5. Repositórios em memória e SQLite com migrações.
6. Sessão de batalha e máquina de estados.
7. Adaptador Discord com painel fixo e componentes persistentes.
8. Importação opcional dos dados do protótipo.

Cada item entra apenas com testes e sem acessar diretamente uma camada externa.

