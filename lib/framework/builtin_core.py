"""builtin_core.py — provedor de geometria, solver EM e campos derivados padrão."""
import hashlib

import numpy as np

from lib.framework.registry import geometry_provider, solver, field
from lib.geometry.unit001_constantes import DX
from lib.geometry.unit001_constantes import (C_LIGHT, EPS0)



def _put(scalars, name, value):
    """escalar -> JSON-safe (complex vira _re/_im)."""
    if isinstance(value, (complex, np.complexfloating)):
        scalars[name + "_re"], scalars[name + "_im"] = float(value.real), float(value.imag)
    elif isinstance(value, (bool, np.bool_)):
        scalars[name] = bool(value)
    elif isinstance(value, (int, np.integer)):
        scalars[name] = int(value)
    elif isinstance(value, (float, np.floating)):
        scalars[name] = float(value)


def rasterize_boxes_nm(boxes_nm, domain_nm, n):
    """Rasteriza caixas FÍSICAS (nm, inteiras) numa malha n=(nx,ny,nz) por amostragem do centro da célula.
    Aritmética inteira exata (sem empates de ponto flutuante); intervalo [a, b). O mesmo objeto contínuo
    vira malhas diferentes conforme n — é isso que permite varrer a resolução sem mudar a física."""
    m = np.zeros(n, dtype=bool)
    idx = [np.arange(k) for k in n]
    for box in boxes_nm:
        ok = []
        for ax in range(3):
            a, b = box[2 * ax], box[2 * ax + 1]
            c2 = (2 * idx[ax] + 1) * int(domain_nm[ax])
            ok.append((a * 2 * n[ax] <= c2) & (c2 < b * 2 * n[ax]))
        m |= ok[0][:, None, None] & ok[1][None, :, None] & ok[2][None, None, :]
    return m


def mask_hash(mask):
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.bool_).tobytes(order="C")).hexdigest()


# ------------------------------------------------------------------ geometria
@geometry_provider("unit001_pillars", description="22 geometrias canônicas (ORDERED, CLUSTERED, RANDOM_1000..1019) — lib.geometry.unit001_dataset_66_cases")
def unit001_pillars(state):
    try:
        from lib.geometry import unit001_dataset_66_cases as G
    except ImportError as e:
        raise RuntimeError("gerador de geometria ausente: lib/geometry/unit001_dataset_66_cases.py não está instalado no run. "
                           "Rode a Célula 2b (ela instala o gerador de referência se faltar) e tente de novo.") from e
    d0 = int(round(float(state.get("mesh_dx", DX)) * 1e9))      # nm por voxel da grade canônica
    px, py, pz = G.PILLAR_NX * d0, G.PILLAR_NY * d0, G.PILLAR_NZ * d0
    dom = [G.NX * d0, G.NY * d0, G.NZ * d0]
    recs = [dict(geometry=g["geometry"], seed=g["seed"], mask=np.asarray(g["mask"], dtype=bool), geometry_hash=g["geometry_hash"],
                 positions_hash=g.get("positions_hash"), meta={"positions": [list(p) for p in g["positions"]]},
                 boxes_nm=[(x * d0, x * d0 + px, y * d0, y * d0 + py, 0, pz) for x, y in g["positions"]], domain_nm=dom)
            for g in G.generate_all_geometries()]
    return {"records": recs, "frequencies_thz": [float(f) for f in G.FREQUENCIES_THZ]}


