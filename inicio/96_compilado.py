# versao: 1
# inicio/96_compilado.py — gera _mapa/CONTEXTO_COMPILADO.md: UM arquivo para anexar a qualquer IA.
# Roda a cada abertura, depois do mapa (95). Não edite à mão: o conteúdo vem dos arquivos de origem.
from datetime import datetime as _dt

_ORDEM_COMPILADO = [
    ("PROMPT INICIAL (como trabalhar com o laboratório)", "lib/PROMPT_INICIAL.md"),
    ("ESTADO ATUAL DO AMBIENTE", "_mapa/CONTEXTO_IA.md"),
    ("LINGUAGEM UNIT-L", "REFERENCIA_UNL.md"),
    ("PADRÃO DE ESTUDO", "lib/PADRAO_ESTUDO.md"),
    ("NOMENCLATURA", "lib/NOMENCLATURA.md"),
]

_partes = [
    f"# CONTEXTO COMPILADO — UNIT-001 (gerado em {_dt.now():%Y-%m-%d %H:%M})\n\n"
    "Anexe este arquivo a qualquer conversa com uma IA. Ele reúne tudo que ela precisa. "
    "Comece pela seção PROMPT INICIAL.\n"
]
_ausentes = []
for _titulo, _rel in _ORDEM_COMPILADO:
    _p = BASE / _rel
    if _p.exists():
        _partes.append(f"\n\n---\n\n## {_titulo}\n_fonte: {_rel}_\n\n" + _p.read_text(encoding="utf-8", errors="replace"))
    else:
        _ausentes.append(_rel)
(BASE / "_mapa" / "CONTEXTO_COMPILADO.md").write_text("".join(_partes), encoding="utf-8")
print("contexto compilado:", len(_partes) - 1, "seções" + (f" | ausentes: {', '.join(_ausentes)}" if _ausentes else ""))
