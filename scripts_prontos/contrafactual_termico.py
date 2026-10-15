"""
UNIT-001.5 | MODULAÇÃO TÉRMICA CONTRAFACTUAL
VERSÃO V4.4 — REVISÃO: constantes de lib/geometry/unit001_fisica.py e de
lib/geometry/unit001_dataset_66_cases.py; tolerâncias relativas à escala de q;
busca de NPZ com o nome que o extrator grava.

OBJETIVO
--------
Testar se a temperatura T(r) muda quando a distribuição espacial da fonte
térmica q(r) é modificada enquanto invariantes físicos são progressivamente
preservados.

EXPERIMENTOS
------------
EXP0 ORIGINAL                       q original extraído do FDFD.
EXP1 UNIFORME_GLOBAL                mesma potência total; q uniforme no material.
EXP2 UNIFORME_POR_PILAR             mesma potência de cada pilar; q uniforme dentro dele.
EXP3 MESMA_POTENCIA_CENTROIDE       preserva, por pilar, sum(q), sum(q*x), sum(q*y), sum(q*z)
                                    e minimiza ||q - q_uniforme||² com q >= 0.

SOLVER
------
-div(k grad T) = q, T = 0 nas seis faces externas. Stencil de 7 pontos,
condutividade harmônica nas interfaces, Dirichlet forte.

PILARES
-------
Identificados por exact-cover da projeção XY (não por componentes conexos,
pois pilares que compartilham uma face formam um único componente 6-conexo).
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import spsolve


# ======================================================================
# FONTES ÚNICAS
# ======================================================================

from lib.geometry.unit001_constantes import (
    DX,
    K_BACKGROUND,
    K_PILLAR,
    LIMIAR_K,
)

from lib.geometry.unit001_dataset_66_cases import (
    NX as STRUCT_NX,
    NY as STRUCT_NY,
    NZ as STRUCT_NZ,
    PILLAR_NX,
    PILLAR_NY,
    PILLAR_NZ,
    N_PILLARS,
    RANDOM_SEEDS,
    FREQUENCIES_THZ,
)
from lib.geometry.unit001_constantes import (SEEDS_ALVO, FREQS_ALVO_THZ, TOL_REL_ZERO, TOL_K_POSITIVE, TOL_K_CONSISTENCY, TOL_INVARIANT_REL, TOL_SOLVER_RESIDUAL, TOL_AUTOTEST, TOL_SLSQP, SLSQP_MAXITER, CUBE_N_AUTOTEST)


# ======================================================================
# CONFIGURAÇÃO
# ======================================================================

VERSION = "V4.4"

BASE_DIR = Path(
    "/content/drive/MyDrive/Colab Notebooks/"
    "UNIT-001_AGENTES/dados/UNIT001"
)

CASES_DIR = BASE_DIR / "resultados" / "extrator" / "cases"

OUTPUT_JSON = BASE_DIR / "modulacao_v4_4_resultados.json"

# Subconjunto de casos processados (validado contra o dataset abaixo).
SEEDS = SEEDS_ALVO
FREQUENCIES_SELECIONADAS_THZ = FREQS_ALVO_THZ

for _s in SEEDS:
    if _s not in RANDOM_SEEDS:
        raise ValueError(f"seed {_s} não pertence ao dataset RANDOM_SEEDS")
for _f in FREQUENCIES_SELECIONADAS_THZ:
    if _f not in FREQUENCIES_THZ:
        raise ValueError(f"frequência {_f} não pertence ao dataset FREQUENCIES_THZ")

PILLAR_CELLS = PILLAR_NX * PILLAR_NY * PILLAR_NZ
TOTAL_MATERIAL_CELLS = N_PILLARS * PILLAR_CELLS

# Tolerâncias. Os testes de sinal e de nulo comparam com a escala de q
# (max |q|), não com um valor absoluto, pois q está em W/m³ e pode ter
# ordem de grandeza de 10^13 a 10^15.

# Se True, T armazenado no NPZ é auditado contra o T reconstruído.
AUDIT_STORED_T = True
# Se True, discrepância grande entre T armazenado e reconstruído invalida o caso.
STRICT_STORED_T = False

EXPERIMENTS = (
    "EXP0_ORIGINAL",
    "EXP1_UNIFORME_GLOBAL",
    "EXP2_UNIFORME_POR_PILAR",
    "EXP3_MESMA_POTENCIA_CENTROIDE_POR_PILAR",
)


# ======================================================================
# EXCEÇÕES
# ======================================================================

class ValidationError(RuntimeError):
    """Falha de validação científica/numérica."""


# ======================================================================
# UTILITÁRIOS
# ======================================================================

def fail(msg: str) -> None:
    raise ValidationError(msg)


def q_scale(q: np.ndarray) -> float:
    """Escala de referência de q: max |q|, com piso para evitar divisão por zero."""
    return max(float(np.max(np.abs(q))) if q.size else 0.0, 1e-300)


def as_scalar(value: Any, default: Any = None) -> Any:
    """Converte escalares armazenados em NPZ em tipos Python quando possível."""
    if value is None:
        return default
    arr = np.asarray(value)
    if arr.ndim == 0 or arr.size == 1:
        item = arr.reshape(-1)[0].item()
        if isinstance(item, bytes):
            try:
                return item.decode("utf-8")
            except Exception:
                return str(item)
        return item
    return value


def finite_or_fail(name: str, x: np.ndarray) -> None:
    if not np.all(np.isfinite(x)):
        n_bad = int(np.count_nonzero(~np.isfinite(x)))
        fail(f"{name}: {n_bad} valores NaN/Inf encontrados.")


def max_abs(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.max(np.abs(x)))


def array_rel_error(a: np.ndarray, b: np.ndarray, floor: float = 1e-30) -> float:
    """Erro relativo baseado na norma infinito."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        return float("inf")
    denom = max(float(np.max(np.abs(b))), floor)
    return float(np.max(np.abs(a - b)) / denom)


def relative_difference(a: float, b: float, floor: float = 1e-30) -> float:
    return abs(a - b) / max(abs(b), floor)


def json_safe(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, np.ndarray):
        if np.iscomplexobj(obj):
            return {"real": np.asarray(obj.real).tolist(), "imag": np.asarray(obj.imag).tolist()}
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


def salvar_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(json_safe(data), f, indent=2, ensure_ascii=False, allow_nan=False)
    tmp.replace(path)


# ======================================================================
# DATACLASS
# ======================================================================

@dataclass
class Caso:
    seed: int
    freq_thz: float
    path: Path

    q_abs_thermal_full: np.ndarray
    q_raw_full: np.ndarray | None
    k_full: np.ndarray
    T_original_full: np.ndarray | None

    q_struct: np.ndarray
    geom_struct: np.ndarray
    k_struct: np.ndarray

    z_struct_start: int
    z_struct_end: int

    dx: float
    dy: float
    dz: float
    dV: float

    geometry_hash: str | None
    positions_hash: str | None
    schema_version: str | None

    q_struct_source: str


