"""
fdfd2d.py — Solver FDFD 2D escalar (polarização TE_y, incidência normal) para o Nível 2 do UNIT-001.

REVISÃO v3:
 - Constantes físicas e regra dos monitores vêm de lib/geometry/unit001_constantes.py.
 - build_domain exige npml_cells e buffer_cells (sem valores padrão ocultos).
 - Bloco de validação deriva o buffer da regra dos monitores (buffer >= λ0 na malha do teste).

Resolve: d²E_y/dx² + d²E_y/dz² + k0² ε_r(x,z) E_y = 0
Método: campo espalhado. Borda em z: PML de coordenada esticada; lateral x: periódica.
"""

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from lib.geometry.unit001_constantes import (
    C_LIGHT,
    EPS0,
    MU0,
    Z0,
    MONITOR_OFFSET_FRAC,
    posicao_monitores,
)


def incident_power_flux(n_bg: complex) -> float:
    """P_inc = 0.5 Re(n_bg) / Z0 (W/m²) para onda plana de amplitude unitária."""
    return 0.5 * np.real(n_bg) / Z0


def pml_sfactors(N: int, npml: int, d: float, k0: float, m: int = 3,
                 R0: float = 1e-12) -> Tuple[np.ndarray, np.ndarray]:
    """Fatores de esticamento complexo nos N nós e nos N meios-pontos, com PML de npml células."""
    if npml <= 0:
        ones = np.ones(N, dtype=complex)
        return ones, ones

    smax = -(m + 1) * np.log(R0) / (2.0 * k0 * npml * d)
    idx = np.arange(N, dtype=float)
    idx_half = idx + 0.5

    def s_of(depth):
        depth = np.clip(depth, 0.0, 1.0)
        return 1.0 + 1j * smax * depth ** m

    s_node = np.ones(N, dtype=complex)
    s_node[:npml] = s_of((npml - idx[:npml]) / npml)
    s_node[N - npml:] = s_of((idx[N - npml:] - (N - npml - 1)) / npml)

    s_half = np.ones(N, dtype=complex)
    s_half[:npml] = s_of((npml - idx_half[:npml]) / npml)
    s_half[N - npml:] = s_of((idx_half[N - npml:] - (N - npml - 1)) / npml)

    return s_node, s_half


def _build_D_forward(N: int, d: float, periodic: bool) -> sp.csr_matrix:
    main = -np.ones(N) / d
    upper = np.ones(N - 1) / d
    D = sp.diags([main, upper], [0, 1], shape=(N, N), format="lil", dtype=complex)
    if periodic:
        D[N - 1, 0] = 1.0 / d
    return D.tocsr()


def build_D2(N: int, d: float, periodic: bool, npml: int, k0: float) -> sp.csr_matrix:
    Df = _build_D_forward(N, d, periodic)
    Db = -Df.T
    if periodic:
        s_node = np.ones(N, dtype=complex)
        s_half = np.ones(N, dtype=complex)
    else:
        s_node, s_half = pml_sfactors(N, npml, d, k0)
    return (sp.diags(1.0 / s_node) @ Db @ sp.diags(1.0 / s_half) @ Df).tocsr()


def build_D1(N: int, d: float, periodic: bool, npml: int, k0: float) -> sp.csr_matrix:
    Df = _build_D_forward(N, d, periodic)
    D1 = 0.5 * (Df + (-Df.T))
    if not periodic and npml > 0:
        s_node, _ = pml_sfactors(N, npml, d, k0)
        D1 = sp.diags(1.0 / s_node) @ D1
    return D1.tocsr()


@dataclass
class DomainSetup:
    eps: np.ndarray
    dx: float
    dz: float
    n_bg: complex
    z_struct_start: int
    z_struct_end: int
    z_mon_in: int
    z_mon_out: int
    npml: int
    k0: float
    wavelength: float


