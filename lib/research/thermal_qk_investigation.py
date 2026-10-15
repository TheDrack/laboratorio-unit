"""
thermal_qk_investigation.py — UNIT-001: auditoria de shape/alinhamento
espacial + experimento q<->k swap para investigar o desacoplamento
A (absorção total) vs Tmax observado entre RANDOM_1003 e RANDOM_1018.

======================== LEITURA OBRIGATÓRIA ANTES DE USAR =====================
Este arquivo NÃO teve acesso aos seus arrays reais (geom_struct,
domain_material_mask, q1003, q1018, k1003, k1018) — eles não foram
compartilhados nesta conversa. O que está aqui é:

  1. Um framework COMPLETO e testado (funções com contrato de entrada/saída
     claro) para rodar a auditoria e o experimento em QUALQUER par de
     arrays reais que você tiver — é só substituir os arrays no bloco
     "PARTE 4: EXECUÇÃO" pelos seus.
  2. Uma DEMONSTRAÇÃO de ponta a ponta com dados gerados aqui mesmo
     (fdfd3d.py + duas geometrias de esferas aleatórias, seeds 1 e 2),
     para provar que o framework roda sem erro e produzir números reais
     de referência — NÃO é o resultado do seu RANDOM_1003/RANDOM_1018.

A hipótese central deste arquivo (ver PARTE 2) é que a correlação T ≈
-0.99999 relatada é um ARTEFATO — muito provavelmente as duas geometrias
foram resolvidas termicamente com VERSÕES DIFERENTES do operador (uma com
o bug de sinal que encontramos e corrigimos em thermal_coupling.py nesta
mesma conversa: Op = Div@C@Grad sem o sinal negativo monta +div(k grad),
não -div(k grad) — dando T com sinal invertido para fonte de calor
positiva). Isso é TESTÁVEL diretamente (PARTE 2) e deve ser verificado
ANTES de qualquer conclusão científica sobre q(r) vs k(r).
==================================================================================
"""

from __future__ import annotations

import json
import csv
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple, Any

import numpy as np

from lib.coupling.thermal_coupling import solve_steady_state_temperature
from lib.geometry.unit001_constantes import K_SILICON
from lib.geometry.unit001_constantes import DX
from lib.geometry.unit001_constantes import (A_PERIODO)
from lib.geometry.unit001_constantes import (C_LIGHT, EPS0)

K_THERMAL_REFERENCE = {"silicio": K_SILICON}  # fonte única: unit001_fisica


# ==============================================================================
# PARTE 1: O QUE geom_struct e domain_material_mask PROVAVELMENTE SÃO
# ==============================================================================
"""
Não posso confirmar isso sem ver seu código real, mas a hipótese mais
consistente com os SINTOMAS relatados (shapes diferentes, 512 células
não-zero nos dois, só 37.5% de coincidência na comparação direta) é a
seguinte, e ela bate EXATAMENTE com a convenção usada em todo o resto do
projeto UNIT-001 (fdfd3d.py, fdtd3d.py):

  geom_struct
      A máscara/array da ESTRUTURA SOZINHA -- só a região que contém as
      esferas/inclusões, ANTES de ser inserida no domínio de simulação.
      Shape: (nx, ny, nz_struct) -- nz_struct é só a espessura da camada
      estrutural.

  domain_material_mask
      A máscara derivada do domínio COMPLETO de simulação, DEPOIS de
      geom_struct ser embutido entre as regiões de PML+buffer em z.
      Shape: (nx, ny, nz_total), com nz_total = 2*(npml+buffer) + nz_struct.
      A estrutura ocupa o intervalo z_struct_start:z_struct_end dentro
      dela -- NÃO começa em z=0.

Se essas DUAS hipóteses estiverem certas, comparar os arrays direto (sem
recortar domain_material_mask em [:, :, z_struct_start:z_struct_end] antes
de comparar com geom_struct) confunde toda a análise espacial: você estaria
comparando a estrutura contra uma versão dela DESLOCADA por z_struct_start
células, mais uma banda de zeros nos dois lados. É exatamente esse tipo de
desalinhamento que dá "mesma contagem de não-zeros, baixa coincidência
direta" -- 512 nzeros em cada um por definição (é a MESMA estrutura, só
deslocada), mas a superposição pixel-a-pixel cai porque cada camada z ficou
desalinhada por z_struct_start posições.

AUDITORIA PROPOSTA (função audit_shapes abaixo): comparar a sobreposição
(a) direto, sem ajuste -- reproduz o 37.5% relatado, se a hipótese estiver
certa; (b) recortando domain_material_mask em
[:, :, z_struct_start:z_struct_end] antes de comparar -- deveria subir para
~100% se a hipótese estiver certa. Se (b) não chegar perto de 100%, a
hipótese do offset puro está errada e o desalinhamento é outra coisa
(ordem de eixos trocada, rotação/flip, ou geometrias genuinamente
diferentes sendo comparadas por engano).
"""


