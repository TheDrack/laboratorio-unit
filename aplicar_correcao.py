#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aplicar_correcao.py — religa GERADOR -> EXTRATOR dentro do laboratório UNIT-001.

Uso (Colab ou local):
  python aplicar_correcao.py --base "/content/drive/MyDrive/Colab Notebooks/UNIT-001_AGENTES" \
      --gerador  <arquivo do gerador canônico atual, qualquer nome> \
      --extrator <arquivo do extrator v7> \
      [--notebook <UNIT001_laboratorio_multiagente.ipynb>]

O que faz (cada troca exige 1 ocorrência exata; senão avisa e não mexe):
  1. gerador  -> BASE/lib/geometry/unit001_dataset_66_cases.py  (+ __main__ grava em dados/UNIT001/geometria)
  2. extrator -> BASE/scripts_prontos/extrator_legado.py (imports via lib.*, OUTPUT_DIR por variável de ambiente,
                 confere hashes contra o catálogo persistido)
  3. cria scripts_prontos/gerar_catalogo_geometrico.py (roda o gerador DENTRO do laboratório e persiste o catálogo)
  4. notebook -> Célula 4: executar() passa a repassar variáveis UNIT001_* ao run
Faz .bak de tudo que sobrescrever.
"""
import argparse, json, shutil, sys
from pathlib import Path

GERADOR = [
 ("import hashlib\nimport json\n", "import hashlib\nimport json\nimport os\n", "import os"),
 ('    OUTPUT_DIR = Path(\n        "unit001_dataset_66_cases"\n    )\n',
  '    _root = os.environ.get("UNIT001_DATA_ROOT")\n'
  '    if _root:\n        OUTPUT_DIR = Path(_root) / "geometria"\n'
  '    else:\n        print("AVISO: UNIT001_DATA_ROOT ausente; gravando em pasta RELATIVA (efêmera dentro de um run).")\n'
  '        OUTPUT_DIR = Path("unit001_dataset_66_cases")\n', "OUTPUT_DIR persistente"),
]

EXTRATOR = [
 ("import json\nimport traceback\n", "import json\nimport os\nimport traceback\n", "import os"),
 ("from unit001_dataset_66_cases import (", "from lib.geometry.unit001_dataset_66_cases import (", "import do gerador via lib.*"),
 ('OUTPUT_DIR = (\n    Path(__file__).resolve().parents[1]\n    / "dados"\n    / "UNIT001"\n    / "resultados"\n    / "extrator"\n)\n',
  '''def _resolver_output_dir() -> Path:
    """Dentro do laboratório, __file__ = runs/run_NNN/code.py, então parents[1] seria BASE/runs (errado).
    A fonte oficial é UNIT001_RESULTS_DIR (exportada pela Célula 1 e repassada por executar())."""
    env = os.environ.get("UNIT001_RESULTS_DIR")
    if env:
        return Path(env) / "extrator"
    here = Path(__file__).resolve()
    if here.parent.name == "scripts_prontos":
        return here.parents[1] / "dados" / "UNIT001" / "resultados" / "extrator"
    raise RuntimeError(
        "UNIT001_RESULTS_DIR ausente e o script não está em scripts_prontos/. "
        "Recusando gravar em caminho adivinhado (isso já fez os casos irem parar em runs/dados/)."
    )


OUTPUT_DIR = _resolver_output_dir()
''', "OUTPUT_DIR via ambiente"),
 ('    validate_geometry_identity(\n        geometry_name="ORDERED",\n        seed=None,\n        geom_struct=geom_struct,\n    )\n',
  '    # (identidade validada em run_case; aqui NÃO fixar "ORDERED")\n', "remove ORDERED fixo"),
 ("def main() -> None:\n",
  '''REQUIRE_PERSISTED_CATALOG = False


def verificar_catalogo_persistido(all_geometries) -> None:
    """Confere as geometrias regeneradas contra dados/UNIT001/geometria/geometry_hashes.json
    (gravado por gerar_catalogo_geometrico.py). Divergência = erro."""
    root = os.environ.get("UNIT001_DATA_ROOT")
    path = Path(root) / "geometria" / "geometry_hashes.json" if root else None
    if path is None or not path.exists():
        msg = f"catálogo persistido não encontrado ({path}); rode gerar_catalogo_geometrico.py"
        if REQUIRE_PERSISTED_CATALOG:
            raise FileNotFoundError(msg)
        print("AVISO:", msg)
        return
    persistido = {(r["geometry"], r["seed"]): r["geometry_hash"] for r in json.loads(path.read_text(encoding="utf-8"))}
    atual = {(g["geometry"], g["seed"]): g["geometry_hash"] for g in all_geometries}
    if persistido != atual:
        faltam = sorted(map(str, set(persistido) ^ set(atual)))
        difer = sorted(str(k) for k in set(persistido) & set(atual) if persistido[k] != atual[k])
        raise RuntimeError(f"Catálogo persistido diverge do gerador. chaves só de um lado={faltam[:5]} hash diferente={difer[:5]}")
    print(f"Catálogo persistido confere: {len(atual)} geometrias ({path})")


def main() -> None:
''', "verificação do catálogo persistido"),
 ('    print(\n        f"Geometrias canônicas: "\n        f"{len(all_geometries)}"\n    )\n',
  '    print(\n        f"Geometrias canônicas: "\n        f"{len(all_geometries)}"\n    )\n\n    verificar_catalogo_persistido(all_geometries)\n',
  "chama a verificação"),
]

NOTEBOOK = [
 ('            chave.startswith("UNIT_")\n            and chave != "UNIT_RUN_DIR"',
  '            chave.startswith(("UNIT_", "UNIT001_"))\n            and chave != "UNIT_RUN_DIR"',
  "executar(): repassar UNIT001_*"),
]

WRAPPER = '''"""
gerar_catalogo_geometrico.py — roda o gerador canônico DENTRO do laboratório e persiste o catálogo.
Saída: $UNIT001_DATA_ROOT/geometria/{geometry_catalog.json, geometry_masks.npz, geometry_hashes.json}
"""
import json, os
from pathlib import Path
from lib.geometry import unit001_dataset_66_cases as G


def main():
    root = os.environ.get("UNIT001_DATA_ROOT")
    if not root:
        raise SystemExit("UNIT001_DATA_ROOT ausente no ambiente do run (executar() precisa repassar UNIT001_*).")
    out = Path(root) / "geometria"
    G.run_self_tests()
    geoms = G.generate_all_geometries()
    cases = G.generate_all_cases()
    G.save_geometry_catalog(geoms, out / "geometry_catalog.json")
    G.save_geometry_masks(geoms, out / "geometry_masks.npz")
    G.save_geometry_hashes(geoms, out / "geometry_hashes.json")
    rel = json.loads((out / "geometry_hashes.json").read_text(encoding="utf-8"))
    assert len(rel) == 22 and len(cases) == 66
    print(f"n_geometrias = {len(geoms)}")
    print(f"n_casos = {len(cases)}")
    print(f"catalogo_dir: {out}")
    print("UNIT_RESULT_JSON: " + json.dumps({
        "tabela": [{"geometria": g["geometry"], "seed": g["seed"], "geometry_hash": g["geometry_hash"][:16]} for g in geoms],
        "escalares": {"n_geometrias": len(geoms), "n_casos": len(cases), "schema": G.DATASET_SCHEMA_VERSION},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


def aplicar(texto, patches, rotulo):
    ok = True
    for old, new, desc in patches:
        n = texto.count(old)
        if n == 1:
            texto = texto.replace(old, new); print(f"  [ok]      {rotulo}: {desc}")
        elif n == 0 and new in texto:
            print(f"  [já feito] {rotulo}: {desc}")
        else:
            ok = False; print(f"  [FALHOU]  {rotulo}: {desc} (ocorrências do trecho original: {n}) — NÃO alterado, aplique à mão")
    return texto, ok


def gravar(path, texto):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, str(path) + ".bak")
    path.write_text(texto, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--gerador", required=True)
    ap.add_argument("--extrator", required=True); ap.add_argument("--notebook")
    a = ap.parse_args()
    base = Path(a.base); ok_geral = True

    print("GERADOR")
    t, ok = aplicar(Path(a.gerador).read_text(encoding="utf-8"), GERADOR, "gerador"); ok_geral &= ok
    if "def get_geometry" not in t or "geometry_hash" not in t:
        print("  [ERRO] este arquivo NÃO é o gerador canônico (faltam get_geometry/geometry_hash) — provavelmente a versão antiga."); sys.exit(2)
    gravar(base / "lib" / "geometry" / "unit001_dataset_66_cases.py", t)
    for init in (base / "lib" / "__init__.py", base / "lib" / "geometry" / "__init__.py"):
        if not init.exists(): init.write_text("", encoding="utf-8")

    print("EXTRATOR")
    t, ok = aplicar(Path(a.extrator).read_text(encoding="utf-8"), EXTRATOR, "extrator"); ok_geral &= ok
    gravar(base / "scripts_prontos" / "extrator_legado.py", t)

    gravar(base / "scripts_prontos" / "gerar_catalogo_geometrico.py", WRAPPER)
    print("WRAPPER  scripts_prontos/gerar_catalogo_geometrico.py criado")

    if a.notebook:
        print("NOTEBOOK")
        nbp = Path(a.notebook); nb = json.loads(nbp.read_text(encoding="utf-8")); feito = False
        for c in nb["cells"]:
            if c["cell_type"] != "code": continue
            src = "".join(c["source"])
            if "def executar(" not in src: continue
            novo, ok = aplicar(src, NOTEBOOK, "notebook"); ok_geral &= ok
            c["source"] = novo.splitlines(keepends=True); feito = True
        if not feito: print("  [FALHOU] célula com executar() não encontrada"); ok_geral = False
        gravar(nbp, json.dumps(nb, ensure_ascii=False, indent=1))

    # cópias antigas do gerador que poderiam ser importadas por engano
    for p in list(base.glob("lib/**/*.py")) + list(base.glob("scripts_prontos/*.py")):
        t = p.read_text(encoding="utf-8", errors="ignore")
        if "def generate_all_geometries" in t and "def get_geometry" not in t:
            print(f"AVISO: {p} é uma versão ANTIGA do gerador (sem get_geometry/hash) — apague/renomeie.")
    print("\nRESULTADO:", "tudo aplicado" if ok_geral else "há trechos que falharam (veja acima)")
    sys.exit(0 if ok_geral else 1)


if __name__ == "__main__":
    main()
