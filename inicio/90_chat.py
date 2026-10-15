# versao: 11
# inicio/90_chat.py — interface do chat (abrir_chat é chamado pelo runner ao final)
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 10 · INTERFACE — CHAT INSTANTÂNEO
# Texto livre  → Codificador (LLM) escreve código usando o framework
# /comandos    → pipeline/testes determinísticos (sem LLM)         /ajuda lista tudo
# ═══════════════════════════════════════════════════════════════
import html as _html
import os, signal, time
import shlex
from IPython.display import display, HTML, update_display

EST = {"unl": None, "unl_nome": None, "codigo": None, "instrucao": "", "revisao": "", "modelos": {}, "ultimo_run": None, "timeout": 1800}
_UI = {"feed": None, "html": None, "log": [], "disp": False, "worker_on": False, "ver": 0, "rend": -1}

AJUDA = """Texto livre ........ o Codificador descreve o EXPERIMENTO em UNIT-L (linguagem semântica; sem Python); o laboratório valida e executa
/experimento [nome] .. roda experimentos/nome.unl (sem nome: lista; ex.: T2_leve, T2_convergencia)   |  /validar  valida o pendente e mostra o plano/custo
/medir ppw=N ........ mede tempo e memória de UM ponto (ex.: /medir ppw=60 backend=iterative) — diagnóstico de hardware
/linguagem ........... referência da UNIT-L (primitivas registradas)   |  colar um bloco ```unl … ``` define o experimento pendente
/pipeline [opções] ... gera os casos AUTOMATICAMENTE (geometrias × frequências → NPZ padrão, retoma o que já existe)
     opções: --refazer  max=N  seeds=1003,1004  geometrias=ORDERED,RANDOM  freq=280,300  spec=nome
/script nome ......... roda um script pronto (scripts_prontos/) pelo AOP; sem nome lista
/gerar ............... grava o catálogo canônico de geometrias (22 geometrias / 66 casos)
/testes .............. lista testes registrados   |  /teste nome1,nome2 [k=v ...]  roda sobre os casos gerados
/catalogo ............ solvers, campos, geometrias, testes, verificadores registrados  |  /plugins recarrega lib/framework/plugins
/spec ................ mostra a spec AOP ativa | /spec nome ativa specs/nome.aop | /specs lista | /spec salvar nome
                       (colar um bloco ```aop-dsl … ``` no chat também ativa, depois de validar)
/rodar ............... roda o pendente (experimento UNIT-L ou código em bloco ```python)   |  /codigo mostra
/modelos [testar] .... LLMs descobertas, descontinuadas e candidatos por papel
/runs ................ últimos runs   |  /pacote [pergunta]  pacote para IA avançada
/restricao | /hipotese | /interpretacao  texto ... registra decisão do pesquisador
/timeout N ........... segundos (padrão 1800)   |  /limpar"""



_CID = {"n": 0}


def _botao_copiar(texto, rotulo="📋 copiar"):
    """Botão que copia o texto inteiro para a área de transferência (funciona no Colab/Jupyter)."""
    _CID["n"] += 1
    uid = f"cp{_CID['n']}"
    payload = _html.escape(str(texto), quote=True)
    return (f"<span style='display:inline-block;margin:4px 0'>"
            f"<textarea id='{uid}' style='position:absolute;left:-9999px;top:-9999px'>{payload}</textarea>"
            f"<button onclick=\"(function(b){{var t=document.getElementById('{uid}').value;"
            f"(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){{b.innerText='✔ copiado'}},"
            f"function(){{var e=document.getElementById('{uid}');e.select();document.execCommand('copy');b.innerText='✔ copiado'}});"
            f"setTimeout(function(){{b.innerText='{rotulo}'}},1600)}})(this)\" "
            f"style='padding:3px 10px;font-size:12px;border:1px solid #9aa0a6;border-radius:6px;background:#fff;cursor:pointer'>{rotulo}</button></span>")

def _bolha(papel, texto, html_extra=""):
    cor = {"voce": "#d2e3fc", "lab": "#f1f3f4", "erro": "#fce8e6", "ok": "#e6f4ea"}.get(papel, "#f1f3f4")
    lado = "flex-end" if papel == "voce" else "flex-start"
    botao = _botao_copiar(texto) if papel != "voce" else ""
    corpo = (f"<div style='text-align:right;margin-bottom:2px'>{botao}</div>" if botao else "") + \
            f"<pre style='margin:0;white-space:pre-wrap;font-family:inherit;font-size:13px'>{_html.escape(str(texto))}</pre>{html_extra}"
    return f"<div style='display:flex;justify-content:{lado};margin:4px 0'><div style='max-width:92%;background:{cor};color:#202124;padding:8px 12px;border-radius:12px'>{corpo}</div></div>"


