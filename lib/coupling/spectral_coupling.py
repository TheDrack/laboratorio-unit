"""
spectral_coupling.py
===============================================================================

TEORIA UNIT
ACOPLAMENTO ESPACIAL + ESPECTRAL + TEMPORAL

Objetivo
--------
Transformar a frequência/espectro em uma variável de primeira classe do
modelo, sem limitar a entrada a uma única onda monocromática.

Arquitetura:

    GEOMETRIA
        G(r)
          +
    MATERIAL
        eps(r, omega)
        sigma(r, omega)
        mu(r, omega)
          +
    ENTRADA
        E_in(t)
        ou
        E_in(omega)
          |
          v
    SOLVER ELETROMAGNÉTICO
        H(r, omega)
          |
          v
    SAÍDA ESPECTRAL
        E_out(omega)
          |
          v
    RECONSTRUÇÃO TEMPORAL
        E_out(t)

Para sistemas LINEARES e INVARIANTES NO TEMPO:

    E_out(omega) = H(omega) E_in(omega)

e uma forma de onda arbitrária pode ser representada pelo seu espectro.

IMPORTANTE
----------
Este módulo trabalha no regime linear/frequency-domain.

Ele NÃO modela diretamente:

    eps = eps(E, T, n_e, omega)
    ionização dinâmica
    geração de harmônicos
    plasma autoconsistente
    aquecimento com retroalimentação temporal
    fluidodinâmica do plasma

Esses fenômenos exigem um solver temporal/multifísico.

Compatibilidade
---------------
O backend eletromagnético é desacoplado deste módulo.

O código tenta suportar:

    1. API moderna 3D:
       fdfd3d.build_domain_3d
       fdfd3d.solve_fdfd_3d
       fdfd3d.analyze_solution_3d

    2. API 2D antiga:
       fdfd2d.build_domain
       fdfd2d.solve_fdfd
       fdfd2d.analyze_solution

=============================== CORREÇÃO NESTA REVISÃO =========================
_extract_rt (ramo 3D) buscava as chaves "R"/"T" em RT_power e RT_specular,
mas analyze_solution_3d (fdfd3d.py) usa "R_power"/"T_power" (em RT_power) e
"R_specular"/"T_specular" (em RT_specular) — as chaves sem sufixo não
existem em nenhum dos dois dicts. Resultado: R e T saíam SEMPRE como NaN
ao usar o backend 3D. Corrigido para usar as chaves reais, preferindo
R_power/T_power (integra Poynting no plano x,y inteiro — captura
espalhamento lateral, não só a ordem especular) com fallback para as
versões especulares, e usando A_volume como fallback de A.
==================================================================================
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import numpy as np
from lib.geometry.unit001_constantes import (EPS0, MU0)


# =============================================================================
# CONSTANTES FÍSICAS
# =============================================================================

C0 = 299_792_458.0


ComplexScalar = Union[complex, float, int]

SpectralFunction = Callable[[float], complex]
MaterialFunction = Union[ComplexScalar, SpectralFunction]


# =============================================================================
# ESTRUTURA DE UMA COMPONENTE ESPECTRAL
# =============================================================================

@dataclass(frozen=True)
class SpectralComponent:
    """Uma componente espectral da onda incidente."""

    wavelength: float
    amplitude: complex = 1.0 + 0.0j
    phase: float = 0.0
    weight: float = 1.0
    metadata: Optional[Dict] = None

    @property
    def frequency(self) -> float:
        return C0 / self.wavelength

    @property
    def omega(self) -> float:
        return 2.0 * np.pi * self.frequency

    @property
    def complex_amplitude(self) -> complex:
        return self.amplitude * np.exp(1j * self.phase)


# =============================================================================
# REPRESENTAÇÃO DE ESPECTRO
# =============================================================================

@dataclass
class Spectrum:
    """Representação discreta de um espectro complexo (amplitude + fase)."""

    wavelengths: np.ndarray
    amplitudes: np.ndarray

    def __post_init__(self):
        self.wavelengths = np.asarray(self.wavelengths, dtype=float)
        self.amplitudes = np.asarray(self.amplitudes, dtype=complex)

        if self.wavelengths.ndim != 1:
            raise ValueError("wavelengths deve ser 1D.")
        if self.amplitudes.ndim != 1:
            raise ValueError("amplitudes deve ser 1D.")
        if len(self.wavelengths) != len(self.amplitudes):
            raise ValueError("wavelengths e amplitudes devem possuir o mesmo tamanho.")
        if np.any(self.wavelengths <= 0.0):
            raise ValueError("Todos os comprimentos de onda devem ser positivos.")

        order = np.argsort(self.wavelengths)
        self.wavelengths = self.wavelengths[order]
        self.amplitudes = self.amplitudes[order]

    @property
    def frequencies(self) -> np.ndarray:
        return C0 / self.wavelengths

    @property
    def omega(self) -> np.ndarray:
        return 2.0 * np.pi * self.frequencies

    @property
    def magnitude(self) -> np.ndarray:
        return np.abs(self.amplitudes)

    @property
    def phase(self) -> np.ndarray:
        return np.unwrap(np.angle(self.amplitudes))

    def normalized(self) -> "Spectrum":
        maximum = np.max(np.abs(self.amplitudes))
        if maximum == 0.0:
            return Spectrum(self.wavelengths.copy(), self.amplitudes.copy())
        return Spectrum(self.wavelengths.copy(), self.amplitudes / maximum)


# =============================================================================
# FUNÇÕES BÁSICAS DE ESPECTRO
# =============================================================================

def gaussian_spectrum(wavelengths, center_wavelength, sigma_wavelength,
                       amplitude: complex = 1.0 + 0.0j) -> Spectrum:
    wavelengths = np.asarray(wavelengths, dtype=float)
    envelope = np.exp(-0.5 * ((wavelengths - center_wavelength) / sigma_wavelength) ** 2)
    return Spectrum(wavelengths=wavelengths, amplitudes=amplitude * envelope)


def gaussian_frequency_spectrum(wavelengths, center_frequency, sigma_frequency,
                                 amplitude: complex = 1.0 + 0.0j) -> Spectrum:
    wavelengths = np.asarray(wavelengths, dtype=float)
    frequencies = C0 / wavelengths
    envelope = np.exp(-0.5 * ((frequencies - center_frequency) / sigma_frequency) ** 2)
    return Spectrum(wavelengths=wavelengths, amplitudes=amplitude * envelope)


def chirped_spectrum(wavelengths, center_wavelength, sigma_wavelength, chirp,
                      amplitude: complex = 1.0 + 0.0j) -> Spectrum:
    wavelengths = np.asarray(wavelengths, dtype=float)
    omega = 2.0 * np.pi * C0 / wavelengths
    omega0 = 2.0 * np.pi * C0 / center_wavelength
    envelope = np.exp(-0.5 * ((wavelengths - center_wavelength) / sigma_wavelength) ** 2)
    phase = chirp * (omega - omega0) ** 2
    return Spectrum(wavelengths=wavelengths, amplitudes=amplitude * envelope * np.exp(1j * phase))


# =============================================================================
# CONVERSÃO DE FORMA DE ONDA TEMPORAL <-> ESPECTRO
# =============================================================================

def waveform_to_spectrum(time, field, *, detrend: bool = False):
    time = np.asarray(time, dtype=float)
    field = np.asarray(field, dtype=complex)
    if time.ndim != 1 or field.ndim != 1:
        raise ValueError("time e field devem ser arrays 1D.")
    if len(time) != len(field):
        raise ValueError("time e field devem possuir o mesmo tamanho.")
    if len(time) < 2:
        raise ValueError("São necessários pelo menos dois pontos temporais.")

    dt_array = np.diff(time)
    if not np.allclose(dt_array, dt_array[0], rtol=1e-8, atol=1e-18):
        raise ValueError("A FFT requer espaçamento temporal uniforme.")

    if detrend:
        field = field - np.mean(field)

    dt = dt_array[0]
    spectrum = np.fft.fft(field)
    frequencies = np.fft.fftfreq(len(field), d=dt)
    return frequencies, spectrum


def positive_frequency_spectrum(frequencies, spectrum):
    frequencies = np.asarray(frequencies, dtype=float)
    spectrum = np.asarray(spectrum, dtype=complex)
    mask = frequencies > 0.0
    return frequencies[mask], spectrum[mask]


def reconstruct_waveform(frequencies, spectrum, time):
    frequencies = np.asarray(frequencies, dtype=float)
    spectrum = np.asarray(spectrum, dtype=complex)
    time = np.asarray(time, dtype=float)
    if len(frequencies) != len(spectrum):
        raise ValueError("frequencies e spectrum devem possuir o mesmo tamanho.")
    omega = 2.0 * np.pi * frequencies
    phase = np.exp(1j * np.outer(omega, time))
    return np.sum(spectrum[:, None] * phase, axis=0)


# =============================================================================
# MATERIAL DISPERSIVO
# =============================================================================

def evaluate_material(value: MaterialFunction, wavelength: float) -> complex:
    result = value(wavelength) if callable(value) else value
    return complex(result)


def complex_epsilon_from_n(refractive_index: complex) -> complex:
    return refractive_index ** 2


def epsilon_from_sigma(epsilon_r: complex, sigma: complex, omega: float) -> complex:
    """
    epsilon_eff = epsilon_r + i*sigma/(omega*eps0), convenção e^{-i omega t}.
    Verificado: sigma>0 (perda física) -> Im(eps_eff)>0, consistente com a
    convenção usada no resto do projeto (Im(eps)>0 = absorção).
    """
    if omega <= 0.0:
        raise ValueError("omega deve ser positivo.")
    return epsilon_r + 1j * sigma / (omega * EPS0)


# =============================================================================
# BACKEND ELETROMAGNÉTICO
# =============================================================================

class FDFDBackend:
    """Adaptador: detecta e chama fdfd3d.py (preferência) ou fdfd2d.py."""

    def __init__(self, module_name: Optional[str] = None):
        self.module = None
        self.dimension = None
        if module_name is not None:
            self._load_module(module_name)
        else:
            self._auto_detect()

    def _load_module(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        self.module = module
        if hasattr(module, "build_domain_3d"):
            self.dimension = 3
            return
        if hasattr(module, "build_domain"):
            self.dimension = 2
            return
        raise ImportError(f"O módulo '{module_name}' não possui uma API FDFD reconhecida.")

    def _auto_detect(self) -> None:
        errors = []
        for module_name in ("fdfd3d", "fdfd2d"):
            try:
                self._load_module(module_name)
                return
            except Exception as exc:
                errors.append(f"{module_name}: {exc}")
        raise ImportError(
            "Não foi possível localizar um backend FDFD compatível.\n" + "\n".join(errors)
        )

    def solve(self, geom: Dict, wavelength: float, n_bg: complex,
              npml_cells: int, buffer_cells: int) -> Tuple[Dict, Dict]:
        if self.dimension == 3:
            build_domain = getattr(self.module, "build_domain_3d")
            domain = build_domain(geom, wavelength, n_bg=n_bg,
                                   npml_cells=npml_cells, buffer_cells=buffer_cells)

            solve_fn = getattr(self.module, "solve_fdfd_3d", None) \
                or getattr(self.module, "solve_fdfd", None)
            if solve_fn is None:
                raise AttributeError("Backend 3D não possui solve_fdfd_3d nem solve_fdfd.")
            result = solve_fn(domain)

            analyze_fn = getattr(self.module, "analyze_solution_3d", None) \
                or getattr(self.module, "analyze_solution", None)
            if analyze_fn is None:
                raise AttributeError("Backend 3D não possui função de análise.")
            analysis = analyze_fn(result)
            return result, analysis

        # API 2D legada
        domain = self.module.build_domain(geom, wavelength, n_bg=n_bg,
                                           npml_cells=npml_cells, buffer_cells=buffer_cells)
        result = self.module.solve_fdfd(domain)
        analysis = self.module.analyze_solution(result)
        return result, analysis


# =============================================================================
# NORMALIZAÇÃO DOS RESULTADOS
# =============================================================================

def _extract_rt(analysis: Dict) -> Dict:
    """
    Extrai R/T/A independentemente da nomenclatura do backend.

    API 2D: RT["R"], RT["T"], RT["A_flux"], RT["r"], RT["t"]

    API 3D — CORRIGIDO nesta revisão (chaves reais, com sufixo):
        RT_power["R_power"], RT_power["T_power"], RT_power["A_flux_power"]
        RT_specular["R_specular"], RT_specular["T_specular"],
            RT_specular["r"], RT_specular["t"]
        absorption["A_volume"]
    """
    if "RT" in analysis:
        rt = analysis["RT"]
        R = rt.get("R", np.nan)
        T = rt.get("T", np.nan)
        A = rt.get("A_flux", rt.get("A", np.nan))
        r = rt.get("r", np.nan + 0j)
        t = rt.get("t", np.nan + 0j)
        return {"R": float(np.real(R)), "T": float(np.real(T)), "A": float(np.real(A)),
                "r": complex(r), "t": complex(t)}

    # API 3D: RT_power (Poynting, plano x,y inteiro -> inclui espalhamento
    # lateral) é preferida sobre RT_specular (só a ordem especular); r,t
    # complexos só existem em RT_specular.
    rt_specular = analysis.get("RT_specular", {})
    rt_power = analysis.get("RT_power", {})

    R = rt_power.get("R_power", rt_specular.get("R_specular", np.nan))
    T = rt_power.get("T_power", rt_specular.get("T_specular", np.nan))

    A = rt_power.get("A_flux_power", np.nan)
    if np.isnan(np.real(A)):
        absorption = analysis.get("absorption", {})
        if isinstance(absorption, dict):
            A = absorption.get("A_volume", np.nan)
    if np.isnan(np.real(A)):
        A = 1.0 - np.real(R) - np.real(T)

    r = rt_specular.get("r", np.nan + 0j)
    t = rt_specular.get("t", np.nan + 0j)

    return {"R": float(np.real(R)), "T": float(np.real(T)), "A": float(np.real(A)),
            "r": complex(r), "t": complex(t)}


# =============================================================================
# FÁBRICA DE GEOMETRIA
# =============================================================================

def build_geometry_factory(geometry_builder: Callable, *, wavelengths: Sequence[float],
                            **geometry_kwargs) -> Callable[[float], Dict]:
    """Constrói a geometria UMA VEZ (na resolução do menor lambda) e devolve
    geom_at(lambda) que reaproveita a mesma malha para todas as frequências."""
    wavelengths = np.asarray(wavelengths, dtype=float)
    if len(wavelengths) == 0:
        raise ValueError("wavelengths não pode ser vazio.")
    wavelength_ref = float(np.min(wavelengths))
    base_geometry = geometry_builder(wavelength=wavelength_ref, **geometry_kwargs)

    def geom_at(wavelength: float) -> Dict:
        return base_geometry

    return geom_at


def update_geometry_material(base_geometry: Dict, wavelength: float, *,
                              epsilon_background: MaterialFunction,
                              epsilon_inclusion: MaterialFunction,
                              inclusion_mask: Optional[np.ndarray] = None,
                              epsilon_key: str = "epsilon") -> Dict:
    """Reaproveita a máscara espacial e atualiza só epsilon(lambda)."""
    geom = dict(base_geometry)
    eps_bg = evaluate_material(epsilon_background, wavelength)
    eps_inc = evaluate_material(epsilon_inclusion, wavelength)

    if inclusion_mask is None:
        if epsilon_key not in base_geometry:
            raise KeyError(f"Geometria não contém '{epsilon_key}' e inclusion_mask não foi fornecida.")
        raise ValueError("Para atualizar uma geometria bifásica é necessário fornecer inclusion_mask explicitamente.")

    epsilon = np.where(inclusion_mask, eps_inc, eps_bg).astype(complex)
    geom[epsilon_key] = epsilon
    return geom


# =============================================================================
# VARREDURA ESPECTRAL
# =============================================================================

def spectral_sweep(geom_at: Callable[[float], Dict], wavelengths: Sequence[float], *,
                    backend: Optional[FDFDBackend] = None, n_bg: MaterialFunction = 1.0,
                    npml_cells: int = 20, buffer_cells: int = 20,
                    incident_amplitude: Optional[Sequence[complex]] = None,
                    store_fields: bool = False, verbose: bool = True, label: str = "") -> Dict:
    """Para cada lambda: geom(lambda) -> FDFD(lambda) -> H(lambda) = (r,t)."""
    if backend is None:
        backend = FDFDBackend()

    wavelengths = np.asarray(wavelengths, dtype=float)
    if np.any(wavelengths <= 0.0):
        raise ValueError("Todos os wavelengths devem ser positivos.")

    n = len(wavelengths)
    if incident_amplitude is None:
        incident_amplitude = np.ones(n, dtype=complex)
    else:
        incident_amplitude = np.asarray(incident_amplitude, dtype=complex)
        if len(incident_amplitude) != n:
            raise ValueError("incident_amplitude deve possuir o mesmo tamanho de wavelengths.")

    out = {
        "wavelength": wavelengths.copy(), "frequency": C0 / wavelengths,
        "omega": 2.0 * np.pi * C0 / wavelengths, "incident_amplitude": incident_amplitude.copy(),
        "R": np.full(n, np.nan), "T": np.full(n, np.nan), "A": np.full(n, np.nan),
        "r": np.full(n, np.nan + 0j, dtype=complex), "t": np.full(n, np.nan + 0j, dtype=complex),
        "phase_r": np.full(n, np.nan), "phase_t": np.full(n, np.nan),
        "H_r": np.full(n, np.nan + 0j, dtype=complex), "H_t": np.full(n, np.nan + 0j, dtype=complex),
    }
    if store_fields:
        out["fields"] = []

    total = len(wavelengths)
    for i, wavelength in enumerate(wavelengths):
        n_bg_w = evaluate_material(n_bg, wavelength)
        geom = geom_at(wavelength)
        result, analysis = backend.solve(geom=geom, wavelength=float(wavelength), n_bg=n_bg_w,
                                          npml_cells=npml_cells, buffer_cells=buffer_cells)
        rt = _extract_rt(analysis)

        out["R"][i] = rt["R"]
        out["T"][i] = rt["T"]
        out["A"][i] = rt["A"]
        out["r"][i] = rt["r"]
        out["t"][i] = rt["t"]
        out["phase_r"][i] = np.angle(rt["r"])
        out["phase_t"][i] = np.angle(rt["t"])
        out["H_r"][i] = rt["r"]
        out["H_t"][i] = rt["t"]

        if store_fields:
            field_data = {}
            for key in ("Etotal", "Einc", "Ez", "Ex", "Ey", "Hx", "Hy", "Hz"):
                if key in result:
                    field_data[key] = result[key]
            out["fields"].append(field_data)

        if verbose:
            tag = f"[{label}] " if label else ""
            print(f"{tag}{i + 1}/{total} lambda={wavelength * 1e9:.3f} nm "
                  f"f={out['frequency'][i] / 1e12:.6f} THz "
                  f"R={out['R'][i]:.6f} T={out['T'][i]:.6f} A={out['A'][i]:.6f}", flush=True)

    return out


# =============================================================================
# APLICAÇÃO DA FUNÇÃO DE TRANSFERÊNCIA A UM ESPECTRO
# =============================================================================

def apply_transfer_function(spectrum: Spectrum, spectral_result: Dict, *, channel: str = "t") -> Spectrum:
    """E_out(lambda) = H(lambda) * E_in(lambda), channel='r' ou 't'."""
    if channel not in ("r", "t"):
        raise ValueError("channel deve ser 'r' ou 't'.")

    wl_solver = np.asarray(spectral_result["wavelength"], dtype=float)
    H = np.asarray(spectral_result[channel], dtype=complex)
    wl = spectrum.wavelengths

    if not np.allclose(wl, wl_solver, rtol=1e-10, atol=1e-18):
        raise ValueError("O espectro incidente e a resposta do solver devem estar na mesma grade espectral.")

    return Spectrum(wavelengths=wl.copy(), amplitudes=H * spectrum.amplitudes)


# =============================================================================
# FUNÇÃO DE TRANSFERÊNCIA ESPACIAL
# =============================================================================

def calculate_spatial_transfer_function(result: Dict, *, floor: float = 1e-14) -> Optional[np.ndarray]:
    """H(r,omega) = E_total(r,omega)/E_inc(r,omega), com máscara onde |E_inc| é pequeno."""
    if "Etotal" not in result or "Einc" not in result:
        return None
    Etotal = np.asarray(result["Etotal"], dtype=complex)
    Einc = np.asarray(result["Einc"], dtype=complex)
    mask = np.abs(Einc) > floor
    H = np.full_like(Etotal, np.nan + 0j, dtype=complex)
    H[mask] = Etotal[mask] / Einc[mask]
    return H


# =============================================================================
# MÉTRICAS ESPECTRAIS
# =============================================================================

def spectral_contrast(results: Dict[str, Dict], reference: str = "A") -> Dict:
    """Delta_R/T/A entre cada estrutura e a referência, ao longo do espectro."""
    if reference not in results:
        raise KeyError(f"Referência '{reference}' não encontrada.")
    ref = results[reference]
    wavelengths = ref["wavelength"]
    out = {"wavelength": wavelengths.copy(), "frequency": C0 / wavelengths}
    for name, result in results.items():
        if name == reference:
            continue
        out[f"dR_{name}_minus_{reference}"] = result["R"] - ref["R"]
        out[f"dT_{name}_minus_{reference}"] = result["T"] - ref["T"]
        out[f"dA_{name}_minus_{reference}"] = result["A"] - ref["A"]
    return out


def integrate_spectral_metric(wavelengths: Sequence[float], values: Sequence[float]) -> float:
    wavelengths = np.asarray(wavelengths, dtype=float)
    values = np.asarray(values, dtype=float)
    order = np.argsort(wavelengths)
    return float(np.trapezoid(values[order], wavelengths[order]))


def weighted_spectral_average(wavelengths, values, weights) -> float:
    wavelengths = np.asarray(wavelengths, dtype=float)
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if not (len(wavelengths) == len(values) == len(weights)):
        raise ValueError("wavelengths, values e weights devem possuir o mesmo tamanho.")
    denominator = np.sum(weights)
    if denominator == 0.0:
        return np.nan
    return float(np.sum(values * weights) / denominator)


def spectrum_from_components(components: Iterable[SpectralComponent]) -> Spectrum:
    components = list(components)
    if not components:
        raise ValueError("Nenhuma componente espectral foi fornecida.")
    wavelengths = np.array([c.wavelength for c in components], dtype=float)
    amplitudes = np.array([c.complex_amplitude for c in components], dtype=complex)
    return Spectrum(wavelengths=wavelengths, amplitudes=amplitudes)


# =============================================================================
# COMPARAÇÃO DE ESTRUTURAS
# =============================================================================

def compare_structures(geometry_factories: Dict[str, Callable[[float], Dict]],
                        wavelengths: Sequence[float], *, backend: Optional[FDFDBackend] = None,
                        n_bg: MaterialFunction = 1.0, npml_cells: int = 20, buffer_cells: int = 20,
                        store_fields: bool = False, verbose: bool = True) -> Dict[str, Dict]:
    """Roda a mesma varredura espectral para várias geometrias (H_ordered vs H_random...)."""
    if backend is None:
        backend = FDFDBackend()
    results = {}
    for name, geom_at in geometry_factories.items():
        print("\n" + "=" * 80)
        print(f"VARREDURA ESPECTRAL: {name}")
        print("=" * 80)
        results[name] = spectral_sweep(geom_at, wavelengths, backend=backend, n_bg=n_bg,
                                        npml_cells=npml_cells, buffer_cells=buffer_cells,
                                        store_fields=store_fields, verbose=verbose, label=name)
    return results


# =============================================================================
# DEMONSTRAÇÃO
# =============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("SPECTRAL COUPLING — TESTE DE ARQUITETURA")
    print("=" * 80)

    wavelengths = np.linspace(0.8e-6, 1.2e-6, 41)

    mono = Spectrum(wavelengths=np.array([1.0e-6]), amplitudes=np.array([1.0 + 0.0j]))
    print("\nExemplo monocromático:")
    print(f"lambda = {mono.wavelengths[0] * 1e9:.2f} nm")
    print(f"f = {mono.frequencies[0] / 1e12:.6f} THz")

    gaussian = gaussian_spectrum(wavelengths=wavelengths, center_wavelength=1.0e-6, sigma_wavelength=0.05e-6)
    print("\nEspectro Gaussiano:")
    print(f"componentes = {len(gaussian.wavelengths)}")
    print(f"lambda_min = {gaussian.wavelengths.min() * 1e9:.2f} nm")
    print(f"lambda_max = {gaussian.wavelengths.max() * 1e9:.2f} nm")

    chirped = chirped_spectrum(wavelengths=wavelengths, center_wavelength=1.0e-6,
                                sigma_wavelength=0.05e-6, chirp=1e-28)
    print("\nEspectro chirped:")
    print(f"fase inicial = {chirped.phase[0]:.6e} rad")
    print(f"fase final   = {chirped.phase[-1]:.6e} rad")

    arbitrary = spectrum_from_components([
        SpectralComponent(wavelength=0.9e-6, amplitude=1.0),
        SpectralComponent(wavelength=1.0e-6, amplitude=0.5, phase=np.pi / 3),
        SpectralComponent(wavelength=1.1e-6, amplitude=0.25, phase=np.pi / 2),
    ])
    print("\nEspectro arbitrário:")
    for wl, amp in zip(arbitrary.wavelengths, arbitrary.amplitudes):
        print(f"  lambda={wl * 1e9:8.3f} nm |A|={abs(amp):.6f} phase={np.angle(amp):+.6f} rad")

    print("\nArquitetura carregada.")
    print("Para executar o solver, forneça uma fábrica de geometria compatível com o backend FDFD instalado.")
