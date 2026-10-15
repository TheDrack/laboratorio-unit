"""
fdfd3d.py — Solver FDFD 3D escalar TE_y (UNIT-001)

REVISÃO v4:
 - EPS0 e C_LIGHT vêm de lib/geometry/unit001_fisica.py (fonte única).
 - Regra única dos monitores: a face de cada monitor fica a MONITOR_OFFSET_FRAC
   do comprimento de onda no vácuo da estrutura (meio comprimento de onda), medida
   a partir da face da estrutura. Função posicao_monitores() é a única fonte dessa
   regra; o FDTD deve usar a mesma função/valor.
 - build_domain_3d exige npml_cells e buffer_cells (sem valores padrão ocultos).

Modelo:
  E = (0, E_y, 0);  ∇² E_y + k0² ε_r E_y = 0
  Formulação espalhada: E_total = E_inc + E_scat;  A E_scat = -(A - A_bg) E_inc
"""

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from dataclasses import dataclass

from lib.geometry.unit001_constantes import EPS0, C_LIGHT
from lib.solvers.fdfd2d import (
    MU0,
    Z0,
    build_D2,
    build_D1,
    _build_D_forward,
    pml_sfactors,
)
from lib.geometry.unit001_constantes import posicao_monitores, MONITOR_OFFSET_FRAC


# =============================================================================
# 0. REGRA DOS MONITORES (fonte única)
# =============================================================================

# Distância da face do monitor até a face da estrutura, em comprimentos de onda
# no vácuo. Meio comprimento de onda: campo evanescente do pilar já decaiu, e a
# decomposição modal de ondas planas continua válida.




# =============================================================================
# 1. DOMÍNIO
# =============================================================================

@dataclass
class DomainSetup3D:
    eps: np.ndarray
    mu: np.ndarray

    dx: float
    dy: float
    dz: float

    n_bg: complex
    mu_bg: complex

    z_struct_start: int
    z_struct_end: int

    z_mon_in: int
    z_mon_out: int

    npml: int

    k0: float
    wavelength: float

    k_inc_discrete: complex = None


# =============================================================================
# 2. NÚMERO DE ONDA DISCRETO
# =============================================================================

def discrete_wavenumber_1d(k0, n, dz):
    """
    Número de onda discreto do stencil central de 2ª ordem:
        -4 sin²(kd dz / 2)/dz² + k0² n² = 0  =>  kd = (2/dz) asin(k0 n dz / 2)
    Aceita n complexo.
    """
    argument = k0 * n * dz / 2.0
    return 2.0 / dz * np.arcsin(argument)


def discrete_derivative_wavenumber(k_discrete, dz):
    """Fator de derivada efetivo do operador central D1: q_d = sin(kd dz)/dz."""
    return np.sin(k_discrete * dz) / dz


# =============================================================================
# 3. DOMÍNIO
# =============================================================================

def build_domain_3d(geom, wavelength, n_bg, npml_cells, buffer_cells, mu_bg=1.0):
    """
    Constrói o domínio FDFD. npml_cells e buffer_cells são obrigatórios
    (definidos na origem do fluxo, em lib/geometry/unit001_fisica.py / extrator).
    """
    nx = geom["nx"]
    ny = geom["ny"]
    nz_struct = geom["nz"]

    dx = geom["dx"]
    dy = geom["dy"]
    dz = geom["dz"]

    n_pad = npml_cells + buffer_cells
    nz_total = 2 * n_pad + nz_struct

    eps_full = np.full((nx, ny, nz_total), n_bg ** 2, dtype=complex)
    eps_full[:, :, n_pad:n_pad + nz_struct] = geom["epsilon"]

    if "mu_r" in geom:
        mu_struct = np.asarray(geom["mu_r"], dtype=complex)
        if mu_struct.shape != (nx, ny, nz_struct):
            raise ValueError(
                f"geom['mu_r'] possui shape {mu_struct.shape}; "
                f"esperado {(nx, ny, nz_struct)}."
            )
    else:
        mu_struct = np.ones((nx, ny, nz_struct), dtype=complex)

    mu_full = np.full((nx, ny, nz_total), mu_bg, dtype=complex)
    mu_full[:, :, n_pad:n_pad + nz_struct] = mu_struct

    k0 = 2.0 * np.pi / wavelength

    n_eff_bg = complex(n_bg) * np.sqrt(complex(mu_bg))
    k_discrete = discrete_wavenumber_1d(k0, n_eff_bg, dz)

    z_mon_in, z_mon_out = posicao_monitores(
        npml_cells, buffer_cells, nz_struct, wavelength, dz,
    )

    return DomainSetup3D(
        eps=eps_full,
        mu=mu_full,
        dx=dx,
        dy=dy,
        dz=dz,
        n_bg=n_bg,
        mu_bg=mu_bg,
        z_struct_start=n_pad,
        z_struct_end=n_pad + nz_struct,
        z_mon_in=z_mon_in,
        z_mon_out=z_mon_out,
        npml=npml_cells,
        k0=k0,
        wavelength=wavelength,
        k_inc_discrete=k_discrete,
    )


