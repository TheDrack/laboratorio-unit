"""
inicio.py — roda AUTOMATICAMENTE, a cada abertura do laboratório, os arquivos de <laboratório>/inicio/.

Cada arquivo NN_nome.py é executado como uma CÉLULA do notebook, no MESMO namespace (as variáveis e
funções de um arquivo ficam disponíveis para os seguintes). Ordem: pelo nome (use 00_, 10_, 20_...).
Ignorados: nomes que começam com "_" ou "desativado".

Se um arquivo falhar, os outros continuam; o erro vai para o status. Ao final, se existir a função
abrir_chat(), o runner a chama (o chat abre por último).

Para adicionar um processo padrão: crie NN_nome.py dentro de inicio/. Não precisa mexer no notebook.
Status de cada execução: _mapa/inicio_status.json (lido pelas IAs como contexto).
"""
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

# Criados só se não existirem (nunca sobrescrevem os seus).
DEFAULTS = {
    "95_mapa.py": ("# inicio/95_mapa.py — mapa de contexto automático\n"
                   "from lib.framework import mapa as _mapa\n_r = _mapa.gerar(BASE)\nprint('mapa atualizado:', _r)\n"),
}


def _scripts(pasta):
    for p in sorted(pasta.glob("*.py")):
        if p.name.startswith(("_", ".")) or p.name.startswith("desativado"):
            continue
        yield p


def rodar(base=None, ns=None):
    """Executa inicio/ no namespace ns (passe globals() do notebook). Devolve o status."""
    base = Path(base) if base else Path(__file__).resolve().parents[2]
    ns = ns if ns is not None else {}
    ns.setdefault("BASE", base)
    pasta = base / "inicio"
    pasta.mkdir(exist_ok=True)
    for nome, texto in DEFAULTS.items():
        if not (pasta / nome).exists():
            (pasta / nome).write_text(texto, encoding="utf-8")
    status = []
    for p in _scripts(pasta):
        t0 = time.time()
        try:
            exec(compile(p.read_text(encoding="utf-8"), str(p), "exec"), ns)
            status.append({"script": p.name, "status": "ok", "tempo_s": round(time.time() - t0, 2)})
        except (Exception, SystemExit) as e:
            status.append({"script": p.name, "status": "erro", "tempo_s": round(time.time() - t0, 2),
                           "erro": f"{type(e).__name__}: {e}", "detalhe": traceback.format_exc(limit=4)[-700:]})
    if callable(ns.get("abrir_chat")):
        t0 = time.time()
        try:
            ns["abrir_chat"]()
            status.append({"script": "abrir_chat()", "status": "ok", "tempo_s": round(time.time() - t0, 2)})
        except Exception as e:
            status.append({"script": "abrir_chat()", "status": "erro", "erro": f"{type(e).__name__}: {e}"})
    saida = base / "_mapa"
    saida.mkdir(exist_ok=True)
    (saida / "inicio_status.json").write_text(json.dumps(
        {"em": datetime.now().isoformat(timespec="seconds"), "scripts": status}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    for s in status:
        extra = f" — {s['erro']}" if s["status"] == "erro" else ""
        print(f"[inicio] {s['script']}: {s['status']}{extra}")
    return status
