"""
parser.py — leitor genérico da UNIT-L. A sintaxe vem de unl_spec.toml; aqui só existem os TIPOS de verbo (kinds).

Adicionar um verbo de um tipo existente = editar o TOML (sem código).
Adicionar um tipo novo = código nesta função KINDS + descrição em unl_spec.toml.
"""
import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from lib.framework.aop_dsl import _strip_comment, _depth
from lib.geometry import unit001_constantes as _C
PARAMETROS_ESTUDO = {n: getattr(_C, n) for n in ("N_FUNDO_ESTUDO", "N_INCLUSAO_ESTUDO", "K_FUNDO_ESTUDO", "K_INCLUSAO_ESTUDO", "PML_NM_ESTUDO", "BUFFER_NM_ESTUDO", "CLOSURE_TOL_ESTUDO")}

SPEC_PATH = Path(__file__).with_name("unl_spec.toml")
KINDS_KNOWN = ("block", "text", "kv", "solve", "measure", "assign_expr", "check", "op_call")
# Checagens que o validador (experiment.validate) realmente implementa. unl_spec.toml só pode citar estas.
ENFORCERS_IMPLEMENTED = {
    "required_param", "fix_vary_conflict", "unknown_name", "check_literal", "numerical_order",
    "unknown_registry_name", "expression_safety", "cost_estimate",
}


class UNLError(ValueError):
    def __init__(self, line, msg):
        self.line, self.msg = line, msg
        super().__init__(f"linha {line}: {msg}" if line else msg)


@dataclass
class Stmt:
    verb: str
    line: int
    data: object


@dataclass
class Experiment:
    name: str
    stmts: list
    text: str
    avisos: list = None

    @property
    def sha256(self):
        import hashlib
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def of(self, verb):
        return [s for s in self.stmts if s.verb == verb]


def _f(level, name, detail):
    return (level, name, detail)


# ───────────────────────── carregamento e validação da especificação ─────────────────────────
def load_spec(path=SPEC_PATH):
    d = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    erros = []
    verbs = d.get("verbs", [])
    nomes = [v.get("name") for v in verbs]
    if len(set(nomes)) != len(nomes):
        erros.append(f"verbos duplicados: {sorted({n for n in nomes if nomes.count(n) > 1})}")
    for v in verbs:
        if v.get("kind") not in KINDS_KNOWN:
            erros.append(f"verbo {v.get('name')}: tipo desconhecido {v.get('kind')!r}; use {KINDS_KNOWN}")
        if not v.get("doc"):
            erros.append(f"verbo {v.get('name')}: falta 'doc' (a LLM precisa da descrição)")
    ids = [n.get("id") for n in d.get("normalize", [])]
    if len(set(ids)) != len(ids):
        erros.append("ids de normalização duplicados")
    for n in d.get("normalize", []):
        if n.get("action") not in ("regex", "wrap_list"):
            erros.append(f"normalize {n.get('id')}: action desconhecida {n.get('action')!r}")
        if n.get("action") == "regex":
            try:
                re.compile(n["pattern"])
            except Exception as e:
                erros.append(f"normalize {n.get('id')}: regex inválida ({e})")
    for r in d.get("rules", []):
        if r.get("enforced_by") not in ENFORCERS_IMPLEMENTED:
            erros.append(f"regra {r.get('id')}: enforced_by {r.get('enforced_by')!r} não está implementado no validador")
    if erros:
        raise ValueError("unl_spec.toml inválido:\n  - " + "\n  - ".join(erros))
    return d


SPEC = load_spec()
VERB_SPEC = {v["name"]: v for v in SPEC["verbs"]}
VERBS = tuple(v["name"] for v in SPEC["verbs"])
LANG_VERSION = f"{SPEC['meta']['name']} {SPEC['meta']['version']}"
ALLOWED_CHECK_NUMBERS = tuple(SPEC["engine"]["allowed_check_numbers"])
INDEPENDENT = tuple(SPEC["engine"]["independent_fix"])
EXPRESSION_FUNCTIONS = tuple(SPEC["engine"]["expression_functions"])


