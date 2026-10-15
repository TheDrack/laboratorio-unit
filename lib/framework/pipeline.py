"""
pipeline.py — geração AUTOMÁTICA e padronizada dos casos.

    Spec (AOP-DSL) -> provedor de geometria -> casos (geometria x frequência) -> grafo de campos -> NPZ padrão
                      -> verificação AOP por caso -> índice

Para estender: registre solver/campo/teste/verificador em lib/framework/plugins/. Nada aqui muda.
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lib.framework import registry as R
from lib.framework import aop_dsl
from lib.framework.dataset import Dataset, ctx_from_npz
from lib.framework.builtin_core import _put
from lib.geometry.unit001_constantes import DX, N_PILLAR, K_PILLAR, K_BACKGROUND, NPML_CELLS, BUFFER_CELLS
from lib.geometry.unit001_constantes import (N_FUNDO_ESTUDO, N_INCLUSAO_ESTUDO, K_FUNDO_ESTUDO, K_INCLUSAO_ESTUDO)

DEFAULT_STATE = dict(geometry_provider="unit001_pillars", geometries=None, seeds=None, frequencies_thz=None, mesh_dx=DX,
                     n_bg=N_FUNDO_ESTUDO, n_inclusion=N_INCLUSAO_ESTUDO, k_bg=K_FUNDO_ESTUDO, k_inclusion=K_INCLUSAO_ESTUDO, npml_cells=NPML_CELLS, buffer_cells=BUFFER_CELLS, max_cases=None)
DEFAULT_FIELDS = ["thermal", "q_metrics"]
DEFAULT_SOLVER = "fdfd3d_te_y"


@dataclass
class CaseSpec:
    case_id: int
    geometry: str
    seed: object
    frequency_thz: float

    @property
    def key(self):
        return f"{self.geometry}_seed_{'none' if self.seed is None else self.seed}_{self.frequency_thz:.0f}THz"


def resolve_state(rt):
    st = dict(DEFAULT_STATE); st.update(rt.state()); return st


def resolve_fields(chosen):
    """Resolve dependências: o usuário cita só os campos finais; os necessários entram sozinhos, em ordem topológica."""
    providers = {}
    for n in R.FIELDS.names():
        for tok in R.FIELDS.meta(n).get("provides", ()):
            providers[tok] = n
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for tok in R.FIELDS.meta(n).get("requires", ()):
            if tok not in providers:
                raise KeyError(f"campo {n!r} requer {tok!r} mas nenhum campo registrado o fornece")
            visit(providers[tok])
        order.append(n)
    for n in chosen:
        visit(R.FIELDS.get(n) and n)
    return order


def expand_cases(state, prov):
    recs = prov["records"]
    gsel = state.get("geometries")
    if gsel:
        up = {str(g).upper() for g in gsel}
        recs = [g for g in recs if g["geometry"].upper() in up]
    if state.get("seeds") is not None:
        seeds = set(state["seeds"])
        recs = [g for g in recs if g["seed"] is None or g["seed"] in seeds]
    freqs = [float(f) for f in (state.get("frequencies_thz") or prov["frequencies_thz"])]
    cases, i = [], 0
    for g in recs:
        for f in freqs:
            i += 1
            cases.append((CaseSpec(i, g["geometry"], g["seed"], f), g))
    if state.get("max_cases"):
        cases = cases[: int(state["max_cases"])]
    return cases, recs, freqs


def _lib_hash():
    h = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    for sub in ("solvers", "coupling", "core", "framework"):
        for p in sorted((root / sub).rglob("*.py")):
            h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()


def signature(state, solver_name, fields, geom, lib_hash):
    payload = {"state": {k: (str(v) if isinstance(v, complex) else v) for k, v in state.items() if k not in ("geometries", "seeds", "frequencies_thz", "max_cases")},
               "solver": solver_name, "fields": fields, "geometry_hash": geom["geometry_hash"], "lib": lib_hash, "fw": R.FRAMEWORK_VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def run_case(state, solver_name, fields, case, geom, options=None, budget_gb=None):
    options = dict(options or {})
    ctx = dict(state=state, case=case, geom=geom, solver=solver_name, arrays={}, scalars={}, grid={}, frequency_hz=case.frequency_thz * 1e12,
               backend=options.get("backend", "auto"), budget_gb=budget_gb)
    for fn in fields:
        R.FIELDS.get(fn)(ctx)
        for tok in R.FIELDS.meta(fn).get("provides", ()):
            if tok not in ctx["arrays"] and tok not in ctx and tok not in ctx["scalars"]:
                raise RuntimeError(f"campo {fn!r} declarou fornecer {tok!r} e não forneceu")
    return ctx


def save_case(ctx, cases_dir, sig):
    a, g, case, geom = ctx["arrays"], ctx["grid"], ctx["case"], ctx["geom"]
    nz = a["epsilon"].shape[2]
    data = dict(a)
    data.update(geom_struct=ctx.get("mask", geom["mask"]), z_axis=np.arange(nz) * g["dz"], dx=g["dx"], dy=g["dy"], dz=g["dz"], dV=g["dx"] * g["dy"] * g["dz"],
                z_struct_start=g["z_struct_start"], z_struct_end=g["z_struct_end"], frequency_THz=case.frequency_thz,
                seed=-1 if case.seed is None else case.seed, geometry=case.geometry, geometry_hash=geom["geometry_hash"],
                case_signature=sig, solver=ctx["solver"], framework_version=R.FRAMEWORK_VERSION,
                scalars_json=json.dumps({k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in ctx["scalars"].items()}))
    cases_dir = Path(cases_dir); cases_dir.mkdir(parents=True, exist_ok=True)
    path = cases_dir / f"{case.key}.npz"
    tmp = cases_dir / f".{case.key}.tmp.npz"
    np.savez_compressed(tmp, **data)
    os.replace(tmp, path)
    return path


def _existing_sig(path):
    try:
        with np.load(path, allow_pickle=False) as z:
            return str(z["case_signature"])
    except Exception:
        return None


def run_pipeline(spec, cases_dir, *, resume=True, fail_fast=None, log=print, report_dir=None):
    """Executa o pipeline para um Spec. Levanta AOPViolation em violação de especificação/parâmetros."""
    R.ensure_loaded()
    rt = aop_dsl.AOPRuntime(spec)
    rt.raise_on_fail(rt.preflight_spec())
    st = resolve_state(rt)
    cap = rt.capability()
    solver_name = cap.get("solver", DEFAULT_SOLVER)
    fields = resolve_fields(cap.get("fields", DEFAULT_FIELDS))
    if fail_fast is None:
        fail_fast = bool(rt.action().get("fail_fast", True))
    prov = R.GEOMETRIES.get(st["geometry_provider"])(st)
    cases, recs, freqs = expand_cases(st, prov)
    n_rand = len({g["seed"] for g in recs if g["seed"] is not None})
    rt.raise_on_fail(rt.check_cases(recs, freqs, n_random=n_rand))
    log(f"AOP: spec {spec.sha256[:12]} | solver={solver_name} | campos={fields} | {len(cases)} casos ({len(recs)} geometrias x {len(freqs)} frequências)")
    lib_hash = _lib_hash()
    done, index, failures, t0 = [], [], [], time.time()
    for n, (case, geom) in enumerate(cases, 1):
        sig = signature(st, solver_name, fields, geom, lib_hash)
        path = Path(cases_dir) / f"{case.key}.npz"
        try:
            if resume and path.exists() and _existing_sig(path) == sig:
                status, ctx_v = "reutilizado", ctx_from_npz(path)
            else:
                t1 = time.time()
                ctx = run_case(st, solver_name, fields, case, geom)
                path = save_case(ctx, cases_dir, sig)
                status, ctx_v = f"calculado em {time.time() - t1:.1f}s", ctx_from_npz(path)
            findings = rt.verify_case(ctx_v)
            bad = [f for f in findings if f[0] == "FALHA"]
            log(f"[{n}/{len(cases)}] {case.key}: {status} | AOP {'FALHA' if bad else 'OK'}")
            for lv, nm, d in bad:
                log(f"      ✗ {nm}: {d}")
            index.append({"caso": case.key, "status": status, "aop": "FALHA" if bad else "OK", "Tmax_K": ctx_v["scalars"].get("Tmax_K"), "A_volume": ctx_v["scalars"].get("A_volume")})
            done.append(str(path))
            if bad:
                failures.append({"caso": case.key, "achados": bad})
                if fail_fast:
                    break
        except Exception as e:
            log(f"[{n}/{len(cases)}] {case.key}: ERRO {type(e).__name__}: {e}")
            failures.append({"caso": case.key, "erro": f"{type(e).__name__}: {e}"})
            if fail_fast:
                break
    res = {"n_planejados": len(cases), "n_concluidos": len(done), "n_falhas": len(failures), "solver": solver_name, "campos": fields,
           "spec_sha256": spec.sha256, "duracao_s": round(time.time() - t0, 1), "cases_dir": str(cases_dir), "falhas": failures, "indice": index}
    Path(cases_dir).parent.mkdir(parents=True, exist_ok=True)
    (Path(cases_dir).parent / "cases_index.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    if report_dir:
        report_dir = Path(report_dir)
        (report_dir / "aop_cases.json").write_text(json.dumps({"npz": done, "spec_sha256": spec.sha256}), encoding="utf-8")
        (report_dir / "aop_report.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return res


def _emit(res):
    print(f"n_planejados: {res['n_planejados']}")
    print(f"n_concluidos: {res['n_concluidos']}")
    print(f"n_falhas: {res['n_falhas']}")
    print(f"duracao_s: {res['duracao_s']}")
    print("UNIT_RESULT_JSON: " + json.dumps({"tabela": res["indice"][:200], "escalares": {k: res[k] for k in ("n_planejados", "n_concluidos", "n_falhas", "duracao_s")}},
                                            ensure_ascii=False, default=str))


def _env_dirs():
    run_dir = Path(os.environ["UNIT_RUN_DIR"])
    cases = os.environ.get("UNIT001_CASES_DIR")
    if not cases:
        raise RuntimeError("UNIT001_CASES_DIR ausente (a Célula 1 exporta; executar() precisa repassar UNIT001_*)")
    return run_dir, Path(cases)


def run_pipeline_in_run(resume=True, fail_fast=None):
    """Entrada usada pelo laboratório: lê <run>/spec.aop, grava NPZ em UNIT001_CASES_DIR, relatório em <run>."""
    run_dir, cases_dir = _env_dirs()
    spec = aop_dsl.parse_file(run_dir / "spec.aop")
    try:
        res = run_pipeline(spec, cases_dir, resume=resume, fail_fast=fail_fast, report_dir=run_dir)
    except aop_dsl.AOPViolation as e:
        print(f"AOP BLOQUEOU: {e}")
        raise SystemExit(3)
    _emit(res)
    if res["n_falhas"]:
        raise SystemExit(4)


def run_tests(names, params=None, cases_dir=None):
    R.ensure_loaded()
    ds = Dataset.from_dir(cases_dir)
    if not len(ds):
        raise RuntimeError(f"nenhum NPZ em {cases_dir}; rode /pipeline primeiro")
    out = {}
    for n in names:
        out[n] = R.TESTS.get(n)(ds, dict(params or {}))
    return out


def run_tests_in_run(names, params=None):
    run_dir, cases_dir = _env_dirs()
    res = run_tests(names, params, cases_dir)
    tabela, esc = [], {}
    for n, r in res.items():
        print(f"--- teste: {n}")
        for k, v in r["escalares"].items():
            print(f"{n}.{k}: {v}")
            esc[f"{n}.{k}"] = v
        tabela += [dict(teste=n, **row) for row in r["tabela"][:100]]
    print("UNIT_RESULT_JSON: " + json.dumps({"tabela": tabela, "escalares": esc}, ensure_ascii=False, default=lambda o: None if o is None else str(o)))
