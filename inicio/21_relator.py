# versao: 11
# inicio/21_relator.py — relator e pacote para IA
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 5 · RELATOR E PACOTE PARA IA AVANÇADA
# ═══════════════════════════════════════════════════════════════
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
PALAVRAS_INTERPRETATIVAS = ["confirma", "refuta", "comprova", "demonstra", "prova que", "sugere que",
                            "indica que", "valida a hipótese", "consistente com a hipótese", "evidencia"]
def _float(t):
    try:
        return float(t)
    except ValueError:
        return None
def checar_fidelidade(tabela, bruto):
    """Todo número da tabela precisa existir na saída bruta; sem palavras interpretativas."""
    toks_bruto = set(NUM_RE.findall(bruto))
    vals_bruto = {_float(t) for t in toks_bruto}
    ausentes = [t for t in dict.fromkeys(NUM_RE.findall(tabela))
                if t not in toks_bruto and _float(t) not in vals_bruto]
    interp = [p for p in PALAVRAS_INTERPRETATIVAS if p in tabela.lower()]
    return ausentes, interp
def _truncar(txt, cab=5000, cauda=3000):
    return txt if len(txt) <= cab + cauda else txt[:cab] + f"\n[... {len(txt)-cab-cauda} caracteres omitidos ...]\n" + txt[-cauda:]
def extrair_resultado_json(out):
    """Procura a última linha 'UNIT_RESULT_JSON: {...}' na saída. Retorna (obj, None) ou (None, motivo)."""
    for linha in reversed(out.splitlines()):
        if linha.startswith("UNIT_RESULT_JSON:"):
            try:
                obj = json.loads(linha[len("UNIT_RESULT_JSON:"):].strip())
            except json.JSONDecodeError as e:
                return None, f"JSON inválido ({e.msg})"
            return (obj, None) if isinstance(obj, dict) else (None, "JSON não é um objeto")
    return None, "linha UNIT_RESULT_JSON ausente"
def tabela_de_json(rj):
    cel = lambda v: str(v).replace("|", "\\|")
    partes = []
    linhas = rj.get("tabela") or []
    if linhas and all(isinstance(l, dict) for l in linhas):
        cols = list(dict.fromkeys(k for l in linhas for k in l))
        partes.append("| " + " | ".join(cols) + " |")
        partes.append("|" + "---" * len(cols))
        for l in linhas:
            partes.append("| " + " | ".join(cel(l.get(c, "")) for c in cols) + " |")
    outros = {k: v for k, v in rj.items() if k != "tabela"}
    esc = outros.pop("escalares", None)
    if isinstance(esc, dict) and esc:
        partes += [""] + [f"- {k}: {v}" for k, v in esc.items()]
    if outros:
        partes += [""] + [f"- {k}: {v}" for k, v in outros.items()]
    return "\n".join(partes)
ARQUIVOS_DO_LAB = {"spec.aop", "experiment.unl", "experiment_result.json", "experiment_provenance.json", "report_unl.md", "aop_report.json", "aop_cases.json", "code.py", "stdout.txt", "stderr.txt", "report.md", "report.json", "instruction.txt",
                   "review.md", "package.md", "provenance.json", "autocorrecao.diff"}
def _nao_finitos_json(obj, caminho="json"):
    if isinstance(obj, float):
        return [] if math.isfinite(obj) else [caminho]
    if isinstance(obj, dict):
        return [x for k, v in obj.items() for x in _nao_finitos_json(v, f"{caminho}.{k}")]
    if isinstance(obj, list):
        return [x for i, v in enumerate(obj) for x in _nao_finitos_json(v, f"{caminho}[{i}]")]
    return []
def _checar_array(nome, a):
    import numpy as np
    a = np.asarray(a)
    base = f"shape={a.shape} dtype={a.dtype}"
    if a.dtype.kind not in "fc":
        return ("OK", nome, base)
    if a.size > 5e7:
        return ("AVISO", nome, base + ": grande demais, não verificado")
    n_nan, n_inf = int(np.isnan(a).sum()), int(np.isinf(a).sum())
    if n_nan or n_inf:
        return ("FALHA", nome, base + f" NaN={n_nan} Inf={n_inf}")
    if a.dtype.kind == "f" and a.size:
        return ("OK", nome, base + f" min={a.min():.4g} max={a.max():.4g}")
    return ("OK", nome, base)
