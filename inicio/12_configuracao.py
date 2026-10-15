# versao: 11
# inicio/12_configuracao.py — configuração e tipos
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# -*- coding: utf-8 -*-

"""
===============================================================================
UNIT-001 · LABORATÓRIO MULTI-AGENTE
===============================================================================

Arquitetura operacional:

    DIREÇÃO CIENTÍFICA
        |
        v
    CODIFICADOR
        |
        v
    REVISOR TÉCNICO
        |
        v
    CÓDIGO APROVADO
        |
        v
    EXECUTOR ISOLADO
        |
        +---- stdout
        +---- stderr
        +---- artefatos
        |
        v
    VALIDADOR DETERMINÍSTICO
        |
        v
    RELATOR
        |
        v
    PACOTE EXPERIMENTAL
        |
        v
    USUÁRIO + IAs AVANÇADAS
        |
        +---- restrição experimental
        +---- hipótese
        +---- interpretação
               |
               +--> somente restrições retornam ao Codificador


PRINCÍPIO EPISTEMOLÓGICO
------------------------

Os agentes locais NÃO:

    - interpretam resultados;
    - declaram descoberta;
    - dizem que uma hipótese foi confirmada;
    - dizem que uma hipótese foi refutada;
    - transformam correlação em causalidade;
    - alteram automaticamente o protocolo por interpretação própria.

Eles:

    - escrevem código;
    - revisam bugs técnicos;
    - executam;
    - coletam stdout/stderr;
    - organizam resultados;
    - verificam invariantes formais;
    - preservam proveniência.

"PASS" significa apenas:

    "o artefato passou pelas verificações determinísticas definidas."

Não significa:

    "a física está correta."

===============================================================================
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import resource
except ImportError:
    resource = None


# =============================================================================
# 1. CONFIGURAÇÃO
# =============================================================================

LAB_VERSION = "UNIT-001-LAB-v3"

DEFAULT_RUN_ROOT = Path(
    os.environ.get(
        "UNIT_AGENT_RUN_ROOT",
        "unit_agents/runs",
    )
)

DEFAULT_LIBRARY_ROOT = Path(
    os.environ.get(
        "UNIT_AGENT_LIBRARY_ROOT",
        "UNIT-001_WORK",
    )
)

DEFAULT_READY_SCRIPTS_ROOT = Path(
    os.environ.get(
        "UNIT_AGENT_READY_SCRIPTS_ROOT",
        "UNIT-001_AGENTES/scripts_prontos",
    )
)

DEFAULT_TIMEOUT_SECONDS = int(
    os.environ.get("UNIT_AGENT_TIMEOUT", "600")
)

DEFAULT_MEMORY_GB = float(
    os.environ.get("LIMITE_MEMORIA_GB", "4")
)

# Limites escalares começam vazios de propósito.
# O laboratório NÃO inventa tolerâncias físicas.
LIMITES_ESCALARES: Dict[str, Dict[str, float]] = {}


# =============================================================================
# 2. ENUMS
# =============================================================================

class AgentRole(str, Enum):
    CODIFICADOR = "codificador"
    REVISOR = "revisor"
    EXECUTOR = "executor"
    RELATOR = "relator"
    VALIDATOR = "validador"
    OPERADOR = "operador"


class OpinionType(str, Enum):
    RESTRICAO = "restricao"
    HIPOTESE = "hipotese"
    INTERPRETACAO = "interpretacao"


class ExecutionStatus(str, Enum):
    NAO_EXECUTADO = "nao_executado"
    EXECUTANDO = "executando"
    SUCESSO = "sucesso"
    ERRO = "erro"
    TIMEOUT = "timeout"


class ValidationStatus(str, Enum):
    NAO_VALIDADO = "nao_validado"
    PASS = "PASS"
    FAIL = "FAIL"
    NAO_APLICAVEL = "N/A"


class ReviewStatus(str, Enum):
    NAO_REVISADO = "nao_revisado"
    APROVADO = "aprovado"
    REPROVADO = "reprovado"


# =============================================================================
# 3. UTILIDADES
# =============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def safe_json(value: Any) -> Any:
    """
    Converte valores comuns para JSON sem destruir informação estrutural.
    """

    if value is None:
        return None

    if is_dataclass(value) and not isinstance(value, type):
        return safe_json(asdict(value))

    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float):
            if math.isnan(value):
                return "NaN"

            if math.isinf(value):
                return "Inf" if value > 0 else "-Inf"

        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Mapping):
        return {
            str(k): safe_json(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [safe_json(v) for v in value]

    if hasattr(value, "item"):
        try:
            return safe_json(value.item())
        except Exception:
            pass

    if hasattr(value, "tolist"):
        try:
            return safe_json(value.tolist())
        except Exception:
            pass

    return repr(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            safe_json(data),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def collect_files(root: Path) -> List[Path]:
    if not root.exists():
        return []

    return sorted(
        p for p in root.rglob("*")
        if p.is_file()
    )


# =============================================================================
# 4. CONTEXTO DO PROJETO
# =============================================================================

@dataclass
class ProjectContext:
    """
    Briefing compartilhado pelos agentes.

    IMPORTANTE:
        PROJECT_CONTEXT descreve o estado operacional conhecido.
        Não deve ser usado para inserir uma conclusão científica
        como se fosse fato.
    """

    project_id: str = "UNIT-001"

    text: str = ""

    updated_at: str = field(
        default_factory=utc_now
    )

    version: int = 1

    def update(
        self,
        text: str,
    ) -> None:

        self.text = text
        self.version += 1
        self.updated_at = utc_now()


# =============================================================================
# 5. RESTRIÇÕES
# =============================================================================

@dataclass
class ExperimentalRestriction:
    """
    Único tipo de parecer externo que pode retornar ao Codificador.

    Exemplo:

        volume_fraction = 0.125
        frequency_thz in [280, 300, 320]
        realizations >= 20

    Uma restrição precisa ser explícita e rastreável.
    """

    restriction_id: str

    statement: str

    source: str

    rationale: str = ""

    parameters: Dict[str, Any] = field(
        default_factory=dict
    )

    active: bool = True

    created_at: str = field(
        default_factory=utc_now
    )


@dataclass
class ExternalOpinion:
    """
    Registro do parecer trazido de fora do laboratório.

    HIPÓTESE e INTERPRETAÇÃO permanecem informativas.
    Não entram automaticamente no contexto do Codificador.
    """

    opinion_id: str

    opinion_type: OpinionType

    text: str

    source: str

    created_at: str = field(
        default_factory=utc_now
    )

    restriction: Optional[ExperimentalRestriction] = None

    warning: str = (
        "Não constitui fato experimental nem instrução operacional."
    )


# =============================================================================
# 6. DIREÇÃO EXPERIMENTAL
# =============================================================================

@dataclass
class ExperimentDirection:
    """
    Direção fornecida pelo usuário / IAs avançadas.

    Não é uma conclusão.
    É a especificação do que deve ser investigado.
    """

    objective: str

    instructions: str

    expected_outputs: List[str] = field(
        default_factory=list
    )

    forbidden_assumptions: List[str] = field(
        default_factory=list
    )

    restrictions: List[ExperimentalRestriction] = field(
        default_factory=list
    )

    created_at: str = field(
        default_factory=utc_now
    )


# =============================================================================
# 7. REGISTRO DE AGENTES
# =============================================================================

@dataclass
class AgentDescriptor:
    agent_id: str

    role: AgentRole

    model: Optional[str] = None

    description: str = ""

    capabilities: List[str] = field(
        default_factory=list
    )


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, AgentDescriptor] = {}

    def register(
        self,
        agent: AgentDescriptor,
    ) -> None:

        if agent.agent_id in self._agents:
            raise ValueError(
                f"Agente já registrado: {agent.agent_id}"
            )

        self._agents[agent.agent_id] = agent

    def get(
        self,
        agent_id: str,
    ) -> AgentDescriptor:

        return self._agents[agent_id]

    def all(self) -> List[AgentDescriptor]:
        return list(self._agents.values())


# =============================================================================
# 8. EVENTOS / AUDITORIA
# =============================================================================

@dataclass
class AgentEvent:
    event_id: str

    timestamp: str

    agent_id: str

    event_type: str

    description: str

    input_refs: List[str] = field(
        default_factory=list
    )

    output_refs: List[str] = field(
        default_factory=list
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =============================================================================
# 9. REVISÃO TÉCNICA
# =============================================================================

@dataclass
class ReviewFinding:
    severity: str

    message: str

    line: Optional[int] = None

    category: str = "technical"


@dataclass
class TechnicalReview:
    status: ReviewStatus

    reviewer_agent: str

    findings: List[ReviewFinding] = field(
        default_factory=list
    )

    summary: str = ""

    created_at: str = field(
        default_factory=utc_now
    )


# =============================================================================
# 10. VALIDAÇÃO DETERMINÍSTICO
# =============================================================================

@dataclass
class ValidationFinding:
    check: str

    status: str

    message: str

    value: Any = None

    limit: Any = None


@dataclass
class ValidationReport:
    status: ValidationStatus

    findings: List[ValidationFinding] = field(
        default_factory=list
    )

    created_at: str = field(
        default_factory=utc_now
    )

    note: str = (
        "Validação formal/determinística. "
        "PASS não implica validade física."
    )


# =============================================================================
# 11. RESULTADO DA EXECUÇÃO
# =============================================================================

@dataclass
class ExecutionResult:
    status: ExecutionStatus

    return_code: Optional[int]

    duration_seconds: float

    stdout_path: str

    stderr_path: str

    artifacts_root: str

    error: Optional[str] = None

    created_at: str = field(
        default_factory=utc_now
    )


# =============================================================================
# 12. RELATÓRIO
# =============================================================================

@dataclass
class ReportRecord:
    """
    Número extraído da saída bruta.

    O Relator não calcula um resultado novo.
    Ele apenas referencia valores existentes.
    """

    key: str

    value: Any

    source: str

    verified_in_raw_output: bool


@dataclass
class RunReport:
    run_id: str

    execution: ExecutionResult

    validation: ValidationReport

    review: TechnicalReview

    records: List[ReportRecord] = field(
        default_factory=list
    )

    generated_at: str = field(
        default_factory=utc_now
    )


# =============================================================================
# 13. PROVENIÊNCIA
# =============================================================================

@dataclass
class Provenance:
    lab_version: str

    run_id: str

    python_version: str

    platform: str

    numpy_version: Optional[str]

    scipy_version: Optional[str]

    matplotlib_version: Optional[str]

    code_hashes: Dict[str, str]

    library_hashes: Dict[str, str]

    generated_by: Optional[str]

    reviewed_by: Optional[str]

    corrected_by: Optional[str]

    reported_by: Optional[str]

    manually_edited: bool

    created_at: str = field(
        default_factory=utc_now
    )


# =============================================================================
# 14. ESTADO DO RUN
# =============================================================================

@dataclass
class RunState:
    run_id: str

    direction: ExperimentDirection

    execution: Optional[ExecutionResult] = None

    review: Optional[TechnicalReview] = None

    validation: Optional[ValidationReport] = None

    report: Optional[RunReport] = None

    provenance: Optional[Provenance] = None

    events: List[AgentEvent] = field(
        default_factory=list
    )

    opinions: List[ExternalOpinion] = field(
        default_factory=list
    )

    created_at: str = field(
        default_factory=utc_now
    )


# =============================================================================
# 15. HASH DA BIBLIOTECA
# =============================================================================

def hash_tree(
    root: Path,
) -> Dict[str, str]:

    result: Dict[str, str] = {}

    if not root.exists():
        return result

    for path in collect_files(root):
        try:
            rel = str(
                path.relative_to(root)
            )
        except ValueError:
            rel = str(path)

        result[rel] = sha256_file(path)

    return result


def compare_hashes(
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> Dict[str, Any]:

    changed = []

    for key in sorted(
        set(before) | set(after)
    ):

        if before.get(key) != after.get(key):
            changed.append(key)

    return {
        "changed": changed,
        "changed_count": len(changed),
        "same": len(changed) == 0,
    }


# =============================================================================
# 16. REVISOR TÉCNICO
# =============================================================================

class TechnicalReviewer:
    """
    Revisor deliberadamente limitado.

    Ele procura problemas técnicos óbvios:
        - sintaxe;
        - imports;
        - sinais de código incompleto;
        - estruturas inválidas.

    Ele NÃO avalia:
        - se a hipótese é verdadeira;
        - se o resultado é interessante;
        - se a física está correta;
        - se existe descoberta.
    """

    def __init__(
        self,
        agent_id: str = "reviewer_local",
    ) -> None:

        self.agent_id = agent_id

    def review(
        self,
        code: str,
    ) -> TechnicalReview:

        findings: List[ReviewFinding] = []

        # ------------------------------------------------------------------
        # Sintaxe
        # ------------------------------------------------------------------

        try:
            tree = ast.parse(code)

        except SyntaxError as exc:

            findings.append(
                ReviewFinding(
                    severity="ERROR",
                    category="syntax",
                    message=str(exc),
                    line=exc.lineno,
                )
            )

            return TechnicalReview(
                status=ReviewStatus.REPROVADO,
                reviewer_agent=self.agent_id,
                findings=findings,
                summary="Código reprovado por erro de sintaxe.",
            )

        # ------------------------------------------------------------------
        # Imports básicos
        # ------------------------------------------------------------------

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for alias in node.names:

                    if not alias.name:
                        findings.append(
                            ReviewFinding(
                                severity="ERROR",
                                message="Import inválido.",
                                line=node.lineno,
                            )
                        )

            elif isinstance(node, ast.ImportFrom):

                if node.module is None:
                    findings.append(
                        ReviewFinding(
                            severity="WARNING",
                            message="Import relativo sem módulo.",
                            line=node.lineno,
                        )
                    )

        # ------------------------------------------------------------------
        # Indicadores de placeholders
        # ------------------------------------------------------------------

        placeholder_patterns = (
            "TODO_IMPLEMENT",
            "IMPLEMENTAR_AQUI",
            "FAKE_PHYSICS",
            "PLACEHOLDER_PHYSICS",
        )

        for index, line in enumerate(
            code.splitlines(),
            start=1,
        ):

            for marker in placeholder_patterns:

                if marker in line:

                    findings.append(
                        ReviewFinding(
                            severity="WARNING",
                            category="placeholder",
                            message=(
                                f"Marcador de placeholder encontrado: "
                                f"{marker}"
                            ),
                            line=index,
                        )
                    )

        has_error = any(
            f.severity == "ERROR"
            for f in findings
        )

        status = (
            ReviewStatus.REPROVADO
            if has_error
            else ReviewStatus.APROVADO
        )

        summary = (
            "Revisão técnica concluída; nenhum erro técnico bloqueante "
            "detectado."
            if not has_error
            else
            "Revisão técnica encontrou problemas bloqueantes."
        )

        return TechnicalReview(
            status=status,
            reviewer_agent=self.agent_id,
            findings=findings,
            summary=summary,
        )


# =============================================================================
# 17. EXECUTOR
# =============================================================================

class IsolatedExecutor:
    """
    Executor operacional.

    O subprocesso recebe:
        - cópia do código;
        - cópia da biblioteca;
        - ambiente reduzido;
        - limite de memória (quando suportado);
        - timeout.

    Ainda pode haver acesso ao sistema/rede dependendo do ambiente.
    """

    def __init__(
        self,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        memory_gb: float = DEFAULT_MEMORY_GB,
    ) -> None:

        self.timeout_seconds = timeout_seconds
        self.memory_gb = memory_gb

    def _minimal_environment(self) -> Dict[str, str]:

        keep = {
            "PATH",
            "PYTHONPATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "TMPDIR",
        }

        env = {
            key: value
            for key, value in os.environ.items()
            if key in keep
        }

        # Impede que credenciais conhecidas sejam propagadas.
        forbidden_suffixes = (
            "API_KEY",
            "TOKEN",
            "SECRET",
            "PASSWORD",
        )

        for key in list(env):

            if any(
                key.upper().endswith(suffix)
                for suffix in forbidden_suffixes
            ):
                env.pop(key, None)

        return env

    def _make_preexec_fn(self):
        if sys.platform == "win32":
            return None

        def preexec():
            os.setsid()

            if resource is not None and self.memory_gb > 0:
                try:
                    bytes_limit = int(self.memory_gb * 1024 * 1024 * 1024)
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (bytes_limit, bytes_limit),
                    )
                except Exception:
                    pass

        return preexec

    def execute(
        self,
        code_path: Path,
        run_dir: Path,
        library_root: Optional[Path] = None,
    ) -> ExecutionResult:

        start = time.monotonic()

        execution_dir = run_dir / "execution"

        execution_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        stdout_path = execution_dir / "stdout.txt"
        stderr_path = execution_dir / "stderr.txt"

        sandbox_code = execution_dir / code_path.name

        shutil.copy2(
            code_path,
            sandbox_code,
        )

        sandbox_library = None

        if library_root and library_root.exists():

            sandbox_library = (
                execution_dir / "library"
            )

            shutil.copytree(
                library_root,
                sandbox_library,
                dirs_exist_ok=True,
            )

        env = self._minimal_environment()

        pythonpath_parts = [
            str(execution_dir)
        ]

        if sandbox_library:
            pythonpath_parts.append(
                str(sandbox_library)
            )

        existing_pythonpath = env.get(
            "PYTHONPATH",
            "",
        )

        if existing_pythonpath:
            pythonpath_parts.append(
                existing_pythonpath
            )

        env["PYTHONPATH"] = os.pathsep.join(
            pythonpath_parts
        )

        command = [
            sys.executable,
            str(sandbox_code),
        ]

        status = ExecutionStatus.ERRO
        return_code: Optional[int] = None
        error: Optional[str] = None

        preexec_fn = self._make_preexec_fn()

        try:

            with stdout_path.open(
                "w",
                encoding="utf-8",
                errors="replace",
            ) as stdout_file, stderr_path.open(
                "w",
                encoding="utf-8",
                errors="replace",
            ) as stderr_file:

                process = subprocess.Popen(
                    command,
                    cwd=str(execution_dir),
                    env=env,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    preexec_fn=preexec_fn if sys.platform != "win32" else None,
                    start_new_session=(sys.platform != "win32"),
                )

                try:

                    return_code = process.wait(
                        timeout=self.timeout_seconds
                    )

                    status = (
                        ExecutionStatus.SUCESSO
                        if return_code == 0
                        else ExecutionStatus.ERRO
                    )

                except subprocess.TimeoutExpired:

                    status = ExecutionStatus.TIMEOUT

                    if sys.platform != "win32":
                        try:
                            os.killpg(
                                os.getpgid(process.pid),
                                signal.SIGTERM,
                            )
                        except Exception:
                            process.kill()
                    else:
                        process.kill()

                    try:
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()

                    error = (
                        f"Timeout após "
                        f"{self.timeout_seconds}s."
                    )

        except Exception as exc:

            status = ExecutionStatus.ERRO

            error = (
                f"{type(exc).__name__}: {exc}"
            )

        duration = time.monotonic() - start

        return ExecutionResult(
            status=status,
            return_code=return_code,
            duration_seconds=duration,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            artifacts_root=str(execution_dir),
            error=error,
        )


# =============================================================================
# 18. VALIDADOR DETERMINÍSTICO
# =============================================================================

class DeterministicValidator:
    """
    Validação sem IA.

    Verifica:

        1. NaN / Inf em stdout;
        2. NaN / Inf em JSON/NPY/NPZ;
        3. limites escalares explicitamente configurados;
        4. integridade básica dos artefatos.

    Não verifica "correção física".
    """

    FLOAT_PATTERN = re.compile(
        r"""
        (?:
            [+-]?
            (?:
                \d+(?:\.\d*)?
                |
                \.\d+
            )
            (?:[eE][+-]?\d+)?
        )
        """,
        re.VERBOSE,
    )

    def __init__(
        self,
        scalar_limits: Optional[
            Mapping[str, Mapping[str, float]]
        ] = None,
    ) -> None:

        self.scalar_limits = (
            dict(scalar_limits or LIMITES_ESCALARES)
        )

    def _contains_bad_float(
        self,
        text: str,
    ) -> bool:

        lowered = text.lower()

        tokens = (
            "nan",
            "+nan",
            "-nan",
            "inf",
            "+inf",
            "-inf",
            "infinity",
            "+infinity",
            "-infinity",
        )

        return any(
            token in lowered
            for token in tokens
        )

    def _validate_text(
        self,
        path: Path,
    ) -> ValidationFinding:

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except Exception as exc:

            return ValidationFinding(
                check="read_text",
                status="FAIL",
                message=(
                    f"Não foi possível ler {path}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        bad = self._contains_bad_float(text)

        return ValidationFinding(
            check=f"nan_inf:{path.name}",
            status="FAIL" if bad else "PASS",
            message=(
                "NaN/Inf encontrado."
                if bad
                else
                "Nenhum NaN/Inf textual encontrado."
            ),
        )

    def _validate_json(
        self,
        path: Path,
    ) -> List[ValidationFinding]:

        findings: List[ValidationFinding] = []

        try:

            data = read_json(path)

        except Exception as exc:

            findings.append(
                ValidationFinding(
                    check=f"json_parse:{path.name}",
                    status="FAIL",
                    message=str(exc),
                )
            )

            return findings

        bad_strings = {
            "nan", "+nan", "-nan",
            "inf", "+inf", "-inf",
            "infinity", "+infinity", "-infinity",
        }

        def walk(
            value: Any,
            location: str,
        ) -> None:

            if isinstance(value, float):

                if not math.isfinite(value):

                    findings.append(
                        ValidationFinding(
                            check=f"json_finite:{path.name}",
                            status="FAIL",
                            message=(
                                f"Valor não finito em {location}."
                            ),
                            value=repr(value),
                        )
                    )

            elif isinstance(value, str):

                if value.lower() in bad_strings:

                    findings.append(
                        ValidationFinding(
                            check=f"json_finite:{path.name}",
                            status="FAIL",
                            message=(
                                f"Representação de NaN/Inf em formato texto em {location}."
                            ),
                            value=value,
                        )
                    )

            elif isinstance(value, dict):

                for key, child in value.items():
                    walk(
                        child,
                        f"{location}.{key}",
                    )

            elif isinstance(value, list):

                for index, child in enumerate(value):
                    walk(
                        child,
                        f"{location}[{index}]",
                    )

        walk(data, "$")

        if not findings:

            findings.append(
                ValidationFinding(
                    check=f"json_finite:{path.name}",
                    status="PASS",
                    message="JSON parseável e sem valores não finitos.",
                )
            )

        return findings

    def _validate_numpy(
        self,
        path: Path,
    ) -> List[ValidationFinding]:

        try:

            import numpy as np

        except Exception as exc:

            return [
                ValidationFinding(
                    check=f"numpy_import:{path.name}",
                    status="FAIL",
                    message=str(exc),
                )
            ]

        findings: List[ValidationFinding] = []

        try:

            if path.suffix == ".npy":

                data = np.load(
                    path,
                    allow_pickle=False,
                )

                arrays = {
                    path.name: data
                }

            else:

                with np.load(path, allow_pickle=False) as loaded:
                    arrays = {
                        key: loaded[key]
                        for key in loaded.files
                    }

            for name, array in arrays.items():

                if np.issubdtype(
                    array.dtype,
                    np.number,
                ):

                    if not np.all(
                        np.isfinite(array)
                    ):

                        findings.append(
                            ValidationFinding(
                                check=f"numpy_finite:{path.name}:{name}",
                                status="FAIL",
                                message=(
                                    "Array contém NaN/Inf."
                                ),
                            )
                        )

            if not any(
                f.status == "FAIL"
                for f in findings
            ):

                findings.append(
                    ValidationFinding(
                        check=f"numpy_finite:{path.name}",
                        status="PASS",
                        message=(
                            "Arrays numéricos sem NaN/Inf."
                        ),
                    )
                )

        except Exception as exc:

            findings.append(
                ValidationFinding(
                    check=f"numpy_read:{path.name}",
                    status="FAIL",
                    message=(
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
            )

        return findings

    def _validate_scalar_limits(
        self,
        stdout_text: str,
    ) -> List[ValidationFinding]:

        findings: List[ValidationFinding] = []

        if not self.scalar_limits:

            findings.append(
                ValidationFinding(
                    check="scalar_limits",
                    status="N/A",
                    message=(
                        "LIMITES_ESCALARES está vazio. "
                        "Nenhum limite foi imposto pelo laboratório."
                    ),
                )
            )

            return findings

        for key, limits in self.scalar_limits.items():

            pattern = re.compile(
                rf"""
                (?P<key>
                    {re.escape(key)}
                )
                \s*[:=]\s*
                (?P<value>
                    [+-]?
                    (?:
                        \d+(?:\.\d*)?
                        |
                        \.\d+
                    )
                    (?:[eE][+-]?\d+)?
                )
                """,
                re.VERBOSE,
            )

            match = pattern.search(stdout_text)

            if not match:

                findings.append(
                    ValidationFinding(
                        check=f"limit:{key}",
                        status="N/A",
                        message=(
                            "Escalar não encontrado no stdout."
                        ),
                    )
                )

                continue

            value = float(
                match.group("value")
            )

            minimum = limits.get("min")
            maximum = limits.get("max")

            ok = True

            if minimum is not None and value < minimum:
                ok = False

            if maximum is not None and value > maximum:
                ok = False

            findings.append(
                ValidationFinding(
                    check=f"limit:{key}",
                    status="PASS" if ok else "FAIL",
                    message=(
                        "Dentro do limite."
                        if ok
                        else
                        "Fora do limite configurado."
                    ),
                    value=value,
                    limit=dict(limits),
                )
            )

        return findings

    def validate(
        self,
        execution: ExecutionResult,
    ) -> ValidationReport:

        if execution.status != ExecutionStatus.SUCESSO:

            return ValidationReport(
                status=ValidationStatus.NAO_APLICAVEL,
                findings=[
                    ValidationFinding(
                        check="execution",
                        status="N/A",
                        message=(
                            "Execução não terminou com sucesso; "
                            "validação física não é inferida."
                        ),
                    )
                ],
            )

        root = Path(
            execution.artifacts_root
        )

        findings: List[ValidationFinding] = []

        stdout_path = Path(
            execution.stdout_path
        )

        if stdout_path.exists():

            findings.append(
                self._validate_text(
                    stdout_path
                )
            )

            stdout_text = stdout_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            findings.extend(
                self._validate_scalar_limits(
                    stdout_text
                )
            )

        else:

            findings.append(
                ValidationFinding(
                    check="stdout_exists",
                    status="FAIL",
                    message="stdout não encontrado.",
                )
            )

        for path in collect_files(root):

            if path.suffix.lower() == ".json":

                if path.name != "provenance.json":

                    findings.extend(
                        self._validate_json(path)
                    )

            elif path.suffix.lower() in (
                ".npy",
                ".npz",
            ):

                findings.extend(
                    self._validate_numpy(path)
                )

        failed = any(
            finding.status == "FAIL"
            for finding in findings
        )

        status = (
            ValidationStatus.FAIL
            if failed
            else
            ValidationStatus.PASS
        )

        return ValidationReport(
            status=status,
            findings=findings,
        )


# =============================================================================
# 19. RELATOR
# =============================================================================

class DeterministicReporter:
    """
    O Relator organiza a evidência.

    Regra:
        nenhum número apresentado na tabela pode existir somente
        na interpretação do Relator.

    Ele precisa existir na saída bruta.
    """

    NUMBER_LINE_PATTERN = re.compile(
        r"""
        ^
        \s*
        (?P<key>
            [A-Za-z_][A-Za-z0-9_.\- ]*
        )
        \s*
        [:=]
        \s*
        (?P<value>
            [+-]?
            (?:
                \d+(?:\.\d*)?
                |
                \.\d+
            )
            (?:[eE][+-]?\d+)?
        )
        \s*
        (?P<unit>.*)?
        $
        """,
        re.VERBOSE,
    )

    def extract_records(
        self,
        stdout: str,
    ) -> List[ReportRecord]:

        records = []

        for line in stdout.splitlines():

            match = self.NUMBER_LINE_PATTERN.match(
                line
            )

            if not match:
                continue

            key = match.group("key").strip()
            raw_value = match.group("value")

            try:
                value: Any = float(raw_value)
            except Exception:
                value = raw_value

            records.append(
                ReportRecord(
                    key=key,
                    value=value,
                    source="stdout",
                    verified_in_raw_output=True,
                )
            )

        return records

    def build(
        self,
        run_id: str,
        execution: ExecutionResult,
        validation: ValidationReport,
        review: TechnicalReview,
    ) -> RunReport:

        stdout_path = Path(
            execution.stdout_path
        )

        stdout = ""

        if stdout_path.exists():

            stdout = stdout_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        records = self.extract_records(
            stdout
        )

        return RunReport(
            run_id=run_id,
            execution=execution,
            validation=validation,
            review=review,
            records=records,
        )


# =============================================================================
# 20. PACOTE EXPERIMENTAL
# =============================================================================

class ExperimentPackageBuilder:

    def build(
        self,
        run_state: RunState,
        run_dir: Path,
        project_context: ProjectContext,
    ) -> Path:

        package_dir = run_dir / "package"

        package_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -------------------------------------------------------------
        # 1. Contexto
        # -------------------------------------------------------------

        write_json(
            package_dir / "project_context.json",
            asdict(project_context),
        )

        # -------------------------------------------------------------
        # 2. Direção
        # -------------------------------------------------------------

        write_json(
            package_dir / "direction.json",
            asdict(run_state.direction),
        )

        # -------------------------------------------------------------
        # 3. Relatório
        # -------------------------------------------------------------

        if run_state.report:

            write_json(
                package_dir / "report.json",
                asdict(run_state.report),
            )

        # -------------------------------------------------------------
        # 4. Validação
        # -------------------------------------------------------------

        if run_state.validation:

            write_json(
                package_dir / "validation.json",
                asdict(run_state.validation),
            )

        # -------------------------------------------------------------
        # 5. Proveniência
        # -------------------------------------------------------------

        if run_state.provenance:

            write_json(
                package_dir / "provenance.json",
                asdict(run_state.provenance),
            )

        # -------------------------------------------------------------
        # 6. Pareceres externos
        # -------------------------------------------------------------

        write_json(
            package_dir / "external_opinions.json",
            [
                asdict(opinion)
                for opinion in run_state.opinions
            ],
        )

        # -------------------------------------------------------------
        # 7. Eventos
        # -------------------------------------------------------------

        write_json(
            package_dir / "agent_events.json",
            [
                asdict(event)
                for event in run_state.events
            ],
        )

        # -------------------------------------------------------------
        # 8. README epistemológico
        # -------------------------------------------------------------

        readme = f"""# UNIT-001 · Pacote experimental

