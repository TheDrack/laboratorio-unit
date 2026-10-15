"""
fdtd3d.py — Solver FDTD 3D (Yee grid completo, 6 componentes E/H), CPML em
z, contorno periódico em x,y (mesma convenção do projeto: rede lateral
periódica, absorção/propagação em z), fonte de onda plana via TF/SF (grade
auxiliar 1D) e extração de H(f) = r(f), t(f) por FFT de um único pulso de
banda larga — em vez de resolver frequência por frequência como o FDFD.

============================== ESCOPO E SIMPLIFICAÇÕES =========================
1. CPML com kappa=1, alpha=0 (sem "CFS" — complex-frequency-shifting).
   Os coeficientes b,a da recursão são derivados diretamente aqui (ver
   docstring de cpml_coefficients), não copiados de memória de uma fórmula
   de livro-texto — mais fácil de auditar, ao custo de uma pequena perda
   de desempenho do PML em frequências muito baixas dentro do pulso
   (alpha>0 ajudaria lá; não crítico para um pulso banda-óptica).
2. Mesmo índice de fundo nos dois lados (sem N_SUB assimétrico) — como na
   v1 do fdfd2d.py/fdfd3d.py. TF/SF com salto de substrato é um TODO.
3. Material (eps_r) atribuído diretamente nos nós Ex/Ey/Ez, sem sub-pixel
   averaging nas interfaces (mesma simplificação dos solvers FDFD).
4. Só materiais SEM PERDA e NÃO DISPERSIVOS nesta v1 (eps_r real,
   constante em omega). Perda/dispersão exigiriam um termo de condutividade
   real (sigma*E) ou equações auxiliares de dispersão (ADE) — não
   implementado ainda.
5. Fonte de onda plana com E ao longo de y, H ao longo de x, propagando em
   +z ("TE_y" do resto do projeto) — mas TODOS os 6 componentes de campo
   são simulados; a escolha de polarização é só da FONTE, não uma
   restrição do solver (uma fonte Ex/Hy também seria possível).
==================================================================================

============================== STATUS DE VALIDAÇÃO (leia antes de usar) ========
VALIDADO — motor Yee + CPML + TF/SF (init_fields/step_fields/cpml_*):
  Testado em regime permanente de onda contínua (run_cw_single_frequency),
  numa lâmina de 300nm/n=2: R=0,1725 vs analítico 0,1627 (Fabry-Pérot),
  T=0,8268 vs 0,8373, R+T=0,9993 — erro ~6%, mesma ordem do erro de
  dispersão numérica já visto no FDFD nessa resolução; conservação de
  energia excelente. Use spectral_sweep_cw / run_cw_single_frequency para
  obter R(f), T(f) — mais lento que um pulso único (uma simulação por
  frequência), mas CONFIÁVEL.

NÃO VALIDADO — extração via pulso de banda larga + FFT (run_fdtd,
  extract_spectral_RT): dá erros que NÃO encolhem com a resolução (~3-9%,
  chegando a bem mais em alguns pontos), incluindo um entalhe espectral
  estreito perto da frequência central do pulso, e uma diferença grande
  entre a amplitude de pico do TRANSIENTE refletido (que bate com Fresnel)
  e o valor de REGIME PERMANENTE medido via CW (que também bate). Isso
  isola o problema ao próprio mecanismo de pulso/FFT — ainda não
  encontrado. NÃO CONFIE em run_fdtd/extract_spectral_RT para números
  quantitativos até isso ser resolvido; a função continua no arquivo para
  quem quiser ajudar a depurar, mas use spectral_sweep_cw como método
  principal por enquanto.
==================================================================================
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from lib.geometry.unit001_constantes import (C_LIGHT, EPS0, MU0, Z0)



# ==============================================================================
# 1. GRADE / DOMÍNIO
# ==============================================================================
@dataclass
class FDTDDomain:
    nx: int
    ny: int
    nz: int                # número de CÉLULAS em z
    delta: float            # malha cúbica: dx=dy=dz
    dt: float
    n_bg: float
    npml: int
    eps_ex: np.ndarray       # (nx,ny,nz+1)
    eps_ey: np.ndarray       # (nx,ny,nz+1)
    eps_ez: np.ndarray       # (nx,ny,nz)
    z_struct_start: int
    z_struct_end: int
    z_mon_in: int
    z_mon_out: int
    k_tfsf: int


def build_fdtd_domain(eps_cell: np.ndarray, wavelength_ref: float, n_bg: float = 1.0,
                       npml: int = 15, buffer_cells: int = 15, resolution_ppw: float = 20,
                       cfl_factor: float = 0.99) -> FDTDDomain:
    """
    eps_cell: array real (nx,ny,nz_struct), permissividade relativa da
    ESTRUTURA (mesma convenção de geometry.py/fdfd3d.py), inserida entre
    duas regiões homogêneas de índice n_bg (PML+buffer) nos dois lados de z.
    O plano de TF/SF fica logo depois do PML de entrada (dentro do buffer).
    """
    nx, ny, nz_struct = eps_cell.shape
    n_max = max(n_bg, float(np.sqrt(np.max(np.real(eps_cell)))))
    delta = wavelength_ref / (n_max * resolution_ppw)

    n_pad = npml + buffer_cells
    nz = 2 * n_pad + nz_struct

    eps_full_cell = np.full((nx, ny, nz), n_bg ** 2, dtype=float)
    eps_full_cell[:, :, n_pad:n_pad + nz_struct] = np.real(eps_cell)

    eps_ex = np.concatenate([eps_full_cell, eps_full_cell[:, :, -1:]], axis=2)
    eps_ey = eps_ex.copy()
    eps_ez = eps_full_cell

    dt = cfl_factor * delta / (C_LIGHT * np.sqrt(3.0))

    return FDTDDomain(
        nx=nx, ny=ny, nz=nz, delta=delta, dt=dt, n_bg=n_bg, npml=npml,
        eps_ex=eps_ex, eps_ey=eps_ey, eps_ez=eps_ez,
        z_struct_start=n_pad, z_struct_end=n_pad + nz_struct,
        z_mon_in=npml + 2,
        z_mon_out=n_pad + nz_struct + buffer_cells // 2,
        k_tfsf=n_pad - 2,
    )


def homogeneous_slab_eps(nx: int, ny: int, nz: int, n_slab: float) -> np.ndarray:
    return np.full((nx, ny, nz), n_slab ** 2, dtype=float)


# ==============================================================================
# 2. CPML (kappa=1, alpha=0)
# ==============================================================================
def cpml_profile(nz: int, npml: int, delta: float, m: int = 3, R0: float = 1e-6) -> Tuple[np.ndarray, np.ndarray]:
    """
    sigma(z) graduada (grau m) dentro do PML, nos NÓS (nz+1 pontos, malha
    Ex/Ey) e nos pontos de MEIA-MALHA (nz pontos, malha Hx/Hy) — mesmo
    padrão de pml_sfactors em fdfd2d.py, agora para condutividade REAL.
    """
    if npml <= 0:
        return np.zeros(nz + 1), np.zeros(nz)

    sigma_max = -(m + 1) * np.log(R0) / (2.0 * Z0 * npml * delta)

    def sigma_of(depth):
        depth = np.clip(depth, 0.0, 1.0)
        return sigma_max * depth ** m

    idx_node = np.arange(nz + 1, dtype=float)
    sigma_node = np.zeros(nz + 1)
    sigma_node[:npml] = sigma_of((npml - idx_node[:npml]) / npml)
    sigma_node[nz - npml + 1:] = sigma_of((idx_node[nz - npml + 1:] - (nz - npml)) / npml)

    idx_half = np.arange(nz, dtype=float) + 0.5
    sigma_half = np.zeros(nz)
    sigma_half[:npml] = sigma_of((npml - idx_half[:npml]) / npml)
    sigma_half[nz - npml:] = sigma_of((idx_half[nz - npml:] - (nz - npml)) / npml)

    return sigma_node, sigma_half


def cpml_coefficients(sigma: np.ndarray, dt: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Coeficientes b,a da recursão CPML (kappa=1, alpha=0).

    Derivação: o fator de esticamento de coordenada é s(omega) = 1 + x/(i*omega),
    x = sigma/eps0. Decompondo em frações parciais:
        1/s = 1 - x/(i*omega + x)
    Definindo psi(omega) = [x/(i*omega+x)] * dF/dz(omega), a derivada
    efetiva no PML é dF/dz - psi. No tempo, psi satisfaz:
        d(psi)/dt + x*psi = x * dF/dz
    Integrando exatamente sobre um passo dt (fonte ~constante no passo):
        psi_(n+1) = b*psi_n + a*g_(n+1),   b = exp(-x*dt),   a = (1-b)
    onde g = dF/dz calculado normalmente. Fora do PML, sigma=0 -> b=1,a=0
    -> psi fica sempre 0 -> derivada efetiva = derivada normal (sem efeito).
    """
    x = sigma / EPS0
    b = np.exp(-x * dt)
    a = 1.0 - b
    return b, a


