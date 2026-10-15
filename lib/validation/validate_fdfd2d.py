"""
validate_fdfd2d.py
================================================================================
BATERIA DE VALIDAÇÃO FÍSICA DO FDFD 2D

1. contraste zero        4. PML                  7. absorção volumétrica
2. espessura zero        5. posição dos monitores 8. espectro transversal
3. convergência espacial 6. conservação de energia (via A_difference, não
                             mais via o "energy_error" tautológico removido)

=============================== CORREÇÕES NESTA REVISÃO =======================
1. run_case: o tratamento de "espessura zero" acessava geom["eps_r"] e
   domain["eps_r"]/domain["j_start"]/domain["j_end"]/domain["source"] —
   NENHUMA dessas chaves existe (homogeneous_slab_geom usa a chave
   "epsilon", não "eps_r"; e `domain` é um dataclass DomainSetup, acessado
   por atributo (domain.eps, domain.z_struct_start...), não por índice —
   e não existe nenhum atributo "source" nele). Isso derrubava teste_E()
   com TypeError na hora. Reescrito para simplesmente inserir uma
   "estrutura" de 1 célula com o MESMO índice do fundo (contraste zero
   -> fisicamente equivalente a não ter estrutura nenhuma), sem tocar em
   internals do domínio.
2. print_table: formatava números via str() cru (ex.: "0.16272000000000002"),
   deixando as tabelas ilegíveis. Agora usa um formato por coluna.
3. Colunas "energy_error" trocadas por "A" (para os testes com material sem
   perdas, onde A->0 é o indicador correto) ou "A_difference" (para os
   testes com material COM perdas, onde A_flux != 0 e o cross-check real é
   contra A_volume) — ver fdfd2d.py para a explicação de por que
   "energy_error" era tautologicamente zero e não testava nada.
4. salvar_csv: caminho default trocado para um local gravável fixo.
================================================================================
"""

from __future__ import annotations

import csv
import numpy as np

from lib.solvers.fdfd2d import (
    build_domain,
    solve_fdfd,
    analyze_solution,
    homogeneous_slab_geom,
    analytic_slab_RT,
)
from lib.geometry.unit001_constantes import (VALID_N_TESTE, VALID_N_SLAB_TESTE)


# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
WAVELENGTH = 1.0e-6
N_BG = 1.0
N_SLAB = 2.0
THICKNESS = 0.3e-6
NX = 8


# ==============================================================================
# CASO BASE
# ==============================================================================
def run_case(resolution_ppw=60, npml_cells=30, buffer_cells=30,
             n_slab=N_SLAB, thickness=THICKNESS, n_bg=N_BG):
    max_n = max(abs(n_bg), abs(n_slab))
    dz = WAVELENGTH / (max_n * resolution_ppw)
    dx = dz

    if thickness <= 1e-14:
        # CORRIGIDO: "espessura zero" agora é só uma célula de estrutura
        # com o MESMO índice do fundo -- fisicamente equivalente a não
        # ter estrutura nenhuma (fonte b = -k0^2(eps-eps_bg)*Einc = 0
        # automaticamente ali, já que eps==eps_bg). Não precisa mexer em
        # nenhum campo interno do domínio.
        nz_struct = 0
        geom = homogeneous_slab_geom(NX, 1, dx, dz, n_bg)
        physical_thickness = 0.0
    else:
        nz_struct = max(1, int(round(thickness / dz)))
        geom = homogeneous_slab_geom(NX, nz_struct, dx, dz, n_slab)
        physical_thickness = nz_struct * dz

    domain = build_domain(geom, WAVELENGTH, n_bg=n_bg,
                           npml_cells=npml_cells, buffer_cells=buffer_cells)
    result = solve_fdfd(domain)
    analysis = analyze_solution(result)
    rt = analysis["RT"]

    analytic = analytic_slab_RT(WAVELENGTH, n_bg, n_slab, physical_thickness)

    return {
        "dz_nm": dz * 1e9,
        "npml": npml_cells,
        "buffer": buffer_cells,
        "nz_struct": nz_struct,
        "thickness_nm": physical_thickness * 1e9,
        "R": rt["R"],
        "T": rt["T"],
        "A": rt["A_flux"],
        "A_volume": analysis["absorption"]["A_volume"],
        "A_difference": analysis["absorption"]["A_difference"],
        "dR": abs(rt["R"] - analytic["R"]),
        "dT": abs(rt["T"] - analytic["T"]),
        "R_poynting": rt["R_poynting"],
        "T_poynting": rt["T_poynting"],
        "leak_in": rt["leak_in"],
        "leak_out": rt["leak_out"],
    }