# ───────────────────────── normalização de forma (declarativa) ─────────────────────────
def _split_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q and line[i - 1] != "\\":
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#":
            return line[:i], "#", line[i + 1:]
    return line, "", ""


def normalize(text):
    """Aplica [[normalize]] do TOML. Devolve (texto, avisos). Só correções inequívocas."""
    avisos, out = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        code, sep, com = _split_comment(raw)
        m = re.match(r"^(\s*)([A-Z]+)\b", code)
        verb = m.group(2) if m and m.group(2) in VERB_SPEC else None
        for rule in SPEC["normalize"]:
            if "*" not in rule["verbs"] and verb not in rule["verbs"]:
                continue
            if rule["action"] == "regex":
                prefixo = m.group(0) if (verb and m) else ""
                corpo = code[len(prefixo):]
                novo = re.sub(rule["pattern"], rule["replace"], corpo)
                if novo != corpo:
                    code = prefixo + novo
                    avisos.append(_f("AVISO", f"unl:forma:linha{n}", rule["message"]))
            elif rule["action"] == "wrap_list" and verb:
                mm = re.match(rf"^(\s*{verb}\s+[A-Za-z_]\w*\s*=\s*)(.+?)\s*$", code)
                if mm and "," in mm.group(2) and not mm.group(2).lstrip().startswith("["):
                    code = mm.group(1) + "[" + mm.group(2).strip() + "]"
                    avisos.append(_f("AVISO", f"unl:forma:linha{n}", rule["message"]))
        out.append(code + (sep + com if sep else ""))
    return "\n".join(out), avisos


# ───────────────────────── leitura de átomos ─────────────────────────
def _lit(n, line):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in PARAMETROS_ESTUDO:
            return PARAMETROS_ESTUDO[n.id]
        return n.id
    if isinstance(n, ast.Attribute):
        return f"{_lit(n.value, line)}.{n.attr}"
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = _lit(n.operand, line)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub)):
        a, b = _lit(n.left, line), _lit(n.right, line)
        if all(isinstance(x, (int, float, complex)) for x in (a, b)):
            return a + b if isinstance(n.op, ast.Add) else a - b
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_lit(e, line) for e in n.elts]
    if isinstance(n, ast.Dict):
        return {_lit(k, line): _lit(v, line) for k, v in zip(n.keys, n.values)}
    raise UNLError(line, f"valor não suportado ({type(n).__name__}); use números, textos, listas ou nomes")


def _call_args(rest, line):
    try:
        call = ast.parse("f(" + rest + ")", mode="eval").body
    except SyntaxError as e:
        raise UNLError(line, f"sintaxe inválida: {e.msg}")
    return [_lit(a, line) for a in call.args], {k.arg: _lit(k.value, line) for k in call.keywords if k.arg}


def _split_top(rest):
    itens, prof, cur = [], 0, ""
    for ch in rest:
        prof += ch in "([{"
        prof -= ch in ")]}"
        if ch == "," and prof == 0:
            itens.append(cur)
            cur = ""
        else:
            cur += ch
    itens.append(cur)
    return [x.strip() for x in itens if x.strip()]


# ───────────────────────── tipos de verbo (kinds) ─────────────────────────
def _k_text(verb, vs, rest, line):
    v = ast.literal_eval(rest) if rest[:1] in "\"'" else rest
    return Stmt(verb, line, str(v))


def _k_kv(verb, vs, rest, line):
    args, kw = _call_args(rest, line)
    if args or not kw:
        raise UNLError(line, f"{verb} usa 'nome = valor, ...'")
    keys = vs.get("keys")
    if keys and set(kw) - set(keys):
        raise UNLError(line, f"{verb}: chaves inválidas {sorted(set(kw) - set(keys))}; aceitas: {keys}")
    if vs.get("wrap_lists"):
        kw = {k: (v if isinstance(v, list) else [v]) for k, v in kw.items()}
    return Stmt(verb, line, kw)


