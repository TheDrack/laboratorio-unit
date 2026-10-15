"""
geometry.py — Parametrização geométrica para o UNIT-001 (Nível 2: 2D estrutural)
VERSÃO REVISADA v1 (pendente de revisão conjunta: coordenador + pesquisador)

Correção aplicada: todo valor que nasce no início é definido UMA vez na seção
CONSTANTES e propagado pelo fluxo através de GeometryParams. Nenhuma função
mantém valor próprio (antes havia resolution_ppw=20 repetido em 3 funções,
comprimento de onda 0.8 µm fixo dentro de _pixel_size, tol=0.02 e seed=42 fixos).

Estruturas de controle:
 A — homogêneo efetivo (Maxwell-Garnett), mesma fração de material
 B — mesmos elementos (N, r, forma) em posições ALEATÓRIAS (hard-disk, sem overlap)
 C — rede periódica (a geometria "otimizável")
"""

from dataclasses import dataclass
from typing import Literal, Optional, Dict
import numpy as np


# ==============================================================================
# 0. CONSTANTES — definidas UMA vez, no início do fluxo
# ==============================================================================
LAMBDA_MIN_REF_M = 0.8e-6     # menor lambda do benchmark 1D atual (m)
RESOLUTION_PPW = 20.0         # pontos por comprimento de onda da malha
MIN_SEP_FACTOR = 1.05         # fator de separação mínima entre elementos (hard-disk)
MAX_TRIES = 50000             # tentativas máximas do sorteio hard-disk
TOL_MATERIAL = 0.02           # tolerância relativa de pareamento de material A/B/C
SEED_B = 42                   # semente do Controle B (usada em generate_ABC e demo)
SAVE_DIR = "."                # diretório de figuras (sem caminho fixo de máquina)


# ==============================================================================
# 1. DEFINIÇÃO DE PARÂMETROS (theta)
# ==============================================================================
@dataclass
class GeometryParams:
    a: float                              # periodicidade da rede de referência (m)
    Lx: float                             # extensão lateral do domínio, x (m)
    Lz: float                             # espessura total do domínio, z (m)
    eps_bg: complex = 1.0 + 0j            # permissividade do meio de fundo
    eps_incl: complex = 4.0 + 0j          # permissividade da inclusão
    shape: Literal["circle", "square"] = "circle"
    lattice: Literal["square", "hex"] = "square"
    r: Optional[float] = None             # raio (ou semi-lado) do elemento (m)
    f: Optional[float] = None             # fração de área ocupada
    ppw: float = RESOLUTION_PPW           # propagado a todas as estruturas
    lambda_min: float = LAMBDA_MIN_REF_M  # propagado a todas as estruturas
    min_sep_factor: float = MIN_SEP_FACTOR
    max_tries: int = MAX_TRIES

    def __post_init__(self):
        if self.r is None and self.f is None:
            raise ValueError("Forneça r ou f (um determina o outro).")
        if self.r is not None and self.f is not None:
            raise ValueError("Forneça APENAS r ou f, não os dois (evita inconsistência).")
        if self.r is None:
            self.r = radius_from_fraction(self.a, self.f, self.shape, self.lattice)
        else:
            self.f = fraction_from_radius(self.a, self.r, self.shape, self.lattice)


# ==============================================================================
# 2. RELAÇÃO r <-> f PARA REDES PERIÓDICAS
# ==============================================================================
def _area_incl(r: float, shape: str) -> float:
    if shape == "circle":
        return np.pi * r ** 2
    elif shape == "square":
        return (2 * r) ** 2
    raise ValueError(f"shape desconhecida: {shape}")


def _area_cell(a: float, lattice: str) -> float:
    if lattice == "square":
        return a ** 2
    elif lattice == "hex":
        return (np.sqrt(3) / 2.0) * a ** 2
    raise ValueError(f"lattice desconhecida: {lattice}")


def fraction_from_radius(a: float, r: float, shape="circle", lattice="square") -> float:
    """f = fração de área ocupada por uma rede periódica de elementos de raio r, período a."""
    return _area_incl(r, shape) / _area_cell(a, lattice)


def radius_from_fraction(a: float, f: float, shape="circle", lattice="square") -> float:
    """Resolve r dado a fração de área desejada f e a periodicidade a."""
    area_incl = f * _area_cell(a, lattice)
    if shape == "circle":
        return float(np.sqrt(area_incl / np.pi))
    elif shape == "square":
        return float(np.sqrt(area_incl) / 2.0)
    raise ValueError(f"shape desconhecida: {shape}")


# ==============================================================================
# 3. MISTURA EFETIVA (Controle A)
# ==============================================================================
def maxwell_garnett(eps_bg: complex, eps_incl: complex, f: float) -> complex:
    """Permissividade efetiva de Maxwell-Garnett para inclusões diluídas (2D)."""
    beta = (eps_incl - eps_bg) / (eps_incl + eps_bg)
    return eps_bg * (1.0 + 2.0 * f * beta) / (1.0 - f * beta)


