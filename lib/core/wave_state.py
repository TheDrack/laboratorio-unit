"""
wave_state.py
UNIT-001 — ESTADO CANÔNICO DO CAMPO ONDULATÓRIO

Define a estrutura de dados que carrega os campos eletromagnéticos e suas
grandezas derivadas (Poynting, absorção), independente de como foram calculados.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from typing import Dict, Optional
from lib.geometry.unit001_constantes import DX

@dataclass
class WaveState:
    """
    Representação do estado do campo em um domínio discreto.
    
    Atributos:
        dx, dy, dz: Passo da malha espacial (m).
        omega: Frequência angular da simulação (rad/s). Se None, assume-se domínio do tempo.
        
        # Campos Primários
        E: Dict[str, np.ndarray]  # Campo elétrico (ex: {"y": array})
        H: Dict[str, np.ndarray]  # Campo magnético (ex: {"x": array, "z": array})
        
        # Grandezas Derivadas
        S: Optional[Dict[str, np.ndarray]] = None      # Vetor de Poynting
        q_abs: Optional[np.ndarray] = None             # Densidade de absorção (W/m³)
        
        # Metadados de Domínio (NCESSÁRIOS para cálculo de canais EM)
        P_incident: float = np.nan                     # Potência incidente total (W)
        n_bg: complex = 1.0 + 0.0j                     # Índice de refração do background
        z_mon_in: Optional[int] = None                 # Índice do monitor de entrada
        z_mon_out: Optional[int] = None                # Índice do monitor de saída
        z_struct_start: Optional[int] = None           # Início da região estrutural
        z_struct_end: Optional[int] = None             # Fim da região estrutural
        
        # Diagnósticos
        solver_residual: float = np.nan
        energy_closure_error: float = np.nan
    """
    # Campos obrigatórios (sem default)
    dx: float
    dy: float
    dz: float
    omega: Optional[float]
    E: Dict[str, np.ndarray]
    H: Dict[str, np.ndarray]
    
    # Campos opcionais (com default)
    S: Optional[Dict[str, np.ndarray]] = None
    q_abs: Optional[np.ndarray] = None
    P_incident: float = float('nan')
    n_bg: complex = 1.0 + 0.0j
    z_mon_in: Optional[int] = None
    z_mon_out: Optional[int] = None
    z_struct_start: Optional[int] = None
    z_struct_end: Optional[int] = None
    solver_residual: float = float('nan')
    energy_closure_error: float = float('nan')

    @property
    def dV(self) -> float:
        """Volume de uma célula da malha."""
        return self.dx * self.dy * self.dz

    @property
    def is_frequency_domain(self) -> bool:
        """True se o estado representa uma solução harmônica (complexa)."""
        return self.omega is not None

    def get_field_component(self, field_type: str, component: str) -> np.ndarray:
        """Retorna de forma segura um componente de campo."""
        if field_type == 'E' and component in self.E:
            return self.E[component]
        if field_type == 'H' and component in self.H:
            return self.H[component]
        raise KeyError(f"Componente {field_type}_{component} não encontrado.")

    def compute_total_E2(self) -> np.ndarray:
        """Calcula |E|² total."""
        if not self.E:
            raise ValueError("Campo E está vazio.")
        total = np.zeros_like(list(self.E.values())[0], dtype=float)
        for comp in self.E.values():
            total += np.abs(comp) ** 2
        return total

    def compute_total_absorption(self) -> float:
        """Integra a densidade de absorção sobre todo o volume."""
        if self.q_abs is None:
            raise ValueError("q_abs não está definido neste WaveState.")
        return float(np.real(np.sum(self.q_abs) * self.dV))

# ==============================================================================
# EXEMPLO DE USO
# ==============================================================================
if __name__ == "__main__":
    # Simulando a saída de um solver FDFD 3D TE_y
    nx, ny, nz = 8, 8, 8
    dummy_Ey = np.ones((nx, ny, nz), dtype=complex) * (1.0 + 0.5j)
    dummy_Hx = np.ones((nx, ny, nz), dtype=complex) * 0.1
    dummy_Hz = np.ones((nx, ny, nz), dtype=complex) * 0.1
    dummy_q = np.ones((nx, ny, nz), dtype=float) * 1e12  # W/m³

    # Criação SEM metadados (compatível com adaptador atual)
    state = WaveState(
        dx=DX, dy=DX, dz=DX,
        omega=2.0 * np.pi * 350e12,
        E={"y": dummy_Ey},
        H={"x": dummy_Hx, "z": dummy_Hz},
        q_abs=dummy_q,
        solver_residual=1e-14,
        energy_closure_error=1e-15
    )

    print(f"Volume da célula: {state.dV:.3e} m³")
    print(f"Domínio de frequência: {state.is_frequency_domain}")
    print(f"Absorção total integrada: {state.compute_total_absorption():.3e} W")
    print(f"P_incident: {state.P_incident}")
    print(f"n_bg: {state.n_bg}")