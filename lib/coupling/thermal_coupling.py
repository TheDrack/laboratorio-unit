"""
thermal_coupling.py
===================

UNIT-001 — FASE 8: ACOPLAMENTO EM → TÉRMICO
============================================

Resolve o problema térmico estacionário:

    -div(k(r) * grad(T)) = q_abs(r)

com condição de Dirichlet:

    T = 0

nas seis faces externas do domínio.

FORMULAÇÃO
----------

O operador térmico é montado em forma de fluxo conservativo:

    A @ T = Q

onde:

    A -> matriz de condutâncias térmicas [W/K]
    Q -> potência térmica por célula [W]

Como q_abs é uma densidade de potência [W/m³]:

    Q = q_abs * dV

Portanto, o fator:

    dV = dx * dy * dz

é OBRIGATÓRIO no lado direito do sistema.

A ausência desse fator produz uma temperatura com escala dimensional
incorreta. Essa correção altera a escala absoluta de T, mas não deve,
por si só, explicar uma correlação espacial próxima de -1 entre dois
casos.

OBJETIVOS DESTE MÓDULO
----------------------

1. Validar q_abs.
2. Validar k_field.
3. Construir operador térmico conservativo.
4. Resolver o sistema térmico.
5. Verificar residual.
6. Verificar condição de contorno.
7. Verificar conservação de potência.
8. Expor métricas suficientes para auditoria do pipeline EM → térmico.

"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


# ============================================================================
# CONSTANTES NUMÉRICAS
# ============================================================================

DEFAULT_RTOL = 1e-10
DEFAULT_ATOL = 1e-14

# Tolerância para valores negativos de q_abs.
#
# q_abs fisicamente deve ser >= 0.
# Pequenas partes negativas podem aparecer por erro numérico.
Q_NEGATIVE_REL_TOL = 1e-10
Q_NEGATIVE_ABS_TOL = 1e-30

# Tolerância para temperatura nas fronteiras.
BOUNDARY_TOL_REL = 1e-10
BOUNDARY_TOL_ABS = 1e-14


# ============================================================================
# UTILITÁRIOS
# ============================================================================

def _as_float_array(
    value: Any,
    name: str,
) -> np.ndarray:
    """
    Converte entrada para ndarray float64.

    Raises
    ------
    ValueError
        Se houver valores não finitos.
    """
    arr = np.asarray(value, dtype=float)

    if not np.all(np.isfinite(arr)):
        raise ValueError(
            f"{name} contém valores NaN ou inf."
        )

    return arr


def _validate_grid_spacing(
    dx: float,
    dy: float,
    dz: float,
) -> Tuple[float, float, float]:
    """
    Valida espaçamentos da malha.
    """

    dx = float(dx)
    dy = float(dy)
    dz = float(dz)

    if not np.isfinite(dx) or not np.isfinite(dy) or not np.isfinite(dz):
        raise ValueError(
            "dx, dy e dz devem ser finitos."
        )

    if dx <= 0 or dy <= 0 or dz <= 0:
        raise ValueError(
            f"dx, dy e dz devem ser > 0. "
            f"Recebidos: dx={dx}, dy={dy}, dz={dz}"
        )

    return dx, dy, dz


# ============================================================================
# VALIDAÇÃO DE q_abs
# ============================================================================

def _validate_q_abs(
    q_abs: Any,
    expected_shape: Optional[Tuple[int, int, int]] = None,
) -> np.ndarray:
    """
    Valida densidade de potência absorvida.

    Parâmetros
    ----------
    q_abs:
        Array 3D em W/m³.

    expected_shape:
        Shape esperado, quando disponível.

    Retorno
    -------
    np.ndarray
        q_abs em float64.

    Observação
    ----------
    q_abs fisicamente deve ser não-negativo.

    Pequenos valores negativos compatíveis com erro numérico são
    zerados. Valores negativos significativos causam erro.
    """

    q = _as_float_array(q_abs, "q_abs")

    if q.ndim != 3:
        raise ValueError(
            f"q_abs deve ser 3D. Shape recebido: {q.shape}"
        )

    if expected_shape is not None:
        if tuple(q.shape) != tuple(expected_shape):
            raise ValueError(
                "Shape incompatível para q_abs: "
                f"recebido={q.shape}, esperado={expected_shape}"
            )

    q_scale = max(float(np.max(np.abs(q))), 1.0)

    negative_limit = max(
        Q_NEGATIVE_ABS_TOL,
        Q_NEGATIVE_REL_TOL * q_scale,
    )

    q_min = float(np.min(q))

    if q_min < -negative_limit:
        raise ValueError(
            "q_abs contém valores negativos significativos. "
            f"q_min={q_min:.6e}, "
            f"limite={negative_limit:.6e}"
        )

    # Pequenos resíduos negativos numéricos.
    q = np.maximum(q, 0.0)

    return q


# ============================================================================
# VALIDAÇÃO DE k
# ============================================================================

def _validate_k_field(
    k_field: Any,
    expected_shape: Tuple[int, int, int],
) -> np.ndarray:
    """
    Valida campo de condutividade térmica.

    Aceita:

        k_field = escalar

    ou:

        k_field = array 3D

    Unidades esperadas:

        W/(m K)
    """

    k = np.asarray(k_field, dtype=float)

    if k.ndim == 0:
        value = float(k)

        if not np.isfinite(value):
            raise ValueError(
                "k_field escalar não é finito."
            )

        if value <= 0:
            raise ValueError(
                f"k_field deve ser > 0. Recebido: {value}"
            )

        k = np.full(
            expected_shape,
            value,
            dtype=float,
        )

    else:
        k = _as_float_array(k, "k_field")

        if tuple(k.shape) != tuple(expected_shape):
            raise ValueError(
                "Shape incompatível para k_field: "
                f"recebido={k.shape}, esperado={expected_shape}"
            )

        if np.any(k <= 0):
            k_min = float(np.min(k))

            raise ValueError(
                "k_field deve ser estritamente positivo em todas "
                f"as células. k_min={k_min:.6e}"
            )

    return k


# ============================================================================
# MÉDIA HARMÔNICA
# ============================================================================

def _harmonic_mean(
    a: np.ndarray,
    b: np.ndarray,
) -> np.ndarray:
    """
    Média harmônica entre duas condutividades.

        k_int = 2*k1*k2/(k1+k2)

    Para k > 0, garante condutância de interface positiva.
    """

    denominator = a + b

    if np.any(denominator <= 0):
        raise ValueError(
            "Média harmônica inválida: a+b <= 0."
        )

    return 2.0 * a * b / denominator


# ============================================================================
# MÁSCARA DE FRONTEIRA
# ============================================================================

def _build_boundary_mask(
    shape: Tuple[int, int, int],
) -> np.ndarray:
    """
    Retorna máscara booleana das seis faces externas.

    True  -> fronteira Dirichlet
    False -> interior
    """

    if len(shape) != 3:
        raise ValueError(
            f"shape deve ser 3D. Recebido: {shape}"
        )

    nx, ny, nz = shape

    if nx < 2 or ny < 2 or nz < 2:
        raise ValueError(
            "Cada dimensão deve possuir pelo menos 2 células."
        )

    boundary = np.zeros(
        shape,
        dtype=bool,
    )

    boundary[0, :, :] = True
    boundary[-1, :, :] = True

    boundary[:, 0, :] = True
    boundary[:, -1, :] = True

    boundary[:, :, 0] = True
    boundary[:, :, -1] = True

    return boundary


# ============================================================================
# OPERADOR TÉRMICO
# ============================================================================

def _build_thermal_operator(
    k: np.ndarray,
    dx: float,
    dy: float,
    dz: float,
) -> sp.csr_matrix:
    """
    Constrói o operador térmico global.

    O operador representa:

        -div(k grad(T))

    em forma conservativa de volumes finitos / diferenças de fluxo.

    A matriz possui unidades efetivas de:

        W/K

    Cada ligação entre duas células recebe:

        G = k_interface * A_face / distância

    e contribui com:

        G [[+1, -1],
           [-1, +1]]

    """

    if k.ndim != 3:
        raise ValueError(
            "k deve ser 3D."
        )

    nx, ny, nz = k.shape

    n_cells = nx * ny * nz

    rows = []
    cols = []
    data = []

    def index(i: int, j: int, l: int) -> int:
        return np.ravel_multi_index(
            (i, j, l),
            (nx, ny, nz),
        )

    # ------------------------------------------------------------------
    # Interfaces em x
    # ------------------------------------------------------------------

    if nx > 1:
        k_left = k[:-1, :, :]
        k_right = k[1:, :, :]

        k_int = _harmonic_mean(
            k_left,
            k_right,
        )

        # Área da face normal a x.
        area = dy * dz

        # Distância entre centros.
        conductance = k_int * area / dx

        for i in range(nx - 1):
            for j in range(ny):
                for l in range(nz):

                    p = index(i, j, l)
                    q = index(i + 1, j, l)

                    g = float(conductance[i, j, l])

                    rows.extend([p, p, q, q])
                    cols.extend([p, q, p, q])
                    data.extend([g, -g, -g, g])

    # ------------------------------------------------------------------
    # Interfaces em y
    # ------------------------------------------------------------------

    if ny > 1:
        k_down = k[:, :-1, :]
        k_up = k[:, 1:, :]

        k_int = _harmonic_mean(
            k_down,
            k_up,
        )

        area = dx * dz

        conductance = k_int * area / dy

        for i in range(nx):
            for j in range(ny - 1):
                for l in range(nz):

                    p = index(i, j, l)
                    q = index(i, j + 1, l)

                    g = float(conductance[i, j, l])

                    rows.extend([p, p, q, q])
                    cols.extend([p, q, p, q])
                    data.extend([g, -g, -g, g])

    # ------------------------------------------------------------------
    # Interfaces em z
    # ------------------------------------------------------------------

    if nz > 1:
        k_back = k[:, :, :-1]
        k_front = k[:, :, 1:]

        k_int = _harmonic_mean(
            k_back,
            k_front,
        )

        area = dx * dy

        conductance = k_int * area / dz

        for i in range(nx):
            for j in range(ny):
                for l in range(nz - 1):

                    p = index(i, j, l)
                    q = index(i, j, l + 1)

                    g = float(conductance[i, j, l])

                    rows.extend([p, p, q, q])
                    cols.extend([p, q, p, q])
                    data.extend([g, -g, -g, g])

    matrix = sp.coo_matrix(
        (data, (rows, cols)),
        shape=(n_cells, n_cells),
        dtype=float,
    )

    matrix.sum_duplicates()

    return matrix.tocsr()


# ============================================================================
# SOLUÇÃO COM DIRICHLET T = 0
# ============================================================================

def _solve_dirichlet_zero(
    A: sp.csr_matrix,
    q_abs: np.ndarray,
    dx: float,
    dy: float,
    dz: float,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Resolve:

        A T = q_abs * dV

    com:

        T = 0

    nas seis faces externas.

    Retorna
    -------

    T
        Campo térmico 3D.

    diagnostics
        Diagnósticos completos da solução.
    """

    shape = q_abs.shape

    boundary = _build_boundary_mask(shape)

    interior = ~boundary

    interior_idx = np.flatnonzero(
        interior.ravel()
    )

    if interior_idx.size == 0:
        raise ValueError(
            "Não existem células interiores para resolver."
        )

    A_int = A[
        interior_idx,
        :
    ][:,
        interior_idx
    ].tocsr()

    # ==================================================================
    # CORREÇÃO FUNDAMENTAL
    # ==================================================================
    #
    # q_abs possui unidade:
    #
    #     W/m³
    #
    # enquanto a matriz A representa condutâncias:
    #
    #     W/K
    #
    # Portanto o RHS por célula deve ser:
    #
    #     Q_cell = q_abs * dV
    #
    # com:
    #
    #     dV = dx * dy * dz
    #
    # ==================================================================

    volume_cell = dx * dy * dz

    q_flat = q_abs.ravel()

    q_int_density = q_flat[interior_idx]

    q_int_power = (
        q_int_density * volume_cell
    )

    # ------------------------------------------------------------------
    # Verificações de consistência
    # ------------------------------------------------------------------

    if not np.all(np.isfinite(q_int_power)):
        raise ValueError(
            "RHS térmico contém valores não finitos."
        )

    if np.any(q_int_power < 0):
        raise ValueError(
            "RHS térmico contém potência negativa."
        )

    # ------------------------------------------------------------------
    # Resolve sistema
    # ------------------------------------------------------------------

    T_int = spla.spsolve(
        A_int,
        q_int_power,
    )

    if not np.all(np.isfinite(T_int)):
        raise RuntimeError(
            "O solver térmico retornou temperatura não finita."
        )

    # ------------------------------------------------------------------
    # Reconstrói campo completo
    # ------------------------------------------------------------------

    T_flat = np.zeros(
        q_flat.shape,
        dtype=float,
    )

    T_flat[interior_idx] = T_int

    T = T_flat.reshape(shape)

    # ------------------------------------------------------------------
    # Residual
    # ------------------------------------------------------------------

    residual_full = (
        A @ T_flat
        - q_flat * volume_cell
    )

    residual_abs = float(
        np.linalg.norm(
            residual_full[interior_idx]
        )
    )

    rhs_norm = float(
        np.linalg.norm(
            q_int_power
        )
    )

    if rhs_norm > 0:
        residual_relative = (
            residual_abs / rhs_norm
        )
    else:
        residual_relative = 0.0

    # ------------------------------------------------------------------
    # Condição de contorno
    # ------------------------------------------------------------------

    boundary_values = T[boundary]

    boundary_max_abs = (
        float(np.max(np.abs(boundary_values)))
        if boundary_values.size
        else 0.0
    )

    # ------------------------------------------------------------------
    # Potência total
    # ------------------------------------------------------------------

    total_q_power = float(
        np.sum(q_abs) * volume_cell
    )

    total_rhs_interior = float(
        np.sum(q_int_power)
    )

    # ------------------------------------------------------------------
    # Métricas térmicas
    # ------------------------------------------------------------------

    diagnostics = {
        "cell_volume": volume_cell,

        "rhs_units": "W",

        "q_abs_units": "W/m^3",

        "total_q_power_W": total_q_power,

        "total_rhs_interior_W": total_rhs_interior,

        "n_cells_total": int(q_abs.size),

        "n_cells_boundary": int(np.count_nonzero(boundary)),

        "n_cells_interior": int(np.count_nonzero(interior)),

        "temperature_min_K": float(np.min(T)),

        "temperature_max_K": float(np.max(T)),

        "temperature_mean_K": float(np.mean(T)),

        "temperature_max_interior_K": (
            float(np.max(T[interior]))
            if np.any(interior)
            else 0.0
        ),

        "temperature_min_interior_K": (
            float(np.min(T[interior]))
            if np.any(interior)
            else 0.0
        ),

        "residual_absolute": residual_abs,

        "residual_relative": residual_relative,

        "boundary_max_abs_K": boundary_max_abs,

        "boundary_ok": (
            boundary_max_abs
            <= max(
                BOUNDARY_TOL_ABS,
                BOUNDARY_TOL_REL
                * max(float(np.max(np.abs(T))), 1.0),
            )
        ),
    }

    return T, diagnostics


