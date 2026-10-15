"""
mapa.py — mapa de contexto AUTOMÁTICO do laboratório. Roda a cada abertura (gerar()).

Produz, dentro de _mapa/ e em cada pasta:
  _mapa/mapa.json       estrutura completa (máquina): pastas, arquivos, hashes, símbolos, imports
  _mapa/CONTEXTO_IA.md  resumo curto para IAs: versões, pontos de entrada, onde mexer
  <pasta>/_SKELETON.md  esqueleto da pasta: cada arquivo com resumo e símbolos (sem o corpo)

Não reabre arquivos que não mudaram (mesmo tamanho e data): a atualização é rápida.
Não altera código nem dados: só escreve em _mapa/ e _SKELETON.md.
"""
import ast
import hashlib
import json
import os
import re
import tomllib
from datetime import datetime
from pathlib import Path

IGNORAR_DIRS = {"__pycache__", ".ipynb_checkpoints", "_mapa"}
IGNORAR_EXT = {".pyc", ".pyo"}
IGNORAR_NOMES = {"_SKELETON.md", "CONTEXTO_IA.md", "mapa.json"}   # gerados por este módulo (não se descrevem)
SO_CONTAGEM = {"runs", "dados"}          # listados por contagem/tamanho; não detalha conteúdo
LIMITE_HASH = 2_000_000                  # bytes
PROPOSITO = {
    "lib/framework": "framework: registros, motor UNIT-L, pipeline, sentinela, chat-apoio",
    "lib/framework/lang": "UNIT-L: sintaxe declarada em unl_spec.toml (fonte única) + parser + referência",
    "lib/framework/plugins": "extensões do usuário (não sobrescritas pela instalação)",
    "lib/geometry": "gerador canônico de geometrias",
    "lib/solvers": "solvers eletromagnéticos",
    "lib/core": "núcleo físico compartilhado",
    "lib/coupling": "acoplamentos (EM -> térmico)",
    "experimentos": "experimentos UNIT-L (.unl)",
    "specs": "especificações AOP-DSL",
    "dados": "dados do projeto (casos NPZ, resultados): árvore completa, sem análise de código",
    "dados/UNIT001": "pasta de dados ativa: casos NPZ e resultados (setup usa dados/UNIT001/resultados/extrator/cases)",
    "runs": "execuções de cada /medir e experimento: árvore completa, sem análise de código",
    "scripts_prontos": "scripts de pesquisa: geração de catálogo, modulação térmica contrafactual (v1 removida), extrator (legado)",
    "lib/solvers": "solvers padrão de estudo: FDFD 2D e 3D (validados), FDTD 3D (CW validado; pulso+FFT não)",
    "lib/core": "estado de onda, estado de material e ledger de energia",
    "lib/adapters": "adapters solver -> WaveState -> EnergyLedger",
    "lib/config": "caminhos e configuração do projeto",
    "lib/validation": "validação dos solvers contra Fabry-Pérot (FDFD 2D, FDFD 3D, FDTD 3D)",
    "lib/research": "investigações e referência de controle: TMM 1D e investigação da Barreira Térmica",
    "validacao": "relatórios de validação gerados (ver PADRAO_ESTUDO.md)",
    "docs": "documentação do projeto",
    "scripts_prontos": "scripts antigos (anteriores ao framework)",
    "inicio": "scripts que rodam automaticamente ao abrir o laboratório (ordem pelo nome)",
    "_mapa": "este mapa (gerado automaticamente)",
}


def _iso(ts):
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _esqueleto_py(path):
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        arvore = ast.parse(src)
    except SyntaxError as e:
        return {"erro": f"sintaxe: linha {e.lineno}: {e.msg}"}
    doc = (ast.get_docstring(arvore) or "").strip().splitlines()
    simbolos = []
    for n in arvore.body:
        if isinstance(n, ast.ClassDef):
            simbolos.append(f"class {n.name} (L{n.lineno})")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            simbolos.append(f"def {n.name} (L{n.lineno})")
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    simbolos.append(f"{t.id} (L{n.lineno})")
    imports = set()
    for n in ast.walk(arvore):
        if isinstance(n, ast.Import):
            imports |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            imports.add(n.module.split(".")[0])
    return {"doc": doc[0] if doc else "", "simbolos": simbolos, "imports": sorted(imports)}


def _esqueleto_toml(path):
    try:
        d = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"erro": f"toml: {e}"}
    resumo = {k: (len(v) if isinstance(v, list) else "tabela" if isinstance(v, dict) else "valor") for k, v in d.items()}
    return {"doc": f"chaves de topo: {sorted(d)}", "simbolos": [f"{k}: {v}" for k, v in resumo.items()]}


def _esqueleto_md(path):
    titulos = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.startswith("#")]
    return {"doc": titulos[0].lstrip("# ") if titulos else "", "simbolos": titulos[1:12]}


