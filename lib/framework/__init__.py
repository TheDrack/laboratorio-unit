"""lib.framework — pipeline padronizado UNIT-001 (registros + AOP-DSL + casos automáticos)."""
from lib.framework.registry import (FRAMEWORK_VERSION, SOLVERS, GEOMETRIES, FIELDS, TESTS, VERIFIERS,  # noqa: F401
                                    solver, geometry_provider, field, test, verifier, ensure_loaded, catalog,
                                    PARAMS, MEASURES, COMPARATORS, ANALYZERS, param, measure, comparator, analyzer)