def build_domain(geom: Dict, wavelength: float, n_bg: complex,
                 npml_cells: int, buffer_cells: int) -> DomainSetup:
    nx, nz_struct = geom["nx"], geom["nz"]
    dx, dz = geom["dx"], geom["dz"]
    n_pad = npml_cells + buffer_cells
    nz_total = 2 * n_pad + nz_struct

    eps_full = np.full((nx, nz_total), n_bg ** 2, dtype=complex)
    eps_full[:, n_pad:n_pad + nz_struct] = geom["epsilon"]

    k0 = 2.0 * np.pi / wavelength
    z_mon_in, z_mon_out = posicao_monitores(npml_cells, buffer_cells, nz_struct, wavelength, dz)

    return DomainSetup(
        eps=eps_full, dx=dx, dz=dz, n_bg=n_bg,
        z_struct_start=n_pad, z_struct_end=n_pad + nz_struct,
        z_mon_in=z_mon_in, z_mon_out=z_mon_out,
        npml=npml_cells, k0=k0, wavelength=wavelength,
    )


def homogeneous_slab_geom(nx: int, nz: int, dx: float, dz: float, n_slab: complex) -> Dict:
    eps = np.full((nx, nz), n_slab ** 2, dtype=complex)
    return {"nx": nx, "nz": nz, "dx": dx, "dz": dz, "epsilon": eps}


def solve_fdfd(domain: DomainSetup) -> Dict:
    nx, nz = domain.eps.shape
    dx, dz = domain.dx, domain.dz
    k0 = domain.k0

    D2x = build_D2(nx, dx, periodic=True, npml=0, k0=k0)
    D2z = build_D2(nz, dz, periodic=False, npml=domain.npml, k0=k0)

    Lap = sp.kron(D2x, sp.identity(nz, format="csr"), format="csr") + \
        sp.kron(sp.identity(nx, format="csr"), D2z, format="csr")

    eps_flat = domain.eps.flatten(order="C")
    A = (Lap + (k0 ** 2) * sp.diags(eps_flat)).tocsc()

    z_axis = np.arange(nz) * dz
    Einc_z = np.exp(1j * k0 * domain.n_bg * z_axis)
    Einc = np.tile(Einc_z, (nx, 1))
    Einc_flat = Einc.flatten(order="C")

    eps_bg_flat = np.full(nx * nz, domain.n_bg ** 2, dtype=complex)
    b = -(k0 ** 2) * (eps_flat - eps_bg_flat) * Einc_flat

    Escat = spla.spsolve(A, b).reshape((nx, nz), order="C")
    return {"Etotal": Einc + Escat, "Escat": Escat, "Einc": Einc,
            "domain": domain, "z_axis": z_axis}


def _decompose_plane_waves(F1, F2, z1, z2, k):
    M = np.array([
        [np.exp(1j * k * z1), np.exp(-1j * k * z1)],
        [np.exp(1j * k * z2), np.exp(-1j * k * z2)],
    ], dtype=complex)
    A, B = np.linalg.solve(M, np.array([F1, F2], dtype=complex))
    return A, B


def compute_RT(result: Dict, mon_span: int = 5) -> Dict:
    domain = result["domain"]
    k = domain.k0 * domain.n_bg
    dz = domain.dz

    Escat_x_avg = result["Escat"].mean(axis=0)
    Etotal_x_avg = result["Etotal"].mean(axis=0)

    zi1, zi2 = domain.z_mon_in, domain.z_mon_in + mon_span
    A_in, B_in = _decompose_plane_waves(Escat_x_avg[zi1], Escat_x_avg[zi2], zi1 * dz, zi2 * dz, k)
    r = B_in

    zo1, zo2 = domain.z_mon_out, domain.z_mon_out + mon_span
    A_out, B_out = _decompose_plane_waves(Etotal_x_avg[zo1], Etotal_x_avg[zo2], zo1 * dz, zo2 * dz, k)
    t = A_out

    R = abs(r) ** 2
    T = abs(t) ** 2

    return {
        "R": R, "T": T, "A_flux": 1.0 - R - T,
        "r": r, "t": t,
        "leak_fwd_in": abs(A_in),
        "leak_bwd_out": abs(B_out),
    }


def _compute_derivatives(E: np.ndarray, dz: float, dx: float):
    dE_dz = np.zeros_like(E, dtype=complex)
    dE_dz[:, 1:-1] = (E[:, 2:] - E[:, :-2]) / (2 * dz)
    dE_dz[:, 0] = (E[:, 1] - E[:, 0]) / dz
    dE_dz[:, -1] = (E[:, -1] - E[:, -2]) / dz

    dE_dx = np.zeros_like(E, dtype=complex)
    dE_dx[1:-1, :] = (E[2:, :] - E[:-2, :]) / (2 * dx)
    dE_dx[0, :] = (E[1, :] - E[0, :]) / dx
    dE_dx[-1, :] = (E[-1, :] - E[-2, :]) / dx

    return dE_dz, dE_dx


