# Roadmap — Clash RPG Bot

Este documento organiza a evolução do bot em uma ordem prática. Cada etapa deve ser concluída, testada e documentada antes da próxima.

## Objetivo do produto

Criar uma plataforma de RPG para Discord baseada em disputas de moedas, sanidade e gerenciamento de encontros. O sistema pode ser inspirado em jogos do gênero, mas deve possuir nome, interface, textos e recursos visuais próprios para poder ser distribuído com mais segurança.

## Estado atual

- Fichas de jogadores com SP, Offense Level, Defense Level e modificadores.
- Inimigos com ou sem sanidade e múltiplas skills.
- Skills normais e defensivas.
- Clash, previsão probabilística, Paralyze e moedas inquebráveis.
- Resolução de dano separada do Clash.
- Sessões de batalha persistentes por canal.
- Painel público com participantes, hostis, ações disponíveis e progresso.
- Registro local decorado e banco SQLite.

---

## 1. Ciclo completo de turnos

Prioridade: crítica.

### Recursos

- [x] Botão **Pronto** para o jogador confirmar que terminou sua ação.
- [x] Estados claros: preparação, declaração, resolução e turno encerrado.
- [x] Lista de jogadores que ainda precisam agir.
- [x] Mestre pode bloquear novas declarações e iniciar a resolução.
- [x] Impedir que duas pessoas reservem a mesma ação.
- [x] Encerrar o turno automaticamente quando todos os participantes confirmarem prontidão.
- [x] Comando para o mestre reabrir a fase em caso de correção.
- [x] Recuperação correta do painel depois de reiniciar o bot.

### Concluído quando

- Todo jogador possui um estado visível e persistente.
- O mestre consegue controlar o fluxo sem apagar mensagens.
- O painel fixo sempre representa a situação real da batalha.
- Erros durante um Clash não deixam ações ou jogadores travados.

## 2. Editor avançado de skills

Prioridade: alta.

- [x] Modelo persistente de efeitos configuráveis por moeda.
- [x] Editor textual inicial com validação e prévia no registro da skill.
- [x] Criador visual guiado para skills de jogadores.
- [x] Oficina única para listar, criar, editar, excluir e gerar skill de teste.
- [x] Comando de Clash unificado para jogadores e inimigos.
- [x] Pedido público e consentido de Clash PvP, com escolha da skill pelo defensor.
- [x] Gatilhos: On Use, On Hit, Heads Hit, Clash Win, Clash Lose, Before Attack e After Attack.
- [x] Aplicação automática dos gatilhos durante Clash e dano.
- Moedas positivas, negativas e inquebráveis configuradas individualmente.
- Condições de ativação e consumo.
- Duplicar skill e salvar modelos.
- Validação e prévia antes de salvar.

## 3. Construtor de encontros

Prioridade: alta.

- Salvar grupos de inimigos.
- Inserir várias ações no campo de uma vez.
- Duplicar encontros e turnos anteriores.
- Presets de dificuldade e quantidade de jogadores.
- Biblioteca privada do mestre e biblioteca compartilhada do servidor.

## 4. Velocidade e direcionamento

Prioridade: alta.

- Slots de velocidade.
- Direcionamento de ataques.
- Interceptação por velocidade.
- Ataques unilaterais.
- Regras configuráveis para empate e troca de alvo.
- Visual do campo mostrando ligações entre atacante e alvo.

## 5. Motor completo de status

Prioridade: alta.

- Potency e Count.
- Duração, consumo e expiração automáticos.
- Status prontos como Burn, Bleed, Rupture, Sinking e Tremor.
- Criador de status personalizados.
- Histórico indicando origem, alteração e consumo de cada efeito.

## 6. Histórico e replay

Prioridade: média.

- Relatório completo de cada turno.
- Registro de moedas, SP, modificadores, efeitos e dano.
- Replay resumido em embeds.
- Exportação para texto, JSON e imagem.
- Identificador único para cada batalha.

## 7. Painel avançado do mestre

Prioridade: média.

- Ajustar SP, efeitos e níveis sem comandos extensos.
- Adicionar, remover, reorganizar e corrigir ações.
- Forçar ou desfazer uma resolução com confirmação.
- Permissões por cargo.
- Auditoria de todas as alterações administrativas.

## 8. Campanhas

Prioridade: média.

- Várias campanhas no mesmo servidor.
- Personagens diferentes por campanha.
- Participantes, mestres e permissões por campanha.
- Biblioteca compartilhada de inimigos, skills e encontros.
- Arquivamento e restauração.

## 9. Personalização visual

Prioridade: média.

- Temas de cores próprios.
- Emojis configuráveis por servidor.
- Imagens e GIFs fornecidos pelo servidor.
- Marca e componentes visuais originais do bot.
- Modo compacto e modo cinematográfico.

## 10. Simulador de balanceamento

Prioridade: média.

- Simular centenas ou milhares de Clashes.
- Chance de vitória, média de rodadas e moedas restantes.
- Dano médio, mínimo e máximo.
- Comparação entre duas versões de uma skill.
- Exportação de relatório para o mestre.

## 11. Hospedagem e confiabilidade

Prioridade: necessária antes da comercialização.

- Execução permanente em servidor.
- Banco isolado por servidor ou campanha.
- Backups automáticos e restauração.
- Importação e exportação de dados.
- Monitoramento de erros, métricas e disponibilidade.
- Política de retenção e exclusão de dados.

## 12. Idiomas e acessibilidade

Prioridade: posterior ao MVP comercial.

- PT-BR, inglês e espanhol.
- Termos de combate configuráveis.
- Textos curtos e modo de alto contraste.
- Evitar depender apenas de cores para comunicar estados.
- Ajuda contextual em botões, seletores e modais.

---

## Modelo comercial sugerido

- Núcleo gratuito para uso local e testes comunitários.
- Plano pago para hospedagem permanente, backups e suporte.
- Personalização visual e configuração assistida como serviço opcional.
- Nunca vender emojis, GIFs, músicas, imagens ou outros arquivos oficiais junto com o bot.
- Apresentar o projeto como ferramenta independente e não oficial.

## Regras de desenvolvimento

1. Não colocar token, senha ou segredo no repositório.
2. Toda mudança de regra precisa de teste automatizado.
3. Alterações no banco devem manter compatibilidade com instalações existentes.
4. Uma interação deve atualizar o painel fixo em vez de criar embeds desnecessários.
5. Falhas precisam restaurar reservas e estados para evitar batalhas travadas.
6. Recursos visuais distribuídos com o bot devem ser originais ou possuir licença adequada.

## Próxima entrega

Implementar a etapa 1 começando pela máquina de estados da batalha, botão **Pronto**, indicação de pendências e controles do mestre.