# ======================================================================
# DESCOBERTA DE CASES
# ======================================================================

def localizar_case(seed: int, freq_thz: float) -> Path:
    """
    Localiza o NPZ com o nome que o extrator grava:
    RANDOM_seed_{seed}_{freq:.0f}THz.npz
    """
    freq_txt = f"{freq_thz:.0f}"
    candidato = CASES_DIR / f"RANDOM_seed_{seed}_{freq_txt}THz.npz"
    if candidato.exists():
        return candidato
    raise FileNotFoundError(
        f"NPZ não encontrado para seed={seed}, freq={freq_thz} THz em {CASES_DIR}: "
        f"esperado {candidato.name}"
    )


# ======================================================================
# CARREGAMENTO
# ======================================================================

def carregar_caso(seed: int, freq_thz: float) -> Caso:

    path = localizar_case(seed, freq_thz)

    with np.load(path, allow_pickle=False) as data:

        required = ["q_abs_thermal", "k_field", "geom_struct", "dx", "dy", "dz",
                    "z_struct_start", "z_struct_end"]
        missing = [key for key in required if key not in data]
        if missing:
            fail(f"{path.name}: campos obrigatórios ausentes: {missing}")

        q_full = np.asarray(data["q_abs_thermal"], dtype=float)
        k_full = np.asarray(data["k_field"], dtype=float)
        geom = np.asarray(data["geom_struct"], dtype=bool)

        if q_full.ndim != 3:
            fail(f"{path.name}: q_abs_thermal não é 3D: {q_full.shape}")
        if k_full.shape != q_full.shape:
            fail(f"{path.name}: k_field {k_full.shape} != q_abs_thermal {q_full.shape}")
        if geom.shape != (STRUCT_NX, STRUCT_NY, STRUCT_NZ):
            fail(f"{path.name}: geom_struct={geom.shape}; esperado "
                 f"{(STRUCT_NX, STRUCT_NY, STRUCT_NZ)}")

        z0 = int(as_scalar(data["z_struct_start"]))
        z1 = int(as_scalar(data["z_struct_end"]))

        if not (0 <= z0 < z1 <= q_full.shape[2]):
            fail(f"{path.name}: intervalo estrutural inválido: [{z0}, {z1}) para NZ={q_full.shape[2]}")

        dx = float(as_scalar(data["dx"]))
        dy = float(as_scalar(data["dy"]))
        dz = float(as_scalar(data["dz"]))

        if not all(np.isfinite([dx, dy, dz])):
            fail(f"{path.name}: dx/dy/dz contém NaN/Inf.")
        if dx <= 0 or dy <= 0 or dz <= 0:
            fail(f"{path.name}: espaçamentos devem ser positivos.")

        dV = dx * dy * dz

        if "q_abs_struct" in data:
            q_struct_stored = np.asarray(data["q_abs_struct"], dtype=float)
            q_struct_slice = q_full[:, :, z0:z1]

            if q_struct_stored.shape != q_struct_slice.shape:
                fail(f"{path.name}: q_abs_struct={q_struct_stored.shape}, slice={q_struct_slice.shape}")

            err = array_rel_error(q_struct_stored, q_struct_slice)
            if err > TOL_REL_ZERO:
                fail(f"{path.name}: q_abs_struct diverge do slice de q_abs_thermal: rel={err:.3e}")

            q_struct = q_struct_stored
            q_source = "q_abs_struct_validated"
        else:
            q_struct = q_full[:, :, z0:z1].copy()
            q_source = "q_abs_thermal_slice"

        if "k_struct" in data:
            k_struct_stored = np.asarray(data["k_struct"], dtype=float)
            k_slice = k_full[:, :, z0:z1]

            if k_struct_stored.shape != k_slice.shape:
                fail(f"{path.name}: k_struct={k_struct_stored.shape}, slice={k_slice.shape}")

            err = array_rel_error(k_struct_stored, k_slice)
            if err > TOL_K_CONSISTENCY:
                fail(f"{path.name}: k_struct diverge de k_field slice: rel={err:.3e}")

            k_struct = k_struct_stored
        else:
            k_struct = k_full[:, :, z0:z1].copy()

        q_raw = None
        if "q_abs_raw" in data:
            q_raw = np.asarray(data["q_abs_raw"], dtype=float)
            if q_raw.shape != q_full.shape:
                fail(f"{path.name}: q_abs_raw={q_raw.shape} != q_abs_thermal={q_full.shape}")

        T_original = None
        if "T" in data:
            T_original = np.asarray(data["T"], dtype=float)
            if T_original.shape != q_full.shape:
                fail(f"{path.name}: T={T_original.shape} != domínio={q_full.shape}")

        geometry_hash = str(as_scalar(data["geometry_hash"])) if "geometry_hash" in data else None
        positions_hash = str(as_scalar(data["positions_hash"])) if "positions_hash" in data else None
        schema_version = str(as_scalar(data["dataset_schema_version"])) \
            if "dataset_schema_version" in data else None

    caso = Caso(
        seed=seed,
        freq_thz=float(freq_thz),
        path=path,
        q_abs_thermal_full=q_full,
        q_raw_full=q_raw,
        k_full=k_full,
        T_original_full=T_original,
        q_struct=q_struct,
        geom_struct=geom,
        k_struct=k_struct,
        z_struct_start=z0,
        z_struct_end=z1,
        dx=dx,
        dy=dy,
        dz=dz,
        dV=dV,
        geometry_hash=geometry_hash,
        positions_hash=positions_hash,
        schema_version=schema_version,
        q_struct_source=q_source,
    )

    validar_caso(caso)
    return caso


# ======================================================================
# VALIDAÇÃO DO CASO
# ======================================================================

