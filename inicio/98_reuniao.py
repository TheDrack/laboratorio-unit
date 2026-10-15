# versao: 2
# inicio/98_reuniao.py — conversa simples na reunião pelo próprio chat.
#   @relator resuma o T2            -> envia pergunta ao estagiario-relator (outros: @codificador @revisor @auditor)
#   @revisor tarefa: revise X       -> tipo "tarefa" (padrão é pergunta)
#   /reuniao                        -> mostra as últimas respostas e o que ainda está pendente
#   qualquer outra coisa            -> segue para o laboratório normalmente (comandos /medir, /rodar etc.)
# Respostas novas do estagiário são publicadas no chat automaticamente (vigia a cada 20 s, sem LLM, sem repetir).
# Não gasta tokens: só grava um arquivo em comunicacao/entrada/ (quem responde é o 97_agente).
import re as _re98
from datetime import datetime as _dt98

_ALIAS_ESTAGIARIO = {
    "codificador": "estagiario-codificador",
    "revisor": "estagiario-revisor",
    "relator": "estagiario-relator",
    "auditor": "estagiario-auditor",
}
_TIPOS_FALA = {"pergunta", "tarefa", "revisao"}

if callable(globals().get("processar")) and not getattr(globals()["processar"], "_fala_simples", False):
    _processar_antes = globals()["processar"]

    def _slug98(texto):
        palavras = _re98.findall(r"[A-Za-zÀ-ÿ0-9]+", texto.lower())[:6]
        return "_".join(palavras)[:60] or "mensagem"

    def _ajuda98():
        emit("reuniao", "Equipe: " + " · ".join(f"@{k}" for k in _ALIAS_ESTAGIARIO)
             + "\nExemplos: `@relator resuma o T2` · `@revisor tarefa: revise a calibração`\n`/reuniao` mostra as respostas.")

    def _falar98(texto):
        resto = texto[1:].strip()
        partes = resto.split(None, 1)
        if not partes or partes[0].lower() not in _ALIAS_ESTAGIARIO:
            _ajuda98()
            return None
        nome = _ALIAS_ESTAGIARIO[partes[0].lower()]
        corpo = partes[1] if len(partes) > 1 else ""
        tipo = "pergunta"
        m = _re98.match(r"^(pergunta|tarefa|revis[aã]o)\s*:\s*(.*)$", corpo, _re98.IGNORECASE | _re98.DOTALL)
        if m:
            tipo = {"revisão": "revisao", "revisao": "revisao"}.get(m.group(1).lower(), m.group(1).lower())
            corpo = m.group(2)
        if not corpo.strip():
            emit("reuniao", f"Escreva a mensagem depois do nome. Ex.: `@{partes[0]} sua pergunta`")
            return None
        agora = _dt98.now()
        nome_arq = f"{agora:%Y-%m-%d_%H%M}_{tipo}_{_slug98(corpo)}.md"
        (_ENTRADA / nome_arq).write_text(
            f"de: pesquisador\npara: {nome}\ntipo: {tipo}\nprioridade: normal\nacao_permitida: responder\n"
            f"data: {agora:%Y-%m-%d %H:%M}\n\n{corpo.strip()}\n", encoding="utf-8")
        _log_md(f"pesquisador enviou `{nome_arq}` para {nome}")
        _reuniao_registrar("pesquisador->" + nome, corpo.strip())
        emit("reuniao", f"✔ enviado a {nome}. A resposta aparece aqui no chat quando estiver pronta.")
        return None

    def _respostas98():
        return [p for p in _SAIDA.glob("*.md") if not p.name.startswith(("_", "."))]

    def _mostrar98():
        respostas = sorted(_respostas98(), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        pendentes = [p.name for p in _ENTRADA.glob("*.md")
                     if not p.name.startswith(("_", ".")) and not (_SAIDA / p.name).exists()]
        if not respostas and not pendentes:
            emit("reuniao", "Ainda não há mensagens na reunião.")
            return None
        blocos = []
        for p in respostas:
            txt = p.read_text(encoding="utf-8", errors="replace")
            corpo = txt.split("\n\n", 1)[1] if "\n\n" in txt else txt
            de = _cabecalho(txt).get("de", "?")
            blocos.append(f"**{de}** · _{p.name}_\n{corpo[:1500]}")
        if pendentes:
            blocos.append("⏳ aguardando resposta: " + ", ".join(pendentes[:5]))
        emit("reuniao", "\n\n".join(blocos))
        return None

    def _bloco_resposta98(p):
        txt = p.read_text(encoding="utf-8", errors="replace")
        corpo = txt.split("\n\n", 1)[1] if "\n\n" in txt else txt
        return f"**{_cabecalho(txt).get('de', '?')}** · _{p.name}_\n{corpo[:1500]}"

    # VIGIA: publica no chat as respostas NOVAS assim que aparecem em saida/ (sem LLM, sem repetir)
    _ja_publicadas98 = set(globals().get("_JA_PUBLICADAS98", set()))
    if not globals().get("_JA_PUBLICADAS98"):
        # na primeira vez, o que já existe não é publicado de novo (fica disponível em /reuniao)
        _ja_publicadas98 = {p.name for p in _respostas98()}
        globals()["_JA_PUBLICADAS98"] = _ja_publicadas98

    def _anunciar_novas98():
        for p in sorted(_respostas98(), key=lambda q: q.stat().st_mtime):
            if p.name in _ja_publicadas98:
                continue
            _ja_publicadas98.add(p.name)
            try:
                emit("reuniao", "🟢 nova resposta\n" + _bloco_resposta98(p))
            except Exception as e:
                print("[reunião] falha ao publicar:", e)

    def _vigia98(intervalo=20):
        while True:
            try:
                _anunciar_novas98()
            except Exception as e:
                print("[reunião] vigia:", e)
            _tm98.sleep(intervalo)

    import threading as _th98, time as _tm98
    _vigia_antigo = globals().get("_VIGIA98_THREAD")
    if _vigia_antigo is None or not _vigia_antigo.is_alive():
        _vigia_antigo = _th98.Thread(target=_vigia98, daemon=True, name="vigia-reuniao")
        _vigia_antigo.start()
        globals()["_VIGIA98_THREAD"] = _vigia_antigo

    def processar(msg):
        texto = (msg or "").strip()
        if texto.startswith("@"):
            _reuniao_registrar("pesquisador", texto)
            return _falar98(texto)
        if texto.lower() in ("/reuniao", "/reunião"):
            _reuniao_registrar("pesquisador", texto)
            return _mostrar98()
        return _processar_antes(msg)
    processar._fala_simples = True
    globals()["processar"] = processar
