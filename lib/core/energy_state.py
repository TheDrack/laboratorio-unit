"""
energy_state.py
UNIT-001 — LEDGER DE ENERGIA EXTENSÍVEL

Define a estrutura canônica para contabilização de energia em múltiplos canais
(EM, térmico, mecânico, acústico, etc.), garantindo conservação global.

Arquitetura:
    WaveState (campos E, H, S, q_abs)
         +
    MaterialState (k_thermal, rho, cp)
         ↓
    EnergyLedger
         ├── Canal EM: R, T, A_volume, A_flux
         ├── Canal Térmico: Q_abs_density, T_max, ΔT
         └── (futuro) Canal Mecânico, Acústico, etc.
         ↓
    Validação: Σ canais = P_inc (ou = 1, se normalizado)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np

from lib.core.wave_state import WaveState
from lib.core.material_state import MaterialState, from_homogeneous
from lib.geometry.unit001_constantes import DX, K_PILLAR, N_PILLAR, RHO_SI, CP_SI
from lib.geometry.unit001_constantes import (C_LIGHT, EPS0, MU0, Z0)
from lib.geometry.unit001_constantes import (F_REF_HZ)

# Constantes físicas


# ==============================================================================
# 1. CANAL DE ENERGIA
# ==============================================================================
@dataclass(frozen=True)
class EnergyChannel:
    """
    Representa um canal de energia individual.

    Atributos:
        name: Nome do canal (ex: "Reflection", "Transmission", "Absorption").
        power_watts: Potência neste canal (W ou W/m, dependendo da dimensionalidade).
        fraction_of_incident: Fração adimensional em relação à potência incidente.
        metadata: Dicionário com dados específicos do canal (ex: T_max para térmico).
        mechanism: Um de "same_channel" | "conversion" | "modulation" | "hybridization"
            (ver seção 2 do documento de extensão teórica da UNIT). "same_channel" é
            o default e cobre R/T (a energia continua no mesmo campo, só é
            redirecionada — não é conversão nem modulação). "conversion" marca
            transferência identificável de energia para OUTRO grau de liberdade
            (ex.: EM->térmico via absorção), habilitando eficiência
            eta_A->B = P_B/P_A quando source_channel/target_channel são
            preenchidos. Isso existe para que "conversão" nunca seja confundida
            com "absorção genérica" (o ledger deve poder distinguir P_conversion
            de P_dissipation) — ver correção pendente: nenhum canal hoje usa
            "modulation"/"hybridization" ainda, pois não há nenhum mecanismo
            desse tipo implementado no projeto (reservado para quando existir).
        source_channel / target_channel: rótulos livres (ex. "EM","thermal")
            usados só quando mechanism="conversion"; None nos demais casos.
        counts_toward_closure: False marca um canal como DIAGNÓSTICO — uma
            medida alternativa de uma grandeza já contada por outro canal
            (ex.: A_flux é uma segunda medida, via balanço de fluxo, da
            MESMA absorção que A_volume já mede via integração de campo;
            T_max/T_mean/delta_T guardam Kelvin, não Watts). Sem essa flag,
            total_power/closure_error do EnergyLedger somavam essas
            grandezas por engano — bugs reais, não hipotéticos, encontrados
            ao integrar a tag de mecanismo.
    """
    name: str
    power_watts: float
    fraction_of_incident: float
    metadata: Dict = field(default_factory=dict)
    mechanism: str = "same_channel"
    source_channel: Optional[str] = None
    target_channel: Optional[str] = None
    counts_toward_closure: bool = True

    def __post_init__(self):
        if not np.isfinite(self.power_watts):
            raise ValueError(f"power_watts deve ser finito, recebido {self.power_watts}")
        if not np.isfinite(self.fraction_of_incident):
            raise ValueError(f"fraction_of_incident deve ser finito, recebido {self.fraction_of_incident}")
        valid_mechanisms = {"same_channel", "conversion", "modulation", "hybridization"}
        if self.mechanism not in valid_mechanisms:
            raise ValueError(f"mechanism deve ser um de {valid_mechanisms}, recebido {self.mechanism!r}")


# ==============================================================================
# 2. LEDGER DE ENERGIA
# ==============================================================================
@dataclass
class EnergyLedger:
    """
    Ledger completo de energia, agregando todos os canais.

    Atributos:
        channels: Dicionário de canais de energia.
        P_incident: Potência incidente total (W ou W/m).
        diagnostics: Dict livre para valores auxiliares que um adaptador queira
            anexar (ex.: frequência, resíduo do solver) sem poluir `channels`
            — adicionado para consertar build_energy_ledger_from_fdtd, que já
            supunha esse campo e quebrava com TypeError por ele não existir.
    """
    channels: Dict[str, EnergyChannel]
    P_incident: float
    diagnostics: Dict = field(default_factory=dict)

    @property
    def total_power(self) -> float:
        """Soma da potência nos canais que contam para o fechamento
        energético (counts_toward_closure=True) — canais diagnósticos que
        remedem uma grandeza já contada em outro canal (ex.: A_flux vs
        A_volume) ficam de fora, senão a mesma energia é somada duas vezes."""
        return sum(ch.power_watts for ch in self.channels.values() if ch.counts_toward_closure)

    @property
    def conversion_power(self) -> float:
        """Soma da potência só nos canais mechanism='conversion' que contam
        para o fechamento — P_conversion da seção 9 do documento de extensão
        teórica, separado de dissipação genérica ou de energia que só ficou
        no mesmo canal (R/T)."""
        return sum(ch.power_watts for ch in self.channels.values()
                   if ch.mechanism == "conversion" and ch.counts_toward_closure)

    @property
    def closure_error(self) -> float:
        """Erro de fechamento energético: |Σ canais - P_inc| / P_inc"""
        if self.P_incident == 0:
            return 0.0
        return abs(self.total_power - self.P_incident) / self.P_incident

    def validate(self, tol: float = 1e-7) -> bool:
        """Verifica se o fechamento energético está dentro da tolerância."""
        return self.closure_error < tol
    
    def summary(self) -> str:
        """Retorna um resumo formatado do ledger."""
        lines = [
            f"EnergyLedger (P_inc = {self.P_incident:.6e} W)",
            f"  Total power: {self.total_power:.6e} W",
            f"  Closure error: {self.closure_error:.2e}",
            f"  Validation: {'PASS' if self.validate() else 'FAIL'}",
            "",
            "  Channels:",
        ]
        for name, channel in self.channels.items():
            lines.append(
                f"    {name:<20} | {channel.power_watts:>12.6e} W | "
                f"{channel.fraction_of_incident:>8.4f} | {channel.metadata}"
            )
        return "\n".join(lines)


# ==============================================================================
# 3. CANAL EM (REFLEXÃO, TRANSMISSÃO, ABSORÇÃO)
# ==============================================================================
def compute_em_channels(wave_state: WaveState) -> Dict[str, EnergyChannel]:
    """
    Calcula os canais EM: R, T, A_volume, A_flux.
    
    Requer que o WaveState tenha:
        - S (Poynting vector)
        - q_abs (densidade de absorção)
        - P_incident (potência incidente)
        - z_mon_in, z_mon_out (planos de monitor)
    """
    if wave_state.S is None:
        raise ValueError("WaveState must have Poynting vector S")
    if wave_state.q_abs is None:
        raise ValueError("WaveState must have q_abs")
    if np.isnan(wave_state.P_incident):
        raise ValueError("WaveState must have P_incident")
    if wave_state.z_mon_in is None or wave_state.z_mon_out is None:
        raise ValueError("WaveState must have z_mon_in and z_mon_out")
    
    S_z = wave_state.S["z"]
    dx, dy, dz = wave_state.dx, wave_state.dy, wave_state.dz
    dA = dx * dy
    dV = dx * dy * dz
    
    P_inc = wave_state.P_incident
    
    # Integrar S_z nos monitores
    P_z_in = float(np.real(np.sum(S_z[:, :, wave_state.z_mon_in]) * dA))
    P_z_out = float(np.real(np.sum(S_z[:, :, wave_state.z_mon_out]) * dA))
    
    # R = (P_inc - P_z_in) / P_inc
    # T = P_z_out / P_inc
    P_refl = P_inc - P_z_in
    P_trans = P_z_out
    
    R = P_refl / P_inc if P_inc > 0 else 0.0
    T = P_trans / P_inc if P_inc > 0 else 0.0
    
    # A_volume = integral de q_abs / P_inc
    # Restringir à região estrutural
    if wave_state.z_struct_start is not None and wave_state.z_struct_end is not None:
        q_abs_phys = wave_state.q_abs[:, :, wave_state.z_struct_start:wave_state.z_struct_end]
    else:
        q_abs_phys = wave_state.q_abs
    
    P_abs = float(np.real(np.sum(q_abs_phys) * dV))
    A_volume = P_abs / P_inc if P_inc > 0 else 0.0
    
    # A_flux = 1 - R - T
    A_flux = 1.0 - R - T
    
    return {
        "R": EnergyChannel(
            name="Reflection",
            power_watts=P_refl,
            fraction_of_incident=R,
            metadata={"method": "Poynting_integration"},
            mechanism="same_channel",
        ),
        "T": EnergyChannel(
            name="Transmission",
            power_watts=P_trans,
            fraction_of_incident=T,
            metadata={"method": "Poynting_integration"},
            mechanism="same_channel",
        ),
        "A_volume": EnergyChannel(
            name="Absorption (volume)",
            power_watts=P_abs,
            fraction_of_incident=A_volume,
            metadata={"method": "q_abs_integration"},
            # CORRIGIDO/estendido: EM absorvida por um material com perdas
            # não é "modulação" nem fica no mesmo canal — é energia
            # identificavelmente transferida para outro grau de liberdade
            # (calor). Isso é "conversion" na terminologia da seção 2 do
            # documento de extensão teórica da UNIT, não dissipação genérica
            # sem destino — o destino (thermal) já é o que
            # compute_thermal_channels calcula a partir daqui.
            mechanism="conversion", source_channel="EM", target_channel="thermal",
        ),
        "A_flux": EnergyChannel(
            name="Absorption (flux)",
            power_watts=P_inc * A_flux,
            fraction_of_incident=A_flux,
            metadata={"method": "1-R-T"},
            mechanism="conversion", source_channel="EM", target_channel="thermal",
            # DIAGNÓSTICO: mede a MESMA absorção que A_volume, por outro
            # método (balanço de fluxo em vez de integração de campo). Não
            # conta de novo no fechamento energético — ver counts_toward_closure.
            counts_toward_closure=False,
        ),
    }


# ==============================================================================
# 4. CANAL TÉRMICO
# ==============================================================================
def compute_thermal_channels(wave_state: WaveState, k_thermal: float) -> Dict[str, EnergyChannel]:
    """
    Calcula os canais térmicos: T_max, T_mean, ΔT.
    
    Resolve a equação de difusão de calor em regime estacionário:
        -k_thermal * ∇²T = Q_abs
    
    Requer que o WaveState tenha:
        - q_abs (densidade de absorção)
        - dx, dy, dz (passo da malha)
    """
    if wave_state.q_abs is None:
        raise ValueError("WaveState must have q_abs")
    
    # Importar build_D2 do fdfd2d (reutiliza o operador de Laplaciano)
    from lib.solvers.fdfd2d import build_D2
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    
    dx, dy, dz = wave_state.dx, wave_state.dy, wave_state.dz
    q_abs = wave_state.q_abs
    
    # Dimensões do domínio
    nx, ny, nz = q_abs.shape
    
    # Construir Laplaciano 3D (sem PML, pois é difusão térmica)
    D2x = build_D2(nx, dx, periodic=False, npml=0, k0=1.0)
    D2y = build_D2(ny, dy, periodic=False, npml=0, k0=1.0)
    D2z = build_D2(nz, dz, periodic=False, npml=0, k0=1.0)
    
    Ix = sp.identity(nx, format="csr")
    Iy = sp.identity(ny, format="csr")
    Iz = sp.identity(nz, format="csr")
    
    Lap = (
        sp.kron(sp.kron(D2x, Iy, format="csr"), Iz, format="csr")
        + sp.kron(sp.kron(Ix, D2y, format="csr"), Iz, format="csr")
        + sp.kron(sp.kron(Ix, Iy, format="csr"), D2z, format="csr")
    )
    
    # Fonte térmica
    Q_flat = np.real(q_abs).flatten(order="C")
    
    # Resolver -k_thermal * Lap(T) = Q
    A = (-k_thermal * Lap).tocsc()
    T_flat = spla.spsolve(A, Q_flat)
    T = np.real(T_flat.reshape((nx, ny, nz), order="C"))
    
    # Estatísticas
    T_max = float(np.max(T))
    T_mean = float(np.mean(T))
    
    # Restringir à região estrutural (se disponível)
    if wave_state.z_struct_start is not None and wave_state.z_struct_end is not None:
        T_struct = T[:, :, wave_state.z_struct_start:wave_state.z_struct_end]
        T_max_struct = float(np.max(T_struct)) if T_struct.size else 0.0
        T_mean_struct = float(np.mean(T_struct)) if T_struct.size else 0.0
    else:
        T_max_struct = T_max
        T_mean_struct = T_mean
    
    # ΔT = T_max - T_mean (gradiente térmico máximo)
    delta_T = T_max - T_mean
    
    return {
        "T_max": EnergyChannel(
            name="Temperature (max)",
            power_watts=T_max,  # Não é potência (Kelvin) — ver counts_toward_closure abaixo
            fraction_of_incident=T_max,  # idem
            metadata={
                "unit": "K",
                "T_max_struct": T_max_struct,
                "interpretation": "Maximum temperature (relative to ambient)"
            },
            mechanism="conversion", source_channel="EM", target_channel="thermal",
            # NÃO é um canal de potência (guarda Kelvin, não Watts) — sem essa
            # flag, total_power somava temperatura como se fosse potência,
            # um bug real e pior que o double-count de A_flux/A_volume.
            counts_toward_closure=False,
        ),
        "T_mean": EnergyChannel(
            name="Temperature (mean)",
            power_watts=T_mean,
            fraction_of_incident=T_mean,
            metadata={
                "unit": "K",
                "T_mean_struct": T_mean_struct,
                "interpretation": "Mean temperature (relative to ambient)"
            },
            mechanism="conversion", source_channel="EM", target_channel="thermal",
            counts_toward_closure=False,
        ),
        "delta_T": EnergyChannel(
            name="Temperature gradient",
            power_watts=delta_T,
            fraction_of_incident=delta_T,
            metadata={
                "unit": "K",
                "interpretation": "Max temperature difference (T_max - T_mean)"
            },
            mechanism="conversion", source_channel="EM", target_channel="thermal",
            counts_toward_closure=False,
        ),
    }


# ==============================================================================
# 5. BUILD ENERGY LEDGER
# ==============================================================================
def build_energy_ledger(wave_state: WaveState, material_state: MaterialState) -> EnergyLedger:
    """
    Constrói o ledger completo de energia.
    
    Args:
        wave_state: Estado do campo (E, H, S, q_abs).
        material_state: Estado do material (k_thermal, rho, cp).
    
    Returns:
        EnergyLedger com todos os canais.
    """
    # Canal EM
    em_channels = compute_em_channels(wave_state)
    
    # Canal Térmico (se k_thermal > 0)
    thermal_channels = {}
    if material_state.k_thermal > 0:
        thermal_channels = compute_thermal_channels(wave_state, material_state.k_thermal)
    
    # Agregar todos os canais
    all_channels = {**em_channels, **thermal_channels}
    
    # Potência incidente (do canal EM)
    P_inc = wave_state.P_incident
    
    return EnergyLedger(channels=all_channels, P_incident=P_inc)


# ==============================================================================
# 6. EXEMPLO DE USO
# ==============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("ENERGY STATE — LEDGER DE ENERGIA EXTENSÍVEL")
    print("=" * 80)
    
    # Criar WaveState de exemplo (simulando saída do FDFD)
    nx, ny, nz = 8, 8, 30  # nz precisa caber z_mon_out=20 e z_struct_end=18 abaixo
    dummy_E = np.ones((nx, ny, nz), dtype=complex)
    dummy_H = {"x": np.ones((nx, ny, nz), dtype=complex) * 0.1,
               "y": np.zeros((nx, ny, nz), dtype=complex),
               "z": np.ones((nx, ny, nz), dtype=complex) * 0.1}
    dummy_S = {"x": np.zeros((nx, ny, nz)),
               "y": np.zeros((nx, ny, nz)),
               "z": np.ones((nx, ny, nz)) * 1e-3}
    dummy_q = np.ones((nx, ny, nz)) * 1e10
    
    wave_state = WaveState(
        dx=DX, dy=DX, dz=DX,
        omega=2.0 * np.pi * F_REF_HZ,
        E={"y": dummy_E},
        H=dummy_H,
        S=dummy_S,
        q_abs=dummy_q,
        P_incident=1e-6,
        n_bg=1.0 + 0.0j,
        z_mon_in=5,
        z_mon_out=20,
        z_struct_start=10,
        z_struct_end=18,
    )
    
    # Criar MaterialState de exemplo (grid espacial numa omega fixa — ver
    # material_state.py consolidado; "silicio" como Material nomeado só
    # empresta k_thermal/rho/cp aqui, a permissividade do grid é direta)
    material_state = from_homogeneous(
        nx, ny, nz, dx=DX, dy=DX, dz=DX,
        eps_r=N_PILLAR ** 2,
        k_thermal=K_PILLAR, rho=RHO_SI, cp=CP_SI,
    )
    
    # Construir ledger
    ledger = build_energy_ledger(wave_state, material_state)
    
    print("\n" + ledger.summary())
    
    print("\n" + "=" * 80)
    print("Ledger construído com sucesso!")
    print("=" * 80)