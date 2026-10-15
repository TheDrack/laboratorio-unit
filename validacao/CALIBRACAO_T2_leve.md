# CALIBRAÇÃO OPERACIONAL — T2_leve (UNIT-001)

Status: APROVADA como calibração operacional, para a faixa testada.
Registro de decisão do pesquisador (10/10/2026). Execução de referência: run_004.

## Escopo
- Geometrias: ORDERED, CLUSTERED, RANDOM_1000.
- PPW: 15, 20 e 30 (9 pontos).
- Frequência 300 THz; backend direto.
- Não extrapolar para PPW 60 nem para outras geometrias sem novos dados.

## Decisões aprovadas
1. closure_tol = 1e-12. Valida o fechamento NUMÉRICO observado (resíduos entre 5e-15 e 2e-14). NÃO valida a conservação física exata nem a correção global do solver.
2. E_crit = 3 × última diferença entre níveis de PPW. Fator 3 = margem convencional de engenharia. NÃO é intervalo de confiança nem garantia de erro máximo.
3. Grandezas:
   - T: primária (estabilidade e monotonicidade nas três geometrias). Piso 0,32%; E_crit 0,96%.
   - R: secundária (diferenças entre níveis maiores). Piso 2,3%; E_crit 7,0%.
   - χ95: secundária e exploratória (monotonicidade falha em ORDERED e CLUSTERED). Piso 1,0%; E_crit 3,1%.
   - R e χ95 não são descartados: diagnosticam efeitos que a transmissão sozinha pode não revelar.

## Ressalvas obrigatórias
- Convergência: três níveis de PPW NÃO demonstram convergência assintótica nem permitem uma ordem de Richardson confiável. Os "pisos" são as últimas diferenças observadas, não erro absoluto comprovado.
- Fechamento de energia: resíduos na precisão de máquina indicam fechamento ALGÉBRICO. Não substituem a validação física independente do balanço (convenções de fluxo, absorção, reflexão e transmissão).
- Limites operacionais: E_crit e piso valem só para a faixa testada.

## Pendências (não concluídas)
1. Recalcular R e T a partir dos fluxos de potência, de forma independente da extração atual.
2. Verificar A_volume contra 1 − R − T quando o balanço for aplicável às condições de contorno.
3. Confirmar que todas as métricas usam a mesma normalização e convenção de potência em todas as geometrias.
4. Só depois, se o orçamento permitir, acrescentar um nível de PPW acima de 30 para avaliar a tendência.

## Regra de uso
Qualquer resultado baseado neste T2 deve citar esta calibração e suas ressalvas. Não declarar convergência assintótica nem erro de discretização com base apenas nestes nove pontos.
