"""
gerar_catalogo_geometrico.py — roda o gerador canônico DENTRO do laboratório e persiste o catálogo.
REVISÃO v2: usa os nomes atuais do dataset e contagens derivadas (sem 22/66 fixos).
Saída: $UNIT001_DATA_ROOT/geometria/{geometry_catalog.json, geometry_masks.npz, geometry_hashes.json}
"""
import json
import os
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
    assert len(rel) == G.N_GEOMETRIES and len(cases) == G.N_CASES
    print(f"n_geometrias = {len(geoms)}")
    print(f"n_casos = {len(cases)}")
    print(f"catalogo_dir: {out}")
    print("UNIT_RESULT_JSON: " + json.dumps({
        "tabela": [{"geometria": g["geometry"], "seed": g["seed"], "geometry_hash": g["geometry_hash"][:16]} for g in geoms],
        "escalares": {"n_geometrias": len(geoms), "n_casos": len(cases), "schema": G.DATASET_SCHEMA_VERSION},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
