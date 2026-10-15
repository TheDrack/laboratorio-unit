"""builtin_tests.py — testes padrão sobre um Dataset. Cada teste: f(ds, params) -> {"tabela": [...], "escalares": {...}}.
Reportam números; NÃO interpretam (veredito é do pesquisador)."""
from itertools import combinations

import numpy as np

from lib.framework.registry import test


def _rank(x):
    return np.argsort(np.argsort(x)).astype(float)


def _corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return float("nan"), float("nan"), len(x)
    return float(np.corrcoef(x, y)[0, 1]), float(np.corrcoef(_rank(x), _rank(y))[0, 1]), len(x)


@test("resumo_casos", description="uma linha por caso: A_volume, Tmax, P_abs, R/T de potência")
def t_resumo(ds, p):
    rows = [{"caso": c.key, "f_THz": c.frequency_thz, "A_volume": c.scalars.get("A_volume"), "Tmax_K": c.scalars.get("Tmax_K"),
             "P_abs_W": c.scalars.get("P_abs_thermal_W"), "R": c.scalars.get("RT_power_R_power"), "T": c.scalars.get("RT_power_T_power")} for c in ds.cases]
    return {"tabela": rows, "escalares": {"n_casos": len(rows)}}


@test("fechamento_energia", description="|A_flux − A_volume| (potência e especular) por caso: máx e média")
def t_fech(ds, p):
    rows, dp, ds_ = [], [], []
    for c in ds.cases:
        a, b = c.scalars.get("A_difference_power"), c.scalars.get("A_difference_specular")
        rows.append({"caso": c.key, "A_diff_power": a, "A_diff_specular": b})
        if a is not None: dp.append(a)
        if b is not None: ds_.append(b)
    return {"tabela": rows, "escalares": {"A_diff_power_max": max(dp, default=float("nan")), "A_diff_power_mean": float(np.mean(dp)) if dp else float("nan"),
                                          "A_diff_specular_max": max(ds_, default=float("nan")), "n_casos": len(rows)}}


@test("suporte_q", description="q_abs fora da estrutura e potência removida pela máscara, por caso")
def t_suporte(ds, p):
    rows = [{"caso": c.key, "q_fora_max": c.scalars.get("q_abs_outside_max_W_m3"),
             "P_removida_W": (c.scalars.get("P_abs_raw_W", 0) - c.scalars.get("P_abs_thermal_W", 0))} for c in ds.cases]
    return {"tabela": rows, "escalares": {"q_fora_max_global": max((r["q_fora_max"] or 0) for r in rows) if rows else float("nan")}}


@test("pares_quase_isabsorptivos", description="pares (mesma f) com ΔA relativo < a_tol e razão de Tmax ≥ t_ratio. params: a_tol=0.01 t_ratio=2.0")
def t_pares(ds, p):
    a_tol, t_ratio = float(p.get("a_tol", 0.01)), float(p.get("t_ratio", 2.0))
    rows = []
    for f in ds.frequencies():
        cs = ds.select(frequency_thz=f).cases
        for a, b in combinations(cs, 2):
            A1, A2, T1, T2 = a.scalars.get("A_volume"), b.scalars.get("A_volume"), a.scalars.get("Tmax_K"), b.scalars.get("Tmax_K")
            if None in (A1, A2, T1, T2) or min(abs(A1), abs(A2)) == 0 or min(T1, T2) <= 0:
                continue
            dA = abs(A1 - A2) / min(abs(A1), abs(A2))
            ratio = max(T1, T2) / min(T1, T2)
            if dA < a_tol and ratio >= t_ratio:
                hot, cold = (a, b) if T1 >= T2 else (b, a)
                rows.append({"f_THz": f, "quente": hot.key, "frio": cold.key, "dA_rel": dA, "Tmax_ratio": ratio,
                             "q_max_over_mean_quente": hot.scalars.get("q_max_over_mean"), "q_max_over_mean_frio": cold.scalars.get("q_max_over_mean")})
    rows.sort(key=lambda r: -r["Tmax_ratio"])
    return {"tabela": rows[:50], "escalares": {"n_pares": len(rows), "a_tol": a_tol, "t_ratio": t_ratio,
                                               "maior_razao_Tmax": rows[0]["Tmax_ratio"] if rows else float("nan")}}


@test("correlacao_A_T", description="Pearson/Spearman de A_volume e métricas de q contra Tmax (global e por frequência)")
def t_corr(ds, p):
    rows = []
    for scope, f in [("todas", None)] + [(f"{x:g} THz", x) for x in ds.frequencies()]:
        cs = ds.cases if f is None else ds.select(frequency_thz=f).cases
        for pred in ("A_volume", "q_max_over_mean", "q_max_over_p95"):
            r, rho, n = _corr([c.scalars.get(pred, np.nan) or np.nan for c in cs], [c.scalars.get("Tmax_K", np.nan) or np.nan for c in cs])
            rows.append({"escopo": scope, "preditor": pred, "n": n, "pearson": r, "spearman": rho})
    return {"tabela": rows, "escalares": {"n_casos": len(ds)}}
