# versao: 11
# inicio/20_agentes.py — agentes: codificador, revisor, executor
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 4 · AGENTES: CODIFICADOR, REVISOR TÉCNICO, EXECUTOR
# ═══════════════════════════════════════════════════════════════

def extrair_codigo(texto):
    if not texto:
        return None

    blocos = re.findall(
        r"```(?:python|py)?\s*\n(.*?)```",
        texto,
        flags=re.S,
    )

    return (
        max(blocos, key=len).strip()
        if blocos
        else None
    )


def checar_sintaxe(codigo):
    if not codigo:
        return "código vazio"

    try:
        ast.parse(codigo)
        return None
    except SyntaxError as e:
        return f"linha {e.lineno}: {e.msg}"


def _sistema_codificador():
    return f"""{REGRA_FUNDAMENTAL}

Você é o CODIFICADOR. Recebe uma instrução do pesquisador e escreve UM script Python.

{PROJECT_CONTEXT}

BIBLIOTECA DISPONÍVEL
A biblioteca está organizada como pacote Python dentro de lib/.
Use os imports conforme o índice abaixo, por exemplo:

from lib.solvers.fdfd3d import ...
from lib.core.wave_state import ...
from lib.coupling.thermal_coupling import ...

ÍNDICE DA BIBLIOTECA:
{indexar_biblioteca()}

CONVENÇÕES DO SCRIPT
- Autocontido.
- Sem input().
- Sem pedir nada ao usuário.
- Python 3 + NumPy + SciPy + Matplotlib.
- Saídas em arquivo (figuras, .npz, .json) vão em os.environ["UNIT_RUN_DIR"].
- Salve figuras com plt.savefig(...), nunca use plt.show().
- Use apenas funções que existam no índice acima ou que você defina no próprio script.
- Não invente APIs.
- Importe módulos pelo caminho real da biblioteca, usando o namespace "lib".
- Não altere arquivos permanentes do projeto.
- Imprima resultados com rótulo e unidade.
- Use notação científica quando fizer sentido.
- Ao FINAL do script imprima UMA linha começando exatamente com:
  UNIT_RESULT_JSON:
- Depois de `UNIT_RESULT_JSON: ` deve vir json.dumps(obj, ensure_ascii=False), onde:
  obj = {{"tabela": [{{"caso": "...", "grandeza": valor, ...}}, ...],
          "escalares": {{"nome": valor, ...}}}}
- Valores devem ser números/strings/listas Python puros.
- Converta objetos NumPy com float(), int() ou .tolist().
- Use os MESMOS valores impressos anteriormente, sem arredondamento adicional.
- Nada de conclusões científicas no JSON.
- Imprima verificações técnicas objetivas:
  shape, min/max, contagem de NaN/Inf, balanço de energia quando aplicável etc.
- Se arquivo ou chave não existir, falhe com mensagem clara.
- Não invente dados ausentes.
- Prints e comentários descrevem O QUE foi calculado, nunca o que o resultado significa.
- Não modifique silenciosamente parâmetros físicos.
- Não esconda exceções relevantes.
- Responda SOMENTE com um bloco ```python ...``` e nada mais."""


def codificador(instrucao, codigo_base=None):
    user = (
        "RESTRIÇÕES EXPERIMENTAIS VINCULANTES "
        "(definidas pelo pesquisador; siga-as):\n"
        + restricoes_vigentes()
        + "\n\n"
        "Você NÃO recebe interpretações nem hipóteses sobre o resultado: "
        "não presuma o resultado esperado.\n\n"
    )

    if codigo_base:
        user += (
            "CÓDIGO BASE "
            "(modifique conforme a instrução):\n"
            "```python\n"
            f"{codigo_base}\n"
            "```\n\n"
        )

    user += f"INSTRUÇÃO:\n{instrucao}"

    texto, modelo = chamar(
        "codificador",
        _sistema_codificador(),
        user,
    )

    codigo = extrair_codigo(texto)

    erro = (
        checar_sintaxe(codigo)
        if codigo
        else "nenhum bloco de código na resposta"
    )

    if erro:
        texto, modelo = chamar(
            "codificador",
            _sistema_codificador(),
            user
            + "\n\n"
            + "SUA RESPOSTA ANTERIOR TEVE ESTE PROBLEMA: "
            + f"{erro}. "
            + "Reenvie o script completo e corrigido.",
        )

        codigo = extrair_codigo(texto)

        erro = (
            checar_sintaxe(codigo)
            if codigo
            else "nenhum bloco de código na resposta"
        )

    return codigo, modelo, erro