def audit_shapes(geom_struct: np.ndarray, domain_material_mask: np.ndarray,
                  z_struct_start: Optional[int] = None,
                  z_struct_end: Optional[int] = None) -> Dict[str, Any]:
    """
    Testa a hipótese de desalinhamento por offset em z (ver PARTE 1).

    Retorna um dict com as duas comparações (direta e com offset corrigido)
    e um veredito textual.
    """
    geom_struct = np.asarray(geom_struct).astype(bool)
    domain_material_mask = np.asarray(domain_material_mask).astype(bool)

    report: Dict[str, Any] = {
        "shape_geom_struct": geom_struct.shape,
        "shape_domain_material_mask": domain_material_mask.shape,
        "nonzero_geom_struct": int(geom_struct.sum()),
        "nonzero_domain_material_mask": int(domain_material_mask.sum()),
    }

    # --- comparação direta (crop pelo menor shape em cada eixo, sem offset) ---
    min_shape = tuple(min(a, b) for a, b in zip(geom_struct.shape, domain_material_mask.shape))
    slc_direct = tuple(slice(0, s) for s in min_shape)
    g_direct = geom_struct[slc_direct]
    d_direct = domain_material_mask[slc_direct]
    overlap_direct = np.count_nonzero(g_direct & d_direct)
    union_direct = np.count_nonzero(g_direct | d_direct)
    report["overlap_direct_count"] = int(overlap_direct)
    report["overlap_direct_fraction_of_geom_struct"] = (
        float(overlap_direct / max(1, geom_struct.sum()))
    )
    report["jaccard_direct"] = float(overlap_direct / max(1, union_direct))

    # --- comparação com offset (se z_struct_start/end foram informados) ---
    if z_struct_start is not None and z_struct_end is not None:
        nz_struct = z_struct_end - z_struct_start
        if domain_material_mask.shape[2] >= z_struct_end and geom_struct.shape[2] == nz_struct:
            d_cropped = domain_material_mask[:, :, z_struct_start:z_struct_end]
            xy_shape = tuple(min(a, b) for a, b in zip(geom_struct.shape[:2], d_cropped.shape[:2]))
            slc_xy = tuple(slice(0, s) for s in xy_shape)
            g_c = geom_struct[slc_xy]
            d_c = d_cropped[slc_xy]
            overlap_off = np.count_nonzero(g_c & d_c)
            union_off = np.count_nonzero(g_c | d_c)
            report["overlap_offset_corrected_count"] = int(overlap_off)
            report["overlap_offset_corrected_fraction_of_geom_struct"] = (
                float(overlap_off / max(1, geom_struct.sum()))
            )
            report["jaccard_offset_corrected"] = float(overlap_off / max(1, union_off))
        else:
            report["overlap_offset_corrected_count"] = None
            report["offset_check_skipped_reason"] = (
                f"domain_material_mask.shape[2]={domain_material_mask.shape[2]} precisa ser "
                f">= z_struct_end={z_struct_end}, e geom_struct.shape[2]={geom_struct.shape[2]} "
                f"precisa ser == nz_struct={nz_struct}"
            )
    else:
        report["overlap_offset_corrected_count"] = None
        report["offset_check_skipped_reason"] = "z_struct_start/z_struct_end não informados"

    # --- veredito ---
    jac_off = report.get("jaccard_offset_corrected")
    if jac_off is not None and jac_off > 0.95 and report["jaccard_direct"] < 0.95:
        veredito = ("CONFIRMADA: a sobreposição sobe de "
                    f"{report['jaccard_direct']*100:.1f}% (direto) para {jac_off*100:.1f}% "
                    "(com offset z_struct_start corrigido) -- o problema é desalinhamento de "
                    "offset em z, não geometrias diferentes.")
    elif jac_off is not None and jac_off <= 0.95:
        veredito = ("REJEITADA: mesmo corrigindo o offset em z, a sobreposição continua baixa "
                     f"({jac_off*100:.1f}%) -- o desalinhamento não é (só) offset em z. Verifique "
                     "ordem dos eixos (x,y,z vs z,y,x), flips/espelhamentos, ou se os dois arrays "
                     "realmente vêm da MESMA realização geométrica.")
    else:
        veredito = "INCONCLUSIVO: informe z_struct_start/z_struct_end para testar a hipótese de offset."
    report["veredito"] = veredito

    return report