Run: `{run_state.run_id}`

## Regra epistemológica

Este pacote contém evidência operacional produzida pelo laboratório.

Ele NÃO contém um veredito científico automático.

A saída bruta é a fonte primária.

A validação determinística verifica apenas as regras explicitamente
configuradas no laboratório.

`PASS` não significa que a física esteja correta.

## Tipos de parecer externo

- `restricao`: pode retornar ao Codificador.
- `hipotese`: informativo; não vira instrução.
- `interpretacao`: informativo; não vira instrução.

## Artefatos principais

- `direction.json`
- `report.json`
- `validation.json`
- `provenance.json`
- `external_opinions.json`
- `agent_events.json`
"""

        (
            package_dir / "README.md"
        ).write_text(
            readme,
            encoding="utf-8",
        )

        return package_dir


# =============================================================================
# 21. LABORATÓRIO
# =============================================================================

class Unit001Laboratory:

    def __init__(
        self,
        run_root: Path = DEFAULT_RUN_ROOT,
        library_root: Path = DEFAULT_LIBRARY_ROOT,
        ready_scripts_root: Path = DEFAULT_READY_SCRIPTS_ROOT,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        memory_gb: float = DEFAULT_MEMORY_GB,
        scalar_limits: Optional[
            Mapping[str, Mapping[str, float]]
        ] = None,
    ) -> None:

        self.run_root = Path(run_root)

        self.library_root = Path(
            library_root
        )

        self.ready_scripts_root = Path(
            ready_scripts_root
        )

        self.timeout_seconds = timeout_seconds

        self.memory_gb = memory_gb

        self.scalar_limits = dict(
            scalar_limits or LIMITES_ESCALARES
        )

        self.project_context = ProjectContext()

        self.registry = AgentRegistry()

        self.reviewer = TechnicalReviewer()

        self.executor = IsolatedExecutor(
            timeout_seconds=timeout_seconds,
            memory_gb=memory_gb,
        )

        self.validator = DeterministicValidator(
            scalar_limits=self.scalar_limits,
        )

        self.reporter = DeterministicReporter()

        self.package_builder = (
            ExperimentPackageBuilder()
        )

        self._register_default_agents()

    # =========================================================================
    # AGENTES
    # =========================================================================

    def _register_default_agents(
        self,
    ) -> None:

        self.registry.register(
            AgentDescriptor(
                agent_id="codificador",
                role=AgentRole.CODIFICADOR,
                description=(
                    "Transforma direção aprovada em código."
                ),
                capabilities=[
                    "write_code",
                    "apply_restrictions",
                ],
            )
        )

        self.registry.register(
            AgentDescriptor(
                agent_id="revisor",
                role=AgentRole.REVISOR,
                description=(
                    "Procura bugs técnicos no código."
                ),
                capabilities=[
                    "technical_review",
                ],
            )
        )

        self.registry.register(
            AgentDescriptor(
                agent_id="executor",
                role=AgentRole.EXECUTOR,
                description=(
                    "Executa código isoladamente."
                ),
                capabilities=[
                    "execute",
                ],
            )
        )

        self.registry.register(
            AgentDescriptor(
                agent_id="relator",
                role=AgentRole.RELATOR,
                description=(
                    "Organiza os resultados sem interpretação."
                ),
                capabilities=[
                    "report",
                ],
            )
        )

        self.registry.register(
            AgentDescriptor(
                agent_id="validador",
                role=AgentRole.VALIDATOR,
                description=(
                    "Executa verificações determinísticas."
                ),
                capabilities=[
                    "validate",
                ],
            )
        )

    # =========================================================================
    # PROJECT CONTEXT
    # =========================================================================

    def update_project_context(
        self,
        text: str,
    ) -> None:

        self.project_context.update(
            text
        )

    # =========================================================================
    # RUN ID
    # =========================================================================

    def _next_run_id(
        self,
    ) -> str:

        self.run_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        numbers = []

        for path in self.run_root.glob(
            "run_*"
        ):

            match = re.fullmatch(
                r"run_(\d+)",
                path.name,
            )

            if match:
                numbers.append(
                    int(match.group(1))
                )

        next_number = (
            max(numbers) + 1
            if numbers
            else 1
        )

        return f"run_{next_number:03d}"

    # =========================================================================
    # EVENT
    # =========================================================================

    def _event(
        self,
        run_state: RunState,
        agent_id: str,
        event_type: str,
        description: str,
        input_refs: Optional[List[str]] = None,
        output_refs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:

        event_number = len(
            run_state.events
        ) + 1

        run_state.events.append(
            AgentEvent(
                event_id=(
                    f"{run_state.run_id}-"
                    f"event-{event_number:03d}"
                ),
                timestamp=utc_now(),
                agent_id=agent_id,
                event_type=event_type,
                description=description,
                input_refs=input_refs or [],
                output_refs=output_refs or [],
                metadata=metadata or {},
            )
        )

    # =========================================================================
    # CODE PREPARATION
    # =========================================================================

    def _prepare_code(
        self,
        code: str,
        run_dir: Path,
        filename: str = "experiment.py",
    ) -> Path:

        if not filename.endswith(".py"):
            filename += ".py"

        code_path = (
            run_dir / filename
        )

        code_path.write_text(
            code,
            encoding="utf-8",
        )

        return code_path

    # =========================================================================
    # PROVENIÊNCIA
    # =========================================================================

    def _build_provenance(
        self,
        run_id: str,
        run_dir: Path,
        code_path: Path,
        generated_by: Optional[str],
        reviewed_by: Optional[str],
        corrected_by: Optional[str],
        reported_by: Optional[str],
        manually_edited: bool,
    ) -> Provenance:

        try:
            import numpy
            numpy_version = numpy.__version__
        except Exception:
            numpy_version = None

        try:
            import scipy
            scipy_version = scipy.__version__
        except Exception:
            scipy_version = None

        try:
            import matplotlib
            matplotlib_version = matplotlib.__version__
        except Exception:
            matplotlib_version = None

        code_hashes = {}

        if code_path.exists():

            code_hashes[
                code_path.name
            ] = sha256_file(
                code_path
            )

        library_hashes = hash_tree(
            self.library_root
        )

        return Provenance(
            lab_version=LAB_VERSION,
            run_id=run_id,
            python_version=sys.version,
            platform=platform.platform(),
            numpy_version=numpy_version,
            scipy_version=scipy_version,
            matplotlib_version=matplotlib_version,
            code_hashes=code_hashes,
            library_hashes=library_hashes,
            generated_by=generated_by,
            reviewed_by=reviewed_by,
            corrected_by=corrected_by,
            reported_by=reported_by,
            manually_edited=manually_edited,
        )

    # =========================================================================
    # EXECUÇÃO PRINCIPAL
    # =========================================================================

    def run(
        self,
        direction: ExperimentDirection,
        code: str,
        filename: str = "experiment.py",
        generated_by: Optional[str] = "codificador",
        reviewed_by: Optional[str] = "revisor",
        corrected_by: Optional[str] = None,
        reported_by: Optional[str] = "relator",
        manually_edited: bool = True,
        require_review: bool = True,
        library_root: Optional[Path] = None,
    ) -> RunState:

        run_id = self._next_run_id()

        run_dir = (
            self.run_root / run_id
        )

        run_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        run_state = RunState(
            run_id=run_id,
            direction=direction,
        )

        # ---------------------------------------------------------------------
        # DIREÇÃO
        # ---------------------------------------------------------------------

        write_json(
            run_dir / "direction.json",
            asdict(direction),
        )

        # ---------------------------------------------------------------------
        # CONTEXTO
        # ---------------------------------------------------------------------

        write_json(
            run_dir / "project_context.json",
            asdict(self.project_context),
        )

        self._event(
            run_state,
            "operador",
            "direction_registered",
            "Direção experimental registrada.",
        )

        # ---------------------------------------------------------------------
        # CÓDIGO
        # ---------------------------------------------------------------------

        code_path = self._prepare_code(
            code,
            run_dir,
            filename,
        )

        self._event(
            run_state,
            "codificador",
            "code_registered",
            "Código registrado para execução.",
            output_refs=[
                str(code_path)
            ],
        )

        # ---------------------------------------------------------------------
        # PROVENIÊNCIA INICIAL
        # ---------------------------------------------------------------------

        run_state.provenance = (
            self._build_provenance(
                run_id=run_id,
                run_dir=run_dir,
                code_path=code_path,
                generated_by=generated_by,
                reviewed_by=reviewed_by,
                corrected_by=corrected_by,
                reported_by=reported_by,
                manually_edited=manually_edited,
            )
        )

        # ---------------------------------------------------------------------
        # REVISÃO
        # ---------------------------------------------------------------------

        run_state.review = self.reviewer.review(
            code
        )

        self._event(
            run_state,
            "revisor",
            "technical_review",
            run_state.review.summary,
            output_refs=[
                "review.json"
            ],
        )

        write_json(
            run_dir / "review.json",
            asdict(run_state.review),
        )

        if (
            require_review
            and run_state.review.status
            == ReviewStatus.REPROVADO
        ):

            self._finalize(
                run_state,
                run_dir,
            )

            return run_state

        # ---------------------------------------------------------------------
        # HASH ANTES DA EXECUÇÃO
        # ---------------------------------------------------------------------

        library_for_run = (
            Path(library_root)
            if library_root
            else self.library_root
        )

        library_before = hash_tree(
            library_for_run
        )

        write_json(
            run_dir / "library_hash_before.json",
            library_before,
        )

        # ---------------------------------------------------------------------
        # EXECUÇÃO
        # ---------------------------------------------------------------------

        run_state.execution = (
            self.executor.execute(
                code_path=code_path,
                run_dir=run_dir,
                library_root=library_for_run,
            )
        )

        self._event(
            run_state,
            "executor",
            "execution_finished",
            (
                f"Execução terminou com status "
                f"{run_state.execution.status.value}."
            ),
            output_refs=[
                run_state.execution.stdout_path,
                run_state.execution.stderr_path,
            ],
        )

        write_json(
            run_dir / "execution.json",
            asdict(run_state.execution),
        )

        # ---------------------------------------------------------------------
        # HASH DEPOIS DA EXECUÇÃO
        # ---------------------------------------------------------------------

        sandbox_library = (
            Path(
                run_state.execution.artifacts_root
            )
            / "library"
        )

        library_after = hash_tree(
            sandbox_library
        )

        write_json(
            run_dir / "library_hash_after.json",
            library_after,
        )

        library_diff = compare_hashes(
            library_before,
            library_after,
        )

        write_json(
            run_dir / "library_hash_diff.json",
            library_diff,
        )

        # ---------------------------------------------------------------------
        # VALIDAÇÃO
        # ---------------------------------------------------------------------

        run_state.validation = (
            self.validator.validate(
                run_state.execution
            )
        )

        # Alteração da biblioteca durante execução
        # é considerada falha de proveniência.
        if not library_diff["same"]:

            run_state.validation.findings.append(
                ValidationFinding(
                    check="library_immutability",
                    status="FAIL",
                    message=(
                        "A cópia da biblioteca foi alterada "
                        "durante a execução."
                    ),
                    value=library_diff["changed"],
                )
            )

            run_state.validation.status = (
                ValidationStatus.FAIL
            )

        self._event(
            run_state,
            "validador",
            "deterministic_validation",
            (
                f"Validação: "
                f"{run_state.validation.status.value}."
            ),
            output_refs=[
                "validation.json"
            ],
        )

        write_json(
            run_dir / "validation.json",
            asdict(run_state.validation),
        )

        # ---------------------------------------------------------------------
        # RELATÓRIO
        # ---------------------------------------------------------------------

        run_state.report = (
            self.reporter.build(
                run_id=run_id,
                execution=run_state.execution,
                validation=run_state.validation,
                review=run_state.review,
            )
        )

        self._event(
            run_state,
            "relator",
            "report_generated",
            (
                "Relatório gerado exclusivamente "
                "a partir dos artefatos do run."
            ),
            output_refs=[
                "report.json"
            ],
        )

        write_json(
            run_dir / "report.json",
            asdict(run_state.report),
        )

        # ---------------------------------------------------------------------
        # FINALIZAÇÃO
        # ---------------------------------------------------------------------

        self._finalize(
            run_state,
            run_dir,
        )

        return run_state

    # =========================================================================
    # FINALIZAÇÃO
    # =========================================================================

    def _finalize(
        self,
        run_state: RunState,
        run_dir: Path,
    ) -> None:

        if run_state.provenance:

            write_json(
                run_dir / "provenance.json",
                asdict(run_state.provenance),
            )

        write_json(
            run_dir / "agent_events.json",
            [
                asdict(event)
                for event in run_state.events
            ],
        )

        package_dir = (
            self.package_builder.build(
                run_state,
                run_dir,
                self.project_context,
            )
        )

        write_json(
            run_dir / "run_state.json",
            asdict(run_state),
        )

        print()
        print("=" * 72)
        print(
            f"UNIT-001 · {run_state.run_id}"
        )
        print("=" * 72)

        if run_state.execution:
            print(
                f"Execução : "
                f"{run_state.execution.status.value}"
            )

        if run_state.validation:
            print(
                f"Validação: "
                f"{run_state.validation.status.value}"
            )

        print(
            f"Run      : {run_dir}"
        )

        print(
            f"Pacote   : {package_dir}"
        )

        print("=" * 72)

    # =========================================================================
    # OPINIÕES EXTERNAS
    # =========================================================================

    def register_external_opinion(
        self,
        run_id: str,
        opinion_type: OpinionType,
        text: str,
        source: str,
        restriction_id: Optional[str] = None,
        restriction_statement: Optional[str] = None,
        restriction_rationale: str = "",
        restriction_parameters: Optional[
            Dict[str, Any]
        ] = None,
    ) -> ExternalOpinion:

        run_dir = (
            self.run_root / run_id
        )

        if not run_dir.exists():
            raise FileNotFoundError(
                f"Run inexistente: {run_id}"
            )

        restriction = None

        if opinion_type == OpinionType.RESTRICAO:

            if not restriction_id:
                raise ValueError(
                    "Uma restrição precisa de restriction_id."
                )

            if not restriction_statement:
                raise ValueError(
                    "Uma restrição precisa de statement."
                )

            restriction = ExperimentalRestriction(
                restriction_id=restriction_id,
                statement=restriction_statement,
                source=source,
                rationale=restriction_rationale,
                parameters=(
                    restriction_parameters or {}
                ),
            )

        opinion = ExternalOpinion(
            opinion_id=(
                f"{run_id}-opinion-"
                f"{int(time.time() * 1000)}"
            ),
            opinion_type=opinion_type,
            text=text,
            source=source,
            restriction=restriction,
        )

        path = (
            run_dir /
            "external_opinions.json"
        )

        existing: List[Dict[str, Any]] = []

        if path.exists():

            try:
                existing = read_json(path)

                if not isinstance(existing, list):
                    existing = []

            except Exception:
                existing = []

        existing.append(
            asdict(opinion)
        )

        write_json(
            path,
            existing,
        )

        return opinion

    # =========================================================================
    # RESTRIÇÕES ATIVAS
    # =========================================================================

    def active_restrictions(
        self,
    ) -> List[ExperimentalRestriction]:

        restrictions = []
        valid_keys = {f.name for f in fields(ExperimentalRestriction)}

        for run_dir in sorted(
            self.run_root.glob("run_*")
        ):

            path = (
                run_dir /
                "external_opinions.json"
            )

            if not path.exists():
                continue

            try:
                opinions = read_json(path)
            except Exception:
                continue

            if not isinstance(opinions, list):
                continue

            for raw in opinions:

                if not isinstance(raw, dict):
                    continue

                if (
                    raw.get("opinion_type")
                    != OpinionType.RESTRICAO.value
                ):
                    continue

                raw_restriction = (
                    raw.get("restriction")
                )

                if not isinstance(raw_restriction, dict):
                    continue

                filtered = {
                    k: v
                    for k, v in raw_restriction.items()
                    if k in valid_keys
                }

                try:
                    restriction = ExperimentalRestriction(**filtered)

                    if restriction.active:
                        restrictions.append(
                            restriction
                        )
                except Exception:
                    pass

        return restrictions

    # =========================================================================
    # MATERIALIZAÇÃO DO CONTEXTO PARA O CODIFICADOR
    # =========================================================================

    def build_coder_context(
        self,
    ) -> Dict[str, Any]:

        """
        Ponto crítico anti-viés.

        O Codificador recebe:

            - PROJECT_CONTEXT
            - restrições vinculantes

        Não recebe automaticamente:

            - hipóteses
            - interpretações
            - conclusões
            - ranking de resultados anteriores
            - "o experimento anterior deu certo"

        """

        return {
            "project_context": asdict(
                self.project_context
            ),
            "active_restrictions": [
                asdict(r)
                for r in self.active_restrictions()
            ],
            "epistemic_rule": (
                "Somente restrições experimentais "
                "explicitamente registradas podem orientar "
                "o Codificador."
            ),
        }


# =============================================================================
# 22. SCRIPTS PRONTOS
# =============================================================================

def list_ready_scripts(
    root: Path = DEFAULT_READY_SCRIPTS_ROOT,
) -> List[Path]:

    if not root.exists():
        return []

    return sorted(
        p for p in root.glob("*.py")
        if p.is_file()
    )


def load_ready_script(
    path: Path,
) -> str:

    return path.read_text(
        encoding="utf-8"
    )


# =============================================================================
# 23. AUDITORIA DO RUN
# =============================================================================

def audit_run(
    run_dir: Path,
) -> Dict[str, Any]:

    run_dir = Path(run_dir)

    required = [
        "direction.json",
        "review.json",
        "execution.json",
        "validation.json",
        "report.json",
        "provenance.json",
        "agent_events.json",
    ]

    missing = [
        name
        for name in required
        if not (run_dir / name).exists()
    ]

    return {
        "run": str(run_dir),
        "exists": run_dir.exists(),
        "missing": missing,
        "complete": (
            run_dir.exists()
            and not missing
        ),
    }


# =============================================================================
# 24. EXEMPLO MÍNIMO
# =============================================================================

def demo() -> None:

    lab = Unit001Laboratory(
        run_root=Path(
            "unit_agents/runs_demo"
        ),
        library_root=Path(
            "UNIT-001_WORK"
        ),
    )

    lab.update_project_context(
        """