def _k_solve(verb, vs, rest, line):
    args, kw = _call_args(rest, line)
    if len(args) != 1 or not isinstance(args[0], str):
        raise UNLError(line, f"{verb} nome_do_solver [, opcao = valor]")
    return Stmt(verb, line, {"solver": args[0], "options": kw})


def _k_measure(verb, vs, rest, line):
    d = {}
    for it in _split_top(rest):
        if "=" in it:
            m = re.match(r"^([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)$", it)
            if not m:
                raise UNLError(line, f"{verb}: item inválido {it!r}; use 'alias = medida' ou 'medida'")
            d[m.group(1)] = m.group(2)
        else:
            if not re.match(r"^[A-Za-z_]\w*$", it):
                raise UNLError(line, f"{verb}: item inválido {it!r}; use 'alias = medida' ou 'medida'")
            d[it] = it
    if not d:
        raise UNLError(line, f"{verb} sem itens")
    return Stmt(verb, line, d)


def _k_assign(verb, vs, rest, line):
    m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", rest, flags=re.S)
    if not m:
        raise UNLError(line, f"{verb} nome = expressão")
    return Stmt(verb, line, {"name": m.group(1), "expr": m.group(2).strip()})


def _k_check(verb, vs, rest, line):
    m = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.+)$", rest, flags=re.S)
    if not m:
        raise UNLError(line, f"{verb} nome : comparação")
    return Stmt(verb, line, {"name": m.group(1), "expr": m.group(2).strip()})


def _k_op_call(verb, vs, rest, line):
    m = re.match(r"^([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\((.*)\)$", rest, flags=re.S)
    if not m:
        raise UNLError(line, f"{verb} resultado = operação(parametro = valor, ...)")
    args, kw = _call_args(m.group(3), line)
    if args:
        raise UNLError(line, "use apenas parâmetros nomeados")
    return Stmt(verb, line, {"name": m.group(1), "op": m.group(2), "params": kw})


KINDS = {"text": _k_text, "kv": _k_kv, "solve": _k_solve, "measure": _k_measure,
         "assign_expr": _k_assign, "check": _k_check, "op_call": _k_op_call}


def _parse_stmt(full, line):
    m = re.match(r"^([A-Z]+)\b\s*(.*)$", full, flags=re.S)
    if not m or m.group(1) not in VERB_SPEC:
        raise UNLError(line, f"verbo desconhecido em {full[:40]!r}; use {VERBS}")
    verb, vs, rest = m.group(1), VERB_SPEC[m.group(1)], m.group(2).strip()
    if vs["kind"] not in KINDS:
        raise UNLError(line, f"{verb}: tipo {vs['kind']} não é de statement")
    return KINDS[vs["kind"]](verb, vs, rest, line)


# ───────────────────────── experimento ─────────────────────────
def parse(text, tolerant=True):
    avisos = []
    if tolerant:
        text, avisos = normalize(text)
    stmts, name, state, buf = [], None, "out", None
    for n, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if state == "out":
            m = re.match(r"^EXPERIMENT\s+([A-Za-z_]\w*)\s*\{$", line)
            if not m:
                raise UNLError(n, "esperado 'EXPERIMENT Nome {'")
            name, state = m.group(1), "in"
            continue
        if state == "done":
            raise UNLError(n, "conteúdo depois do fechamento '}' (apenas um EXPERIMENT por arquivo)")
        if buf is not None:
            buf[1] += " " + line
            if _depth(buf[1]) <= 0:
                stmts.append(_parse_stmt(buf[1], buf[0]))
                buf = None
            continue
        if line == "}":
            state = "done"
            continue
        if _depth(line) > 0:
            buf = [n, line]
        else:
            stmts.append(_parse_stmt(line, n))
    if state == "out":
        raise UNLError(0, "nenhum bloco EXPERIMENT encontrado")
    if state != "done" or buf is not None:
        raise UNLError(0, "bloco EXPERIMENT não foi fechado com '}'")
    return Experiment(name, stmts, text, avisos)


def extract_from_markdown(text):
    m = re.search(r"```(?:unl|unit-l)\s*\n(.*?)```", text, flags=re.S | re.I)
    return m.group(1).strip() if m else None