# ------------------------------------------------------------------ solver EM
def _grid_for(state, geom, frequency_hz):
    """Discretização efetiva. Sem 'ppw' na state: grade canônica (comportamento original).
    Com 'ppw': a MESMA geometria física (boxes_nm) é re-rasterizada; PML/buffer mantêm espessura FÍSICA (pml_nm/buffer_nm)."""
    n_bg, n_in = complex(state["n_bg"]), complex(state["n_inclusion"])
    if state.get("ppw") is None:
        m = geom["mask"]
        dx = float(state["mesh_dx"])
        return dict(mask=m, dxs=(dx, dx, dx), n=m.shape, npml=int(state["npml_cells"]), buf=int(state["buffer_cells"]), ppw_eff=None)
    boxes, dom = geom.get("boxes_nm"), geom.get("domain_nm")
    if boxes is None or dom is None:
        raise RuntimeError("o provedor de geometria não fornece boxes_nm/domain_nm: refinamento por 'ppw' indisponível")
    lam = C_LIGHT / frequency_hz
    nmax = max(n_bg.real, n_in.real)
    dx_t = lam / (nmax * float(state["ppw"]))
    n = tuple(max(2, int(round(L * 1e-9 / dx_t))) for L in dom)
    dxs = tuple(L * 1e-9 / k for L, k in zip(dom, n))
    d0 = float(state["mesh_dx"]) * 1e9
    out = {}
    for key, cells_key in (("pml_nm", "npml_cells"), ("buffer_nm", "buffer_cells")):
        nm = float(state.get(key) or int(state[cells_key]) * d0)
        c = nm * 1e-9 / dxs[2]
        if abs(c - round(c)) > 1e-6:
            raise RuntimeError(f"{key}={nm:g} nm não é múltiplo de dx={dxs[2]*1e9:.4f} nm (ppw={state['ppw']}): daria {c:.3f} células. "
                               f"Fixe {key} num valor comum a todos os níveis (ex.: múltiplo de 100/3 nm para ppw 15/30/60).")
        out[key] = int(round(c))
    return dict(mask=rasterize_boxes_nm(boxes, dom, n), dxs=dxs, n=n, npml=out["pml_nm"], buf=out["buffer_nm"], ppw_eff=lam / (nmax * dxs[0]))


def _choose_backend(requested, unknowns, budget_gb):
    """'direct' custa ~1,7 GB em 48k incógnitas e cresce ~n^1.3-1.9; 'iterative' cabe no orçamento e é mais lento."""
    if requested in ("direct", "iterative"):
        return requested, f"pedido no SOLVE (backend={requested})"
    # auto: tenta o direto SEMPRE, sob o sentinela; se a RAM cair abaixo da reserva, o motor repete o ponto
    # com o iterativo (mesma física, validado ~1e-11). A estimativa vai só como informação.
    mem_direct, _t = _est_direct(unknowns)
    return "direct", f"direto primeiro (estimativa ~{mem_direct:.1f} GB; fallback iterativo se o sentinela abortar)"


def _est_direct(unknowns):
    r = unknowns / 48384.0
    return 0.1 + 1.63 * r ** 1.3, 22.9 * r ** 1.9


def _solve_fdfd_iterative(domain, ctx):
    """Mesmo sistema de solve_fdfd_3d, resolvido por GMRES. Reaproveita a montagem do solver direto
    capturando A e b (sem duplicar física); reporta progresso via lib.framework.progress."""
    import lib.solvers.fdfd3d as F
    from lib.framework import progress as PG
    cap = {}
    orig = F.spla.spsolve

    def _capture(A, b, *a, **k):
        cap["A"], cap["b"] = A, b
        return np.zeros(A.shape[0], dtype=complex)
    F.spla.spsolve = _capture
    try:
        F.solve_fdfd_3d(domain)
    finally:
        F.spla.spsolve = orig
    A, b = cap["A"], cap["b"]
    PG.emit(ctx, "solver", f"GMRES+ILU em {A.shape[0]} incógnitas (nnz={A.nnz})")
    x, info, res = _solve_iterative(A, b)
    if info != 0 or res > 1e-6:
        raise RuntimeError(f"GMRES não convergiu (info={info}, resíduo={res:.2e}); use backend=direct ou aumente o orçamento")
    PG.emit(ctx, "solver", f"convergiu (resíduo {res:.1e})")
    return _assemble_result(domain, x, b, A)