def _redesenhar(forcar=False):
    """Renderiza o histórico inteiro num único painel com rolagem INTERNA (a barra de entrada fica fora dele).
    Só repinta se houve mensagem nova desde o último desenho (ou se forçado): evita tremor no timer."""
    if not forcar and _UI.get("rend") == _UI.get("ver"):
        return
    _UI["rend"] = _UI.get("ver")
    if not _UI.get("disp") and _UI["html"] is None:
        if _UI["log"]:
            p, t, _ = _UI["log"][-1]
            print(f"[{p}] {t}")
        return
    transcript = "\n\n".join(f"[{p}] {t[:4000]}" for p, t, _x in _UI["log"][-120:])
    topo = f"<div style='text-align:right;margin-bottom:6px'>{_botao_copiar(transcript, '📋 copiar tudo (chat inteiro)')}</div>"
    blocos = "".join(_bolha(p, t, x) for p, t, x in _UI["log"])
    # rola o painel para o fim a cada redesenho (onerror de imagem falsa roda o JS sem <script>)
    timer = ("if(!window._unitT){window._unitT=setInterval(function(){try{google.colab.kernel.invokeFunction('unit_chat_refresh',[],{})}catch(e){}},3000)}" if _UI.get("colab") else "")
    rolar = "<img src='x' style='display:none' onerror=\"var d=document.getElementById('feedbox');if(d){d.scrollTop=d.scrollHeight}" + timer + "\">"
    conteudo = (f"<div id='feedbox' style='height:520px;overflow-y:auto;border:1px solid #dadce0;padding:8px;"
                f"box-sizing:border-box;font-family:sans-serif'>{topo}{blocos}</div>{rolar}")
    if _UI.get("disp"):
        # atualização via mensagem de saída (iopub): aparece ao vivo, mesmo a partir de threads em segundo plano
        update_display(HTML(conteudo), display_id="unit-feed")
    else:
        _UI["html"].value = conteudo


LOG_MAX = 300          # mantém só as últimas mensagens na tela (menos repintura)
REDESENHO_S = 1.5      # no máximo um redesenho a cada 1,5 s durante execuções (sem tremor)
_REP = {"sujo": False, "ultimo": 0.0, "thread": None}


def _agendar_redesenho():
    """Agrupa várias mensagens num único redesenho; evita repintar o painel a cada evento."""
    import threading
    _REP["sujo"] = True
    if _REP["thread"] is not None and _REP["thread"].is_alive():
        return

    def _laco():
        while _REP["sujo"]:
            espera = REDESENHO_S - (time.time() - _REP["ultimo"])
            if espera > 0:
                time.sleep(espera)
            _REP["sujo"] = False
            _REP["ultimo"] = time.time()
            try:
                _redesenhar()
            except Exception:
                pass
    _REP["thread"] = threading.Thread(target=_laco, daemon=True)
    _REP["thread"].start()


def emit(papel, texto, html_extra=""):
    _UI["ver"] = _UI.get("ver", 0) + 1
    if papel == "tele":
        # telemetria (sentinela/monitor): UMA entrada que se atualiza; o histórico completo fica recolhido
        tele = _UI.setdefault("tele", [])
        tele.append(str(texto))
        del tele[:-400]
        extra = _detalhes(f"telemetria do run ({len(tele)} eventos) — clique para ver", "\n".join(tele[-300:]))
        novo = ("tele", str(texto)[:300], extra)
        for k in range(len(_UI["log"]) - 1, -1, -1):
            if _UI["log"][k][0] == "tele":
                _UI["log"][k] = novo
                break
        else:
            _UI["log"].append(novo)
    else:
        _UI["log"].append((papel, str(texto), html_extra))
    if len(_UI["log"]) > LOG_MAX:
        del _UI["log"][: len(_UI["log"]) - LOG_MAX]
    # mensagens do usuário e comandos: redesenho imediato; saídas de execução: agrupadas
    if papel in ("voce", "erro") and not (_REP["thread"] is not None and _REP["thread"].is_alive()):
        _redesenhar(forcar=True)
        _REP["ultimo"] = time.time()
    else:
        _agendar_redesenho()

def _detalhes(titulo, texto):
    return (f"<details style='margin-top:6px'><summary style='cursor:pointer'>{_html.escape(titulo)}</summary>"
            f"<div style='text-align:right'>{_botao_copiar(texto, '📋 copiar ' + titulo[:18])}</div>"
            f"<pre style='white-space:pre-wrap;font-size:12px;max-height:420px;overflow:auto'>{_html.escape(texto)}</pre></details>")


def _achados_txt(achados):
    return "\n".join(f"  {'✔' if lv == 'OK' else '⚠' if lv == 'AVISO' else '✗'} {n}: {d}" for lv, n, d in achados)