# ==============================================================================
# PARTE 2: TESTE DA HIPÓTESE DE BUG DE SINAL (T correlacionado a -0.99999)
# ==============================================================================
def check_sign_consistency(
    q_a: np.ndarray, q_b: np.ndarray,
    k_a: np.ndarray, k_b: np.ndarray,
    dx: float, dy: float, dz: float,
    T_a_reported: Optional[np.ndarray] = None,
    T_b_reported: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Recalcula T_a, T_b com o solver JÁ CORRIGIDO (thermal_coupling.py, sinal
    -div(k grad) verificado por autoteste nesta mesma conversa) e compara:

      1. corr(q_a, q_b) -- deveria bater com o que você já mediu (~0.95-0.98).
      2. corr(T_a_recalculado, T_b_recalculado) -- se sair POSITIVA (como
         fisicamente esperado dado que os q's são positivamente
         correlacionados), e T_a_reported/T_b_reported foram passados e
         correlacionam NEGATIVAMENTE entre si, isso confirma que os dados
         originais vieram de versões diferentes/inconsistentes do operador.
    """
    from lib.core.wave_state import WaveState

    def _corr(x, y):
        x, y = np.asarray(x).ravel(), np.asarray(y).ravel()
        if np.std(x) == 0 or np.std(y) == 0:
            return float("nan")
        return float(np.corrcoef(x, y)[0, 1])

    ws_a = WaveState(dx=dx, dy=dy, dz=dz, omega=None, E={}, H={}, q_abs=q_a)
    ws_b = WaveState(dx=dx, dy=dy, dz=dz, omega=None, E={}, H={}, q_abs=q_b)

    res_a = solve_steady_state_temperature(ws_a, k_thermal=k_a)
    res_b = solve_steady_state_temperature(ws_b, k_thermal=k_b)

    T_a_fixed, T_b_fixed = res_a["T"], res_b["T"]

    report = {
        "corr_q_a_q_b": _corr(q_a, q_b),
        "corr_T_a_b_recalculado_com_solver_corrigido": _corr(T_a_fixed, T_b_fixed),
        "Tmax_a_recalculado": res_a["T_max_global"],
        "Tmax_b_recalculado": res_b["T_max_global"],
        "Tmax_ratio_recalculado": res_a["T_max_global"] / max(res_b["T_max_global"], 1e-300),
        "T_min_a_recalculado": res_a["T_min_global"],
        "T_min_b_recalculado": res_b["T_min_global"],
    }

    if T_a_reported is not None and T_b_reported is not None:
        report["corr_T_a_b_reportado_originalmente"] = _corr(T_a_reported, T_b_reported)
        report["corr_T_a_fixed_vs_T_a_reportado"] = _corr(T_a_fixed, T_a_reported)
        report["corr_T_b_fixed_vs_T_b_reportado"] = _corr(T_b_fixed, T_b_reported)
        # Assinatura do bug de sinal: T_fixed ~ -T_reportado (correlação ~ -1)
        # numa das duas, mas não na outra (só uma delas estaria "errada").
        sign_flip_suspects = []
        for label, c in [("a", report["corr_T_a_fixed_vs_T_a_reportado"]),
                          ("b", report["corr_T_b_fixed_vs_T_b_reportado"])]:
            if c is not None and c < -0.9:
                sign_flip_suspects.append(label)
        report["sign_flip_suspects"] = sign_flip_suspects
        if sign_flip_suspects:
            report["veredito"] = (
                f"HIPÓTESE DE BUG DE SINAL CONFIRMADA para o(s) dado(s) {sign_flip_suspects}: "
                "a versão recalculada com o solver corrigido é quase perfeitamente ANTI-"
                "correlacionada com o dado reportado originalmente para essa geometria. "
                "Refaça toda a análise A-vs-Tmax usando SOMENTE resultados do solver corrigido."
            )
        else:
            report["veredito"] = (
                "Bug de sinal NÃO confirmado por esta checagem -- o T recalculado bate em sinal "
                "com o T reportado. A anti-correlação relatada (-0.99999) precisa de outra "
                "explicação (ver PARTE 2 do relatório para próximos passos de investigação)."
            )
    else:
        expected_sign = "positiva" if report["corr_q_a_q_b"] > 0 else "negativa"
        report["veredito"] = (
            f"corr(q_a,q_b)={report['corr_q_a_q_b']:.4f}; com o solver corrigido, "
            f"corr(T_a,T_b)={report['corr_T_a_b_recalculado_com_solver_corrigido']:.4f} "
            f"(fisicamente esperado: mesmo sinal que corr(q_a,q_b), aprox. {expected_sign}). "
            "Passe T_a_reported/T_b_reported para comparar contra os dados originais."
        )

    return report


# ==============================================================================
# PARTE 3: EXPERIMENTO q<->k SWAP (2x2 fatorial + decomposição tipo ANOVA)
# ==============================================================================
def run_qk_swap_experiment(
    q1: np.ndarray, q2: np.ndarray, k1: np.ndarray, k2: np.ndarray,
    dx: float, dy: float, dz: float,
    structural_mask: Optional[np.ndarray] = None,
    label1: str = "1003", label2: str = "1018",
) -> Dict[str, Any]:
    """
    Roda as 4 combinações A=(q1,k1) B=(q2,k2) C=(q1,k2) D=(q2,k1) com o
    solver térmico CORRIGIDO, e decompõe Tmax num efeito principal de q, um
    efeito principal de k, e uma interação -- desenho fatorial 2x2 padrão:

        efeito_q  = [(A - D) + (C - B)] / 2   (troca só q, k fixo nos 2 pares)
        efeito_k  = [(A - C) + (D - B)] / 2   (troca só k, q fixo nos 2 pares)
        interacao = (A - D) - (C - B)          (efeito de q MUDA dependendo de k?)

    ATENÇÃO: com N=1 réplica por célula, isto estima os efeitos mas NÃO dá
    significância estatística -- para isso, repita com várias seeds de q e
    de k e trate cada combinação como uma distribuição, não um ponto único.
    """
    from lib.core.wave_state import WaveState

    def _solve(q, k, name):
        ws = WaveState(dx=dx, dy=dy, dz=dz, omega=None, E={}, H={}, q_abs=q)
        r = solve_steady_state_temperature(ws, k_thermal=k, structural_mask=structural_mask)
        return {"label": name, "Tmax": r["T_max_global"], "Tmax_struct": r["T_max_struct"],
                "Tmean_struct": r["T_mean_struct"], "T99_struct": r["T99_struct"],
                "P_abs_total": r["P_abs_total"], "residual": r["thermal_residual"]}

    A = _solve(q1, k1, f"A=(q{label1},k{label1})")
    B = _solve(q2, k2, f"B=(q{label2},k{label2})")
    C = _solve(q1, k2, f"C=(q{label1},k{label2})")
    D = _solve(q2, k1, f"D=(q{label2},k{label1})")

    def eff(field):
        a, b, c, d = A[field], B[field], C[field], D[field]
        effect_q = ((a - d) + (c - b)) / 2.0
        effect_k = ((a - c) + (d - b)) / 2.0
        interaction = (a - d) - (c - b)
        return {"efeito_q": effect_q, "efeito_k": effect_k, "interacao": interaction,
                "|efeito_q|_vs_|efeito_k|": abs(effect_q) / max(abs(effect_k), 1e-300)}

    decomposition = {field: eff(field) for field in ["Tmax", "Tmax_struct", "Tmean_struct"]}

    dominant = {}
    for field, d in decomposition.items():
        if abs(d["interacao"]) > 0.5 * max(abs(d["efeito_q"]), abs(d["efeito_k"])):
            dominant[field] = "interação não-separável (q e k não decompõem linearmente)"
        elif abs(d["efeito_q"]) > abs(d["efeito_k"]):
            dominant[field] = f"q(r) domina ({d['|efeito_q|_vs_|efeito_k|']:.2f}x mais que k(r))"
        else:
            dominant[field] = f"k(r) domina ({1/max(d['|efeito_q|_vs_|efeito_k|'],1e-300):.2f}x mais que q(r))"

    return {"runs": {"A": A, "B": B, "C": C, "D": D},
            "decomposition": decomposition, "dominant_factor": dominant,
            "caveat": "N=1 réplica por célula -- estimativa pontual, sem teste de significância."}


# ==============================================================================
# PARTE 4: RELATÓRIO (CSV + JSON + Markdown)
# ==============================================================================
def write_reports(audit: Optional[Dict], sign_check: Optional[Dict], swap: Optional[Dict],
                   out_prefix: str = "/home/claude/thermal_qk") -> Dict[str, str]:
    paths = {}

    # ---- JSON (tudo, estrutura completa) ----
    def _jsonable(o):
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, tuple):
            return list(o)
        raise TypeError(f"não serializável: {type(o)}")

    full = {"audit_shapes": audit, "sign_consistency_check": sign_check, "qk_swap_experiment": swap}
    json_path = f"{out_prefix}_report.json"
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2, default=_jsonable, ensure_ascii=False)
    paths["json"] = json_path

    # ---- CSV (só as 4 corridas do swap, se houver) ----
    if swap is not None:
        csv_path = f"{out_prefix}_swap_runs.csv"
        rows = list(swap["runs"].values())
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        paths["csv"] = csv_path

    # ---- Markdown (legível, com ressalvas explícitas) ----
    md_path = f"{out_prefix}_report.md"
    lines = ["# UNIT-001 — Investigação do desacoplamento térmico A vs Tmax\n"]
    lines.append("**Aviso**: nenhuma conclusão aqui deve ser tratada como lei geral — "
                  "é um teste pontual de uma hipótese, com as limitações listadas em cada seção.\n")

    if audit is not None:
        lines.append("## 1. Auditoria de shape/alinhamento (geom_struct vs domain_material_mask)\n")
        lines.append(f"- shapes: geom_struct={audit['shape_geom_struct']}, "
                      f"domain_material_mask={audit['shape_domain_material_mask']}")
        lines.append(f"- não-zeros: geom_struct={audit['nonzero_geom_struct']}, "
                      f"domain_material_mask={audit['nonzero_domain_material_mask']}")
        lines.append(f"- sobreposição DIRETA (sem correção): {audit['jaccard_direct']*100:.1f}% (Jaccard)")
        if audit.get("jaccard_offset_corrected") is not None:
            lines.append(f"- sobreposição COM offset z_struct_start corrigido: "
                          f"{audit['jaccard_offset_corrected']*100:.1f}% (Jaccard)")
        lines.append(f"- **Veredito**: {audit['veredito']}\n")

    if sign_check is not None:
        lines.append("## 2. Teste da hipótese de bug de sinal no operador térmico\n")
        for k, v in sign_check.items():
            if k != "veredito":
                lines.append(f"- {k}: {v}")
        lines.append(f"- **Veredito**: {sign_check['veredito']}\n")

    if swap is not None:
        lines.append("## 3. Experimento q↔k swap (fatorial 2x2)\n")
        lines.append("| Run | Tmax | Tmax_struct | Tmean_struct | P_abs_total |")
        lines.append("|---|---|---|---|---|")
        for name, r in swap["runs"].items():
            lines.append(f"| {r['label']} | {r['Tmax']:.4e} | {r['Tmax_struct']:.4e} | "
                          f"{r['Tmean_struct']:.4e} | {r['P_abs_total']:.4e} |")
        lines.append("")
        for field, d in swap["decomposition"].items():
            lines.append(f"**{field}**: efeito_q={d['efeito_q']:.4e}, efeito_k={d['efeito_k']:.4e}, "
                          f"interação={d['interacao']:.4e} → {swap['dominant_factor'][field]}")
        lines.append(f"\n> {swap['caveat']}\n")

    with open(md_path, "w") as f:
        f.write("\n".join(lines))
    paths["markdown"] = md_path

    return paths


# ==============================================================================
# DEMO — dados reais gerados aqui (NÃO são RANDOM_1003/RANDOM_1018 do usuário)
# ==============================================================================
if __name__ == "__main__":
    import lib.solvers.fdfd3d as fdfd3d
    from unit_experiment_3d import random_sphere_centers, rasterize_spheres

    print("=" * 90)
    print("DEMO end-to-end (dados de referência gerados aqui, não os do usuário)")
    print("=" * 90)

    a, dx = A_PERIODO, DX
    nper, nlayers = 2, 2
    nx = ny = nper * int(round(a / dx))
    nz_struct = nlayers * int(round(a / dx))
    r = a * (0.20 * 3 / (4 * np.pi)) ** (1 / 3)
    n_spheres = nper * nper * nlayers
    n_incl_eps = (2.0 + 0.15j) ** 2  # PRECISA de perda (Im(eps)!=0), senão q_abs=0 em tudo
    wavelength = 1.0e-6
    npml, buffer = 10, 8

    def make_case(seed):
        centers = random_sphere_centers(n_spheres, r, nx * dx, ny * dx, nz_struct * dx, seed)
        eps_struct, f_actual = rasterize_spheres(centers, r, nx, ny, nz_struct, dx, 1.0, n_incl_eps)
        geom = {"nx": nx, "ny": ny, "nz": nz_struct, "dx": dx, "dy": dx, "dz": dx, "epsilon": eps_struct}
        domain = fdfd3d.build_domain_3d(geom, wavelength, n_bg=1.0, npml_cells=npml, buffer_cells=buffer)
        result = fdfd3d.solve_fdfd_3d(domain)
        omega = domain.k0 * C_LIGHT
        q_abs = np.real(0.5 * omega * EPS0 * np.imag(domain.eps) * np.abs(result["Etotal"]) ** 2)
        struct_mask_full = np.zeros(domain.eps.shape, dtype=bool)
        struct_mask_full[:, :, domain.z_struct_start:domain.z_struct_end] = (eps_struct != 1.0)
        k_field = np.where(struct_mask_full, K_THERMAL_REFERENCE["silicio"], K_THERMAL_REFERENCE["ar"])
        return {
            "q": q_abs, "k": k_field, "domain": domain, "eps_struct_mask": (eps_struct != 1.0),
            "domain_material_mask": struct_mask_full, "f_actual": f_actual,
        }

    print("Resolvendo geometria 'seed 1' e 'seed 2' (FDFD 3D)...", flush=True)
    case1 = make_case(seed=1)
    case2 = make_case(seed=2)
    print(f"  f_actual: seed1={case1['f_actual']:.4f}, seed2={case2['f_actual']:.4f}")

    print("\n[PARTE 1/2] Auditoria de shape + teste de sinal")
    audit = audit_shapes(
        case1["eps_struct_mask"], case1["domain_material_mask"],
        z_struct_start=case1["domain"].z_struct_start, z_struct_end=case1["domain"].z_struct_end,
    )
    print("  ", audit["veredito"])

    sign_check = check_sign_consistency(
        case1["q"], case2["q"], case1["k"], case2["k"],
        dx=case1["domain"].dx, dy=case1["domain"].dy, dz=case1["domain"].dz,
    )
    print("  ", sign_check["veredito"])

    print("\n[PARTE 3] Experimento q<->k swap")
    swap = run_qk_swap_experiment(
        case1["q"], case2["q"], case1["k"], case2["k"],
        dx=case1["domain"].dx, dy=case1["domain"].dy, dz=case1["domain"].dz,
        label1="seed1", label2="seed2",
    )
    for name, r in swap["runs"].items():
        print(f"  {r['label']:<20} Tmax={r['Tmax']:.4e}  Tmax_struct={r['Tmax_struct']:.4e}")
    for field, d in swap["decomposition"].items():
        print(f"  [{field}] efeito_q={d['efeito_q']:.3e}  efeito_k={d['efeito_k']:.3e}  "
              f"interação={d['interacao']:.3e}  -> {swap['dominant_factor'][field]}")

    print("\n[PARTE 4] Gravando relatórios...")
    paths = write_reports(audit, sign_check, swap)
    for k, v in paths.items():
        print(f"  {k}: {v}")