def _assemble_result(domain, x, b, A):
    """Monta o dicionário que solve_fdfd_3d devolveria, a partir da solução iterativa."""
    import lib.solvers.fdfd3d as F
    nx, ny, nz = domain.eps.shape
    Escat_flat = x
    Escat = Escat_flat.reshape((nx, ny, nz), order="C")
    Einc, z_axis = F.build_incident_field_3d(domain)
    Etotal = Einc + Escat
    residual = A @ Escat_flat - b
    return {"Etotal": Etotal, "Escat": Escat, "Einc": Einc, "domain": domain, "z_axis": z_axis,
            "relative_residual": float(np.linalg.norm(residual) / max(np.linalg.norm(b), 1e-300)),
            "incident_operator_residual": F.compute_incident_operator_residual(domain, Einc, None),
            "k_inc_discrete": domain.k_inc_discrete}


def _solve_iterative(A, b, rtol=1e-8, restart=40, maxiter=200):
    """GMRES + ILU de baixa memória. Validado: no PPW 30 converge com 0,16 GB (direto: 1,7 GB);
    no PPW 15 o campo bate com o direto a ~1e-11 (relativo). Devolve (x, info, resíduo relativo)."""
    import scipy.sparse.linalg as spla
    A = A.tocsc()
    M = spla.LinearOperator(A.shape, spla.spilu(A, drop_tol=1e-4, fill_factor=10).solve)
    x, info = spla.gmres(A, b, M=M, rtol=rtol, restart=restart, maxiter=maxiter)
    res = float(np.linalg.norm(A @ x - b) / max(np.linalg.norm(b), 1e-300))
    return x, info, res


@solver("fdfd3d_te_y", description="FDFD 3D escalar TE_y. Opções: backend=direct|iterative|auto (auto: iterativo se o direto não couber). Aceita 'ppw' (re-rasteriza a geometria física).")
def solve_fdfd3d(ctx):
    from lib.solvers.fdfd3d import build_domain_3d, solve_fdfd_3d, analyze_solution_3d
    from lib.framework import progress as PG
    st, geom = ctx["state"], ctx["geom"]
    n_bg, n_in = complex(st["n_bg"]), complex(st["n_inclusion"])
    G = _grid_for(st, geom, ctx["frequency_hz"])
    mask, (dxx, dyy, dzz) = G["mask"], G["dxs"]
    nx, ny, nz = mask.shape
    eps = np.where(mask, n_in ** 2, n_bg ** 2).astype(complex)
    gd = dict(nx=nx, ny=ny, nz=nz, dx=dxx, dy=dyy, dz=dzz, epsilon=eps, mu_r=np.ones_like(eps))
    wl = C_LIGHT / ctx["frequency_hz"]
    domain = build_domain_3d(gd, wl, n_bg=n_bg, npml_cells=G["npml"], buffer_cells=G["buf"])
    backend, why = _choose_backend(ctx.get("backend", "auto"), int(domain.eps.size), ctx.get("budget_gb"))
    PG.emit(ctx, "solver", f"backend={backend} ({why}) · incógnitas={int(domain.eps.size)}")
    if backend == "iterative":
        result = _solve_fdfd_iterative(domain, ctx)
    else:
        result = solve_fdfd_3d(domain)
    an = analyze_solution_3d(result)
    sc = {}
    _put(sc, "fdfd_relative_residual", result["relative_residual"])
    _put(sc, "fdfd_incident_operator_residual", result["incident_operator_residual"])
    for k, v in an["absorption"].items():
        _put(sc, k, v)
    for pref, d in (("RT_power", an["RT_power"]), ("RT_specular", an["RT_specular"])):
        for k, v in d.items():
            if np.isscalar(v):
                _put(sc, f"{pref}_{k}", v)
    eff = {"frequency_thz": ctx["frequency_hz"] / 1e12, "n_bg": n_bg, "n_inclusion": n_in, "k_bg": float(st["k_bg"]), "k_inclusion": float(st["k_inclusion"]),
           "pml_nm": G["npml"] * dzz * 1e9, "buffer_nm": G["buf"] * dzz * 1e9, "dx_nm": dxx * 1e9, "n_cells": list(G["n"]), "ppw_eff": G["ppw_eff"],
           "f_discreta": float(mask.mean()), "mask_hash": mask_hash(mask), "unknowns": int(domain.eps.size),
           "n_inclusion_efetivo": complex(np.sqrt(eps[mask][0])) if mask.any() else n_in}
    eff["physical"] = {"boxes_nm": [list(map(int, b)) for b in geom["boxes_nm"]] if geom.get("boxes_nm") else geom["geometry_hash"],
                       "domain_nm": list(geom["domain_nm"]) if geom.get("domain_nm") else None, "frequency_thz": round(eff["frequency_thz"], 9),
                       "n_bg": [n_bg.real, n_bg.imag], "n_inclusion": [n_in.real, n_in.imag], "k_bg": eff["k_bg"], "k_inclusion": eff["k_inclusion"],
                       "pml_nm": round(eff["pml_nm"], 6), "buffer_nm": round(eff["buffer_nm"], 6)}
    return {"arrays": {"epsilon": np.asarray(domain.eps), "Etotal": np.asarray(result["Etotal"]),
                       "Escat": np.asarray(result["Escat"]), "Einc": np.asarray(result["Einc"])},
            "grid": {"dx": float(domain.dx), "dy": float(domain.dy), "dz": float(domain.dz),
                     "z_struct_start": int(domain.z_struct_start), "z_struct_end": int(domain.z_struct_end),
                     "omega": 2.0 * np.pi * ctx["frequency_hz"]},
            "scalars": sc, "mask": mask, "effective": eff}


