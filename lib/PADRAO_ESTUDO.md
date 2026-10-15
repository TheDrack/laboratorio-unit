# PADRÃO DE ESTUDO — UNIT-001 (para humanos e IAs)

Descreve o código padrão da pesquisa UNIT e o estado de validação de cada módulo, segundo a Teoria UNIT (Documento de Estado Atual v0.8). Atualizado em 2026-10-11.

## Princípios
- Mesma matéria, mesma quantidade, mesma fonte e mesmo contorno; só o arranjo geométrico muda.
- Um número só é "físico" se passou por checagem independente (solução analítica, conservação, convergência).
- PASS significa que o artefato passou nas checagens determinísticas. Não significa que a física está correta.
- Constantes físicas fundamentais ficam em `lib/geometry/unit001_constantes.py`. Todo valor de estudo e de validação fica em `lib/geometry/parametros_estudo.json`. Nenhum número de estudo é escrito dentro de função.
- O laboratório é eletromagnético (`tipo_onda: "eletromagnetica"` no JSON). Outros tipos de onda exigem bloco próprio no JSON e solver próprio; a velocidade `c` não se aplica a eles.

## Estado de validação (2026-10-11)
| Item | Módulo | Estado |
|---|---|---|
| FDFD 2D escalar TE_y | `lib/solvers/fdfd2d.py` | VALIDADO na lâmina homogênea (escada de convergência 20/30/40 ppw; conservação) |
| FDFD 3D escalar TE_y | `lib/solvers/fdfd3d.py` | VALIDADO na lâmina homogênea (ordem p = 2,03; fechamento ~10⁻¹³) |
| FDTD 3D, regime CW | `lib/solvers/fdtd3d.py` (`spectral_sweep_cw`, `run_cw_single_frequency`) | VALIDADO na lâmina homogênea (ordem p = 2,10; \|R+T−1\| abaixo do erro de discretização) |
| FDTD 3D, pulso + FFT | `run_fdtd`, `extract_spectral_RT` | NÃO VALIDADO (documentado no próprio arquivo). Não usar para números quantitativos |
| Solver térmico (Poisson 3D) | `lib/coupling/thermal_coupling.py` | autoteste de simetria, linearidade e resíduo; usado pelo framework |
| Ledger de energia | `lib/core/energy_state.py` | em uso pelos adapters |
| TMM 1D | `lib/research/tmm_benchmark.py` | referência de controle |

## Critérios de validação (derivados da física, não de limiar escolhido à mão)
1. **Ordem de convergência:** p = log(e_primeiro / e_último) / log(ppw_último / ppw_primeiro). Deve ficar dentro de ±`TOL_ORDEM_CONVERGENCIA` de `ORDEM_TEORICA_2A` (= 2: diferenças centrais e Yee são de 2ª ordem). A faixa ±0,5 é [PENDENTE]: decisão do pesquisador.
2. **Conservação:** |R + T − 1| (no FDFD 3D, |R + T + A_vol − 1| com A_vol independente de R e T) deve ficar abaixo do erro de discretização da própria malha.

Cada execução da bateria grava um relatório em `validacao/relatorios/`, com a cópia exata dos parâmetros usados.

## Escopo atual da validação
- Geometria: lâmina homogênea, `nx = 4`. A condição periódica lateral não foi exercitada além desse caso.
- As geometrias do dataset (ORDERED, CLUSTERED, RANDOM) ainda não têm escada de convergência. É o próximo teste necessário para o estudo.

## Parâmetros de domínio (derivados)
- Malha: dx = 25 nm (JSON). PML = ceil(λ0min / (|n_Si| · dx)) = 11 células. Buffer = ceil(λ0max / dx) = 43 células.
- Monitores: a d = 0,5 · λ0 da face da estrutura, exigindo buffer ≥ 2d, para que cada monitor fique a pelo menos d tanto da estrutura quanto da PML.
- Correção de 2026-10-11: a regra antiga (monitor em `buffer // 2`) não garantia afastamento da PML. Dados gerados antes dessa data usam a regra antiga e precisam ser regenerados para comparação.

## Achados da pesquisa (estado atual)
- **Barreira Térmica Periférica:** hotspot a 3 células (75 nm) da fronteira T = 0, com κ = 0,026 W/(m·K). Grau de evidência 3 (efeito observado sem controle estatístico).
- **Desacoplamento A × Tmax:** pares com ΔA < 1% e razão de Tmax > 2 nos dados escalares.

## Limitações conhecidas
- FDFD escalar (TE_y), sem full-vector.
- FDTD sem perda, sem campos espaciais; ainda não alimenta o térmico.
- Índice de fundo igual nos dois lados; sem média sub-pixel.
- Sumidouro térmico T = 0 é numérico: a barreira periférica depende do tamanho do domínio.
- Índice do silício (n = 3,6 + 5·10⁻⁴ i) segundo Green (2008). A parte imaginária precisa de confirmação em 1000 nm.
- Dados gerados antes de 2026-10-11 usam buffer e índices antigos.

## Onde está cada coisa
- Código ativo: `lib/framework/` (motor, UNL-L, pipeline, sentinela).
- Parâmetros de estudo e de validação: `lib/geometry/parametros_estudo.json` (único lugar com esses valores).
- Constantes: `lib/geometry/unit001_constantes.py` (carrega o JSON; não edite valores aqui).
- Bateria de validação: `lib/validation/rodar_testes.py` (`rodar_tudo()`).
- Sintaxe da linguagem: `lib/framework/lang/unl_spec.toml`.
- Mapa atual: `_mapa/CONTEXTO_IA.md` (resumo) e `_mapa/mapa.json` (detalhes).

## Para IAs
1. Não reimplemente solver, geometria ou validação que já existe: componha.
2. Não escreva constante nem valor de estudo dentro de função. Use o JSON, e nos experimentos use os nomes dos parâmetros (por exemplo `N_INCLUSAO_ESTUDO`) em vez de números.
3. Antes de usar um número do FDTD, confira que veio do caminho CW.
4. Antes de declarar algo como resultado físico, procure a checagem independente correspondente.
5. Se encontrar um módulo citado aqui que não existe no mapa, registre a divergência; não invente o conteúdo.