def compute_H_fields(result: Dict) -> Dict:
    domain = result["domain"]
    E = result["Etotal"]
    dE_dz, dE_dx = _compute_derivatives(E, domain.dz, domain.dx)
    omega_mu = domain.k0 * C_LIGHT * MU0
    return {"H_x": -dE_dz / (1j * omega_mu), "H_z": dE_dx / (1j * omega_mu),
            "dE_dz": dE_dz, "dE_dx": dE_dx}


def compute_poynting(result: Dict) -> Dict:
    E = result["Etotal"]
    H = compute_H_fields(result)
    S_x_complex = E * np.conj(H["H_z"])
    S_z_complex = -E * np.conj(H["H_x"])
    return {"S_x": 0.5 * np.real(S_x_complex), "S_z": 0.5 * np.real(S_z_complex),
            "S_x_complex": S_x_complex, "S_z_complex": S_z_complex}


def compute_absorption_volume(result: Dict) -> Dict:
    domain = result["domain"]
    E = result["Etotal"]
    dx, dz = domain.dx, domain.dz
    omega = domain.k0 * C_LIGHT

    P_abs_density = 0.5 * omega * EPS0 * np.imag(domain.eps) * np.abs(E) ** 2
    P_abs_total = np.sum(P_abs_density) * dx * dz

    Lx = domain.eps.shape[0] * dx
    P_inc = incident_power_flux(domain.n_bg) * Lx
    A_volume = P_abs_total / P_inc

    return {"P_abs_density": P_abs_density, "P_abs_total": P_abs_total,
            "A_volume": A_volume, "P_inc": P_inc}


def analytic_slab_RT(wavelength: float, n_bg: complex, n_slab: complex, thickness: float) -> Dict:
    k0 = 2.0 * np.pi / wavelength
    k1 = k0 * n_slab
    r12 = (n_bg - n_slab) / (n_bg + n_slab)
    phase = np.exp(2j * k1 * thickness)
    r = r12 * (1.0 - phase) / (1.0 - r12 ** 2 * phase)
    t = (1.0 - r12 ** 2) * np.exp(1j * k1 * thickness) / (1.0 - r12 ** 2 * phase)
    R = abs(r) ** 2
    T = abs(t) ** 2
    return {"R": R, "T": T, "A_flux": 1.0 - R - T, "r": r, "t": t}


def validate_homogeneous_slab(wavelength: float, n_bg: complex, n_slab: complex,
                              thickness: float, resolution_ppw: float,
                              npml_cells: int, buffer_cells: int, nx: int) -> Dict:
    dz = wavelength / (max(abs(n_bg), abs(n_slab)) * resolution_ppw)
    dx = dz
    nz_struct = max(4, int(round(thickness / dz)))
    geom = homogeneous_slab_geom(nx, nz_struct, dx, dz, n_slab)
    domain = build_domain(geom, wavelength, n_bg=n_bg,
                          npml_cells=npml_cells, buffer_cells=buffer_cells)
    result = solve_fdfd(domain)

    rt_fdfd = compute_RT(result)
    abs_data = compute_absorption_volume(result)
    rt_analytic = analytic_slab_RT(wavelength, n_bg, n_slab, nz_struct * dz)

    dR = abs(rt_fdfd["R"] - rt_analytic["R"])
    dT = abs(rt_fdfd["T"] - rt_analytic["T"])

    return {"fdfd": rt_fdfd, "analytic": rt_analytic, "dR": dR, "dT": dT,
            "A_volume": abs_data["A_volume"],
            "A_difference": abs(rt_fdfd["A_flux"] - abs_data["A_volume"])}


