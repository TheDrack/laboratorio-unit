"""
skill_correcao_rapida.py — skill do laboratório UNIT-001.

Aplica correções pontuais em arquivos grandes sem reescrevê-los inteiros.

REGRAS DE SEGURANÇA
- Cada operação é exata ('substituir') ou regex, com contagem esperada: se o
  trecho aparecer um número diferente de vezes, a operação falha e nada é gravado.
- Um arquivo só é gravado se TODAS as operações dele derem certo e, se for .py,
  o resultado compilar (ast) — ou, se for .json/.ipynb, o JSON for válido.
- Simulação é o padrão. Gravar exige aplicar=True.
- Pastas dados/, runs/, inicio/ e comunicacao/ são protegidas.
- Toda execução gera uma linha em comunicacao/log.md e um relatório em saida/.

FORMATO DA ESPECIFICAÇÃO (lista de operações)
  {"arquivo": "lib/solvers/fdfd3d.py",
   "tipo": "substituir",            # ou "regex"
   "antigo": "texto exato",
   "novo": "texto substituto",
   "esperado": 1,                   # quantas ocorrências se espera
   "motivo": "por que mudar"}

USO (célula do Colab)
  executar(ops)                    # simula, mostra diff
  executar(ops, aplicar=True)      # grava

USO PELO AGENTE
  executar_mensagem(caminho)       # só roda se o cabeçalho tiver
                                   # acao_permitida: aplicar_correcao e modo: aplicar|simular
"""

import ast
import datetime
import difflib
import json
import pathlib
import re

ROOT = pathlib.Path("/content/drive/MyDrive/Colab Notebooks/UNIT-001_AGENTES")
PROTEGIDOS = ("dados/", "runs/", "inicio/", "comunicacao/")
TIPOS_VALIDOS = ("substituir", "regex")


class ErroCorrecao(Exception):
    pass


def _agora():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _resolver(arquivo):
    p = (ROOT / arquivo).resolve()
    raiz = ROOT.resolve()
    if raiz not in p.parents:
        raise ErroCorrecao(f"fora do laboratório: {arquivo}")
    rel = p.relative_to(raiz).as_posix()
    if any(rel.startswith(x) for x in PROTEGIDOS):
        raise ErroCorrecao(f"pasta protegida: {rel}")
    return p, rel


def _aplicar_operacao(texto, op):
    tipo = op.get("tipo", "substituir")
    if tipo not in TIPOS_VALIDOS:
        raise ErroCorrecao(f"tipo desconhecido: {tipo}")
    esperado = op.get("esperado", 1)
    antigo = op["antigo"]
    novo = op["novo"]

    if tipo == "substituir":
        n = texto.count(antigo)
        if n != esperado:
            raise ErroCorrecao(f"trecho ocorre {n}x; esperado {esperado}: {antigo[:70]!r}")
        return texto.replace(antigo, novo)

    padrao = re.compile(antigo, re.M)
    n = len(padrao.findall(texto))
    if n != esperado:
        raise ErroCorrecao(f"regex casa {n}x; esperado {esperado}: {antigo[:70]!r}")
    return padrao.sub(novo, texto)


def _validar_conteudo(p, texto, rel):
    if p.suffix == ".py":
        try:
            ast.parse(texto, filename=rel)
        except SyntaxError as e:
            raise ErroCorrecao(f"sintaxe inválida após a correção: {e}")
    elif p.suffix in (".json", ".ipynb"):
        try:
            json.loads(texto)
        except json.JSONDecodeError as e:
            raise ErroCorrecao(f"JSON inválido após a correção: {e}")


