# versao: 14
# inicio/11_contexto.py — contexto do projeto e decisões
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 3 · CONTEXTO DO PROJETO
# ═══════════════════════════════════════════════════════════════
# EDITE PROJECT_CONTEXT quando houver mudança científica ou estrutural.
# Esta célula NÃO executa simulações.
# ═══════════════════════════════════════════════════════════════

PROJECT_CONTEXT = f"""
PROJETO UNIT-001

HIPÓTESE EM TESTE
-----------------
Hipótese EM TESTE (não é fato estabelecido): a geometria/distribuição
espacial da matéria, e não somente as propriedades de bulk, pode alterar
a interação de uma onda incidente com o meio, incluindo reflexão,
transmissão, absorção e redistribuição espacial do campo.

A hipótese deve permanecer separada dos resultados numéricos.
Nenhum agente técnico deste laboratório deve interpretar os resultados
como confirmação ou refutação da hipótese.

ARQUITETURA ATUAL
-----------------
Raiz do projeto:
{BASE}

Biblioteca científica:
{LIB}

Scripts executáveis oficiais:
{SCRIPTS_DIR}

Dados:
{DATA_ROOT}

Resultados do extrator:
{EXTRACTOR_RESULTS_DIR}

Casos NPZ:
{CASES_DIR}

Resultados FDFD:
{FDFD_RESULTS_DIR}

Resultados FDTD:
{FDTD_RESULTS_DIR}

Resultados térmicos:
{THERMAL_RESULTS_DIR}

Análises:
{ANALYSIS_DIR}

Relatórios de validação:
{VALIDATION_DIR}

DOCUMENTAÇÃO DOS SOLVERS
------------------------
- FDFD 2D/3D escalar.
- FDFD 3D atual: TE_y escalar, com calibração discreta e suporte a
  permeabilidade magnética.
- FDFD 3D possui diagnóstico de residual e métricas de energia.
- FDTD 3D: Yee + CPML + TF/SF.
- FDTD 3D foi validado em onda contínua (CW).
- A extração PULSO + FFT permanece fora do fluxo confiável enquanto
  o problema conhecido não for resolvido.
- thermal_coupling resolve temperatura estacionária a partir de Q_abs.
- O acoplamento térmico atual não inclui eps(T).

REGRA DE VALIDAÇÃO
------------------
Mudanças de organização de arquivos, imports ou caminhos não devem
alterar a lógica científica ou os resultados numéricos dos solvers.

Qualquer regressão deve ser investigada antes de considerar a migração
concluída.

BENCHMARK UNIT-001
------------------
Geometrias:
- ORDERED
- CLUSTERED
- RANDOM_1000 até RANDOM_1019
- 20 realizações RANDOM
- volume de material pareado entre as geometrias

Geometria estrutural:
- 4 pilares
- cada pilar: 4 x 4 x 8 células
- total de material: 512 células
- fração volumétrica: 0.125

Grade estrutural:
- NX = 16
- NY = 16
- NZ_estrutura = 16
- dx = dy = dz = 25e-9 m
- PML = 10 células
- buffer = 10 células em cada lado de z
- domínio total: 16 x 16 x 56

ÓPTICA
------
- n_bg = 1.0 + 0j
- n_pilar = 2.0 + 0.05j
- frequências: 280, 300 e 320 THz

MÉTRICAS ÓPTICAS
----------------
O extrator V7 mantém separadas:

Amplitude complexa:
- r
- t

Métricas de potência:
- R_power
- T_power
- A_flux_power

Métricas espectrais/especulares:
- R_specular
- T_specular
- A_flux_specular

Não tratar amplitudes complexas como se fossem diretamente potências.

TÉRMICA
-------
- k_bg = 0.026 W/(m.K)
- k_pilar = 150 W/(m.K)
- q_abs em W/m^3
- P_abs = integral/soma de q_abs sobre o volume, conforme discretização
- T = solução estacionária de thermal_coupling
- condição térmica de contorno: T = 0
- q_abs é mascarado pela região estrutural para evitar contribuição
  artificial da PML

DADOS ATUAIS
------------
Os casos atuais ficam em:

{CASES_DIR}

Os arquivos são NPZ produzidos pelo pipeline atual do extrator.

O nome típico do caso atual segue o padrão:

<GEOMETRIA>_seed_<SEED>_<FREQ>THz.npz

As chaves efetivamente produzidas devem ser consultadas no NPZ antes
de qualquer agente assumir uma estrutura fixa.

O pipeline atual pode conter, entre outras:
- geom_struct
- Etotal
- Escat
- Einc
- q_abs
- T
- k_field
- z_axis
- r
- t
- R_power
- T_power
- A_flux_power
- R_specular
- T_specular
- A_flux_specular
- métricas de potência incidente/absorvida
- diagnósticos de residual

Não presumir a existência de uma chave apenas porque ela existia em
versões antigas do pipeline.

MÓDULOS PRINCIPAIS (padrão de estudo da UNIT — detalhes e status em lib/PADRAO_ESTUDO.md)
------------------
Status segue o documento de estado da Teoria UNIT v0.8: VALIDADO = testado contra solução analítica.

Solvers (lib/solvers/):
- fdfd2d.py     FDFD 2D escalar TE_y. VALIDADO (Fabry-Pérot, lâmina homogênea).
- fdfd3d.py     FDFD 3D escalar TE_y. VALIDADO. É o solver usado pelo framework (fdfd3d_te_y).
- fdtd3d.py     FDTD 3D. VALIDADO só em regime CW (spectral_sweep_cw / run_cw_single_frequency).
                O caminho pulso + FFT (run_fdtd / extract_spectral_RT) NÃO está validado: não use para números.

Estado (lib/core/):
- wave_state.py, material_state.py, energy_state.py   (ledger de energia: EM e térmico)

Adapters (lib/adapters/):
- fdfd_adapter.py, fdtd_adapter.py   (solver -> WaveState -> EnergyLedger)

Acoplamentos (lib/coupling/):
- thermal_coupling.py     EM -> térmico (usado pelo framework)
- spectral_coupling.py, spectral_integration.py   resposta espectral (varredura de frequências)

Geometria (lib/geometry/):
- unit001_dataset_66_cases.py   gerador CANÔNICO (usado pelo framework)
- geometry.py                   controles A/B/C e geometria 2D (confirme a localização em _mapa/mapa.json)

Validação (lib/validation/):
- validate_fdfd2d.py, validate_fdfd3d.py, validate_fdtd3d.py   comparação com Fabry-Pérot

Pesquisa/investigação (lib/research/ e scripts_prontos/):
- tmm_benchmark.py     TMM 1D: referência de controle (baseline numérico)
- thermal_qk_investigation.py   investigação da Barreira Térmica (lib/research/)
- gerar_catalogo_geometrico.py   gera dados/UNIT001/geometria a partir do gerador canônico
- contrafactual_termico_v43.py   experimento contrafactual completo (V4.3: EXP0 a EXP3); referência
- contrafactual_termico_simples.py   versão corrigida e mais simples (solver térmico próprio)
- extrator_legado.py   legado autônomo: o framework o substitui; mantido por referência

Regra: para uma execução nova, use o framework (lib.framework); estes módulos são a base física e a referência.

FRAMEWORK PADRONIZADO (lib.framework) — USE-O; não reescreva solver, geometria nem campos:
- Casos (22 geometrias x 3 frequências) são gerados AUTOMATICAMENTE por
  lib.framework.pipeline.run_pipeline_in_run(), lendo spec.aop (AOP-DSL) da pasta do run.
  NPZ padrão em os.environ["UNIT001_CASES_DIR"], nome <GEOMETRIA>_seed_<seed|none>_<f>THz.npz, chaves:
  geom_struct, domain_material_mask, epsilon, Etotal, Escat, Einc, q_abs_raw, q_abs_thermal, q_abs_struct,
  k_field, k_struct, T, dx, dy, dz, dV, z_struct_start, z_struct_end, scalars_json.
- Para ANALISAR casos: from lib.framework.dataset import Dataset ; ds = Dataset.from_dir(os.environ["UNIT001_CASES_DIR"]) ;
  cada caso c tem c.scalars (dict), c.geometry, c.seed, c.frequency_thz e c.array("T").
- Para adicionar teste/campo/solver/verificador: registrar com os decoradores de lib.framework
  (test, field, solver, verifier) em lib/framework/plugins/.
- EXPERIMENTOS (varrer parâmetros, medir, comparar, calibrar) NÃO se escrevem em Python: use a linguagem semântica UNIT-L
  (/linguagem, /experimento). Vocabulário: EXPERIMENT CASE FIX VARY SOLVE MEASURE DERIVE LIMIT CHECK COMPARE ANALYZE OUTPUT.
  Exemplo real: experimentos/T2_leve.unl. Python livre só para o que NÃO existe como primitiva (e então proponha um plugin).
- Todo código passa pelo AOP-DSL: proibido eval/exec/compile/__import__ e os módulos importlib/subprocess/socket/ctypes;
  imports lib.* só em CAPABILITY.allowed_modules.

ESTRUTURA DE EXECUÇÃO ISOLADA
-----------------------------
Quando um script for executado pelo laboratório multiagente, a cópia
isolada deve preservar a árvore recursiva da biblioteca.

Exemplo:

run_xxx/
├── code.py
└── lib/
    ├── __init__.py
    ├── core/
    ├── geometry/
    ├── solvers/
    ├── adapters/
    ├── coupling/
    ├── validation/
    └── research/

O PYTHONPATH da execução deve apontar para a raiz da execução isolada,
não diretamente para run_xxx/lib.

Assim imports como:

from lib.solvers.fdfd3d import ...

continuam funcionando.

REGRAS DE CONSERVAÇÃO
---------------------
- Não alterar código científico apenas para satisfazer um agente.
- Não substituir um solver por outro sem decisão explícita.
- Não inventar módulos ausentes.
- Não inventar dados ausentes.
- Não corrigir silenciosamente resultados científicos.
- Não alterar parâmetros físicos sem registrar a alteração.
- Não misturar resultados de execuções diferentes.
- Não confundir amplitude complexa com potência.
- Não assumir que R/T/A são amplitudes.
- Não tratar um resultado isolado como conclusão científica.
"""

