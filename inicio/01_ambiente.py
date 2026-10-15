# versao: 11
# inicio/01_ambiente.py — ambiente, chaves e integrações
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

_BASE_BOOTSTRAP = BASE   # o bootstrap já definiu o caminho do Drive: preservar
# ═══════════════════════════════════════════════════════════════
# CÉLULA 1 · SETUP E CONFIGURAÇÃO — UNIT-001 LAB V2
# ═══════════════════════════════════════════════════════════════

import os
import sys
import re
import json
import time
import ast
import hashlib
import subprocess
import difflib
import math
import shutil
import platform
import datetime as dt

from pathlib import Path

import requests


# ═══════════════════════════════════════════════════════════════
# 1. AMBIENTE
# ═══════════════════════════════════════════════════════════════

try:
    from google.colab import userdata, drive
    EM_COLAB = True
except ImportError:
    EM_COLAB = False


def segredo(nome):
    """
    Obtém segredo preferencialmente do Colab Secrets,
    depois das variáveis de ambiente.
    """
    valor = None

    if EM_COLAB:
        try:
            valor = userdata.get(nome)
        except Exception:
            valor = None

    return valor or os.environ.get(nome) or None


# ═══════════════════════════════════════════════════════════════
# 2. CHAVES / INTEGRAÇÕES
# ═══════════════════════════════════════════════════════════════

KEYS = {
    "openrouter": segredo("OPENROUTER_API_KEY"),
    "gemini":     segredo("GEMINI_API_KEY"),
    "groq":       segredo("GROQ_API_KEY"),
}