# ==============================================================================
# 4. GERAÇÃO DE CENTROS (rede periódica e aleatória pareada)
# ==============================================================================
def lattice_centers(p: GeometryParams) -> np.ndarray:
    """Centros (x, z) da rede periódica dentro do domínio [0, Lx] x [0, Lz]."""
    centers = []
    if p.lattice == "square":
        nx = int(np.floor(p.Lx / p.a))
        nz = int(np.floor(p.Lz / p.a))
        for i in range(nx):
            for j in range(nz):
                cx, cz = (i + 0.5) * p.a, (j + 0.5) * p.a
                if cx + p.r <= p.Lx and cz + p.r <= p.Lz:
                    centers.append((cx, cz))
    elif p.lattice == "hex":
        row_spacing = p.a * np.sqrt(3) / 2.0
        nz = int(np.floor(p.Lz / row_spacing))
        nx = int(np.floor(p.Lx / p.a))
        for j in range(nz):
            offset = 0.0 if j % 2 == 0 else p.a / 2.0
            for i in range(nx):
                cx, cz = offset + (i + 0.5) * p.a, (j + 0.5) * row_spacing
                if cx + p.r <= p.Lx and cz + p.r <= p.Lz:
                    centers.append((cx, cz))
    else:
        raise ValueError(f"lattice desconhecida: {p.lattice}")
    if len(centers) == 0:
        raise ValueError("Nenhum elemento coube no domínio — Lx/Lz pequenos demais para 'a'.")
    return np.array(centers)


def random_hard_disk_centers(p: GeometryParams, n_targets: int, seed: int) -> np.ndarray:
    """
    Amostragem sequencial tipo 'hard-disk': sorteia n_targets centros dentro do
    domínio com separação mínima (evita overlap). Separação e tentativas vêm de p.
    """
    rng = np.random.default_rng(seed)
    min_sep = 2.0 * p.r * p.min_sep_factor
    centers = []
    tries = 0
    while len(centers) < n_targets and tries < p.max_tries:
        cx = rng.uniform(p.r, p.Lx - p.r)
        cz = rng.uniform(p.r, p.Lz - p.r)
        if all((cx - ex) ** 2 + (cz - ez) ** 2 >= min_sep ** 2 for ex, ez in centers):
            centers.append((cx, cz))
        tries += 1
    if len(centers) < n_targets:
        raise RuntimeError(
            f"Só foi possível posicionar {len(centers)}/{n_targets} elementos sem overlap "
            f"em {p.max_tries} tentativas. Reduza f, aumente Lx/Lz, ou reduza min_sep_factor."
        )
    return np.array(centers)


# ==============================================================================
# 5. RASTERIZAÇÃO: centros -> epsilon_r(x, z)
# ==============================================================================
def _pixel_size(p: GeometryParams) -> float:
    """Passo da malha derivado de lambda_min e ppw, ambos vindos de p."""
    return p.lambda_min / p.ppw


def rasterize(p: GeometryParams, centers: np.ndarray, dx: float) -> Dict:
    """Constrói epsilon_r(x, z) numa malha regular de passo dx, a partir dos centros dados."""
    nx = max(4, int(np.ceil(p.Lx / dx)))
    nz = max(4, int(np.ceil(p.Lz / dx)))
    x = np.linspace(0, p.Lx, nx)
    z = np.linspace(0, p.Lz, nz)
    X, Z = np.meshgrid(x, z, indexing="ij")
    eps = np.full((nx, nz), p.eps_bg, dtype=complex)

    for (cx, cz) in centers:
        if p.shape == "circle":
            mask = (X - cx) ** 2 + (Z - cz) ** 2 <= p.r ** 2
        elif p.shape == "square":
            mask = (np.abs(X - cx) <= p.r) & (np.abs(Z - cz) <= p.r)
        else:
            raise ValueError(f"shape desconhecida: {p.shape}")
        eps[mask] = p.eps_incl

    f_actual = float(np.mean(eps != p.eps_bg))
    return {
        "X": X, "Z": Z, "epsilon": eps, "centers": centers,
        "dx": p.Lx / nx, "dz": p.Lz / nz, "nx": nx, "nz": nz,
        "f_actual": f_actual,
    }


# ==============================================================================
# 6. AS TRÊS ESTRUTURAS DE CONTROLE (A / B / C) — todas leem de p
# ==============================================================================
def make_structure_C_periodic(p: GeometryParams) -> Dict:
    """C — rede periódica (a geometria 'otimizável')."""
    dx = _pixel_size(p)
    centers = lattice_centers(p)
    grid = rasterize(p, centers, dx)
    grid.update({"label": "C_periodico", "params": p,
                 "n_elements": len(centers), "f_nominal": p.f})
    return grid


def make_structure_B_random(p: GeometryParams, seed: int) -> Dict:
    """B — mesmos elementos de C (mesmo N, r, forma), posições aleatórias sem overlap."""
    dx = _pixel_size(p)
    n_elements = len(lattice_centers(p))
    centers = random_hard_disk_centers(p, n_elements, seed=seed)
    grid = rasterize(p, centers, dx)
    grid.update({"label": f"B_aleatorio_seed{seed}", "params": p,
                 "n_elements": n_elements, "f_nominal": p.f})
    return grid


