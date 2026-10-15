"""builtin_experiment.py — vocabulário padrão da linguagem UNIT-L: parâmetros, medidas, comparadores, analisadores."""
import math

import numpy as np

from lib.framework.registry import param, measure, comparator, analyzer, MEASURES

# ------------------------------------------------------------------ parâmetros (FIX / VARY)
param("frequency_thz", "float", "physical", required=True, unit="THz", description="frequência da onda incidente")
param("ppw", "float", "numerical", unit="1", description="pontos por comprimento de onda no meio mais denso (re-rasteriza a MESMA geometria física)")
param("mesh_dx", "float", "numerical", unit="m", description="passo da malha canônica (m)")
param("n_bg", "complex", "physical", description="índice do fundo")
param("n_inclusion", "complex", "physical", description="índice da inclusão (Im>0 = absorção)")
param("k_bg", "float", "physical", unit="W/(m·K)", description="condutividade térmica do fundo")
param("k_inclusion", "float", "physical", unit="W/(m·K)", description="condutividade térmica da inclusão")
param("pml_nm", "float", "physical", unit="nm", description="espessura FÍSICA da PML (deve ser múltiplo de dx em todos os níveis)")
param("buffer_nm", "float", "physical", unit="nm", description="espessura FÍSICA do buffer entre PML e estrutura")