# ==============================================================================
# 3. CAMPOS
# ==============================================================================
def init_fields(domain: FDTDDomain) -> Dict[str, np.ndarray]:
    nx, ny, nz = domain.nx, domain.ny, domain.nz
    z = lambda *shape: np.zeros(shape, dtype=float)
    return {
        "Ex": z(nx, ny, nz + 1), "Ey": z(nx, ny, nz + 1), "Ez": z(nx, ny, nz),
        "Hx": z(nx, ny, nz), "Hy": z(nx, ny, nz), "Hz": z(nx, ny, nz + 1),
        "psi_Ey_z": z(nx, ny, nz), "psi_Ex_z": z(nx, ny, nz),           # p/ Hx,Hy (malha meia-célula)
        "psi_Hy_z": z(nx, ny, nz - 1), "psi_Hx_z": z(nx, ny, nz - 1),   # p/ Ex,Ey (malha nó, interior)
    }


def step_fields(fields: Dict[str, np.ndarray], domain: FDTDDomain,
                 b_half: np.ndarray, a_half: np.ndarray,
                 b_node_int: np.ndarray, a_node_int: np.ndarray) -> None:
    """Um passo de leapfrog completo (H depois E), com CPML em z. In-place."""
    Ex, Ey, Ez = fields["Ex"], fields["Ey"], fields["Ez"]
    Hx, Hy, Hz = fields["Hx"], fields["Hy"], fields["Hz"]
    dx = dy = dz = domain.delta
    dt = domain.dt

    # ---------------- H update ----------------
    dEz_dy = (np.roll(Ez, -1, axis=1) - Ez) / dy
    dEy_dz_raw = (Ey[:, :, 1:] - Ey[:, :, :-1]) / dz
    fields["psi_Ey_z"][...] = b_half[None, None, :] * fields["psi_Ey_z"] + a_half[None, None, :] * dEy_dz_raw
    dEy_dz_eff = dEy_dz_raw - fields["psi_Ey_z"]
    Hx -= (dt / MU0) * (dEz_dy - dEy_dz_eff)

    dEx_dz_raw = (Ex[:, :, 1:] - Ex[:, :, :-1]) / dz
    fields["psi_Ex_z"][...] = b_half[None, None, :] * fields["psi_Ex_z"] + a_half[None, None, :] * dEx_dz_raw
    dEx_dz_eff = dEx_dz_raw - fields["psi_Ex_z"]
    dEz_dx = (np.roll(Ez, -1, axis=0) - Ez) / dx
    Hy -= (dt / MU0) * (dEx_dz_eff - dEz_dx)

    dEy_dx = (np.roll(Ey, -1, axis=0) - Ey) / dx
    dEx_dy = (np.roll(Ex, -1, axis=1) - Ex) / dy
    Hz -= (dt / MU0) * (dEy_dx - dEx_dy)

    # ---------------- E update ----------------
    dHz_dy = (Hz - np.roll(Hz, 1, axis=1)) / dy
    dHy_dz_raw = np.zeros_like(Ex)
    dHy_dz_raw[:, :, 1:-1] = (Hy[:, :, 1:] - Hy[:, :, :-1]) / dz
    fields["psi_Hy_z"][...] = (b_node_int[None, None, :] * fields["psi_Hy_z"]
                                + a_node_int[None, None, :] * dHy_dz_raw[:, :, 1:-1])
    dHy_dz_eff = np.zeros_like(Ex)
    dHy_dz_eff[:, :, 1:-1] = dHy_dz_raw[:, :, 1:-1] - fields["psi_Hy_z"]
    Ex[:, :, 1:-1] += (dt / (EPS0 * domain.eps_ex[:, :, 1:-1])) * (dHz_dy[:, :, 1:-1] - dHy_dz_eff[:, :, 1:-1])

    dHz_dx = (Hz - np.roll(Hz, 1, axis=0)) / dx
    dHx_dz_raw = np.zeros_like(Ey)
    dHx_dz_raw[:, :, 1:-1] = (Hx[:, :, 1:] - Hx[:, :, :-1]) / dz
    fields["psi_Hx_z"][...] = (b_node_int[None, None, :] * fields["psi_Hx_z"]
                                + a_node_int[None, None, :] * dHx_dz_raw[:, :, 1:-1])
    dHx_dz_eff = np.zeros_like(Ey)
    dHx_dz_eff[:, :, 1:-1] = dHx_dz_raw[:, :, 1:-1] - fields["psi_Hx_z"]
    Ey[:, :, 1:-1] += (dt / (EPS0 * domain.eps_ey[:, :, 1:-1])) * (dHx_dz_eff[:, :, 1:-1] - dHz_dx[:, :, 1:-1])

    dHy_dx = (Hy - np.roll(Hy, 1, axis=0)) / dx
    dHx_dy = (Hx - np.roll(Hx, 1, axis=1)) / dy
    Ez += (dt / (EPS0 * domain.eps_ez)) * (dHy_dx - dHx_dy)


