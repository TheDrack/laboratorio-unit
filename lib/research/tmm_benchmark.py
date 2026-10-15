import os
# CORREÇÃO: precisa vir ANTES de "import numpy". Em notebooks (Colab/Jupyter),
# o ProcessPoolExecutor usa fork() por padrão no Linux. Se o NumPy/SciPy já
# inicializou threads internas do BLAS (OpenBLAS/MKL) antes do fork, os
# processos-filho podem travar (deadlock silencioso, sem exceção) na primeira
# operação de álgebra linear, porque herdam locks presos de threads que não
# existem mais neles. Forçar 1 thread por processo BLAS evita esse deadlock
# e também evita "oversubscription" de CPU (cada worker tentando abrir suas
# próprias threads dentro de um processo que já é uma unidade de paralelismo).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import time
import sys
import threading
import numpy as np
from scipy.optimize import differential_evolution
from scipy import stats
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from numpy.polynomial.legendre import leggauss
from lib.geometry.unit001_constantes import (BOUNDS_LO, BOUNDS_HI, N_BATCHES, SEED_BASE_BASELINE, MAX_CORES)
from lib.geometry.unit001_constantes import (C_LIGHT, EPS0, MU0, Z0)

# ==============================================================================
# 1. CONSTANTES FÍSICAS EXATAS (SI) E GEOMETRIA
# ==============================================================================

# Configuração BroadBand Multi-Escala (sem dispersão material - mesmo n em todos os λ)
WAVELENGTHS = np.array([0.8e-6, 1.0e-6, 1.2e-6])
OMEGAS = 2.0 * np.pi * C_LIGHT / WAVELENGTHS
K0S = 2.0 * np.pi / WAVELENGTHS
N_WAVELENGTHS = len(WAVELENGTHS)

TOTAL_THICKNESS = 1.0e-6
L = TOTAL_THICKNESS

N_INC = 1.0
N_SUB = 1.5
Z_INC = Z0 / N_INC
Z_SUB = Z0 / N_SUB

SYSTEM_DIMENSION = 1
NUM_CORES = min(multiprocessing.cpu_count(), MAX_CORES)

# ==============================================================================
# 1.1 QUADRATURA PRÉ-CALCULADA
# ==============================================================================
GAUSS_SAMPLES = 64
GAUSS_NODES, GAUSS_WEIGHTS_BASE = leggauss(GAUSS_SAMPLES)

# ==============================================================================
# 1.2 CONFIGURAÇÃO ESTATÍSTICA
# ==============================================================================
N_SEEDS = 20
SIGMAS = [0.04e-6, 0.08e-6, 0.12e-6, 0.16e-6]
N_RANDOM_BASELINE = 500
RECOVERY_CAP = 0.45

# Tolerância única, usada tanto no objetivo "rápido" (durante a otimização)
# quanto na validação rigorosa final. Antes eram diferentes (1e-4 vs 1e-5),
# o que fazia o otimizador convergir para pontos que a validação final rejeitava
# com FloatingPointError não capturado -> processo inteiro derrubado.
CONSERVATION_TOL = 1e-5

# ==============================================================================
# 2. GERAÇÃO DE KERNELS COM LIMITE FÍSICO RÍGIDO
# ==============================================================================
def generate_kernels_for_sigma(x_grid, L, sigma, recovery_cap=RECOVERY_CAP):
    """
    Gera kernels respeitando C(x) <= recovery_cap.
    ATENÇÃO: Equalização de área é tentada, mas pode ser quebrada pelo teto físico
    em kernels de borda (Frontal/Traseiro) com σ pequeno.
    """
    centers = {"Frontal": 0.0, "Central": 0.5, "Traseiro": 1.0}
    kernels = {}
    kernel_params = {}

    ref_unscaled = np.exp(-((x_grid - 0.5 * L) ** 2) / (2.0 * sigma ** 2))
    ref_area = np.trapezoid(ref_unscaled, x_grid) * recovery_cap

    for name, frac in centers.items():
        unscaled = np.exp(-((x_grid - frac * L) ** 2) / (2.0 * sigma ** 2))
        unscaled_area = np.trapezoid(unscaled, x_grid)
        required_amp = ref_area / unscaled_area if unscaled_area > 1e-20 else recovery_cap
        actual_amp = min(recovery_cap, required_amp)
        c = actual_amp * unscaled
        kernels[name] = c
        actual_area = np.trapezoid(c, x_grid)
        c_mean = actual_area / L
        kernel_params[name] = {
            "center": frac * L, "sigma": sigma, "cmax": actual_amp,
            "c_mean": c_mean, "effective_area": actual_area, "name": name,
            "dimension": SYSTEM_DIMENSION
        }

    uniform_required_amp = ref_area / L
    uniform_actual_amp = min(recovery_cap, uniform_required_amp)
    c_uniform = np.full_like(x_grid, uniform_actual_amp)
    kernels["Uniforme"] = c_uniform
    kernel_params["Uniforme"] = {
        "center": 0.5 * L, "sigma": L, "cmax": uniform_actual_amp,
        "c_mean": uniform_actual_amp, "effective_area": uniform_actual_amp * L,
        "name": "Uniforme", "dimension": SYSTEM_DIMENSION
    }
    return kernels, kernel_params

def evaluate_kernel_analytical(x, params):
    """Avaliação analítica do kernel. C(x) é função de ponderação, não propriedade física retroativa."""
    if params["name"] == "Uniforme":
        return np.full_like(x, params["cmax"])
    return params["cmax"] * np.exp(-((x - params["center"])**2) / (2.0 * params["sigma"]**2))

