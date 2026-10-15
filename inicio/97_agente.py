# versao: 2
# inicio/97_agente.py — estagiário do laboratório + registro da reunião da equipe UNIT.
# (1) REGISTRO: tudo que você digita no chat e tudo que o laboratório responde vai para comunicacao/reuniao/AAAA-MM-DD.md
# (2) EQUIPE: 4 estagiários; cada um age só quando é o destinatário (para:) de mensagem de pesquisador ou coordenador
# Permissões: só lê; só escreve em comunicacao/. Nunca chama processar() nem executa experimento. Não define LIMIT/tolerâncias.
import re as _re
import threading as _th
import time as _tm
from datetime import datetime as _dt
from pathlib import Path as _P

_COM = BASE / "comunicacao"
_ENTRADA, _SAIDA, _REUNIAO = _COM / "entrada", _COM / "saida", _COM / "reuniao"
for _d in (_ENTRADA, _SAIDA, _REUNIAO):
    _d.mkdir(parents=True, exist_ok=True)
_LIMITE_REGISTRO = 20000   # caracteres por entrada na reunião (saídas longas são cortadas com aviso)


def _reuniao_registrar(quem, texto):
    try:
        agora = _dt.now()
        corpo = str(texto)
        corte = ""
        if len(corpo) > _LIMITE_REGISTRO:
            corte = f"\n_(saída cortada: {len(corpo)} caracteres)_"
            corpo = corpo[:_LIMITE_REGISTRO]
        with open(_REUNIAO / f"{agora:%Y-%m-%d}.md", "a", encoding="utf-8") as f:
            f.write(f"\n### {agora:%H:%M:%S} · {quem}\n```\n{corpo}\n```{corte}\n")
    except Exception as e:
        print("[reunião] falha ao registrar:", e)


# (1) envolve emit (saídas do laboratório) e processar (comandos digitados) — sem mudar o chat
if callable(globals().get("emit")) and not getattr(globals()["emit"], "_reuniao", False):
    _emit_orig = globals()["emit"]

    def emit(papel, texto, html_extra=""):
        _reuniao_registrar(f"laboratorio:{papel}", texto)
        return _emit_orig(papel, texto, html_extra)
    emit._reuniao = True
    globals()["emit"] = emit

if callable(globals().get("processar")) and not getattr(globals()["processar"], "_reuniao", False):
    _processar_orig = globals()["processar"]

    def processar(msg):
        _reuniao_registrar("pesquisador", msg)
        return _processar_orig(msg)
    processar._reuniao = True
    globals()["processar"] = processar

_reuniao_registrar("sistema", f"sessão iniciada em {_dt.now():%Y-%m-%d %H:%M}")


# (2) EQUIPE DE ESTAGIÁRIOS — cada um só age quando é o destinatário (para:) e a mensagem vem de um autor permitido.
# Mensagem para outro, de outro estagiário, ou de autor não permitido: ignorada ANTES de qualquer chamada de LLM (custo zero).
_AUTORES_PERMITIDOS = {"pesquisador", "coordenador"}
_TIPOS_PERMITIDOS = {"pergunta", "tarefa", "revisao"}
_ACOES_PERMITIDAS = {"ler", "responder", "propor"}
_LIMITE_CHAMADAS_HORA = 10          # teto global de chamadas de LLM por hora (proteção de tokens)
_chamadas_hora = []                 # marcas de tempo das últimas chamadas

ESTAGIARIOS = {
    "estagiario-codificador": {
        "papel": "codificador",
        "funcao": "Propõe experimentos em UNIT-L. Escreve a proposta em texto. Não executa nada e não escreve em propostas/ sem pedido explícito.",
    },
    "estagiario-revisor": {
        "papel": "revisor",
        "funcao": "Revisa protocolos, limites e ressalvas. Aponta riscos e lacunas. Não escolhe tolerâncias nem LIMIT.",
    },
    "estagiario-relator": {
        "papel": "relator",
        "funcao": "Resume resultados e escreve atas. Separa o que foi medido do que foi interpretado. Não conclui física sem checagem independente.",
    },
    "estagiario-auditor": {
        "papel": "revisor",
        "funcao": "Confere integridade (hashes, PASS, pendências, nomes de arquivos) e lista o que falta. Não altera nada.",
    },
}

_REGRAS_COMUNS = (
    " Responda em português, curto e preciso, usando SOMENTE o contexto fornecido. "
    "NÃO executa experimentos, NÃO escolhe tolerâncias nem limites (LIMIT são decisões do pesquisador), "
    "NÃO altera código ou dados. Se faltar informação, faça uma pergunta. "
    "Formato: (1) resposta; (2) o que foi usado do contexto; (3) pendências ou perguntas."
)


def _cabecalho(texto):
    dados = {}
    for linha in texto.splitlines()[:12]:
        m = _re.match(r"^(\w+):\s*(.*)$", linha.strip())
        if m:
            dados[m.group(1).lower()] = m.group(2).strip()
    return dados


def _corpo(texto):
    linhas = texto.splitlines()
    return "\n".join(linhas[8:]) if len(linhas) > 8 else texto


def _log_md(linha):
    try:
        with open(_COM / "log.md", "a", encoding="utf-8") as f:
            f.write(f"- {_dt.now():%Y-%m-%d %H:%M} · {linha}\n")
    except Exception as e:
        print("[log] falha:", e)