REGRA_FUNDAMENTAL = """
REGRA ABSOLUTA: você é um executor técnico, não um cientista.

NUNCA tire conclusões sobre a hipótese.

NUNCA diga que algo:
- "confirma";
- "refuta";
- "comprova";
- "valida a teoria";
- "é consistente com a teoria";
- "demonstra o efeito proposto".

NUNCA sugira o rumo da pesquisa.

A interpretação científica é responsabilidade do pesquisador e das IAs
de nível superior designadas para essa função.

Sua função é verificar e relatar exclusivamente aspectos técnicos,
como:
- erro de execução;
- exceções;
- imports;
- dependências ausentes;
- sintaxe;
- shapes;
- NaN/Inf;
- tipos;
- unidades;
- limites numéricos;
- residual;
- conservação de energia;
- arquivos gerados;
- integridade dos dados;
- timeout;
- consumo de memória;
- incompatibilidade entre versões;
- divergência entre entradas e saídas esperadas.

APRESENTE OS NÚMEROS COMO FORAM OBTIDOS.

Não transforme uma observação numérica em interpretação física.
"""

# ═══════════════════════════════════════════════════════════════
# ÍNDICE AUTOMÁTICO DA BIBLIOTECA
# ═══════════════════════════════════════════════════════════════
# A arquitetura nova possui subdiretórios.
# Portanto, o índice deve ser RECURSIVO.
# ═══════════════════════════════════════════════════════════════

