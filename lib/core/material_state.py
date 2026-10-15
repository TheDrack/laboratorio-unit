"""
material_state.py — UNIT, Fase 1 (canonicalização): fundação consolidada
para a representação da matéria.

REVISÃO: o silício da biblioteca usa as constantes de lib/geometry/unit001_fisica.py
(antes ε = 11,7 e k = 150 fixos, que não correspondem ao silício na banda
280–320 THz). Demais propriedades mantidas.

Material  — receita de UMA substância: epsilon(omega), mu(omega), propriedades térmicas.
MaterialState — instanciação espacial que um solver consome: grid (nx,ny,nz) de epsilon,
  avaliado numa frequência de projeto omega_design.
rasterize_materials() liga os dois a partir de uma máscara de rótulos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Union

import numpy as np

from lib.geometry.unit001_constantes import N_PILLAR, K_SILICON

DispersiveProperty = Union[float, complex, Callable[[float], complex]]


# ==============================================================================
# 1. MATERIAL — receita nomeada de uma substância, sem posição no espaço
# ==============================================================================
@dataclass(frozen=True)
class Material:
    """Uma substância física: como responde a uma frequência angular omega (rad/s)."""
    name: str
    epsilon: DispersiveProperty
    mu: DispersiveProperty = 1.0 + 0.0j
    k_thermal: float = 0.0           # W/(m·K)
    rho: float = 0.0                 # kg/m³
    cp: float = 0.0                  # J/(kg·K)

    def get_epsilon(self, omega: float) -> complex:
        return complex(self.epsilon(omega)) if callable(self.epsilon) else complex(self.epsilon)

    def get_mu(self, omega: float) -> complex:
        return complex(self.mu(omega)) if callable(self.mu) else complex(self.mu)

    def is_lossy(self, omega: float) -> bool:
        return np.imag(self.get_epsilon(omega)) > 1e-12 or np.imag(self.get_mu(omega)) > 1e-12


# Silício cristalino, ~300 K. ε = n² com n da fonte única (Green 2008, 280–320 THz).
# Densidade e calor específico: valores de referência a 300 K.
SILICIO_RHO = 2329.0             # kg/m³
SILICIO_CP = 712.0               # J/(kg·K)

MATERIAL_LIBRARY: Dict[str, Material] = {
    "vacuo": Material(name="vacuo", epsilon=1.0 + 0.0j),
    "silica": Material(name="silica", epsilon=2.25 + 0.0j, k_thermal=1.4, rho=2200.0, cp=700.0),
    "silicio": Material(
        name="silicio",
        epsilon=N_PILLAR ** 2,
        k_thermal=K_SILICON,
        rho=SILICIO_RHO,
        cp=SILICIO_CP,
    ),
    "ouro": Material(name="ouro", epsilon=-30.0 + 2.0j, k_thermal=317.0, rho=19300.0, cp=129.0),
}


# ==============================================================================
# 2. MATERIALSTATE — instanciação espacial (o que um solver de fato consome)
# ==============================================================================
@dataclass
class MaterialState:
    epsilon: np.ndarray              # (nx,ny,nz) complexo — eps_r por célula, em UMA omega
    dx: float
    dy: float
    dz: float
    mu: float = 1.0
    sigma: Optional[np.ndarray] = None
    k_thermal: float = 0.0           # escalar "em massa" para o domínio inteiro
    rho: float = 0.0
    cp: float = 0.0
    omega_design: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.epsilon = np.asarray(self.epsilon, dtype=complex)
        if self.sigma is not None:
            self.sigma = np.asarray(self.sigma, dtype=float)
            if self.sigma.shape != self.epsilon.shape:
                raise ValueError(f"sigma.shape {self.sigma.shape} != epsilon.shape {self.epsilon.shape}")

    @property
    def shape(self):
        return self.epsilon.shape

    def sigma_or_zero(self) -> np.ndarray:
        if self.sigma is not None:
            return self.sigma
        return np.zeros(self.epsilon.shape, dtype=float)


# ==============================================================================
# 3. CONSTRUTORES DIRETOS
# ==============================================================================
def from_homogeneous(nx: int, ny: int, nz: int, dx: float, dy: float, dz: float,
                     eps_r: complex, **kwargs) -> MaterialState:
    eps = np.full((nx, ny, nz), eps_r, dtype=complex)
    return MaterialState(epsilon=eps, dx=dx, dy=dy, dz=dz, **kwargs)


def from_geometry_dict(geom: Dict, **kwargs) -> MaterialState:
    """A partir do dict que geometry.py/fdfd3d.py produzem (chaves 'epsilon','dx','dz';
    'dy' opcional, ausente em geometrias 2D, onde se assume dy=dx)."""
    eps = np.asarray(geom["epsilon"])
    dx = geom["dx"]
    dy = geom.get("dy", dx)
    dz = geom["dz"]
    return MaterialState(epsilon=eps, dx=dx, dy=dy, dz=dz, **kwargs)


# ==============================================================================
# 4. PONTE: máscara de rótulos + biblioteca de Material -> MaterialState
# ==============================================================================
def rasterize_materials(label_mask: np.ndarray, materials: Dict[Any, Material],
                        dx: float, dy: float, dz: float, omega: float,
                        dominant_label: Optional[Any] = None, **kwargs) -> MaterialState:
    """
    label_mask: array (nx,ny,nz) de rótulos (ex.: 0=fundo, 1=inclusão).
    materials:  dict rótulo -> Material.
    omega:      frequência em que Material.get_epsilon(omega) é avaliada.
    dominant_label: rótulo cujas propriedades térmicas viram os valores "em massa";
                    se None, usa o rótulo mais frequente na máscara.
    """
    label_mask = np.asarray(label_mask)
    eps = np.empty(label_mask.shape, dtype=complex)
    for label, material in materials.items():
        eps[label_mask == label] = material.get_epsilon(omega)

    if dominant_label is None:
        labels, counts = np.unique(label_mask, return_counts=True)
        dominant_label = labels[np.argmax(counts)]
    dominant = materials[dominant_label]

    return MaterialState(
        epsilon=eps, dx=dx, dy=dy, dz=dz,
        k_thermal=dominant.k_thermal, rho=dominant.rho, cp=dominant.cp,
        omega_design=omega, **kwargs,
    )


# ==============================================================================
# 5. ADAPTADORES
# ==============================================================================
def to_fdfd3d_geom(material: MaterialState) -> Dict:
    """MaterialState -> dict no formato que fdfd3d.build_domain_3d espera."""
    nx, ny, nz = material.shape
    return {"nx": nx, "ny": ny, "nz": nz,
            "dx": material.dx, "dy": material.dy, "dz": material.dz,
            "epsilon": material.epsilon}


def to_fdtd3d_eps_cell(material: MaterialState) -> np.ndarray:
    """MaterialState -> eps_cell do fdtd3d. A v1 do fdtd3d ainda não suporta perda
    (eps complexo); o suporte via sigma fica para a próxima fase."""
    return material.epsilon


if __name__ == "__main__":
    from lib.geometry.unit001_constantes import C_LIGHT, DX

    nx, ny, nz = 6, 6, 10
    mask = np.zeros((nx, ny, nz), dtype=int)
    mask[2:4, 2:4, 3:7] = 1                       # inclusão de silício em fundo de vácuo

    materials = {0: MATERIAL_LIBRARY["vacuo"], 1: MATERIAL_LIBRARY["silicio"]}
    omega0 = 2.0 * np.pi * C_LIGHT / 1.0e-6

    state = rasterize_materials(mask, materials, dx=DX, dy=DX, dz=DX, omega=omega0)
    print(f"MaterialState: shape={state.shape} eps no fundo={state.epsilon[0,0,0]} "
          f"eps na inclusão={state.epsilon[2,2,4]} k_thermal (dominante)={state.k_thermal}")
