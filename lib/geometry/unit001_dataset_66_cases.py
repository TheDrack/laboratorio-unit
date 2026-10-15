from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Any
import hashlib
import json

import numpy as np
from lib.geometry.unit001_constantes import (NX, NY, NZ, PILLAR_NX, PILLAR_NY, PILLAR_NZ, N_PILLARS, RANDOM_SEEDS_START, RANDOM_SEEDS_COUNT, FREQUENCIES_THZ)


# =============================================================================
# UNIT-001 — DATASET CANÔNICO DE GEOMETRIAS
# =============================================================================
#
# ESTE ARQUIVO É A FONTE ÚNICA DE VERDADE DA GEOMETRIA.
#
# Qualquer outro módulo que precise construir uma geometria deve importar
# as funções deste arquivo.
#
# Não duplicar:
# - make_geometry_from_positions()
# - generate_random_positions()
# - ORDERED_POSITIONS
# - CLUSTERED_POSITIONS
#
# especialmente no extrator FDFD.
#
# Cadeia canônica:
#
# seed
# ↓
# posições
# ↓
# máscara estrutural NX×NY×NZ
# ↓
# epsilon/material
# ↓
# FDFD
# ↓
# q_abs
# ↓
# térmico
#
# REVISÃO v2: todas as contagens (22 geometrias, 66 casos, 20 seeds, 3
# frequências) e a origem z = Z_ORIGEM agora são derivadas das constantes do topo.
# Nenhum literal numérico de contagem aparece nas validações.
# =============================================================================


DATASET_SCHEMA_VERSION = "UNIT001_GEOMETRY_V2"


# =============================================================================
# CONFIGURAÇÃO (única fonte de cada valor)
# =============================================================================




Z_ORIGEM = 0                                   # origem z dos pilares (convenção canônica)

RANDOM_SEEDS = tuple(
    range(RANDOM_SEEDS_START, RANDOM_SEEDS_START + RANDOM_SEEDS_COUNT)
)


OUTPUT_DIR_NAME = "unit001_dataset_66_cases"


# =============================================================================
# GEOMETRIAS FIXAS
# =============================================================================

# Cada tupla é (x0, y0). O pilar ocupa:
#   x = x0 : x0 + PILLAR_NX
#   y = y0 : y0 + PILLAR_NY
#   z = Z_ORIGEM : Z_ORIGEM + PILLAR_NZ
ORDERED_POSITIONS = (
    (2, 2),
    (10, 2),
    (2, 10),
    (10, 10),
)

CLUSTERED_POSITIONS = (
    (4, 4),
    (8, 4),
    (4, 8),
    (8, 8),
)


# =============================================================================
# CONSTANTES DERIVADAS (todas a partir da configuração acima)
# =============================================================================

N_RANDOM = len(RANDOM_SEEDS)
N_FIXED = 2                              # ORDERED + CLUSTERED
N_GEOMETRIES = N_FIXED + N_RANDOM
N_FREQUENCIES = len(FREQUENCIES_THZ)
N_CASES = N_GEOMETRIES * N_FREQUENCIES

EXPECTED_MATERIAL_CELLS = (
    N_PILLARS
    * PILLAR_NX
    * PILLAR_NY
    * PILLAR_NZ
)

EXPECTED_MATERIAL_FRACTION = (
    EXPECTED_MATERIAL_CELLS
    / (NX * NY * NZ)
)


# =============================================================================
# HASH CANÔNICO DA GEOMETRIA
# =============================================================================

def geometry_hash(mask: np.ndarray) -> str:
    """
    Calcula hash SHA-256 determinístico da máscara geométrica.

    A representação canônica é:
    - ndarray bool
    - shape (NX, NY, NZ)
    - bytes C-contiguous

    O hash permite detectar qualquer alteração silenciosa da geometria.
    """

    mask = np.asarray(mask, dtype=bool)

    if mask.shape != (NX, NY, NZ):
        raise ValueError(
            f"geometry_hash(): shape inválido: {mask.shape}; "
            f"esperado {(NX, NY, NZ)}"
        )

    canonical = np.ascontiguousarray(mask, dtype=np.bool_)

    return hashlib.sha256(
        canonical.tobytes(order="C")
    ).hexdigest()


