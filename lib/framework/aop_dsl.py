"""
aop_dsl.py — AOP-DSL (Agent-Oriented Physics DSL) ESTRUTURAL.

Não é um middleware opcional: o pipeline (pipeline.py) não roda sem um Spec, e o laboratório
(notebook) só executa código passando por AOPRuntime.preflight_* antes e verify_* depois.

Gramática (blocos nomeados, uma chave por linha, comentários com #):

    KIND Nome {
        chave: valor        # valor = literal Python (números, 1e-9, 2.0+0.05j, "texto", [listas], {dicts}) ou true/false/null
    }

KINDs: STATE GOAL CONSTRAINT CAPABILITY AGENT ACTION OBSERVATION VERIFICATION PROVENANCE
Compatível também com o formato legado BEGIN KIND ... END KIND.

Convenção de achados: tuplas (nivel, nome, detalhe), nivel em {"OK","AVISO","FALHA"} — o mesmo formato
que validar_run() do laboratório, então entram direto no relatório.
"""
import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from lib.framework import registry as R

KINDS = ("STATE", "GOAL", "CONSTRAINT", "CAPABILITY", "AGENT", "ACTION", "OBSERVATION", "VERIFICATION", "PROVENANCE")

DEFAULT_FORBID_CALLS = ("__import__", "eval", "exec", "compile")
DEFAULT_FORBID_MODULES = ("importlib", "subprocess", "socket", "ctypes")


class AOPSyntaxError(ValueError):
    pass


class AOPViolation(Exception):
    def __init__(self, findings):
        self.findings = findings
        fl = [f"{n}: {d}" for lv, n, d in findings if lv == "FALHA"]; super().__init__("; ".join(fl[:3]) + (f" (+{len(fl)-3} violações)" if len(fl) > 3 else "") or "violação AOP")


@dataclass
class Block:
    kind: str
    name: str
    data: dict = field(default_factory=dict)
    line: int = 0


@dataclass
class Spec:
    blocks: list
    text: str = ""

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def of(self, kind):
        return [b for b in self.blocks if b.kind == kind]

    def merged(self, kind):
        out = {}
        for b in self.of(kind):
            out.update(b.data)
        return out

    def to_dict(self):
        return {"sha256": self.sha256, "blocks": [{"kind": b.kind, "name": b.name, "data": b.data} for b in self.blocks]}


# --------------------------------------------------------------------------- parser
_HEADER = re.compile(r"^([A-Z]+)\s+([A-Za-z_][\w\-\.]*)\s*\{$")
_BEGIN = re.compile(r"^BEGIN\s+([A-Za-z]+)$", re.I)
_END = re.compile(r"^END\s+([A-Za-z]+)$", re.I)
_KV = re.compile(r"^([A-Za-z_]\w*)\s*[:=]\s*(.*)$")
_BOOL = re.compile(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')|\b(true|false|null)\b')


def _strip_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q and line[i - 1] != "\\":
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#":
            return line[:i]
    return line


def _depth(s):
    d, q = 0, None
    for i, ch in enumerate(s):
        if q:
            if ch == q and s[i - 1] != "\\":
                q = None
        elif ch in "\"'":
            q = ch
        elif ch in "([{":
            d += 1
        elif ch in ")]}":
            d -= 1
    return d


def _value(raw, lineno):
    raw = raw.strip()
    if not raw:
        raise AOPSyntaxError(f"linha {lineno}: valor vazio")
    conv = _BOOL.sub(lambda m: m.group(1) or {"true": "True", "false": "False", "null": "None"}[m.group(2)], raw)
    try:
        return ast.literal_eval(conv)
    except (ValueError, SyntaxError):
        if re.fullmatch(r"[A-Za-z_][\w\.\-]*", raw):
            return raw  # palavra solta vira string (ex.: RANDOM_1002, lib.x.y)
        raise AOPSyntaxError(f"linha {lineno}: valor inválido: {raw!r}")


