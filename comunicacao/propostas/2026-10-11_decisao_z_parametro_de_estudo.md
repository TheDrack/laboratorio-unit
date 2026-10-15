de: ia-externa
para: agentes do laboratório (Codificador, Executor, Relator)
tipo: decisão do pesquisador + correção de tarefa
acao_permitida: executar
data: 2026-10-11
substitui: achado A1 de 2026-10-11_tarefa_auditoria_engrenagem_pipeline.md

# A1 resolvido por decisão: z é parâmetro de estudo, não constante

Decisão do pesquisador: a posição de z dos pilares é uma variável definida no início de cada teste/estudo. Não há razão para um valor fixo no código.

Consequências para a auditoria:

1. A1 deixa de ser "escolher entre z = 4..12 e z = 0..8". O achado passa a ser: `extrator.py` (`add_pillar`, `z0 = 4`) e `geometry_generator.py` (`z = 0` a `pillar_nz`) contêm valores fixos de z, que devem ser removidos e substituídos por um parâmetro declarado no estudo.
2. O parâmetro é declarado no início do estudo (no bloco CASE/FIX do UNIT-L, ou no equivalente da execução) e passa por todo o circuito sem reinterpretação. Não existe valor padrão implícito.
3. Os dois geradores passam a receber o mesmo parâmetro. Assim o problema de divergência entre eles desaparece por construção, sem escolher um lado.
4. Como z altera a distância dos pilares aos monitores e ao sumidouro térmico, o valor escolhido entra no relatório de cada estudo. Ele também é uma variável do T6 (distância ao sumidouro): os estudos que variam z precisam declarar isso explicitamente, e os que não variam, declarar o valor usado.

Pedido aos agentes: listar todos os lugares do pipeline onde z (ou qualquer posição) está fixada sem parâmetro, com linha de código. Não escolher valores. O pesquisador define o valor de cada estudo.

Os demais achados (A2 a A5) continuam como estão na tarefa original.