# =============================================================================
# HASH DAS POSIÇÕES
# =============================================================================

def positions_hash(
    positions: Tuple[Tuple[int, int], ...],
) -> str:
    """
    Hash determinístico das posições dos pilares.
    """

    normalized = tuple(
        sorted(
            (int(x), int(y))
            for x, y in positions
        )
    )

    payload = json.dumps(
        normalized,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


# =============================================================================
# VALIDAÇÃO DE POSIÇÕES
# =============================================================================

def validate_positions(
    positions: Tuple[Tuple[int, int], ...],
    nx: int = NX,
    ny: int = NY,
    pillar_nx: int = PILLAR_NX,
    pillar_ny: int = PILLAR_NY,
    n_pillars: int = N_PILLARS,
) -> None:
    """
    Valida posições dos pilares antes da construção da máscara.
    """

    if len(positions) != n_pillars:
        raise ValueError(
            f"Número incorreto de pilares: "
            f"{len(positions)}; esperado {n_pillars}"
        )

    normalized = [
        (int(x), int(y))
        for x, y in positions
    ]

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            "Posições duplicadas detectadas."
        )

    for x0, y0 in normalized:

        if x0 < 0 or y0 < 0:
            raise ValueError(
                f"Posição negativa: {(x0, y0)}"
            )

        x1 = x0 + pillar_nx
        y1 = y0 + pillar_ny

        if x1 > nx or y1 > ny:
            raise ValueError(
                f"Pilar fora do domínio: "
                f"posição={(x0, y0)}, "
                f"fim={(x1, y1)}, "
                f"domínio={(nx, ny)}"
            )

    # Verificação explícita de sobreposição XY.
    for i, (x0, y0) in enumerate(normalized):

        for j, (x1, y1) in enumerate(normalized):

            if j <= i:
                continue

            overlap = not (
                x0 + pillar_nx <= x1
                or x1 + pillar_nx <= x0
                or y0 + pillar_ny <= y1
                or y1 + pillar_ny <= y0
            )

            if overlap:
                raise ValueError(
                    "Sobreposição detectada entre pilares: "
                    f"{(x0, y0)} e {(x1, y1)}"
                )


# =============================================================================
# CONSTRUÇÃO DA MÁSCARA
# =============================================================================

def make_geometry_from_positions(
    positions: Tuple[Tuple[int, int], ...],
    nx: int = NX,
    ny: int = NY,
    nz: int = NZ,
    pillar_nx: int = PILLAR_NX,
    pillar_ny: int = PILLAR_NY,
    pillar_nz: int = PILLAR_NZ,
    z0: int = Z_ORIGEM,
) -> np.ndarray:
    """
    Cria a máscara estrutural canônica.

    Shape:
        (nx, ny, nz)

    Convenção:
        True  = material do pilar
        False = fundo

    Os pilares ocupam SEMPRE:
        z = z0 : z0 + pillar_nz

    Para o dataset padrão: z = Z_ORIGEM : Z_ORIGEM + PILLAR_NZ.
    """

    positions = tuple(
        (int(x), int(y))
        for x, y in positions
    )

    validate_positions(
        positions=positions,
        nx=nx,
        ny=ny,
        pillar_nx=pillar_nx,
        pillar_ny=pillar_ny,
        n_pillars=len(positions),
    )

    if pillar_nz <= 0:
        raise ValueError(
            f"pillar_nz inválido: {pillar_nz}"
        )

    if z0 + pillar_nz > nz:
        raise ValueError(
            f"pillar_nz={pillar_nz} com z0={z0} excede nz={nz}"
        )

    mask = np.zeros(
        (nx, ny, nz),
        dtype=bool,
    )

    for x0, y0 in positions:

        x1 = x0 + pillar_nx
        y1 = y0 + pillar_ny
        z1 = z0 + pillar_nz

        region = mask[
            x0:x1,
            y0:y1,
            z0:z1,
        ]

        if np.any(region):
            raise ValueError(
                f"Sobreposição detectada no pilar {(x0, y0)}"
            )

        mask[
            x0:x1,
            y0:y1,
            z0:z1,
        ] = True

    return mask


# =============================================================================
# GERAÇÃO RANDOM CANÔNICA
# =============================================================================