# =============================================================================
# 4. GEOMETRIAS AUXILIARES
# =============================================================================

def homogeneous_slab_geom_3d(nx, ny, nz, dx, dy, dz, n_slab):
    eps = np.full((nx, ny, nz), n_slab ** 2, dtype=complex)
    return {"nx": nx, "ny": ny, "nz": nz, "dx": dx, "dy": dy, "dz": dz, "epsilon": eps}


# =============================================================================
# 5. ONDA INCIDENTE DISCRETA
# =============================================================================

def build_incident_field_3d(domain):
    """E_inc = exp(i kd z), com kd da relação de dispersão da malha."""
    nx, ny, nz = domain.eps.shape
    z_axis = np.arange(nz) * domain.dz
    Einc_z = np.exp(1j * domain.k_inc_discrete * z_axis)
    Einc = np.broadcast_to(Einc_z, (nx, ny, nz)).copy()
    return Einc, z_axis


# =============================================================================
# 5.5 OPERADORES MAGNÉTICOS (flux-form)
# =============================================================================

def _inverse_mu_half_axis(mu, axis, periodic):
    """mu^{-1} nos meios-pontos: média dos vizinhos; em z o último coeficiente é mantido."""
    inv_mu = 1.0 / np.asarray(mu, dtype=complex)
    out = np.empty_like(inv_mu)

    if periodic:
        out = 0.5 * (inv_mu + np.roll(inv_mu, -1, axis=axis))
    else:
        sl0 = [slice(None)] * inv_mu.ndim
        sl1 = [slice(None)] * inv_mu.ndim
        sl0[axis] = slice(0, -1)
        sl1[axis] = slice(1, None)
        out[tuple(sl0)] = 0.5 * (inv_mu[tuple(sl0)] + inv_mu[tuple(sl1)])

        sl_last = [slice(None)] * inv_mu.ndim
        sl_last[axis] = -1
        out[tuple(sl_last)] = inv_mu[tuple(sl_last)]

    return out


def _build_flux_operator_axis(N, d, periodic, npml, k0, coeff_half):
    """Sn^{-1} Db C_half Sh^{-1} Df, com C_half = mu^{-1} nos meios-pontos."""
    Df = _build_D_forward(N, d, periodic)
    Db = -Df.T

    if periodic:
        s_node = np.ones(N, dtype=complex)
        s_half = np.ones(N, dtype=complex)
    else:
        s_node, s_half = pml_sfactors(N, npml, d, k0)

    Sn_inv = sp.diags(1.0 / s_node, format="csr")
    Sh_inv = sp.diags(1.0 / s_half, format="csr")
    C_half = sp.diags(np.asarray(coeff_half, dtype=complex), format="csr")

    return (Sn_inv @ Db @ C_half @ Sh_inv @ Df).tocsr()