def _assinatura(no):
    try:
        args = ast.unparse(no.args)
    except Exception:
        args = "..."

    ret = ""

    if getattr(no, "returns", None) is not None:
        try:
            ret = " -> " + ast.unparse(no.returns)
        except Exception:
            pass

    return f"{no.name}({args}){ret}"


def _doc(no, limite=350):
    d = " ".join(
        (ast.get_docstring(no) or "").split()
    )

    return (
        d[:limite]
        + ("…" if len(d) > limite else "")
    )


def _indexar_arquivo_python(arq, linhas):
    """
    Adiciona ao índice as funções/classes públicas de um arquivo Python.
    """

    caminho_relativo = arq.relative_to(LIB)

    try:
        arvore = ast.parse(
            arq.read_text(
                encoding="utf-8"
            )
        )
    except SyntaxError as erro:
        linhas.append(
            f"# {caminho_relativo}: "
            f"[erro de sintaxe: {erro}]"
        )
        return
    except Exception as erro:
        linhas.append(
            f"# {caminho_relativo}: "
            f"[erro de leitura: "
            f"{type(erro).__name__}: {erro}]"
        )
        return

    linhas.append(
        f"# {caminho_relativo}"
    )

    for no in arvore.body:

        if (
            isinstance(no, ast.FunctionDef)
            and not no.name.startswith("_")
        ):
            linhas.append(
                f"  - {_assinatura(no)}"
            )

            doc = _doc(no)

            if doc:
                linhas.append(
                    f"      {doc}"
                )

        elif (
            isinstance(no, ast.AsyncFunctionDef)
            and not no.name.startswith("_")
        ):
            linhas.append(
                f"  - async {_assinatura(no)}"
            )

            doc = _doc(no)

            if doc:
                linhas.append(
                    f"      {doc}"
                )

        elif (
            isinstance(no, ast.ClassDef)
            and not no.name.startswith("_")
        ):
            linhas.append(
                f"  - class {no.name}"
            )

            doc = _doc(no)

            if doc:
                linhas.append(
                    f"      {doc}"
                )

            for metodo in no.body:

                if not isinstance(
                    metodo,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                ):
                    continue

                if (
                    metodo.name.startswith("_")
                    and metodo.name != "__init__"
                ):
                    continue

                prefixo = (
                    ".async "
                    if isinstance(
                        metodo,
                        ast.AsyncFunctionDef,
                    )
                    else "."
                )

                linhas.append(
                    f"      {prefixo}"
                    f"{_assinatura(metodo)}"
                )

                doc_metodo = _doc(
                    metodo,
                    200,
                )

                if doc_metodo:
                    linhas.append(
                        f"          "
                        f"{doc_metodo}"
                    )