def generate_random_positions(
    seed: int,
    nx: int = NX,
    ny: int = NY,
    pillar_nx: int = PILLAR_NX,
    pillar_ny: int = PILLAR_NY,
    n_pillars: int = N_PILLARS,
) -> Tuple[Tuple[int, int], ...]:
    """
    Gera posições RANDOM de maneira determinística.

    ALGORITMO CANÔNICO:

    1. cria todos os candidatos;
    2. embaralha com np.random.default_rng(seed);
    3. percorre os candidatos na ordem embaralhada;
    4. aceita somente candidatos sem sobreposição;
    5. para ao atingir n_pillars;
    6. ordena as posições antes de retornar.

    NÃO substituir por amostragem repetida com rng.integers().
    """

    seed = int(seed)

    rng = np.random.default_rng(seed)

    candidates = [
        (x, y)
        for x in range(
            0,
            nx - pillar_nx + 1,
        )
        for y in range(
            0,
            ny - pillar_ny + 1,
        )
    ]

    rng.shuffle(candidates)

    selected: List[Tuple[int, int]] = []

    for candidate in candidates:

        x0, y0 = candidate

        overlap = False

        for x1, y1 in selected:

            if not (
                x0 + pillar_nx <= x1
                or x1 + pillar_nx <= x0
                or y0 + pillar_ny <= y1
                or y1 + pillar_ny <= y0
            ):
                overlap = True
                break

        if overlap:
            continue

        selected.append(
            (int(x0), int(y0))
        )

        if len(selected) == n_pillars:
            break

    if len(selected) != n_pillars:
        raise RuntimeError(
            f"Não foi possível gerar "
            f"{n_pillars} pilares sem sobreposição "
            f"para seed={seed}"
        )

    selected = sorted(selected)

    result = tuple(selected)

    validate_positions(
        positions=result,
        nx=nx,
        ny=ny,
        pillar_nx=pillar_nx,
        pillar_ny=pillar_ny,
        n_pillars=n_pillars,
    )

    return result


# =============================================================================
# VALIDAÇÃO DA MÁSCARA
# =============================================================================

def validate_geometry(
    mask: np.ndarray,
    expected_material_cells: int = EXPECTED_MATERIAL_CELLS,
    nx: int = NX,
    ny: int = NY,
    nz: int = NZ,
) -> Dict[str, Any]:
    """
    Valida invariantes físicos/estruturais da máscara.
    """

    mask = np.asarray(
        mask,
        dtype=bool,
    )

    expected_shape = (
        nx,
        ny,
        nz,
    )

    if mask.shape != expected_shape:
        raise ValueError(
            f"Shape incorreto: {mask.shape}; "
            f"esperado {expected_shape}"
        )

    if not np.all(
        np.isfinite(
            mask.astype(float)
        )
    ):
        raise ValueError(
            "Máscara contém valores não finitos."
        )

    n_material = int(
        np.count_nonzero(mask)
    )

    if n_material != expected_material_cells:
        raise ValueError(
            "Número de células materiais incorreto: "
            f"{n_material}; "
            f"esperado {expected_material_cells}"
        )

    fraction = (
        n_material
        / mask.size
    )

    return {
        "shape": list(mask.shape),
        "n_cells_total": int(mask.size),
        "n_material": n_material,
        "material_fraction": float(fraction),
        "n_background": int(
            mask.size - n_material
        ),
        "geometry_hash": geometry_hash(mask),
    }


# =============================================================================
# VALIDAÇÃO ESTRUTURAL DOS PILARES
# =============================================================================

def validate_pillar_structure(
    mask: np.ndarray,
    positions: Tuple[Tuple[int, int], ...],
) -> None:
    """
    Garante que a máscara corresponde exatamente às posições declaradas.
    """

    expected = make_geometry_from_positions(
        positions=positions,
        nx=mask.shape[0],
        ny=mask.shape[1],
        nz=mask.shape[2],
    )

    if not np.array_equal(
        mask,
        expected,
    ):
        xor = np.logical_xor(
            mask,
            expected,
        )

        raise ValueError(
            "Máscara não corresponde às posições declaradas. "
            f"Células divergentes: "
            f"{int(np.count_nonzero(xor))}"
        )