def _esqueleto_ipynb(path):
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
        return {"doc": f"{len(nb.get('cells', []))} células", "simbolos": []}
    except Exception as e:
        return {"erro": f"ipynb: {e}"}


def _esqueleto(path):
    ext = path.suffix.lower()
    if ext == ".py":
        return _esqueleto_py(path)
    if ext == ".toml":
        return _esqueleto_toml(path)
    if ext == ".md":
        return _esqueleto_md(path)
    if ext == ".ipynb":
        return _esqueleto_ipynb(path)
    return {}


def _carregar_anterior(saida):
    try:
        return json.loads((saida / "mapa.json").read_text(encoding="utf-8")).get("arquivos", {})
    except Exception:
        return {}


def _varrer(base, anterior):
    """Percorre TUDO. Pastas de contagem (runs/, dados/) entram sem hash nem análise de código: só nome, tamanho e data."""
    arquivos, pastas = {}, {}
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if d not in IGNORAR_DIRS and not d.startswith("."))
        rel_dir = Path(dp).relative_to(base).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        leve = (rel_dir.split("/")[0] if rel_dir else "") in SO_CONTAGEM
        filhos = []
        for nome in sorted(fns):
            p = Path(dp) / nome
            if p.suffix.lower() in IGNORAR_EXT or nome.startswith(".") or nome in IGNORAR_NOMES:
                continue
            rel = f"{rel_dir}/{nome}" if rel_dir else nome
            st = p.stat()
            if leve:
                arquivos[rel] = {"tamanho": st.st_size, "modificado": _iso(st.st_mtime), "leve": True}
                filhos.append(rel)
                continue
            ant = anterior.get(rel)
            if ant and ant.get("tamanho") == st.st_size and ant.get("modificado") == _iso(st.st_mtime) and "sha256" in ant:
                info = dict(ant)
            else:
                info = {"tamanho": st.st_size, "modificado": _iso(st.st_mtime)}
                if st.st_size <= LIMITE_HASH:
                    info["sha256"] = _sha(p)
                info.update(_esqueleto(p))
            arquivos[rel] = info
            filhos.append(rel)
        pastas[rel_dir] = {"arquivos": filhos, "subpastas": list(dns), "leve": leve}
    return arquivos, pastas


def _versoes(base):
    v = {}
    reg = base / "lib/framework/registry.py"
    if reg.exists():
        m = re.search(r"FRAMEWORK_VERSION\s*=\s*(\d+)", reg.read_text(encoding="utf-8", errors="replace"))
        v["framework"] = int(m.group(1)) if m else None
    spec = base / "lib/framework/lang/unl_spec.toml"
    if spec.exists():
        try:
            meta = tomllib.loads(spec.read_text(encoding="utf-8"))["meta"]
            v["unit_l"] = f"{meta['name']} {meta['version']}"
        except Exception:
            v["unit_l"] = None
    return v


def _skeleton_pasta(base, rel_dir, pasta, arquivos, pastas):
    proposito = PROPOSITO.get(rel_dir, "")
    L = [f"# SKELETON — {rel_dir or 'raiz'}", "",
         f"Gerado automaticamente em {datetime.now().isoformat(timespec='seconds')}. Não edite à mão.", ""]
    if proposito:
        L += [f"**Função:** {proposito}", ""]
    prefixo = rel_dir + "/" if rel_dir else ""
    # 1) ÁRVORE COMPLETA: tudo o que está dentro desta pasta, em qualquer profundidade
    L += ["## Conteúdo completo (árvore)", ""]
    dirs = sorted(d for d in pastas if d.startswith(prefixo) and d != rel_dir)
    arqs = sorted(a for a in arquivos if a.startswith(prefixo))
    if not dirs and not arqs:
        L += ["(vazia)", ""]
    entradas = [(d, True) for d in dirs] + [(a, False) for a in arqs]
    for caminho, eh_pasta in sorted(entradas, key=lambda t: t[0]):
        rel = caminho[len(prefixo):]
        if eh_pasta:
            L.append(f"- {rel}/")
        else:
            info = arquivos[caminho]
            L.append(f"- {rel}  ({info.get('tamanho', 0)} bytes, {info.get('modificado', '?')})")
    L.append("")
    if pasta.get("leve"):
        L += ["Conteúdo de execuções/dados: listado por nome, tamanho e data (sem análise de código).", ""]
    # 2) DETALHE dos arquivos diretos (código: resumo, símbolos, imports)
    L += ["## Detalhe dos arquivos diretos", ""]
    if not pasta["arquivos"]:
        L += ["(nenhum arquivo direto)", ""]
    for rel in pasta["arquivos"]:
        info = arquivos.get(rel, {})
        if info.get("leve"):
            continue
        nome = rel.split("/")[-1]
        L.append(f"### {nome}")
        L.append(f"- tamanho: {info.get('tamanho', 0)} bytes · modificado: {info.get('modificado', '?')}")
        if info.get("erro"):
            L.append(f"- ERRO: {info['erro']}")
        if info.get("doc"):
            L.append(f"- resumo: {info['doc']}")
        if info.get("simbolos"):
            L.append("- símbolos: " + "; ".join(info["simbolos"][:25]))
        if info.get("imports"):
            L.append("- imports: " + ", ".join(info["imports"]))
        L.append("")
    return "\n".join(L) + "\n"