def parse(text):
    blocks, cur, legacy = [], None, False
    pend_key, pend_val, pend_line = None, "", 0
    for n, original in enumerate(text.splitlines(), 1):
        line = _strip_comment(original).strip()
        if not line:
            continue
        if cur is None:
            m = _HEADER.match(line)
            if m:
                if m.group(1) not in KINDS:
                    raise AOPSyntaxError(f"linha {n}: tipo de bloco desconhecido {m.group(1)!r}; use {KINDS}")
                cur, legacy = Block(m.group(1), m.group(2), {}, n), False
                continue
            m = _BEGIN.match(line)
            if m:
                if m.group(1).upper() not in KINDS:
                    raise AOPSyntaxError(f"linha {n}: tipo de bloco desconhecido {m.group(1)!r}")
                cur, legacy = Block(m.group(1).upper(), "default", {}, n), True
                continue
            raise AOPSyntaxError(f"linha {n}: esperado 'KIND Nome {{' ou 'BEGIN KIND', achei: {line!r}")
        # dentro de bloco
        if pend_key is not None:
            pend_val += " " + line
            if _depth(pend_val) <= 0:
                cur.data[pend_key] = _value(pend_val, pend_line)
                pend_key = None
            continue
        if (not legacy and line == "}") or (legacy and _END.match(line)):
            blocks.append(cur)
            cur = None
            continue
        m = _KV.match(line)
        if not m:
            raise AOPSyntaxError(f"linha {n}: esperado 'chave: valor', achei: {line!r}")
        k, v = m.group(1), m.group(2)
        if k in cur.data:
            raise AOPSyntaxError(f"linha {n}: chave duplicada {k!r} no bloco {cur.kind} {cur.name}")
        if _depth(v) > 0:
            pend_key, pend_val, pend_line = k, v, n
        else:
            cur.data[k] = _value(v, n)
    if cur is not None:
        raise AOPSyntaxError(f"bloco {cur.kind} {cur.name} (linha {cur.line}) não foi fechado")
    if pend_key is not None:
        raise AOPSyntaxError(f"valor de {pend_key!r} (linha {pend_line}) não foi fechado")
    return Spec(blocks, text)


def parse_file(path):
    return parse(Path(path).read_text(encoding="utf-8"))


def extract_from_markdown(text):
    """Devolve o texto do primeiro bloco ```aop-dsl / ```aop encontrado, ou None."""
    m = re.search(r"```(?:aop-dsl|aop)\s*\n(.*?)```", text, flags=re.S | re.I)
    return m.group(1).strip() if m else None


# --------------------------------------------------------------------------- esquema
_NUM = (int, float)
SCHEMA = {
    "STATE": {"geometry_provider": (str,), "geometries": (list,), "seeds": (list,), "frequencies_thz": (list,),
              "mesh_dx": _NUM, "n_bg": _NUM + (complex,), "n_inclusion": _NUM + (complex,), "k_bg": _NUM,
              "k_inclusion": _NUM, "npml_cells": (int,), "buffer_cells": (int,), "max_cases": (int,)},
    "CONSTRAINT": {"max_volume_fraction": _NUM, "frequencies_thz_allowed": (list,), "min_realizations": (int,),
                   "temperature_limit_k": (list,), "energy_conservation_tolerance": _NUM,
                   "required_authority_level": _NUM, "forbid_calls": (list,), "forbid_modules": (list,)},
    "CAPABILITY": {"solver": (str,), "fields": (list,), "tests": (list,), "allowed_modules": (list,)},
    "AGENT": {"role": (str,), "authority_level": _NUM, "allow_autocorrect": (bool,), "max_retries": (int,)},
    "ACTION": {"run": (str,), "tests": (list,), "fail_fast": (bool,)},
    "PROVENANCE": {"track_hashes": (list,), "immutable_library": (bool,)},
}


def _f(level, name, detail):
    return (level, name, detail)


def has_fail(findings):
    return any(lv == "FALHA" for lv, _, _ in findings)