UNIT-001.

Objetivo atual:
investigar se alterações na organização espacial da matéria,
mantendo constantes as condições experimentais explicitamente
definidas, produzem diferenças mensuráveis na interação com a onda.

Não assumir causalidade.
Não assumir mecanismo.
Não tratar correlação como explicação.
        """.strip()
    )

    direction = ExperimentDirection(
        objective=(
            "Executar um teste técnico controlado "
            "e produzir evidência rastreável."
        ),
        instructions=(
            "Execute o código fornecido sem modificar "
            "seus resultados e registre os escalares."
        ),
        expected_outputs=[
            "R",
            "T",
            "A",
        ],
        forbidden_assumptions=[
            "A maior absorção prova o mecanismo UNIT.",
            "Diferença entre geometrias implica causalidade.",
        ],
    )

    code = r'''
print("RESULTADO EXPERIMENTAL")
print("R = 0.100")
print("T = 0.700")
print("A = 0.200")
'''

    state = lab.run(
        direction=direction,
        code=code,
        filename="experiment.py",
        manually_edited=True,
    )

    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "execution": (
                    state.execution.status.value
                    if state.execution
                    else None
                ),
                "validation": (
                    state.validation.status.value
                    if state.validation
                    else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


# =============================================================================
# 25. CLI
# =============================================================================

# =============================================================================
# LIGAÇÃO COM O COLAB (Células 1 e 3)
# =============================================================================
# O kernel v3 não usa UNIT-001_WORK. A biblioteca oficial é lib/ sob
# UNIT-001_AGENTES, e os runs ficam em UNIT-001_AGENTES/runs.

lab = Unit001Laboratory(
    run_root=RUNS,
    library_root=LIB,
    ready_scripts_root=SCRIPTS_DIR,
    timeout_seconds=int(os.environ.get("UNIT_AGENT_TIMEOUT", "600")),
    memory_gb=float(LIMITE_MEMORIA_GB),
    scalar_limits=LIMITES_ESCALARES,
)

lab.update_project_context(PROJECT_CONTEXT)

print()
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(" Kernel UNIT-001 v3 ligado.")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(" run_root :", lab.run_root.resolve())
print(" library  :", lab.library_root.resolve())
print(" scripts  :", lab.ready_scripts_root.resolve())
print(" contexto : v" + str(lab.project_context.version))
print(" PASS     : só significa que o artefato passou nas")
print("            checagens determinísticas. Não é física.")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