def validar_run(out, run_dir, rj, executou_ok, integridade=None, res=None):
    """NÍVEL 0 (sem IA). Valida o que é verificável de forma determinística. PASS não significa física correta."""
    if res is not None and res.get("aop_bloqueado"):
        return "FAIL", list(res.get("aop_preflight") or [])
    if not executou_ok:
        return "N/A", [("AVISO", "execução", "falhou; validação não aplicável")]
    run_dir = Path(run_dir)
    checks = []
    n = len(re.findall(r"\b(nan|inf)\b", out, flags=re.I))
    checks.append(("FALHA" if n else "OK", "stdout sem NaN/Inf", f"{n} ocorrência(s)"))
    for chave, rot in (("original_modificada", "biblioteca ORIGINAL"), ("copia_modificada", "cópia da biblioteca usada no run")):
        lst = (integridade or {}).get(chave) or []
        checks.append(("FALHA" if lst else "OK", f"integridade: {rot}",
                       ("MODIFICADA pelo script: " + ", ".join(lst)) if lst else "inalterada"))
    if rj is None:
        checks.append(("AVISO", "UNIT_RESULT_JSON", "ausente: valores não validados estruturalmente"))
    else:
        ruins = _nao_finitos_json(rj)
        checks.append(("FALHA" if ruins else "OK", "valores do JSON finitos", ", ".join(ruins[:8]) or "ok"))
        esc = rj.get("escalares") if isinstance(rj.get("escalares"), dict) else {}
        for nome, (lo, hi) in LIMITES_ESCALARES.items():
            v = esc.get(nome)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                checks.append(("AVISO", f"limite {nome}", "escalar ausente ou não numérico no JSON")); continue
            ok = (lo is None or v >= lo) and (hi is None or v <= hi)
            checks.append(("OK" if ok else "FALHA", f"limite {nome}", f"valor={v} faixa=({lo}, {hi})"))
    for p in sorted(run_dir.rglob("*")):
        rel = p.relative_to(run_dir)
        if p.is_dir() or rel.parts[0] in ("lib", ".mplconfig") or (len(rel.parts) == 1 and rel.name in ARQUIVOS_DO_LAB):
            continue
        ext = p.suffix.lower()
        if p.stat().st_size == 0:
            checks.append(("AVISO", str(rel), "arquivo vazio")); continue
        try:
            if ext == ".npz":
                import numpy as np
                with np.load(p, allow_pickle=False) as z:
                    for k in list(z.files)[:200]:
                        checks.append(_checar_array(f"{rel}:{k}", z[k]))
            elif ext == ".npy":
                import numpy as np
                checks.append(_checar_array(str(rel), np.load(p, allow_pickle=False, mmap_mode="r")))
            elif ext == ".json":
                ruins = _nao_finitos_json(json.loads(p.read_text(encoding="utf-8")))
                checks.append(("FALHA" if ruins else "OK", str(rel),
                               ("valores não finitos: " + ", ".join(ruins[:5])) if ruins else "JSON válido, valores finitos"))
            else:
                checks.append(("OK", str(rel), f"{p.stat().st_size} bytes"))
        except json.JSONDecodeError as e:
            checks.append(("FALHA", str(rel), f"JSON inválido ({e.msg})"))
        except Exception as e:
            checks.append(("AVISO", str(rel), f"não foi possível validar ({type(e).__name__}: {str(e)[:80]})"))
    if res is not None and "aop_hook" in globals():
        checks.extend(aop_hook(out, run_dir, rj, res))   # AOP-DSL: preflight + reverificação Zero-Trust
    niveis = [c[0] for c in checks]
    return ("FAIL" if "FALHA" in niveis else "PASS COM AVISOS" if "AVISO" in niveis else "PASS"), checks
