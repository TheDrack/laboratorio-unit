"""
unit001_constantes.py — constantes do UNIT-001.

Todos os valores vêm de parametros_estudo.json, no mesmo diretório. Nenhum valor é escrito aqui.
Os nomes C_LIGHT, EPS0 e MU0 são da física eletromagnética: o módulo só aceita
tipo_onda = "eletromagnetica". Para outro tipo de onda, o JSON precisa de bloco próprio
(velocidade de propagação do meio), e os solvers correspondentes precisam ser escritos.
"""
import json
import math
from pathlib import Path

import numpy as np

_P = json.loads(Path(__file__).with_name("parametros_estudo.json").read_text(encoding="utf-8"))

if _P.get("tipo_onda") != "eletromagnetica":
    raise NotImplementedError(
        f"tipo_onda={_P.get('tipo_onda')!r}: os solvers do laboratório são eletromagnéticos. "
        f"Para outro tipo de onda, declare o bloco correspondente no JSON."
    )


def _complexo(par):
    return complex(par[0], par[1])


# ---------------------------------------------------------------------------
# 1. FÍSICA ELETROMAGNÉTICA DO VÁCUO (do JSON)
# ---------------------------------------------------------------------------
_F = _P["fisica_eletromagnetica"]
C_LIGHT = float(_F["velocidade_luz_vacuo_m_s"])     # velocidade de fase no vácuo (m/s)
EPS0 = float(_F["permissividade_vacuo_F_m"])
MU0 = 1.0 / (EPS0 * C_LIGHT ** 2)                   # derivada: μ0 = 1/(ε0·c²)
Z0 = float(np.sqrt(MU0 / EPS0))                     # impedância do vácuo (Ω)


# ---------------------------------------------------------------------------
# 2. MATERIAIS (do JSON)
# ---------------------------------------------------------------------------
SI_N = _complexo(_P["silicio"]["n"])
SI_EPS = SI_N ** 2
SI_K_TERMICA = float(_P["silicio"]["k_termica_w_mk"])
SI_RHO = float(_P["silicio"]["rho_kg_m3"])
SI_CP = float(_P["silicio"]["cp_j_kgk"])

AR_N = _complexo(_P["ar"]["n"])
AR_K_TERMICA = float(_P["ar"]["k_termica_w_mk"])

PRESETS_MATERIAIS = {nome: _complexo(v) for nome, v in _P["presets_materiais"].items()}


# ---------------------------------------------------------------------------
# 3. FREQUÊNCIAS, ONDAS E MALHA (do JSON + derivados)
# ---------------------------------------------------------------------------
FREQUENCIES_THZ = tuple(float(f) for f in _P["frequencias_thz"])
FREQUENCIAS_THZ = FREQUENCIES_THZ
F_MIN_HZ = min(FREQUENCIES_THZ) * 1e12
F_MAX_HZ = max(FREQUENCIES_THZ) * 1e12
LAMBDA0_MIN = C_LIGHT / F_MAX_HZ
LAMBDA0_MAX = C_LIGHT / F_MIN_HZ

DX = float(_P["malha"]["dx_m"])
DY = DX
DZ = DX
MONITOR_OFFSET_FRAC = float(_P["monitores"]["offset_frac"])


# ---------------------------------------------------------------------------
# 4. GEOMETRIA CANÔNICA (do JSON)
# ---------------------------------------------------------------------------
NX = int(_P["geometria"]["nx"])
NY = int(_P["geometria"]["ny"])
NZ = int(_P["geometria"]["nz"])
PILLAR_NX = int(_P["geometria"]["pillar_nx"])
PILLAR_NY = int(_P["geometria"]["pillar_ny"])
PILLAR_NZ = int(_P["geometria"]["pillar_nz"])
N_PILLARS = int(_P["geometria"]["n_pillars"])
RANDOM_SEEDS_START = int(_P["geometria"]["random_seeds_start"])
RANDOM_SEEDS_COUNT = int(_P["geometria"]["random_seeds_count"])


# ---------------------------------------------------------------------------
# 5. PARÂMETROS DO ESTUDO (do JSON)
# ---------------------------------------------------------------------------
_E = _P["estudo"]
A_PERIODO = float(_E["a_periodo_m"])
N_RANDOM_BASELINE = int(_E["n_random_baseline"])
N_BATCHES = int(_E["n_batches"])
SEED_BASE_BASELINE = int(_E["seed_base_baseline"])
MAX_CORES = int(_E["max_cores"])
BOUNDS_LO = np.array(_E["bounds_lo"], dtype=float)
BOUNDS_HI = np.array(_E["bounds_hi"], dtype=float)
SEEDS_ALVO = tuple(int(s) for s in _E["seeds_alvo"])
FREQS_ALVO_THZ = tuple(float(f) for f in _E["freqs_alvo_thz"])
PML_NM_ESTUDO = float(_E["pml_nm_estudo"])          # PML em nm (derivada da malha)
BUFFER_NM_ESTUDO = float(_E["buffer_nm_estudo"])    # buffer em nm (>= λ0 pela regra dos monitores)

# PML e buffer em células: derivados dos nomes em nm (múltiplos de 100 nm, válidos em todos os ppw).
NPML_CELLS = round(PML_NM_ESTUDO * 1e-9 / DX)
BUFFER_CELLS = round(BUFFER_NM_ESTUDO * 1e-9 / DX)
if PML_NM_ESTUDO * 1e-9 < LAMBDA0_MIN / abs(SI_N):
    raise ValueError("PML_NM_ESTUDO menor que 1 comprimento de onda no silício (pior caso)")