# ==============================================================================
# 3. EXTRAÇÃO DOS PARÂMETROS
# ==============================================================================
def _decode_params(params):
    params = np.asarray(params, dtype=float)
    if params.shape != (12,):
        raise ValueError("params deve possuir 12 parâmetros.")
    n_real = params[0:8:2]
    n_imag = params[1:8:2]
    n_layers = n_real + 1j * n_imag
    raw_weights = np.maximum(params[8:12], 1e-12)
    weights = raw_weights / np.sum(raw_weights)
    d_layers = TOTAL_THICKNESS * weights
    if not np.all(np.isfinite(n_layers)) or not np.all(np.isfinite(d_layers)):
        raise FloatingPointError("Índices ou espessuras não-finitas.")
    if not np.all(d_layers > 0.0):
        raise FloatingPointError("Espessuras inválidas.")
    return n_layers, d_layers

# ==============================================================================
# 4. SOLVER TMM MULTI-CROMÁTICO
# ==============================================================================
def _solve_core_multispectral(params):
    """Solver TMM para M comprimentos de onda (mesmo índice em todos os λ - sem dispersão)."""
    n_layers, d_layers = _decode_params(params)
    results_per_lambda = []

    for m in range(N_WAVELENGTHS):
        k0 = K0S[m]
        omega = OMEGAS[m]

        n_media = np.concatenate((
            np.array([complex(N_INC)]),
            n_layers,
            np.array([complex(N_SUB)])
        ))

        delta = k0 * n_layers * d_layers
        propagation_roundtrip = np.exp(2j * delta)

        if not np.all(np.isfinite(propagation_roundtrip)):
            raise FloatingPointError(f"Propagação não-finita em λ={WAVELENGTHS[m]*1e6:.2f}µm")

        r_interface = np.empty(5, dtype=complex)
        for j in range(5):
            na, nb = n_media[j], n_media[j + 1]
            denominator = na + nb
            if abs(denominator) < 1e-14:
                raise FloatingPointError("Interface singular.")
            r_interface[j] = (na - nb) / denominator

        R_right = r_interface[4]
        for j in range(3, -1, -1):
            r_j = r_interface[j]
            phase = propagation_roundtrip[j]
            denominator = 1.0 + r_j * R_right * phase
            if abs(denominator) < 1e-14:
                raise FloatingPointError(f"Denominador ressonante camada {j+1}")
            R_right = (r_j + R_right * phase) / denominator

        r = R_right
        R = abs(r) ** 2

        A_left = np.empty(4, dtype=complex)
        B_left = np.empty(4, dtype=complex)
        A_current, B_current = 1.0 + 0j, r
        max_err_E, max_err_H = 0.0, 0.0

        for j in range(4):
            na, nb = n_media[j], n_media[j + 1]
            denominator = 2.0 * nb
            if abs(denominator) < 1e-14:
                raise FloatingPointError("Interface singular.")
            A_next = ((na + nb) * A_current + (nb - na) * B_current) / denominator
            B_next = ((nb - na) * A_current + (na + nb) * B_current) / denominator

            E_left = A_current + B_current
            H_left = (na / Z0) * (A_current - B_current)
            E_right = A_next + B_next
            H_right = (nb / Z0) * (A_next - B_next)

            err_E = abs(E_left - E_right)
            err_H = abs(H_left - H_right)
            max_err_E = max(max_err_E, err_E)
            max_err_H = max(max_err_H, err_H)

            if err_E > 1e-10 or err_H > 1e-10:
                raise FloatingPointError(f"Falha interface {j}: |ΔE|={err_E:.3e}")

            A_left[j], B_left[j] = A_next, B_next
            A_current = A_next * np.exp(1j * k0 * n_layers[j] * d_layers[j])
            B_current = B_next * np.exp(-1j * k0 * n_layers[j] * d_layers[j])

        na, nb = n_layers[-1], complex(N_SUB)
        denominator = 2.0 * nb
        if abs(denominator) < 1e-14:
            raise FloatingPointError("Interface final singular.")
        A_sub = ((na + nb) * A_current + (nb - na) * B_current) / denominator
        B_sub = ((nb - na) * A_current + (na + nb) * B_current) / denominator

        substrate_residual = abs(B_sub)
        if substrate_residual > 1e-8:
            raise FloatingPointError(f"Onda regressiva substrato: |B_sub|={substrate_residual:.3e}")

        t = A_sub
        T = abs(t) ** 2 * N_SUB / N_INC

        if not np.isfinite(R) or not np.isfinite(T) or R < -1e-10 or T < -1e-10:
            raise FloatingPointError("R/T inválido.")
        if R > 1.0 + 1e-10 or T > 1.0 + 1e-10:
            raise FloatingPointError(f"R ou T > 1: R={R}, T={T}")

        A_flux = 1.0 - R - T
        if A_flux < -1e-8:
            raise FloatingPointError(f"Absorção negativa: A={A_flux}")

        results_per_lambda.append({
            "k0": k0, "omega": omega, "lambda": WAVELENGTHS[m],
            "R": R, "T": T, "A_flux": A_flux, "r": r, "t": t,
            "A_left": A_left, "B_left": B_left,
            "max_err_E": max_err_E, "max_err_H": max_err_H,
            "substrate_residual": substrate_residual
        })

    return results_per_lambda, n_layers, d_layers