def _build_scalar_laplacian_3d(nx, ny, nz, dx, dy, dz, k0, npml):
    """Laplaciano escalar na convenção do solver."""
    D2x = build_D2(nx, dx, periodic=True, npml=0, k0=k0)
    D2y = build_D2(ny, dy, periodic=True, npml=0, k0=k0)
    D2z = build_D2(nz, dz, periodic=False, npml=npml, k0=k0)

    Ix = sp.identity(nx, format="csr")
    Iy = sp.identity(ny, format="csr")
    Iz = sp.identity(nz, format="csr")

    return (
        sp.kron(sp.kron(D2x, Iy, format="csr"), Iz, format="csr")
        + sp.kron(sp.kron(Ix, D2y, format="csr"), Iz, format="csr")
        + sp.kron(sp.kron(Ix, Iy, format="csr"), D2z, format="csr")
    ).tocsr()


def _build_mu_divergence_operator_3d(domain):
    """div(mu_r^{-1} grad E_y) em forma flux-form conservativa."""
    nx, ny, nz = domain.eps.shape
    dx, dy, dz = domain.dx, domain.dy, domain.dz
    k0 = domain.k0

    mu = np.asarray(domain.mu, dtype=complex)

    if mu.shape != (nx, ny, nz):
        raise ValueError("domain.mu possui shape incompatível.")
    if np.any(~np.isfinite(mu)):
        raise ValueError("mu_r contém valores não finitos.")
    if np.any(np.abs(mu) == 0.0):
        raise ValueError("mu_r não pode conter zero.")

    inv_mu_x = _inverse_mu_half_axis(mu, axis=0, periodic=True)
    inv_mu_y = _inverse_mu_half_axis(mu, axis=1, periodic=True)
    inv_mu_z = _inverse_mu_half_axis(mu, axis=2, periodic=False)

    Ix = sp.identity(nx, format="csr")
    Iy = sp.identity(ny, format="csr")
    Iz = sp.identity(nz, format="csr")

    Dfx = _build_D_forward(nx, dx, True)
    Dbx = -Dfx.T
    Dfy = _build_D_forward(ny, dy, True)
    Dby = -Dfy.T
    Dfz = _build_D_forward(nz, dz, False)
    Dbz = -Dfz.T

    sx_node = np.ones(nx, dtype=complex)
    sy_node = np.ones(ny, dtype=complex)
    sz_node, sz_half = pml_sfactors(nz, domain.npml, dz, k0)

    Sx_inv = sp.diags(1.0 / sx_node, format="csr")
    Sy_inv = sp.diags(1.0 / sy_node, format="csr")
    Sz_inv = sp.diags(1.0 / sz_node, format="csr")
    Szh_inv = sp.diags(1.0 / sz_half, format="csr")

    Cx = sp.diags(inv_mu_x.flatten(order="C"), format="csr")
    Cy = sp.diags(inv_mu_y.flatten(order="C"), format="csr")
    Cz = sp.diags(inv_mu_z.flatten(order="C"), format="csr")

    Grad_x = sp.kron(sp.kron(Sx_inv @ Dfx, Iy, format="csr"), Iz, format="csr")
    Grad_y = sp.kron(sp.kron(Ix, Sy_inv @ Dfy, format="csr"), Iz, format="csr")
    Grad_z_flux = sp.kron(sp.kron(Ix, Iy, format="csr"), Szh_inv @ Dfz, format="csr")

    Div_x = sp.kron(sp.kron(Sx_inv @ Dbx, Iy, format="csr"), Iz, format="csr")
    Div_y = sp.kron(sp.kron(Ix, Sy_inv @ Dby, format="csr"), Iz, format="csr")
    Div_z = sp.kron(sp.kron(Ix, Iy, format="csr"), Sz_inv @ Dbz, format="csr")

    Op = (
        Div_x @ Cx @ Grad_x
        + Div_y @ Cy @ Grad_y
        + Div_z @ Cz @ Grad_z_flux
    )

    return Op.tocsr()


# =============================================================================
# 6. SOLVER PRINCIPAL
# =============================================================================