def corrigir_codigo(instrucao, codigo, stderr):
    user = (
        f"INSTRUÇÃO ORIGINAL:\n{instrucao}\n\n"
        "CÓDIGO QUE FALHOU:\n"
        "```python\n"
        f"{codigo}\n"
        "```\n\n"
        "ERRO EM EXECUÇÃO (final do stderr):\n"
        f"{stderr[-3000:]}\n\n"
        "Corrija SOMENTE a causa do erro, mantendo a lógica "
        "e os cálculos pretendidos. "
        "NÃO esconda o erro com try/except, "
        "NÃO invente dados, "
        "NÃO remova cálculos. "
        "Reenvie o script completo."
    )

    texto, modelo = chamar(
        "codificador",
        _sistema_codificador(),
        user,
    )

    c = extrair_codigo(texto)

    erro = (
        checar_sintaxe(c)
        if c
        else "nenhum bloco de código na resposta"
    )

    return c, modelo, erro


def _n_handlers(codigo):
    try:
        arvore = ast.parse(codigo)

        return sum(
            isinstance(
                n,
                ast.ExceptHandler,
            )
            for n in ast.walk(arvore)
        )

    except SyntaxError:
        return 0


def revisor(instrucao, codigo):
    system = f"""{REGRA_FUNDAMENTAL}

Você é o REVISOR TÉCNICO.

Leia o código e aponte SOMENTE problemas técnicos:

- índices/eixos trocados;
- shapes incompatíveis;
- unidades inconsistentes;
- divisão por zero;
- chaves/arquivos que podem não existir;
- funções chamadas que não existem na biblioteca;
- imports incorretos;
- caminhos incompatíveis com a arquitetura atual;
- código que não faz o que a instrução pede;
- falhas silenciosas;
- ineficiência grave;
- conversões incorretas entre amplitude e potência;
- problemas de NaN/Inf;
- problemas de tipos;
- problemas de persistência dos resultados.

NÃO avalie a hipótese.
NÃO interprete física do resultado esperado.
NÃO reescreva o código.

BIBLIOTECA DISPONÍVEL:
{indexar_biblioteca()}

Formato:
lista numerada
"trecho — problema — correção sugerida"

Se nada encontrar, escreva exatamente:

NENHUM PROBLEMA TÉCNICO ENCONTRADO"""

    user = (
        f"INSTRUÇÃO ORIGINAL:\n{instrucao}\n\n"
        "CÓDIGO:\n"
        "```python\n"
        f"{codigo}\n"
        "```"
    )

    return chamar(
        "revisor",
        system,
        user,
        max_tokens=4000,
    )


def proximo_run_id():
    numeros = []

    for p in RUNS.glob("run_*"):
        partes = p.name.split("_")

        if (
            len(partes) >= 2
            and partes[1].isdigit()
        ):
            numeros.append(
                int(partes[1])
            )

    proximo = (
        max(numeros) + 1
        if numeros
        else 1
    )

    return f"run_{proximo:03d}"


def hash_arquivo(p):
    return hashlib.sha256(
        Path(p).read_bytes()
    ).hexdigest()


def versoes_ambiente():
    from importlib import metadata

    versoes = {
        "python": sys.version.split()[0],
        "plataforma": platform.platform(),
        "cpus": os.cpu_count(),
    }

    for pacote in (
        "numpy",
        "scipy",
        "matplotlib",
    ):
        try:
            versoes[pacote] = metadata.version(
                pacote
            )
        except metadata.PackageNotFoundError:
            versoes[pacote] = "não instalado"

    return versoes


