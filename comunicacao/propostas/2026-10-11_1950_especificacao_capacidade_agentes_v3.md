de: coordenador
para: pesquisador (aprovação) e equipe de desenvolvimento do laboratório
tipo: especificação de capacidade — VERSÃO 3 (substitui a versão 2 de 19:05)
acao_permitida: propor (nenhuma implementação feita pela IA externa)
data: 2026-10-11

# Especificação: capacidade de execução e edição controlada para os agentes

Esta versão incorpora as decisões D3 e D4 do pesquisador. Todo o restante segue a versão 2.

## Decisões incorporadas

D1. Coordenador aprova somente em reunião com o pesquisador, e a aprovação registra a reunião (data e hora) e que foi dada em nome do pesquisador.

D2. Executor roda qualquer experimento ou código solicitado pelo pesquisador ou por um coordenador. Sem solicitação, não executa.

D3. Edições em lib/solvers/ e lib/coupling/ (física) são revisadas em conjunto pelo coordenador e pelo pesquisador, antes de qualquer aprovação. Nenhuma aprovação de um só papel basta para essas pastas.

D4. Não haverá pasta de backup. A pasta de revisão é a garantia de que nada sobe com falha: o original só muda após aprovação. O hash do original de referência fica registrado no log.

## Ponto de atenção sobre D4 (não altera a decisão, apenas registra a consequência)

Sem backup, quando uma revisão aprovada substitui o original, a versão anterior deixa de existir como arquivo. Para que ainda seja possível reconstruir o estado anterior, cada revisão aprovada permanece em revisao/aprovadas/, com seu hash de origem e o hash do resultado, sem ser apagada. Isso não é backup do original: é o registro das revisões aplicadas. Se o pesquisador preferir que nem isso exista, a reconstrução de versões antigas depende só do log (hashes), e o código antigo não se recupera sem outra cópia. Decisão de manter ou não o registro: pesquisador.

## Garantias técnicas (acréscimos à versão 2)

- T-A12: editor recusa aplicar em lib/solvers/ ou lib/coupling/ sem a dupla aprovação (coordenador e pesquisador) registrada.
- T-A13: nenhuma revisão aprovada é apagada da pasta de revisão ao ser aplicada.

Os demais testes (T-A1 a T-A11) continuam valendo.

## Próximo passo

Implementar executor, editor e pasta de revisão com os testes T-A1 a T-A13, em cópia do projeto, antes de ligar ao laboratório real. Decisão pendente: manter ou não revisao/aprovadas/ (ver ponto de atenção).
