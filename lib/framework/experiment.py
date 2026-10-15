"""
experiment.py — UNIT-L 0.1: linguagem semântica de experimentos para IAs.

O Codificador DESCREVE o experimento; o laboratório fornece primitivas, contratos, validação e execução.
Não há laços, I/O nem funções definidas pelo usuário: só composição de primitivas registradas.

    EXPERIMENT Nome {
        GOAL    "pergunta científica"
        CASE    geometry = [ORDERED, RANDOM_1000]          # quais entidades
        FIX     frequency_thz = 300, n_inclusion = 2.0+0.05j  # invariantes: o motor VERIFICA que ficaram constantes
        VARY    ppw = [15, 30, 60]                          # eixos de varredura (produto cartesiano com CASE)
        SOLVE   fdfd3d_te_y                                 # solver registrado
        MEASURE R = R_power, chi95                          # medidas registradas (alias = nome)
        DERIVE  closure = 1 - R - T - A                     # aritmética sobre medidas
        LIMIT   closure_tol = pending                       # limites são do PESQUISADOR; 'pending' => só reporta o valor
        CHECK   fechamento : abs(closure) <= closure_tol
        COMPARE passos = successive_diff(of=[R], along=ppw)
        ANALYZE conv   = convergence(of=[R], along=ppw, safety_factor=3)
        OUTPUT  tables=[passos, conv], scalars=[conv]
    }

Regras estruturais: (1) números em CHECK só 0/1/2 — limite numérico exige LIMIT; (2) eixos 'numerical' (ex.: ppw) exigem
invariância FÍSICA entre níveis (verificada sobre a discretização efetiva); (3) custo de memória/tempo é estimado antes de rodar.
"""
import ast
import hashlib
import json
import math
import os
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lib.framework import registry as R
from lib.framework import aop_dsl
from lib.framework.aop_dsl import _strip_comment, _depth

from lib.framework.lang.parser import (  # sintaxe vem de lang/unl_spec.toml (fonte única)
    LANG_VERSION, VERBS, ALLOWED_CHECK_NUMBERS, INDEPENDENT, UNLError, Stmt, Experiment,
    normalize, parse, extract_from_markdown, _split_comment, _lit, _call_args,
)
from lib.framework.lang.parser import _f as _f_lang  # noqa: F401


# ------------------------------------------------------------------ expressões seguras
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)


def _check_expr(expr, names, line, is_check):
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise UNLError(line, f"expressão inválida: {e.msg}")
    for n in ast.walk(tree):
        if isinstance(n, ast.Expression) or isinstance(n, (ast.Load, ast.cmpop, ast.boolop, ast.unaryop, ast.operator)):
            continue
        if isinstance(n, ast.BinOp) and isinstance(n.op, _BINOPS):
            continue
        if isinstance(n, ast.UnaryOp):
            continue
        if isinstance(n, (ast.Compare, ast.BoolOp)):
            if not is_check:
                raise UNLError(line, "comparações só são permitidas em CHECK")
            continue
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
                raise UNLError(line, f"constante não numérica: {n.value!r}")
            if is_check and n.value not in ALLOWED_CHECK_NUMBERS:
                raise UNLError(line, f"constante numérica {n.value!r} em CHECK não é permitida: declare 'LIMIT nome = valor' (limites são decisão do pesquisador)")
            continue
        if isinstance(n, ast.Name):
            if n.id not in names and n.id not in R_SAFE():
                raise UNLError(line, f"nome desconhecido {n.id!r} (disponíveis: {sorted(names)})")
            continue
        if isinstance(n, ast.Call):
            if not (isinstance(n.func, ast.Name) and n.func.id in R_SAFE()) or n.keywords:
                raise UNLError(line, f"chamada não permitida; funções: {sorted(R_SAFE())}")
            continue
        raise UNLError(line, f"construção não permitida na expressão: {type(n).__name__}")
    if is_check and not isinstance(tree.body, (ast.Compare, ast.BoolOp)):
        raise UNLError(line, "CHECK precisa ser uma comparação (ex.: abs(x) <= limite)")
    return tree


def R_SAFE():
    from lib.framework.builtin_experiment import SAFE_FUNCS
    return SAFE_FUNCS


def _eval(node, ns):
    from lib.framework.builtin_experiment import SAFE_FUNCS
    return eval(compile(ast.Expression(node), "<unl>", "eval"), {"__builtins__": {}}, {**SAFE_FUNCS, **ns})


def _names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _eval_check(node, ns, pending):
    """-> ('PASS'|'FAIL'|'PENDENTE', detalhe). PENDENTE quando depende de LIMIT 'pending': só reporta o valor medido."""
    if isinstance(node, ast.BoolOp):
        sts = [_eval_check(v, ns, pending) for v in node.values]
        ss = [s[0] for s in sts]
        if isinstance(node.op, ast.And):
            st = "FAIL" if "FAIL" in ss else "PENDENTE" if "PENDENTE" in ss else "PASS"
        else:
            st = "PASS" if "PASS" in ss else "PENDENTE" if "PENDENTE" in ss else "FAIL"
        return st, "; ".join(s[1] for s in sts)
    lefts = [node.left] + list(node.comparators)
    uses_pending = any(_names_in(x) & pending for x in lefts)
    vals = [None if (_names_in(x) & pending) else _eval(x, ns) for x in lefts]
    txt = ast.unparse(node)
    if uses_pending:
        known = [f"{ast.unparse(x)}={v:.6g}" for x, v in zip(lefts, vals) if v is not None]
        return "PENDENTE", f"{txt}  → {', '.join(known)} (limite pendente)"
    ok = _eval(node, ns)
    return ("PASS" if ok else "FAIL"), f"{txt}  → " + ", ".join(f"{ast.unparse(x)}={v:.6g}" for x, v in zip(lefts, vals))


