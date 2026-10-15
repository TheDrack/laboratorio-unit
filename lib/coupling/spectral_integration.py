"""
spectral_integration.py
================================================================================
UNIT-001 — INTEGRAÇÃO ESPECTRAL FDFD ↔ FDTD
================================================================================

Fornece funções para comparar as respostas espectrais (R, T, A) obtidas
pelos solvers FDFD (multifrequência) e FDTD-CW (extração espectral).

Funções principais:
    - compare_energy_responses(): calcula diferenças absolutas e relativas
    - print_energy_comparison_report(): imprime relatório formatado

Uso típico (Fase 9):
    comparison = compare_energy_responses(
        fdfd_frequency=frequencies,
        fdfd_R=fdfd_R, fdfd_T=fdfd_T,
        fdtd_frequency=frequencies,
        fdtd_R=fdtd_R, fdtd_T=fdtd_T,
    )
    print_energy_comparison_report(comparison)
================================================================================
"""
from __future__ import annotations

from typing import Dict
import numpy as np


def compare_energy_responses(
    fdfd_frequency: np.ndarray,
    fdfd_R: np.ndarray,
    fdfd_T: np.ndarray,
    fdtd_frequency: np.ndarray,
    fdtd_R: np.ndarray,
    fdtd_T: np.ndarray,
    n_points: int = 3,
) -> Dict:
    """
    Compara as respostas espectrais de FDFD e FDTD nas mesmas frequências.

    Args:
        fdfd_frequency: array de frequências do FDFD (Hz)
        fdfd_R: reflectância FDFD
        fdfd_T: transmitância FDFD
        fdtd_frequency: array de frequências do FDTD (Hz)
        fdtd_R: reflectância FDTD
        fdtd_T: transmitância FDTD
        n_points: número de pontos (deve coincidir com len dos arrays)

    Returns:
        Dict com:
            "frequencies": frequências usadas (Hz)
            "dR": diferença R_FDFD - R_FDTD
            "dT": diferença T_FDFD - T_FDTD
            "dR_rel": diferença relativa |dR| / max(|R_FDFD|, eps)
            "dT_rel": diferença relativa |dT| / max(|T_FDFD|, eps)
            "dR_abs_max": máximo de |dR|
            "dT_abs_max": máximo de |dT|
            "mean_dR": média de |dR|
            "mean_dT": média de |dT|
            "n_points": número de pontos comparados
    """
    fdfd_frequency = np.asarray(fdfd_frequency)
    fdtd_frequency = np.asarray(fdtd_frequency)
    fdfd_R = np.asarray(fdfd_R)
    fdfd_T = np.asarray(fdfd_T)
    fdtd_R = np.asarray(fdtd_R)
    fdtd_T = np.asarray(fdtd_T)

    if len(fdfd_frequency) != len(fdtd_frequency):
        raise ValueError(
            f"Arrays de frequência têm tamanhos diferentes: "
            f"FDFD={len(fdfd_frequency)}, FDTD={len(fdtd_frequency)}"
        )

    if not np.allclose(fdfd_frequency, fdtd_frequency, rtol=1e-10):
        raise ValueError(
            "Arrays de frequência não coincidem. "
            "Ambos os solvers devem ser avaliados nas mesmas frequências."
        )

    n = len(fdfd_frequency)
    if n != n_points:
        raise ValueError(
            f"n_points={n_points} não coincide com len(frequencies)={n}"
        )

    # Diferenças absolutas
    dR = fdfd_R - fdtd_R
    dT = fdfd_T - fdtd_T

    # Diferenças relativas (evitar divisão por zero)
    eps = 1e-30
    dR_rel = np.abs(dR) / np.maximum(np.abs(fdfd_R), eps)
    dT_rel = np.abs(dT) / np.maximum(np.abs(fdfd_T), eps)

    return {
        "frequencies": fdfd_frequency,
        "dR": dR,
        "dT": dT,
        "dR_rel": dR_rel,
        "dT_rel": dT_rel,
        "dR_abs_max": float(np.max(np.abs(dR))),
        "dT_abs_max": float(np.max(np.abs(dT))),
        "mean_dR": float(np.mean(np.abs(dR))),
        "mean_dT": float(np.mean(np.abs(dT))),
        "n_points": n,
    }


def print_energy_comparison_report(comparison: Dict) -> None:
    """
    Imprime relatório formatado da comparação espectral.
    """
    frequencies = comparison["frequencies"]
    dR = comparison["dR"]
    dT = comparison["dT"]
    n = comparison["n_points"]

    print("\n" + "-" * 90)
    print("RELATÓRIO DE COMPARAÇÃO ESPECTRAL FDFD ↔ FDTD")
    print("-" * 90)
    print(f"{'Frequência (THz)':>20} | {'ΔR':>12} | {'ΔT':>12} | {'|ΔR|_rel':>12} | {'|ΔT|_rel':>12}")
    print("-" * 90)

    for i in range(n):
        f_thz = frequencies[i] / 1e12
        print(
            f"{f_thz:>20.2f} | "
            f"{dR[i]:>+12.5f} | "
            f"{dT[i]:>+12.5f} | "
            f"{comparison['dR_rel'][i]:>12.2%} | "
            f"{comparison['dT_rel'][i]:>12.2%}"
        )

    print("-" * 90)
    print(f"{'Máximo |ΔR|':>20} = {comparison['dR_abs_max']:.2%}")
    print(f"{'Máximo |ΔT|':>20} = {comparison['dT_abs_max']:.2%}")
    print(f"{'Média |ΔR|':>20} = {comparison['mean_dR']:.2%}")
    print(f"{'Média |ΔT|':>20} = {comparison['mean_dT']:.2%}")
    print(f"{'Nº de pontos':>20} = {n}")
    print("-" * 90)