def validar_caso(caso: Caso) -> None:

    q = caso.q_abs_thermal_full
    k = caso.k_full
    geom = caso.geom_struct
    qs = caso.q_struct
    ks = caso.k_struct

    for name, arr in (("q_abs_thermal", q), ("k_field", k), ("q_abs_struct", qs), ("k_struct", ks)):
        finite_or_fail(name, arr)

    scale = q_scale(q)

    if np.min(q) < -TOL_REL_ZERO * scale:
        fail(f"seed={caso.seed}: q_abs_thermal contém valores negativos. min={np.min(q):.6e}")
    if np.min(qs) < -TOL_REL_ZERO * scale:
        fail(f"seed={caso.seed}: q_struct contém valores negativos. min={np.min(qs):.6e}")

    if np.min(k) <= TOL_K_POSITIVE:
        fail(f"seed={caso.seed}: k_field não é estritamente positivo. min={np.min(k):.6e}")
    if np.min(ks) <= TOL_K_POSITIVE:
        fail(f"seed={caso.seed}: k_struct não é estritamente positivo. min={np.min(ks):.6e}")

    # q deve estar contido no intervalo estrutural z0:z1.
    z0 = caso.z_struct_start
    z1 = caso.z_struct_end

    outside_z = np.concatenate([q[:, :, :z0].ravel(), q[:, :, z1:].ravel()])
    if outside_z.size:
        max_outside_z = float(np.max(np.abs(outside_z)))
        if max_outside_z > TOL_REL_ZERO * scale:
            fail(f"seed={caso.seed}: q_abs_thermal não é zero fora do intervalo estrutural. "
                 f"max={max_outside_z:.6e}")

    # q fora da máscara material deve ser zero.
    if qs.shape != geom.shape:
        fail(f"seed={caso.seed}: q_struct={qs.shape} != geom_struct={geom.shape}")

    q_outside_material = qs[~geom]
    if q_outside_material.size:
        max_outside_material = float(np.max(np.abs(q_outside_material)))
        if max_outside_material > TOL_REL_ZERO * scale:
            fail(f"seed={caso.seed}: q_struct possui absorção fora da máscara material. "
                 f"max={max_outside_material:.6e}")

    # k: fora do material = K_BACKGROUND; dentro = K_PILLAR (classificação por LIMIAR_K).
    k_background = ks[~geom]
    k_material = ks[geom]

    if k_background.size:
        err_bg = float(np.max(np.abs(k_background - K_BACKGROUND)))
        if err_bg > TOL_K_CONSISTENCY * max(K_BACKGROUND, 1e-30):
            fail(f"seed={caso.seed}: k fora do material não coincide com K_BACKGROUND. erro={err_bg:.6e}")

    if k_material.size:
        if np.any(k_material < LIMIAR_K):
            fail(f"seed={caso.seed}: material possui k abaixo do limiar LIMIAR_K. "
                 f"min_material={np.min(k_material):.6e}")

    n_material = int(np.count_nonzero(geom))
    if n_material != TOTAL_MATERIAL_CELLS:
        fail(f"seed={caso.seed}: número de células materiais={n_material}; esperado={TOTAL_MATERIAL_CELLS}")


# ======================================================================
# IDENTIFICAÇÃO ROBUSTA DOS PILARES (exact-cover XY)
# ======================================================================

def identificar_pilares(geom: np.ndarray) -> List[np.ndarray]:
    """
    Identifica os pilares PILLAR_NX x PILLAR_NY x PILLAR_NZ por exact-cover.
    Não usa componentes conexos: pilares adjacentes por face formam um único
    componente 6-conexo.
    """
    geom = np.asarray(geom, dtype=bool)

    if geom.ndim != 3:
        fail(f"geom_struct deve ser 3D; shape={geom.shape}")

    nx, ny, nz = geom.shape
    if (nx, ny, nz) != (STRUCT_NX, STRUCT_NY, STRUCT_NZ):
        fail(f"geom_struct inesperada: {geom.shape}; esperado={(STRUCT_NX, STRUCT_NY, STRUCT_NZ)}")

    material_positions = np.argwhere(geom)
    if len(material_positions) != TOTAL_MATERIAL_CELLS:
        fail(f"Geometria incompatível com {N_PILLARS} pilares {PILLAR_NX}x{PILLAR_NY}x{PILLAR_NZ}: "
             f"{len(material_positions)} células.")

    footprint = np.any(geom, axis=2)
    n_footprint = int(np.count_nonzero(footprint))
    expected_footprint = N_PILLARS * PILLAR_NX * PILLAR_NY
    if n_footprint != expected_footprint:
        fail(f"Footprint XY possui {n_footprint} células; esperado={expected_footprint}")

    # Todas as células XY materiais devem ter exatamente as mesmas camadas Z.
    z_sets = {}
    for x, y in np.argwhere(footprint):
        z_sets[(int(x), int(y))] = np.flatnonzero(geom[x, y, :])

    primeiro_zs = next(iter(z_sets.values()))
    if len(primeiro_zs) != PILLAR_NZ:
        fail(f"Extensão Z incompatível com pilar: {len(primeiro_zs)} camadas.")

    z0 = int(primeiro_zs[0])
    z1 = int(primeiro_zs[-1]) + 1
    if z1 - z0 != PILLAR_NZ:
        fail(f"Extensão Z incompatível: [{z0},{z1})")

    for xy, zs in z_sets.items():
        if len(zs) != PILLAR_NZ:
            fail(f"Célula {xy} possui {len(zs)} camadas Z; esperado={PILLAR_NZ}")
        if not np.array_equal(zs, primeiro_zs):
            fail("Os pilares não compartilham a mesma extensão Z.")
        if not np.all(np.diff(zs) == 1):
            fail(f"Camadas Z não contíguas em {xy}: {zs}")

    footprint_set = {(int(x), int(y)) for x, y in np.argwhere(footprint)}

    candidates = []
    for x0 in range(nx - PILLAR_NX + 1):
        for y0 in range(ny - PILLAR_NY + 1):
            cells = frozenset(
                (x, y)
                for x in range(x0, x0 + PILLAR_NX)
                for y in range(y0, y0 + PILLAR_NY)
            )
            if cells <= footprint_set:
                candidates.append((x0, y0, cells))

    if not candidates:
        fail(f"Nenhum retângulo {PILLAR_NX}x{PILLAR_NY} encontrado no footprint.")

    containing = {cell: [] for cell in footprint_set}
    for candidate in candidates:
        _, _, cells = candidate
        for cell in cells:
            containing[cell].append(candidate)

    solution: List[Tuple[int, int, frozenset]] = []

    def backtrack(chosen: List[Tuple[int, int, frozenset]], covered: set) -> bool:
        if len(chosen) == N_PILLARS:
            return covered == footprint_set

        remaining = footprint_set - covered
        if not remaining:
            return False

        anchor = min(remaining)
        for candidate in containing.get(anchor, []):
            x0, y0, cells = candidate
            if cells & covered:
                continue
            if not cells <= footprint_set:
                continue
            chosen.append(candidate)
            if backtrack(chosen, covered | set(cells)):
                return True
            chosen.pop()
        return False

    chosen: List[Tuple[int, int, frozenset]] = []
    if not backtrack(chosen, set()):
        fail(f"Não foi possível decompor a geometria em {N_PILLARS} pilares {PILLAR_NX}x{PILLAR_NY}.")
    solution = chosen

    pilares = []
    for x0, y0, _ in solution:
        coords = np.array(
            [(x, y, z)
             for x in range(x0, x0 + PILLAR_NX)
             for y in range(y0, y0 + PILLAR_NY)
             for z in range(z0, z1)],
            dtype=int,
        )
        if coords.shape != (PILLAR_CELLS, 3):
            fail(f"Pilar {x0},{y0}: {coords.shape[0]} células; esperado={PILLAR_CELLS}")
        pilares.append(coords)

    pilares.sort(key=lambda c: (int(np.min(c[:, 0])), int(np.min(c[:, 1])), int(np.min(c[:, 2]))))

    # Auditoria final: a união dos pilares reproduz exatamente geom.
    combined = np.zeros_like(geom, dtype=bool)
    for i, coords in enumerate(pilares):
        if np.any(combined[coords[:, 0], coords[:, 1], coords[:, 2]]):
            fail(f"Pilar {i}: sobreposição detectada.")
        combined[coords[:, 0], coords[:, 1], coords[:, 2]] = True

    if not np.array_equal(combined, geom):
        fail("A união dos pilares não reproduz exatamente geom_struct.")

    return pilares