# ==============================================================================
# 4. GRADE AUXILIAR 1D (para TF/SF) — mesma dispersão numérica do eixo z 3D
# ==============================================================================
class Aux1D:
    """Réplica 1D (Ey,Hx) do par de campos que se propaga em z, usada só
    para gerar os valores de onda incidente consistentes com a MESMA
    dispersão numérica da malha 3D (ponto central do método TF/SF: a onda
    injetada tem que "conhecer" a discretização, senão vaza no contorno).

    NOTA (revisão): uma variante com fonte suave injetada diretamente em
    k_tfsf + ABC de Mur foi testada e piorou o isolamento SF/TF (vazamento
    subiu de ~1e-5 para ~0,87, quase a amplitude inteira da onda incidente)
    porque ler o valor exatamente no mesmo ponto onde a fonte acabou de
    injetar energia (nos dois sentidos) não reproduz uma onda puramente
    incidente ali. Fonte dura numa ponta + malha auxiliar comprida o
    bastante para não haver reflexão dentro do tempo de simulação
    (abordagem abaixo) evita esse problema por construção."""

    def __init__(self, n_cells: int, delta: float, dt: float, n_bg: float):
        self.n_cells = n_cells
        self.delta = delta
        self.dt = dt
        self.eps_bg = n_bg ** 2
        self.Ey = np.zeros(n_cells + 1)
        self.Hx = np.zeros(n_cells)

    def step(self, source_value: float) -> None:
        dz, dt = self.delta, self.dt
        # H update (usa E no nível atual, ANTES de injetar a fonte deste passo)
        self.Hx += (dt / MU0) * (self.Ey[1:] - self.Ey[:-1]) / dz
        # E update (interior; a extremidade 0 é sobrescrita pela fonte a seguir)
        self.Ey[1:-1] += (dt / (EPS0 * self.eps_bg)) * (self.Hx[1:] - self.Hx[:-1]) / dz
        self.Ey[0] = source_value  # fonte "hard" (onda progressiva pura para a direita)


