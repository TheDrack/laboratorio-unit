"""
fdfd_adapter.py
UNIT-001 — FASE 4: ADAPTADOR FDFD → ARQUITETURA CANÔNICA
"""
from __future__ import annotations
from typing import Dict, Optional, Tuple
import numpy as np

from lib.core.wave_state import WaveState
from lib.core.material_state import MaterialState
from lib.core.energy_state import (
    EnergyLedger,
    EnergyChannel,
    compute_em_channels,
    compute_thermal_channels,
)
from lib.geometry.unit001_constantes import (C_LIGHT, EPS0, MU0)



def compute_q_abs_density(result: Dict) -> np.ndarray:
    """q_abs(r) = 0.5 * ω * ε₀ * Im(ε_r) * |E_total|²"""
    domain = result["domain"]
    omega = domain.k0 * C_LIGHT
    E = result["Etotal"]
    return np.real(0.5 * omega * EPS0 * np.imag(domain.eps) * np.abs(E) ** 2)


def compute_poynting_vectors(result: Dict) -> Dict[str, np.ndarray]:
    from lib.solvers.fdfd3d import compute_poynting_3d
    poynting = compute_poynting_3d(result)
    return {"x": poynting["S_x"], "y": poynting["S_y"], "z": poynting["S_z"]}


def compute_h_fields(result: Dict) -> Dict[str, np.ndarray]:
    from lib.solvers.fdfd3d import compute_H_fields_3d
    H_fields = compute_H_fields_3d(result)
    return {"x": H_fields["H_x"], "y": H_fields["H_y"], "z": H_fields["H_z"]}


def fdfd_result_to_wave_state(
    result: Dict,
    analysis: Optional[Dict] = None,
) -> WaveState:
    """Converte saída do FDFD 3D em WaveState canônico, enviando TODOS os metadados."""
    domain = result["domain"]
    
    if analysis is None:
        from lib.solvers.fdfd3d import analyze_solution_3d
        analysis = analyze_solution_3d(result)
    
    # Campos
    E_fields = {"y": result["Etotal"]}
    H_fields = compute_h_fields(result)
    S_fields = compute_poynting_vectors(result)
    q_abs = compute_q_abs_density(result)
    
    # METADADOS (o WaveState atual ACEITA estes campos)
    P_incident = float(analysis["RT_power"]["P_inc"])
    n_bg = complex(domain.n_bg)
    z_mon_in = domain.z_mon_in
    z_mon_out = domain.z_mon_out
    z_struct_start = domain.z_struct_start
    z_struct_end = domain.z_struct_end
    
    # Diagnósticos
    solver_residual = float(result.get("relative_residual", np.nan))
    # CORRIGIDO: o antigo |R+T+A_flux-1| era tautológico (A_flux_power é
    # definido como 1-R-T, então dava 0 sempre, qualquer que fosse a
    # qualidade da solução). O fechamento real compara duas medidas
    # INDEPENDENTES da mesma absorção: balanço de fluxo (A_flux_power) vs
    # integração de campo no volume (A_volume).
    A_flux_power = float(analysis["RT_power"]["A_flux_power"])
    A_volume = float(analysis["absorption"]["A_volume"])
    energy_closure_error = abs(A_flux_power - A_volume)
    
    # Construir WaveState ENVIANDO TODOS OS METADADOS
    wave_state = WaveState(
        dx=domain.dx,
        dy=domain.dy,
        dz=domain.dz,
        omega=domain.k0 * C_LIGHT,
        E=E_fields,
        H=H_fields,
        S=S_fields,
        q_abs=q_abs,
        P_incident=P_incident,
        n_bg=n_bg,
        z_mon_in=z_mon_in,
        z_mon_out=z_mon_out,
        z_struct_start=z_struct_start,
        z_struct_end=z_struct_end,
        solver_residual=solver_residual,
        energy_closure_error=energy_closure_error,
    )
    
    return wave_state


def build_energy_ledger_from_fdfd(
    result: Dict,
    analysis: Optional[Dict] = None,
    material_state: Optional[MaterialState] = None,
    include_thermal: bool = False,
) -> Tuple[WaveState, EnergyLedger]:
    """Constrói WaveState + EnergyLedger a partir do resultado FDFD."""
    wave_state = fdfd_result_to_wave_state(result, analysis)
    em_channels = compute_em_channels(wave_state)
    
    thermal_channels = {}
    if include_thermal:
        if material_state is None or material_state.k_thermal <= 0:
            raise ValueError("include_thermal=True requer material_state com k_thermal > 0")
        thermal_channels = compute_thermal_channels(wave_state, material_state.k_thermal)
    
    ledger = EnergyLedger(
        channels={**em_channels, **thermal_channels},
        P_incident=wave_state.P_incident,
    )
    
    return wave_state, ledger


def validate_fdfd_wave_state(wave_state: WaveState, tol_closure: float = 1e-5) -> Dict:
    validations = {
        "energy_closure": {
            "passed": wave_state.energy_closure_error < tol_closure,
            "value": wave_state.energy_closure_error,
        },
        "solver_residual": {
            "passed": wave_state.solver_residual < 1e-10,
            "value": wave_state.solver_residual,
        },
    }
    validations["overall"] = {"passed": all(v["passed"] for v in validations.values())}
    return validations