# ==============================================================================
# TABELA (CORRIGIDO: formatação numérica por coluna)
# ==============================================================================
_DEFAULT_FMT = {
    "dz_nm": ".2f", "npml": "d", "buffer": "d", "nz_struct": "d",
    "thickness_nm": ".2f",
    "R": ".5f", "T": ".5f", "A": ".2e", "A_volume": ".2e", "A_difference": ".2e",
    "dR": ".2e", "dT": ".2e",
    "R_poynting": ".5f", "T_poynting": ".5f",
    "leak_in": ".2e", "leak_out": ".2e",
}


def _fmt_value(value, spec):
    try:
        return format(value, spec)
    except (ValueError, TypeError):
        return str(value)


def print_table(rows, columns, fmt=None):
    if not rows:
        return
    fmt = {**_DEFAULT_FMT, **(fmt or {})}
    cells = [[_fmt_value(r[c], fmt.get(c, ".5g")) for c in columns] for r in rows]
    widths = {c: max(len(c), *(len(cells[i][j]) for i in range(len(rows))))
              for j, c in enumerate(columns)}
    header = " | ".join(f"{c:>{widths[c]}}" for c in columns)
    print(header)
    print("-" * len(header))
    for row_cells in cells:
        print(" | ".join(f"{v:>{widths[c]}}" for v, c in zip(row_cells, columns)))


# ==============================================================================
# TESTE A — CONVERGÊNCIA ESPACIAL
# ==============================================================================
def teste_A():
    print("\n" + "=" * 100)
    print("TESTE A — CONVERGÊNCIA ESPACIAL  (material sem perdas -> A deveria -> 0)")
    print("=" * 100)
    rows = [run_case(resolution_ppw=ppw, npml_cells=30, buffer_cells=30)
            for ppw in [15, 30, 60, 90, 120]]
    print_table(rows, ["dz_nm", "R", "T", "A", "dR", "dT"])
    return rows


# ==============================================================================
# TESTE B — CONVERGÊNCIA DO PML
# ==============================================================================
def teste_B():
    print("\n" + "=" * 100)
    print("TESTE B — CONVERGÊNCIA DO PML  (A não deveria mudar muito se o problema não for truncamento)")
    print("=" * 100)
    rows = [run_case(resolution_ppw=60, npml_cells=npml, buffer_cells=40)
            for npml in [10, 15, 20, 30, 40, 60]]
    print_table(rows, ["npml", "R", "T", "A", "dR", "dT"])
    return rows


# ==============================================================================
# TESTE C — POSIÇÃO DOS MONITORES
# ==============================================================================
def teste_C():
    print("\n" + "=" * 100)
    print("TESTE C — POSIÇÃO DOS MONITORES  (R,T não deveriam mudar se não há campo evanescente residual)")
    print("=" * 100)
    rows = [run_case(resolution_ppw=60, npml_cells=30, buffer_cells=buf)
            for buf in [10, 20, 30, 40, 60, 80]]
    print_table(rows, ["buffer", "R", "T", "A", "dR", "dT", "leak_in", "leak_out"])
    return rows


# ==============================================================================
# TESTE D — CONTRASTE ZERO
# ==============================================================================
def teste_D():
    print("\n" + "=" * 100)
    print("TESTE D — CONTRASTE ZERO (n_slab=n_bg=1.0): espera-se R~0, T~1, A~0")
    print("=" * 100)
    rows = [run_case(resolution_ppw=60, npml_cells=30, buffer_cells=30,
                      n_slab=N_BG, thickness=thickness)
            for thickness in [0.1e-6, 0.3e-6, 0.6e-6, 1.0e-6]]
    print_table(rows, ["thickness_nm", "R", "T", "A", "A_volume"])
    return rows


# ==============================================================================
# TESTE E — ESPESSURA ZERO  (CORRIGIDO: usa o novo caminho em run_case)
# ==============================================================================
def teste_E():
    print("\n" + "=" * 100)
    print("TESTE E — ESPESSURA ZERO (sem estrutura nenhuma): ar -> ar, espera-se R~0,T~1,A~0")
    print("(isola o piso de ruído numérico puro do PML+monitores, sem nenhuma interface real)")
    print("=" * 100)
    rows = [run_case(resolution_ppw=ppw, npml_cells=40, buffer_cells=40,
                      n_slab=2.0, thickness=0.0)
            for ppw in [30, 60, 120]]
    print_table(rows, ["dz_nm", "R", "T", "A", "A_volume"])
    return rows


