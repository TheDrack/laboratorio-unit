de: ia-externa
para: agentes do laboratório (Codificador, Executor, Relator)
tipo: inventário (leitura estática, não executada)
acao_permitida: verificar e propor
data: 2026-10-11
regra: parâmetro de estudo é declarado no início do estudo e passa pelo circuito; constante física é a única exceção. Tolerância numérica é decisão do pesquisador (LIMIT pending).

# Inventário de valores fixos no código

Escopo: arquivos presentes na conversa. Não inclui unit_experiment_3d.py, unit002..., nem os logs de execução, que não foram lidos. Cada item foi lido em linha, mas nada foi executado.

## A. Mesma grandeza com duas definições (quebra de engrenagem) — prioridade máxima

A1. Posição de z dos pilares: extrator.py (`add_pillar`, z0 = 4) x geometry_generator.py (z = 0 a pillar_nz). Já decidido: passa a parâmetro de estudo.

A2. Geometria RANDOM_<seed>: extrator.py (`geometry_random`, rejeição com rng.integers) e geometry_generator.py (`generate_random_positions`, rng.shuffle de candidatos) produzem geometrias DIFERENTES com o mesmo nome. Os dados rotulados RANDOM_1003 e RANDOM_1018 podem não ser as mesmas geometrias nos dois pipelines. Pergunta ao pesquisador: qual gerador é o canônico, e qual foi usado nas execuções já feitas?

A3. Plano de monitor de entrada z_mon_in: fdfd3d.py e fdfd2d.py usam npml + buffer//2; fdtd3d.py usa npml + 2. R e T medidos em planos diferentes. Não comparável sem declaração.

A4. Validação FDTD x FDFD (validate_fdtd3d.py): FDTD roda com ppw 20 e PML 15; o comparador FDFD roda com ppw 30 (wl/(N_SLAB*30)) e PML 25. Não é comparação de mesma discretização.

A5. Material 'silício': material_state.py define silicio com ε = 11.7 e κ = 150; extrator.py usa pilar n = 2.0 (ε = 4) com κ = 150; thermal_qk_investigation.py usa K_THERMAL_REFERENCE["silicio"], que não está definido em thermal_coupling.py. O mesmo nome tem valores ópticos diferentes.

A6. Índice do pilar: extrator.py N_PILLAR = 2.0+0.05j; thermal_qk_investigation.py demo usa (2.0+0.15j)^2. Demo, mas o nome 'pilar' tem dois valores.

A7. Laplaciano térmico: energy_state.compute_thermal_channels (build_D2, npml=0) x thermal_coupling.solve_steady_state_temperature (T=0 nas seis faces, média harmônica). Já é o achado A5 da auditoria.

A8. Limites do otimizador duplicados: tmm_benchmark_fixed.py repete bounds em _run_single_optimization e em _run_random_baseline (bounds_lo/bounds_hi). Devem ser idênticos e hoje são mantidos à mão.

A9. Número de amostras aleatórias depende da máquina: tmm_benchmark_fixed.py calcula batch_size = N_RANDOM_BASELINE // NUM_CORES, com NUM_CORES = min(cpu_count, 8). Exemplo: 500 // 8 × 8 = 496; 500 // 3 × 3 = 498. O total de amostras muda com o hardware.

A10. Geometria duplicada: extrator.py e geometry_generator.py repetem NX, NY, NZ, dimensões do pilar, N_PILLARS, FREQUENCIES (280, 300, 320 THz), ORDERED e CLUSTERED. Definir uma vez e importar.

A11. Defaults de PML e buffer em cada módulo, sem vínculo com o estudo: fdfd2d (20/20), fdfd3d (20/20), fdtd3d (15/15), extrator (10/10), validate_fdfd2d (30/30 e 40/40), validate_fdtd3d (25/25), thermal_qk demo (10/8). Nenhum lê do estudo.

A12. Unidades mistas: o código usa células (npml_cells, buffer_cells); os rascunhos UNL usam nm (pml_nm, buffer_nm). A conversão nm → células precisa ser uma função única, chamada no início do estudo.

## B. Parâmetros de estudo fixados no código (devem ser declarados no estudo)

