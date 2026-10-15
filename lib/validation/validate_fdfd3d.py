"""
validate_fdfd3d.py — validação do FDFD 3D pela lâmina homogênea, com os mesmos critérios do FDTD.

Parâmetros vêm dos presets de validação em lib/geometry/unit001_constantes.py (seção 11).
Critérios derivados da física:
  1) Ordem de convergência: diferenças centrais de 2ª ordem; p ≈ 2.
  2) Conservação: |R + T + A_vol - 1| abaixo do erro de discretização. A_vol vem da
     integral de q no volume, independente de R e T.
"""
import math

from lib.solvers.fdfd3d import (
    build_domain_3d,
    solve_fdfd_3d,
    analyze_solution_3d,
    homogeneous_slab_geom_3d,
)
from lib.solvers.fdfd2d import analytic_slab_RT
from lib.geometry.unit001_constantes import (
    LAMINA_TESTE_LAMBDA0,
    LAMINA_TESTE_N_BG,
    LAMINA_TESTE_N_SLAB,
    LAMINA_TESTE_ESPESSURA,
    LAMINA_TESTE_NX,
    NIVEIS_PPW_CONVERGENCIA,
    ORDEM_TEORICA_2A,
    TOL_ORDEM_CONVERGENCIA,
)


def _caso(ppw):
    lam, n_bg, n_slab = LAMINA_TESTE_LAMBDA0, LAMINA_TESTE_N_BG, LAMINA_TESTE_N_SLAB
    dz = lam / (n_slab * ppw)
    nz = max(1, int(round(LAMINA_TESTE_ESPESSURA / dz)))
    geom = homogeneous_slab_geom_3d(LAMINA_TESTE_NX, LAMINA_TESTE_NX, nz, dz, dz, dz, n_slab)
    npml = math.ceil(lam / (n_slab * dz))
    buffer = math.ceil(lam / dz)
    domain = build_domain_3d(geom, lam, n_bg=n_bg, npml_cells=npml, buffer_cells=buffer)
    result = solve_fdfd_3d(domain)
    rt = analyze_solution_3d(result)
    R = float(rt["RT_power"]["R_power"])
    T = float(rt["RT_power"]["T_power"])
    A_vol = float(rt["absorption"]["A_volume"])
    an = analytic_slab_RT(lam, n_bg, n_slab, nz * dz)
    return {"ppw": ppw, "nz": nz, "npml": npml, "buffer": buffer,
            "R": R, "T": T, "A_vol": A_vol,
            "errR": abs(R - an["R"]), "errT": abs(T - an["T"]),
            "cons": abs(R + T + A_vol - 1.0)}


def main():
    casos = [_caso(p) for p in NIVEIS_PPW_CONVERGENCIA]
    print("ppw | nz  npml buffer |      R        T       A_vol | errR      errT      | closure")
    for c in casos:
        print(f"{c['ppw']:3d} | {c['nz']:3d} {c['npml']:4d} {c['buffer']:6d} | "
              f"{c['R']:.5f} {c['T']:.5f} {c['A_vol']:.5f} | {c['errR']:.2e} {c['errT']:.2e} | "
              f"{c['cons']:.2e}")

    e_first = max(casos[0]["errR"], casos[0]["errT"])
    e_last = max(casos[-1]["errR"], casos[-1]["errT"])
    ratio = NIVEIS_PPW_CONVERGENCIA[-1] / NIVEIS_PPW_CONVERGENCIA[0]
    p = math.log(e_first / e_last) / math.log(ratio)
    ok_ordem = abs(p - ORDEM_TEORICA_2A) <= TOL_ORDEM_CONVERGENCIA
    ok_cons = all(c["cons"] <= max(c["errR"], c["errT"]) for c in casos)

    print(f"\nordem de convergência p = {p:.2f} (teórica {ORDEM_TEORICA_2A:.0f}, "
          f"faixa ±{TOL_ORDEM_CONVERGENCIA})  ->  {'PASS' if ok_ordem else 'FAIL'}")
    print(f"|R+T+A_vol-1| <= erro de discretização em todas as malhas  ->  {'PASS' if ok_cons else 'FAIL'}")
    status = "PASS" if (ok_ordem and ok_cons) else "FAIL"
    print(f"VEREDITO FDFD 3D (lâmina): {status}")
    return {"status": status, "p": p, "casos": casos}


if __name__ == "__main__":
    main()