# ==============================================================================
# 5. INTEGRAÇÃO RÁPIDA MULTI-CROMÁTICA
# ==============================================================================
def _calculate_absorption_recovery_fast(core_results, n_layers, d_layers, kernel_params):
    """Integra q_abs e η_rec para todos os comprimentos de onda. Também devolve A_poynting
    para permitir que o objetivo 'rápido' aplique a MESMA checagem de conservação de energia
    usada na validação rigorosa (antes só a validação final checava Poynting)."""
    P_in_total = 0.0
    P_abs_total = 0.0
    P_rec_total = 0.0
    A_poynting_list = []

    for core in core_results:
        k0 = core["k0"]
        omega = core["omega"]
        A_left = core["A_left"]
        B_left = core["B_left"]
        P_in = 0.5 / Z_INC
        P_in_total += P_in

        A_poynting_list.append((P_in * (1.0 - core["R"]) - 0.5 * abs(core["t"]) ** 2 / Z_SUB) / P_in)

        x_offset = 0.0
        for j in range(4):
            n, d = n_layers[j], d_layers[j]
            local_x = 0.5 * d * (GAUSS_NODES + 1.0)
            quad_weights = 0.5 * d * GAUSS_WEIGHTS_BASE
            k = k0 * n

            A, B = A_left[j], B_left[j]
            E = A * np.exp(1j * k * local_x) + B * np.exp(-1j * k * local_x)
            q_abs = 0.5 * omega * EPS0 * np.imag(n ** 2) * np.abs(E) ** 2

            if np.min(q_abs) < -1e-10:
                raise FloatingPointError(f"q_abs negativa em λ={core['lambda']*1e6:.2f}µm")

            global_x = x_offset + local_x
            c_local = evaluate_kernel_analytical(global_x, kernel_params)

            P_abs_total += np.sum(quad_weights * q_abs)
            P_rec_total += np.sum(quad_weights * c_local * q_abs)
            x_offset += d

    A_integrated = P_abs_total / P_in_total
    eta_rec = P_rec_total / P_in_total
    A_poynting_mean = float(np.mean(A_poynting_list))
    return A_integrated, eta_rec, A_poynting_mean

# ==============================================================================
# 6. SOLVER RIGOROSO MULTI-CROMÁTICO
# ==============================================================================
def simulate_multispectral(params, kernel_params, samples_per_layer=64):
    """Solver rigoroso multi-cromático com todas as métricas."""
    gauss_nodes, gauss_weights_base = (
        (GAUSS_NODES, GAUSS_WEIGHTS_BASE)
        if samples_per_layer == GAUSS_SAMPLES
        else leggauss(samples_per_layer)
    )

    core_results, n_layers, d_layers = _solve_core_multispectral(params)

    R_total = np.mean([c["R"] for c in core_results])
    T_total = np.mean([c["T"] for c in core_results])
    A_flux_total = np.mean([c["A_flux"] for c in core_results])
    max_err_E = max([c["max_err_E"] for c in core_results])
    max_err_H = max([c["max_err_H"] for c in core_results])
    max_sub_res = max([c["substrate_residual"] for c in core_results])

    S_in_gross = 0.5 / Z_INC
    x_all, q_all, w_all = [], [], []
    P_abs_total, P_rec_total = 0.0, 0.0

    for core in core_results:
        k0 = core["k0"]
        omega = core["omega"]
        A_left = core["A_left"]
        B_left = core["B_left"]

        x_offset = 0.0
        for j in range(4):
            n, d = n_layers[j], d_layers[j]
            local_x = 0.5 * d * (gauss_nodes + 1.0)
            quad_weights = 0.5 * d * gauss_weights_base
            k = k0 * n

            A, B = A_left[j], B_left[j]
            forward = A * np.exp(1j * k * local_x)
            backward = B * np.exp(-1j * k * local_x)
            E = forward + backward
            q_abs = 0.5 * omega * EPS0 * np.imag(n ** 2) * np.abs(E) ** 2

            global_x = x_offset + local_x
            c_local = evaluate_kernel_analytical(global_x, kernel_params)

            P_abs_total += np.sum(quad_weights * q_abs)
            P_rec_total += np.sum(quad_weights * c_local * q_abs)

            x_all.append(global_x)
            q_all.append(q_abs)
            w_all.append(quad_weights)
            x_offset += d

    A_integrated_total = P_abs_total / (S_in_gross * N_WAVELENGTHS)
    eta_rec_total = P_rec_total / (S_in_gross * N_WAVELENGTHS)

    if P_abs_total > 1e-20:
        x_flat = np.concatenate(x_all)
        q_flat = np.concatenate(q_all)
        w_flat = np.concatenate(w_all)
        q_weighted = q_flat * w_flat
        total_q = np.sum(q_weighted)
        x_abs = np.sum(q_weighted * x_flat) / total_q
        sigma_abs = np.sqrt(np.sum(q_weighted * (x_flat - x_abs)**2) / total_q)
    else:
        x_abs, sigma_abs = 0.0, 0.0

    x_C = kernel_params["center"]
    d_C = abs(x_abs - x_C) / L

    rho_rec = eta_rec_total / A_flux_total if A_flux_total > 1e-15 else 0.0
    c_mean = kernel_params["c_mean"]
    rho_spatial = (eta_rec_total / (c_mean * A_flux_total)) if (c_mean * A_flux_total) > 1e-15 else 0.0

    A_poynting_total = np.mean([
        (S_in_gross * (1.0 - c["R"]) - 0.5 * abs(c["t"])**2 / Z_SUB) / S_in_gross
        for c in core_results
    ])

    quadrature_error = abs(A_integrated_total - A_flux_total)
    poynting_error = abs(A_poynting_total - A_flux_total)

    if quadrature_error > CONSERVATION_TOL or poynting_error > CONSERVATION_TOL:
        raise FloatingPointError(f"Falha conservação: |ΔA_quad|={quadrature_error:.3e}, |ΔA_poy|={poynting_error:.3e}")

    eta_global = T_total + eta_rec_total
    kernel_cmax = kernel_params["cmax"]
    eta_max_theoretical = kernel_cmax * (1.0 - R_total) + (1.0 - kernel_cmax) * T_total

    if eta_global > eta_max_theoretical + CONSERVATION_TOL:
        raise FloatingPointError(f"η_global excede cota: {eta_global:.6f} > {eta_max_theoretical:.6f}")

    return {
        "R": R_total, "T": T_total, "A_flux": A_flux_total,
        "A_integrated": A_integrated_total, "A_poynting": A_poynting_total,
        "eta_rec": eta_rec_total, "eta_global": eta_global,
        "rho_rec": rho_rec, "rho_spatial": rho_spatial,
        "x_abs": x_abs, "sigma_abs": sigma_abs,
        "d_C": d_C,
        "quadrature_error": quadrature_error, "poynting_error": poynting_error,
        "max_err_E": max_err_E, "max_err_H": max_err_H,
        "substrate_residual": max_sub_res,
        "n_layers": n_layers, "d_layers": d_layers,
    }

