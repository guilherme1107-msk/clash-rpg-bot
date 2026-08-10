# Como contribuir

## Preparação

1. Use Python 3.11 ou superior.
2. Crie um ambiente virtual.
3. Instale `requirements.txt`.
4. Copie `.env.example` para `.env`.
5. Use um bot e servidor exclusivos para desenvolvimento.

## Branches

- `main`: futura versão estável.
- `prototype`: marco funcional preservado e correções críticas.
- `develop`: integração da versão séria.
- `feature/nome-curto`: desenvolvimento isolado de recursos.
- `fix/nome-curto`: correções isoladas.

## Antes de enviar mudanças

Execute:

```powershell
.\.venv\Scripts\python.exe -m py_compile bot.py database.py clash_engine.py
.\.venv\Scripts\python.exe -m unittest -v
```

Confira também:

- nenhum token ou ID pessoal foi adicionado;
- `.env`, banco e logs não estão preparados para commit;
- o README corresponde aos comandos atuais;
- novas regras possuem testes;
- migrações preservam bancos existentes;
- embeds respeitam os limites do Discord;
- falhas devolvem ações reservadas e estados temporários.

## Commits sugeridos

Use mensagens curtas e específicas:

```text
feat: adiciona construtor de encontros
fix: libera ação quando clash falha
docs: atualiza instalação do protótipo
refactor: extrai serviço de desafios
test: cobre moedas inquebráveis
```

## Segurança

Nunca compartilhe o token do Discord. Se um token aparecer em commit, captura de tela ou log público, redefina-o imediatamente no Developer Portal. Remover apenas do último commit não elimina o segredo do histórico.

## Conteúdo externo

Não adicione recursos oficiais ou de terceiros sem licença adequada. Prefira recursos originais, links configuráveis e arquivos fornecidos pelos próprios administradores dos servidores.