def make_structure_A_homogeneous(p: GeometryParams) -> Dict:
    """A — meio homogêneo com epsilon efetivo de Maxwell-Garnett, mesma fração f."""
    dx = _pixel_size(p)
    nx = max(4, int(np.ceil(p.Lx / dx)))
    nz = max(4, int(np.ceil(p.Lz / dx)))
    x = np.linspace(0, p.Lx, nx)
    z = np.linspace(0, p.Lz, nz)
    X, Z = np.meshgrid(x, z, indexing="ij")
    eps_eff = maxwell_garnett(p.eps_bg, p.eps_incl, p.f)
    eps = np.full((nx, nz), eps_eff, dtype=complex)
    return {
        "X": X, "Z": Z, "epsilon": eps, "centers": np.empty((0, 2)),
        "dx": p.Lx / nx, "dz": p.Lz / nz, "nx": nx, "nz": nz,
        "f_actual": p.f, "label": "A_homogeneo", "params": p,
        "n_elements": 0, "f_nominal": p.f, "eps_eff": eps_eff,
    }


def generate_ABC(p: GeometryParams, seed_B: int = SEED_B) -> Dict[str, Dict]:
    """Gera as três estruturas pareadas em fração de material a partir do mesmo theta."""
    return {
        "A": make_structure_A_homogeneous(p),
        "B": make_structure_B_random(p, seed_B),
        "C": make_structure_C_periodic(p),
    }


# ==============================================================================
# 7. VERIFICAÇÃO DE PAREAMENTO DE MATERIAL
# ==============================================================================
def check_matched_material(geoms: Dict[str, Dict], tol: float = TOL_MATERIAL) -> Dict:
    """
    Compara a fração de material discretizada (f_actual) entre A, B, C.
    Levanta sinal (ok=False) se a diferença relativa exceder tol.
    """
    f_values = {k: v["f_actual"] for k, v in geoms.items()}
    f_ref = f_values["C"]
    report = {}
    ok = True
    for k, f in f_values.items():
        rel_diff = abs(f - f_ref) / f_ref if f_ref > 0 else 0.0
        report[k] = {"f_actual": f, "rel_diff_vs_C": rel_diff}
        if rel_diff > tol:
            ok = False
    report["ok"] = ok
    return report


# ==============================================================================
# 8. VISUALIZAÇÃO RÁPIDA (opcional)
# ==============================================================================
def plot_ABC(geoms: Dict[str, Dict], save_path: Optional[str] = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    for ax, key in zip(axes, ["A", "B", "C"]):
        g = geoms[key]
        ax.imshow(np.real(g["epsilon"]).T, origin="lower",
                  extent=[0, g["params"].Lx * 1e6, 0, g["params"].Lz * 1e6],
                  aspect="equal", cmap="viridis")
        ax.set_title(f"{g['label']}\nf_actual={g['f_actual']:.3f}")
        ax.set_xlabel("x (µm)")
        ax.set_ylabel("z (µm)")
    if save_path:
        fig.savefig(save_path, dpi=140)
    return fig


# ==============================================================================
# 9. DEMO — parâmetros de demo também saem de constantes nomeadas
# ==============================================================================
DEMO_A = 0.15e-6
DEMO_LX = 1.5e-6
DEMO_LZ = 1.5e-6
DEMO_EPS_INCL = (3.5 + 0.1j) ** 2
DEMO_F = 0.30

if __name__ == "__main__":
    params = GeometryParams(
        a=DEMO_A, Lx=DEMO_LX, Lz=DEMO_LZ,
        eps_bg=1.0 + 0j, eps_incl=DEMO_EPS_INCL,
        shape="circle", lattice="square", f=DEMO_F,
    )
    print(f"theta: a={params.a*1e9:.1f}nm, r={params.r*1e9:.1f}nm, f_nominal={params.f:.3f}")

    geoms = generate_ABC(params, seed_B=SEED_B)
    for key, g in geoms.items():
        print(f" {g['label']:<20} | malha={g['nx']}x{g['nz']} | "
              f"N_elementos={g['n_elements']} | f_actual={g['f_actual']:.4f}")

    report = check_matched_material(geoms, tol=TOL_MATERIAL)
    print(f"\nVerificação de pareamento de material (tol={TOL_MATERIAL*100:.0f}%):")
    for k, v in report.items():
        if k == "ok":
            continue
        print(f" {k}: f_actual={v['f_actual']:.4f} | diff vs C = {v['rel_diff_vs_C']*100:.2f}%")
    print(f" -> pareamento OK: {report['ok']}")

    fig = plot_ABC(geoms, save_path=f"{SAVE_DIR}/geometry_ABC_demo.png")
    print(f"\nFigura salva em {SAVE_DIR}/geometry_ABC_demo.png")