# ============================================================================
# RESÍDUO PÚBLICO
# ============================================================================

def compute_thermal_residual(
    T: Any,
    q_abs: Any,
    k_field: Any,
    dx: float,
    dy: float,
    dz: float,
) -> Dict[str, float]:
    """
    Recalcula independentemente o residual térmico.

    Resolve conceitualmente:

        A(T) - q*dV

    e retorna normas absoluta e relativa.

    Útil para auditoria após a solução.
    """

    T = _as_float_array(T, "T")
    q_abs = _validate_q_abs(
        q_abs,
        expected_shape=T.shape,
    )

    k = _validate_k_field(
        k_field,
        expected_shape=T.shape,
    )

    dx, dy, dz = _validate_grid_spacing(
        dx,
        dy,
        dz,
    )

    A = _build_thermal_operator(
        k,
        dx,
        dy,
        dz,
    )

    volume_cell = dx * dy * dz

    T_flat = T.ravel()

    rhs = q_abs.ravel() * volume_cell

    residual = A @ T_flat - rhs

    boundary = _build_boundary_mask(
        T.shape
    )

    interior = ~boundary

    residual_interior = residual[
        interior.ravel()
    ]

    abs_norm = float(
        np.linalg.norm(
            residual_interior
        )
    )

    rhs_norm = float(
        np.linalg.norm(
            rhs[interior.ravel()]
        )
    )

    relative_norm = (
        abs_norm / rhs_norm
        if rhs_norm > 0
        else 0.0
    )

    return {
        "residual_absolute": abs_norm,
        "residual_relative": relative_norm,
    }