# =============================================================================
# REGISTRO CANÔNICO DE UMA GEOMETRIA
# =============================================================================

def build_geometry_record(
    geometry: str,
    seed: int | None,
    positions: Tuple[Tuple[int, int], ...],
) -> Dict[str, Any]:
    """
    Constrói um registro completo e auditável de uma geometria.
    """

    mask = make_geometry_from_positions(
        positions
    )

    validate_pillar_structure(
        mask,
        positions,
    )

    validation = validate_geometry(
        mask
    )

    return {
        "geometry": str(geometry),
        "seed": (
            None
            if seed is None
            else int(seed)
        ),
        "positions": tuple(
            (int(x), int(y))
            for x, y in positions
        ),
        "positions_hash": positions_hash(
            positions
        ),
        "geometry_hash": validation[
            "geometry_hash"
        ],
        "mask": mask,
        "validation": validation,
        "schema_version": DATASET_SCHEMA_VERSION,
    }


# =============================================================================
# GERAÇÃO DAS GEOMETRIAS (N_FIXED fixas + N_RANDOM aleatórias)
# =============================================================================

def generate_all_geometries() -> List[Dict[str, Any]]:
    """
    Gera exatamente:

      1 ORDERED
      1 CLUSTERED
      N_RANDOM RANDOM

    Total: N_GEOMETRIES.
    """

    geometries: List[Dict[str, Any]] = []

    geometries.append(
        build_geometry_record(
            geometry="ORDERED",
            seed=None,
            positions=ORDERED_POSITIONS,
        )
    )

    geometries.append(
        build_geometry_record(
            geometry="CLUSTERED",
            seed=None,
            positions=CLUSTERED_POSITIONS,
        )
    )

    for seed in RANDOM_SEEDS:

        positions = generate_random_positions(
            seed=seed
        )

        geometries.append(
            build_geometry_record(
                geometry="RANDOM",
                seed=seed,
                positions=positions,
            )
        )

    if len(geometries) != N_GEOMETRIES:
        raise RuntimeError(
            "Dataset inválido: "
            f"{len(geometries)} geometrias; "
            f"esperadas {N_GEOMETRIES}."
        )

    random_seeds = [
        g["seed"]
        for g in geometries
        if g["geometry"] == "RANDOM"
    ]

    if tuple(random_seeds) != RANDOM_SEEDS:
        raise RuntimeError(
            "Conjunto de seeds RANDOM inesperado: "
            f"{random_seeds}"
        )

    hashes = [
        g["geometry_hash"]
        for g in geometries
    ]

    if len(set(hashes)) != len(hashes):
        raise RuntimeError(
            "Duas geometrias diferentes possuem "
            "o mesmo geometry_hash."
        )

    return geometries


# =============================================================================
# EXPANSÃO GEOMETRIAS × FREQUÊNCIAS
# =============================================================================

def generate_all_cases() -> List[Dict[str, Any]]:
    """
    Expande as N_GEOMETRIES geometrias para as N_FREQUENCIES frequências.

    Total: N_CASES casos.
    """

    geometries = generate_all_geometries()

    cases: List[Dict[str, Any]] = []

    case_id = 0

    for geom in geometries:

        for frequency_thz in FREQUENCIES_THZ:

            case_id += 1

            cases.append(
                {
                    "case_id": int(case_id),
                    "geometry": geom["geometry"],
                    "seed": geom["seed"],
                    "frequency_thz": float(frequency_thz),
                    "positions": tuple(geom["positions"]),
                    "positions_hash": geom["positions_hash"],
                    "geometry_hash": geom["geometry_hash"],
                    "mask": geom["mask"].copy(),
                    "validation": geom["validation"].copy(),
                    "schema_version": DATASET_SCHEMA_VERSION,
                }
            )

    if len(cases) != N_CASES:
        raise RuntimeError(
            "Dataset inválido: "
            f"{len(cases)} casos; "
            f"esperados {N_CASES}."
        )

    return cases


# =============================================================================
# LOCALIZAÇÃO CANÔNICA DE UMA GEOMETRIA
# =============================================================================