# ==============================================================================
# 7. FUNÇÕES OBJETIVO E WORKERS
# ==============================================================================
def obj_baseline_2_fast(params):
    try:
        core_results, _, _ = _solve_core_multispectral(params)
        T_mean = np.mean([c["T"] for c in core_results])
        return -T_mean
    except (FloatingPointError, ValueError, ZeroDivisionError, OverflowError):
        return 1e6

def obj_unit_fast(params, kernel_params):
    """
    CORREÇÃO: as checagens abaixo agora usam a MESMA tolerância (CONSERVATION_TOL)
    e o MESMO critério (incluindo Poynting) que simulate_multispectral() usa na
    validação final. Antes, este objetivo usava tolerâncias mais frouxas (1e-4/1e-6)
    e não checava Poynting, então o otimizador convergia com frequência para pontos
    que a validação rigorosa final rejeitava com FloatingPointError -- e como essa
    validação era chamada sem try/except dentro do worker, o processo inteiro
    (ProcessPoolExecutor) morria sem terminar o benchmark.
    """
    try:
        core_results, n_layers, d_layers = _solve_core_multispectral(params)
        A_integrated, eta_rec, A_poynting = _calculate_absorption_recovery_fast(
            core_results, n_layers, d_layers, kernel_params
        )
        A_flux_mean = np.mean([c["A_flux"] for c in core_results])
        R_mean = np.mean([c["R"] for c in core_results])
        T_mean = np.mean([c["T"] for c in core_results])

        if abs(A_integrated - A_flux_mean) > CONSERVATION_TOL:
            return 1e6
        if abs(A_poynting - A_flux_mean) > CONSERVATION_TOL:
            return 1e6
        if eta_rec < -1e-10:
            return 1e6

        kernel_cmax = kernel_params["cmax"]
        eta_global = T_mean + eta_rec
        eta_max_theoretical = kernel_cmax * (1.0 - R_mean) + (1.0 - kernel_cmax) * T_mean

        if eta_global > eta_max_theoretical + CONSERVATION_TOL:
            return 1e6

        return -eta_global
    except (FloatingPointError, ValueError, ZeroDivisionError, OverflowError):
        return 1e6

def _run_single_optimization(args):
    """
    CORREÇÃO CRÍTICA: toda a lógica (incluindo a chamada final a
    simulate_multispectral, que antes rodava fora de qualquer try/except)
    agora está protegida. Se, mesmo com o objetivo mais rígido, a solução
    final ainda falhar na validação, a tarefa é marcada como inválida
    (valid=False) em vez de derrubar o ProcessPoolExecutor inteiro.
    """
    name, kernel_params, worker_seed, mode, sigma = args
    try:
        np.random.seed(worker_seed)

        bounds = [
            (1.1, 3.5), (0.001, 0.5), (1.1, 3.5), (0.001, 0.5),
            (1.1, 3.5), (0.001, 0.5), (1.1, 3.5), (0.001, 0.5),
            (0.05, 1.0), (0.05, 1.0), (0.05, 1.0), (0.05, 1.0)
        ]

        if mode == "B2":
            obj = obj_baseline_2_fast
            obj_args = ()
        else:
            obj = obj_unit_fast
            obj_args = (kernel_params,)

        result = differential_evolution(
            obj, bounds, args=obj_args,
            seed=worker_seed, maxiter=150, popsize=15, polish=True, tol=1e-4,
            workers=1, updating='deferred'
        )

        null_kernel_params = {
            "center": 0.0, "sigma": 1e-9, "cmax": 0.0, "c_mean": 0.0,
            "effective_area": 0.0, "name": "Null", "dimension": SYSTEM_DIMENSION
        }
        kernel_for_sim = null_kernel_params if mode == "B2" else kernel_params

        res = simulate_multispectral(result.x, kernel_for_sim, samples_per_layer=64)

        return {
            "name": name, "mode": mode, "seed": worker_seed, "sigma": sigma,
            "simulation": res, "params": result.x,
            "objective": result.fun, "success": result.success, "nfev": result.nfev,
            "valid": True, "error": None,
        }
    except Exception as e:
        # Nenhuma exceção sai do worker sem tratamento: a tarefa é descartada
        # com o motivo registrado, e o benchmark continua normalmente.
        return {
            "name": name, "mode": mode, "seed": worker_seed, "sigma": sigma,
            "simulation": None, "params": None,
            "objective": None, "success": False, "nfev": None,
            "valid": False, "error": f"{type(e).__name__}: {e}",
        }

