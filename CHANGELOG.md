# Histórico de versões

Todas as mudanças relevantes do projeto serão registradas neste arquivo.

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