TELEGRAM_TOKEN = segredo("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = segredo("TELEGRAM_CHAT_ID")


# ═══════════════════════════════════════════════════════════════
# 3. PROJETO UNIT-001
# ═══════════════════════════════════════════════════════════════

PROJECT = "UNIT-001"

USAR_DRIVE = True

# True  → cria UNIT-001_AGENTES se a pasta ainda não existir
#         (primeira sessão no Colab).
# False → falha se o caminho estiver errado, para não mascarar
#         um Drive montado no lugar incorreto.
CRIAR_ESTRUTURA_SE_AUSENTE = True


if EM_COLAB and USAR_DRIVE:

    # Monta o Google Drive.
    drive.mount(
        "/content/drive",
        force_remount=False,
    )

    DRIVE_NB = (
        Path("/content/drive/MyDrive")
        / "Colab Notebooks"
    )

    BASE = (
        DRIVE_NB
        / "UNIT-001_AGENTES"
    )

else:

    DRIVE_NB = (
        Path.cwd()
        / "Colab Notebooks"
    )

    BASE = (
        Path.cwd()
        / "UNIT-001_AGENTES"
    )


# ═══════════════════════════════════════════════════════════════
# 4. ARQUITETURA OFICIAL
# ═══════════════════════════════════════════════════════════════
#
# UNIT-001_AGENTES/
#
# ├── lib/
# │   ├── config/
# │   ├── core/
# │   ├── geometry/
# │   ├── solvers/
# │   ├── adapters/
# │   ├── coupling/
# │   ├── validation/
# │   └── research/
# │
# ├── scripts_prontos/
# │
# ├── dados/
# │   └── UNIT001/
# │       ├── geometria/
# │       ├── resultados/
# │       │   ├── extrator/
# │       │   │   └── cases/
# │       │   ├── fdfd/
# │       │   ├── fdtd/
# │       │   └── termico/
# │       └── analises/
# │
# ├── validacao/
# ├── docs/
# ├── runs/
# └── decisoes.jsonl
#
# NÃO usar:
#
#   UNIT-001/WORK
#   UNIT-001_WORK
#   resultados_geometrias/
#   casos_individuais/
#
# ═══════════════════════════════════════════════════════════════


# Biblioteca científica oficial.
LIB = BASE / "lib"

# Scripts executáveis oficiais.
SCRIPTS_DIR = BASE / "scripts_prontos"

# Dados do experimento UNIT-001.
DATA_ROOT = (
    BASE
    / "dados"
    / "UNIT001"
)

# Resultados.
RESULTS_DIR = (
    DATA_ROOT
    / "resultados"
)

# Resultados do extrator.
EXTRACTOR_RESULTS_DIR = (
    RESULTS_DIR
    / "extrator"
)

# Casos NPZ oficiais.
CASES_PATH = (
    EXTRACTOR_RESULTS_DIR
    / "cases"
)

# Resultados específicos.
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

SPECS_DIR = BASE / "specs"          # especificações AOP-DSL (.aop)
GEOMETRY_DIR = DATA_ROOT / "geometria"   # catálogo canônico de geometrias

# Análises.
ANALYSIS_DIR = (
    DATA_ROOT
    / "analises"
)

# Validação.
VALIDATION_DIR = (
    BASE
    / "validacao"
    / "relatorios"
)

# Documentação.
DOCS_DIR = (
    BASE
    / "docs"
)

# Execuções isoladas do laboratório.
RUNS = (
    BASE
    / "runs"
)

# Registro de decisões.
DECISOES = (
    BASE
    / "decisoes.jsonl"
)

# Mapa/auditoria.
MAP_DIR = (
    BASE
    / "_mapa"
)


# ═══════════════════════════════════════════════════════════════
# 5. VALIDAR PROJETO
# ═══════════════════════════════════════════════════════════════

if not BASE.exists():
    if CRIAR_ESTRUTURA_SE_AUSENTE:
        BASE.mkdir(parents=True, exist_ok=True)
        print("AVISO: pasta do projeto não existia.")
        print("Estrutura nova criada em:")
        print(" ", BASE.resolve())
        print("Se o Drive já tinha o projeto noutro caminho,")
        print("pare e ajuste BASE / USAR_DRIVE.")
    else:
        raise FileNotFoundError(
            "\n"
            "Projeto UNIT-001_AGENTES não encontrado.\n\n"
            f"Esperado em:\n"
            f"  {BASE}\n\n"
            "A Célula 1 não cria um projeto novo silenciosamente, "
            "pois isso poderia mascarar um caminho incorreto.\n"
            "Defina CRIAR_ESTRUTURA_SE_AUSENTE = True para criar."
        )


# ═══════════════════════════════════════════════════════════════
# 6. CRIAR DIRETÓRIOS OPERACIONAIS
# ═══════════════════════════════════════════════════════════════

DIRETORIOS = [
    LIB,
    SCRIPTS_DIR,
    DATA_ROOT,
    RESULTS_DIR,
    EXTRACTOR_RESULTS_DIR,
    CASES_PATH,
    FDFD_RESULTS_DIR,
    FDTD_RESULTS_DIR,
    THERMAL_RESULTS_DIR,
    SPECS_DIR,
    GEOMETRY_DIR,
    ANALYSIS_DIR,
    VALIDATION_DIR,
    DOCS_DIR,
    RUNS,
    MAP_DIR,
]

for diretorio in DIRETORIOS:
    diretorio.mkdir(
        parents=True,
        exist_ok=True,
    )


# ═══════════════════════════════════════════════════════════════
# 7. GARANTIR PACOTES PYTHON
# ═══════════════════════════════════════════════════════════════
#
# Isso é importante para:
#
#     from lib.solvers.fdfd3d import ...
#
# funcionar também no ambiente isolado dos runs.
# ═══════════════════════════════════════════════════════════════

PACOTES_PYTHON = [
    LIB,
    LIB / "config",
    LIB / "core",
    LIB / "geometry",
    LIB / "solvers",
    LIB / "adapters",
    LIB / "coupling",
    LIB / "validation",
    LIB / "research",
    LIB / "framework",
    LIB / "framework" / "plugins",
]

for pacote in PACOTES_PYTHON:

    pacote.mkdir(
        parents=True,
        exist_ok=True,
    )

    init_file = pacote / "__init__.py"

    if not init_file.exists():

        init_file.write_text(
            "",
            encoding="utf-8",
        )


# ═══════════════════════════════════════════════════════════════
# 8. PYTHONPATH DO PROJETO
# ═══════════════════════════════════════════════════════════════
#
# A raiz correta é:
#
#     UNIT-001_AGENTES/
#
# e NÃO:
#
#     UNIT-001_AGENTES/lib/
#
# porque os imports oficiais são:
#
#     from lib.solvers.fdfd3d import ...
#
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT_STR = str(
    BASE.resolve()
)

PYTHONPATH_ATUAL = os.environ.get(
    "PYTHONPATH",
    "",
)

PYTHONPATH_PARTES = [
    PROJECT_ROOT_STR
]

if PYTHONPATH_ATUAL:

    partes_existentes = [
        p
        for p in PYTHONPATH_ATUAL.split(
            os.pathsep
        )
        if p
    ]

    for parte in partes_existentes:

        if parte not in PYTHONPATH_PARTES:
            PYTHONPATH_PARTES.append(parte)


os.environ["PYTHONPATH"] = os.pathsep.join(
    PYTHONPATH_PARTES
)


if PROJECT_ROOT_STR not in sys.path:

    sys.path.insert(
        0,
        PROJECT_ROOT_STR,
    )


# ═══════════════════════════════════════════════════════════════
# 9. VARIÁVEIS DE AMBIENTE UNIT-001
# ═══════════════════════════════════════════════════════════════

os.environ["UNIT001_PROJECT_ROOT"] = (
    str(BASE.resolve())
)

os.environ["UNIT001_LIB"] = (
    str(LIB.resolve())
)

os.environ["UNIT001_SCRIPTS_DIR"] = (
    str(SCRIPTS_DIR.resolve())
)

os.environ["UNIT001_DATA_ROOT"] = (
    str(DATA_ROOT.resolve())
)

os.environ["UNIT001_RESULTS_DIR"] = (
    str(RESULTS_DIR.resolve())
)

os.environ["UNIT001_CASES_DIR"] = (
    str(CASES_PATH.resolve())
)

os.environ["UNIT001_RUNS_DIR"] = (
    str(RUNS.resolve())
)

os.environ["UNIT001_SPECS_DIR"] = str(SPECS_DIR.resolve())
os.environ["UNIT001_GEOMETRY_DIR"] = str(GEOMETRY_DIR.resolve())


# ═══════════════════════════════════════════════════════════════
# 10. COMPATIBILIDADE COM O EXECUTOR
# ═══════════════════════════════════════════════════════════════
#
# Mantemos CASES_DIR como string porque partes antigas do
# laboratório podem esperar esse formato.
#
# A fonte oficial, entretanto, é CASES_PATH.
# ═══════════════════════════════════════════════════════════════

CASES_DIR = str(
    CASES_PATH.resolve()
)


# ═══════════════════════════════════════════════════════════════
# 11. VERIFICAÇÃO DA BIBLIOTECA
# ═══════════════════════════════════════════════════════════════

ARQUIVOS_LIB = sorted(
    p
    for p in LIB.rglob("*.py")
    if "__pycache__" not in p.parts
)

ARQUIVOS_SCRIPTS = sorted(
    p
    for p in SCRIPTS_DIR.glob("*.py")
    if not p.name.startswith("_")
)

ARQUIVOS_CASES = sorted(
    CASES_PATH.glob("*.npz")
)


# ═══════════════════════════════════════════════════════════════
# 12. HASH DA BIBLIOTECA
# ═══════════════════════════════════════════════════════════════

def sha256_arquivo(path):
    """
    Calcula SHA-256 de um arquivo.
    """

    h = hashlib.sha256()

    with open(
        path,
        "rb",
    ) as arquivo:

        for bloco in iter(
            lambda: arquivo.read(1024 * 1024),
            b"",
        ):

            h.update(bloco)

    return h.hexdigest()


def hash_biblioteca():

    resultado = {}

    for path in ARQUIVOS_LIB:

        relativo = path.relative_to(
            BASE
        )

        resultado[
            str(relativo)
        ] = sha256_arquivo(path)

    return resultado


HASH_LIB_INICIAL = hash_biblioteca()


# ═══════════════════════════════════════════════════════════════
# 13. EXECUTOR — CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════

# Limite de memória do script gerado (GB).
# None = sem limite.
LIMITE_MEMORIA_GB = 8


# ═══════════════════════════════════════════════════════════════
# 14. VALIDAÇÃO
# ═══════════════════════════════════════════════════════════════

# Faixas aceitáveis para escalares do UNIT_RESULT_JSON.
#
# VAZIO por padrão.
#
# Os limites são decisão do pesquisador.
#
# Exemplo:
#
# LIMITES_ESCALARES = {
#     "residuo_energia_rel": (None, 1e-6),
#     "A": (0.0, 1.0),
# }

LIMITES_ESCALARES = {}


# ═══════════════════════════════════════════════════════════════
# 15. PAPEIS DOS AGENTES
# ═══════════════════════════════════════════════════════════════

# Papéis LLM: agora DESCOBERTOS automaticamente (Célula 3). Para fixar manualmente: PAPEIS_FIXOS['codificador']=[('gemini','nome')]


# ═══════════════════════════════════════════════════════════════
# 16. FUNÇÃO DE DIAGNÓSTICO
# ═══════════════════════════════════════════════════════════════

def diagnostico_setup():

    print()
    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    print(
        " UNIT-001 | LABORATÓRIO MULTIAGENTE V2 | SETUP"
    )
    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    print()
    print(
        "Ambiente:",
        "Colab" if EM_COLAB else "local",
    )

    print(
        "Projeto:",
        BASE.resolve(),
    )

    print(
        "Biblioteca:",
        LIB.resolve(),
    )

    print(
        "Scripts oficiais:",
        SCRIPTS_DIR.resolve(),
    )

    print(
        "Dados:",
        DATA_ROOT.resolve(),
    )

    print(
        "Casos:",
        CASES_PATH.resolve(),
    )

    print(
        "Runs:",
        RUNS.resolve(),
    )

    print()

    print(
        "Biblioteca:",
        len(ARQUIVOS_LIB),
        "arquivos Python",
    )

    print(
        "Scripts prontos:",
        len(ARQUIVOS_SCRIPTS),
    )

    print(
        "Casos NPZ:",
        len(ARQUIVOS_CASES),
    )

    print()

    print(
        "PYTHONPATH raiz:",
        PROJECT_ROOT_STR,
    )

    print()

    print(
        "Chaves encontradas:",
        [
            k
            for k, v in KEYS.items()
            if v
        ]
        or "NENHUMA",
    )

    print(
        "Telegram:",
        (
            "configurado"
            if TELEGRAM_TOKEN
            and TELEGRAM_CHAT_ID
            else "desligado"
        ),
    )

    print()

    print(
        "Arquitetura antiga:"
    )

    referencias_antigas = [
        "UNIT-001/WORK",
        "UNIT-001_WORK",
        "resultados_geometrias/",
        "casos_individuais/",
    ]

    for referencia in referencias_antigas:
        print(
            "  NÃO USAR:",
            referencia,
        )

    print()

    print(
        "Arquitetura atual:"
    )

    print(
        "  OK  lib/ recursiva"
    )

    print(
        "  OK  scripts_prontos/"
    )

    print(
        "  OK  dados/UNIT001/"
    )

    print(
        "  OK  resultados/extrator/cases/"
    )

    print(
        "  OK  runs/"
    )

    print()

    if ARQUIVOS_CASES:

        print(
            "Primeiros casos:"
        )

        for caso in ARQUIVOS_CASES[:10]:

            print(
                "  -",
                caso.name,
            )

    else:

        print(
            "⚠ Nenhum .npz encontrado em:"
        )

        print(
            f"  {CASES_PATH}"
        )

    print()

    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ═══════════════════════════════════════════════════════════════
# 17. EXECUTAR DIAGNÓSTICO
# ═══════════════════════════════════════════════════════════════

diagnostico_setup()

BASE = _BASE_BOOTSTRAP   # não deixar a detecção local trocar o caminho