def _registrar(resultado, modo, origem):
    linhas = [f"- {_agora()} | correcao_rapida | modo={modo} | origem={origem}"]
    for rel, n in resultado["ok"]:
        linhas.append(f"  - OK: {rel} ({n} operação(ões))")
    for arq, motivo in resultado["falhou"]:
        linhas.append(f"  - FALHOU: {arq} — {motivo}")
    log = ROOT / "comunicacao" / "log.md"
    with log.open("a", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")

    nome = f"{datetime.datetime.now():%Y-%m-%d_%H%M}_resposta_correcao_rapida.md"
    cab = (
        "de: agente-lab\n"
        "para: pesquisador\n"
        "tipo: resposta\n"
        "prioridade: normal\n"
        "acao_permitida: ler\n"
        f"data: {_agora()}\n\n"
    )
    corpo = "\n".join(linhas) + "\n"
    (ROOT / "comunicacao" / "saida" / nome).write_text(cab + corpo, encoding="utf-8")


def executar(operacoes, aplicar=False, origem="pesquisador"):
    """
    Executa uma lista de operações. Retorna {'ok': [...], 'falhou': [...]}.
    Com aplicar=False, mostra o diff e não grava nada.
    """
    if isinstance(operacoes, dict):
        operacoes = operacoes["operacoes"]

    por_arquivo = {}
    for op in operacoes:
        por_arquivo.setdefault(op["arquivo"], []).append(op)

    resultado = {"ok": [], "falhou": []}

    for arquivo, lista in por_arquivo.items():
        try:
            p, rel = _resolver(arquivo)
            original = p.read_text(encoding="utf-8")
            novo = original
            for op in lista:
                novo = _aplicar_operacao(novo, op)
            if novo == original:
                raise ErroCorrecao("nenhuma mudança produzida")
            _validar_conteudo(p, novo, rel)

            diff = "".join(difflib.unified_diff(
                original.splitlines(True), novo.splitlines(True),
                f"{rel} (antes)", f"{rel} (depois)", n=1))
            print(diff[:4000])

            if aplicar:
                p.write_text(novo, encoding="utf-8")
            resultado["ok"].append((rel, len(lista)))

        except (ErroCorrecao, KeyError, OSError) as e:
            resultado["falhou"].append((arquivo, str(e)))

    modo = "aplicar" if aplicar else "simular"
    _registrar(resultado, modo, origem)

    print("\n=== RESUMO ===")
    for rel, n in resultado["ok"]:
        print(f"  OK     {rel} ({n} op.)")
    for arq, motivo in resultado["falhou"]:
        print(f"  FALHOU {arq}: {motivo}")
    if not aplicar:
        print("  (simulação: nada foi gravado — use aplicar=True para gravar)")
    return resultado


def executar_mensagem(caminho):
    """
    Lê uma mensagem de comunicacao/entrada/ e executa a correção nela descrita.
    Exige no cabeçalho:  acao_permitida: aplicar_correcao  e  modo: simular|aplicar
    A especificação fica num bloco ```json ... ``` no corpo da mensagem.
    """
    texto = pathlib.Path(caminho).read_text(encoding="utf-8")
    cab = dict(
        linha.split(":", 1)
        for linha in texto.splitlines()
        if ":" in linha and linha.split(":", 1)[0] in ("acao_permitida", "modo", "para")
    )
    cab = {k: v.strip() for k, v in cab.items()}

    if cab.get("acao_permitida") != "aplicar_correcao":
        raise ErroCorrecao("mensagem sem acao_permitida: aplicar_correcao")
    if cab.get("modo") not in ("simular", "aplicar"):
        raise ErroCorrecao("mensagem sem modo: simular|aplicar")

    m = re.search(r"```json\s*(.*?)```", texto, re.S)
    if not m:
        raise ErroCorrecao("mensagem sem bloco ```json```")
    operacoes = json.loads(m.group(1))

    return executar(operacoes, aplicar=(cab["modo"] == "aplicar"),
                    origem=pathlib.Path(caminho).name)


def varrer_valores_fixos(padroes=None):
    """Lista linhas de código do laboratório que contêm valores para revisar."""
    if padroes is None:
        padroes = r"150\.0|0\.026|11\.7|100\.0|25e-9|resolution_ppw\s*=\s*20|npml_cells\s*=\s*20"
    rx = re.compile(padroes)
    achados = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if any(rel.startswith(x) for x in PROTEGIDOS) or "__pycache__" in rel:
            continue
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(linha):
                achados.append(f"{rel}:{n}: {linha.strip()}")
    return achados


def enviar_para_agente(operacoes, assunto, para="estagiario-codificador", modo="simular"):
    """
    Cria uma tarefa em comunicacao/entrada/ para o agente executar a correção.
    """
    data = datetime.datetime.now()
    nome = f"{data:%Y-%m-%d_%H%M}_tarefa_{assunto}.md"
    cab = (
        "de: pesquisador\n"
        f"para: {para}\n"
        "tipo: tarefa\n"
        "prioridade: normal\n"
        "acao_permitida: aplicar_correcao\n"
        f"modo: {modo}\n"
        f"data: {_agora()}\n\n"
    )
    corpo = "Executar a correção abaixo com a skill_correcao_rapida.executar_mensagem.\n\n"
    corpo += "```json\n" + json.dumps(operacoes, ensure_ascii=False, indent=2) + "\n```\n"
    caminho = ROOT / "comunicacao" / "entrada" / nome
    caminho.write_text(cab + corpo, encoding="utf-8")
    return caminho


# -----------------------------------------------------------------------------
# EXEMPLO (não executa sozinho)
# -----------------------------------------------------------------------------
EXEMPLO = [
    {
        "arquivo": "lib/geometry/gerar_catalogo_geometrico.py",
        "tipo": "substituir",
        "antigo": "generate_22_geometries",
        "novo": "generate_all_geometries",
        "esperado": 1,
        "motivo": "nome novo do dataset",
    },
]