def solve_fdfd_3d(domain):
    """
    div(mu_r^-1 grad Ey) + k0² eps_r Ey = 0, em forma espalhada:
        A Escat = -(A - A_bg) Einc
    """
    nx, ny, nz = domain.eps.shape
    k0 = domain.k0
    N = nx * ny * nz

    Magnetic_operator = _build_mu_divergence_operator_3d(domain)

    eps_flat = domain.eps.flatten(order="C")

    A = (Magnetic_operator + (k0 ** 2) * sp.diags(eps_flat, format="csr")).tocsc()

    Einc, z_axis = build_incident_field_3d(domain)
    Einc_flat = Einc.flatten(order="C")

    eps_bg = complex(domain.n_bg) ** 2
    mu_bg = complex(domain.mu_bg)

    if abs(mu_bg) == 0.0:
        raise ValueError("mu_bg não pode ser zero.")

    Lap = _build_scalar_laplacian_3d(nx, ny, nz, domain.dx, domain.dy, domain.dz, k0, domain.npml)

    A_bg = ((1.0 / mu_bg) * Lap + (k0 ** 2) * eps_bg * sp.identity(N, format="csr")).tocsc()

    contrast = A - A_bg
    b = -(contrast @ Einc_flat)

    Escat_flat = spla.spsolve(A, b)
    Escat = Escat_flat.reshape((nx, ny, nz), order="C")
    Etotal = Einc + Escat

    residual_flat = A @ Escat_flat - b
    residual_norm = np.linalg.norm(residual_flat)
    b_norm = np.linalg.norm(b)
    relative_residual = residual_norm / b_norm if b_norm > 0 else 0.0

    incident_operator_residual = compute_incident_operator_residual(domain, Einc, Lap)

    return {
        "Etotal": Etotal,
        "Escat": Escat,
        "Einc": Einc,
        "domain": domain,
        "z_axis": z_axis,
        "relative_residual": relative_residual,
        "incident_operator_residual": incident_operator_residual,
        "k_inc_discrete": domain.k_inc_discrete,
    }


# =============================================================================
# 7. RESÍDUO DA ONDA INCIDENTE
# =============================================================================

def compute_incident_operator_residual(domain, Einc, Lap=None):
    """
    Residual relativo da onda incidente discreta no operador homogêneo em z.
    Não utiliza PML neste diagnóstico.
    """
    nx, ny, nz = domain.eps.shape

    k0 = float(domain.k0)
    dz = float(domain.dz)
    n = complex(domain.n_bg)

    n_eff = n * np.sqrt(complex(domain.mu_bg))
    k_continuous = k0 * n_eff

    argument = k_continuous * dz / 2.0
    if abs(argument) > 1.0:
        return np.nan

    k_discrete = 2.0 / dz * np.arcsin(argument)
    if not np.isfinite(k_discrete):
        return np.nan

    D2z = build_D2(nz, dz, periodic=False, npml=0, k0=k0)

    z = np.arange(nz, dtype=float) * dz
    Einc_z = np.exp(1j * k_discrete * z)

    D2_E = D2z @ Einc_z
    eps_bg = n ** 2
    mu_bg = complex(domain.mu_bg)

    residual_z = (1.0 / mu_bg) * D2_E + k0 ** 2 * eps_bg * Einc_z

    # Excluímos as duas extremidades: o stencil tem tratamento especial de fronteira.
    zmin = 2
    zmax = nz - 2
    if zmax <= zmin:
        return np.nan

    numerator = np.linalg.norm(residual_z[zmin:zmax])
    denominator = k0 ** 2 * abs(eps_bg) * np.linalg.norm(Einc_z[zmin:zmax])

    if denominator == 0.0 or not np.isfinite(denominator):
        return np.nan

    return float(numerator / denominator)


# =============================================================================
# 8. DIAGNÓSTICO MAGNÉTICO DA ONDA INCIDENTE
# =============================================================================

def compute_incident_magnetic_fields_3d(result):
    """Hx = -qd/(ω μ0 μ_bg) Ey para a onda discreta."""
    domain = result["domain"]

    q = discrete_derivative_wavenumber(domain.k_inc_discrete, domain.dz)
    omega = domain.k0 * C_LIGHT

    Hx = (-q / (omega * MU0 * domain.mu_bg)) * result["Einc"]

    return {
        "H_x": Hx,
        "H_y": np.zeros_like(result["Einc"]),
        "H_z": np.zeros_like(result["Einc"]),
    }