def escrever_provenance(run_dir, run_id, codigo, res, prov_extra):
    prov = {"run": run_id, "quando": dt.datetime.now().isoformat(timespec="seconds"),
            "code_sha256": hashlib.sha256(codigo.encode()).hexdigest(),
            "library_sha256": res.get("lib_hashes", {}),
            "project_context_sha256": hashlib.sha256(PROJECT_CONTEXT.encode()).hexdigest(),
            "ambiente": versoes_ambiente(),
            "limite_memoria_gb": res.get("limite_memoria_gb"),
            "limites_escalares_configurados": {k: list(v) for k, v in LIMITES_ESCALARES.items()}}
    prov.update(prov_extra or {})
    (Path(run_dir) / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    return prov
def relator(run_id, instrucao, revisao, codigo, res, run_dir, usar_llm=True, extra="", prov_extra=None):
    run_dir = Path(run_dir)
    out, err = res["stdout"], res["stderr"]
    arquivos = sorted(p.name for p in run_dir.iterdir()
                      if p.name not in ARQUIVOS_DO_LAB and p.name not in ("lib", ".mplconfig"))
    executou_ok = res["returncode"] == 0 and not res["timeout"]
    if res["timeout"]:
        status = "TIMEOUT"
    elif res["returncode"] != 0:
        status = f"ERRO (código de saída {res['returncode']})"
    else:
        status = "EXECUTADO SEM ERRO"
    rj, motivo_json = extrair_resultado_json(out)
    val_status, checks = validar_run(out, run_dir, rj, executou_ok, res.get("integridade"), res)
    tabela, aviso_tabela, modelo_rel, modelo_llm = "", "", "-", "nenhum (determinístico)"
    if rj is not None:
        tabela, modelo_rel = tabela_de_json(rj), "determinística, a partir de UNIT_RESULT_JSON"
        aviso_tabela = "✔ tabela montada em Python a partir do JSON do script (sem LLM)\n"
    elif usar_llm and out.strip() and res["returncode"] == 0:
        system = f"""{REGRA_FUNDAMENTAL}
Você é o RELATOR. Reorganize a saída bruta de um script numa tabela markdown limpa (uma linha por
caso/medida, colunas = grandezas). Copie os números EXATAMENTE como aparecem, sem arredondar, sem converter, sem inventar.
Sem adjetivos, sem interpretação, sem sugestões. Se algo não couber em tabela, liste como 'campo: valor'."""
        try:
            tabela, modelo_rel = chamar("relator", system, f"SAÍDA BRUTA:\n{_truncar(out, 12000, 4000)}", max_tokens=4000)
            modelo_llm = modelo_rel
            ausentes, interp = checar_fidelidade(tabela, out)
            aviso_tabela += f"⚠ {motivo_json}: tabela gerada por LLM (menos confiável que a determinística)\n"
            if ausentes:
                aviso_tabela += f"⚠ números da tabela que NÃO aparecem na saída bruta: {', '.join(ausentes[:15])} — confie na saída bruta.\n"
            if interp:
                aviso_tabela += f"⚠ linguagem interpretativa detectada na tabela: {', '.join(interp)} — ignore.\n"
            if not (ausentes or interp):
                aviso_tabela += "✔ todos os números da tabela foram encontrados na saída bruta (conferência automática)\n"
        except ErroLLM as e:
            aviso_tabela = f"Tabela não gerada (LLM indisponível): {str(e)[:200]}\n"
    ruins = [c for c in checks if c[0] != "OK"]
    oks = [c for c in checks if c[0] == "OK"]
    icone = {"FALHA": "✘", "AVISO": "⚠", "OK": "✔"}
    linhas_chk = [f"    {icone[n]} {nome}: {det}" for n, nome, det in ruins + oks[:12]]
    if len(oks) > 12:
        linhas_chk.append(f"    (+{len(oks) - 12} verificações OK omitidas)")
    bloco_chk = "\n".join(linhas_chk) + "\n"
    barra = "━" * 64
    md = f"""{barra}
UNIT-001 | RELATÓRIO DE TESTE | {run_id}
{barra}
Executado:    {dt.datetime.now().strftime('%d/%m/%Y %H:%M')}
Duração:      {res['duracao_s']:.1f}s
Execução:     {status}
Validação:    {val_status}   (técnica automática: NaN/Inf, arquivos, limites configurados — PASS não significa física correta)
Instrução:    {instrucao.strip()}
Hash do código: {hashlib.sha256(codigo.encode()).hexdigest()[:10]}
Arquivos gerados: {', '.join(arquivos) or 'nenhum'}
{barra}
STATUS TÉCNICO
  Revisão técnica: {(revisao or 'não executada').strip().splitlines()[0][:150] if (revisao or '').strip() else 'não executada'}
{extra}  Verificações automáticas (nível 0, sem IA):
{bloco_chk}{barra}
TABELA ORGANIZADA ({modelo_rel}) — conferida automaticamente
{aviso_tabela}
{tabela or '(sem tabela)'}
{barra}
SAÍDA BRUTA (fonte da verdade)
{_truncar(out) or '(vazia)'}
""" + (f"{barra}\nSTDERR\n{_truncar(err, 2500, 2500)}\n" if err.strip() else "") + f"""{barra}
Resultado pronto. Aguardando direção.
"""
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    (run_dir / "report.json").write_text(json.dumps(
        {"run": run_id, "execution_status": status, "validation_status": val_status,
         "checks": [{"nivel": n, "nome": nm, "detalhe": d} for n, nm, d in checks],
         "duracao_s": res["duracao_s"], "instrucao": instrucao, "arquivos": arquivos,
         "tabela_deterministica": rj is not None, "tabela_conferida": "⚠" not in aviso_tabela},
        ensure_ascii=False, indent=2), encoding="utf-8")
    pe = dict(prov_extra or {})
    modelos = dict(pe.get("modelos", {})); modelos["relator"] = modelo_llm
    pe["modelos"] = modelos
    escrever_provenance(run_dir, run_id, codigo, res, pe)
    return md, f"{status} | validação {val_status}"
MAX_AUTOCORRECOES = 2
def rodar_com_autocorrecao(codigo, instrucao, revisao, timeout=600, autocorrigir=True, log=print,
                           revisar_corrigido=True, prov_extra=None):
    """Roda; se falhar em RUNTIME (nem timeout, nem MemoryError), pede correção ao Codificador (máx. MAX_AUTOCORRECOES).
    Todo código corrigido passa de novo pelo Revisor técnico antes de rodar. Cada tentativa é um run próprio.
    Retorna (relatório_md, status, run_id_final, código_final)."""
    original, atual, rev_atual, rev_original = codigo, codigo, revisao, revisao
    cadeia, avisos = [], []
    prov_extra = dict(prov_extra or {})
    modelos = dict(prov_extra.get("modelos", {})); modelos["autocorrecao"] = []
    while True:
        run_id = proximo_run_id(); d = RUNS / run_id; d.mkdir(parents=True)
        (d / "instruction.txt").write_text(instrucao or "(código editado/colado manualmente)", encoding="utf-8")
        (d / "review.md").write_text(rev_atual or "(sem revisão)", encoding="utf-8")
        log(f"⚙️  {run_id}: executando (timeout {timeout}s)…")
        res = executar_gated(atual, d, timeout=timeout)
        falha_rt = res["returncode"] != 0 and not res["timeout"]
        ult = (res["stderr"].strip().splitlines() or ["(sem stderr)"])[-1][:200]
        cadeia.append(f"{run_id}: " + ("EXECUTADO SEM ERRO" if res["returncode"] == 0 else "TIMEOUT" if res["timeout"] else f"ERRO — {ult}"))
        if falha_rt and "MemoryError" in res["stderr"]:
            avisos.append(f"⚠ MemoryError: limite de memória ({LIMITE_MEMORIA_GB} GB) atingido — sem autocorreção; decisão é sua")
            break
        if not (falha_rt and autocorrigir and len(cadeia) <= MAX_AUTOCORRECOES):
            break
        log(f"❌ {run_id} falhou ({ult}). Pedindo correção ao Codificador ({len(cadeia)}/{MAX_AUTOCORRECOES})…")
        try:
            novo, modelo, erro = corrigir_codigo(instrucao, atual, res["stderr"])
        except ErroLLM as e:
            avisos.append(f"⚠ autocorreção indisponível: {str(e)[:200]}"); break
        if not novo or erro:
            avisos.append(f"⚠ autocorreção devolveu código inválido ({erro})"); break
        modelos["autocorrecao"].append(modelo)
        if _n_handlers(novo) > _n_handlers(atual):
            avisos.append(f"⚠ a correção ({modelo}) ADICIONOU bloco(s) try/except — verifique se não está escondendo o erro")
        atual = novo
        if revisar_corrigido:
            log("🔎 Revisor técnico lendo o código corrigido…")
            try:
                rev_atual, mrev = revisor(instrucao, novo)
                modelos["revisor_pos_correcao"] = mrev
            except ErroLLM:
                rev_atual = "(revisão do código corrigido indisponível)"
        else:
            rev_atual = "(código corrigido NÃO foi revisado)"
    extra = ""
    if len(cadeia) > 1 or avisos:
        extra += "  Autocorreção (cada tentativa é um run próprio):\n" + "".join(f"    {c}\n" for c in cadeia)
        extra += "".join(f"  {a}\n" for a in avisos)
    if atual != original:
        diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), atual.splitlines(keepends=True),
                                            "codigo_original", "codigo_final"))
        (d / "autocorrecao.diff").write_text(diff, encoding="utf-8")
        extra += ("  ⚠ CÓDIGO FINAL DIFERE DO ORIGINAL (o original está no primeiro run acima). "
                  + ("A revisão técnica acima refere-se ao código FINAL.\n" if revisar_corrigido
                     else "O código final NÃO foi revisado.\n")
                  + "  Diff (resumo):\n" + "".join("    " + l for l in diff[:2500].splitlines(keepends=True)) + "\n")
        prov_extra["codigo_original_sha256"] = hashlib.sha256(original.encode()).hexdigest()
    prov_extra["modelos"] = modelos
    prov_extra["autocorrecoes"] = len(cadeia) - 1
    rel, status = relator(run_id, instrucao or "(manual)", rev_atual, atual, res, d, extra=extra, prov_extra=prov_extra)
    return rel, status, run_id, atual