# ======================================================================
# INFORMAÇÕES DOS PILARES
# ======================================================================

def resumo_pilares(pilares: Sequence[np.ndarray]) -> List[Dict[str, Any]]:
    resultado = []
    for i, coords in enumerate(pilares):
        resultado.append({
            "id": i + 1,
            "n_cells": int(len(coords)),
            "bbox": {
                "x0": int(np.min(coords[:, 0])), "x1": int(np.max(coords[:, 0])) + 1,
                "y0": int(np.min(coords[:, 1])), "y1": int(np.max(coords[:, 1])) + 1,
                "z0": int(np.min(coords[:, 2])), "z1": int(np.max(coords[:, 2])) + 1,
            },
            "centroide_indices": [
                float(np.mean(coords[:, 0])),
                float(np.mean(coords[:, 1])),
                float(np.mean(coords[:, 2])),
            ],
        })
    return resultado


# ======================================================================
# MÉTRICAS DE q
# ======================================================================

def q_total(q: np.ndarray, dV: float) -> float:
    return float(np.sum(q) * dV)


def momento_q(q: np.ndarray, dV: float) -> np.ndarray:
    """Primeiro momento discreto em índices de célula, escalado por dV."""
    nx, ny, nz = q.shape
    ix = np.arange(nx, dtype=float)[:, None, None]
    iy = np.arange(ny, dtype=float)[None, :, None]
    iz = np.arange(nz, dtype=float)[None, None, :]
    return np.array([
        np.sum(q * ix) * dV,
        np.sum(q * iy) * dV,
        np.sum(q * iz) * dV,
    ], dtype=float)


def centroide_q(q: np.ndarray) -> np.ndarray:
    total = float(np.sum(q))
    if total <= 0:
        return np.array([np.nan, np.nan, np.nan], dtype=float)
    nx, ny, nz = q.shape
    ix = np.arange(nx, dtype=float)[:, None, None]
    iy = np.arange(ny, dtype=float)[None, :, None]
    iz = np.arange(nz, dtype=float)[None, None, :]
    return np.array([
        np.sum(q * ix) / total,
        np.sum(q * iy) / total,
        np.sum(q * iz) / total,
    ], dtype=float)


# ======================================================================
# CONSTRUÇÃO DOS EXPERIMENTOS
# ======================================================================

def experimento_uniforme_global(q_original: np.ndarray, mask: np.ndarray) -> np.ndarray:
    q = np.zeros_like(q_original, dtype=float)
    material = int(np.count_nonzero(mask))
    if material <= 0:
        fail("EXP1: máscara material vazia.")
    total = float(np.sum(q_original[mask]))
    q[mask] = total / material
    return q


def experimento_uniforme_por_pilar(q_original: np.ndarray, pilares: Sequence[np.ndarray]) -> np.ndarray:
    q = np.zeros_like(q_original, dtype=float)
    for pilar in pilares:
        valores = q_original[pilar[:, 0], pilar[:, 1], pilar[:, 2]]
        total = float(np.sum(valores))
        q[pilar[:, 0], pilar[:, 1], pilar[:, 2]] = total / len(pilar)
    return q