# ------------------------------------------------------------------ campos
@field("em_solve", requires=(), provides=("epsilon", "Etotal", "grid"), description="executa o solver EM escolhido (contrato validado)")
def f_em_solve(ctx):
    from lib.framework.registry import SOLVERS
    out = SOLVERS.get(ctx["solver"])(ctx)
    miss = [k for k in ("epsilon", "Etotal") if k not in out.get("arrays", {})]
    miss += [k for k in ("dx", "dy", "dz", "z_struct_start", "z_struct_end", "omega") if k not in out.get("grid", {})]
    if miss:
        raise RuntimeError(f"solver {ctx['solver']!r} viola o contrato; faltam: {miss}")
    ctx["arrays"].update(out["arrays"]); ctx["grid"].update(out["grid"]); ctx["scalars"].update(out.get("scalars", {}))
    ctx["mask"] = out.get("mask", ctx["geom"]["mask"])          # máscara EFETIVAMENTE discretizada
    ctx["effective"] = out.get("effective", {})


@field("domain_mask", requires=("grid",), provides=("domain_material_mask",), description="máscara do material no domínio completo")
def f_domain_mask(ctx):
    g, m = ctx["grid"], ctx.get("mask", ctx["geom"]["mask"])
    full = ctx["arrays"]["epsilon"].shape
    z0, z1 = g["z_struct_start"], g["z_struct_end"]
    if (full[0], full[1], z1 - z0) != m.shape:
        raise RuntimeError(f"máscara {m.shape} incompatível com domínio {full} z={z0}:{z1}")
    mask = np.zeros(full, dtype=bool)
    mask[:, :, z0:z1] = m
    ctx["arrays"]["domain_material_mask"] = mask


@field("q_abs", requires=("epsilon", "Etotal", "grid"), provides=("q_abs_raw",), description="q = 1/2 w eps0 Im(eps) |E|^2 (W/m^3)")
def f_q_abs(ctx):
    a = ctx["arrays"]
    ctx["arrays"]["q_abs_raw"] = np.real(0.5 * ctx["grid"]["omega"] * EPS0 * np.imag(a["epsilon"]) * np.abs(a["Etotal"]) ** 2)


@field("q_thermal", requires=("q_abs_raw", "domain_material_mask", "grid"), provides=("q_abs_thermal", "q_abs_struct"),
       description="q restrito à estrutura (zero fora) + bloco estrutural")