# ------------------------------------------------------------------ recursos
def available_memory_gb():
    """Memória disponível AGORA (sentinela: MemAvailable + limite de container). Não é mais um valor fixo."""
    from lib.framework.sentinela import memoria_disponivel_gb
    v = memoria_disponivel_gb()
    return v if v == v else 8.0


def _legacy_available_memory_gb():
    best = []
    try:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:"):
                best.append(int(ln.split()[1]) / 1e6)
    except Exception:
        pass
    try:
        import resource
        soft = resource.getrlimit(resource.RLIMIT_AS)[0]
        if soft not in (-1, resource.RLIM_INFINITY):
            best.append(soft / 1e9)
    except Exception:
        pass
    return min(best) if best else 8.0


def estimate_fdfd_cost(unknowns):
    """Estimativa calibrada em 2 pontos (6 048 → 0,2 GB/0,4 s; 48 384 → 1,7 GB/23 s; solver direto 1 núcleo). É ORDEM DE GRANDEZA."""
    r = unknowns / 48384.0
    return 0.1 + 1.63 * r ** 1.3, 22.9 * r ** 1.9



# ------------------------------------------------------------------ sugestões de nome (distância de edição)
def _lev(a, b):
    a, b = a.lower(), b.lower()
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggest(name, options, k=2):
    """Os nomes mais próximos (distância normalizada: ignora '_' e caixa, então chi_95 ~ chi95)."""
    key = lambda x: x.replace("_", "").lower()
    scored = sorted(((_lev(key(name), key(o)), o) for o in options), key=lambda t: (t[0], t[1]))
    lim = max(2, len(name) // 3)
    return [o for d, o in scored[:k] if d <= lim]


def _unknown(name, options, line, kind):
    sg = suggest(name, options)
    hint = f" — você quis dizer {', '.join(repr(x) for x in sg)}?" if sg else ""
    return _f("FALHA", f"unl:linha{line}", f"{kind} {name!r} não registrado{hint} (disponíveis: {sorted(options)[:12]}…)")


# ------------------------------------------------------------------ validação estática
def _f(level, name, detail):
    return (level, name, detail)


def validate(exp, rt):
    """Valida tipos/nomes/contratos e estima custo. Devolve (findings, plan)."""
    R.ensure_loaded()
    out, plan = [], {"points": [], "axes": [], "fields": [], "solver": None, "cost": []}

    def bad(line, msg):
        out.append(_f("FALHA", f"unl:linha{line}", msg))

    out += list(exp.avisos or [])
    S = {v: exp.of(v) for v in VERBS}
    for v in ("SOLVE", "CASE", "MEASURE"):
        if not S[v]:
            bad(0, f"falta {v}")
    if len(S["SOLVE"]) > 1:
        bad(S["SOLVE"][1].line, "apenas um SOLVE por experimento")
    if out:
        return out, plan
    fix, vary, case = {}, {}, {}
    for st in S["CASE"]:
        for k, v in st.data.items():
            if k != "geometry":
                bad(st.line, f"eixo de caso desconhecido {k!r}: use 'geometry'")
            case[k] = v if isinstance(v, list) else [v]
    for verb, dst in (("FIX", fix), ("VARY", vary)):
        for st in S[verb]:
            for k, v in st.data.items():
                if not R.PARAMS.has(k):
                    out.append(_unknown(k, R.PARAMS.names(), st.line, "parâmetro"))
                    continue
                if k in dst or k in (fix if verb == "VARY" else vary):
                    bad(st.line, f"{k!r} não pode ser FIX e VARY (nem repetido)")
                meta = R.PARAMS.meta(k)
                vals = v if (verb == "VARY") else [v]
                if verb == "VARY" and (not isinstance(v, list) or len(v) < 2):
                    bad(st.line, f"VARY {k} precisa de lista com ≥2 valores")
                    continue
                for x in (vals if isinstance(vals, list) else [vals]):
                    ok = isinstance(x, (int, float, complex)) and not isinstance(x, bool) if meta["type"] in ("float", "complex") else True
                    if meta["type"] == "float" and isinstance(x, complex):
                        ok = False
                    if not ok:
                        bad(st.line, f"{k}: valor {x!r} incompatível com tipo {meta['type']}")
                dst[k] = v
    for k in R.PARAMS.names():
        if R.PARAMS.meta(k).get("required") and k not in fix and k not in vary:
            bad(0, f"parâmetro obrigatório {k!r} deve estar em FIX ou VARY")
    for v in vary:
        if R.PARAMS.has(v) and R.PARAMS.meta(v)["kind"] == "numerical":
            vs = vary[v]
            if isinstance(vs, list) and vs != sorted(vs):
                bad(0, f"VARY {v}: valores devem estar em ordem crescente")
    solver = S["SOLVE"][0].data["solver"]
    if not R.SOLVERS.has(solver):
        out.append(_unknown(solver, R.SOLVERS.names(), S["SOLVE"][0].line, "solver"))
    names, measured = set(fix) | set(vary) | {"geometry"}, set()
    fields = []
    for st in S["MEASURE"]:
        for alias, mn in st.data.items():
            if not R.MEASURES.has(mn):
                out.append(_unknown(mn, R.MEASURES.names(), st.line, "medida"))
                continue
            if alias in names:
                bad(st.line, f"alias {alias!r} já em uso")
            names.add(alias); measured.add(alias)
            fields += list(R.MEASURES.meta(mn).get("fields", ()))
    limits, pending = {}, set()
    for st in S["LIMIT"]:
        for k, v in st.data.items():
            limits[k] = v
            names.add(k)
            if v == "pending":
                pending.add(k)
            elif not isinstance(v, (int, float)) or isinstance(v, bool):
                bad(st.line, f"LIMIT {k}: use número ou 'pending'")
    derived = []
    for st in S["DERIVE"]:
        try:
            _check_expr(st.data["expr"], names, st.line, False)
        except UNLError as e:
            bad(e.line, e.msg)
        if st.data["name"] in names:
            bad(st.line, f"nome {st.data['name']!r} já em uso")
        names.add(st.data["name"]); measured.add(st.data["name"]); derived.append(st.data["name"])
    for st in S["CHECK"]:
        try:
            _check_expr(st.data["expr"], names, st.line, True)
        except UNLError as e:
            bad(e.line, e.msg)
    axes = ["geometry"] + list(vary)
    result_names, scal_names = {"cases"}, {}
    for verb, reg in (("COMPARE", R.COMPARATORS), ("ANALYZE", R.ANALYZERS)):
        for st in S[verb]:
            d = st.data
            if not reg.has(d["op"]):
                out.append(_unknown(d["op"], reg.names(), st.line, verb.lower()))
                continue
            schema = reg.meta(d["op"])["params"]
            for pk in d["params"]:
                if pk not in schema:
                    bad(st.line, f"parâmetro {pk!r} inexistente em {d['op']}; aceitos: {sorted(schema)}")
            for pk, (ty, req, desc) in schema.items():
                if pk not in d["params"]:
                    if req:
                        bad(st.line, f"{d['op']}: parâmetro obrigatório {pk!r} ({desc})")
                    continue
                v = d["params"][pk]
                if ty == "measures":
                    vs = v if isinstance(v, list) else [v]
                    for x in vs:
                        if x not in measured:
                            bad(st.line, f"{pk}: {x!r} não é medida/derivada (disponíveis: {sorted(measured)})")
                    d["params"][pk] = vs
                elif ty == "axis":
                    if v not in axes:
                        bad(st.line, f"{pk}: {v!r} não é um eixo (CASE/VARY): {axes}")
                    elif R.PARAMS.has(v) is False and v != "geometry":
                        bad(st.line, f"{pk}: eixo inválido")
                elif ty == "axes":
                    vs = v if isinstance(v, list) else [v]
                    for x in vs:
                        if x not in axes:
                            bad(st.line, f"{pk}: {x!r} não é um eixo: {axes}")
                    d["params"][pk] = vs
                elif ty == "float" and (not isinstance(v, (int, float)) or isinstance(v, bool)):
                    bad(st.line, f"{pk}: esperado número, veio {v!r}")
            if d["name"] in result_names or d["name"] in names:
                bad(st.line, f"nome de resultado {d['name']!r} já em uso")
            result_names.add(d["name"])
    for st in S["OUTPUT"]:
        for t in st.data.get("tables", []):
            if t not in result_names:
                bad(st.line, f"tabela {t!r} desconhecida: {sorted(result_names)}")
        for sc in st.data.get("scalars", []):
            if sc.split(".")[0] not in result_names - {"cases"}:
                bad(st.line, f"escalares de {sc!r}: resultado desconhecido")
    if not S["OUTPUT"]:
        out.append(_f("AVISO", "unl:output", "sem OUTPUT: serão emitidos os casos e todos os resultados"))
    if has_fail(out):
        return out, plan
    # --- plano + custo + capacidade AOP
    state = {**__import__("lib.framework.pipeline", fromlist=["x"]).resolve_state(rt)}
    prov = R.GEOMETRIES.get(state["geometry_provider"])(state)
    tok = {(g["geometry"] if g["seed"] is None else f"{g['geometry']}_{g['seed']}"): g for g in prov["records"]}
    for t in case["geometry"]:
        if t not in tok:
            bad(S["CASE"][0].line, f"geometria {t!r} inexistente; use {sorted(tok)[:6]}…")
    out2 = rt.check_cases([tok[t] for t in case["geometry"] if t in tok], [float(x) for x in (vary.get("frequency_thz") or [fix.get("frequency_thz")])])
    out += [x for x in out2 if x[0] != "OK"]
    if has_fail(out):
        return out, plan
    from lib.framework.pipeline import resolve_fields
    plan["fields"] = resolve_fields(sorted(set(fields)) or ["em_solve"])
    plan["solver"], plan["fix"], plan["vary"], plan["axes"], plan["tokens"] = solver, fix, vary, axes, tok
    plan["solver_options"] = dict(S["SOLVE"][0].data["options"])
    plan["limits"], plan["pending"], plan["derived"], plan["measured"] = limits, pending, derived, measured
    plan["fixed_state"] = dict(fix)
    import itertools
    combos = list(itertools.product(case["geometry"], *[vary[k] for k in vary]))
    budget = float(S["SOLVE"][0].data["options"].get("memory_gb") or available_memory_gb())
    from lib.framework.builtin_core import _grid_for
    from lib.framework.builtin_core import _choose_backend, _est_direct
    req = plan["solver_options"].get("backend", "auto")
    for i, c in enumerate(combos):
        p = dict(zip(axes, c))
        params = {**fix, **{k: p[k] for k in vary}}
        st = {**state, **{k: v for k, v in params.items() if k != "frequency_thz"}}
        pt = {"i": i, "geometry": p["geometry"], "axes": p, "params": params}
        try:
            G = _grid_for(st, tok[p["geometry"]], float(params["frequency_thz"]) * 1e12)
            unk = G["n"][0] * G["n"][1] * (G["n"][2] + 2 * (G["npml"] + G["buf"]))
            be, why = _choose_backend(req, int(unk), budget)
            mem_d, t_d = _est_direct(unk)
            if be == "direct":
                mem, tsec = mem_d, t_d
            else:
                mem, tsec = 0.25 + 0.0 * unk, t_d * 2.0          # iterativo: memória ~constante, ~2x mais lento (medido)
            pt.update(unknowns=int(unk), est_mem_gb=round(mem, 2), est_time_s=round(tsec, 1), backend=be, backend_motivo=why,
                      feasible=(True if req in ("auto", "direct") else bool(mem * 1.25 <= budget)))  # direto: o sentinela decide em tempo real
        except Exception as e:
            bad(0, f"grade do ponto {p}: {e}")
            pt["feasible"] = False
        plan["points"].append(pt)
    plan["budget_gb"] = budget
    nbad = [p for p in plan["points"] if not p.get("feasible")]
    nit = [p for p in plan["points"] if p.get("backend") == "iterative"]
    if nit:
        out.append(_f("AVISO", "unl:backend", f"{len(nit)} pontos usarão o backend iterativo (RAM baixa, mais lento): "
                      + "; ".join(f"{p['axes']}: {p['backend_motivo']}" for p in nit[:4])))
    out.append(_f("AVISO" if nbad else "OK", "unl:custo",
                  f"{len(plan['points'])} pontos; orçamento de memória {budget:.1f} GB; inviáveis: {len(nbad)}"
                  + ("".join(f"\n      · {p['axes']}: ~{p.get('est_mem_gb', '?')} GB, ~{p.get('est_time_s', '?')} s ({p.get('unknowns', '?')} incógnitas)" for p in nbad[:6]))
                  + ("  → esses pontos NÃO cabem nem com o backend iterativo; reduza ppw/geometria ou use SOLVE ..., memory_gb=N" if nbad else "")))
    if not has_fail(out):
        out.append(_f("OK", "unl:validação", f"{exp.name}: {len(plan['points'])} pontos, solver={solver}, campos={plan['fields']}"))
    return out, plan


def has_fail(f):
    return any(x[0] == "FALHA" for x in f)



# ------------------------------------------------------------------ correção por diff
PATCH_RX = re.compile(r"^(\d+)\s*(?:-|:)\s*(.*)$")


def parse_patch(text):
    """Formato de correção: linhas 'N: nova linha' (troca a linha N do experimento) e 'N+: linha' (insere após N),
    'N-' (remove a linha N). Devolve lista de (op, n, conteudo)."""
    ops = []
    for raw in text.splitlines():
        t = raw.strip()
        if not t or t.startswith("#") or t.startswith("```"):
            continue
        m = re.match(r"^(\d+)(\+|-)?\s*[:]\s*(.*)$", t) or re.match(r"^(\d+)(\+|-)\s*()$", t)
        if not m:
            raise UNLError(0, f"linha de correção inválida: {t!r}; use 'N: nova linha', 'N+: linha' ou 'N-'")
        op = {"": "replace", "+": "insert", "-": "delete"}[m.group(2) or ""]
        ops.append((op, int(m.group(1)), m.group(3)))
    if not ops:
        raise UNLError(0, "correção vazia")
    return ops


def apply_patch(text, ops, protect_fix=True):
    """Aplica o patch sobre o texto ORIGINAL (numeração das linhas do que foi mostrado à LLM).
    FIX é invariante do pesquisador: qualquer troca/remoção de linha FIX é recusada, salvo se a linha
    nova for IDÊNTICA à original (no-op). Para mudar um FIX, o pesquisador edita manualmente."""
    lines = text.splitlines()
    fix_lines = {i + 1 for i, l in enumerate(lines) if re.match(r"^\s*FIX\b", _split_comment(l)[0])}
    for op, n, content in ops:
        if n < 1 or n > len(lines):
            raise UNLError(n, "número de linha fora do experimento")
        if protect_fix and n in fix_lines:
            if op == "delete" or (op == "replace" and content.strip() != lines[n - 1].strip()):
                raise UNLError(n, "a correção altera uma linha FIX; FIX é invariante do pesquisador. "
                                  "Corrija as outras linhas, ou peça a mudança explicitamente")
    if protect_fix and any(op == "insert" and n in fix_lines for op, n, _c in ops):
        pass  # inserir DEPOIS de uma linha FIX é permitido (ex.: nova FIX), inserir antes dela também
    out = list(lines)
    # aplica de baixo para cima para não deslocar índices
    for op, n, content in sorted(ops, key=lambda t: (-t[1], t[0] != "insert")):
        if op == "replace":
            out[n - 1] = content
        elif op == "delete":
            del out[n - 1]
        else:
            out.insert(n, content)
    return "\n".join(out)


def numbered(text):
    """Texto com numeração para a LLM citar linhas."""
    return "\n".join(f"{i:>3}| {l}" for i, l in enumerate(text.splitlines(), 1))


# ------------------------------------------------------------------ execução
def _close(a, b, tol=1e-9):
    return abs(complex(a) - complex(b)) <= tol * max(1.0, abs(complex(b)))



# ------------------------------------------------------------------ execução isolada de UM ponto (processo filho)
def _parar_pedido():
    """Pedido de parada do usuário: arquivo 'parar' dentro do run (criado pelo botão ⏹ do chat)."""
    d = os.environ.get("UNIT_RUN_DIR")
    return bool(d) and (Path(d) / "parar").exists()


def _point_worker(payload, q):
    """Roda no processo filho. Só devolve resultados pequenos (escalares, hashes, achados): nunca arrays grandes."""
    try:
        import resource as _res
        R.ensure_loaded()
        from lib.framework import pipeline as P
        rt = aop_dsl.AOPRuntime(aop_dsl.parse(payload["spec_text"]))
        st = {**payload["state0"], **{k: v for k, v in payload["params"].items() if k != "frequency_thz"}}
        rec = payload["rec"]
        case = P.CaseSpec(payload["i"] + 1, rec["geometry"], rec["seed"], float(payload["params"]["frequency_thz"]))
        ctx = P.run_case(st, payload["solver"], payload["fields"], case, rec, options=payload["options"], budget_gb=payload["budget_gb"])
        measures = {alias: float(R.MEASURES.get(mn)(ctx)) for alias, mn in payload["measures"].items()}
        eff = ctx["effective"]
        sig = hashlib.sha256(json.dumps(eff["physical"], sort_keys=True).encode()).hexdigest()[:16]
        fix = {}
        for k, v in payload["params"].items():
            if R.PARAMS.meta(k)["kind"] == "numerical" or k not in payload["fix"]:
                continue
            e = eff.get({"n_inclusion": "n_inclusion_efetivo"}.get(k, k))
            d = fix.setdefault(k, {"verificavel": e is not None, "violacoes": 0, "n": 0, "independente": k in INDEPENDENT})
            if e is not None:
                d["n"] += 1
                if not _close(e, v, 1e-7):
                    d["violacoes"] += 1
        arrays = dict(ctx["arrays"]); arrays["geom_struct"] = ctx["mask"]
        g = dict(ctx["grid"]); g["dV"] = g["dx"] * g["dy"] * g["dz"]
        findings = rt.verify_case({"arrays": arrays, "scalars": ctx["scalars"], "grid": g, "meta": {"geometry_hash": eff["mask_hash"]}})
        pico = _res.getrusage(_res.RUSAGE_SELF).ru_maxrss / 1e6   # GB (ru_maxrss é em KB no Linux)
        q.put(("ok", {"measures": measures, "sig": sig, "fix": fix, "findings": [tuple(x) for x in findings],
                      "mask_hash": eff["mask_hash"], "n_cells": eff["n_cells"], "dx_nm": eff["dx_nm"],
                      "ppw_eff": eff["ppw_eff"], "f_discreta": eff["f_discreta"], "rss_pico_gb": round(pico, 3)}))
    except Exception as e:
        import traceback as _tb
        q.put(("erro", f"{type(e).__name__}: {e}\n{_tb.format_exc(limit=4)[-600:]}"))


def run_experiment(exp, rt, *, log=print, fail_fast=False):
    from lib.framework import pipeline as P
    findings, plan = validate(exp, rt)
    rt.raise_on_fail(findings)
    state0 = P.resolve_state(rt)
    solver, fields, fix, vary, axes = plan["solver"], plan["fields"], plan["fix"], plan["vary"], plan["axes"]
    measures = {}
    for st in exp.of("MEASURE"):
        measures.update(st.data)
    lim = {k: (None if v == "pending" else float(v)) for k, v in plan["limits"].items()}
    t_start = time.time()
    rows, prov_pts, fix_log, aop_log = [], [], {}, []
    from lib.framework.sentinela import run_isolated, memoria_disponivel_gb
    from lib.framework.builtin_core import _choose_backend
    opts = dict(plan["solver_options"])
    reserva = float(opts.get("reserva_gb", 1.0))
    timeout_pt = float(opts.get("timeout_s", 1800))
    req_backend = opts.get("backend", "auto")
    log(f"UNIT-L: {exp.name} | {len(plan['points'])} pontos | solver={solver} | campos={fields} | sentinela: reserva {reserva:.1f} GB")
    for pt in plan["points"]:
        rec = plan["tokens"][pt["geometry"]]
        row = {"geometry": pt["geometry"], **{k: pt["axes"][k] for k in vary}}
        pp = {"i": pt["i"], "axes": pt["axes"], "unknowns": pt.get("unknowns"), "est_mem_gb": pt.get("est_mem_gb")}
        if _parar_pedido():
            rows.append({**row, "_status": "interrompido"})
            prov_pts.append({**pp, "status": "interrompido pelo usuário (não iniciado)"})
            continue
        if not pt.get("feasible"):
            row["_status"] = "inviavel"
            pp["status"] = "inviavel: memória estimada acima do orçamento"
            rows.append(row); prov_pts.append(pp)
            log(f"  [{pt['i'] + 1}/{len(plan['points'])}] {pt['axes']}: INVIÁVEL (~{pt['est_mem_gb']} GB > {plan['budget_gb']:.1f} GB) — pulado")
            continue
        disp_agora = memoria_disponivel_gb()
        if req_backend == "auto" and pt.get("unknowns") and disp_agora == disp_agora:
            be, why = _choose_backend("auto", int(pt["unknowns"]), disp_agora - reserva)
            pt["backend"], pt["backend_motivo"] = be, why + " (memória medida agora)"
        options = {**opts, "backend": pt.get("backend", "direct")}
        payload = {"spec_text": rt.spec.text, "state0": state0, "params": pt["params"], "i": pt["i"], "rec": rec,
                   "solver": solver, "fields": fields, "measures": measures, "options": options, "budget_gb": plan["budget_gb"],
                   "fix": fix}
        label = f"[{pt['i'] + 1}/{len(plan['points'])}] {pt['axes']}"
        log(f"  {label}: iniciando (backend {options['backend']}, RAM livre agora {disp_agora:.1f} GB)")
        res = run_isolated(_point_worker, payload, reserva_gb=reserva, timeout_s=timeout_pt, label=label)
        if res["status"] == "abortado_memoria" and req_backend == "auto" and options["backend"] == "direct" and not _parar_pedido():
            log(f"  {label}: direto abortado pelo sentinela (RAM caiu abaixo de {reserva:.1f} GB); repetindo este ponto com o iterativo (mesma física)")
            options = {**options, "backend": "iterative"}
            payload["options"] = options
            pt["fallback"] = True
            res = run_isolated(_point_worker, payload, reserva_gb=reserva, timeout_s=timeout_pt, label=label)
        if _parar_pedido() and res["status"] != "ok":
            res = {**res, "status": "interrompido"}
        pp.update(backend=options["backend"], fallback=bool(pt.get("fallback")), backend_motivo=pt.get("backend_motivo"), t_s=round(res["tempo_s"], 1),
                  pico_sentinela_gb=round(res["pico_gb"], 3), min_disp_gb=round(res["min_disp_gb"], 3) if res["min_disp_gb"] != float("inf") else None)
        if res["status"] == "ok":
            d = res["data"]
            row.update(d["measures"])
            row.update({"tempo_s": round(res["tempo_s"], 1), "rss_pico_gb": d["rss_pico_gb"]})
            row["_status"] = "ok"
            row["_sig"] = d["sig"]
            for k, v in d["fix"].items():
                acc = fix_log.setdefault(k, {"verificavel": v["verificavel"], "violacoes": 0, "n": 0, "independente": v["independente"]})
                acc["n"] += v["n"]; acc["violacoes"] += v["violacoes"]
            bad = [x for x in d["findings"] if x[0] == "FALHA"]
            row["_aop"] = "FALHA" if bad else "OK"
            aop_log += [(pt["axes"], x) for x in bad]
            pp.update(status="ok", mask_hash=d["mask_hash"], physical_sig=d["sig"], n_cells=d["n_cells"], dx_nm=d["dx_nm"],
                      ppw_eff=d["ppw_eff"], f_discreta=d["f_discreta"], aop=row["_aop"], rss_pico_gb=d["rss_pico_gb"])
            first = list(measures)[:4]
            log(f"  {label}: ok em {res['tempo_s']:.1f}s · pico {d['rss_pico_gb']:.2f} GB | " + ", ".join(f"{a}={row[a]:.6g}" for a in first) + f" | AOP {row['_aop']}")
            for x in bad:
                log(f"      ✗ {x[1]}: {x[2]}")
        else:
            row["_status"] = res["status"]
            pp["status"] = f"{res['status']}: {res['data']}"
            log(f"  {label}: {res['status'].upper()} — {str(res['data'])[:200]}")
            if res["status"] == "interrompido":
                log(f"  {label}: INTERROMPIDO pelo usuário")
                rows.append(row); prov_pts.append(pp)
                break
            if fail_fast and res["status"] == "erro":
                rows.append(row); prov_pts.append(pp)
                break
        rows.append(row); prov_pts.append(pp)
    okrows = [r for r in rows if r.get("_status") == "ok"]
    # DERIVE
    for st in exp.of("DERIVE"):
        tree = ast.parse(st.data["expr"], mode="eval")
        for r in okrows:
            ns = {k: v for k, v in r.items() if not k.startswith("_") and isinstance(v, (int, float))}
            ns.update({k: v for k, v in lim.items() if v is not None})
            try:
                r[st.data["name"]] = float(_eval(tree.body, ns))
            except Exception as e:
                r[st.data["name"]] = float("nan")
    # CHECK
    checks = []
    for st in exp.of("CHECK"):
        tree = ast.parse(st.data["expr"], mode="eval").body
        cnt, det = {"PASS": 0, "FAIL": 0, "PENDENTE": 0}, []
        for r in okrows:
            ns = {k: v for k, v in r.items() if not k.startswith("_") and isinstance(v, (int, float))}
            ns.update({k: v for k, v in lim.items() if v is not None})
            try:
                s, d = _eval_check(tree, ns, plan["pending"])
            except Exception as e:
                s, d = "FAIL", f"erro ao avaliar: {type(e).__name__}: {e}"
            cnt[s] += 1
            det.append({"ponto": {a: r[a] for a in axes}, "status": s, "detalhe": d})
        status = "FAIL" if cnt["FAIL"] else ("PENDENTE" if cnt["PENDENTE"] else ("PASS" if cnt["PASS"] else "SEM_DADOS"))
        checks.append({"nome": st.data["name"], "expr": st.data["expr"], "status": status, **cnt, "detalhes": det})
    # invariantes estruturais
    inv = []
    phys_vary = [k for k in vary if R.PARAMS.meta(k)["kind"] == "physical"]
    numerical = [k for k in vary if R.PARAMS.meta(k)["kind"] == "numerical"]
    if numerical:
        grp = {}
        for r in okrows:
            grp.setdefault((r["geometry"], tuple(r[k] for k in phys_vary)), set()).add(r["_sig"])
        badg = [k for k, v in grp.items() if len(v) > 1]
        inv.append({"nome": f"invariância física ao variar {numerical}", "status": "FAIL" if badg else "PASS",
                    "detalhe": f"{len(grp)} grupos; violados: {badg}" if badg else f"{len(grp)} grupos com assinatura física idêntica (geometria, domínio, frequência, índices, PML/buffer EFETIVOS)"})
    for k, d in fix_log.items():
        inv.append({"nome": f"FIX {k}", "status": ("FAIL" if d["violacoes"] else "PASS") if d["verificavel"] else "NAO_VERIFICAVEL",
                    "detalhe": (f"{d['n']} pontos; violações={d['violacoes']}; " + ("valor efetivo RECOMPUTADO da discretização" if d["independente"] else "apenas eco do parâmetro repassado ao solver (verificação fraca)")) if d["verificavel"] else "o solver não expõe o valor efetivo"})
    inv.append({"nome": "AOP por ponto", "status": "FAIL" if aop_log else "PASS", "detalhe": f"{len(aop_log)} violações" if aop_log else "verificadores AOP OK em todos os pontos"})
    # COMPARE / ANALYZE
    results = {}
    info = {"axes": axes}
    for verb, reg in (("COMPARE", R.COMPARATORS), ("ANALYZE", R.ANALYZERS)):
        for st in exp.of(verb):
            d = st.data
            try:
                results[d["name"]] = reg.get(d["op"])(okrows, d["params"], info)
                results[d["name"]]["op"] = d["op"]
            except Exception as e:
                results[d["name"]] = {"rows": [], "scalars": {}, "erro": f"{type(e).__name__}: {e}"}
                log(f"  ✗ {verb} {d['name']}: {type(e).__name__}: {e}")
    lib_h = P._lib_hash()
    prov = {"language": LANG_VERSION, "experiment": exp.name, "experiment_sha256": exp.sha256, "aop_spec_sha256": rt.spec.sha256,
            "framework_version": R.FRAMEWORK_VERSION, "lib_hash": lib_h, "solver": solver, "fields": fields, "fix": fix, "vary": vary,
            "limits": plan["limits"], "points": prov_pts, "duracao_s": round(time.time() - t_start, 1), "budget_gb": plan["budget_gb"],
            "results_lineage": {k: {"op": v.get("op"), "inputs": "linhas 'ok' de cases"} for k, v in results.items()}}
    n_inv = sum(1 for r in rows if r.get("_status") == "inviavel")
    n_err = sum(1 for r in rows if r.get("_status") not in ("ok", "inviavel"))
    return {"experiment": exp.name, "goal": next((s.data for s in exp.of("GOAL")), ""), "rows": rows, "checks": checks, "invariants": inv, "results": results,
            "provenance": prov, "n_ok": len(okrows), "n_inviaveis": n_inv, "n_erros": n_err, "findings": findings}


def public_row(r):
    return {k: v for k, v in r.items() if not k.startswith("_")} | {"status": r.get("_status")}


def _fv(v, spec=".6g"):
    """Valor para o relatório: não finito vira 'n/d' (o laboratório trata 'nan' no stdout como FALHA)."""
    if isinstance(v, (float, np.floating)):
        return format(float(v), spec) if math.isfinite(float(v)) else "n/d"
    return str(v)


def render_report(res):
    L = [f"# {res['experiment']} — relatório UNIT-L", ""]
    if res["goal"]:
        L += [f"**Pergunta:** {res['goal']}", ""]
    L += [f"Pontos ok: {res['n_ok']} · inviáveis (memória): {res['n_inviaveis']} · erros: {res['n_erros']}", "", "## Invariantes verificados pelo motor"]
    L += [f"- [{i['status']}] {i['nome']}: {i['detalhe']}" for i in res["invariants"]]
    L += ["", "## CHECKs"]
    L += [f"- [{c['status']}] {c['nome']}: `{c['expr']}` (pass={c['PASS']} fail={c['FAIL']} pendente={c['PENDENTE']})" for c in res["checks"]] or ["(nenhum)"]
    for c in res["checks"]:
        for d in c["detalhes"][:12]:
            L.append(f"    · {d['ponto']}: {d['detalhe']}")
    L += ["", "## Casos"]
    cols = [k for k in res["rows"][0] if not k.startswith("_")] if res["rows"] else []
    ok = [r for r in res["rows"] if r.get("_status") == "ok"]
    allc = list(dict.fromkeys(c for r in ok for c in r if not c.startswith("_")))
    L.append("| status | " + " | ".join(allc) + " |")
    L.append("|---|" + "---|" * len(allc))
    for r in res["rows"]:
        L.append(f"| {r.get('_status')} | " + " | ".join(_fv(r.get(c, "")) for c in allc) + " |")
    for name, r in res["results"].items():
        L += ["", f"## {name} ({r.get('op')})"]
        if r.get("erro"):
            L.append(f"ERRO: {r['erro']}")
        for k, v in r["scalars"].items():
            L.append(f"- {k} = {_fv(v)}")
        for row in r["rows"][:40]:
            L.append("    · " + ", ".join(f"{k}={_fv(v, '.5g')}" for k, v in row.items() if k not in ("niveis", "valores")))
    return "\n".join(L)


# ------------------------------------------------------------------ entrada do laboratório
def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, complex):
        return {"re": o.real, "im": o.imag}
    return o