# ==============================================================================
# TESTE F — CONSERVAÇÃO DE ENERGIA (com e sem perdas)
# ==============================================================================
def teste_F():
    print("\n" + "=" * 100)
    print("TESTE F — CONSERVAÇÃO DE ENERGIA")
    print("  A_difference = |A_flux - A_volume| é o cross-check real (duas medidas")
    print("  independentes de absorção). R_poynting/T_poynting devem bater com R/T modal.")
    print("=" * 100)
    materiais = list(VALID_N_TESTE)
    rows = []
    for n in materiais:
        r = run_case(resolution_ppw=60, npml_cells=40, buffer_cells=40, n_slab=n)
        r["material"] = str(n)
        rows.append(r)
    for r in rows:
        print(f"  material={r['material']:<12} R={r['R']:.5f}  T={r['T']:.5f}  A={r['A']:.5f}  "
              f"A_volume={r['A_volume']:.5f}  A_difference={r['A_difference']:.2e}  "
              f"R_poynting={r['R_poynting']:.5f}  T_poynting={r['T_poynting']:.5f}  "
              f"|ΔR_poynt|={abs(r['R_poynting']-r['R']):.2e}  |ΔT_poynt|={abs(r['T_poynting']-r['T']):.2e}")
    return rows


# ==============================================================================
# TESTE G — ABSORÇÃO ESPACIAL
# ==============================================================================
def teste_G():
    print("\n" + "=" * 100)
    print("TESTE G — ABSORÇÃO ESPACIAL (centroide/sigma da distribuição de absorção)")
    print("=" * 100)
    max_n = abs(2.0 + 0.15j)
    dz = WAVELENGTH / (max_n * 80.0)
    dx = dz
    nz_struct = max(1, int(round(THICKNESS / dz)))

    geom = homogeneous_slab_geom(NX, nz_struct, dx, dz, 2.0 + 0.15j)
    domain = build_domain(geom, WAVELENGTH, n_bg=1.0, npml_cells=40, buffer_cells=40)
    result = solve_fdfd(domain)
    analysis = analyze_solution(result)

    dist = analysis["absorption_distribution"]
    a_flux = analysis["RT"]["A_flux"]
    a_vol = analysis["absorption"]["A_volume"]

    print(f"A_flux   = {a_flux:.10f}")
    print(f"A_volume = {a_vol:.10f}")
    print(f"diferença = {abs(a_flux-a_vol):.3e}")
    print()
    print("CENTRO DA ABSORÇÃO")
    print(f"x_centroid = {dist['x_centroid']*1e9:.3f} nm")
    print(f"z_centroid = {dist['z_centroid']*1e9:.3f} nm")
    print(f"x_sigma = {dist['x_sigma']*1e9:.3f} nm")
    print(f"z_sigma = {dist['z_sigma']*1e9:.3f} nm")
    return analysis


# ==============================================================================
# TESTE H — ESPECTRO TRANSVERSAL
# ==============================================================================
def teste_H():
    print("\n" + "=" * 100)
    print("TESTE H — ESPECTRO TRANSVERSAL")
    print("=" * 100)
    dz = WAVELENGTH / (2.0 * 60.0)
    dx = dz
    nz_struct = max(1, int(round(THICKNESS / dz)))

    geom = homogeneous_slab_geom(NX, nz_struct, dx, dz, VALID_N_SLAB_TESTE)
    domain = build_domain(geom, WAVELENGTH, n_bg=1.0, npml_cells=30, buffer_cells=30)
    result = solve_fdfd(domain)
    analysis = analyze_solution(result)
    out = analysis["diffraction"]["outgoing"]

    print(f"{'m':>6} | {'kx [1/m]':>18} | {'kz [1/m]':>22} | {'power':>12} | {'propaga':>8}")
    print("-" * 90)
    mask = np.abs(out["m"]) <= 5
    for m, kx, kz, p, prop in zip(out["m"][mask], out["kx"][mask], out["kz"][mask],
                                   out["power_relative"][mask], out["propagating"][mask]):
        print(f"{m:>6d} | {kx:>18.5e} | {kz.real:>10.5e}{kz.imag:+.5e}j | "
              f"{p:>12.5e} | {str(bool(prop)):>8}")
    return out


# ==============================================================================
# CSV  (CORRIGIDO: caminho default gravável)
# ==============================================================================
def salvar_csv(rows, filename="/home/claude/fdfd_validation.csv"):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV salvo em: {filename}")


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    all_rows = []
    all_rows.extend(teste_A())
    all_rows.extend(teste_B())
    all_rows.extend(teste_C())
    teste_D()
    teste_E()
    teste_F()
    teste_G()
    teste_H()
    salvar_csv(all_rows)