def indexar_biblioteca(limite_total=14000):
    """
    Gera índice recursivo da biblioteca UNIT-001.

    Inclui:
    - todos os .py dentro de lib/;
    - caminho relativo;
    - funções públicas;
    - classes públicas;
    - métodos públicos;
    - assinaturas;
    - docstrings resumidas.

    O índice é apenas informativo. Não executa módulos.
    """

    linhas = []

    if not LIB.exists():
        return f"(biblioteca inexistente: {LIB})"

    arquivos = sorted(
        LIB.rglob("*.py")
    )

    if not arquivos:
        return f"(biblioteca vazia: {LIB})"

    for arq in arquivos:
        _indexar_arquivo_python(
            arq,
            linhas,
        )

    texto = "\n".join(linhas)

    if len(texto) > limite_total:
        texto = (
            texto[:limite_total]
            + "\n[... índice truncado ...]"
        )

    return texto


# ═══════════════════════════════════════════════════════════════
# REGISTRO DE DECISÕES
# ═══════════════════════════════════════════════════════════════
#
# restricao
#     → vinculante para o Codificador
#
# hipotese
#     → somente informativa no pacote
#
# interpretacao
#     → somente informativa no pacote
#
# Isso evita que interpretações de agentes sejam transformadas
# automaticamente em restrições técnicas.
# ═══════════════════════════════════════════════════════════════

TIPOS_DECISAO = (
    "restricao",
    "hipotese",
    "interpretacao",
)


def registrar_decisao(
    texto,
    fonte,
    run_id=None,
    tipo="interpretacao",
):
    if tipo not in TIPOS_DECISAO:
        raise ValueError(
            f"tipo inválido: {tipo}. "
            f"Use: {TIPOS_DECISAO}"
        )

    reg = {
        "quando": dt.datetime.now().isoformat(
            timespec="seconds"
        ),
        "fonte": fonte,
        "run": run_id,
        "tipo": tipo,
        "texto": str(texto).strip(),
    }

    DECISOES.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with DECISOES.open(
        "a",
        encoding="utf-8",
    ) as arquivo:
        arquivo.write(
            json.dumps(
                reg,
                ensure_ascii=False,
            )
            + "\n"
        )

    return reg


def ler_decisoes(
    n=5,
    tipos=None,
):
    if not DECISOES.exists():
        return []

    registros = []

    for linha in DECISOES.read_text(
        encoding="utf-8"
    ).splitlines():

        if not linha.strip():
            continue

        try:
            registro = json.loads(
                linha
            )
        except json.JSONDecodeError:
            # Registro corrompido não deve derrubar
            # o laboratório inteiro.
            continue

        registro.setdefault(
            "tipo",
            "interpretacao",
        )

        registros.append(
            registro
        )

    if tipos:
        registros = [
            registro
            for registro in registros
            if registro.get("tipo")
            in tipos
        ]

    return registros[-n:]


def restricoes_vigentes(n=10):
    registros = ler_decisoes(
        n,
        ("restricao",),
    )

    if not registros:
        return "(nenhuma registrada)"

    return "\n".join(
        f"- {registro.get('texto', '')[:1500]}"
        for registro in registros
    )


# ═══════════════════════════════════════════════════════════════
# DIAGNÓSTICO DA CÉLULA
# ═══════════════════════════════════════════════════════════════

INDICE_BIBLIOTECA = indexar_biblioteca()

print(
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)
print(
    " UNIT-001 · CONTEXTO E ÍNDICE DA BIBLIOTECA"
)
print(
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)

print(
    f"Projeto : {BASE}"
)
print(
    f"Biblioteca : {LIB}"
)
print(
    f"Arquivos Python : "
    f"{len(list(LIB.rglob('*.py')))}"
)
print(
    f"Casos NPZ : "
    f"{len(list(Path(CASES_DIR).glob('*.npz')))}"
)
print(
    f"Decisões : {DECISOES}"
)

print(
    "\nÍNDICE DA BIBLIOTECA:\n"
)
print(
    INDICE_BIBLIOTECA
)

print(
    "\n"
    "Célula 3 carregada."
)
print(
    "Índice recursivo: ATIVO"
)
print(
    "Registro de decisões: ATIVO"
)
print(
    "Regra de executor técnico: ATIVA"
)