def experimento_mesma_potencia_centroide(
    q_original: np.ndarray,
    pilares: Sequence[np.ndarray],
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    Por pilar resolve min ||q - u||² sujeito a:
        sum(q) = sum(q0); sum(q*x) = sum(q0*x); sum(q*y) = sum(q0*y);
        sum(q*z) = sum(q0*z); q >= 0.
    Problema convexo: qualquer ótimo é global.
    """
    q = np.zeros_like(q_original, dtype=float)
    auditoria = []

    for pilar_id, coords in enumerate(pilares):

        n = len(coords)
        if n != PILLAR_CELLS:
            fail(f"EXP3: pilar {pilar_id+1} possui {n} células; esperado={PILLAR_CELLS}")

        q0 = q_original[coords[:, 0], coords[:, 1], coords[:, 2]].astype(float)

        if np.any(q0 < -TOL_REL_ZERO * q_scale(q_original)):
            fail(f"EXP3: q original negativo no pilar {pilar_id+1}.")

        coords_phys = coords.astype(float)

        # linha 0 = potência; linhas 1..3 = momentos x, y, z
        A = np.vstack([
            np.ones(n),
            coords_phys[:, 0],
            coords_phys[:, 1],
            coords_phys[:, 2],
        ])

        b = A @ q0
        total = float(b[0])

        if total < -TOL_REL_ZERO * q_scale(q_original):
            fail(f"EXP3: potência negativa no pilar {pilar_id+1}.")

        # q0 é factível (q0 >= 0) e serve de ponto inicial.
        x0 = q0.copy() if np.min(q0) >= 0 else np.maximum(q0, 0.0)

        u = np.full(n, total / n, dtype=float)

        def objective(x):
            d = x - u
            return 0.5 * float(np.dot(d, d))

        def gradient(x):
            return x - u

        constraints = [LinearConstraint(A, b, b)]
        bounds = Bounds(np.zeros(n), np.full(n, np.inf))

        result = minimize(
            objective,
            x0,
            jac=gradient,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": TOL_SLSQP, "maxiter": SLSQP_MAXITER, "disp": False},
        )

        if not result.success:
            fail(f"EXP3: SLSQP falhou no pilar {pilar_id+1}: {result.message}")

        x = np.asarray(result.x, dtype=float)
        finite_or_fail(f"EXP3 pilar {pilar_id+1}", x)

        if np.min(x) < -TOL_REL_ZERO * q_scale(q_original):
            fail(f"EXP3: solução negativa no pilar {pilar_id+1}: min={np.min(x):.6e}")

        residual_constraints = A @ x - b
        max_constraint_error = float(np.max(np.abs(residual_constraints)))
        scale_constraints = max(float(np.max(np.abs(b))), 1e-30)
        rel_constraint_error = max_constraint_error / scale_constraints

        if rel_constraint_error > TOL_INVARIANT_REL:
            fail(f"EXP3: invariantes não preservados no pilar {pilar_id+1}: "
                 f"rel={rel_constraint_error:.3e}")

        q[coords[:, 0], coords[:, 1], coords[:, 2]] = x

        auditoria.append({
            "pillar": pilar_id + 1,
            "success": bool(result.success),
            "iterations": int(getattr(result, "nit", -1)),
            "objective": float(result.fun),
            "constraint_max_abs": max_constraint_error,
            "constraint_max_rel": rel_constraint_error,
            "q_min": float(np.min(x)),
            "q_max": float(np.max(x)),
            "power_original_index_sum": float(b[0]),
            "power_new_index_sum": float(np.sum(x)),
        })

    return q, auditoria


def construir_experimentos(caso: Caso) -> Tuple[Dict[str, np.ndarray], Dict[str, Any]]:

    q0 = caso.q_struct
    mask = caso.geom_struct

    pilares = identificar_pilares(mask)

    q_exp0 = np.where(mask, q0, 0.0)
    q_exp1 = experimento_uniforme_global(q_exp0, mask)
    q_exp2 = experimento_uniforme_por_pilar(q_exp0, pilares)
    q_exp3, audit_exp3 = experimento_mesma_potencia_centroide(q_exp0, pilares)

    experiments = {
        "EXP0_ORIGINAL": q_exp0,
        "EXP1_UNIFORME_GLOBAL": q_exp1,
        "EXP2_UNIFORME_POR_PILAR": q_exp2,
        "EXP3_MESMA_POTENCIA_CENTROIDE_POR_PILAR": q_exp3,
    }

    metadata = {
        "pillar_identification": f"exact_cover_{PILLAR_NX}x{PILLAR_NY}x{PILLAR_NZ}",
        "n_pillars": len(pilares),
        "pillars": resumo_pilares(pilares),
        "exp3_slsqp": audit_exp3,
    }

    return experiments, metadata


# ======================================================================
# AUDITORIA DOS EXPERIMENTOS
# ======================================================================

def validar_experimentos(
    caso: Caso,
    experiments: Dict[str, np.ndarray],
    pilares: Sequence[np.ndarray],
) -> Dict[str, Any]:

    mask = caso.geom_struct
    q0 = experiments["EXP0_ORIGINAL"]

    auditoria: Dict[str, Any] = {}

    total0 = q_total(q0, caso.dV)
    momento0 = momento_q(q0, caso.dV)

    for nome, q in experiments.items():

        if q.shape != mask.shape:
            fail(f"{nome}: shape={q.shape}; esperado={mask.shape}")

        finite_or_fail(nome, q)

        scale = q_scale(q0)

        if np.min(q) < -TOL_REL_ZERO * scale:
            fail(f"{nome}: q negativo.")

        outside = q[~mask]
        if outside.size and max_abs(outside) > TOL_REL_ZERO * scale:
            fail(f"{nome}: q fora da máscara material.")

        total = q_total(q, caso.dV)
        rel_total = abs(total - total0) / max(abs(total0), 1e-30)

        auditoria[nome] = {
            "power_total_W": total,
            "power_error_abs_W": abs(total - total0),
            "power_error_rel": rel_total,
        }

        if rel_total > TOL_INVARIANT_REL:
            fail(f"{nome}: potência total não preservada. erro_rel={rel_total:.3e}")

    exp2 = experiments["EXP2_UNIFORME_POR_PILAR"]
    exp3 = experiments["EXP3_MESMA_POTENCIA_CENTROIDE_POR_PILAR"]

    exp2_audit = []
    exp3_audit = []

    for pilar_id, coords in enumerate(pilares):

        idx = (coords[:, 0], coords[:, 1], coords[:, 2])
        q_orig = q0[idx]
        q2 = exp2[idx]
        q3 = exp3[idx]

        p0 = float(np.sum(q_orig) * caso.dV)
        p2 = float(np.sum(q2) * caso.dV)
        p3 = float(np.sum(q3) * caso.dV)

        err2 = abs(p2 - p0)
        err3 = abs(p3 - p0)
        rel2 = err2 / max(abs(p0), 1e-30)
        rel3 = err3 / max(abs(p0), 1e-30)

        if rel2 > TOL_INVARIANT_REL:
            fail(f"EXP2: potência do pilar {pilar_id+1} não preservada.")
        if rel3 > TOL_INVARIANT_REL:
            fail(f"EXP3: potência do pilar {pilar_id+1} não preservada.")

        def physical_moments(values):
            xyz = coords.astype(float)
            x = xyz[:, 0] * caso.dx
            y = xyz[:, 1] * caso.dy
            z = xyz[:, 2] * caso.dz
            return np.array([
                np.sum(values * x) * caso.dV,
                np.sum(values * y) * caso.dV,
                np.sum(values * z) * caso.dV,
            ], dtype=float)

        m0 = physical_moments(q_orig)
        m3 = physical_moments(q3)

        dm = np.abs(m3 - m0)
        rel_m = dm / np.maximum(np.abs(m0), 1e-30)
        max_m_abs = float(np.max(dm))
        max_m_rel = float(np.max(rel_m))

        if max_m_rel > TOL_INVARIANT_REL:
            fail(f"EXP3: primeiro momento não preservado no pilar {pilar_id+1}. "
                 f"rel={max_m_rel:.3e}")

        exp2_audit.append({
            "pillar": pilar_id + 1,
            "power_original_W": p0,
            "power_exp2_W": p2,
            "error_abs_W": err2,
            "error_rel": rel2,
        })

        exp3_audit.append({
            "pillar": pilar_id + 1,
            "power_original_W": p0,
            "power_exp3_W": p3,
            "power_error_abs_W": err3,
            "power_error_rel": rel3,
            "moment_original": m0,
            "moment_exp3": m3,
            "moment_error_abs": dm,
            "moment_error_rel": rel_m,
            "moment_max_abs": max_m_abs,
            "moment_max_rel": max_m_rel,
        })

    auditoria["EXP2_per_pillar"] = exp2_audit
    auditoria["EXP3_per_pillar"] = exp3_audit
    auditoria["global"] = {
        "power_original_W": total0,
        "moment_original": momento0,
    }

    return auditoria


# ======================================================================
# EMBEDDING NO DOMÍNIO COMPLETO
# ======================================================================

def embutir_q(q_struct: np.ndarray, full_shape: Tuple[int, int, int], z0: int, z1: int) -> np.ndarray:
    q_full = np.zeros(full_shape, dtype=float)
    expected = (full_shape[0], full_shape[1], z1 - z0)
    if q_struct.shape != expected:
        fail(f"Embedding incompatível: q_struct={q_struct.shape}; esperado={expected}")
    q_full[:, :, z0:z1] = q_struct
    return q_full


# ======================================================================
# CONDUTIVIDADE HARMÔNICA
# ======================================================================

def harmonic_mean(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        fail(f"Condutividade inválida na interface: a={a}, b={b}")
    return 2.0 * a * b / (a + b)


# ======================================================================
# SOLVER TÉRMICO
# ======================================================================

def resolver_T(q: np.ndarray, k: np.ndarray, dx: float, dy: float, dz: float) -> np.ndarray:
    """
    Resolve -div(k grad T) = q com T = 0 nas seis faces externas.
    Discretização nodal de 7 pontos com condutividade harmônica nas faces.
    """

    q = np.asarray(q, dtype=float)
    k = np.asarray(k, dtype=float)

    if q.ndim != 3:
        fail(f"resolver_T: q deve ser 3D; {q.shape}")
    if q.shape != k.shape:
        fail(f"resolver_T: q={q.shape}, k={k.shape}")

    finite_or_fail("resolver_T q", q)
    finite_or_fail("resolver_T k", k)

    if np.min(k) <= 0:
        fail("resolver_T: k deve ser estritamente positivo.")

    nx, ny, nz = q.shape
    N = nx * ny * nz

    if min(nx, ny, nz) < 2:
        fail(f"resolver_T: domínio degenerado {q.shape}")

    def idx(i, j, l):
        return (i * ny + j) * nz + l

    A = lil_matrix((N, N), dtype=float)
    b = q.ravel(order="C").copy()

    for i in range(nx):
        for j in range(ny):
            for l in range(nz):

                p = idx(i, j, l)

                boundary = (i == 0 or i == nx - 1 or j == 0 or j == ny - 1
                            or l == 0 or l == nz - 1)

                if boundary:
                    A[p, p] = 1.0
                    b[p] = 0.0
                    continue

                diag = 0.0

                for (di, dj, dl, h) in ((1, 0, 0, dx), (-1, 0, 0, dx),
                                        (0, 1, 0, dy), (0, -1, 0, dy),
                                        (0, 0, 1, dz), (0, 0, -1, dz)):
                    kp = harmonic_mean(k[i, j, l], k[i + di, j + dj, l + dl])
                    G = kp / h ** 2
                    A[p, idx(i + di, j + dj, l + dl)] = -G
                    diag += G

                A[p, p] = diag

    A = csr_matrix(A)

    T_flat = spsolve(A, b)
    finite_or_fail("T", T_flat)

    T = T_flat.reshape(q.shape, order="C")

    boundary_values = np.concatenate([
        T[0, :, :].ravel(), T[-1, :, :].ravel(),
        T[:, 0, :].ravel(), T[:, -1, :].ravel(),
        T[:, :, 0].ravel(), T[:, :, -1].ravel(),
    ])

    if max_abs(boundary_values) > TOL_SOLVER_RESIDUAL * max(float(np.max(np.abs(T))), 1e-30):
        fail(f"Solver térmico violou T=0 na fronteira: max={max_abs(boundary_values):.6e}")

    residual = residuo_thermal(T, q, k, dx, dy, dz)
    residual_rel = max_abs(residual) / q_scale(q)

    if residual_rel > TOL_SOLVER_RESIDUAL:
        fail(f"Residual térmico excessivo: rel={residual_rel:.6e}")

    return T


# ======================================================================
# RESIDUAL TÉRMICO
# ======================================================================

def residuo_thermal(T, q, k, dx, dy, dz) -> np.ndarray:

    T = np.asarray(T, dtype=float)
    q = np.asarray(q, dtype=float)
    k = np.asarray(k, dtype=float)

    nx, ny, nz = q.shape
    r = np.zeros_like(q, dtype=float)

    boundary = np.zeros_like(q, dtype=bool)
    boundary[0, :, :] = True
    boundary[-1, :, :] = True
    boundary[:, 0, :] = True
    boundary[:, -1, :] = True
    boundary[:, :, 0] = True
    boundary[:, :, -1] = True

    r[boundary] = T[boundary]

    for i in range(1, nx - 1):
        for j in range(1, ny - 1):
            for l in range(1, nz - 1):

                div = (
                    harmonic_mean(k[i, j, l], k[i + 1, j, l]) * (T[i + 1, j, l] - T[i, j, l]) / dx ** 2
                    + harmonic_mean(k[i, j, l], k[i - 1, j, l]) * (T[i - 1, j, l] - T[i, j, l]) / dx ** 2
                    + harmonic_mean(k[i, j, l], k[i, j + 1, l]) * (T[i, j + 1, l] - T[i, j, l]) / dy ** 2
                    + harmonic_mean(k[i, j, l], k[i, j - 1, l]) * (T[i, j - 1, l] - T[i, j, l]) / dy ** 2
                    + harmonic_mean(k[i, j, l], k[i, j, l + 1]) * (T[i, j, l + 1] - T[i, j, l]) / dz ** 2
                    + harmonic_mean(k[i, j, l], k[i, j, l - 1]) * (T[i, j, l - 1] - T[i, j, l]) / dz ** 2
                )

                # PDE: -div(k grad T) = q  ->  residual = -div - q
                r[i, j, l] = -div - q[i, j, l]

    return r


# ======================================================================
# MÉTRICAS DE TEMPERATURA
# ======================================================================

def metricas_T(T: np.ndarray) -> Dict[str, float]:
    finite_or_fail("T", T)
    return {
        "T_min": float(np.min(T)),
        "T_max": float(np.max(T)),
        "T_mean": float(np.mean(T)),
        "T_std": float(np.std(T)),
        "T_l2": float(np.linalg.norm(T.ravel())),
    }


# ======================================================================
# AUTOTESTE DO CUBO
# ======================================================================

def autoteste_cubo() -> Dict[str, Any]:
    """
    Problema -laplacian(T) = 1 em [0,1]³, T = 0 nas faces.
    Compara o solver com uma montagem independente da matriz 7 pontos.
    """

    n = CUBE_N_AUTOTEST
    dx = 1.0 / (n - 1)
    q = np.ones((n, n, n), dtype=float)
    k = np.ones_like(q)

    T_num = resolver_T(q, k, dx, dx, dx)

    # Referência independente (sem chamar resolver_T).
    N = n ** 3
    A = lil_matrix((N, N), dtype=float)
    b = q.ravel(order="C").copy()

    def idx(i, j, l):
        return (i * n + j) * n + l

    G = 1.0 / dx ** 2

    for i in range(n):
        for j in range(n):
            for l in range(n):
                p = idx(i, j, l)
                boundary = (i == 0 or i == n - 1 or j == 0 or j == n - 1
                            or l == 0 or l == n - 1)
                if boundary:
                    A[p, p] = 1.0
                    b[p] = 0.0
                else:
                    A[p, p] = 6.0 * G
                    A[p, idx(i + 1, j, l)] = -G
                    A[p, idx(i - 1, j, l)] = -G
                    A[p, idx(i, j + 1, l)] = -G
                    A[p, idx(i, j - 1, l)] = -G
                    A[p, idx(i, j, l + 1)] = -G
                    A[p, idx(i, j, l - 1)] = -G

    T_ref = spsolve(csr_matrix(A), b).reshape(q.shape, order="C")

    error = array_rel_error(T_num, T_ref)

    if error > TOL_AUTOTEST:
        fail(f"AUTOTESTE CUBO FALHOU: erro relativo={error:.6e}")

    return {
        "status": "PASS",
        "n": n,
        "dx": dx,
        "Tmax_numerical": float(np.max(T_num)),
        "Tmax_reference": float(np.max(T_ref)),
        "relative_error": error,
    }


# ======================================================================
# AUTOTESTE DE ESCALA
# ======================================================================

def autoteste_escala() -> Dict[str, Any]:
    """Se q -> alpha q (k, geometria e BC fixos), então T -> alpha T."""

    n = 7
    dx = 0.2

    q = np.zeros((n, n, n), dtype=float)
    q[1:-1, 1:-1, 1:-1] = 1.0
    k = np.ones_like(q)
    alpha = 2.0

    T1 = resolver_T(q, k, dx, dx, dx)
    T2 = resolver_T(alpha * q, k, dx, dx, dx)

    error = array_rel_error(T2, alpha * T1)

    if error > TOL_AUTOTEST:
        fail(f"AUTOTESTE ESCALA FALHOU: erro relativo={error:.6e}")

    return {"status": "PASS", "alpha": alpha, "relative_error": error}


# ======================================================================
# AUTOTESTE EXACT-COVER
# ======================================================================

def autoteste_exact_cover() -> Dict[str, Any]:
    """Quatro pilares, incluindo pares adjacentes por face, recuperados exatamente."""

    geom = np.zeros((STRUCT_NX, STRUCT_NY, STRUCT_NZ), dtype=bool)

    positions = [(0, 0), (PILLAR_NX, 0), (0, PILLAR_NY), (PILLAR_NX, PILLAR_NY)]

    z0 = 3
    z1 = z0 + PILLAR_NZ

    for x0, y0 in positions:
        geom[x0:x0 + PILLAR_NX, y0:y0 + PILLAR_NY, z0:z1] = True

    pilares = identificar_pilares(geom)

    if len(pilares) != N_PILLARS:
        fail(f"AUTOTESTE EXACT-COVER: {len(pilares)} pilares encontrados; esperado={N_PILLARS}.")

    total = sum(len(p) for p in pilares)
    if total != TOTAL_MATERIAL_CELLS:
        fail(f"AUTOTESTE EXACT-COVER: {total} células; esperado={TOTAL_MATERIAL_CELLS}.")

    return {"status": "PASS", "n_pillars": len(pilares), "cells_total": total,
            "adjacent_face_case": True}


# ======================================================================
# AUTOTESTE EXP3
# ======================================================================

def autoteste_exp3() -> Dict[str, Any]:
    """Testa a construção EXP3 em um único pilar."""

    shape = (PILLAR_NX, PILLAR_NY, PILLAR_NZ)

    rng = np.random.default_rng(123456)
    q = rng.uniform(0.1, 2.0, size=shape)

    coords = np.argwhere(np.ones(shape, dtype=bool))

    q3, audit = experimento_mesma_potencia_centroide(q, [coords])

    A = np.vstack([
        np.ones(len(coords)),
        coords[:, 0].astype(float),
        coords[:, 1].astype(float),
        coords[:, 2].astype(float),
    ])

    b0 = A @ q.ravel()
    b3 = A @ q3.ravel()

    error_rel = max_abs(b3 - b0) / max(max_abs(b0), 1e-30)
    minimum = float(np.min(q3))

    if error_rel > TOL_INVARIANT_REL:
        fail(f"AUTOTESTE EXP3 falhou: erro relativo de invariantes={error_rel:.6e}")

    if minimum < -TOL_REL_ZERO * q_scale(q):
        fail(f"AUTOTESTE EXP3 falhou: q mínimo={minimum:.6e}")

    return {
        "status": "PASS",
        "constraint_max_rel": error_rel,
        "q_min": minimum,
        "slsqp": audit,
    }


# ======================================================================
# AUDITORIA DO T ORIGINAL
# ======================================================================

def auditar_T_original(caso: Caso, T_calculado: np.ndarray) -> Dict[str, Any]:

    if caso.T_original_full is None:
        return {"available": False, "status": "NOT_AVAILABLE"}

    T_saved = caso.T_original_full
    finite_or_fail("T_original armazenado", T_saved)

    err = array_rel_error(T_calculado, T_saved)

    result = {
        "available": True,
        "relative_error": err,
        "T_saved_max": float(np.max(T_saved)),
        "T_calculated_max": float(np.max(T_calculado)),
    }

    if STRICT_STORED_T and err > TOL_SOLVER_RESIDUAL:
        fail(f"seed={caso.seed}: T armazenado diverge do T reconstruído: rel={err:.6e}")

    result["status"] = "PASS" if err <= TOL_SOLVER_RESIDUAL else "AUDIT_WARNING"
    return result


# ======================================================================
# EXECUÇÃO DE UM CASO
# ======================================================================

def processar_caso(caso: Caso) -> Dict[str, Any]:

    inicio = time.perf_counter()

    print(f"\n{'=' * 72}\nCASE | RANDOM_{caso.seed} | {caso.freq_thz:.0f} THz\n{'=' * 72}")

    experiments, metadata = construir_experimentos(caso)

    pilares = identificar_pilares(caso.geom_struct)

    audit_q = validar_experimentos(caso, experiments, pilares)

    resultados = {}

    for nome in EXPERIMENTS:

        print(f" Solvendo {nome}...")

        q_struct = experiments[nome]

        q_full = embutir_q(q_struct, caso.q_abs_thermal_full.shape, caso.z_struct_start, caso.z_struct_end)

        T = resolver_T(q_full, caso.k_full, caso.dx, caso.dy, caso.dz)

        residual = residuo_thermal(T, q_full, caso.k_full, caso.dx, caso.dy, caso.dz)
        residual_rel = max_abs(residual) / q_scale(q_full)

        resultados[nome] = {
            "q_total_W": q_total(q_struct, caso.dV),
            "q_min": float(np.min(q_struct)),
            "q_max": float(np.max(q_struct)),
            "q_mean_material": float(np.mean(q_struct[caso.geom_struct])),
            "q_l2": float(np.linalg.norm(q_struct.ravel())),
            "T": metricas_T(T),
            "thermal_residual_max": max_abs(residual),
            "thermal_residual_relative": residual_rel,
            "centroid_q": centroide_q(q_struct),
        }

    # Auditoria do EXP0 contra o T armazenado (T não é salvo no JSON, só métricas).
    q_exp0_full = embutir_q(
        experiments["EXP0_ORIGINAL"],
        caso.q_abs_thermal_full.shape,
        caso.z_struct_start,
        caso.z_struct_end,
    )
    T_exp0 = resolver_T(q_exp0_full, caso.k_full, caso.dx, caso.dy, caso.dz)

    stored_T_audit = auditar_T_original(caso, T_exp0) if AUDIT_STORED_T else None

    elapsed = time.perf_counter() - inicio

    result = {
        "seed": caso.seed,
        "frequency_thz": caso.freq_thz,
        "source_file": str(caso.path),
        "schema_version": caso.schema_version,
        "geometry_hash": caso.geometry_hash,
        "positions_hash": caso.positions_hash,
        "q_struct_source": caso.q_struct_source,
        "grid": {
            "dx_m": caso.dx,
            "dy_m": caso.dy,
            "dz_m": caso.dz,
            "dV_m3": caso.dV,
            "full_shape": caso.q_abs_thermal_full.shape,
            "struct_shape": caso.geom_struct.shape,
            "z_struct_start": caso.z_struct_start,
            "z_struct_end": caso.z_struct_end,
        },
        "geometry": metadata,
        "q_audit": audit_q,
        "experiments": resultados,
        "stored_T_audit": stored_T_audit,
        "elapsed_seconds": elapsed,
        "status": "PASS",
    }

    for nome in EXPERIMENTS:
        print(f" PASS | Tmax {nome} = {resultados[nome]['T']['T_max']:.8e}")

    return result


# ======================================================================
# TESTES GLOBAIS
# ======================================================================

def executar_autotestes() -> Dict[str, Any]:

    print("\n" + "=" * 70 + f"\nAUTOTESTES UNIT-001.5 {VERSION}\n" + "=" * 70)

    testes = {}

    print("\n[1/4] Solver térmico — cubo...")
    testes["cube"] = autoteste_cubo()
    print(" PASS")

    print("\n[2/4] Linearidade de escala...")
    testes["scale"] = autoteste_escala()
    print(" PASS")

    print("\n[3/4] Exact-cover dos pilares...")
    testes["exact_cover"] = autoteste_exact_cover()
    print(" PASS")

    print("\n[4/4] EXP3 — potência + centroide...")
    testes["exp3"] = autoteste_exp3()
    print(" PASS")

    return testes


# ======================================================================
# MAIN
# ======================================================================

def main() -> int:

    inicio_global = time.perf_counter()

    print("\n" + "━" * 68 + f"\nUNIT-001.5 | MODULAÇÃO TÉRMICA CONTRAFACTUAL {VERSION}\n" + "━" * 68)
    print(f"BASE_DIR : {BASE_DIR}")
    print(f"CASES_DIR: {CASES_DIR}")
    print(f"OUTPUT : {OUTPUT_JSON}")
    print(f"\nConfiguração:\n"
          f" seeds = {SEEDS}\n"
          f" frequencies = {FREQUENCIES_SELECIONADAS_THZ} THz\n"
          f" pillars = {N_PILLARS}\n"
          f" pillar = {PILLAR_NX}x{PILLAR_NY}x{PILLAR_NZ}\n"
          f" cells/pilar = {PILLAR_CELLS}\n"
          f" material = {TOTAL_MATERIAL_CELLS} células\n")

    try:

        autotests = executar_autotestes()

        casos = []

        print("\n" + "=" * 70 + "\nDESCOBERTA DOS CASES\n" + "=" * 70)

        for seed in SEEDS:
            for freq in FREQUENCIES_SELECIONADAS_THZ:
                path = localizar_case(seed, freq)
                print(f" FOUND: seed={seed}, freq={freq:.0f} THz -> {path.name}")
                casos.append(carregar_caso(seed, freq))

        expected_cases = len(SEEDS) * len(FREQUENCIES_SELECIONADAS_THZ)
        if len(casos) != expected_cases:
            fail(f"Esperados {expected_cases} casos; carregados {len(casos)}.")

        case_results = [processar_caso(caso) for caso in casos]

        elapsed = time.perf_counter() - inicio_global

        output = {
            "unit": "UNIT-001.5",
            "version": VERSION,
            "status": "PASS",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "configuration": {
                "seeds": SEEDS,
                "frequencies_thz": FREQUENCIES_SELECIONADAS_THZ,
                "k_background": K_BACKGROUND,
                "k_pillar": K_PILLAR,
                "limiar_k": LIMIAR_K,
                "dx_m": DX,
                "pillar_shape": [PILLAR_NX, PILLAR_NY, PILLAR_NZ],
                "n_pillars": N_PILLARS,
                "total_material_cells": TOTAL_MATERIAL_CELLS,
            },
            "scientific_model": {
                "equation": "-div(k grad T) = q",
                "boundary_condition": "T = 0 on all six outer faces",
                "face_conductivity": "harmonic_mean",
                "solver": "sparse 7-point finite-difference",
                "pillar_identification": f"exact-cover {PILLAR_NX}x{PILLAR_NY} footprint "
                                         f"+ common {PILLAR_NZ}-layer z extent",
            },
            "autotests": autotests,
            "cases": case_results,
            "summary": {
                "n_cases": len(case_results),
                "n_pass": sum(r["status"] == "PASS" for r in case_results),
                "n_fail": sum(r["status"] != "PASS" for r in case_results),
                "elapsed_seconds": elapsed,
            },
        }

        if output["summary"]["n_fail"] != 0:
            fail("Existem cases sem PASS.")

        salvar_json(OUTPUT_JSON, output)

        print("\n" + "━" * 68 + "\nRESULTADO FINAL: PASS\n" + "━" * 68)
        print(f"Cases: {output['summary']['n_pass']}/{output['summary']['n_cases']}")
        print(f"Tempo total: {elapsed:.3f} s")
        print(f"JSON: {OUTPUT_JSON}")
        print("━" * 68)

        return 0

    except Exception as exc:

        elapsed = time.perf_counter() - inicio_global

        print("\n" + "━" * 68 + "\nRESULTADO FINAL: ERRO\n" + "━" * 68)
        print(f"Tipo: {type(exc).__name__}")
        print(f"Mensagem: {exc}")
        print(f"Tempo até falha: {elapsed:.3f} s")
        print("\nTRACEBACK:\n")
        traceback.print_exc()
        print("━" * 68)

        return 1


# ======================================================================
# ENTRY POINT
# ======================================================================

if __name__ == "__main__":
    sys.exit(main())
