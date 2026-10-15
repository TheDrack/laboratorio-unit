de: coordenador
para: pesquisador (aprovação) e equipe de desenvolvimento do laboratório
tipo: especificação de capacidade
acao_permitida: propor (nenhuma implementação feita pela IA externa)
data: 2026-10-11

# Especificação: capacidade de execução e edição controlada para os agentes

## 1. Problema

Hoje os estagiários só leem e escrevem texto (pelo protocolo de comunicacao/entrada/, em EQUIPE.md). O codificador não executa e o auditor não altera arquivos. Assim, correções de código e reexecuções precisam de um humano em cada passo. Esta especificação define um caminho controlado para que os agentes façam esse trabalho com rastreabilidade, sem ampliar o que eles podem decidir sozinhos.

## 2. Princípios

1. Propor, aprovar e executar são atos separados, feitos por papéis diferentes.
2. Nenhuma ação altera física, tolerância (LIMIT) ou critério de aceitação sem decisão do pesquisador.
3. Nada é sobrescrito. Antes de qualquer edição, o arquivo original é copiado com seu hash.
4. Toda ação gera uma linha em comunicacao/log.md com data, papel, arquivo, hash antes e depois.
5. PASS significa que passou nas checagens técnicas, nunca que a física está correta (PADRAO_ESTUDO.md).

## 3. Papéis e permissões

| Papel | Pode | Não pode |
|---|---|---|
| estagiario-codificador (existente) | propor edições e experimentos em comunicacao/propostas/ | executar; editar lib/ |
| estagiario-auditor (existente) | ler tudo; escrever em comunicacao/saida/ | alterar arquivos; executar |
| estagiario-relator (existente) | resumir resultados em saida/ | concluir física sem checagem independente |
| executor (NOVO) | rodar experimentos já validados (/validar passou) de experimentos/, somente com aprovação registrada | editar código; alterar LIMIT; rodar experimento não aprovado |
| editor (NOVO) | aplicar uma proposta aprovada, somente nos arquivos listados na proposta e fora de lib/framework/ (motor, validação) e de lib/validation/ | aplicar proposta sem hash de aprovação; tocar em dados/ ou em resultados anteriores |

Os dois papéis novos não decidem nada: só executam o que o pesquisador aprovou.

## 4. Fluxo com portões

1. Codificador escreve a proposta em propostas/: arquivos, linhas, motivo, efeito em resultados existentes, e o hash da versão atual de cada arquivo.
2. Revisor confere e lista perguntas (não escolhe tolerância).
3. Pesquisador responde em entrada/ com tipo: aprovacao, citando o nome e o hash da proposta. Sem esse arquivo, nada avança.
4. Editor confere que o hash atual do arquivo ainda é o da proposta. Se mudou, recusa e devolve ao codificador. Copia o original para backup/<data>/ e só então aplica.
5. Executor roda o experimento (ou o menor caso de verificação) com a aprovação citada. Os resultados vão para pasta versionada: resultados_<versao>_<data>/.
6. Auditor confere a integridade (hashes, pasta de saída, log). Relator resume. Ninguém conclui física.

## 5. Garantias técnicas (testes de aceitação antes de ligar a capacidade)

- T-A1: executor recusa experimento sem aprovação registrada.
- T-A2: executor recusa experimento que não passou em /validar.
- T-A3: editor recusa aplicar proposta quando o hash do arquivo mudou.
- T-A4: editor recusa arquivo fora da lista da proposta e qualquer arquivo em lib/framework/ ou lib/validation/.
- T-A5: nenhuma execução sobrescreve pasta de resultados existente.
- T-A6: toda ação aparece no log com hash antes e depois.
- T-A7: LIMIT pending continua pending após qualquer ação dos papéis novos (diff do .unl antes e depois).
- T-A8: reexecução do mesmo experimento com o mesmo código produz o mesmo resultado (determinismo). Se não produzir, registrar e não concluir.

Cada teste roda em cópia do projeto, nunca no projeto real, até passar.

## 6. Limites de custo e segurança

- Limite de chamadas de LLM por hora, já existente (10/h), vale também para executor e editor.
- reserva_gb e timeout_s definidos por experimento (REFERENCIA_UNL.md).
- Execução em máquina do pesquisador: nenhuma credencial de Drive é entregue ao executor além do acesso já usado pela equipe.

## 7. Decisões que cabem ao pesquisador

D1. Quem aprova: somente o pesquisador, ou também o coordenador com aprovação escrita?
D2. O executor pode rodar experimentos novos criados pelo codificador, ou só os já existentes em experimentos/?
D3. Edições em lib/solvers/ e lib/coupling/ (física) exigem revisão humana adicional além da aprovação?
D4. Onde ficam os backups: pasta backup/ no Drive ou repositório com histórico?

## 8. Fora de escopo desta especificação

Não define o modelo de linguagem usado por cada papel, nem a aparência da interface. Não autoriza nenhuma alteração retroativa de resultados.

## 9. Próximo passo

Após D1 a D4 respondidas, o desenvolvimento implementa o executor e o editor com os testes T-A1 a T-A8, em cópia do projeto, e só depois os liga ao laboratório real.
