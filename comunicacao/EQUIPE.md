# EQUIPE — reunião UNIT-001

Estagiários só agem quando são chamados. Não respondem a mensagens que não sejam para eles.

## Quem chama
- pesquisador (você)
- coordenador (IA superior, quando você pedir)

## Como chamar
Coloque o arquivo em `entrada/`, com `para:` apontando para um dos estagiários abaixo, e `de:` = pesquisador ou coordenador. Tipos aceitos: pergunta, tarefa, revisao. Ações aceitas: ler, responder, propor, aplicar_correcao.

Para aplicar_correcao, o cabeçalho também traz `modo: simular` ou `modo: aplicar`. A correção é feita só pela skill_correcao_rapida, nunca por edição manual.

## Equipe
| Estagiário | Função | Não faz |
|---|---|---|
| estagiario-codificador | propõe experimentos em UNIT-L, em texto; aplica correções aprovadas pela skill | executar experimentos; escrever em propostas/ sem pedido; editar arquivo à mão |
| estagiario-revisor | revisa protocolos, limites e ressalvas | escolher tolerâncias ou LIMIT |
| estagiario-relator | resume resultados e escreve atas | concluir física sem checagem independente |
| estagiario-auditor | confere integridade e lista pendências | alterar arquivos |

## Regras de custo
- Mensagem para outro destinatário, de outro estagiário ou com tipo não aceito: ignorada sem gastar LLM.
- Cada mensagem é respondida uma única vez.
- Limite global de 10 chamadas de LLM por hora.
- Estagiários não conversam entre si.
