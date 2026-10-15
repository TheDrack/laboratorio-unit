"""
spec.py — referência da UNIT-L GERADA a partir de unl_spec.toml (+ registros do framework).

Use:
  describe_language()   texto compacto para prompts de LLM (dentro do laboratório)
  referencia_md()       documento completo em Markdown (para colar em outra IA, fora do laboratório)
Nada aqui é escrito à mão: se o TOML mudar, a referência muda junto.
"""
from lib.framework.lang.parser import SPEC, VERB_SPEC, LANG_VERSION


def _registros():
    from lib.framework import registry as R
    R.ensure_loaded()
    return R


def describe_language():
    R = _registros()
    m = SPEC["meta"]
    L = [f"{LANG_VERSION} — {m['purpose']}", m["rule_zero"], "",
         "ESTRUTURA (um bloco; um comando por linha; # comentário):",
         "EXPERIMENT Nome {"]
    for v in SPEC["verbs"]:
        if v["kind"] == "block":
            continue
        L.append(f"  {v['example']}  # {v['doc']}")
    L += ["}", "", "PARÂMETROS (FIX/VARY):"]
    for n in R.PARAMS.names():
        p = R.PARAMS.meta(n)
        L.append(f"  {n} [{p['type']}, {p['kind']}{', obrigatório' if p['required'] else ''}{', ' + p['unit'] if p['unit'] else ''}] {p['description']}")
    L.append("SOLVERS: " + ", ".join(R.SOLVERS.names()))
    L.append("MEDIDAS (MEASURE):")
    for n in R.MEASURES.names():
        L.append(f"  {n} [{R.MEASURES.meta(n)['unit']}] {R.MEASURES.meta(n)['description']}")
    for titulo, reg in (("COMPARE", R.COMPARATORS), ("ANALYZE", R.ANALYZERS)):
        L.append(f"{titulo}:")
        for n in reg.names():
            meta = reg.meta(n)
            sig = ", ".join(k + ("" if v[1] else "?") + ":" + v[0] for k, v in meta["params"].items())
            L.append(f"  {n}({sig}) — {meta['description']}")
    L += ["", "CONCEITOS:"] + [f"  {c['name']}: {c['definition']}" for c in SPEC["concepts"]]
    L += ["", "REGRAS (o validador recusa a violação):"] + [f"  {r['id']}: {r['text']}" for r in SPEC["rules"]]
    L += ["", "CORREÇÕES AUTOMÁTICAS DE FORMA (viram AVISO, não erro):"] + [f"  {n['id']}: {n['message']}" for n in SPEC["normalize"]]
    L += ["", "CONTEXTO ATUAL DO LABORATÓRIO (atualizado a cada abertura): _mapa/CONTEXTO_IA.md; estrutura detalhada em _mapa/mapa.json e no _SKELETON.md de cada pasta."]
    L += ["", "Se faltar uma capacidade (medida, comparador, solver, parâmetro), NÃO a invente: responda um bloco ```falta com a descrição da primitiva necessária."]
    return "\n".join(L)


def referencia_md():
    R = _registros()
    m = SPEC["meta"]
    L = [f"# {LANG_VERSION} — referência da linguagem", "",
         f"{m['purpose']}", "", f"> {m['rule_zero']}", "",
         "Este documento é gerado a partir de `unl_spec.toml` e dos registros do framework.", "",
         "## Estrutura", "", "```unl", "EXPERIMENT Nome {", "    ...", "}", "```", "",
         "Um comando por linha. `#` inicia comentário. Um EXPERIMENT por arquivo.", "",
         "## Comandos", ""]
    for v in SPEC["verbs"]:
        if v["kind"] == "block":
            continue
        L += [f"### {v['name']}", "", f"- tipo: `{v['kind']}`"]
        if v.get("keys"):
            L.append(f"- chaves aceitas: {', '.join(v['keys'])}")
        if v.get("requires_list"):
            L.append("- valores: lista com 2 ou mais itens")
        L += [f"- {v['doc']}", "", "```unl", v["example"], "```", ""]
    L += ["## Conceitos", ""] + [f"- **{c['name']}**: {c['definition']}" for c in SPEC["concepts"]] + [""]
    L += ["## Regras", "", "| id | regra | checagem |", "|---|---|---|"]
    L += [f"| {r['id']} | {r['text']} | `{r['enforced_by']}` |" for r in SPEC["rules"]] + [""]
    L += ["## Correções automáticas de forma", "", "Estas correções são feitas sem perguntar e aparecem como AVISO:", ""]
    L += [f"- `{n['id']}`: {n['message']}" for n in SPEC["normalize"]] + [""]
    L += ["## Parâmetros", "", "| nome | tipo | natureza | obrigatório | unidade | descrição |", "|---|---|---|---|---|---|"]
    for n in R.PARAMS.names():
        p = R.PARAMS.meta(n)
        L.append(f"| {n} | {p['type']} | {p['kind']} | {'sim' if p['required'] else 'não'} | {p['unit']} | {p['description']} |")
    L += ["", "## Medidas", "", "| nome | unidade | descrição |", "|---|---|---|"]
    L += [f"| {n} | {R.MEASURES.meta(n)['unit']} | {R.MEASURES.meta(n)['description']} |" for n in R.MEASURES.names()]
    L += ["", "## Solvers", ""] + [f"- `{n}`: {R.SOLVERS.meta(n).get('description', '')}" for n in R.SOLVERS.names()]
    L += ["", "## Exemplos", ""]
    for ex in SPEC["examples"]:
        L += [f"### {ex['name']}", "", "```unl", ex["text"], "```", ""]
    return "\n".join(L) + "\n"