def _status(estado, processadas, ultimo=None):
    import json as _json
    (_COM / "status.json").write_text(_json.dumps({
        "agentes": list(ESTAGIARIOS), "estado": estado,
        "ultima_leitura": f"{_dt.now():%Y-%m-%d %H:%M:%S}", "respostas_emitidas": processadas,
        "ultimo_respondido": ultimo,
        "autores_permitidos": sorted(_AUTORES_PERMITIDOS),
        "limite_chamadas_hora": _LIMITE_CHAMADAS_HORA,
        "permissoes": "le tudo; escreve so em comunicacao/; nao executa experimentos; so age quando para: aponta para ele"},
        ensure_ascii=False, indent=1), encoding="utf-8")


def _contexto():
    p = BASE / "_mapa" / "CONTEXTO_COMPILADO.md"
    return p.read_text(encoding="utf-8", errors="replace")[:30000] if p.exists() else "(contexto compilado ainda não gerado)"


def _cota_disponivel():
    agora = _tm.time()
    _chamadas_hora[:] = [t for t in _chamadas_hora if agora - t < 3600]
    return len(_chamadas_hora) < _LIMITE_CHAMADAS_HORA


def _decidir(arq):
    """Devolve o nome do estagiário que deve responder, ou None. Não gasta tokens."""
    cab = _cabecalho(arq.read_text(encoding="utf-8", errors="replace"))
    if cab.get("de") not in _AUTORES_PERMITIDOS:
        return None
    if cab.get("para") not in ESTAGIARIOS:
        return None
    if cab.get("tipo") not in _TIPOS_PERMITIDOS or cab.get("acao_permitida") not in _ACOES_PERMITIDAS:
        return None
    return cab.get("para")


def _responder(arq, nome_estagiario):
    texto = arq.read_text(encoding="utf-8", errors="replace")
    cab = _cabecalho(texto)
    info = ESTAGIARIOS[nome_estagiario]
    system = f"Você é {nome_estagiario} do laboratório UNIT-001. Sua função: {info['funcao']}" + _REGRAS_COMUNS
    user = f"CONTEXTO DO LABORATÓRIO:\n{_contexto()}\n\nMENSAGEM RECEBIDA ({arq.name}):\n{_corpo(texto)}"
    _chamadas_hora.append(_tm.time())
    resposta, modelo = chamar(info["papel"], system, user, max_tokens=4000, temperature=0.2)
    saida = _SAIDA / arq.name
    saida.write_text(
        f"de: {nome_estagiario}\npara: {cab.get('de')}\ntipo: resposta\nprioridade: {cab.get('prioridade', 'normal')}\n"
        f"acao_permitida: ler\ndata: {_dt.now():%Y-%m-%d %H:%M}\nreferencia: entrada/{arq.name}\nmodelo: {modelo}\n\n"
        f"{resposta}\n", encoding="utf-8")
    return saida.name


def _ciclo_estagiarios():
    emitidas, ultimo = 0, None
    for arq in sorted(_ENTRADA.glob("*.md")):
        if (_SAIDA / arq.name).exists():
            continue                      # já respondida: não repete
        try:
            nome = _decidir(arq)
            if nome is None:
                continue                  # não é para nós: ignora sem custo
            if not _cota_disponivel():
                (_SAIDA / arq.name).write_text(
                    f"de: {nome}\ntipo: aviso\n\nLimite de {_LIMITE_CHAMADAS_HORA} chamadas por hora atingido. "
                    "Mensagem não respondida; reenvie depois.\n", encoding="utf-8")
                _log_md(f"cota atingida: `{arq.name}` não respondida")
                continue
            out = _responder(arq, nome)
            emitidas += 1
            ultimo = f"{nome}: {arq.name}"
            _log_md(f"{nome} respondeu `{arq.name}` → saida/{out}")
            _reuniao_registrar(nome, f"respondeu {arq.name}")
        except Exception as e:
            (_SAIDA / arq.name).write_text(f"de: agente-lab\ntipo: aviso\n\nerro ao processar: {type(e).__name__}: {e}\n",
                                           encoding="utf-8")
            _log_md(f"ERRO ao processar `{arq.name}`: {type(e).__name__}")
    return emitidas, ultimo


_total = globals().get("_ESTAGIARIOS_TOTAL", 0)


def _loop_estagiarios(intervalo=60):
    global _total
    while True:
        try:
            emitidas, ultimo = _ciclo_estagiarios()
            _total += emitidas
            globals()["_ESTAGIARIOS_TOTAL"] = _total
            _status("online", _total, ultimo)
        except Exception as e:
            _status(f"erro: {type(e).__name__}", _total)
        _tm.sleep(intervalo)


_thread_antiga = globals().get("_ESTAGIARIOS_THREAD")
if _thread_antiga is None or not _thread_antiga.is_alive():
    _thread_antiga = _th.Thread(target=_loop_estagiarios, daemon=True, name="estagiarios-lab")
    _thread_antiga.start()
    globals()["_ESTAGIARIOS_THREAD"] = _thread_antiga
    _log_md("equipe de estagiários ativa: " + ", ".join(ESTAGIARIOS))
    print("[estagiários] ativos:", ", ".join(ESTAGIARIOS))
else:
    print("[estagiários] já estavam ativos")
