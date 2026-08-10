# Publicação no GitHub e criação das branches

Esta pasta ainda não possui um repositório Git inicializado. Execute os comandos abaixo dentro da pasta `clash-rpg-bot`.

## 1. Congelar o protótipo

```powershell
git init
git branch -M prototype
git add .
git status
```

Antes do commit, confirme que estes arquivos **não aparecem** na área preparada:

```text
.env
.venv/
clash_rpg.sqlite3
clash_audit.log
clash_gifs.txt
```

Depois:

```powershell
git commit -m "chore: freeze prototype v1"
git tag -a prototype-v1.0 -m "Functional Discord RPG prototype"
```

## 2. Conectar ao GitHub

Use a URL do seu repositório:

```powershell
git remote add origin https://github.com/SEU_USUARIO/clash-rpg-bot.git
git push -u origin prototype
git push origin prototype-v1.0
```

Se `origin` já existir:

```powershell
git remote set-url origin https://github.com/SEU_USUARIO/clash-rpg-bot.git
```

## 3. Abrir a versão séria

Crie a nova branch a partir do mesmo commit marcado:

```powershell
git switch -c develop
git push -u origin develop
```

O trabalho novo passa a acontecer em branches menores:

```powershell
git switch -c feature/refactor-architecture
```

Quando a nova arquitetura estiver estável, `main` poderá ser criada a partir de `develop`. A branch `prototype` deve receber apenas correções críticas.

## 4. Verificação de segurança

Antes de cada push:

```powershell
git status
git diff --cached
```

Se um token real tiver sido incluído em qualquer commit, redefina-o imediatamente no Discord Developer Portal. Apenas apagar o arquivo em outro commit não remove o segredo do histórico.