# =============================================================================
# 9. CAMPOS H
# =============================================================================

def compute_H_fields_3d(result):
    """Hx = -(1/iωμ) dEy/dz;  Hz = +(1/iωμ) dEy/dx."""
    domain = result["domain"]
    nx, ny, nz = domain.eps.shape

    E_flat = result["Etotal"].flatten(order="C")

    D1x = build_D1(nx, domain.dx, periodic=True, npml=0, k0=domain.k0)
    D1z = build_D1(nz, domain.dz, periodic=False, npml=domain.npml, k0=domain.k0)

    Ix = sp.identity(nx, format="csr")
    Iy = sp.identity(ny, format="csr")
    Iz = sp.identity(nz, format="csr")

    Grad_x = sp.kron(sp.kron(D1x, Iy, format="csr"), Iz, format="csr")
    Grad_z = sp.kron(sp.kron(Ix, Iy, format="csr"), D1z, format="csr")

    dE_dx = (Grad_x @ E_flat).reshape((nx, ny, nz), order="C")
    dE_dz = (Grad_z @ E_flat).reshape((nx, ny, nz), order="C")

    omega = domain.k0 * C_LIGHT
    mu_local = domain.mu

    return {
        "H_x": -dE_dz / (1j * omega * MU0 * mu_local),
        "H_y": np.zeros((nx, ny, nz), dtype=complex),
        "H_z": dE_dx / (1j * omega * MU0 * mu_local),
    }


# =============================================================================
# 10. POYNTING
# =============================================================================

def compute_poynting_3d(result):
    """S = ½ Re(E × H*). Para E = (0,Ey,0): Sx = +½ Re(Ey Hz*), Sz = -½ Re(Ey Hx*)."""
    E = result["Etotal"]
    H = compute_H_fields_3d(result)

    return {
        "S_x": 0.5 * np.real(E * np.conj(H["H_z"])),
        "S_y": np.zeros_like(E),
        "S_z": -0.5 * np.real(E * np.conj(H["H_x"])),
    }


# =============================================================================
# 11. POTÊNCIA INCIDENTE DISCRETA
# =============================================================================

def compute_discrete_incident_power(result):
    """
    Potência da onda incidente com a mesma derivada discreta usada em H:
        S_inc = qd/(2 ω μ) |E|²  (com E de amplitude unitária)  e  P_inc = S_inc · área.
    """
    domain = result["domain"]

    nx, ny, _ = domain.eps.shape
    area = (nx * domain.dx) * (ny * domain.dy)

    q = discrete_derivative_wavenumber(domain.k_inc_discrete, domain.dz)
    omega = domain.k0 * C_LIGHT

    S_inc = np.real(q) / (2.0 * omega * MU0 * domain.mu_bg)
    return float(np.real(S_inc * area))


# =============================================================================
# 12. R/T MODAL E ENERGÉTICO
# =============================================================================

def _decompose_ls_3d(F_values, z_values, k):
    M = np.column_stack([np.exp(1j * k * z_values), np.exp(-1j * k * z_values)])
    result, _, _, _ = np.linalg.lstsq(M, F_values, rcond=None)
    return result[0], result[1]


def compute_RT_specular_3d(result, n_points=5):
    """R/T modal especular: somente a componente média transversal."""
    domain = result["domain"]

    k = domain.k_inc_discrete
    dz = domain.dz

    Escat_avg = result["Escat"].mean(axis=(0, 1))
    Etotal_avg = result["Etotal"].mean(axis=(0, 1))

    zi = np.arange(domain.z_mon_in, domain.z_mon_in + n_points)
    A_in, B_in = _decompose_ls_3d(Escat_avg[zi], zi * dz, k)

    zo = np.arange(domain.z_mon_out, domain.z_mon_out + n_points)
    A_out, B_out = _decompose_ls_3d(Etotal_avg[zo], zo * dz, k)

    z_in_ref = domain.z_struct_start * dz

    r = B_in * np.exp(-2j * k * z_in_ref)
    t = A_out

    R = abs(r) ** 2
    T = abs(t) ** 2
    A = 1.0 - R - T

    return {
        "R_specular": float(R),
        "T_specular": float(T),
        "A_flux_specular": float(A),
        "r": r,
        "t": t,
    }