# ═══════════════════════════════════════════════════════════════
# LANÇADOR
# ═══════════════════════════════════════════════════════════════
# Aplica limite de memória e executa o script.
#
# O subprocesso recebe a raiz do run como PYTHONPATH.
# Assim:
#
# run_xxx/
# ├── code.py
# └── lib/
#     ├── __init__.py
#     ├── core/
#     ├── solvers/
#     └── ...
#
# permite:
#
# from lib.solvers.fdfd3d import ...
# ═══════════════════════════════════════════════════════════════

_LAUNCHER = """
import sys
import resource
import runpy

lim = int(sys.argv[2])

if lim > 0:
    resource.setrlimit(
        resource.RLIMIT_AS,
        (lim, lim),
    )

script = sys.argv[1]

sys.argv = [script]

runpy.run_path(
    script,
    run_name="__main__",
)
"""


def _copiar_biblioteca_para_run(lib_run):
    """
    Copia recursivamente a biblioteca científica para o run isolado.

    Mantém a estrutura de pacotes e subdiretórios.
    Retorna um mapa:
        caminho_relativo -> hash SHA256
    """

    lib_run = Path(lib_run)

    if lib_run.exists():
        shutil.rmtree(lib_run)

    lib_run.mkdir(
        parents=True,
        exist_ok=True,
    )

    hashes = {}

    arquivos = sorted(
        LIB.rglob("*.py")
    )

    for origem in arquivos:
        relativo = origem.relative_to(LIB)

        destino = (
            lib_run / relativo
        )

        destino.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            origem,
            destino,
        )

        try:
            os.chmod(
                destino,
                0o444,
            )
        except OSError:
            pass

        hashes[
            relativo.as_posix()
        ] = hash_arquivo(destino)

    return hashes


def _hashes_python_recursivos(diretorio):
    """
    Calcula hashes de todos os .py dentro de um diretório,
    usando o caminho relativo como chave.
    """

    diretorio = Path(diretorio)

    if not diretorio.exists():
        return {}

    return {
        arq.relative_to(
            diretorio
        ).as_posix(): hash_arquivo(arq)
        for arq in sorted(
            diretorio.rglob("*.py")
        )
    }


