# UNIT-L 0.1 — referência da linguagem

Descrever experimentos científicos sobre o framework UNIT-001. Quem escreve DESCREVE o experimento; o laboratório valida e executa. Não há laços, I/O nem funções definidas pelo usuário.

> Nunca reimplemente uma capacidade que já existe: componha medidas, solvers, comparadores e analisadores registrados.

Este documento é gerado a partir de `unl_spec.toml` e dos registros do framework.

## Estrutura

```unl
EXPERIMENT Nome {
    ...
}
```

Um comando por linha. `#` inicia comentário. Um EXPERIMENT por arquivo.

## Comandos

### GOAL

- tipo: `text`
- Pergunta científica do experimento, em texto. Aparece no relatório.

```unl
GOAL "Piso numérico de R e T com PPW 15, 20, 30"
```

### CASE

- tipo: `kv`
- chaves aceitas: geometry
- Entidades sobre as quais o experimento roda. Cada valor de geometry vira um conjunto de casos (eixo de caso).

```unl
CASE geometry = [ORDERED, CLUSTERED, RANDOM_1000]
```

### FIX

- tipo: `kv`
- INVARIANTE: parâmetros constantes em todo o experimento. O motor VERIFICA que ficaram constantes no solver (quando o valor efetivo é recomputado) e recusa mudanças.

```unl
FIX frequency_thz = 300.0, n_bg = 1.0+0.0j, pml_nm = 200.0, buffer_nm = 300.0
```

### VARY

- tipo: `kv`
- valores: lista com 2 ou mais itens
- Eixo de varredura: lista com 2 ou mais valores. Produto cartesiano com CASE. Eixos numéricos de resolução (kind numerical) devem estar em ordem crescente.

```unl
VARY ppw = [15, 20, 30]
```

### SOLVE

- tipo: `solve`
- Solver registrado. Opções: backend (auto|direct|iterative), memory_gb, reserva_gb (RAM mínima para o sentinela), timeout_s. Só um SOLVE por experimento.

```unl
SOLVE fdfd3d_te_y, backend = auto, reserva_gb = 2.0
```

### MEASURE

- tipo: `measure`
- Medidas registradas que viram colunas de resultado. Formato alias = medida, ou só medida (alias = nome).

```unl
MEASURE R = R_power, T = T_power, A = A_volume, chi95
```

### DERIVE

- tipo: `assign_expr`
- Grandeza calculada a partir de medidas, limites e constantes, com operadores aritméticos e funções em [engine].expression_functions.

```unl
DERIVE closure = 1 - R - T - A
```

### LIMIT

- tipo: `kv`
- Limite numérico que um CHECK usa. Valor 'pending' significa: o limite é decisão do pesquisador; o CHECK só reporta o valor medido (status PENDENTE).

```unl
LIMIT closure_tol = pending
```

### CHECK

- tipo: `check`
- Condição booleana sobre medidas e limites. Status por ponto: PASS, FAIL ou PENDENTE. Números literais só 0, 1 ou 2.

```unl
CHECK fechamento : abs(closure) <= closure_tol
```

### COMPARE

- tipo: `op_call`
- Operação de comparação entre pontos (registrada em COMPARATORS). Ex.: diferenças entre níveis consecutivos de um eixo.

```unl
COMPARE passos = successive_diff(of = [R, T], along = ppw, group_by = [geometry])
```

### ANALYZE

- tipo: `op_call`
- Análise de resultados (registrada em ANALYZERS). Ex.: piso numérico e E_crit por convergência.

```unl
ANALYZE conv = convergence(of = [R], along = ppw, safety_factor = 3)
```

### OUTPUT

- tipo: `kv`
- chaves aceitas: tables, scalars
- O que vai para o relatório e para o resultado: tabelas (nomes de resultados) e escalares (resultado.chave).

```unl
OUTPUT tables = [cases, passos, conv], scalars = [conv]
```

## Conceitos

- **parâmetro físico**: Propriedade do sistema que define a física (frequência, índices, espessuras físicas). Pode ser FIX ou VARY, mas varrê-lo muda o problema físico.
- **parâmetro numérico**: Escolha de discretização (ex.: ppw). Variá-lo NÃO deve mudar a física: o motor confere que a assinatura física permanece idêntica entre níveis.
- **invariante (FIX)**: Parâmetro declarado constante. O motor confere que o valor efetivamente usado pelo solver é igual ao declarado, quando isso é verificável.
- **eixo**: Dimensão de variação: a geometria (CASE) e cada parâmetro em VARY. Um grupo é o conjunto de pontos que compartilham os valores dos eixos que não são 'along'.
- **medida**: Grandeza escalar por ponto, registrada em MEASURES. Não é reimplementada: é selecionada pelo nome.
- **limite pendente**: LIMIT x = pending. Um CHECK que depende dele fica PENDENTE e só reporta o valor medido. Não se escolhe limite sem evidência.
- **piso numérico**: Diferença entre níveis consecutivos de um eixo numérico, na última etapa. Estimativa de erro de discretização nos dados disponíveis (não é erro assintótico com menos de 4 níveis).
- **E_crit**: Erro operacional de referência = fator de segurança × piso. O fator é convenção declarada no ANALYZE, não derivada.
- **backend auto**: auto: tenta o solver direto sob o sentinela de memória. Se a RAM cair abaixo da reserva, o mesmo ponto é repetido com o iterativo (mesma física).

