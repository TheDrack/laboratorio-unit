"""
UNIT-001 — caminhos oficiais do projeto.

Este módulo centraliza caminhos de código, dados e resultados.
Não contém lógica científica.
"""

from pathlib import Path
import os


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]


DATA_ROOT = (
    PROJECT_ROOT
    / "dados"
    / "UNIT001"
)


GEOMETRY_DIR = (
    DATA_ROOT
    / "geometria"
)


RESULTS_DIR = (
    DATA_ROOT
    / "resultados"
)


EXTRACTOR_RESULTS_DIR = (
    RESULTS_DIR
    / "extrator"
)


EXTRACTOR_CASES_DIR = (
    EXTRACTOR_RESULTS_DIR
    / "cases"
)


FDFD_RESULTS_DIR = (
    RESULTS_DIR
    / "fdfd"
)


FDTD_RESULTS_DIR = (
    RESULTS_DIR
    / "fdtd"
)


THERMAL_RESULTS_DIR = (
    RESULTS_DIR
    / "termico"
)


ANALYSIS_DIR = (
    DATA_ROOT
    / "analises"
)


VALIDATION_DIR = (
    PROJECT_ROOT
    / "validacao"
    / "relatorios"
)


DOCS_DIR = (
    PROJECT_ROOT
    / "docs"
)


# Permite sobrescrever o diretório de dados quando necessário.
#
# Exemplo:
#
#   export UNIT_DATA_DIR=/algum/outro/local
#
# Por padrão, usa dados/UNIT001 dentro do projeto.

UNIT_DATA_DIR = Path(
    os.environ.get(
        "UNIT_DATA_DIR",
        str(DATA_ROOT),
    )
).expanduser().resolve()


def ensure_project_directories() -> None:
    """Cria os diretórios oficiais de dados."""
    
    directories = [
        UNIT_DATA_DIR,
        UNIT_DATA_DIR / "geometria",
        UNIT_DATA_DIR / "resultados",
        UNIT_DATA_DIR / "resultados" / "extrator",
        UNIT_DATA_DIR / "resultados" / "extrator" / "cases",
        UNIT_DATA_DIR / "resultados" / "fdfd",
        UNIT_DATA_DIR / "resultados" / "fdtd",
        UNIT_DATA_DIR / "resultados" / "termico",
        UNIT_DATA_DIR / "analises",
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