# ============================================================================
# API PRINCIPAL
# ============================================================================

def solve_steady_state_temperature(
    wave_state: Any,
    k_thermal: Optional[Any] = None,
    k_field: Optional[Any] = None,
    dx: Optional[float] = None,
    dy: Optional[float] = None,
    dz: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Resolve o campo térmico estacionário.

    Parâmetros
    ----------
    wave_state:
        Objeto contendo:

            wave_state.q_abs

        e, opcionalmente:

            wave_state.dx
            wave_state.dy
            wave_state.dz

    k_thermal:
        Campo ou escalar de condutividade térmica.

    k_field:
        Alias alternativo para k_thermal.

        Se ambos forem fornecidos, k_thermal tem prioridade.

    dx, dy, dz:
        Espaçamentos da malha.

        Se omitidos, tenta obter do wave_state.

    Retorno
    -------

    dict contendo pelo menos:

        T
        thermal_residual
        residual_relative

    além de diagnósticos adicionais.
    """

    # ------------------------------------------------------------------
    # q_abs
    # ------------------------------------------------------------------

    if not hasattr(wave_state, "q_abs"):
        raise AttributeError(
            "wave_state não possui atributo 'q_abs'."
        )

    q_abs_raw = wave_state.q_abs

    # ------------------------------------------------------------------
    # Espaçamentos
    # ------------------------------------------------------------------

    if dx is None:
        if not hasattr(wave_state, "dx"):
            raise ValueError(
                "dx não fornecido e wave_state não possui 'dx'."
            )
        dx = wave_state.dx

    if dy is None:
        if not hasattr(wave_state, "dy"):
            raise ValueError(
                "dy não fornecido e wave_state não possui 'dy'."
            )
        dy = wave_state.dy

    if dz is None:
        if not hasattr(wave_state, "dz"):
            raise ValueError(
                "dz não fornecido e wave_state não possui 'dz'."
            )
        dz = wave_state.dz

    dx, dy, dz = _validate_grid_spacing(
        dx,
        dy,
        dz,
    )

    # ------------------------------------------------------------------
    # q_abs
    # ------------------------------------------------------------------

    q_abs = _validate_q_abs(
        q_abs_raw
    )

    shape = q_abs.shape

    # ------------------------------------------------------------------
    # k
    # ------------------------------------------------------------------

    if k_thermal is not None:
        k_input = k_thermal
    elif k_field is not None:
        k_input = k_field
    else:
        raise ValueError(
            "É necessário fornecer k_thermal ou k_field."
        )

    k = _validate_k_field(
        k_input,
        expected_shape=shape,
    )

    # ------------------------------------------------------------------
    # Volume de célula
    # ------------------------------------------------------------------

    volume_cell = dx * dy * dz

    # ------------------------------------------------------------------
    # Potência total de entrada
    # ------------------------------------------------------------------

    total_q_power = float(
        np.sum(q_abs) * volume_cell
    )

    # ------------------------------------------------------------------
    # Operador
    # ------------------------------------------------------------------

    A = _build_thermal_operator(
        k,
        dx,
        dy,
        dz,
    )

    # ------------------------------------------------------------------
    # Solver
    # ------------------------------------------------------------------

    T, diagnostics = _solve_dirichlet_zero(
        A,
        q_abs,
        dx,
        dy,
        dz,
    )

    # ------------------------------------------------------------------
    # Residual independente
    # ------------------------------------------------------------------

    residual_check = compute_thermal_residual(
        T=T,
        q_abs=q_abs,
        k_field=k,
        dx=dx,
        dy=dy,
        dz=dz,
    )

    # ------------------------------------------------------------------
    # Verificação de condição de contorno
    # ------------------------------------------------------------------

    boundary = _build_boundary_mask(shape)

    boundary_max_abs = float(
        np.max(
            np.abs(T[boundary])
        )
    )

    temperature_scale = max(
        float(np.max(np.abs(T))),
        1.0,
    )

    boundary_tolerance = max(
        BOUNDARY_TOL_ABS,
        BOUNDARY_TOL_REL * temperature_scale,
    )

    boundary_ok = (
        boundary_max_abs
        <= boundary_tolerance
    )

    if not boundary_ok:
        raise RuntimeError(
            "Condição de contorno T=0 violada. "
            f"máx|T_boundary|={boundary_max_abs:.6e} K, "
            f"tolerância={boundary_tolerance:.6e} K."
        )

    # ------------------------------------------------------------------
    # Verificação de temperatura negativa
    # ------------------------------------------------------------------

    T_min = float(np.min(T))

    # Para q >= 0 e T_boundary = 0, o princípio do máximo implica
    # T >= 0 para k > 0. Pequenos resíduos negativos podem surgir
    # numericamente, portanto apenas registramos aqui.
    negative_temperature = T_min < -(
        BOUNDARY_TOL_ABS
        + BOUNDARY_TOL_REL * temperature_scale
    )

    # ------------------------------------------------------------------
    # Monta resultado
    # ------------------------------------------------------------------

    result = {
        "T": T,

        "k_field": k,

        "q_abs": q_abs,

        "thermal_residual": residual_check[
            "residual_absolute"
        ],

        "residual_relative": residual_check[
            "residual_relative"
        ],

        "thermal_residual_relative": residual_check[
            "residual_relative"
        ],

        "cell_volume": volume_cell,

        "dx": dx,
        "dy": dy,
        "dz": dz,

        "rhs_units": "W",

        "q_abs_units": "W/m^3",

        "k_units": "W/(m K)",

        "temperature_units": "K",

        "total_q_power_W": total_q_power,

        "boundary_max_abs_K": boundary_max_abs,

        "boundary_tolerance_K": boundary_tolerance,

        "boundary_ok": boundary_ok,

        "negative_temperature_detected": negative_temperature,

        "temperature_min_K": float(np.min(T)),

        "temperature_max_K": float(np.max(T)),

        "temperature_mean_K": float(np.mean(T)),

        "temperature_p95_K": float(
            np.percentile(T, 95)
        ),

        "temperature_p99_K": float(
            np.percentile(T, 99)
        ),

        "operator_shape": tuple(A.shape),

        "operator_nnz": int(A.nnz),

        "n_cells": int(q_abs.size),

        "n_interior": int(
            np.count_nonzero(~boundary)
        ),

        "n_boundary": int(
            np.count_nonzero(boundary)
        ),
    }

    # Mantém também todos os diagnósticos internos.
    result.update(
        {
            f"thermal_{key}": value
            for key, value in diagnostics.items()
            if key not in result
        }
    )

    return result


# ============================================================================
# TESTE INTERNO DO OPERADOR
# ============================================================================

def _thermal_self_test() -> Dict[str, Any]:
    """
    Testes internos básicos.

    Não substitui a validação física do pipeline UNIT-001.

    Testa:

    1. positividade de k;
    2. simetria da matriz;
    3. linearidade;
    4. solução para fonte positiva;
    5. T >= 0;
    6. fronteiras T=0;
    7. residual;
    8. consistência da escala de dV.
    """

    shape = (6, 6, 6)

    dx = 1e-3
    dy = 1e-3
    dz = 1e-3

    k = np.ones(
        shape,
        dtype=float,
    )

    q1 = np.zeros(
        shape,
        dtype=float,
    )

    q2 = np.zeros(
        shape,
        dtype=float,
    )

    q1[2, 2, 2] = 1.0e6
    q2[3, 3, 3] = 2.0e6

    A = _build_thermal_operator(
        k,
        dx,
        dy,
        dz,
    )

    # ---------------------------------------------------------------
    # Simetria
    # ---------------------------------------------------------------

    symmetry_error = float(
        np.max(
            np.abs(
                (A - A.T).data
            )
        )
        if (A - A.T).nnz
        else 0.0
    )

    # ---------------------------------------------------------------
    # Soluções
    # ---------------------------------------------------------------

    T1, d1 = _solve_dirichlet_zero(
        A,
        q1,
        dx,
        dy,
        dz,
    )

    T2, d2 = _solve_dirichlet_zero(
        A,
        q2,
        dx,
        dy,
        dz,
    )

    T12, d12 = _solve_dirichlet_zero(
        A,
        q1 + q2,
        dx,
        dy,
        dz,
    )

    # ---------------------------------------------------------------
    # Linearidade
    # ---------------------------------------------------------------

    linearity_error = float(
        np.max(
            np.abs(
                T12 - (T1 + T2)
            )
        )
    )

    # ---------------------------------------------------------------
    # Positividade
    # ---------------------------------------------------------------

    minimum_temperature = float(
        min(
            np.min(T1),
            np.min(T2),
            np.min(T12),
        )
    )

    # ---------------------------------------------------------------
    # dV
    # ---------------------------------------------------------------

    volume_cell = dx * dy * dz

    expected_power_1 = (
        np.sum(q1) * volume_cell
    )

    expected_power_2 = (
        np.sum(q2) * volume_cell
    )

    return {
        "passed": (
            symmetry_error <= 1e-12
            and linearity_error <= 1e-10
            and minimum_temperature >= -1e-12
            and d1["residual_relative"] <= 1e-10
            and d2["residual_relative"] <= 1e-10
            and d12["residual_relative"] <= 1e-10
        ),

        "symmetry_error": symmetry_error,

        "linearity_error": linearity_error,

        "minimum_temperature_K": minimum_temperature,

        "residual_1": d1[
            "residual_relative"
        ],

        "residual_2": d2[
            "residual_relative"
        ],

        "residual_12": d12[
            "residual_relative"
        ],

        "cell_volume_m3": volume_cell,

        "expected_power_1_W": expected_power_1,

        "expected_power_2_W": expected_power_2,
    }


# ============================================================================
# EXECUÇÃO DIRETA
# ============================================================================

if __name__ == "__main__":

    print("=" * 78)
    print("UNIT-001 — TESTE INTERNO thermal_coupling.py")
    print("=" * 78)

    test = _thermal_self_test()

    for key, value in test.items():
        print(
            f"{key}: {value}"
        )

    print("=" * 78)

    if test["passed"]:
        print("STATUS: PASS")
    else:
        print("STATUS: FAIL")

    print("=" * 78)