def gerar_pacote(run_id, pergunta):
    """Documento pronto para colar no Claude / ChatGPT / Gemini Pro."""
    d = RUNS / run_id
    ler = lambda n: (d / n).read_text(encoding="utf-8") if (d / n).exists() else "(não disponível)"
    fmt = lambda xs: "\n".join(f"- [{x['quando']} · {x['fonte']} · {x.get('run') or '-'}] {x['texto'][:1200]}" for x in xs) or "(nenhuma registrada)"
    pacote = f"""# UNIT-001 — Pacote para revisão avançada ({run_id})
## Seu papel
Os agentes locais (modelos gratuitos) apenas escreveram o código, rodaram e organizaram os números.
Eles NÃO interpretaram nada. A interpretação, as críticas e o veredito são com você e o pesquisador.
Atenção: a ausência de crítica do revisor técnico NÃO significa que o experimento esteja fisicamente correto, e
validação "PASS" no relatório cobre só checagens técnicas automáticas (NaN/Inf, arquivos, limites configurados).
Seja rigoroso: separe fato / resultado dos dados / hipótese / especulação; aponte artefatos numéricos e explicações alternativas;
não concorde por padrão; se o dado não sustenta a conclusão, diga.
## Contexto do projeto
{PROJECT_CONTEXT.strip()}
## Restrições experimentais vigentes (vinculantes para o Codificador)
{fmt(ler_decisoes(10, ("restricao",)))}
## Hipóteses em teste (NÃO são fatos)
{fmt(ler_decisoes(10, ("hipotese",)))}
## Interpretações anteriores (podem estar erradas; não assuma como verdade)
{fmt(ler_decisoes(8, ("interpretacao",)))}
## Especificação AOP-DSL vigente (spec.aop)
```
{ler('spec.aop')}
```
## Instrução dada aos agentes
{ler('instruction.txt')}
## Código executado
```python
{ler('code.py')}
```
## Revisão técnica (modelo gratuito — apenas bugs)
{ler('review.md')}
## Relatório
{ler('report.md')}
## Proveniência (modelos, hashes, versões)
```json
{ler('provenance.json')}
```
## Pergunta ao revisor avançado
{pergunta.strip() or 'O que estes dados mostram? O que NÃO mostram? Há artefato numérico ou bug que invalide a leitura? Qual o próximo teste mais informativo?'}
"""
    (d / "package.md").write_text(pacote, encoding="utf-8")
    return pacote