def _escrever_se_mudou(path, texto):
    if path.exists() and path.read_text(encoding="utf-8") == texto:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf-8")
    return True


def gerar(base=None):
    """Atualiza _mapa/mapa.json, _mapa/CONTEXTO_IA.md e _SKELETON.md de cada pasta. Devolve um resumo."""
    base = Path(base) if base else Path(__file__).resolve().parents[2]
    saida = base / "_mapa"
    saida.mkdir(exist_ok=True)
    anterior = _carregar_anterior(saida)
    arquivos, pastas = _varrer(base, anterior)
    versoes = _versoes(base)
    agora = datetime.now().isoformat(timespec="seconds")
    mapa = {"gerado_em": agora, "versoes": versoes, "estatisticas": {
                "arquivos": len(arquivos), "pastas": len(pastas),
                "tamanho_total_bytes": sum(a.get("tamanho", 0) for a in arquivos.values())},
            "pastas": pastas, "arquivos": arquivos}
    _escrever_se_mudou(saida / "mapa.json", json.dumps(mapa, ensure_ascii=False, indent=1))
    trocados = 0
    for rel_dir, pasta in pastas.items():
        destino = base / rel_dir / "_SKELETON.md" if rel_dir else base / "_SKELETON.md"
        if rel_dir.startswith('runs/'):
            continue   # cada execução (runs/<run>/) não ganha _SKELETON: a árvore fica no skeleton de runs/
        # dados/ e suas subpastas (ex.: dados/UNIT001/...) TÊM skeleton, como qualquer pasta do projeto
        if _escrever_se_mudou(destino, _skeleton_pasta(base, rel_dir, pasta, arquivos, pastas)):
            trocados += 1
    ctx = [f"# CONTEXTO DO LABORATÓRIO UNIT-001 (automático · {agora})", "",
           f"- framework: v{versoes.get('framework')} · linguagem: {versoes.get('unit_l')}",
           f"- entrada do usuário: UNIT001_laboratorio.ipynb · referência da linguagem: REFERENCIA_UNL.md",
           f"- código ativo: lib/framework/ (motor, registros, sentinela) · linguagem: lib/framework/lang/unl_spec.toml",
           f"- experimentos: experimentos/*.unl · execuções: runs/ ({len(pastas.get('runs', {}).get('subpastas', []))} runs; detalhe completo no _SKELETON.md de runs/)",
           f"- geometria canônica: lib/geometry/unit001_dataset_66_cases.py",
           "", "## Pastas", ""]
    for rel_dir in sorted(pastas):
        if rel_dir in ("", "."):
            continue
        ctx.append(f"- {rel_dir}/ — {PROPOSITO.get(rel_dir, '')}".rstrip(" —"))
        pasta = pastas[rel_dir]
        nomes = [r.split("/")[-1] for r in pasta.get("arquivos", [])]
        if pasta.get("contagem") is not None:
            # runs/, dados/: nomes das subpastas (não o conteúdo)
            subs = pasta.get("subpastas", [])
            ctx.append(f"    subpastas ({len(subs)}): " + ", ".join(sorted(subs)[:40]) + (" …" if len(subs) > 40 else ""))
        elif nomes:
            ctx.append("    arquivos: " + ", ".join(nomes[:40]) + (f" … (+{len(nomes) - 40})" if len(nomes) > 40 else ""))
    ctx += ["", "Para detalhes de um arquivo: _mapa/mapa.json (símbolos, hashes) ou o _SKELETON.md da pasta.", ""]
    _escrever_se_mudou(saida / "CONTEXTO_IA.md", "\n".join(ctx))
    return {"arquivos": len(arquivos), "pastas": len(pastas), "skeletons_atualizados": trocados, "gerado_em": agora}


def resumo_para_prompt():
    """Trecho curto para colocar no prompt de uma IA (aponta para o contexto detalhado)."""
    p = Path(__file__).resolve().parents[2] / "_mapa" / "CONTEXTO_IA.md"
    return p.read_text(encoding="utf-8")[:2500] if p.exists() else "(mapa ainda não gerado)"


if __name__ == "__main__":
    print(gerar())