def get_geometry(
    geometry: str,
    seed: int | None = None,
) -> Dict[str, Any]:
    """
    Retorna exatamente uma geometria do catálogo canônico.

    Exemplos:
        get_geometry("ORDERED")
        get_geometry("CLUSTERED")
        get_geometry("RANDOM", 1007)
    """

    geometry = str(geometry).upper()

    geometries = generate_all_geometries()

    for geom in geometries:

        if geom["geometry"] != geometry:
            continue

        if geom["seed"] != seed:
            continue

        return geom

    raise KeyError(
        f"Geometria não encontrada: "
        f"geometry={geometry!r}, "
        f"seed={seed!r}"
    )


# =============================================================================
# CATÁLOGO SERIALIZÁVEL
# =============================================================================

def geometry_catalog(
    geometries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Converte registros internos para uma estrutura JSON serializável.
    """

    catalog = []

    for geom in geometries:

        catalog.append(
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "geometry": geom["geometry"],
                "seed": geom["seed"],
                "positions": [
                    [int(x), int(y)]
                    for x, y in geom["positions"]
                ],
                "positions_hash": geom["positions_hash"],
                "geometry_hash": geom["geometry_hash"],
                "validation": geom["validation"],
            }
        )

    return catalog


# =============================================================================
# RESUMO
# =============================================================================

def print_dataset_summary(
    geometries: List[Dict[str, Any]],
    cases: List[Dict[str, Any]],
) -> None:

    print()
    print("=" * 80)
    print("UNIT-001 — DATASET CANÔNICO DE GEOMETRIAS")
    print("=" * 80)

    print(f"Schema: {DATASET_SCHEMA_VERSION}")
    print(f"Domínio estrutural: {NX} × {NY} × {NZ}")
    print(f"Pilar: {PILLAR_NX} × {PILLAR_NY} × {PILLAR_NZ}")
    print(f"Posição Z dos pilares: {Z_ORIGEM}:{Z_ORIGEM + PILLAR_NZ}")
    print(f"Células materiais esperadas: {EXPECTED_MATERIAL_CELLS}")
    print(f"Fração material: {EXPECTED_MATERIAL_FRACTION:.6f}")

    print()
    print(f"Geometrias: {len(geometries)}")
    print(f"Frequências: {N_FREQUENCIES}")
    print(f"Casos totais: {len(cases)}")

    print()
    print("Distribuição:")

    for name in ("ORDERED", "CLUSTERED", "RANDOM"):
        count = sum(c["geometry"] == name for c in cases)
        print(f" {name:<9}: {count:2d}")

    print()
    print("Frequências:")

    for frequency in FREQUENCIES_THZ:
        count = sum(c["frequency_thz"] == frequency for c in cases)
        print(f" {frequency:.1f} THz : {count:2d} casos")

    print()
    print("Geometrias RANDOM:")

    for geom in geometries:
        if geom["geometry"] != "RANDOM":
            continue
        print(
            f" seed={geom['seed']:4d} | "
            f"positions={geom['positions']} | "
            f"hash={geom['geometry_hash'][:16]}"
        )

    print()
    print("Primeiros casos:")

    for case in cases[:6]:
        seed_text = "none" if case["seed"] is None else str(case["seed"])
        print(
            f" case={case['case_id']:02d} | "
            f"{case['geometry']:<9} | "
            f"seed={seed_text:<4} | "
            f"f={case['frequency_thz']:.1f} THz | "
            f"hash={case['geometry_hash'][:12]}"
        )

    print()
    print("Últimos casos:")

    for case in cases[-6:]:
        seed_text = "none" if case["seed"] is None else str(case["seed"])
        print(
            f" case={case['case_id']:02d} | "
            f"{case['geometry']:<9} | "
            f"seed={seed_text:<4} | "
            f"f={case['frequency_thz']:.1f} THz | "
            f"hash={case['geometry_hash'][:12]}"
        )

    print("=" * 80)


# =============================================================================
# SALVAR CATÁLOGO, MÁSCARAS E HASHES
# =============================================================================

def save_geometry_catalog(
    geometries: List[Dict[str, Any]],
    output_path: Path,
) -> None:

    catalog = geometry_catalog(geometries)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)


def _mask_key(geom: Dict[str, Any]) -> str:

    if geom["geometry"] == "ORDERED":
        return "ORDERED"

    if geom["geometry"] == "CLUSTERED":
        return "CLUSTERED"

    return f"RANDOM_{geom['seed']}"


def save_geometry_masks(
    geometries: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Salva as máscaras estruturais em NPZ.

    uint8:
        0 = fundo
        1 = material
    """

    arrays: Dict[str, np.ndarray] = {
        _mask_key(geom): geom["mask"].astype(np.uint8)
        for geom in geometries
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(output_path, **arrays)


def save_geometry_hashes(
    geometries: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Arquivo auxiliar simples para auditoria externa.
    """

    records = [
        {
            "schema_version": DATASET_SCHEMA_VERSION,
            "geometry": geom["geometry"],
            "seed": geom["seed"],
            "positions": [list(p) for p in geom["positions"]],
            "positions_hash": geom["positions_hash"],
            "geometry_hash": geom["geometry_hash"],
        }
        for geom in geometries
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


# =============================================================================
# TESTES INTERNOS DO DATASET
# =============================================================================

def run_self_tests() -> None:
    """
    Testes internos do gerador.

    Se qualquer teste falhar, o dataset não deve ser utilizado.
    """

    print()
    print("Executando autotestes do dataset...")

    # 1. Dataset completo
    geometries = generate_all_geometries()
    cases = generate_all_cases()

    assert len(geometries) == N_GEOMETRIES
    assert len(cases) == N_CASES

    # 2. ORDERED
    ordered = get_geometry("ORDERED")
    assert ordered["seed"] is None
    assert ordered["positions"] == ORDERED_POSITIONS

    # 3. CLUSTERED
    clustered = get_geometry("CLUSTERED")
    assert clustered["seed"] is None
    assert clustered["positions"] == CLUSTERED_POSITIONS

    # 4. RANDOM reproduzível
    for seed in RANDOM_SEEDS:

        geom_a = get_geometry("RANDOM", seed)
        geom_b = get_geometry("RANDOM", seed)

        assert geom_a["positions"] == geom_b["positions"]
        assert geom_a["geometry_hash"] == geom_b["geometry_hash"]
        assert generate_random_positions(seed) == geom_a["positions"]

    # 5. Hashes únicos
    hashes = [geom["geometry_hash"] for geom in geometries]
    assert len(hashes) == len(set(hashes))

    # 6. Máscaras corretas
    for geom in geometries:

        mask = geom["mask"]

        assert mask.shape == (NX, NY, NZ)
        assert mask.dtype == np.bool_
        assert np.count_nonzero(mask) == EXPECTED_MATERIAL_CELLS

        validate_pillar_structure(mask, geom["positions"])

    # 7. Frequências
    assert len(FREQUENCIES_THZ) == N_FREQUENCIES

    for case in cases:
        assert case["frequency_thz"] in FREQUENCIES_THZ

    # 8. IDs únicos e sequenciais
    case_ids = [c["case_id"] for c in cases]
    assert len(case_ids) == len(set(case_ids))
    assert case_ids == list(range(1, N_CASES + 1))

    print(f" [PASS] {N_GEOMETRIES} geometrias")
    print(f" [PASS] {N_CASES} casos")
    print(" [PASS] hashes determinísticos")
    print(" [PASS] RANDOM reproduzível")
    print(" [PASS] posições ↔ máscaras")
    print(" [PASS] fração material")
    print(" [PASS] IDs dos casos")
    print("Autotestes: PASS")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    OUTPUT_DIR = Path(OUTPUT_DIR_NAME)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run_self_tests()

    geometries = generate_all_geometries()
    cases = generate_all_cases()

    print_dataset_summary(geometries, cases)

    save_geometry_catalog(geometries, OUTPUT_DIR / "geometry_catalog.json")
    save_geometry_masks(geometries, OUTPUT_DIR / "geometry_masks.npz")
    save_geometry_hashes(geometries, OUTPUT_DIR / "geometry_hashes.json")

    print()
    print("Arquivos de auditoria salvos:")
    print(f" {OUTPUT_DIR / 'geometry_catalog.json'}")
    print(f" {OUTPUT_DIR / 'geometry_masks.npz'}")
    print(f" {OUTPUT_DIR / 'geometry_hashes.json'}")

    print()
    print(f"{N_CASES} CASOS GERADOS COM SUCESSO.")