# --------------------------------------------------------------------------- runtime
class AOPRuntime:
    def __init__(self, spec):
        if not isinstance(spec, Spec):
            raise TypeError("AOPRuntime exige um Spec (aop_dsl.parse(...)). Não existe execução sem especificação.")
        self.spec = spec
        R.ensure_loaded()

    # -- acesso
    def state(self):
        return self.spec.merged("STATE")

    def constraint(self):
        return self.spec.merged("CONSTRAINT")

    def capability(self):
        return self.spec.merged("CAPABILITY")

    def agent(self):
        return self.spec.merged("AGENT")

    def action(self):
        return self.spec.merged("ACTION")

    def raise_on_fail(self, findings):
        if has_fail(findings):
            raise AOPViolation(findings)
        return findings

    # -- 1. especificação
    def preflight_spec(self):
        out = []
        if not self.spec.blocks:
            return [_f("FALHA", "aop:spec", "especificação vazia")]
        for b in self.spec.blocks:
            schema = SCHEMA.get(b.kind, {})
            for k, v in b.data.items():
                if k in schema:
                    if isinstance(v, bool) and bool not in schema[k]:
                        out.append(_f("FALHA", f"aop:tipo:{b.kind}.{k}", f"bool não aceito aqui"))
                    elif not isinstance(v, schema[k]):
                        out.append(_f("FALHA", f"aop:tipo:{b.kind}.{k}", f"esperado {[t.__name__ for t in schema[k]]}, veio {type(v).__name__}"))
                elif b.kind in ("CONSTRAINT", "CAPABILITY", "AGENT", "PROVENANCE"):
                    out.append(_f("AVISO", f"aop:chave:{b.kind}.{k}", "chave fora do esquema (ignorada pelo runtime)"))
        st, cap, act = self.state(), self.capability(), self.action()
        gp = st.get("geometry_provider")
        if gp and not R.GEOMETRIES.has(gp):
            out.append(_f("FALHA", "aop:capability", f"geometry_provider {gp!r} não registrado: {R.GEOMETRIES.names()}"))
        if cap.get("solver") and not R.SOLVERS.has(cap["solver"]):
            out.append(_f("FALHA", "aop:capability", f"solver {cap['solver']!r} não registrado: {R.SOLVERS.names()}"))
        for fl in cap.get("fields", []):
            if not R.FIELDS.has(fl):
                out.append(_f("FALHA", "aop:capability", f"campo {fl!r} não registrado: {R.FIELDS.names()}"))
        for tn in list(cap.get("tests", [])) + list(act.get("tests", [])):
            if not R.TESTS.has(tn):
                out.append(_f("FALHA", "aop:capability", f"teste {tn!r} não registrado: {R.TESTS.names()}"))
        for b in self.spec.of("VERIFICATION"):
            for k, v in b.data.items():
                if not k.startswith("assert_"):
                    out.append(_f("FALHA", f"aop:verification:{k}", "chaves de VERIFICATION devem começar com 'assert_'"))
                elif not R.VERIFIERS.has(k):
                    out.append(_f("FALHA", f"aop:verification:{k}", f"verificador não registrado (erro de digitação não passa em silêncio): {R.VERIFIERS.names()}"))
        need = self.constraint().get("required_authority_level", 0)
        have = self.agent().get("authority_level", 0)
        if have < need:
            out.append(_f("FALHA", "aop:autoridade", f"agente nível {have} < exigido {need}"))
        if not has_fail(out):
            out.append(_f("OK", "aop:spec", f"válida (sha256 {self.spec.sha256[:12]}, {len(self.spec.blocks)} blocos)"))
        return out

    # -- 2. código (AST)
    def preflight_code(self, code):
        con, cap = self.constraint(), self.capability()
        fcalls = set(con.get("forbid_calls", DEFAULT_FORBID_CALLS))
        fmods = set(con.get("forbid_modules", DEFAULT_FORBID_MODULES))
        allowed = cap.get("allowed_modules")
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [_f("FALHA", "aop:código", f"sintaxe linha {e.lineno}: {e.msg}")]
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                nm = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
                if nm in fcalls:
                    bad.append(f"linha {node.lineno}: chamada proibida {nm}()")
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                top = m.split(".")[0]
                if top in fmods:
                    bad.append(f"linha {node.lineno}: módulo proibido {m}")
                if (top == "lib") and allowed is not None and not any(m == a or m.startswith(a + ".") for a in allowed):
                    bad.append(f"linha {node.lineno}: {m} fora de CAPABILITY.allowed_modules")
        if bad:
            return [_f("FALHA", "aop:código", "; ".join(bad[:8]))]
        out = [_f("OK", "aop:código", "AST sem chamadas/módulos proibidos e imports lib.* dentro do permitido")]
        # Regra fundamental: não reimplementar o que o laboratório já tem (aviso — o veredito é do pesquisador)
        known = set()
        for reg in (R.MEASURES, R.COMPARATORS, R.ANALYZERS, R.FIELDS, R.TESTS, R.VERIFIERS, R.SOLVERS):
            known |= {n.lower() for n in reg.names() if len(n) >= 4}
        redo = sorted({n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and any(k in n.name.lower() for k in known)})
        if redo:
            out.append(_f("AVISO", "aop:reimplementação", f"funções {redo} parecem reimplementar primitivas registradas (/catalogo); componha-as em UNIT-L (/linguagem)"))
        io = sorted({f"{ast.unparse(n.func)}" for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) in ("np.load", "numpy.load", "os.listdir", "glob.glob", "os.walk")})
        if io:
            out.append(_f("AVISO", "aop:infraestrutura", f"{io}: leitura/descoberta de arquivos feita à mão; use lib.framework.dataset.Dataset ou um EXPERIMENT UNIT-L"))
        return out

    # -- 3. parâmetros (antes de gastar CPU)
    def check_cases(self, geoms, frequencies_thz, n_random=None):
        con, out = self.constraint(), []
        mx = con.get("max_volume_fraction")
        if mx is not None:
            for g in geoms:
                frac = float(g["mask"].mean())
                if frac > mx + 1e-12:
                    out.append(_f("FALHA", "aop:max_volume_fraction", f"{g['geometry']} seed={g['seed']}: {frac:.6f} > {mx}"))
        allowed = con.get("frequencies_thz_allowed")
        if allowed is not None:
            for f in frequencies_thz:
                if float(f) not in [float(a) for a in allowed]:
                    out.append(_f("FALHA", "aop:frequencies_thz_allowed", f"{f} THz fora de {allowed}"))
        mr = con.get("min_realizations")
        if mr is not None and n_random is not None and n_random < mr:
            out.append(_f("FALHA", "aop:min_realizations", f"{n_random} realizações RANDOM < {mr}"))
        if not out:
            out.append(_f("OK", "aop:parâmetros", f"{len(geoms)} geometrias e {len(frequencies_thz)} frequências dentro das CONSTRAINT"))
        return out

    # -- 4. verificação pós-execução (Zero Trust: sobre os dados brutos)
    def _verification_items(self):
        items = []
        for b in self.spec.of("VERIFICATION"):
            for k, v in b.data.items():
                if k.startswith("assert_") and v is not False:
                    items.append((k, v))
        con = self.constraint()
        if "temperature_limit_k" in con:
            items.append(("assert_temperature_limit_k", con["temperature_limit_k"]))
        if "energy_conservation_tolerance" in con:
            items.append(("assert_energy_conservation", con["energy_conservation_tolerance"]))
        return items

    def verify(self, ctx):
        out = []
        for key, val in self._verification_items():
            try:
                res = R.VERIFIERS.get(key)(self, val, ctx)
            except KeyError as e:
                res = [_f("FALHA", f"aop:{key}", str(e))]
            except Exception as e:
                res = [_f("FALHA", f"aop:{key}", f"verificador levantou {type(e).__name__}: {e}")]
            out.extend(res or [])
        return out

    def verify_case(self, ctx):
        ctx = dict(ctx, scope="case")
        return self.verify(ctx)

    def verify_run(self, run_dir, rj=None, stdout=""):
        """Reverifica um run do laboratório: escalares do JSON + cada NPZ listado em aop_cases.json."""
        from lib.framework.dataset import ctx_from_npz
        run_dir, out = Path(run_dir), []
        out += self.verify({"scope": "run", "json": rj, "scalars": (rj or {}).get("escalares", {}) if isinstance(rj, dict) else {},
                            "stdout": stdout, "run_dir": run_dir, "arrays": {}, "grid": {}})
        idx = run_dir / "aop_cases.json"
        if idx.exists():
            paths = json.loads(idx.read_text(encoding="utf-8")).get("npz", [])
            n_bad = 0
            for p in paths:
                try:
                    f = self.verify_case(ctx_from_npz(p))
                except Exception as e:
                    f = [_f("FALHA", "aop:npz", f"{Path(p).name}: {type(e).__name__}: {e}")]
                for lv, nm, d in f:
                    if lv != "OK":
                        n_bad += 1
                        out.append((lv, nm, f"{Path(p).name}: {d}"))
            if not n_bad:
                out.append(_f("OK", "aop:reverificação", f"{len(paths)} casos reverificados a partir dos NPZ no disco"))
        return out
