# Clash RPG Bot — V2

Reconstrução limpa do projeto. O protótipo da raiz continua preservado para
comparação, mas nenhum módulo da V2 depende dele.

## Decisões fundamentais

- regras de combate não conhecem Discord, SQLite, embeds ou emojis;
- cada moeda é uma entidade configurável da skill;
- resultados são objetos imutáveis, adequados para animação e replay;
- aleatoriedade pode receber uma seed para testes reproduzíveis;
- interface, aplicação e persistência dependem do domínio, nunca o contrário;
- termos e recursos visuais serão configuráveis e independentes de terceiros.

## Estrutura

```text
src/clash_rpg/
  domain/          regras e modelos puros
  application/     casos de uso e portas
  infrastructure/  banco, configuração e logs
  presentation/    Discord, embeds e componentes
tests/             testes da V2
```

## Executar os testes

Na pasta `v2`:

```powershell
python -m unittest discover -s tests -v
```

## Primeiro marco

O primeiro marco cobre Skill, moedas comuns e inquebráveis, Sanidade,
Paralisia, Base/Coin/Clash Power, Offense/Defense Level e resolução auditável
de Clash. Dano, efeitos avançados, persistência e Discord serão adicionados
sobre essa base somente depois que seus contratos estiverem definidos.