def f_q_thermal(ctx):
    a, g = ctx["arrays"], ctx["grid"]
    dV = g["dx"] * g["dy"] * g["dz"]
    q = a["q_abs_raw"] * a["domain_material_mask"]
    a["q_abs_thermal"] = q
    a["q_abs_struct"] = q[:, :, g["z_struct_start"]:g["z_struct_end"]]
    sc = ctx["scalars"]
    _put(sc, "dV", dV)
    _put(sc, "P_abs_raw_W", float(a["q_abs_raw"].sum() * dV))
    _put(sc, "P_abs_thermal_W", float(q.sum() * dV))
    _put(sc, "q_abs_outside_max_W_m3", float(np.max(np.abs(a["q_abs_raw"][~a["domain_material_mask"]]))))


@field("k_field", requires=("domain_material_mask", "grid"), provides=("k_field", "k_struct"), description="k(r) térmico a partir da máscara")
def f_k_field(ctx):
    a, g, st = ctx["arrays"], ctx["grid"], ctx["state"]
    k = np.where(a["domain_material_mask"], float(st["k_inclusion"]), float(st["k_bg"]))
    a["k_field"] = k
    a["k_struct"] = k[:, :, g["z_struct_start"]:g["z_struct_end"]]


@field("thermal", requires=("q_abs_thermal", "k_field", "grid"), provides=("T",), description="-div(k grad T) = q, T=0 nas 6 faces (lib.coupling.thermal_coupling)")
def f_thermal(ctx):
    from lib.coupling.thermal_coupling import solve_steady_state_temperature
    from lib.core.wave_state import WaveState
    a, g = ctx["arrays"], ctx["grid"]
    ws = WaveState(dx=g["dx"], dy=g["dy"], dz=g["dz"], omega=g["omega"], E={"y": a["Etotal"]}, H={}, q_abs=a["q_abs_thermal"])
    th = solve_steady_state_temperature(ws, k_thermal=a["k_field"])
    T = np.asarray(th["T"])
    a["T"] = T
    m = a["domain_material_mask"]
    sc = ctx["scalars"]
    _put(sc, "thermal_residual", th["thermal_residual"])
    _put(sc, "thermal_residual_relative", th["residual_relative"])
    _put(sc, "Tmax_K", float(T[m].max()))
    _put(sc, "Tmean_K", float(T[m].mean()))
    _put(sc, "T_material_p95_K", float(np.percentile(T[m], 95)))
    _put(sc, "T_material_p99_K", float(np.percentile(T[m], 99)))
    P = sc.get("P_abs_thermal_W", 0.0)
    _put(sc, "R_th_eff_K_W", float(T[m].max() / P) if P > 0 else float("nan"))


@field("q_metrics", requires=("q_abs_thermal", "domain_material_mask"), provides=("q_material_max_W_m3",), description="estatísticas de q dentro do material")
def f_q_metrics(ctx):
    a, sc = ctx["arrays"], ctx["scalars"]
    v = a["q_abs_thermal"][a["domain_material_mask"]]
    _put(sc, "q_material_max_W_m3", float(v.max()))
    _put(sc, "q_material_mean_W_m3", float(v.mean()))
    _put(sc, "q_material_p95_W_m3", float(np.percentile(v, 95)))
    _put(sc, "q_material_p99_W_m3", float(np.percentile(v, 99)))
    _put(sc, "q_max_over_mean", float(v.max() / v.mean()) if v.mean() > 0 else float("nan"))
    _put(sc, "q_max_over_p95", float(v.max() / np.percentile(v, 95)) if np.percentile(v, 95) > 0 else float("nan"))
    _put(sc, "chi95", float(np.percentile(v, 95) / v.mean()) if v.mean() > 0 else float("nan"))   # χ95 = P95(q)/média(q) no material
    _put(sc, "chi99", float(np.percentile(v, 99) / v.mean()) if v.mean() > 0 else float("nan"))
