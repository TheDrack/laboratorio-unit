de: coordenador
para: pesquisador (aprovação) e equipe de desenvolvimento do laboratório
tipo: especificação de capacidade — VERSÃO 4 (substitui a versão 3 de 19:09)
acao_permitida: propor (nenhuma implementação feita pela IA externa)
data: 2026-10-11

# Especificação: capacidade de execução e edição controlada para os agentes

Esta versão fecha o último ponto em aberto. Todo o restante segue a versão 3.

## Decisões do pesquisador

D1. Coordenador aprova somente em reunião com o pesquisador; a aprovação registra a reunião (data e hora) e que foi dada em nome do pesquisador.

D2. Executor roda qualquer experimento ou código solicitado pelo pesquisador ou por um coordenador. Sem solicitação, não executa.

D3. Edições em lib/solvers/ e lib/coupling/ exigem revisão conjunta do coordenador e do pesquisador.

D4. Sem pasta de backup. A pasta de revisão garante que nada sobe com falha, porque o original só muda após aprovação.

D5 (nova). Sem registro de revisões aplicadas (revisao/aprovadas/ não existe). Se algo quebrar, corrige-se no próprio código. O log continua registrando hash antes e depois de cada ação, como já previsto (T-A9).

## Efeito sobre a especificação

- Removidos: a pasta revisao/aprovadas/ e o teste T-A13.
- Nenhuma outra garantia muda.
- Não há mais decisão pendente nesta especificação.

## Garantias técnicas em vigor

T-A1 a T-A12 e T-A13 retirado, conforme as versões anteriores. Os testes rodam em cópia do projeto antes de ligar ao laboratório real.