def _monitor(run_dir, rotulo, stop):
    """Lê <run>/progress.jsonl e mostra no chat: fase, ponto, memória do processo e memória disponível."""
    import json as _j
    p = Path(run_dir) / "progress.jsonl"
    vistos = 0
    while not stop.is_set():
        try:
            if p.exists():
                linhas = p.read_text(encoding="utf-8").splitlines()
                for ln in linhas[vistos:]:
                    ev = _j.loads(ln)
                    emit("tele", f"⏱ [{ev['fonte']}] {ev['msg']} · RAM processo {ev['mem_gb']:.2f} GB · disponível {ev['mem_disp_gb']:.1f} GB")
                vistos = len(linhas)
        except Exception:
            pass
        stop.wait(2.0)


EXEC = {"thread": None, "run_dir": None, "pausado": False}


def _executar(codigo, rotulo, autocorrigir=False, revisao="(código do framework / script pronto: sem revisão por LLM)", prov_extra=None, arquivos=None):
    """Roda em SEGUNDO PLANO: o chat continua responsivo (botões ⏸ ▶ ⏹ funcionam durante a execução)."""
    import threading
    if EXEC["thread"] is not None and EXEC["thread"].is_alive():
        return emit("erro", "já existe uma execução em andamento. Use ⏸ pausar, ⏹ parar, ou aguarde terminar.")
    PENDING_FILES.clear()
    PENDING_FILES.update(arquivos or {})
    permite = aop_aplicar_agente()
    prov_extra = dict(prov_extra or {})
    prov_extra["aop_spec_sha256"] = aop_dsl.parse(AOP["texto"]).sha256
    prov_extra["aop_spec_nome"] = AOP["nome"]
    emit("lab", f"⚙️ {rotulo} — timeout {EST['timeout']}s (AOP: preflight → execução → reverificação)")
    stop = threading.Event()
    th = {"mon": None}

    def _log(m):
        emit("lab", m)
        if th["mon"] is None and "run_" in m and "executando" in m:
            rid = re.search(r"run_\d+", m)
            if rid:
                EXEC["run_dir"] = RUNS / rid.group(0)
                th["mon"] = threading.Thread(target=_monitor, args=(RUNS / rid.group(0), rotulo, stop), daemon=True)
                th["mon"].start()

    def _alvo():
        try:
            rel, status, run_id, final = rodar_com_autocorrecao(codigo, rotulo, revisao, EST["timeout"], autocorrigir and permite,
                                                                 log=_log, revisar_corrigido=False, prov_extra=prov_extra)
            EST["ultimo_run"] = run_id
            emit("ok" if "validação PASS" in str(status) else "erro", f"{run_id} · {status}\n" + "\n".join(rel.splitlines()[:22]),
                 _detalhes("relatório completo (copiável)", rel))
        except Exception as e:
            emit("erro", f"execução terminou com erro: {type(e).__name__}: {e}")
        finally:
            stop.set()
            EXEC["run_dir"] = None
            EXEC["pausado"] = False

    EXEC["thread"] = threading.Thread(target=_alvo, daemon=True)
    EXEC["thread"].start()
    return None, "em andamento", None, codigo


