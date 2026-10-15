# PLANO DE EXPERIMENTOS — UNIT-001 (atualizado 2026-10-11)

Parâmetros: lib/geometry/parametros_estudo.json. PML e buffer em nm (pml_nm_estudo, buffer_nm_estudo)
vêm da malha e satisfazem a regra dos monitores (buffer >= 2d). Os experimentos usam esses nomes, não números.

## Ordem de execução (um por vez, após /validar)
| # | Experimento | Pergunta | Estado |
|---|---|---|---|
| 1 | T2_ordem_geometria | ordem de convergência de R, T e chi95 nas geometrias do dataset (PPW 20/30/40) | NOVO. A ordem observada p depende de analisador ainda não registrado (falta). O convergence atual entrega o piso numérico |
| 2 | T2_leve | piso numérico com PPW 15/20/30 | existente, atualizado para a regra |
| 3 | T2_pendencia_fluxo | R/T por Poynting vs especular; A_volume vs 1-R-T | existente, atualizado |
| 4 | T2_ppw40 | quarto nível de PPW | existente, atualizado. Validar o backend antes de rodar |
| 5 | T6_sumidouro_z | Tmax vs distância ao sumidouro em z | BLOQUEADO: a varredura de buffer_nm (200 a 600) viola a regra dos monitores |

## Dados existentes
Rodadas anteriores usaram buffer de 300 nm e PML de 200 nm, com a regra antiga. Não são comparáveis às novas: regenerar.

## Falta (primitivas ainda não registradas)
- Analisador de ordem observada: p = log(e_1/e_2) / log(ppw_2/ppw_1), com critério |p - ORDEM_TEORICA_2A| <= tol_ordem_convergencia.
- T6 lateral e substrato (proposta de 2026-10-10).
- T7, T8, T9 e T3 a T5 (proposta de 2026-10-10).

## Decisões do pesquisador (LIMIT pending)
- closure_tol e spec_tol (T2_pendencia_fluxo).
- tol_ordem_convergencia (JSON, marcado [PENDENTE]).
- Redesenho da varredura de buffer do T6 (sumidouro em z).
- Escada de PPW (20/30/40 no T2_ordem_geometria; 15/20/30 no T2_leve). A escada está escrita no VARY, não no JSON.

## Regras que todos os experimentos seguem
- Valores de estudo por nome (N_FUNDO_ESTUDO, N_INCLUSAO_ESTUDO, PML_NM_ESTUDO, BUFFER_NM_ESTUDO), nunca número escrito.
- PASS = checagens técnicas. Não é validação física.