SAFE_FUNCS = {"abs": abs, "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10, "exp": math.exp, "min": min, "max": max}


# ------------------------------------------------------------------ medidas
def _scalar_measure(name, key, unit="1", fields=("em_solve",), description=""):
    @measure(name, fields=fields, unit=unit, description=description or f"escalar '{key}' do caso")
    def _m(ctx, _k=key):
        v = ctx["scalars"].get(_k)
        if v is None:
            raise KeyError(f"escalar '{_k}' ausente no caso (campos que o produzem rodaram?)")
        return float(v)
    return _m


_scalar_measure("R_power", "RT_power_R_power", description="reflectância por fluxo de Poynting (todas as ordens)")
_scalar_measure("T_power", "RT_power_T_power", description="transmitância por fluxo de Poynting")
_scalar_measure("A_flux_power", "RT_power_A_flux_power", description="absorção por balanço de fluxo (1−R−T)")
_scalar_measure("A_volume", "A_volume", description="absorção por integral de q no volume (medida INDEPENDENTE de A_flux)")
_scalar_measure("A_difference_power", "A_difference_power", description="|A_flux − A_volume|")
_scalar_measure("R_specular", "RT_specular_R_specular", description="reflectância da ordem especular")
_scalar_measure("T_specular", "RT_specular_T_specular", description="transmitância da ordem especular")
_scalar_measure("chi95", "chi95", fields=("q_metrics",), description="χ95 = P95(q)/média(q) dentro do material")
_scalar_measure("chi99", "chi99", fields=("q_metrics",), description="χ99 = P99(q)/média(q) dentro do material")
_scalar_measure("q_max_over_mean", "q_max_over_mean", fields=("q_metrics",), description="q_max/q_médio no material")
_scalar_measure("P_abs_W", "P_abs_thermal_W", unit="W", fields=("q_metrics",), description="potência absorvida no material")
_scalar_measure("Tmax_K", "Tmax_K", unit="K", fields=("thermal",), description="temperatura máxima no material (θ=0 nas faces)")
_scalar_measure("Tmean_K", "Tmean_K", unit="K", fields=("thermal",), description="temperatura média no material")


@measure("f_discreta", fields=("em_solve",), unit="1", description="fração de volume do material NA MALHA (muda com a resolução; é derivada, não FIX)")
def _m_f(ctx):
    return float(ctx["effective"]["f_discreta"])


@measure("ppw_efetivo", fields=("em_solve",), unit="1", description="PPW efetivamente obtido após arredondar o número de células")
def _m_ppw(ctx):
    v = ctx["effective"].get("ppw_eff")
    return float("nan") if v is None else float(v)


@measure("dx_nm", fields=("em_solve",), unit="nm", description="passo efetivo da malha")
def _m_dx(ctx):
    return float(ctx["effective"]["dx_nm"])


# ------------------------------------------------------------------ utilitários de grupo
def _groups(rows, along, group_by, axes):
    keep = list(group_by) if group_by else [a for a in axes if a != along]
    extra = [a for a in axes if a != along and a not in keep]
    out = {}
    for r in rows:
        out.setdefault(tuple(r[a] for a in keep), []).append(r)
    for k, rs in out.items():
        for a in extra:
            if len({r[a] for r in rs}) > 1:
                raise ValueError(f"o eixo '{a}' varia dentro de um grupo; inclua-o em group_by (ou fixe-o)")
    return keep, out


def _series(rs, along, q):
    pts = sorted(((r[along], r[q]) for r in rs if r.get(q) is not None and np.isfinite(r.get(q, np.nan))), key=lambda t: t[0])
    return [p[0] for p in pts], [p[1] for p in pts]


# ------------------------------------------------------------------ COMPARE
@comparator("successive_diff", params={"of": ("measures", True, "grandezas a comparar"), "along": ("axis", True, "eixo numérico ordenado"),
                                       "group_by": ("axes", False, "eixos que definem os grupos (padrão: todos os outros)")},
            description="diferenças absolutas e relativas entre níveis consecutivos do eixo 'along', por grupo")
def c_successive(rows, p, info):
    keep, groups = _groups(rows, p["along"], p.get("group_by"), info["axes"])
    out, sc = [], {}
    for gk, rs in groups.items():
        for q in p["of"]:
            xs, ys = _series(rs, p["along"], q)
            for i in range(1, len(xs)):
                d = abs(ys[i] - ys[i - 1])
                out.append({**dict(zip(keep, gk)), "grandeza": q, "de": xs[i - 1], "para": xs[i], "Q_de": ys[i - 1], "Q_para": ys[i], "diff_abs": d,
                            "diff_rel": d / abs(ys[i]) if ys[i] else float("nan")})
    for q in p["of"]:
        ds = [r["diff_abs"] for r in out if r["grandeza"] == q]
        sc[f"max_diff_abs_{q}"] = max(ds) if ds else float("nan")
    return {"rows": out, "scalars": sc}


# ------------------------------------------------------------------ ANALYZE
@analyzer("convergence", params={"of": ("measures", True, "grandezas"), "along": ("axis", True, "eixo de resolução (ex.: ppw)"),
                                 "group_by": ("axes", False, "grupos (padrão: todos os outros eixos)"),
                                 "safety_factor": ("float", True, "fator de segurança para E_crit — CONVENÇÃO declarada, não derivada"),
                                 "working_ppw": ("float", False, "resolução de trabalho, para extrapolar o erro nela")},
          description="piso numérico por grandeza e grupo (diferenças entre níveis, ordem observada, Richardson) e E_crit operacional")
def a_convergence(rows, p, info):
    along, sf = p["along"], float(p["safety_factor"])
    wp = p.get("working_ppw")
    keep, groups = _groups(rows, along, p.get("group_by"), info["axes"])
    out, per_q = [], {q: [] for q in p["of"]}
    for gk, rs in groups.items():
        for q in p["of"]:
            xs, ys = _series(rs, along, q)
            row = {**dict(zip(keep, gk)), "grandeza": q, "niveis": xs, "valores": ys, "status": "ok"}
            if len(xs) < 3:
                row["status"] = f"insuficiente ({len(xs)} níveis válidos; precisa de ≥3)"
                out.append(row)
                continue
            d_first, d_last = abs(ys[-2] - ys[-3]), abs(ys[-1] - ys[-2])
            steps = np.diff(ys)
            monotone = bool(np.all(steps > 0) or np.all(steps < 0))
            contraction = d_last / d_first if d_first > 0 else float("nan")
            r1, r2 = xs[-2] / xs[-3], xs[-1] / xs[-2]
            const_ratio = abs(r1 - r2) < 1e-6 * r1
            order = float("nan"); rich = float("nan"); err_w = float("nan")
            if const_ratio and monotone and 0 < contraction < 1:
                order = math.log(d_first / d_last) / math.log(r1)
                rich = d_last / (r1 ** order - 1)                      # erro estimado do nível mais fino
                if wp:
                    err_w = rich * (xs[-1] / float(wp)) ** order       # erro estimado na resolução de trabalho
            floor = d_last
            e_basis = max(floor, err_w) if np.isfinite(err_w) else floor
            ref = abs(ys[-1])
            row.update(d_first=d_first, d_last=d_last, contraction=contraction, monotone=monotone, ordem_observada=order,
                       erro_richardson_fino=rich, erro_na_res_trabalho=err_w, piso_abs=floor, piso_rel=floor / ref if ref else float("nan"),
                       E_crit_abs=sf * e_basis, E_crit_rel=sf * e_basis / ref if ref else float("nan"), convergindo=bool(np.isfinite(contraction) and contraction < 1))
            if not const_ratio:
                row["aviso"] = "razão entre níveis não constante: sem ordem/Richardson; piso = última diferença"
            out.append(row)
            per_q[q].append(row)
    sc = {"safety_factor": sf}
    rel = {}
    for q, rs in per_q.items():
        if not rs:
            sc[f"piso_abs_{q}"] = sc[f"E_crit_abs_{q}"] = sc[f"E_crit_rel_{q}"] = float("nan")
            continue
        sc[f"piso_abs_{q}"] = max(r["piso_abs"] for r in rs)
        sc[f"piso_rel_{q}"] = max(r["piso_rel"] for r in rs)
        sc[f"E_crit_abs_{q}"] = max(r["E_crit_abs"] for r in rs)
        sc[f"E_crit_rel_{q}"] = max(r["E_crit_rel"] for r in rs)
        sc[f"todos_convergindo_{q}"] = all(r["convergindo"] for r in rs)
        rel[q] = sc[f"E_crit_rel_{q}"]
    sc["grandeza_primaria_sugerida"] = min(rel, key=rel.get) if rel else "indeterminada"
    sc["n_grupos"] = len(groups)
    return {"rows": out, "scalars": sc}