def _pids_do_run(run_dir):
    """Processos do run (launcher + descendentes, incluindo os filhos de cada ponto)."""
    rd = str(run_dir)
    filhos, raizes = {}, []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            filhos.setdefault(ppid, []).append(int(d))
            with open(f"/proc/{d}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="ignore")
            if rd in cmd:
                raizes.append(int(d))
        except Exception:
            continue
    saida, pilha = [], list(raizes)
    while pilha:
        p = pilha.pop()
        saida.append(p)
        pilha.extend(filhos.get(p, []))
    return saida


def parar_execucao():
    rd = EXEC.get("run_dir")
    if not rd:
        return emit("erro", "nenhuma execução ativa para parar.")
    (Path(rd) / "parar").write_text("parar", encoding="utf-8")   # o motor marca os pontos restantes como interrompidos
    pids = _pids_do_run(rd)
    for p in pids:
        try:
            os.kill(p, signal.SIGCONT)
            os.kill(p, signal.SIGTERM)
        except Exception:
            pass
    def _forcar():
        for p in _pids_do_run(rd):
            try:
                os.kill(p, signal.SIGKILL)
            except Exception:
                pass
    import threading as _th
    _th.Timer(3.0, _forcar).start()
    EXEC["pausado"] = False
    emit("lab", f"⏹ parada solicitada: {len(pids)} processo(s) encerrado(s). O run termina e registra o estado.")


def pausar_execucao():
    rd = EXEC.get("run_dir")
    if not rd:
        return emit("erro", "nenhuma execução ativa para pausar.")
    for p in _pids_do_run(rd):
        try:
            os.kill(p, signal.SIGSTOP)
        except Exception:
            pass
    EXEC["pausado"] = True
    emit("lab", "⏸ pausado: processos congelados. Atenção: o timeout do run continua contando (tempo de parede).")


def continuar_execucao():
    rd = EXEC.get("run_dir")
    if not rd:
        return emit("erro", "nenhuma execução ativa.")
    for p in _pids_do_run(rd):
        try:
            os.kill(p, signal.SIGCONT)
        except Exception:
            pass
    EXEC["pausado"] = False
    emit("lab", "▶ execução retomada.")

def _kv(args):
    out, flags = {}, set()
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            out[k] = v
        else:
            flags.add(a)
    return out, flags


def _lista(v, conv=str):
    return [conv(x) for x in v.split(",") if x.strip()]


def cmd_pipeline(args):
    kv, flags = _kv(args)
    texto = AOP["texto"]
    if "spec" in kv:
        texto = (SPECS_DIR / f"{kv['spec']}.aop").read_text(encoding="utf-8")
    ov = []
    if "max" in kv: ov.append(f"    max_cases: {int(kv['max'])}")
    if "seeds" in kv:
        ov.append(f"    seeds: {_lista(kv['seeds'], int)}")
        if "geometrias" not in kv: ov.append('    geometrias: ["RANDOM"]')
    if "geometrias" in kv: ov.append(f"    geometries: {_lista(kv['geometrias'])}".replace("'", '"'))
    if "freq" in kv: ov.append(f"    frequencies_thz: {_lista(kv['freq'], float)}")
    if ov:
        texto += "\nSTATE Override {\n" + "\n".join(ov).replace("geometrias:", "geometries:") + "\n}\n"
    antigo = dict(AOP)
    try:
        aop_ativar(texto, AOP["nome"] + (" + override" if ov else ""))
        resume = "--refazer" not in flags
        codigo = f"from lib.framework.pipeline import run_pipeline_in_run\nrun_pipeline_in_run(resume={resume})\n"
        _executar(codigo, "pipeline automático (framework)")
    finally:
        AOP.update(antigo)


def cmd_teste(args):
    if not args:
        return emit("erro", "uso: /teste nome1,nome2 [chave=valor ...]   (veja /testes)")
    nomes = _lista(args[0])
    kv, _ = _kv(args[1:])
    import ast as _ast
    params = {}
    for k, v in kv.items():
        try: params[k] = _ast.literal_eval(v)
        except Exception: params[k] = v
    codigo = f"from lib.framework.pipeline import run_tests_in_run\nrun_tests_in_run({nomes!r}, {params!r})\n"
    _executar(codigo, f"teste(s) {','.join(nomes)} {params if params else ''}")


def cmd_spec(args):
    try:
        if not args:
            return emit("lab", f"spec ativa: {AOP['nome']}\n\n{AOP['texto']}")
        if args[0] == "salvar" and len(args) > 1:
            (SPECS_DIR / f"{args[1]}.aop").write_text(AOP["texto"], encoding="utf-8")
            return emit("ok", f"spec salva em specs/{args[1]}.aop")
        ach = aop_carregar(args[0])
        emit("ok", f"spec «{args[0]}» ativada\n" + _achados_txt(ach))
    except Exception as e:
        emit("erro", f"{type(e).__name__}: {e}")


def cmd_catalogo(_):
    cat = FWR.catalog()
    linhas = []
    for tipo, itens in cat.items():
        linhas.append(f"{tipo.upper()}")
        for n, m in itens.items():
            linhas.append(f"  - {n}" + (f": {m['description']}" if m.get("description") else ""))
    emit("lab", "\n".join(linhas))


def cmd_testes(_):
    emit("lab", "\n".join(f"  - {n}: {FWR.TESTS.meta(n).get('description', '')}" for n in FWR.TESTS.names()))


def cmd_rodar(_):
    if EST["unl"] and not EST["codigo"]:
        return _rodar_unl(EST["unl"], EST["unl_nome"] or "(experimento do chat)")
    if not EST["codigo"]:
        return emit("erro", "nenhum código pendente. Escreva uma instrução em texto livre ou cole um bloco ```python.")
    chk = checar_sintaxe(EST["codigo"])
    if chk:
        return emit("erro", f"erro de sintaxe: {chk}")
    run_id, status, final = _executar(EST["codigo"], EST["instrucao"] or "(código colado)", autocorrigir=True, revisao=EST["revisao"] or "(sem revisão)",
                                      prov_extra={"modelos": dict(EST["modelos"])})
    if final != EST["codigo"]:
        EST["codigo"] = final
        emit("lab", "o código pendente foi atualizado pela autocorreção (ver diff no relatório).")


def cmd_modelos(args):
    emit("lab", "⏳ consultando provedores…" if args else "modelos:")
    emit("lab", diagnostico_modelos(testar=bool(args)))


def cmd_runs(_):
    rs = sorted(p.name for p in RUNS.glob("run_*"))[-10:]
    emit("lab", "\n".join(rs) or "(nenhum run ainda)")


def cmd_pacote(args):
    if not EST["ultimo_run"]:
        return emit("erro", "ainda não há run.")
    p = gerar_pacote(EST["ultimo_run"], " ".join(args))
    emit("ok", f"pacote de {EST['ultimo_run']} gerado ({len(p)} caracteres). Copie abaixo e cole na IA avançada.", _detalhes("pacote completo", p)
         + f"<textarea id='pk' style='position:absolute;left:-9999px'>{_html.escape(p)}</textarea>"
         + "<button onclick=\"navigator.clipboard.writeText(document.getElementById('pk').value).then(()=>this.innerText='✔ copiado')\" style='margin-top:6px;padding:6px 12px'>📋 copiar pacote</button>")


def cmd_decisao(tipo, args):
    if not args:
        return emit("erro", f"uso: /{tipo} texto")
    registrar_decisao(" ".join(args), "pesquisador", EST["ultimo_run"], tipo)
    emit("ok", f"{tipo} registrada.")


def cmd_gerar(_):
    codigo, _sha = carregar_script_pronto("gerar_catalogo_geometrico")
    _executar(codigo, "catálogo canônico de geometrias (gerador → dados/UNIT001/geometria)")


def cmd_script(args):
    if not args:
        return emit("lab", "scripts prontos: " + ", ".join(listar_scripts_prontos()) + "\nuso: /script nome")
    codigo, sha = carregar_script_pronto(args[0])
    _executar(codigo, f"[script pronto] {args[0]}", prov_extra={"script_pronto": {"nome": args[0], "sha256": sha}})


def _achados_unl(achados):
    return "\n".join(f"  {'✔' if lv == 'OK' else '⚠' if lv == 'AVISO' else '✗'} {n}: {d}" for lv, n, d in achados)


def _validar_unl(texto):
    """-> (ok, achados, plano). Erros de sintaxe viram achados (não levantam)."""
    from lib.framework import experiment as X
    try:
        exp = X.parse(texto)
    except X.UNLError as e:
        return False, [("FALHA", "unl:sintaxe", str(e))], None
    ach, plano = X.validate(exp, aop_runtime())
    return not X.has_fail(ach), ach, plano


def _rodar_unl(texto, nome):
    from lib.framework import experiment as X
    ok, ach, plano = _validar_unl(texto)
    if not ok:
        return emit("erro", f"experimento «{nome}» inválido — nada foi executado:\n" + _achados_unl(ach))
    emit("lab", f"plano: {len(plano['points'])} pontos · solver {plano['solver']} · campos {plano['fields']}\n" + _achados_unl([a for a in ach if a[0] != "OK"]))
    codigo = "from lib.framework.experiment import run_experiment_in_run\nrun_experiment_in_run()\n"
    _executar(codigo, f"[UNIT-L] {nome}", arquivos={"experiment.unl": texto},
              prov_extra={"unl_nome": nome, "unl_sha256": X.parse(texto).sha256})


def cmd_experimento(args):
    if not args:
        return emit("lab", "experimentos salvos:\n" + "\n".join(f"  - {p.stem}" for p in sorted(EXPERIMENTOS_DIR.glob("*.unl"))) + "\n\nuso: /experimento nome")
    p = EXPERIMENTOS_DIR / f"{args[0]}.unl"
    if not p.exists():
        return emit("erro", f"experimentos/{args[0]}.unl não existe")
    EST.update(unl=p.read_text(encoding="utf-8"), unl_nome=args[0], codigo=None)
    _rodar_unl(EST["unl"], args[0])


def _validar_pendente(args):
    """/validar [nome|caminho] — valida o experimento indicado; sem nome, valida o pendente."""
    if args:
        alvo = args[0]
        arq = Path(alvo) if alvo.endswith(".unl") else EXPERIMENTOS_DIR / f"{alvo}.unl"
        if not arq.is_absolute() or not arq.exists():
            arq = EXPERIMENTOS_DIR / arq.name
        if not arq.exists():
            return emit("erro", f"experimento não encontrado: {alvo} (procurado em {EXPERIMENTOS_DIR})")
        EST.update(unl=arq.read_text(encoding="utf-8"), unl_nome=arq.stem, codigo=None)
    if not EST["unl"]:
        return emit("erro", "nenhum experimento pendente. Informe o nome: /validar T2_leve (ou cole um bloco de unl).")
    ok, ach, _p = _validar_unl(EST["unl"])
    cabeca = ("VÁLIDO" if ok else "INVÁLIDO") + " — " + str(EST["unl_nome"])
    emit("ok" if ok else "erro", cabeca + chr(10) + _achados_unl(ach))


def cmd_validar(args):
    _validar_pendente(args)


def _cmd_validar_antigo(_):
    if not EST["unl"]:
        return emit("erro", "nenhum experimento pendente (cole um bloco ```unl ou descreva em texto livre).")
    ok, ach, _p = _validar_unl(EST["unl"])
    emit("ok" if ok else "erro", ("VÁLIDO" if ok else "INVÁLIDO") + f" — {EST['unl_nome']}\n" + _achados_unl(ach))


def cmd_linguagem(_):
    from lib.framework import experiment as X
    emit("lab", X.describe_language())


def _experimentador(instrucao):
    """A LLM DESCREVE o experimento em UNIT-L. Primeira resposta: bloco ```unl completo.
    Correções: só um bloco ```patch com linhas 'N: nova' / 'N+: inserir' / 'N-' (aplicado pelo laboratório)."""
    from lib.framework import experiment as X
    from lib.framework.unl_examples import T2_LEVE
    sistema = ("Você é o Codificador do laboratório UNIT-001. Sua saída é um EXPERIMENTO na linguagem semântica abaixo, dentro de UM bloco ```unl. "
               "Não escreva Python. Não reimplemente nada: componha as primitivas existentes. Não invente limites numéricos (use LIMIT nome = pending). "
               "Se faltar uma capacidade, responda um bloco ```falta descrevendo a primitiva necessária.\n\n" + X.describe_language()
               + "\n\nEXEMPLO REAL:\n```unl\n" + T2_LEVE + "```")
    ultimo_texto, msg, modelo, nota = None, instrucao, "-", ""
    for rodada in range(3):
        txt, modelo = chamar("codificador", sistema, msg, max_tokens=4000, temperature=0.1)
        falta = re.search(r"```falta\s*\n(.*?)```", txt, flags=re.S)
        if falta:
            return None, modelo, "CAPACIDADE AUSENTE (registre um plugin em lib/framework/plugins/):\n" + falta.group(1).strip()
        if rodada == 0 or not re.search(r"```patch", txt):
            unl = X.extract_from_markdown(txt)
            if not unl:
                msg = instrucao + "\n\nResponda SOMENTE com um bloco ```unl."
                continue
            base = unl
        else:
            pm = re.search(r"```patch\s*\n(.*?)```", txt, flags=re.S)
            try:
                unl = X.apply_patch(base, X.parse_patch(pm.group(1)))
            except X.UNLError as e:
                msg = (instrucao + f"\n\nSua correção não pôde ser aplicada: {e}\n\nExperimento atual (numerado):\n"
                       + X.numbered(base) + "\n\nResponda SOMENTE com um bloco ```patch.")
                continue
            base = unl
        ok, ach, _p = _validar_unl(unl)
        ultimo_texto = (unl, modelo, _achados_unl(ach))
        if ok:
            return unl, modelo, _achados_unl(ach)
        erros = [a for a in ach if a[0] == "FALHA"]
        sug = "\n".join(f"  · {d}" for _lv, _n, d in erros)
        msg = (instrucao + "\n\nO validador recusou o experimento. Erros:\n" + sug
               + "\n\nExperimento atual (numerado):\n" + X.numbered(unl)
               + "\n\nResponda SOMENTE com um bloco ```patch, uma linha por correção: 'N: nova linha' troca a linha N; "
                 "'N+: linha' insere depois de N; 'N-' remove a linha N. Não altere linhas FIX nem o que não está errado.")
    if ultimo_texto:
        return ultimo_texto[0], ultimo_texto[1], "AINDA INVÁLIDO após 3 rodadas:\n" + ultimo_texto[2]
    return None, modelo, "a LLM não produziu um bloco ```unl"


def cmd_medir(args):
    """/medir ppw=60 backend=iterative geometria=ORDERED freq=300 — mede tempo/memória de UM ponto no hardware atual."""
    kv, _f = _kv(args)
    if "ppw" not in kv:
        return emit("erro", "uso: /medir ppw=60 [backend=iterative|direct] [geometria=ORDERED] [freq=300]")
    codigo = ("from lib.framework.benchmark import medir\nimport json\n"
              f"r = medir(ppw={float(kv['ppw'])!r}, backend={kv.get('backend', 'iterative')!r}, geometria={kv.get('geometria', 'ORDERED')!r}, "
              f"freq={float(kv.get('freq', 300))!r})\nprint(json.dumps(r, indent=1))\n"
              "print('UNIT_RESULT_JSON: ' + json.dumps({'tabela': [r], 'escalares': {k: v for k, v in r.items() if isinstance(v, (int, float))}}))\n")
    _executar(codigo, f"[medição] ppw={kv['ppw']} {kv.get('backend', 'iterative')}")


def cmd_plugins(_):
    r = FWR.load_plugins(force=True)
    emit("erro" if r["errors"] else "ok", f"plugins carregados: {r['loaded']}\n" + "".join(f"\n✗ {k}:\n{v}" for k, v in r["errors"].items()))


def _texto_livre(txt):
    spec_txt = aop_dsl.extract_from_markdown(txt)
    if spec_txt:
        try:
            ach = aop_ativar(spec_txt, "chat")
            emit("ok", "spec AOP do chat validada e ATIVADA (vale para os próximos runs)\n" + _achados_txt(ach))
        except Exception as e:
            emit("erro", f"spec AOP inválida — mantida a anterior ({AOP['nome']}):\n{e}")
        return
    from lib.framework import experiment as X
    unl = X.extract_from_markdown(txt)
    if unl:
        ok, ach, _p = _validar_unl(unl)
        EST.update(unl=unl, unl_nome="(chat)", codigo=None)
        return emit("ok" if ok else "erro", ("experimento UNIT-L VÁLIDO — digite /rodar" if ok else "experimento UNIT-L INVÁLIDO — corrija e cole de novo") + "\n" + _achados_unl(ach))
    m = re.search(r"```(?:python)?\s*\n(.*?)```", txt, flags=re.S)
    if m:
        EST.update(unl=None, codigo=m.group(1), instrucao="(código colado no chat)", revisao="", modelos={})
        return emit("ok", f"código recebido ({len(EST['codigo'].splitlines())} linhas). Digite /rodar para executar (passa pelo AOP).")
    emit("lab", "⏳ Codificador descrevendo o experimento em UNIT-L…")
    try:
        unl, modelo, nota = _experimentador(txt)
    except ErroLLM as e:
        return emit("erro", f"LLMs indisponíveis:\n{e}\n\nTente /modelos testar. /experimento, /pipeline, /teste e /gerar funcionam sem LLM.")
    if not unl:
        return emit("erro", f"({modelo}) {nota}")
    ok = not nota.startswith("AINDA INVÁLIDO")
    EST.update(unl=unl, unl_nome="(gerado por " + modelo + ")", codigo=None, instrucao=txt, modelos={"codificador": modelo})
    emit("ok" if ok else "erro", f"experimento de {modelo}: {'VÁLIDO' if ok else 'INVÁLIDO'} — " + ("digite /rodar" if ok else "ajuste e cole de novo") + "\n" + nota, _detalhes("experimento (UNIT-L)", unl))


COMANDOS = {"/pipeline": cmd_pipeline, "/teste": cmd_teste, "/testes": cmd_testes, "/spec": cmd_spec, "/catalogo": cmd_catalogo, "/rodar": cmd_rodar,
            "/modelos": cmd_modelos, "/runs": cmd_runs, "/pacote": cmd_pacote, "/gerar": cmd_gerar, "/plugins": cmd_plugins, "/script": cmd_script,
            "/experimento": cmd_experimento, "/medir": cmd_medir, "/pausar": lambda a: pausar_execucao(), "/continuar": lambda a: continuar_execucao(), "/parar": lambda a: parar_execucao(), "/validar": cmd_validar, "/linguagem": cmd_linguagem}


def processar(msg):
    msg = msg.strip()
    if not msg:
        return
    emit("voce", msg if len(msg) < 600 else msg[:600] + " …")
    try:
        if msg.startswith("/"):
            cmd, *rest = shlex.split(msg.split("\n")[0]) if "```" not in msg else [msg.split()[0]]
            if cmd == "/ajuda": emit("lab", AJUDA)
            elif cmd == "/specs": emit("lab", "\n".join(sorted(p.stem for p in SPECS_DIR.glob("*.aop"))) or "(vazio)")
            elif cmd == "/codigo": emit("lab", EST["codigo"] or "(nenhum código pendente)")
            elif cmd == "/timeout": EST["timeout"] = int(rest[0]); emit("ok", f"timeout = {EST['timeout']}s")
            elif cmd in ("/restricao", "/hipotese", "/interpretacao"): cmd_decisao(cmd[1:], rest)
            elif cmd == "/limpar":
                _UI["log"].clear(); _redesenhar()
            elif cmd in COMANDOS: COMANDOS[cmd](rest)
            else: emit("erro", f"comando desconhecido: {cmd}. /ajuda lista os comandos.")
        else:
            _texto_livre(msg)
    except Exception as e:
        import traceback
        emit("erro", f"{type(e).__name__}: {e}", _detalhes("traceback", traceback.format_exc()))


import queue as _queue
import threading as _threading
CMD_Q = _queue.Queue()
CONTROLES = ("/parar", "/pausar", "/continuar")


def _enviar(msg):
    """Chamado pela célula de entrada: retorna NA HORA. Comandos de controle agem direto; o resto vai para a fila."""
    msg = (msg or "").strip()
    if not msg:
        return
    if msg.split()[0] in CONTROLES:
        return processar(msg)
    CMD_Q.put(msg)


def _worker():
    while True:
        msg = CMD_Q.get()
        try:
            processar(msg)
        except Exception as e:
            emit("erro", f"{type(e).__name__}: {e}")


def abrir_entrada():
    """CÉLULA DE ENTRADA (estática): só widgets. Retorna logo; pode ser reexecutada a qualquer momento."""
    import ipywidgets as W
    entrada = W.Text(placeholder="Mensagem ou /comando (Enter envia) — /ajuda", layout=W.Layout(flex="1 1 auto"), continuous_update=False)
    b_env = W.Button(description="Enviar", button_style="primary", layout=W.Layout(width="90px", flex="0 0 auto"))
    multi = W.Textarea(placeholder="Texto/código/spec com várias linhas (cole aqui)", layout=W.Layout(width="100%", height="120px"))
    b_multi = W.Button(description="Enviar bloco", layout=W.Layout(width="120px"))
    b_pausar = W.Button(description="⏸ pausar", layout=W.Layout(width="100px"))
    b_continuar = W.Button(description="▶ continuar", layout=W.Layout(width="110px"))
    b_parar = W.Button(description="⏹ parar", button_style="danger", layout=W.Layout(width="100px"))

    def _env(_=None):
        v = entrada.value
        entrada.value = ""
        _enviar(v)

    try:
        entrada.on_submit(_env)
    except Exception:
        pass
    b_env.on_click(_env)
    b_multi.on_click(lambda _b: (_enviar(multi.value), setattr(multi, "value", "")))
    b_pausar.on_click(lambda _b: pausar_execucao())
    b_continuar.on_click(lambda _b: continuar_execucao())
    b_parar.on_click(lambda _b: parar_execucao())
    _acc = W.Accordion(children=[W.VBox([multi, b_multi])])
    _acc.set_title(0, "multi-linha (cole código/spec com várias linhas)")
    _acc.selected_index = None
    controles = W.HBox([b_pausar, b_continuar, b_parar], layout=W.Layout(width="100%", padding="4px 0 0 0"))
    barra = W.HBox([entrada, b_env], layout=W.Layout(width="100%", padding="6px 0 0 0"))
    display(W.VBox([controles, barra, _acc], layout=W.Layout(width="100%")))
    print("Entrada pronta. As respostas aparecem na célula de feed (a que está rodando).")


def abrir_feed():
    """CÉLULA DE FEED (async): mostra o histórico ao vivo e processa a fila de comandos numa thread."""
    _UI["html"] = None
    _UI["disp"] = True
    display(HTML(""), display_id="unit-feed")
    if not _UI.get("worker_on"):
        _threading.Thread(target=_worker, daemon=True).start()
        _UI["worker_on"] = True
    emit("lab", f"UNIT-001 · spec AOP ativa: {AOP['nome']} · /ajuda para os comandos\nLLMs: " + ", ".join(p for p, k in KEYS.items() if k) + " (descoberta automática de modelos)")


def abrir_chat():
    """Chat em célula NORMAL (não fica rodando): os botões respondem sempre.
    O histórico atualiza a cada clique em qualquer botão (inclusive 🔄). Execuções rodam em segundo plano."""
    import ipywidgets as W
    html_w = W.HTML(value="")
    _UI["html"] = html_w
    _UI["disp"] = False
    entrada = W.Text(placeholder="Mensagem ou /comando (Enter envia) — /ajuda", layout=W.Layout(flex="1 1 auto"), continuous_update=False)
    b_env = W.Button(description="Enviar", button_style="primary", layout=W.Layout(width="90px", flex="0 0 auto"))
    multi = W.Textarea(placeholder="Texto/código/spec com várias linhas (cole aqui)", layout=W.Layout(width="100%", height="120px"))
    b_multi = W.Button(description="Enviar bloco", layout=W.Layout(width="120px"))
    b_atualizar = W.Button(description="🔄 atualizar", layout=W.Layout(width="120px"))
    b_pausar = W.Button(description="⏸ pausar", layout=W.Layout(width="100px"))
    b_continuar = W.Button(description="▶ continuar", layout=W.Layout(width="110px"))
    b_parar = W.Button(description="⏹ parar", button_style="danger", layout=W.Layout(width="100px"))

    def _env(_=None):
        v = entrada.value
        entrada.value = ""
        _enviar(v)

    try:
        entrada.on_submit(_env)
    except Exception:
        pass
    b_env.on_click(_env)
    b_multi.on_click(lambda _b: (_enviar(multi.value), setattr(multi, "value", "")))
    b_atualizar.on_click(lambda _b: _redesenhar(forcar=True))
    b_pausar.on_click(lambda _b: pausar_execucao())
    b_continuar.on_click(lambda _b: continuar_execucao())
    b_parar.on_click(lambda _b: parar_execucao())
    _acc = W.Accordion(children=[W.VBox([multi, b_multi])])
    _acc.set_title(0, "multi-linha (cole código/spec com várias linhas)")
    _acc.selected_index = None
    controles = W.HBox([b_atualizar, b_pausar, b_continuar, b_parar], layout=W.Layout(width="100%", padding="4px 0 0 0"))
    try:
        from google.colab import output as _colab_output
        _colab_output.register_callback("unit_chat_refresh", lambda *a: _redesenhar())
        _UI["colab"] = True
    except Exception:
        _UI["colab"] = False
    barra = W.HBox([entrada, b_env], layout=W.Layout(width="100%", padding="6px 0 0 0"))
    display(W.VBox([html_w, controles, barra, _acc], layout=W.Layout(width="100%")))
    if not _UI.get("worker_on"):
        _threading.Thread(target=_worker, daemon=True).start()
        _UI["worker_on"] = True
    emit("lab", f"UNIT-001 · spec AOP ativa: {AOP['nome']} · /ajuda para os comandos\nLLMs: " + ", ".join(p for p, k in KEYS.items() if k) + " (descoberta automática de modelos)")