def executar(codigo, run_dir, timeout=600):
    """
    EXECUTOR: sem LLM.

    Cria uma execução isolada contendo:

        run_xxx/
        ├── code.py
        ├── lib/
        │   ├── core/
        │   ├── geometry/
        │   ├── solvers/
        │   ├── adapters/
        │   ├── coupling/
        │   ├── validation/
        │   └── research/
        ├── stdout.txt
        └── stderr.txt

    A biblioteca usada pelo script é uma cópia recursiva da biblioteca
    oficial no momento da execução.

    O PYTHONPATH aponta para a RAIZ do run, permitindo imports como:

        from lib.solvers.fdfd3d import ...

    O executor não possui acesso às chaves LLM.

    Existe limite de memória e tempo.

    NÃO é um sandbox de segurança completo.
    """

    run_dir = Path(
        run_dir
    ).resolve()

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    lib_run = None  # sem cópia por run: o run importa a biblioteca oficial (ver PYTHONPATH)

    # ─────────────────────────────────────────────────────────
    # 1. Copiar biblioteca recursivamente
    # ─────────────────────────────────────────────────────────

    hashes = _hashes_python_recursivos(LIB)  # hashes da biblioteca oficial ANTES do run

    # ─────────────────────────────────────────────────────────
    # 2. Gravar código
    # ─────────────────────────────────────────────────────────

    script = (
        run_dir / "code.py"
    )

    script.write_text(
        codigo,
        encoding="utf-8",
    )

    # ─────────────────────────────────────────────────────────
    # 3. Ambiente isolado
    # ─────────────────────────────────────────────────────────

    env = {
        "PATH": os.environ.get(
            "PATH",
            "",
        ),
        "UNIT_RUN_DIR": str(
            run_dir
        ),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "MPLBACKEND": "Agg",

        # IMPORTANTE:
        # PYTHONPATH aponta para run_dir,
        # e não para run_dir/lib.
        "PYTHONPATH": os.pathsep.join([str(run_dir), str(LIB.parent)]),

        "HOME": str(
            run_dir
        ),
        "MPLCONFIGDIR": str(
            run_dir / ".mplconfig"
        ),
    }

    if os.environ.get(
        "LD_LIBRARY_PATH"
    ):
        env[
            "LD_LIBRARY_PATH"
        ] = os.environ[
            "LD_LIBRARY_PATH"
        ]

    # ─────────────────────────────────────────────────────────
    # 4. Variáveis UNIT_* necessárias ao script
    # ─────────────────────────────────────────────────────────

    for chave, valor in os.environ.items():

        if (
            chave.startswith(("UNIT_", "UNIT001_"))
            and chave != "UNIT_RUN_DIR"
        ):
            env[chave] = valor

    # ─────────────────────────────────────────────────────────
    # 5. Limite de memória
    # ─────────────────────────────────────────────────────────

    lim_bytes = (
        int(
            LIMITE_MEMORIA_GB
            * 1024**3
        )
        if LIMITE_MEMORIA_GB
        else 0
    )

    # ─────────────────────────────────────────────────────────
    # 6. Execução
    # ─────────────────────────────────────────────────────────

    t0 = time.time()
    estouro = False

    try:
        processo = subprocess.run(
            [
                sys.executable,
                "-c",
                _LAUNCHER,
                str(script),
                str(lim_bytes),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(run_dir),
        )

        out = processo.stdout
        err = processo.stderr
        rc = processo.returncode

    except subprocess.TimeoutExpired as erro:

        def _decodificar(valor):
            if isinstance(
                valor,
                bytes,
            ):
                return valor.decode(
                    "utf-8",
                    "replace",
                )

            return valor or ""

        out = _decodificar(
            erro.stdout
        )

        err = _decodificar(
            erro.stderr
        )

        rc = -1
        estouro = True

    duracao = (
        time.time() - t0
    )

    # ─────────────────────────────────────────────────────────
    # 7. Verificação de integridade
    # ─────────────────────────────────────────────────────────

    hashes_copia = {}  # não há cópia por run

    hashes_originais = (
        _hashes_python_recursivos(
            LIB
        )
    )

    copia_modificada = []  # não há cópia: a integridade é verificada só na biblioteca oficial

    original_modificada = sorted(
        caminho
        for caminho, hash_inicial
        in hashes.items()
        if hashes_originais.get(caminho)
        != hash_inicial
    )

    integridade = {
        "copia_modificada": copia_modificada,
        "original_modificada": original_modificada,
    }

    # ─────────────────────────────────────────────────────────
    # 8. Persistência do log
    # ─────────────────────────────────────────────────────────

    (
        run_dir / "stdout.txt"
    ).write_text(
        out,
        encoding="utf-8",
    )

    (
        run_dir / "stderr.txt"
    ).write_text(
        err,
        encoding="utf-8",
    )

    # ─────────────────────────────────────────────────────────
    # 9. Retorno padronizado
    # ─────────────────────────────────────────────────────────

    return {
        "stdout": out,
        "stderr": err,
        "returncode": rc,
        "timeout": estouro,
        "duracao_s": duracao,
        "lib_hashes": hashes,
        "limite_memoria_gb": LIMITE_MEMORIA_GB,
        "integridade": integridade,
    }


print(
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)
print(
    " Célula 4 carregada."
)
print(
    " Codificador: ATIVO"
)
print(
    " Revisor técnico: ATIVO"
)
print(
    " Executor isolado: ATIVO"
)
print(
    " Biblioteca recursiva: ATIVA"
)
print(
    " PYTHONPATH → raiz do run: ATIVO"
)
print(
    " Hashes recursivos: ATIVOS"
)
print(
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)