def _run_random_baseline(args):
    seed_start, seed_end = args
    rng = np.random.RandomState(seed_start)
    bounds_lo, bounds_hi = BOUNDS_LO, BOUNDS_HI
    results = []
    for i in range(seed_end - seed_start):
        params = rng.uniform(bounds_lo, bounds_hi)
        try:
            core_results, _, _ = _solve_core_multispectral(params)
            results.append({
                "T": np.mean([c["T"] for c in core_results]),
                "R": np.mean([c["R"] for c in core_results]),
                "A_flux": np.mean([c["A_flux"] for c in core_results]),
                "valid": True
            })
        except (FloatingPointError, ValueError, ZeroDivisionError, OverflowError):
            results.append({"valid": False})
    return results

# ==============================================================================
# 7.1 EXECUÇÃO PARALELA COM PROGRESSO EM TEMPO REAL
# ==============================================================================
def run_pool_with_progress(executor, fn, tasks, label="Tarefas", heartbeat_seconds=15):
    """
    Substitui executor.map(...) (que só retorna quando TUDO termina, sem
    feedback intermediário) por submit()+as_completed(), imprimindo progresso
    conforme cada tarefa termina: % concluído, falhas acumuladas, tempo
    decorrido e ETA. A ordem dos resultados não importa aqui porque cada
    resultado carrega seus próprios identificadores (name/seed/mode/sigma).

    Além disso, uma thread de "heartbeat" imprime o status a cada
    `heartbeat_seconds`, MESMO que nenhuma tarefa tenha terminado ainda.
    Isso é essencial para distinguir "está rodando, só é lento" de
    "travou de verdade" (ex.: deadlock de multiprocessing) — sem isso, o
    primeiro print só aparece depois que a 1ª leva de tarefas terminar,
    o que pode demorar bastante com poucos núcleos.
    """
    total = len(tasks)
    if total == 0:
        return []
    t0 = time.time()
    print(f"    [{label}] enviando {total} tarefas para o pool de processos...", flush=True)
    futures = {executor.submit(fn, t): t for t in tasks}

    state = {"done": 0, "fail": 0, "finished": False}
    lock = threading.Lock()

    def heartbeat():
        while True:
            time.sleep(heartbeat_seconds)
            with lock:
                if state["finished"]:
                    return
                done, n_fail = state["done"], state["fail"]
            elapsed = time.time() - t0
            print(
                f"    [{label}] (heartbeat) ainda em execução | {done}/{total} concluídas | "
                f"falhas={n_fail} | decorrido={elapsed:6.1f}s",
                flush=True
            )

    hb_thread = threading.Thread(target=heartbeat, daemon=True)
    hb_thread.start()

    results = []
    print_every = max(1, total // 40)  # ~40 atualizações de progresso no total

    for fut in as_completed(futures):
        try:
            res = fut.result()
        except Exception as e:
            # Se até o próprio future falhar de forma inesperada (ex.: processo
            # worker morto por sinal), registramos e seguimos em frente.
            task = futures[fut]
            res = {"valid": False, "error": f"Future falhou: {e}", "task": task}

        with lock:
            state["done"] += 1
            if isinstance(res, dict) and res.get("valid", True) is False:
                state["fail"] += 1
            done, n_fail = state["done"], state["fail"]

        results.append(res)

        if done % print_every == 0 or done == total:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else 0.0
            print(
                f"    [{label}] {done:>4}/{total} ({done/total*100:5.1f}%) | "
                f"falhas={n_fail:>3} | decorrido={elapsed:6.1f}s | ETA={eta:6.1f}s",
                flush=True
            )

    with lock:
        state["finished"] = True
    return results

# ==============================================================================
# 8. UTILITÁRIOS ESTATÍSTICOS PAREADOS (CORRIGIDOS)
# ==============================================================================
def wilcoxon_signed_rank_paired(D, alternative='greater'):
    """Wilcoxon Signed-Rank Test pareado (uma cauda)."""
    D = np.asarray(D)
    D = D[D != 0]
    if len(D) < 5:
        return 1.0
    stat, pval = stats.wilcoxon(D, alternative=alternative, method='auto')
    return pval

def sign_permutation_test_paired(D, n_permutations=10000, alternative='greater'):
    """Teste de Permutação de Sinal Pareado (Monte Carlo)."""
    D = np.asarray(D)
    observed_mean = np.mean(D)
    rng = np.random.default_rng(42)
    count = 0
    for _ in range(n_permutations):
        signs = rng.choice([-1, 1], size=len(D))
        perm_mean = np.mean(D * signs)
        if alternative == 'greater':
            if perm_mean >= observed_mean:
                count += 1
        else:
            if perm_mean <= observed_mean:
                count += 1
    return count / n_permutations

def bootstrap_paired_ci(D, n_bootstraps=2000, ci=0.95):
    """Bootstrap pareado da diferença média."""
    D = np.asarray(D)
    rng = np.random.default_rng(42)
    means = []
    for _ in range(n_bootstraps):
        sample = rng.choice(D, size=len(D), replace=True)
        means.append(np.mean(sample))
    lower = np.percentile(means, (1 - ci) / 2 * 100)
    upper = np.percentile(means, (1 + ci) / 2 * 100)
    return lower, upper

def apply_fdr_correction(pvalues, alpha=0.05):
    """Correção Benjamini-Hochberg FDR."""
    if len(pvalues) == 0:
        return np.array([])
    try:
        from scipy.stats import false_discovery_control
        return false_discovery_control(np.array(pvalues), method='bh')
    except ImportError:
        pvalues = np.array(pvalues)
        n = len(pvalues)
        order = np.argsort(pvalues)
        ranked = np.empty_like(pvalues, dtype=float)
        cummin = 1.0
        for i in range(n - 1, -1, -1):
            idx = order[i]
            adjusted = min(pvalues[idx] * n / (i + 1), 1.0)
            cummin = min(cummin, adjusted)
            ranked[idx] = cummin
        return ranked

# ==============================================================================
# 9. EXECUÇÃO DO BENCHMARK UNIT-001C.1 REVISED v3 (COM PROGRESSO + FAULT-TOLERANCE)
# ==============================================================================
def run_benchmark_unit_001c1_revised_v2():
    print("=" * 140)
    print("  BENCHMARK UNIT-001C.1 REVISED v3 — PAREAMENTO POR SEED + FDR DUPLO + PROGRESSO + FAULT-TOLERANCE")
    print(f"  λ = {WAVELENGTHS*1e6} µm | Dimensão = {SYSTEM_DIMENSION}D | {N_SEEDS} seeds pareadas | {len(SIGMAS)} σ")
    print("=" * 140, flush=True)

    shared_seeds = list(range(1, N_SEEDS + 1))

    tasks_b2 = [(f"B2_s{s}", None, s, "B2", None) for s in shared_seeds]

    tasks_unit = []
    for sigma in SIGMAS:
        kernels, kernel_params = generate_kernels_for_sigma(np.linspace(0, L, 1000), L, sigma)
        sigma_um = sigma * 1e6
        for kernel_name, params in kernel_params.items():
            for s in shared_seeds:
                tasks_unit.append((f"{kernel_name}_sig{sigma_um:.0f}_s{s}", params, s, "UNIT", sigma))

    N_BATCHES = 8  # fixo: o total de amostras não depende da máquina
    sizes = [N_RANDOM_BASELINE // N_BATCHES + (1 if i < N_RANDOM_BASELINE % N_BATCHES else 0)
             for i in range(N_BATCHES)]
    tasks_random = []
    start = SEED_BASE_BASELINE
    for sz in sizes:
        tasks_random.append((start, start + sz))
        start += sz

    all_tasks = tasks_b2 + tasks_unit
    print(f"\n[1/3] Executando {len(tasks_b2)} B2 + {len(tasks_unit)} UNIT (seeds pareadas) em {NUM_CORES} núcleos...")
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=NUM_CORES) as executor:
        opt_results = run_pool_with_progress(executor, _run_single_optimization, all_tasks, label="B2+UNIT")

    print(f"      Concluído em {time.time() - t0:.1f}s", flush=True)

    print(f"\n[2/3] Baseline aleatória ({N_RANDOM_BASELINE} amostras)...")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=NUM_CORES) as executor:
        random_batches = run_pool_with_progress(executor, _run_random_baseline, tasks_random, label="Baseline")
    random_samples = [s for batch in random_batches if isinstance(batch, list) for s in batch if s.get("valid", False)]
    print(f"      Concluído em {time.time() - t0:.1f}s ({len(random_samples)} válidas)", flush=True)

    b2_runs = [r for r in opt_results if r.get("mode") == "B2" and r.get("valid", True)]
    unit_runs = [r for r in opt_results if r.get("mode") == "UNIT" and r.get("valid", True)]
    failed_runs = [r for r in opt_results if not r.get("valid", True)]

    print(f"\n  Tarefas B2 válidas   : {len(b2_runs)}/{len(tasks_b2)}")
    print(f"  Tarefas UNIT válidas : {len(unit_runs)}/{len(tasks_unit)}")
    if failed_runs:
        print(f"  {len(failed_runs)} tarefas falharam e foram descartadas. Exemplos:")
        for r in failed_runs[:5]:
            print(f"    - {r.get('name')}: {r.get('error')}")

    if len(b2_runs) == 0 or len(unit_runs) == 0:
        print("\n  ERRO: não há execuções válidas suficientes para prosseguir com a análise estatística.")
        print("  Verifique as mensagens de falha acima (tolerâncias, bounds, etc).")
        return {
            "b2_runs": b2_runs, "unit_runs": unit_runs,
            "random_samples": random_samples, "failed_runs": failed_runs,
        }

    # Reavaliação B2+C com pareamento explícito por seed
    print(f"\n[3/3] Reavaliando {len(b2_runs)} soluções B2 com kernels (pareamento por seed)...")
    t0 = time.time()
    b2_plus_c_results = {}  # {(sigma_um, kernel_name): {seed: sim_result}}

    reval_total = len(SIGMAS) * 4 * len(b2_runs)  # 4 kernels por sigma
    reval_done = 0
    reval_print_every = max(1, reval_total // 20)

    for sigma in SIGMAS:
        sigma_um = sigma * 1e6
        _, kernel_params = generate_kernels_for_sigma(np.linspace(0, L, 1000), L, sigma)
        for kernel_name, kparams in kernel_params.items():
            b2_plus_c_results[(sigma_um, kernel_name)] = {}
            for b2_run in b2_runs:
                seed = b2_run["seed"]
                try:
                    sim = simulate_multispectral(b2_run["params"], kparams, samples_per_layer=64)
                    b2_plus_c_results[(sigma_um, kernel_name)][seed] = sim
                except (FloatingPointError, ValueError):
                    pass
                reval_done += 1
                if reval_done % reval_print_every == 0 or reval_done == reval_total:
                    print(f"    [Reavaliação B2+C] {reval_done}/{reval_total} "
                          f"({reval_done/reval_total*100:5.1f}%)", flush=True)
    print(f"      Concluído em {time.time() - t0:.1f}s", flush=True)

    # ==============================================================================
    # RELATÓRIO
    # ==============================================================================
    print("\n" + "=" * 140)
    print("  RESULTADOS ESTATÍSTICOS PAREADOS (CORRIGIDOS)")
    print("=" * 140)

    all_valid = b2_runs + unit_runs
    max_quad = max([r["simulation"]["quadrature_error"] for r in all_valid])
    max_poy = max([r["simulation"]["poynting_error"] for r in all_valid])
    max_E = max([r["simulation"]["max_err_E"] for r in all_valid])
    max_sub = max([r["simulation"]["substrate_residual"] for r in all_valid])

    print(f"\n[1. VALIDAÇÃO NUMÉRICA MULTI-CROMÁTICA]")
    print(f"  Erro máx. quadratura |ΔA|  : {max_quad:.2e}  (limite: {CONSERVATION_TOL:.0e})")
    print(f"  Erro máx. Poynting          : {max_poy:.2e}  (limite: {CONSERVATION_TOL:.0e})")
    print(f"  Erro máx. continuidade E    : {max_E:.2e}")
    print(f"  Resíduo máx. substrato      : {max_sub:.2e}  (limite: 1e-8)")
    print(f"  → Conservação validada em todos os {N_WAVELENGTHS} comprimentos de onda.")

    success_b2 = np.mean([r["success"] for r in b2_runs])
    nfev_b2 = np.mean([r["nfev"] for r in b2_runs])
    print(f"\n[2. CONVERGÊNCIA DO OTIMIZADOR]")
    print(f"  B2   : Taxa sucesso = {success_b2*100:.1f}%, nfev médio = {nfev_b2:.0f}")
    for sigma in SIGMAS:
        sigma_um = sigma * 1e6
        u_runs = [r for r in unit_runs if abs(r["sigma"] - sigma) < 1e-12]
        if not u_runs:
            print(f"  UNIT (σ={sigma_um:.2f}µm): sem execuções válidas.")
            continue
        success_u = np.mean([r["success"] for r in u_runs])
        nfev_u = np.mean([r["nfev"] for r in u_runs])
        print(f"  UNIT (σ={sigma_um:.2f}µm): Taxa = {success_u*100:.1f}%, nfev = {nfev_u:.0f}")

    print(f"\n[3. ÁREAS EFETIVAS DOS KERNELS (∫C(x)dx) - ATENÇÃO: Equalização pode ser quebrada pelo teto físico]")
    print(f"  Teto físico: C(x) ≤ {RECOVERY_CAP}")
    print("-" * 140)
    for sigma in SIGMAS:
        sigma_um = sigma * 1e6
        _, kparams = generate_kernels_for_sigma(np.linspace(0, L, 1000), L, sigma)
        print(f"  σ = {sigma_um:.2f} µm:")
        for kn in ["Frontal", "Central", "Traseiro", "Uniforme"]:
            kp = kparams[kn]
            print(f"    {kn:<10}: Área = {kp['effective_area']*1e6:.4f} µm | cmax = {kp['cmax']:.3f} | c_mean = {kp['c_mean']:.3f}")

    print(f"\n[4. DECOMPOSIÇÃO CAUSAL PAREADA (CORRIGIDA: pareamento explícito por seed)]")
    print(f"    G_rec = <η_B2+C> - <T_B2>     (recuperação passiva)")
    print(f"    G_co  = <η_UNIT> - <η_B2+C>   (ganho de co-design)")
    print(f"    f_co  = G_co / G_total        (fração do ganho pelo co-design)")
    print("-" * 140)

    T_b2 = np.array([r["simulation"]["T"] for r in b2_runs])
    d_C_b2 = np.array([r["simulation"]["d_C"] for r in b2_runs])

    print(f"  B2 (max T):")
    print(f"    <T> = {np.mean(T_b2)*100:.4f}% ± {np.std(T_b2)*100:.4f}%")
    print(f"    <d_C> = {np.mean(d_C_b2):.4f}")
    print("-" * 140)

    header = (
        f"{'Kernel (σ)':<18} | {'G_rec':>8} | {'G_co':>8} | {'G_tot':>8} | {'f_co':>7} | "
        f"{'Δd_C':>7} | {'Γ_C':>7} | {'Wilcox-p':>9} | {'FDR-W':>8} | {'Perm-p':>8} | {'FDR-P':>8}"
    )
    print(header)
    print("-" * 140)

    all_pvalues_wilcox = []
    all_pvalues_perm = []
    all_configs = []

    for sigma in SIGMAS:
        sigma_um = sigma * 1e6
        _, kparams = generate_kernels_for_sigma(np.linspace(0, L, 1000), L, sigma)

        for kernel_name in kparams.keys():
            runs_k = [r for r in unit_runs if r["name"].startswith(f"{kernel_name}_sig{sigma_um:.0f}")]

            eta_unit_list = []
            eta_b2c_list = []
            d_C_unit_list = []
            d_C_b2c_list = []
            rho_rec_list = []

            for r in runs_k:
                seed = r["seed"]
                if seed in b2_plus_c_results[(sigma_um, kernel_name)]:
                    eta_unit_list.append(r["simulation"]["eta_global"])
                    eta_b2c_list.append(b2_plus_c_results[(sigma_um, kernel_name)][seed]["eta_global"])
                    d_C_unit_list.append(r["simulation"]["d_C"])
                    d_C_b2c_list.append(b2_plus_c_results[(sigma_um, kernel_name)][seed]["d_C"])
                    rho_rec_list.append(r["simulation"]["rho_rec"])

            if len(eta_unit_list) < 5:
                print(f"  [aviso] {kernel_name} (σ={sigma_um:.2f}µm): apenas {len(eta_unit_list)} pares válidos, pulando.")
                continue

            eta_unit = np.array(eta_unit_list)
            eta_b2c = np.array(eta_b2c_list)
            d_C_unit = np.array(d_C_unit_list)
            d_C_b2c = np.array(d_C_b2c_list)

            D_eta = eta_unit - eta_b2c
            D_dC = d_C_b2c - d_C_unit

            G_rec = np.mean(eta_b2c) - np.mean(T_b2)
            G_co = np.mean(D_eta)
            G_total = G_rec + G_co
            f_co = G_co / G_total if abs(G_total) > 1e-10 else 0.0
            mean_delta_dC = np.mean(D_dC)
            mean_gamma_C = np.mean(rho_rec_list)  # Γ_C = ρ_rec = média de C ponderada por q

            p_wilcox = wilcoxon_signed_rank_paired(D_eta, alternative='greater')
            p_perm = sign_permutation_test_paired(D_eta, n_permutations=10000, alternative='greater')

            all_pvalues_wilcox.append(p_wilcox)
            all_pvalues_perm.append(p_perm)

            all_configs.append({
                "kernel": kernel_name, "sigma_um": sigma_um,
                "G_rec": G_rec, "G_co": G_co, "G_total": G_total, "f_co": f_co,
                "delta_dC": mean_delta_dC, "gamma_C": mean_gamma_C,
                "p_wilcox": p_wilcox, "p_perm": p_perm
            })

    fdr_wilcox = apply_fdr_correction(all_pvalues_wilcox)
    fdr_perm = apply_fdr_correction(all_pvalues_perm)

    for i, cfg in enumerate(all_configs):
        label = f"{cfg['kernel']} ({cfg['sigma_um']:.2f}µm)"
        print(
            f"{label:<18} | "
            f"{cfg['G_rec']*100:+7.4f} | "
            f"{cfg['G_co']*100:+7.4f} | "
            f"{cfg['G_total']*100:+7.4f} | "
            f"{cfg['f_co']*100:6.1f}% | "
            f"{cfg['delta_dC']:+6.4f} | "
            f"{cfg['gamma_C']:6.3f} | "
            f"{cfg['p_wilcox']:9.2e} | "
            f"{fdr_wilcox[i]:8.2e} | "
            f"{cfg['p_perm']:8.2e} | "
            f"{fdr_perm[i]:8.2e}"
        )

    print("-" * 140)
    print("  Legenda: Γ_C = ρ_rec = média de C(x) ponderada por q_abs | FDR-W = Wilcoxon corrigido | FDR-P = Permutation corrigido")

    n_sig_wilcox = int(np.sum(fdr_wilcox < 0.05)) if len(fdr_wilcox) else 0
    n_sig_perm = int(np.sum(fdr_perm < 0.05)) if len(fdr_perm) else 0
    print(f"\n  [RESUMO FDR] Wilcoxon: {n_sig_wilcox}/{len(all_configs)} | Permutation: {n_sig_perm}/{len(all_configs)} significativos (α=0.05)")

    print(f"\n[5. REORGANIZAÇÃO ESPACIAL (Δd_C = d_C(B2+C) - d_C(UNIT))]")
    print("-" * 140)
    for sigma in SIGMAS:
        sigma_um = sigma * 1e6
        print(f"  σ = {sigma_um:.2f} µm:")
        for kn in ["Frontal", "Central", "Traseiro", "Uniforme"]:
            cfg = next((c for c in all_configs if c["kernel"] == kn and c["sigma_um"] == sigma_um), None)
            if cfg:
                print(f"    {kn:<10}: Δd_C = {cfg['delta_dC']:+.4f} | Γ_C = {cfg['gamma_C']:.3f}")

    if random_samples:
        T_rand = np.array([s["T"] for s in random_samples])
        print(f"\n[6. ISOLAMENTO DO EFEITO DE OTIMIZAÇÃO]")
        print(f"  T médio (aleatório)    = {np.mean(T_rand)*100:.3f}%")
        print(f"  T médio (B2)           = {np.mean(T_b2)*100:.3f}%  → ganho: {(np.mean(T_b2) - np.mean(T_rand))*100:+.3f} pp")
        all_eta = [r["simulation"]["eta_global"] for r in unit_runs]
        print(f"  η_glb médio (UNIT)     = {np.mean(all_eta)*100:.3f}%  → ganho total: {(np.mean(all_eta) - np.mean(T_rand))*100:+.3f} pp")
    else:
        print(f"\n[6. ISOLAMENTO DO EFEITO DE OTIMIZAÇÃO]")
        print("  Nenhuma amostra aleatória válida — pulando esta seção.")

    print("\n" + "=" * 140)
    print("  CONCLUSÃO TÉCNICA (UNIT-001C.1 REVISED v3)")
    print("=" * 140)
    print("  Solver TMM multi-cromático validou conservação de energia com |ΔA| <", f"{CONSERVATION_TOL:.0e}.")
    print("  Pareamento estatístico explícito por seed elimina fragilidade de ordenação.")
    print("  FDR duplo (Wilcoxon + Permutation) controla erro familiar em múltiplas comparações.")
    print("  Γ_C = ρ_rec mede diretamente a média de C(x) ponderada pela absorção.")
    print("  C(x) é função de ponderação pós-processada, não propriedade física retroativa.")
    print("  Se G_co > 0 com p-FDR < 0.05 e Δd_C > 0, há evidência de co-design efetivo.")
    if failed_runs:
        print(f"  ATENÇÃO: {len(failed_runs)} tarefas falharam durante a execução (ver lista acima) e foram excluídas.")
    print("=" * 140)

    return {
        "b2_runs": b2_runs, "unit_runs": unit_runs,
        "random_samples": random_samples,
        "b2_plus_c_results": b2_plus_c_results,
        "all_configs": all_configs, "fdr_wilcox": fdr_wilcox, "fdr_perm": fdr_perm,
        "failed_runs": failed_runs,
    }


if __name__ == "__main__":
    run_benchmark_unit_001c1_revised_v2()