if BUFFER_NM_ESTUDO * 1e-9 < LAMBDA0_MAX:
    raise ValueError("BUFFER_NM_ESTUDO menor que λ0max (regra dos monitores)")

# PML e buffer em células: derivados dos nomes em nm (múltiplos de 100 nm, válidos em todos os ppw).
if PML_NM_ESTUDO * 1e-9 < LAMBDA0_MIN / abs(SI_N):
    raise ValueError("PML_NM_ESTUDO menor que 1 comprimento de onda no silício (pior caso)")
if BUFFER_NM_ESTUDO * 1e-9 < LAMBDA0_MAX:
    raise ValueError("BUFFER_NM_ESTUDO menor que λ0max (regra dos monitores)")

N_FUNDO_ESTUDO = _complexo(_E["n_fundo"])
N_INCLUSAO_ESTUDO = _complexo(_E["n_inclusao"])
K_FUNDO_ESTUDO = float(_E["k_fundo_w_mk"])
K_INCLUSAO_ESTUDO = float(_E["k_inclusao_w_mk"])
PPW_FDTD = int(_E["ppw_fdtd"])
PPW_VALIDACAO_FDFD3D = int(_E["ppw_validacao_fdfd3d"])
PPW_COMPARADOR_FDFD = int(_E["ppw_comparador_fdfd"])
NPML_COMPARADOR_FDFD = int(_E["npml_comparador_fdfd"])
NX_COMPARADOR_FDFD = int(_E["nx_comparador_fdfd"])
F_REF_HZ = float(_E["f_ref_hz"])
CLOSURE_TOL_ESTUDO = float(_E["closure_tol"])   # fechamento de energia (ver closure_tol_base no JSON)
VALID_N_TESTE = tuple(_complexo(v) for v in _E["valid_n_teste"])
VALID_N_SLAB_TESTE = _complexo(_E["valid_n_slab_teste"])


# ---------------------------------------------------------------------------
# 6. TOLERÂNCIAS NUMÉRICAS (do JSON) — [PENDENTE]: decisão do pesquisador
# ---------------------------------------------------------------------------
_T = _P["tolerancias_pendentes"]
TOL_CONSISTENCIA = float(_T["consistencia_L2"])
TOL_ESCALA = float(_T["escala"])
TOL_RESIDUO_SISTEMA = float(_T["residuo_sistema"])
FATOR_TOL_DISCRETIZACAO = float(_T["fator_tol_discretizacao"])
Q_TESTE_ESCALA = float(_T["q_teste_escala_w_m3"])
ALFA_ESCALA = float(_T["alfa_escala"])
TOL_REL_ZERO = float(_T["rel_zero"])
TOL_K_POSITIVE = float(_T["k_positive"])
TOL_K_CONSISTENCY = float(_T["k_consistency"])
TOL_INVARIANT_REL = float(_T["invariant_rel"])
TOL_SOLVER_RESIDUAL = float(_T["solver_residual"])
TOL_AUTOTEST = float(_T["autotest"])
TOL_SLSQP = float(_T["slsqp"])
SLSQP_MAXITER = int(_T["slsqp_maxiter"])
CUBE_N_AUTOTEST = int(_T["cube_n_autotest"])
TOL_ORDEM_CONVERGENCIA = float(_T["tol_ordem_convergencia"])


# ---------------------------------------------------------------------------
# 7. PRESETS DE VALIDAÇÃO (do JSON)
# ---------------------------------------------------------------------------
_L = _P["lamina_teste"]
LAMINA_TESTE_LAMBDA0 = float(_L["lambda0_m"])
LAMINA_TESTE_N_BG = float(_L["n_bg"])
LAMINA_TESTE_N_SLAB = float(_L["n_slab"])
LAMINA_TESTE_ESPESSURA = float(_L["espessura_m"])
LAMINA_TESTE_NX = int(_L["nx"])

NIVEIS_PPW_CONVERGENCIA = tuple(int(p) for p in _P["convergencia"]["niveis_ppw"])
ORDEM_TEORICA_2A = float(_P["convergencia"]["ordem_teorica"])
LAMBDAS_VARREDURA_CW = tuple(float(l) for l in _P["varredura_cw_lambdas_m"])


# ---------------------------------------------------------------------------
# 8. DERIVADOS
# ---------------------------------------------------------------------------
N_BG = AR_N
N_PILLAR = SI_N
K_SILICON = SI_K_TERMICA
K_AIR = AR_K_TERMICA
K_PILLAR = SI_K_TERMICA
K_BACKGROUND = AR_K_TERMICA
RHO_SI = SI_RHO
CP_SI = SI_CP
LIMIAR_K = math.sqrt(AR_K_TERMICA * SI_K_TERMICA)


# ---------------------------------------------------------------------------
# 9. REGRA DOS MONITORES
# ---------------------------------------------------------------------------
def posicao_monitores(npml_cells: int, buffer_cells: int, nz_struct: int,
                      wavelength: float, dz: float):
    """(z_mon_in, z_mon_out) em índices de célula. Exige buffer >= 2d."""
    n_pad = npml_cells + buffer_cells
    d = int(round(MONITOR_OFFSET_FRAC * wavelength / dz))
    if buffer_cells < 2 * d:
        raise ValueError(f"buffer_cells={buffer_cells} insuficiente: precisa de >= {2 * d} "
                         f"(monitor a {d} células da estrutura e da PML)")
    return n_pad - d, n_pad + nz_struct + d
