# versao: 11
# inicio/30_aop.py — AOP-DSL estrutural: toda execução passa por aqui
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 9 · AOP-DSL ESTRUTURAL NO LABORATÓRIO
#
# Toda execução (código de LLM, pipeline, teste, script pronto) passa por aqui:
#   PREFLIGHT  → spec válida? capacidades existem? AST sem chamadas/módulos proibidos? imports lib.* permitidos?
#   EXECUÇÃO   → executar() (isolado)
#   POSTFLIGHT → reverificação Zero-Trust: relê escalares e cada NPZ do disco e aplica VERIFICATION/CONSTRAINT.
# Não existe caminho da interface até o executor que não passe por executar_gated().
# ═══════════════════════════════════════════════════════════════
import importlib
importlib.invalidate_caches()
from lib.framework import aop_dsl, registry as FWR
from lib.framework.specs import DEFAULT_SPEC

AOP = {"texto": None, "nome": None}
PENDING_FILES = {}
PROGRESS = {"ultimo_len": 0}                      # arquivos extras (ex.: experiment.unl) gravados na pasta do próximo run
EXPERIMENTOS_DIR = BASE / "experimentos"
EXPERIMENTOS_DIR.mkdir(parents=True, exist_ok=True)


def aop_ativar(texto, nome):
    """Valida e ativa uma especificação. Levanta AOPSyntaxError/AOPViolation se inválida."""
    spec = aop_dsl.parse(texto)
    rt = aop_dsl.AOPRuntime(spec)
    achados = rt.preflight_spec()
    if aop_dsl.has_fail(achados):
        raise aop_dsl.AOPViolation(achados)
    AOP.update(texto=texto, nome=nome)
    return achados


def aop_carregar(nome):
    p = SPECS_DIR / f"{nome}.aop"
    if not p.exists():
        raise FileNotFoundError(f"spec {nome!r} não existe em {SPECS_DIR}")
    return aop_ativar(p.read_text(encoding="utf-8"), nome)


def aop_runtime():
    return aop_dsl.AOPRuntime(aop_dsl.parse(AOP["texto"]))


def executar_gated(codigo, run_dir, timeout=600):
    run_dir = Path(run_dir)
    (run_dir / "spec.aop").write_text(AOP["texto"], encoding="utf-8")
    for _nome, _txt in list(PENDING_FILES.items()):
        (run_dir / _nome).write_text(_txt, encoding="utf-8")
    PENDING_FILES.clear()
    try:
        rt = aop_runtime()
        pre = rt.preflight_spec() + rt.preflight_code(codigo)
    except aop_dsl.AOPSyntaxError as e:
        pre = [("FALHA", "aop:sintaxe", str(e))]
    if aop_dsl.has_fail(pre):
        msg = "AOP preflight BLOQUEOU a execução:\n" + "\n".join(f"  ✗ {n}: {d}" for lv, n, d in pre if lv == "FALHA")
        (run_dir / "stdout.txt").write_text("", encoding="utf-8")
        (run_dir / "stderr.txt").write_text(msg, encoding="utf-8")
        return {"stdout": "", "stderr": msg, "returncode": -2, "timeout": False, "duracao_s": 0.0, "lib_hashes": {},
                "limite_memoria_gb": LIMITE_MEMORIA_GB, "integridade": {}, "aop_preflight": pre, "aop_bloqueado": True}
    res = executar(codigo, run_dir, timeout=timeout)
    res["aop_preflight"] = pre
    return res


def aop_hook(out, run_dir, rj, res):
    checks = list(res.get("aop_preflight") or [])
    try:
        checks += aop_runtime().verify_run(run_dir, rj, out)
    except Exception as e:
        checks.append(("FALHA", "aop:verify_run", f"{type(e).__name__}: {e}"))
    return checks


def aop_aplicar_agente():
    """AGENT da spec manda na política de autocorreção do laboratório."""
    global MAX_AUTOCORRECOES
    ag = aop_runtime().agent()
    MAX_AUTOCORRECOES = int(ag.get("max_retries", 2))
    return bool(ag.get("allow_autocorrect", True))


# experimentos de referência (UNIT-L) — nunca sobrescreve os seus
from lib.framework import unl_examples as _ux
for _n, _t in (("T2_convergencia", _ux.T2_CONVERGENCIA), ("T2_leve", _ux.T2_LEVE)):
    if not (EXPERIMENTOS_DIR / f"{_n}.unl").exists():
        (EXPERIMENTOS_DIR / f"{_n}.unl").write_text(_t, encoding="utf-8")

# spec padrão: grava em specs/ (sem sobrescrever a do usuário) e ativa
_p = SPECS_DIR / "unit001_padrao.aop"
if not _p.exists():
    _p.write_text(DEFAULT_SPEC, encoding="utf-8")
aop_carregar("unit001_padrao")
print("AOP-DSL estrutural: ATIVO | spec:", AOP["nome"], "| sha256", aop_dsl.parse(AOP["texto"]).sha256[:12])
print("Registros:", {k: len(v) for k, v in FWR.catalog().items()}, "| plugins:", FWR.load_plugins())