def run_experiment_in_run():
    run_dir = Path(os.environ["UNIT_RUN_DIR"])
    exp = parse((run_dir / "experiment.unl").read_text(encoding="utf-8"))
    rt = aop_dsl.AOPRuntime(aop_dsl.parse_file(run_dir / "spec.aop"))
    try:
        res = run_experiment(exp, rt)
    except aop_dsl.AOPViolation as e:
        print(f"AOP/UNIT-L BLOQUEOU: {e}")
        for lv, n, d in e.findings:
            print(f"  {'✗' if lv == 'FALHA' else '·'} {n}: {d}")
        raise SystemExit(3)
    (run_dir / "experiment_provenance.json").write_text(json.dumps(_clean(res["provenance"]), indent=1, ensure_ascii=False), encoding="utf-8")
    (run_dir / "experiment_result.json").write_text(json.dumps(_clean({k: v for k, v in res.items() if k != "provenance"}), indent=1, ensure_ascii=False), encoding="utf-8")
    report = render_report(res)
    (run_dir / "report_unl.md").write_text(report, encoding="utf-8")
    outs = exp.of("OUTPUT")
    want_t = [t for o in outs for t in o.data.get("tables", [])] or ["cases"] + list(res["results"])
    want_s = [s for o in outs for s in o.data.get("scalars", [])] or list(res["results"])
    tabela, esc = [], {}
    for t in want_t:
        rows = [public_row(r) for r in res["rows"]] if t == "cases" else res["results"][t]["rows"]
        tabela += [{"tabela": t, **{k: v for k, v in r.items() if k not in ("niveis", "valores")}} for r in rows]
    for s in want_s:
        base, _, key = s.partition(".")
        sc = res["results"][base]["scalars"]
        for k, v in sc.items():
            if not key or k == key:
                esc[f"{base}.{k}"] = v
    for c in res["checks"]:
        esc[f"check.{c['nome']}"] = c["status"]
    esc.update(pontos_ok=res["n_ok"], pontos_inviaveis=res["n_inviaveis"], pontos_erro=res["n_erros"])
    print(report)
    for k, v in esc.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
            print(f"{k}: {v}")
    print("UNIT_RESULT_JSON: " + json.dumps(_clean({"tabela": tabela[:300], "escalares": esc}), ensure_ascii=False))
    fails = [i for i in res["invariants"] if i["status"] == "FAIL"] + [c for c in res["checks"] if c["status"] == "FAIL"]
    if fails or res["n_erros"]:
        raise SystemExit(4)


# ------------------------------------------------------------------ referência da linguagem (gerada do TOML)
from lib.framework.lang.spec import describe_language, referencia_md  # noqa: E402,F401
