"""
fdtd_adapter.py
===============

UNIT-001 — ADAPTADOR FDTD → ARQUITETURA CANÔNICA

Responsabilidade
----------------
Adaptar a saída do FDTD (fdtd3d.py) para:

    FDTD
      ↓
    WaveState
      ↓
    EnergyLedger

IMPORTANTE
----------
O FDTD atual (fdtd3d.py) fornece, por frequência, apenas R/T/A escalares —
via spectral_sweep_cw() (varredura) ou run_cw_single_frequency() (um único
ponto). Ele NÃO fornece E, H, S ou q_abs espaciais ainda (isso exigiria
extrair fasores por DFT durante a simulação, não implementado). Portanto
este adapter NÃO inventa campos espaciais: WaveState.E/H ficam vazios,
S/q_abs ficam None.

A absorção A é interpretada como A = 1 - R - T (fechamento energético
global). Consequentemente A_volume e Delta_A ficam NaN nos diagnósticos até
o solver FDTD fornecer os campos necessários para uma medida independente.

=============================== CORREÇÕES NESTA REVISÃO =========================
1. EnergyLedger(... diagnostics=...) — o EnergyLedger em energy_state.py não
   tinha campo `diagnostics`; toda chamada a build_energy_ledger_from_fdtd
   quebrava com TypeError. Corrigido em energy_state.py (campo adicionado,
   retrocompatível).
2. _clip_small_negative usava tolerância fixa 1e-12 enquanto
   _validate_energy_fractions validava contra closure_tolerance (default
   1e-7) — um resíduo entre 1e-12 e 1e-7 passava sem ser zerado. Agora as
   duas usam a MESMA tolerância.
3. Adicionado domain_info_from_fdtd_domain(): não existia nenhum conversor
   de FDTDDomain (o dataclass real de fdtd3d.py) para o dict domain_info
   que este adapter espera — e FDTDDomain usa `delta` (malha cúbica única),
   não dx/dy/dz separados, então montar esse dict à mão era fonte fácil de
   erro de nome.
4. extract_fdtd_frequency_point agora aceita tanto o retorno de
   spectral_sweep_cw() (arrays, chave "frequency") quanto de
   run_cw_single_frequency() (escalares, chave "f0") — antes só o primeiro
   formato funcionava, apesar de os dois serem igualmente validados em
   fdtd3d.py.
5. frequency_index agora aceita índices negativos (convenção Python), antes
   rejeitados com IndexError.
==================================================================================
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

from lib.core.wave_state import WaveState
from lib.core.energy_state import EnergyChannel, EnergyLedger
from lib.geometry.unit001_constantes import NPML_CELLS, BUFFER_CELLS
from lib.geometry.unit001_constantes import (C_LIGHT)
from lib.geometry.unit001_constantes import (PPW_FDTD)


# =============================================================================
# CONSTANTES
# =============================================================================



# =============================================================================
# UTILITÁRIOS
# =============================================================================

def _as_1d_array(value: Any, name: str) -> np.ndarray:
    """Converte uma entrada (array ou escalar) em array 1D float."""
    arr = np.atleast_1d(np.asarray(value, dtype=float))

    if arr.ndim != 1:
        raise ValueError(f"'{name}' deve ser um array 1D. Recebido shape={arr.shape}.")
    if arr.size == 0:
        raise ValueError(f"'{name}' não pode ser vazio.")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"'{name}' contém valores não finitos.")
    return arr


def _normalize_fdtd_result(fdtd_result: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """
    CORRIGIDO: normaliza os dois formatos de retorno do fdtd3d.py para um
    único esquema (arrays, chave "frequency") antes de extrair um ponto:

        spectral_sweep_cw()        -> {"frequency","wavelength","R","T","A"} (arrays)
        run_cw_single_frequency()  -> {"f0","wavelength","R","T","A", ...}   (escalares)

    Sem isso, um resultado de run_cw_single_frequency (igualmente validado
    em fdtd3d.py) era rejeitado com KeyError só por causa do nome da chave.
    """
    if not isinstance(fdtd_result, dict):
        raise TypeError("fdtd_result deve ser um dicionário.")

    if "frequency" in fdtd_result:
        frequency = fdtd_result["frequency"]
    elif "f0" in fdtd_result:
        frequency = fdtd_result["f0"]
    else:
        raise KeyError(
            "fdtd_result não contém 'frequency' (spectral_sweep_cw) "
            "nem 'f0' (run_cw_single_frequency)."
        )

    required_rest = ("wavelength", "R", "T", "A")
    missing = [k for k in required_rest if k not in fdtd_result]
    if missing:
        raise KeyError("fdtd_result não contém os campos obrigatórios: " + ", ".join(missing))

    return {
        "frequency": _as_1d_array(frequency, "frequency"),
        "wavelength": _as_1d_array(fdtd_result["wavelength"], "wavelength"),
        "R": _as_1d_array(fdtd_result["R"], "R"),
        "T": _as_1d_array(fdtd_result["T"], "T"),
        "A": _as_1d_array(fdtd_result["A"], "A"),
    }


def _validate_frequency_index(frequency_index: int, n_points: int) -> int:
    """Valida e normaliza o índice espectral. CORRIGIDO: aceita índices
    negativos (convenção Python, ex. -1 para o último ponto)."""
    if not isinstance(frequency_index, (int, np.integer)):
        raise TypeError("frequency_index deve ser inteiro.")

    index = int(frequency_index)
    normalized = index if index >= 0 else index + n_points

    if normalized < 0 or normalized >= n_points:
        raise IndexError(
            f"frequency_index={index} fora do intervalo [-{n_points}, {n_points - 1}]."
        )
    return normalized


def _validate_domain_info(domain_info: Dict[str, Any]) -> None:
    """Valida os metadados espaciais necessários pelo WaveState."""
    required = ("dx", "dy", "dz", "nx", "ny", "nz",
                "z_mon_in", "z_mon_out", "z_struct_start", "z_struct_end")
    missing = [key for key in required if key not in domain_info]
    if missing:
        raise KeyError("domain_info não contém os campos obrigatórios: " + ", ".join(missing))

    for key in ("dx", "dy", "dz"):
        value = float(domain_info[key])
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"domain_info['{key}'] deve ser positivo e finito.")

    for key in ("nx", "ny", "nz", "z_mon_in", "z_mon_out", "z_struct_start", "z_struct_end"):
        value = domain_info[key]
        if not isinstance(value, (int, np.integer)):
            raise TypeError(f"domain_info['{key}'] deve ser inteiro.")


def domain_info_from_fdtd_domain(domain: Any) -> Dict[str, Any]:
    """
    CORRIGIDO (não existia): constrói o dict domain_info esperado por este
    adapter a partir de um FDTDDomain real (fdtd3d.py). FDTDDomain usa uma
    malha cúbica única (`delta`), não dx/dy/dz separados — este builder
    evita que quem for usar o adapter tenha que lembrar disso e errar o
    nome do atributo.
    """
    return {
        "dx": float(domain.delta), "dy": float(domain.delta), "dz": float(domain.delta),
        "nx": int(domain.nx), "ny": int(domain.ny), "nz": int(domain.nz),
        "z_mon_in": int(domain.z_mon_in), "z_mon_out": int(domain.z_mon_out),
        "z_struct_start": int(domain.z_struct_start), "z_struct_end": int(domain.z_struct_end),
    }


def _clip_small_negative(value: float, tolerance: float) -> float:
    """Remove pequenos resíduos negativos numéricos. CORRIGIDO: tolerance
    agora é sempre a MESMA passada para _validate_energy_fractions (antes
    era um valor fixo 1e-12, dessincronizado do closure_tolerance real)."""
    value = float(value)
    if value < 0.0 and abs(value) <= tolerance:
        return 0.0
    return value


def _validate_energy_fractions(R: float, T: float, A: float, tolerance: float) -> None:
    """
    Valida R, T e A. NOTA DE HONESTIDADE: como A é calculado a montante
    (fdtd3d.py) como 1-R-T, "R+T+A≈1" aqui é uma checagem tautológica — não
    pode falhar por construção, então não é uma validação física
    independente (mesma armadilha já corrigida em fdfd2d.py para o
    "energy_error"). Mantida apenas como tripwire de sanidade contra dados
    corrompidos/mal formados chegando de fora do pipeline normal.
    """
    values = {"R": R, "T": T, "A": A}
    for name, value in values.items():
        if not np.isfinite(value):
            raise ValueError(f"{name} não é finito: {value}")
        if value < -tolerance:
            raise ValueError(f"{name} é fisicamente inválido: {value:.12e}")

    closure = R + T + A
    if not np.isclose(closure, 1.0, rtol=0.0, atol=tolerance):
        raise ValueError(f"Falha no fechamento energético FDTD: R + T + A = {closure:.12e}")


# =============================================================================
# EXTRAÇÃO DE UM PONTO ESPECTRAL
# =============================================================================

def extract_fdtd_frequency_point(
    fdtd_result: Dict[str, Any],
    frequency_index: int,
    closure_tolerance: float = 1e-7,
) -> Dict[str, float]:
    """
    Extrai um ponto espectral do resultado de spectral_sweep_cw() OU de
    run_cw_single_frequency() (ver _normalize_fdtd_result).
    """
    normalized = _normalize_fdtd_result(fdtd_result)
    n_points = normalized["frequency"].size

    for name in ("wavelength", "R", "T", "A"):
        if normalized[name].size != n_points:
            raise ValueError(
                f"'{name}' possui {normalized[name].size} pontos, mas 'frequency' possui {n_points}."
            )

    index = _validate_frequency_index(frequency_index, n_points)

    f = float(normalized["frequency"][index])
    wavelength_value = float(normalized["wavelength"][index])

    R = _clip_small_negative(float(normalized["R"][index]), closure_tolerance)
    T = _clip_small_negative(float(normalized["T"][index]), closure_tolerance)
    A = _clip_small_negative(float(normalized["A"][index]), closure_tolerance)

    closure = R + T + A
    closure_error = closure - 1.0

    _validate_energy_fractions(R, T, A, tolerance=closure_tolerance)

    omega = 2.0 * np.pi * f

    return {
        "frequency": f, "wavelength": wavelength_value,
        "R": R, "T": T, "A": A,
        "omega": omega, "energy_closure_error": closure_error,
    }


# =============================================================================
# FDTD → WAVESTATE
# =============================================================================

def fdtd_result_to_wave_state(
    fdtd_result: Dict[str, Any],
    frequency_index: int,
    domain_info: Dict[str, Any],
    n_bg: complex = 1.0 + 0.0j,
    P_incident: float = 1.0,
    closure_tolerance: float = 1e-7,
) -> WaveState:
    """Converte um ponto espectral FDTD em WaveState canônico. Como o FDTD
    ainda não fornece campos espaciais, E/H/S/q_abs ficam vazios/None."""
    _validate_domain_info(domain_info)

    if not np.isfinite(P_incident) or P_incident <= 0.0:
        raise ValueError("P_incident deve ser finito e > 0.")

    point = extract_fdtd_frequency_point(fdtd_result, frequency_index, closure_tolerance)

    return WaveState(
        dx=float(domain_info["dx"]), dy=float(domain_info["dy"]), dz=float(domain_info["dz"]),
        omega=float(point["omega"]),
        E={}, H={}, S=None, q_abs=None,
        P_incident=float(P_incident),
        n_bg=complex(n_bg),
        z_mon_in=int(domain_info["z_mon_in"]), z_mon_out=int(domain_info["z_mon_out"]),
        z_struct_start=int(domain_info["z_struct_start"]), z_struct_end=int(domain_info["z_struct_end"]),
        solver_residual=float("nan"),  # o solver atual não expõe resíduo
        energy_closure_error=float(point["energy_closure_error"]),
    )


# =============================================================================
# FDTD → ENERGY LEDGER
# =============================================================================

def build_energy_ledger_from_fdtd(
    fdtd_result: Dict[str, Any],
    frequency_index: int,
    domain_info: Dict[str, Any],
    n_bg: complex = 1.0 + 0.0j,
    P_incident: float = 1.0,
    closure_tolerance: float = 1e-7,
) -> Tuple[WaveState, EnergyLedger]:
    """Constrói WaveState + EnergyLedger a partir de um ponto espectral FDTD."""
    point = extract_fdtd_frequency_point(fdtd_result, frequency_index, closure_tolerance)
    wave_state = fdtd_result_to_wave_state(
        fdtd_result, frequency_index, domain_info, n_bg, P_incident, closure_tolerance
    )

    P_inc = float(P_incident)
    meta_common = {
        "solver": "FDTD", "frequency_hz": point["frequency"], "wavelength_m": point["wavelength"],
    }

    channels = {
        "R": EnergyChannel(
            name="R", power_watts=point["R"] * P_inc, fraction_of_incident=point["R"],
            metadata={**meta_common, "method": "CW_amplitude_ratio"},
            mechanism="same_channel",
        ),
        "T": EnergyChannel(
            name="T", power_watts=point["T"] * P_inc, fraction_of_incident=point["T"],
            metadata={**meta_common, "method": "CW_amplitude_ratio"},
            mechanism="same_channel",
        ),
        "A": EnergyChannel(
            name="A", power_watts=point["A"] * P_inc, fraction_of_incident=point["A"],
            metadata={**meta_common, "method": "energy_closure", "definition": "A = 1 - R - T"},
            # ainda não sabemos SE essa energia vira calor de fato (o FDTD não
            # mede q_abs independentemente ainda) -- ver nota em
            # extract_fdtd_frequency_point sobre o fechamento ser tautológico.
            mechanism="conversion", source_channel="EM", target_channel="thermal",
        ),
    }

    # CORRIGIDO: EnergyLedger agora aceita diagnostics (energy_state.py foi
    # estendido) -- antes esta chamada quebrava com TypeError sempre.
    ledger = EnergyLedger(
        P_incident=P_inc,
        channels=channels,
        diagnostics={
            "R": point["R"], "T": point["T"], "A_flux": point["A"],
            # Não disponíveis no solver FDTD atual (sem campos espaciais):
            "A_volume": float("nan"), "Delta_A": float("nan"),
            "P_incident": P_inc, "P_reflected": point["R"] * P_inc,
            "P_transmitted": point["T"] * P_inc, "P_absorbed": point["A"] * P_inc,
            "frequency_hz": point["frequency"], "wavelength_m": point["wavelength"],
            "omega_rad_s": point["omega"],
            "energy_closure_error": point["energy_closure_error"],
        },
    )
    return wave_state, ledger


# =============================================================================
# VALIDAÇÃO
# =============================================================================

def validate_fdtd_wave_state(
    wave_state: WaveState, ledger: EnergyLedger, closure_tolerance: float = 1e-7
) -> bool:
    """Valida coerência entre WaveState e EnergyLedger."""
    if not isinstance(wave_state, WaveState):
        raise TypeError("wave_state deve ser WaveState.")
    if not isinstance(ledger, EnergyLedger):
        raise TypeError("ledger deve ser EnergyLedger.")

    if not np.isclose(wave_state.P_incident, ledger.P_incident, rtol=0.0, atol=0.0):
        raise ValueError("P_incident inconsistente entre WaveState e EnergyLedger.")

    for name in ("R", "T", "A"):
        if name not in ledger.channels:
            raise KeyError(f"EnergyLedger não contém canal '{name}'.")

    R = float(ledger.channels["R"].fraction_of_incident)
    T = float(ledger.channels["T"].fraction_of_incident)
    A = float(ledger.channels["A"].fraction_of_incident)
    closure = R + T + A

    if not np.isclose(closure, 1.0, rtol=0.0, atol=closure_tolerance):
        raise ValueError(f"EnergyLedger FDTD não fecha energia: R + T + A = {closure:.12e}")

    if not np.isclose(wave_state.energy_closure_error, closure - 1.0, rtol=0.0, atol=closure_tolerance):
        raise ValueError("energy_closure_error inconsistente.")

    return True


# =============================================================================
# RESUMO
# =============================================================================

def summarize_fdtd_frequency(ledger: EnergyLedger) -> Dict[str, float]:
    """Retorna um resumo numérico simples do ponto espectral."""
    if not isinstance(ledger, EnergyLedger):
        raise TypeError("ledger deve ser EnergyLedger.")
    return {
        "P_incident": float(ledger.P_incident),
        "R": float(ledger.channels["R"].fraction_of_incident),
        "T": float(ledger.channels["T"].fraction_of_incident),
        "A": float(ledger.channels["A"].fraction_of_incident),
        "energy_closure_error": float(ledger.diagnostics.get("energy_closure_error", np.nan)),
    }


__all__ = [
    "extract_fdtd_frequency_point",
    "fdtd_result_to_wave_state",
    "build_energy_ledger_from_fdtd",
    "validate_fdtd_wave_state",
    "summarize_fdtd_frequency",
    "domain_info_from_fdtd_domain",
]


if __name__ == "__main__":
    import lib.solvers.fdtd3d as fdtd3d

    print("=" * 90)
    print("TESTE fdtd_adapter.py — lâmina homogênea, um único ponto CW e uma varredura")
    print("=" * 90)

    N_BG, N_SLAB, LAMBDA0, THICKNESS = 1.0, 2.0, 1.0e-6, 0.3e-6
    dz = LAMBDA0 / (N_SLAB * 20)
    nz = max(1, int(round(THICKNESS / dz)))
    eps_cell = fdtd3d.homogeneous_slab_eps(4, 4, nz, N_SLAB)
    domain = fdtd3d.build_fdtd_domain(eps_cell, LAMBDA0, n_bg=N_BG, npml=NPML_CELLS, buffer_cells=BUFFER_CELLS, resolution_ppw=PPW_FDTD)
    domain_info = domain_info_from_fdtd_domain(domain)

    print("\n-- run_cw_single_frequency (formato 'f0', escalares) --")
    r_single = fdtd3d.run_cw_single_frequency(domain, fdtd3d.C_LIGHT / LAMBDA0, n_cycles_total=25)
    ws1, ledger1 = build_energy_ledger_from_fdtd(r_single, 0, domain_info)
    validate_fdtd_wave_state(ws1, ledger1)
    print(summarize_fdtd_frequency(ledger1))

    print("\n-- spectral_sweep_cw (formato 'frequency', arrays) --")
    freqs = fdtd3d.C_LIGHT / np.array([0.9e-6, 1.0e-6, 1.1e-6])
    r_sweep = fdtd3d.spectral_sweep_cw(domain, freqs, verbose=False, n_cycles_total=25)
    ws2, ledger2 = build_energy_ledger_from_fdtd(r_sweep, -1, domain_info, closure_tolerance=1e-3)
    # tolerância mais frouxa aqui só porque n_cycles_total=25 é baixo (demo
    # rápida) -- ruído numérico do CW nesse ponto (R pequeno) passa de 1e-7
    validate_fdtd_wave_state(ws2, ledger2, closure_tolerance=1e-3)
    print(summarize_fdtd_frequency(ledger2))

    print("\nOK — os dois formatos de resultado do fdtd3d.py foram aceitos sem erro.")
