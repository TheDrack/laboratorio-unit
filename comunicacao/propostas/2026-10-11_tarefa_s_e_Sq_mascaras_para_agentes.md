de: ia-externa
para: agentes do laboratório (Codificador, Executor, Relator)
tipo: tarefa
acao_permitida: executar
data: 2026-10-11
origem: item 3 da análise de curadoria (2026-10-11_analise_curadoria_verificacao_fontes.md)

# Tarefa: área superficial específica s e função de correlação S(q) das máscaras existentes

Esta tarefa é executada pelos agentes do laboratório. A IA externa não roda cálculos e não interpreta resultados. Nenhum LIMIT é escolhido aqui: todos ficam `pending` para o pesquisador. Este trabalho não altera nenhum resultado anterior e não entra em conclusão física.

## Objetivo

Para cada uma das máscaras estruturais usadas no dataset (22 geometrias: ORDERED, CLUSTERED, RANDOM_1000 a RANDOM_1019), calcular:
1. s: área de interface material/fundo por volume total do domínio estrutural (1/m).
2. S(q): fator de estrutura da máscara binária, na convenção S(q) = |FFT(m - <m>)|^2 / N, com m a máscara 0/1 e N o número de células, agrupado por |q| em anéis radiais.
3. Contatos: número médio de vizinhos materiais em contato face a face por pilar (sem lógica de sobreposição nova).

Os três são descritores candidatos de T7 e T8. Não são controles nem descritores aprovados.

## Entradas (usar exatamente estas, sem reconstruir por conta própria)

- Máscaras: obter do arquivo gerado pelo pipeline de extração (`extrator.py`, função `geometry_*` e `build_full_domain_material_mask`) OU de `geometry_masks.npz` (`geometry_generator.py`). Os dois usam convenções de z diferentes (ver aviso abaixo). O agente deve registrar qual fonte usou e comparar as duas.
- Dimensões: NX = NY = NZ_STRUCT = 16; dx = dy = dz = 25 nm.
- Pilares: 4 × 4 × 8 células, 4 pilares, 64 células por pilar, 256 células de material no total.

## AVISO DE CONSISTÊNCIA (verificar antes de qualquer cálculo)

`extrator.py` posiciona cada pilar em z = 4 até 12. `geometry_generator.py` posiciona em z = 0 até 8. A máscara que o solver usa é a de `extrator.py`. Se o agente calcular s ou S(q) com a máscara de `geometry_generator.py`, o resultado descreve outra geometria. Registrar a diferença e usar a máscara de `extrator.py` como referência para o solver. Não corrigir nenhum dos arquivos sem decisão do pesquisador.

## Checagens independentes (obrigatórias, sem tolerância escolhida pelo agente)

- C1 (pilar isolado): para um único pilar 4×4×8 isolado no domínio, s deve coincidir com a fórmula analítica da área da caixa, 2(4·4 + 4·8 + 4·8) = 160 faces de 25 nm, dividida pelo volume do domínio estrutural. Comparar valor numérico com valor analítico.
- C2 (pilares encostados): dois pilares encostados face a face perdem 2 × 16 faces de contato (área 4×8 em cada face de contato, ou área 4×4 se o contato for pela face menor). O agente deve derivar a perda no papel, registrar a fórmula e comparar com o cálculo numérico.
- C3 (S(q) de uma caixa): o S(q) de um único pilar deve coincidir com |F(q)|^2 / N, com F o fator de forma da caixa calculado analiticamente. Comparar nos mesmos pontos de q.
- C4 (fundo vazio): máscara toda zero deve dar s = 0 e S(q) = 0 para todo q ≠ 0.
- C5 (simetria): ORDERED e CLUSTERED têm simetrias conhecidas nos pilares; S(q) deve respeitá-las. Registrar o resultado.

Se C1 a C4 falharem, o agente para e reporta. Não tenta ajustar até passar.

## Saídas (cada uma com caminho e hash)

- tabela `descritores_mascaras.csv`: uma linha por geometria, com colunas geometry, seed, s, contatos_medios, fonte_mascara.
- tabela `S_q_radial.csv`: uma linha por (geometry, anel de |q|), com S_q e número de pontos no anel.
- relatório `checagens_C1_C5.md`: para cada checagem, valor calculado, valor esperado, diferença absoluta e status (executado / falhou / não executado). Sem conclusão.
- registro de execução: versão do código, data, fonte da máscara, número de células, ambiente.

## Fora do escopo

- Não rodar solver (FDFD, FDTD ou térmico).
- Não calcular ℓ_s, χ95, χ99 nem qualquer desfecho físico.
- Não selecionar descritores nem comparar com modelos de referência.
- Não modificar `extrator.py`, `geometry_generator.py` ou os resultados existentes.

## Dependências de primitiva

O laboratório precisa ter registradas as medidas `area_superficial_especifica`, `fator_estrutura_radial` e `contatos_medios` (ver blocos `falta` em 2026-10-10_1947_proposta_testes_pendentes.md). Se não estiverem registradas, o agente não as implementa dentro de um experimento: emite o bloco `falta` correspondente e para. A implementação deve seguir as regras de composição do laboratório (REFERENCIA_UNL.md).

## Critério de conclusão

A tarefa termina quando as saídas estiverem geradas e o relatório de checagens estiver completo, inclusive com os itens que falharam ou não puderam ser executados. O relatório é entregue ao pesquisador, que decide o que fazer com cada resultado.