## Regras

| id | regra | checagem |
|---|---|---|
| R01 | Todo parâmetro obrigatório do registro deve estar em FIX ou VARY. | `required_param` |
| R02 | Um parâmetro não pode ser FIX e VARY ao mesmo tempo, nem aparecer duas vezes. | `fix_vary_conflict` |
| R03 | Todo nome usado em DERIVE, CHECK, COMPARE, ANALYZE e OUTPUT deve ser medida, derivação, limite ou resultado já definido. | `unknown_name` |
| R04 | Em CHECK, números literais só podem ser 0, 1 ou 2. Limites vêm de LIMIT. | `check_literal` |
| R05 | Um eixo numérico de resolução (kind numerical) deve estar em ordem crescente. | `numerical_order` |
| R06 | Nomes de parâmetros, medidas, solvers, geometrias e operações devem existir no registro; sugerimos o mais próximo. | `unknown_registry_name` |
| R07 | Expressões só usam nomes conhecidos, constantes numéricas e as funções de [engine].expression_functions. | `expression_safety` |
| R08 | A soma de casos (geometria × VARY) é estimada em memória e tempo antes da execução; pontos sem backend viável são declarados. | `cost_estimate` |

## Correções automáticas de forma

Estas correções são feitas sem perguntar e aparecem como AVISO:

- `trailing_comma`: vírgula final removida
- `colon_assignment`: ':' trocado por '=' na atribuição
- `vary_brackets`: lista de VARY envolvida em colchetes

## Parâmetros

| nome | tipo | natureza | obrigatório | unidade | descrição |
|---|---|---|---|---|---|
| buffer_nm | float | physical | não | nm | espessura FÍSICA do buffer entre PML e estrutura |
| frequency_thz | float | physical | sim | THz | frequência da onda incidente |
| k_bg | float | physical | não | W/(m·K) | condutividade térmica do fundo |
| k_inclusion | float | physical | não | W/(m·K) | condutividade térmica da inclusão |
| mesh_dx | float | numerical | não | m | passo da malha canônica (m) |
| n_bg | complex | physical | não |  | índice do fundo |
| n_inclusion | complex | physical | não |  | índice da inclusão (Im>0 = absorção) |
| pml_nm | float | physical | não | nm | espessura FÍSICA da PML (deve ser múltiplo de dx em todos os níveis) |
| ppw | float | numerical | não | 1 | pontos por comprimento de onda no meio mais denso (re-rasteriza a MESMA geometria física) |

## Medidas

| nome | unidade | descrição |
|---|---|---|
| A_difference_power | 1 | |A_flux − A_volume| |
| A_flux_power | 1 | absorção por balanço de fluxo (1−R−T) |
| A_volume | 1 | absorção por integral de q no volume (medida INDEPENDENTE de A_flux) |
| P_abs_W | W | potência absorvida no material |
| R_power | 1 | reflectância por fluxo de Poynting (todas as ordens) |
| R_specular | 1 | reflectância da ordem especular |
| T_power | 1 | transmitância por fluxo de Poynting |
| T_specular | 1 | transmitância da ordem especular |
| Tmax_K | K | temperatura máxima no material (θ=0 nas faces) |
| Tmean_K | K | temperatura média no material |
| chi95 | 1 | χ95 = P95(q)/média(q) dentro do material |
| chi99 | 1 | χ99 = P99(q)/média(q) dentro do material |
| dx_nm | nm | passo efetivo da malha |
| f_discreta | 1 | fração de volume do material NA MALHA (muda com a resolução; é derivada, não FIX) |
| ppw_efetivo | 1 | PPW efetivamente obtido após arredondar o número de células |
| q_max_over_mean | 1 | q_max/q_médio no material |

## Solvers

- `fdfd3d_te_y`: FDFD 3D escalar TE_y. Opções: backend=direct|iterative|auto (auto: iterativo se o direto não couber). Aceita 'ppw' (re-rasteriza a geometria física).

## Exemplos

### convergencia_minima

```unl
EXPERIMENT Convergencia_minima {
    GOAL    "Piso numérico de T entre PPW 15 e 20"
    CASE    geometry = [ORDERED]
    FIX     frequency_thz = 300.0, n_bg = 1.0+0.0j, n_inclusion = 2.0+0.05j, pml_nm = 200.0, buffer_nm = 300.0
    VARY    ppw = [15, 20]
    SOLVE   fdfd3d_te_y, backend = auto
    MEASURE T = T_power, A = A_volume
    DERIVE  closure = 1 - T - A
    LIMIT   closure_tol = pending
    CHECK   fechamento : abs(closure) <= closure_tol
    ANALYZE conv = convergence(of = [T], along = ppw, group_by = [geometry], safety_factor = 3)
    OUTPUT  tables = [cases, conv], scalars = [conv]
}
```