if __name__ == "__main__":
    # Lâmina de validação: o buffer é derivado da regra dos monitores, nunca fixo.
    VAL_WAVELENGTH = 1.0e-6
    VAL_N_BG = 1.0
    VAL_N_SLAB = 2.0
    VAL_THICKNESS = 0.3e-6
    VAL_PPW = 30
    VAL_NPML = 25
    VAL_NX = 8

    dz_val = VAL_WAVELENGTH / (max(abs(VAL_N_BG), abs(VAL_N_SLAB)) * VAL_PPW)
    VAL_BUFFER = math.ceil(VAL_WAVELENGTH / dz_val)   # >= 2·d, com d = λ0/(2·dz)

    res = validate_homogeneous_slab(
        VAL_WAVELENGTH, VAL_N_BG, VAL_N_SLAB, VAL_THICKNESS,
        VAL_PPW, VAL_NPML, VAL_BUFFER, VAL_NX,
    )
    print(f"|ΔR| = {res['dR']:.2e} | |ΔT| = {res['dT']:.2e} | "
          f"|A_flux - A_volume| = {res['A_difference']:.2e}")


def compute_absorption_distribution(result):
    domain = result["domain"]
    abs_data = compute_absorption_volume(result)
    P_abs = abs_data["P_abs_density"]
    nx, nz = P_abs.shape
    x = np.arange(nx) * domain.dx
    z = np.arange(nz) * domain.dz
    X, Z = np.meshgrid(x, z, indexing="ij")
    total_abs = np.sum(P_abs)
    if total_abs > 1e-20:
        x_centroid = np.sum(X * P_abs) / total_abs
        z_centroid = np.sum(Z * P_abs) / total_abs
        x_sigma = np.sqrt(np.sum((X - x_centroid) ** 2 * P_abs) / total_abs)
        z_sigma = np.sqrt(np.sum((Z - z_centroid) ** 2 * P_abs) / total_abs)
    else:
        x_centroid = z_centroid = x_sigma = z_sigma = 0.0
    return {"x_centroid": x_centroid, "z_centroid": z_centroid,
            "x_sigma": x_sigma, "z_sigma": z_sigma, "total_absorption": total_abs}


def compute_diffraction_spectrum(result, z_monitor=None):
    domain = result["domain"]
    E = result["Etotal"]
    if z_monitor is None:
        z_monitor = domain.z_mon_out
    E_slice = E[:, z_monitor]
    E_fft = np.fft.fftshift(np.fft.fft(E_slice))
    nx = len(E_slice)
    L_x = nx * domain.dx
    m = np.arange(-nx // 2, nx // 2)
    kx = np.fft.fftshift(2 * np.pi * m / L_x)
    k_bg = domain.k0 * domain.n_bg
    kz = np.sqrt(k_bg ** 2 - kx ** 2 + 0j)
    propagating = np.abs(np.imag(kz)) < 1e-9 * abs(k_bg)
    power = np.abs(E_fft) ** 2
    total = np.sum(power)
    power_relative = power / total if total > 0 else power
    return {"m": m, "kx": kx, "kz": kz, "power": power,
            "power_relative": power_relative, "propagating": propagating,
            "z_monitor": z_monitor}


def analyze_solution(result):
    domain = result["domain"]
    rt_modal = compute_RT(result)
    poynting = compute_poynting(result)
    S_z = poynting["S_z"]
    Sz_in = np.mean(S_z[:, domain.z_mon_in])
    Sz_out = np.mean(S_z[:, domain.z_mon_out])
    P_inc = incident_power_flux(domain.n_bg)
    T_poynting = Sz_out / P_inc
    R_poynting = (P_inc - Sz_in) / P_inc
    abs_data = compute_absorption_volume(result)
    abs_dist = compute_absorption_distribution(result)
    diffraction = compute_diffraction_spectrum(result)
    A_difference = abs(rt_modal["A_flux"] - abs_data["A_volume"])
    return {
        "RT": {**rt_modal, "R_poynting": R_poynting, "T_poynting": T_poynting,
               "leak_in": rt_modal["leak_fwd_in"], "leak_out": rt_modal["leak_bwd_out"]},
        "absorption": {"A_volume": abs_data["A_volume"],
                       "P_abs_total": abs_data["P_abs_total"], "A_difference": A_difference},
        "absorption_distribution": abs_dist,
        "diffraction": {"outgoing": diffraction},
        "poynting": poynting,
        "H_fields": compute_H_fields(result),
    }
