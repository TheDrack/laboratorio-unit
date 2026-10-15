de: coordenador
para: pesquisador (aprovação) e equipe de desenvolvimento do laboratório
tipo: especificação de capacidade — VERSÃO 2 (substitui a versão de 19:01)
acao_permitida: propor (nenhuma implementação feita pela IA externa)
data: 2026-10-11

# Especificação: capacidade de execução e edição controlada para os agentes

## 1. Problema

Hoje os estagiários só leem e escrevem texto pelo protocolo de comunicacao/entrada/ (EQUIPE.md). O codificador não executa e o auditor não altera arquivos. Correções e reexecuções exigem um humano em cada passo. Esta especificação define um caminho controlado, com rastreabilidade e sem ampliar o que os agentes decidem sozinhos.

## 2. Princípios

1. Propor, aprovar e executar são atos separados, feitos por papéis diferentes.
2. Nada altera física, tolerância (LIMIT) ou critério de aceitação sem decisão do pesquisador.
3. O original só muda depois de aprovado. Antes disso, toda alteração de código fica na pasta de revisão.
4. Toda ação gera uma linha em comunicacao/log.md com data, papel, arquivo, hash antes e depois.
5. PASS significa que passou nas checagens técnicas, nunca que a física está correta (PADRAO_ESTUDO.md).

## 3. Papéis e permissões

| Papel | Pode | Não pode |
|---|---|---|
| estagiario-codificador | propor experimentos e edições de código, na pasta de revisão | executar; alterar o original |
| estagiario-auditor | ler tudo; escrever em comunicacao/saida/ | alterar arquivos; executar |
| estagiario-relator | resumir resultados em saida/ | concluir física sem checagem independente |
| executor (NOVO) | executar qualquer experimento ou código solicitado pelo pesquisador ou por um coordenador | executar sem solicitação; alterar código; alterar LIMIT |
| editor (NOVO) | aplicar ao original uma revisão aprovada, com backup | aplicar revisão sem aprovação; tocar em dados/ ou em resultados anteriores |

Solicitação: só o pesquisador ou um coordenador pode pedir execução. Um experimento pedido pelo codificador não é executado sem essa solicitação.

## 4. Aprovação

- O pesquisador aprova diretamente, em entrada/, com tipo: aprovacao, citando o nome e o hash da revisão.
- O coordenador pode aprovar somente quando estiver em reunião com o pesquisador. A aprovação deve citar a reunião (data e hora) e registrar que foi dada em nome do pesquisador. Fora de reunião, o coordenador não aprova.

## 5. Pasta de revisão e regra de fila

- Todo código criado ou editado vai para a pasta de revisão (revisao/), nunca diretamente para o original.
- Só existe uma revisão pendente por arquivo. Se já houver uma aguardando aprovação, a nova alteração é feita em cima dela (a revisão pendente é atualizada), e não em uma cópia paralela. O log registra cada atualização com o hash.
- Uma revisão aprovada sai da fila. Depois disso, uma nova alteração do mesmo arquivo cria nova revisão pendente, partindo do original atual.
- Se o original mudou depois que a revisão foi criada, o editor recusa aplicar e devolve ao codificador para rebase.

## 6. Fluxo com portões

1. Codificador escreve a alteração na revisão pendente do arquivo, com: arquivos e linhas, motivo, efeito em resultados existentes, hash do original de referência.
2. Revisor confere e lista perguntas (não escolhe tolerância).
3. Aprovação conforme seção 4.
4. Editor confere que o hash do original ainda é o de referência, copia o original para backup/<data>/, e só então aplica a revisão.
5. Executor roda o experimento ou código solicitado. Resultados vão para pasta versionada: resultados_<versao>_<data>/.
6. Auditor confere integridade (hashes, pasta de saída, log). Relator resume. Ninguém conclui física.

## 7. Garantias técnicas (testes de aceitação antes de ligar a capacidade)

- T-A1: executor recusa execução sem solicitação do pesquisador ou de coordenador.
- T-A2: executor recusa experimento que não passou em /validar.
- T-A3: editor recusa aplicar revisão sem aprovação registrada.
- T-A4: editor recusa aplicar quando o hash do original mudou.
- T-A5: codificador não consegue criar segunda revisão pendente para o mesmo arquivo.
- T-A6: coordenador fora de reunião não consegue aprovar.
- T-A7: editor não escreve fora da lista da revisão e não altera lib/framework/ nem lib/validation/ sem aprovação explícita nominal.
- T-A8: nenhuma execução sobrescreve pasta de resultados existente.
- T-A9: toda ação aparece no log com hash antes e depois.
- T-A10: LIMIT pending continua pending após qualquer ação dos papéis novos (diff do .unl).
- T-A11: reexecução do mesmo experimento com o mesmo código produz o mesmo resultado. Se não produzir, registrar e não concluir.

Os testes rodam em cópia do projeto, nunca no projeto real, até passar.

## 8. Limites de custo e segurança

- Limite de chamadas de LLM por hora (10/h, EQUIPE.md) vale também para executor e editor.
- reserva_gb e timeout_s definidos por experimento (REFERENCIA_UNL.md).
- Nenhuma credencial além do acesso já usado pela equipe é entregue ao executor.

## 9. Decisões ainda abertas

D3. Edições em lib/solvers/ e lib/coupling/ (física) exigem revisão humana adicional, além da aprovação?
D4. Onde ficam os backups: pasta backup/ no Drive ou repositório com histórico?

Decisões já tomadas pelo pesquisador (incorporadas acima): D1 (coordenador aprova só em reunião com o pesquisador); D2 (executor roda qualquer experimento ou código solicitado pelo pesquisador ou coordenador).

## 10. Fora de escopo

Não define o modelo de linguagem de cada papel nem a interface. Não autoriza alteração retroativa de resultados.

## 11. Próximo passo

Com D3 e D4 respondidas, o desenvolvimento implementa executor, editor e a pasta de revisão com os testes T-A1 a T-A11, em cópia do projeto, e só depois liga ao laboratório real.
