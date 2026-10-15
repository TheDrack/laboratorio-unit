"""
registry.py — registros padronizados do framework UNIT-001.

Tudo que o laboratório "conhece" (solvers, provedores de geometria, campos derivados,
testes, verificadores) é registrado aqui por decorador. Para ADICIONAR algo basta criar
um arquivo em lib/framework/plugins/ (veja plugins/_exemplo.py); nada mais precisa mudar.
"""
FRAMEWORK_VERSION = 11

import importlib
import traceback
from pathlib import Path


class Registry:
    def __init__(self, kind):
        self.kind = kind
        self._items = {}
        self._meta = {}
        self.overrides = []

    def register(self, name=None, **meta):
        def deco(obj):
            n = name or obj.__name__
            if n in self._items and self._items[n] is not obj and getattr(self._items[n], "__module__", None) != getattr(obj, "__module__", None):
                self.overrides.append(n)
            self._items[n] = obj
            self._meta[n] = meta
            return obj
        return deco

    def get(self, name):
        if name not in self._items:
            raise KeyError(f"{self.kind} '{name}' não registrado. Disponíveis: {sorted(self._items)}")
        return self._items[name]

    def has(self, name):
        return name in self._items

    def names(self):
        return sorted(self._items)

    def meta(self, name):
        return dict(self._meta.get(name, {}))


SOLVERS = Registry("solver")
GEOMETRIES = Registry("provedor de geometria")
FIELDS = Registry("campo")
TESTS = Registry("teste")
VERIFIERS = Registry("verificador")
# --- registros da linguagem de experimentos (UNIT-L)
PARAMS = Registry("parâmetro")
MEASURES = Registry("medida")
COMPARATORS = Registry("comparador")
ANALYZERS = Registry("analisador")


def solver(name, **meta):
    return SOLVERS.register(name, **meta)


def geometry_provider(name, **meta):
    return GEOMETRIES.register(name, **meta)


def field(name, requires=(), provides=(), **meta):
    return FIELDS.register(name, requires=tuple(requires), provides=tuple(provides), **meta)


def test(name, description="", **meta):
    return TESTS.register(name, description=description, **meta)


def verifier(name, **meta):
    return VERIFIERS.register(name, **meta)


def param(name, type="float", kind="physical", required=False, unit="", description=""):
    """Parâmetro que FIX/VARY podem usar. kind='numerical' (resolução...) exige invariância física entre níveis."""
    return PARAMS.register(name, type=type, kind=kind, required=required, unit=unit, description=description)(lambda: None)


def measure(name, fields=("em_solve",), unit="1", description=""):
    """Medida: f(ctx_do_caso) -> float. 'fields' = campos do grafo que precisam ter rodado."""
    return MEASURES.register(name, fields=tuple(fields), unit=unit, description=description)


def comparator(name, params=None, description=""):
    """COMPARE: f(rows, p, info) -> {"rows": [...], "scalars": {...}}. params: {nome: (tipo, obrigatório, descrição)}."""
    return COMPARATORS.register(name, params=params or {}, description=description)


def analyzer(name, params=None, description=""):
    return ANALYZERS.register(name, params=params or {}, description=description)


_LOADED = {"builtins": False, "plugins": None}


def load_builtins():
    if not _LOADED["builtins"]:
        for mod in ("builtin_core", "builtin_verifiers", "builtin_tests", "builtin_experiment"):
            importlib.import_module(f"lib.framework.{mod}")
        _LOADED["builtins"] = True


def load_plugins(force=False):
    """Importa lib/framework/plugins/*.py (exceto os que começam com _). Erros não derrubam o laboratório."""
    if _LOADED["plugins"] is not None and not force:
        return _LOADED["plugins"]
    out = {"loaded": [], "errors": {}}
    pdir = Path(__file__).parent / "plugins"
    for p in sorted(pdir.glob("*.py")):
        if p.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"lib.framework.plugins.{p.stem}")
            importlib.reload(mod)
            out["loaded"].append(p.stem)
        except Exception:
            out["errors"][p.stem] = traceback.format_exc(limit=3)
    _LOADED["plugins"] = out
    return out


def ensure_loaded(force_plugins=False):
    load_builtins()
    return load_plugins(force=force_plugins)


def catalog():
    ensure_loaded()
    return {r.kind: {n: r.meta(n) for n in r.names()} for r in (SOLVERS, GEOMETRIES, FIELDS, TESTS, VERIFIERS, PARAMS, MEASURES, COMPARATORS, ANALYZERS)}
