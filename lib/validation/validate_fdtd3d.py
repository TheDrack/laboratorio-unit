"""
validate_fdtd3d.py — validação do FDTD 3D pelo caminho CW (o único validado; ver fdtd3d.py).

Parâmetros vêm dos presets de validação em lib/geometry/unit001_constantes.py (seção 11).
Critérios derivados da física:
  1) Ordem de convergência: Yee é de 2ª ordem; p = log(e_first/e_last)/log(ratio) ≈ 2.
  2) Conservação: |R + T - 1| abaixo do erro de discretização em cada malha.
"""
import math

from lib.solvers import fdtd3d as F
from lib.solvers.fdfd2d import analytic_slab_RT
from lib.geometry.unit001_constantes import (
    C_LIGHT,
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
    eps = F.homogeneous_slab_eps(LAMINA_TESTE_NX, LAMINA_TESTE_NX, nz, n_slab)
    npml = math.ceil(lam / (n_slab * dz))
    buffer = math.ceil(lam / dz)
    dom = F.build_fdtd_domain(eps, lam, n_bg=n_bg, npml=npml,
                              buffer_cells=buffer, resolution_ppw=ppw)
    r = F.run_cw_single_frequency(dom, C_LIGHT / lam)
    R, T = float(r["R"]), float(r["T"])
    an = analytic_slab_RT(lam, n_bg, n_slab, nz * dz)
    return {"ppw": ppw, "nz": nz, "npml": npml, "buffer": buffer, "R": R, "T": T,
            "errR": abs(R - an["R"]), "errT": abs(T - an["T"]),
            "cons": abs(R + T - 1.0)}


def main():
    casos = [_caso(p) for p in NIVEIS_PPW_CONVERGENCIA]
    print("ppw | nz  npml buffer |      R        T   | errR      errT      |R+T-1|")
    for c in casos:
        print(f"{c['ppw']:3d} | {c['nz']:3d} {c['npml']:4d} {c['buffer']:6d} | "
              f"{c['R']:.5f} {c['T']:.5f} | {c['errR']:.2e} {c['errT']:.2e} | {c['cons']:.2e}")

    e_first = max(casos[0]["errR"], casos[0]["errT"])
    e_last = max(casos[-1]["errR"], casos[-1]["errT"])
    ratio = NIVEIS_PPW_CONVERGENCIA[-1] / NIVEIS_PPW_CONVERGENCIA[0]
    p = math.log(e_first / e_last) / math.log(ratio)
    ok_ordem = abs(p - ORDEM_TEORICA_2A) <= TOL_ORDEM_CONVERGENCIA
    ok_cons = all(c["cons"] <= max(c["errR"], c["errT"]) for c in casos)

    print(f"\nordem de convergência p = {p:.2f} (teórica {ORDEM_TEORICA_2A:.0f}, "
          f"faixa ±{TOL_ORDEM_CONVERGENCIA})  ->  {'PASS' if ok_ordem else 'FAIL'}")
    print(f"|R+T-1| <= erro de discretização em todas as malhas  ->  {'PASS' if ok_cons else 'FAIL'}")
    status = "PASS" if (ok_ordem and ok_cons) else "FAIL"
    print(f"VEREDITO FDTD 3D (CW, lâmina): {status}")
    return {"status": status, "p": p, "casos": casos}


if __name__ == "__main__":
    main()