extrator.py: FREQUENCIES_THz; NX, NY, NZ_STRUCT = 16; DX = 25 nm; PILLAR_NX, NY, NZ = 4, 4, 8; N_PILLARS; NPML_CELLS = 10; BUFFER_CELLS = 10; N_BG; N_PILLAR; K_BACKGROUND; K_PILLAR; posições ORDERED e CLUSTERED; range(1000, 1020); max_attempts = 10000; z0 = 4.

fdfd2d.py / fdfd3d.py: condição lateral periódica (x e y) fixada nos operadores; R0 (1e-12 em 2D, 1e-6 em FDTD) e m = 3 da PML; mon_span = 5 (fdfd2d.compute_RT); n_points = 5 (fdfd3d.compute_RT_specular_3d); limite de propagação 1e-9 (compute_diffraction_spectrum); regra de posição dos monitores (buffer//2).

fdtd3d.py: resolution_ppw = 20; npml = 15; buffer_cells = 15; cfl_factor = 0.99; z_mon_in = npml + 2 (ver A3); k_tfsf = n_pad - 2; run_cw_single_frequency: n_cycles_ramp = 8, n_cycles_total = 40, tail_fraction = 0.2.

tmm_benchmark_fixed.py: WAVELENGTHS (0,8; 1,0; 1,2 µm); N_INC = 1.0; N_SUB = 1.5; TOTAL_THICKNESS = 1,0 µm; SIGMAS; RECOVERY_CAP = 0.45 (teto arbitrário de C(x), declarado no próprio código como "limite físico" — não é físico; é escolha de desenho); centros dos kernels 0, 0,5, 1,0; grade de 1000 pontos repetida em várias funções; N_SEEDS = 20; N_RANDOM_BASELINE = 500; seeds base 20000; GAUSS_SAMPLES = 64; differential_evolution (maxiter 150, popsize 15, tol 1e-4); penalidade 1e6; default_rng(42) em permutação e bootstrap.

analise_unit001_desacoplamento.py: INPUT com data fixa (resumo_escalares_20260930_101000.json); OUT com data fixa (analise_desacoplamento_20260930); A_TOL = 0.01; T_RATIO = 2.0; escala de plot 1e12; título do gráfico "ΔA < 1% e Tmax ratio ≥ 2" escrito à mão (fica errado se A_TOL mudar).

geometry.py: wavelength_min = 0,8 µm de referência fixa; min_sep_factor = 1.05; max_tries = 50000; tol = 0.02; fração 0.20 de esfera em thermal_qk demo; caminhos /home/claude.

validate_fdtd3d.py: banda 0,8 a 1,2 µm; n_freq = 25; 6 pontos de checagem; nx = 4.

## C. Tolerâncias numéricas no código (decisão do pesquisador, LIMIT pending)

thermal_coupling.py: Q_NEGATIVE_REL_TOL 1e-10; Q_NEGATIVE_ABS_TOL 1e-30; BOUNDARY_TOL_REL 1e-10; BOUNDARY_TOL_ABS 1e-14; DEFAULT_RTOL 1e-10; DEFAULT_ATOL 1e-14.
energy_state.py: validate(tol = 1e-7).
fdtd_adapter.py: closure_tolerance = 1e-7 nos defaults; 1e-3 no __main__ (o próprio comentário admite).
tmm_benchmark_fixed.py: CONSERVATION_TOL = 1e-5; 1e-8 e 1e-10 em verificações internas; denominador 1e-14.
extrator.py: validate_q_abs tol relativa 1e-12.
spectral_integration.py: eps = 1e-30; rtol = 1e-10.
geometry.py: check_matched_material tol = 0.02.

## D. Constantes físicas repetidas

EPS0, MU0, C_LIGHT e Z0 estão definidos em vários arquivos. Valores equivalentes, exceto formas diferentes de MU0: 4e-7·π (energy_state, spectral_coupling, fdfd_adapter) x 1/(EPS0·c²) (fdfd2d, tmm). Diferença relativa da ordem de 1e-10. Baixa gravidade, mas deve haver uma única fonte.

## Próximo passo sugerido

1. Pesquisador decide: A2 (gerador RANDOM canônico e qual foi usado nas execuções), A3 (regra do plano de monitor), A5 (valores de silício e da fonte de κ), A9 (número de amostras independente do hardware).
2. Codificador elimina duplicações A8, A10 e as constantes repetidas (D), sem alterar valores.
3. Executor confirma cada item com a menor execução possível antes de regenerar dados.