def compute_RT_power_3d(result, poynting):
    """R/T energético por Poynting, com P_inc da onda discreta do solver."""
    domain = result["domain"]

    dA = domain.dx * domain.dy

    P_inc = compute_discrete_incident_power(result)

    Pz_in = float(np.real(np.sum(poynting["S_z"][:, :, domain.z_mon_in]) * dA))
    Pz_out = float(np.real(np.sum(poynting["S_z"][:, :, domain.z_mon_out]) * dA))

    P_refl = P_inc - Pz_in
    P_trans = Pz_out

    R = P_refl / P_inc if P_inc > 0 else 0.0
    T = P_trans / P_inc if P_inc > 0 else 0.0
    A = 1.0 - R - T

    return {
        "P_inc": float(P_inc),
        "Pz_in": float(Pz_in),
        "Pz_out": float(Pz_out),
        "P_refl": float(P_refl),
        "P_trans": float(P_trans),
        "R_power": float(R),
        "T_power": float(T),
        "A_flux_power": float(A),
    }


# =============================================================================
# 13. ABSORÇÃO VOLUMÉTRICA
# =============================================================================

def compute_absorption_volume_3d(result):
    """q = ½ ω ε0 Im(ε) |E|² + ½ ω μ0 Im(μ) |H|²."""
    domain = result["domain"]

    omega = domain.k0 * C_LIGHT

    E = result["Etotal"]
    H = compute_H_fields_3d(result)

    H2 = np.abs(H["H_x"]) ** 2 + np.abs(H["H_y"]) ** 2 + np.abs(H["H_z"]) ** 2

    q_electric = 0.5 * omega * EPS0 * np.imag(domain.eps) * np.abs(E) ** 2
    q_magnetic = 0.5 * omega * MU0 * np.imag(domain.mu) * H2

    q_abs = np.real(q_electric) + np.real(q_magnetic)

    z0 = domain.z_struct_start
    z1 = domain.z_struct_end

    dV = domain.dx * domain.dy * domain.dz

    P_abs_total = float(np.sum(q_abs[:, :, z0:z1]) * dV)
    P_abs_electric = float(np.sum(np.real(q_electric[:, :, z0:z1])) * dV)
    P_abs_magnetic = float(np.sum(np.real(q_magnetic[:, :, z0:z1])) * dV)

    P_inc = compute_discrete_incident_power(result)

    A_volume = P_abs_total / P_inc if P_inc > 0 else 0.0

    return {
        "P_abs_total": P_abs_total,
        "P_abs_electric": P_abs_electric,
        "P_abs_magnetic": P_abs_magnetic,
        "P_inc": P_inc,
        "A_volume": float(np.real(A_volume)),
    }


# =============================================================================
# 14. ANÁLISE COMPLETA
# =============================================================================

def analyze_solution_3d(result):
    """1. R/T modal  2. R/T energético  3. absorção volumétrica  4. comparação."""
    rt_specular = compute_RT_specular_3d(result)
    poynting = compute_poynting_3d(result)
    rt_power = compute_RT_power_3d(result, poynting)
    abs_vol = compute_absorption_volume_3d(result)

    return {
        "RT_specular": rt_specular,
        "RT_power": rt_power,
        "absorption": {
            "A_volume": abs_vol["A_volume"],
            "A_difference_specular": abs(rt_specular["A_flux_specular"] - abs_vol["A_volume"]),
            "A_difference_power": abs(rt_power["A_flux_power"] - abs_vol["A_volume"]),
        },
        "residual": {"relative": result["relative_residual"]},
        "incident": {
            "k_continuous": result["domain"].k0 * result["domain"].n_bg * np.sqrt(result["domain"].mu_bg),
            "k_discrete": result["domain"].k_inc_discrete,
            "operator_residual": result["incident_operator_residual"],
        },
    }
