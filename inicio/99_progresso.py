# versao: 2
# inicio/99_progresso.py — previsão de tempo restante para experimentos (UNIT-L e pipeline).
# Lê as linhas de andamento que o laboratório já emite ("[i/N] ... iniciando", "[i/N] ... ok em Xs")
# e publica no chat, a cada ponto concluído, quantos faltam, a média, a previsão e a hora de término.
# /progresso mostra a previsão no momento do comando. Contagem regressiva a cada 30 s na telemetria. Sem tokens.
import re as _re99
from datetime import datetime as _dt99, timedelta as _td99

_PROG99 = globals().get("_PROG99", {"total": None, "concluidos": {}, "inicio": None, "ativo": False})
globals()["_PROG99"] = _PROG99

_RE_INICIO99 = _re99.compile(r"\[(\d+)/(\d+)\].*iniciando")
_RE_OK99 = _re99.compile(r"\[(\d+)/(\d+)\].*ok em ([\d.]+)s")
_RE_FALHA99 = _re99.compile(r"\[(\d+)/(\d+)\].*(erro|inviável|falhou)", _re99.IGNORECASE)


def _fmt_tempo99(segundos):
    s = int(round(segundos))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600} h {(s % 3600) // 60:02d} min"


def _previsao99():
    p = _PROG99
    total = p["total"]
    feitos = list(p["concluidos"].values())
    if not total or not feitos:
        return None
    restam = total - len(feitos)
    media = sum(feitos) / len(feitos)
    rapido, lento = min(feitos), max(feitos)
    previsao = restam * media
    agora = _dt99.now()
    termino = agora + _td99(seconds=previsao)
    return {
        "total": total, "feitos": len(feitos), "restam": restam, "media": media,
        "previsao": previsao, "faixa": (restam * rapido, restam * lento), "termino": termino,
        "decorrido": (agora - p["inicio"]).total_seconds() if p["inicio"] else None,
    }


def _texto_previsao99(v, cabecalho=None):
    if v is None:
        return "Ainda não há pontos concluídos para estimar."
    if v["restam"] == 0:
        return f"✔ concluído: {v['feitos']}/{v['total']} pontos."
    decor = f" · decorrido {_fmt_tempo99(v['decorrido'])}" if v["decorrido"] is not None else ""
    return (f"⏱ {cabecalho or ''}{v['feitos']}/{v['total']} concluídos · restam {v['restam']} · "
            f"média {_fmt_tempo99(v['media'])}/ponto{decor}\n"
            f"   previsão para terminar: ~{_fmt_tempo99(v['previsao'])} "
            f"(faixa {_fmt_tempo99(v['faixa'][0])} – {_fmt_tempo99(v['faixa'][1])}) · término ~{v['termino']:%H:%M}")


def _observar99(texto):
    """Atualiza o estado a partir de uma linha do laboratório. Devolve a previsão se houve ponto concluído."""
    if not isinstance(texto, str):
        return None
    m = _RE_INICIO99.search(texto)
    if m and (m.group(1) == "1" or _PROG99["total"] is None):
        _PROG99.update({"total": int(m.group(2)), "concluidos": {}, "inicio": _dt99.now(), "ativo": True})
        return None
    m = _RE_OK99.search(texto)
    if m:
        _PROG99["total"] = int(m.group(2))
        _PROG99["concluidos"][int(m.group(1))] = float(m.group(3))
        _PROG99["ultimo_ponto"] = _dt99.now()
        return _previsao99()
    m = _RE_FALHA99.search(texto)
    if m:
        _PROG99["total"] = int(m.group(2))
        _PROG99["concluidos"][int(m.group(1))] = 0.0   # ponto com falha conta como concluído (sem tempo)
        _PROG99["ultimo_ponto"] = _dt99.now()
        return _previsao99()
    return None


# CONTAGEM REGRESSIVA: a cada 30 s, publica na MESMA entrada de telemetria do sentinela (ela se atualiza no lugar).
# Para quando o experimento termina, é interrompido ou fica parado por mais de 15 min.
def _tick99():
    p = _PROG99
    v = _previsao99()
    if not v or v["restam"] == 0 or not p.get("ultimo_ponto"):
        return
    ex = globals().get("EXEC") or {}
    if isinstance(ex, dict) and ex.get("thread") is not None and not ex["thread"].is_alive():
        return
    decorrido_ultimo = (_dt99.now() - p["ultimo_ponto"]).total_seconds()
    if decorrido_ultimo > 900:
        return
    restante = max(0.0, v["previsao"] - decorrido_ultimo)
    fim = _dt99.now() + _td99(seconds=restante)
    _emit_99("tele", f"⏳ ponto {v['feitos']}/{v['total']} · faltam ~{_fmt_tempo99(restante)} · término ~{fim:%H:%M}")


def _loop_tick99(intervalo=30):
    import time as _t99
    while True:
        try:
            _tick99()
        except Exception as e:
            print("[progresso] contagem:", e)
        _t99.sleep(intervalo)


import threading as _th99
_tick_antigo = globals().get("_TICK99_THREAD")
if _tick_antigo is None or not _tick_antigo.is_alive():
    _tick_antigo = _th99.Thread(target=_loop_tick99, daemon=True, name="contagem-progresso")
    _tick_antigo.start()
    globals()["_TICK99_THREAD"] = _tick_antigo

# envolve emit: a cada ponto concluído, publica a previsão logo após a linha do laboratório
if callable(globals().get("emit")) and not getattr(globals()["emit"], "_progresso", False):
    _emit_99 = globals()["emit"]

    def emit(papel, texto, html_extra=""):
        resultado = _emit_99(papel, texto, html_extra)
        try:
            v = _observar99(texto)
            if v is not None:
                _emit_99("progresso", _texto_previsao99(v))
        except Exception as e:
            print("[progresso] falha:", e)
        return resultado
    emit._progresso = True
    globals()["emit"] = emit

# comando /progresso (sem tocar nos demais comandos)
if callable(globals().get("processar")) and not getattr(globals()["processar"], "_progresso", False):
    _processar_99 = globals()["processar"]

    def processar(msg):
        if (msg or "").strip().lower() in ("/progresso", "/progresso?"):
            v = _previsao99()
            _emit_99("progresso", _texto_previsao99(v) if v else "Nenhum experimento em andamento.")
            return None
        return _processar_99(msg)
    processar._progresso = True
    globals()["processar"] = processar
