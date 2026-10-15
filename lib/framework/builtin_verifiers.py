"""builtin_verifiers.py — verificadores AOP padrão (Zero Trust: recalculam a partir dos arrays)."""
import hashlib

import numpy as np

from lib.framework.registry import verifier

FULL = ("epsilon", "Etotal", "Escat", "Einc", "q_abs_raw", "q_abs_thermal", "k_field", "T", "domain_material_mask")


def _ok(n, d): return [("OK", n, d)]
def _bad(n, d): return [("FALHA", n, d)]


@verifier("assert_npz_finite")
def v_finite(rt, val, ctx):
    bad = [k for k, a in ctx["arrays"].items() if a.dtype.kind in "fc" and not np.all(np.isfinite(a))]
    if not ctx["arrays"]:
        return []
    return _bad("aop:npz_finite", f"NaN/inf em {bad}") if bad else _ok("aop:npz_finite", f"{len(ctx['arrays'])} arrays finitos")


@verifier("assert_shapes_consistent")
def v_shapes(rt, val, ctx):
    a = ctx["arrays"]
    if not a:
        return []
    shp = {a[k].shape for k in FULL if k in a}
    if len(shp) > 1:
        return _bad("aop:shapes", f"shapes divergentes: {shp}")
    g = ctx.get("grid", {})
    if "geom_struct" in a and shp and g:
        full = next(iter(shp))
        want = (full[0], full[1], g["z_struct_end"] - g["z_struct_start"])
        if a["geom_struct"].shape != want:
            return _bad("aop:shapes", f"geom_struct {a['geom_struct'].shape} != {want}")
    return _ok("aop:shapes", f"consistentes {sorted(shp)}")


@verifier("assert_geometry_identity")
def v_geom(rt, val, ctx):
    a, m = ctx["arrays"], ctx.get("meta", {})
    if "geom_struct" not in a or not m.get("geometry_hash"):
        return []
    h = hashlib.sha256(np.ascontiguousarray(a["geom_struct"].astype(bool), dtype=np.bool_).tobytes(order="C")).hexdigest()
    return _ok("aop:identidade_geométrica", h[:12]) if h == m["geometry_hash"] else _bad("aop:identidade_geométrica", f"hash recalculado {h[:12]} != gravado {m['geometry_hash'][:12]}")


@verifier("assert_q_outside_zero")
def v_qout(rt, val, ctx):
    a = ctx["arrays"]
    if "q_abs_thermal" not in a:
        return []
    tol = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else 0.0
    mx = float(np.max(np.abs(a["q_abs_thermal"][~a["domain_material_mask"]]))) if (~a["domain_material_mask"]).any() else 0.0
    return _ok("aop:q_fora_zero", f"max|q| fora = {mx:.1e}") if mx <= tol else _bad("aop:q_fora_zero", f"q ≠ 0 fora da estrutura: {mx:.3e}")


@verifier("assert_power_balance")
def v_power(rt, val, ctx):
    a, sc, g = ctx["arrays"], ctx["scalars"], ctx.get("grid", {})
    if "q_abs_struct" not in a or "P_abs_thermal_W" not in sc or "dV" not in g:
        return []
    P = float(a["q_abs_struct"].sum() * g["dV"])
    ref = float(sc["P_abs_thermal_W"])
    rel = abs(P - ref) / max(abs(ref), 1e-300)
    return _ok("aop:balanço_potência", f"rel={rel:.1e}") if rel <= float(val) else _bad("aop:balanço_potência", f"P recalculada {P:.6e} vs declarada {ref:.6e} (rel {rel:.2e} > {val})")


@verifier("assert_limit")
def v_limit(rt, val, ctx):
    out = []
    for name, (lo, hi) in dict(val).items():
        x = ctx["scalars"].get(name)
        if x is None:
            out.append(("AVISO", f"aop:limite:{name}", "escalar ausente neste escopo"))
        elif not (lo <= x <= hi):
            out.append(("FALHA", f"aop:limite:{name}", f"{x:.6e} fora de [{lo}, {hi}]"))
        else:
            out.append(("OK", f"aop:limite:{name}", f"{x:.6e} em [{lo}, {hi}]"))
    return out


@verifier("assert_temperature_limit_k")
def v_temp(rt, val, ctx):
    a = ctx["arrays"]
    if "T" not in a:
        return []
    lo, hi = val
    t = a["T"][a["domain_material_mask"]]
    return _ok("aop:temperatura", f"[{t.min():.3e}, {t.max():.3e}] K") if lo <= t.min() and t.max() <= hi else _bad("aop:temperatura", f"T∈[{t.min():.3e},{t.max():.3e}] K fora de [{lo},{hi}]")


@verifier("assert_energy_conservation")
def v_energy(rt, val, ctx):
    x = ctx["scalars"].get("A_difference_power")
    if x is None:
        return []
    return _ok("aop:conservação", f"|A_flux-A_vol|={x:.2e}") if x <= float(val) else _bad("aop:conservação", f"|A_flux-A_vol|={x:.2e} > {val}")