def gaussian_modulated_source(t: np.ndarray, f0: float, tau: float, t0: float) -> np.ndarray:
    return np.exp(-((t - t0) / tau) ** 2) * np.sin(2.0 * np.pi * f0 * (t - t0))


# ==============================================================================
# 5. SIMULAÇÃO COMPLETA
# ==============================================================================
def run_fdtd(domain: FDTDDomain, n_steps: int, f0: float, tau: float, t0: float,
             verbose: bool = True) -> Dict:
    """
    Roda a simulação completa: injeta um pulso Gaussiano-modulado via TF/SF
    e grava, a cada passo, o campo Ey (médio em x,y — filtra harmônicos de
    Bloch m!=0) nos monitores de entrada (SF: só campo espalhado) e saída
    (TF: campo total), além do próprio Ey incidente de referência (da
    grade 1D) nesses dois planos, para normalização na extração de H(f).
    """
    fields = init_fields(domain)
    sigma_node, sigma_half = cpml_profile(domain.nz, domain.npml, domain.delta)
    b_half, a_half = cpml_coefficients(sigma_half, domain.dt)
    b_node, a_node = cpml_coefficients(sigma_node, domain.dt)
    b_node_int, a_node_int = b_node[1:-1], a_node[1:-1]

    n1d_pad = n_steps + 20
    aux = Aux1D(domain.nz + n1d_pad, domain.delta, domain.dt, domain.n_bg)

    k_tfsf = domain.k_tfsf
    time_axis = (np.arange(n_steps) + 0.5) * domain.dt  # nível "E" aproximado (ver nota abaixo)

    mon_in_scat = np.zeros(n_steps)
    mon_out_total = np.zeros(n_steps)
    inc_ref_in = np.zeros(n_steps)
    inc_ref_out = np.zeros(n_steps)

    dz = domain.delta
    dt = domain.dt

    for n in range(n_steps):
        t_n = n * dt
        src_val = gaussian_modulated_source(np.array([t_n]), f0, tau, t0)[0]

        Einc_at_ktfsf_n = aux.Ey[k_tfsf]  # nível E "n" (antes de avançar aux)

        # ---- H update (3D) ----
        Ex, Ey, Ez = fields["Ex"], fields["Ey"], fields["Ez"]
        Hx, Hy, Hz = fields["Hx"], fields["Hy"], fields["Hz"]
        dEz_dy = (np.roll(Ez, -1, axis=1) - Ez) / dz
        dEy_dz_raw = (Ey[:, :, 1:] - Ey[:, :, :-1]) / dz
        fields["psi_Ey_z"][...] = b_half[None, None, :] * fields["psi_Ey_z"] + a_half[None, None, :] * dEy_dz_raw
        dEy_dz_eff = dEy_dz_raw - fields["psi_Ey_z"]
        Hx -= (dt / MU0) * (dEz_dy - dEy_dz_eff)

        dEx_dz_raw = (Ex[:, :, 1:] - Ex[:, :, :-1]) / dz
        fields["psi_Ex_z"][...] = b_half[None, None, :] * fields["psi_Ex_z"] + a_half[None, None, :] * dEx_dz_raw
        dEx_dz_eff = dEx_dz_raw - fields["psi_Ex_z"]
        dEz_dx = (np.roll(Ez, -1, axis=0) - Ez) / dz
        Hy -= (dt / MU0) * (dEx_dz_eff - dEz_dx)

        dEy_dx = (np.roll(Ey, -1, axis=0) - Ey) / dz
        dEx_dy = (np.roll(Ex, -1, axis=1) - Ex) / dz
        Hz -= (dt / MU0) * (dEy_dx - dEx_dy)

        # ---- avança a grade auxiliar 1D (fonte suave + ABC de Mur) ----
        aux.step(src_val)
        Hinc_at_ktfsf_half = aux.Hx[k_tfsf - 1]  # nível H "n+1/2"

        # ---- correção TF/SF em Hx (usa Einc no nível n, ANTES do avanço acima) ----
        Hx[:, :, k_tfsf - 1] -= (dt / MU0) * (Einc_at_ktfsf_n / dz)

        # ---- E update (3D) ----
        dHz_dy = (Hz - np.roll(Hz, 1, axis=1)) / dz
        dHy_dz_raw = np.zeros_like(Ex)
        dHy_dz_raw[:, :, 1:-1] = (Hy[:, :, 1:] - Hy[:, :, :-1]) / dz
        fields["psi_Hy_z"][...] = (b_node_int[None, None, :] * fields["psi_Hy_z"]
                                    + a_node_int[None, None, :] * dHy_dz_raw[:, :, 1:-1])
        dHy_dz_eff = np.zeros_like(Ex)
        dHy_dz_eff[:, :, 1:-1] = dHy_dz_raw[:, :, 1:-1] - fields["psi_Hy_z"]
        Ex[:, :, 1:-1] += (dt / (EPS0 * domain.eps_ex[:, :, 1:-1])) * (dHz_dy[:, :, 1:-1] - dHy_dz_eff[:, :, 1:-1])

        dHz_dx = (Hz - np.roll(Hz, 1, axis=0)) / dz
        dHx_dz_raw = np.zeros_like(Ey)
        dHx_dz_raw[:, :, 1:-1] = (Hx[:, :, 1:] - Hx[:, :, :-1]) / dz
        fields["psi_Hx_z"][...] = (b_node_int[None, None, :] * fields["psi_Hx_z"]
                                    + a_node_int[None, None, :] * dHx_dz_raw[:, :, 1:-1])
        dHx_dz_eff = np.zeros_like(Ey)
        dHx_dz_eff[:, :, 1:-1] = dHx_dz_raw[:, :, 1:-1] - fields["psi_Hx_z"]
        Ey[:, :, 1:-1] += (dt / (EPS0 * domain.eps_ey[:, :, 1:-1])) * (dHx_dz_eff[:, :, 1:-1] - dHz_dx[:, :, 1:-1])

        dHy_dx = (Hy - np.roll(Hy, 1, axis=0)) / dz
        dHx_dy = (Hx - np.roll(Hx, 1, axis=1)) / dz
        Ez += (dt / (EPS0 * domain.eps_ez)) * (dHy_dx - dHx_dy)

        # ---- correção TF/SF em Ey (usa Hinc em n+1/2, calculado acima) ----
        Ey[:, :, k_tfsf] -= (dt / (EPS0 * domain.eps_ey[:, :, k_tfsf])) * (Hinc_at_ktfsf_half / dz)

        # ---- monitores ----
        mon_in_scat[n] = np.mean(Ey[:, :, domain.z_mon_in])
        mon_out_total[n] = np.mean(Ey[:, :, domain.z_mon_out])
        inc_ref_in[n] = aux.Ey[domain.z_mon_in]
        inc_ref_out[n] = aux.Ey[domain.z_mon_out]

        if verbose and (n % max(1, n_steps // 10) == 0 or n == n_steps - 1):
            print(f"    passo {n+1}/{n_steps}  t={t_n*1e15:.1f}fs  "
                  f"|Ey_mon_out|={abs(mon_out_total[n]):.3e}", flush=True)

    return {
        "time": time_axis, "dt": dt,
        "mon_in_scat": mon_in_scat, "mon_out_total": mon_out_total,
        "inc_ref_in": inc_ref_in, "inc_ref_out": inc_ref_out,
        "domain": domain,
    }


# ==============================================================================
# 6. EXTRAÇÃO DE H(f) = r(f), t(f) POR FFT
# ==============================================================================
def extract_spectral_RT(run_result: Dict, f_min: float, f_max: float, n_freq: int = 60) -> Dict:
    """FFT dos sinais temporais e razão espectral: r(f)=FFT(scat_in)/FFT(inc_in),
    t(f)=FFT(total_out)/FFT(inc_out). R=|r|^2, T=|t|^2 (mesmo n_bg dos dois lados)."""
    dt = run_result["dt"]
    n = len(run_result["mon_in_scat"])
    freqs_fft = np.fft.rfftfreq(n, d=dt)

    F_scat_in = np.fft.rfft(run_result["mon_in_scat"])
    F_inc_in = np.fft.rfft(run_result["inc_ref_in"])
    F_total_out = np.fft.rfft(run_result["mon_out_total"])
    F_inc_out = np.fft.rfft(run_result["inc_ref_out"])

    f_query = np.linspace(f_min, f_max, n_freq)
    r_f = np.interp(f_query, freqs_fft, F_scat_in.real) + 1j * np.interp(f_query, freqs_fft, F_scat_in.imag)
    r_f /= (np.interp(f_query, freqs_fft, F_inc_in.real) + 1j * np.interp(f_query, freqs_fft, F_inc_in.imag))
    t_f = np.interp(f_query, freqs_fft, F_total_out.real) + 1j * np.interp(f_query, freqs_fft, F_total_out.imag)
    t_f /= (np.interp(f_query, freqs_fft, F_inc_out.real) + 1j * np.interp(f_query, freqs_fft, F_inc_out.imag))

    return {
        "frequency": f_query, "wavelength": C_LIGHT / f_query,
        "r": r_f, "t": t_f, "R": np.abs(r_f) ** 2, "T": np.abs(t_f) ** 2,
    }


def cfl_report(domain: FDTDDomain) -> str:
    dt_limit = domain.delta / (C_LIGHT * np.sqrt(3.0))
    return (f"dt={domain.dt*1e18:.3f} as | limite CFL={dt_limit*1e18:.3f} as | "
            f"margem={domain.dt/dt_limit*100:.1f}% do limite")


# ==============================================================================
# 7. VARREDURA CW (onda contínua, uma frequência por vez) — MÉTODO VALIDADO
# ==============================================================================
# O caminho "pulso de banda larga + FFT" (run_fdtd/extract_spectral_RT acima)
# tem um bug NÃO RESOLVIDO: comparado contra Fabry-Pérot, dá erros que não
# encolhem com a resolução (R chegando a ~50% de erro relativo em alguns
# casos). Isolei que o motor Yee+CPML+TF/SF em si está correto testando em
# regime permanente com onda contínua (CW): rodando até a amplitude no
# monitor estabilizar, R e T batem com Fabry-Pérot dentro de ~1-6% (mesma
# ordem do erro de dispersão numérica já visto no FDFD nessa resolução) e
# R+T=0.999 (conservação de energia). Isso restringe o bug ao pulso/FFT
# especificamente (foi observado um entalhe espectral estreito e uma
# diferença grande entre o pico transiente da reflexão e seu valor de
# regime permanente) — ainda não diagnosticado.
#
# Até esse bug ser resolvido, use run_cw_single_frequency ou
# spectral_sweep_cw para obter R(f)/T(f) — mais lento (uma simulação por
# frequência, como o FDFD), mas validado.
def run_cw_single_frequency(domain: FDTDDomain, f0: float, n_cycles_ramp: float = 8.0,
                             n_cycles_total: float = 40.0, tail_fraction: float = 0.2) -> Dict:
    """Roda onda contínua em f0 (com rampa suave) até regime permanente, e
    mede R,T pela amplitude de pico na parte final do sinal (tail_fraction)."""
    fields = init_fields(domain)
    sigma_node, sigma_half = cpml_profile(domain.nz, domain.npml, domain.delta)
    b_half, a_half = cpml_coefficients(sigma_half, domain.dt)
    b_node, a_node = cpml_coefficients(sigma_node, domain.dt)
    b_node_int, a_node_int = b_node[1:-1], a_node[1:-1]

    period_steps = max(1, int(round(1.0 / f0 / domain.dt)))
    n_steps = int(n_cycles_total * period_steps)
    ramp_time = n_cycles_ramp / f0

    aux = Aux1D(domain.nz + n_steps + 20, domain.delta, domain.dt, domain.n_bg)
    k_tfsf = domain.k_tfsf
    dz, dt = domain.delta, domain.dt

    mon_in_scat = np.zeros(n_steps)
    mon_out_total = np.zeros(n_steps)
    inc_ref_in = np.zeros(n_steps)
    inc_ref_out = np.zeros(n_steps)

    for n in range(n_steps):
        t_n = n * dt
        ramp = min(1.0, t_n / ramp_time)
        src_val = ramp * np.sin(2.0 * np.pi * f0 * t_n)

        Einc_n = aux.Ey[k_tfsf]
        Ex, Ey, Ez = fields["Ex"], fields["Ey"], fields["Ez"]
        Hx, Hy, Hz = fields["Hx"], fields["Hy"], fields["Hz"]

        dEz_dy = (np.roll(Ez, -1, axis=1) - Ez) / dz
        dEy_dz_raw = (Ey[:, :, 1:] - Ey[:, :, :-1]) / dz
        fields["psi_Ey_z"][...] = b_half[None, None, :] * fields["psi_Ey_z"] + a_half[None, None, :] * dEy_dz_raw
        Hx -= (dt / MU0) * (dEz_dy - (dEy_dz_raw - fields["psi_Ey_z"]))

        dEx_dz_raw = (Ex[:, :, 1:] - Ex[:, :, :-1]) / dz
        fields["psi_Ex_z"][...] = b_half[None, None, :] * fields["psi_Ex_z"] + a_half[None, None, :] * dEx_dz_raw
        dEz_dx = (np.roll(Ez, -1, axis=0) - Ez) / dz
        Hy -= (dt / MU0) * ((dEx_dz_raw - fields["psi_Ex_z"]) - dEz_dx)

        dEy_dx = (np.roll(Ey, -1, axis=0) - Ey) / dz
        dEx_dy = (np.roll(Ex, -1, axis=1) - Ex) / dz
        Hz -= (dt / MU0) * (dEy_dx - dEx_dy)

        aux.step(src_val)
        Hinc_half = aux.Hx[k_tfsf - 1]
        Hx[:, :, k_tfsf - 1] -= (dt / MU0) * (Einc_n / dz)

        dHz_dy = (Hz - np.roll(Hz, 1, axis=1)) / dz
        dHy_dz_raw = np.zeros_like(Ex)
        dHy_dz_raw[:, :, 1:-1] = (Hy[:, :, 1:] - Hy[:, :, :-1]) / dz
        fields["psi_Hy_z"][...] = (b_node_int[None, None, :] * fields["psi_Hy_z"]
                                    + a_node_int[None, None, :] * dHy_dz_raw[:, :, 1:-1])
        dHy_dz_eff = np.zeros_like(Ex)
        dHy_dz_eff[:, :, 1:-1] = dHy_dz_raw[:, :, 1:-1] - fields["psi_Hy_z"]
        Ex[:, :, 1:-1] += (dt / (EPS0 * domain.eps_ex[:, :, 1:-1])) * (dHz_dy[:, :, 1:-1] - dHy_dz_eff[:, :, 1:-1])

        dHz_dx = (Hz - np.roll(Hz, 1, axis=0)) / dz
        dHx_dz_raw = np.zeros_like(Ey)
        dHx_dz_raw[:, :, 1:-1] = (Hx[:, :, 1:] - Hx[:, :, :-1]) / dz
        fields["psi_Hx_z"][...] = (b_node_int[None, None, :] * fields["psi_Hx_z"]
                                    + a_node_int[None, None, :] * dHx_dz_raw[:, :, 1:-1])
        dHx_dz_eff = np.zeros_like(Ey)
        dHx_dz_eff[:, :, 1:-1] = dHx_dz_raw[:, :, 1:-1] - fields["psi_Hx_z"]
        Ey[:, :, 1:-1] += (dt / (EPS0 * domain.eps_ey[:, :, 1:-1])) * (dHx_dz_eff[:, :, 1:-1] - dHz_dx[:, :, 1:-1])

        dHy_dx = (Hy - np.roll(Hy, 1, axis=0)) / dz
        dHx_dy = (Hx - np.roll(Hx, 1, axis=1)) / dz
        Ez += (dt / (EPS0 * domain.eps_ez)) * (dHy_dx - dHx_dy)

        Ey[:, :, k_tfsf] -= (dt / (EPS0 * domain.eps_ey[:, :, k_tfsf])) * (Hinc_half / dz)

        mon_in_scat[n] = np.mean(Ey[:, :, domain.z_mon_in])
        mon_out_total[n] = np.mean(Ey[:, :, domain.z_mon_out])
        inc_ref_in[n] = aux.Ey[domain.z_mon_in]
        inc_ref_out[n] = aux.Ey[domain.z_mon_out]

    tail = slice(int(n_steps * (1.0 - tail_fraction)), n_steps)
    amp_scat = np.max(np.abs(mon_in_scat[tail]))
    amp_inc_in = np.max(np.abs(inc_ref_in[tail]))
    amp_out = np.max(np.abs(mon_out_total[tail]))
    amp_inc_out = np.max(np.abs(inc_ref_out[tail]))

    R = (amp_scat / amp_inc_in) ** 2
    T = (amp_out / amp_inc_out) ** 2
    return {"f0": f0, "wavelength": C_LIGHT / f0, "R": R, "T": T, "A": 1.0 - R - T,
            "n_steps": n_steps, "amp_scat": amp_scat, "amp_inc_in": amp_inc_in,
            "amp_out": amp_out, "amp_inc_out": amp_inc_out}


def spectral_sweep_cw(domain: FDTDDomain, frequencies: np.ndarray, verbose: bool = True, **kwargs) -> Dict:
    """Varre R(f),T(f) rodando uma simulação CW por frequência (mais lento
    que o pulso único, mas validado — ver nota acima de por que o caminho
    pulso+FFT não deve ser usado ainda)."""
    R = np.zeros(len(frequencies))
    T = np.zeros(len(frequencies))
    for i, f in enumerate(frequencies):
        r = run_cw_single_frequency(domain, f, **kwargs)
        R[i], T[i] = r["R"], r["T"]
        if verbose:
            print(f"    [{i+1}/{len(frequencies)}] lambda={C_LIGHT/f*1e9:.1f}nm  "
                  f"R={R[i]:.5f}  T={T[i]:.5f}  A={1-R[i]-T[i]:.5f}", flush=True)
    return {"frequency": np.asarray(frequencies), "wavelength": C_LIGHT / np.asarray(frequencies),
            "R": R, "T": T, "A": 1.0 - R - T}


if __name__ == "__main__":
    print("Use validate_fdtd3d.py para rodar a validação contra Fabry-Pérot / fdfd2d.py.")