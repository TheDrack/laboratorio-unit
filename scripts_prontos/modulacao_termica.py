"""
modulacao_termica_v2.py  (REVISÃO v2)
UNIT-001.5 — modulação térmica contrafactual dos casos RANDOM.

Lê os casos salvos pelo extrator, re-resolve o problema térmico com um solver
próprio (-div(k grad T) = q, T=0 nas faces) e mede quanto T_max muda quando
k ou q são alterados de forma controlada. Experimentos CONTRAFACTUAIS: o campo
eletromagnético não é recalculado, só o problema térmico.

REVISÃO v2 — o que mudou:
 1. Constantes físicas vêm de lib/geometry/unit001_fisica.py (fonte única).
 2. Busca do NPZ corrigida: o extrator grava "{freq:.0f}THz" (ex.: 280THz).
    A versão anterior montava "280.0THz" e nunca encontrava o arquivo.
 3. Limiar material/fundo = LIMIAR_K (média geométrica de k_bg e k_pilar),
    no lugar de 100 e 50 fixos.
 4. Tolerância do autoteste derivada da ordem do erro de discretização
    O(dx²) do esquema de 7 pontos: TOL = 5·(1/(n-1))².
 5. Constantes de teste (q de teste, tolerâncias) nomeadas.
"""
import os
import sys
import json
import time
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from lib.geometry.unit001_constantes import (
    DX,
    K_BACKGROUND,
    K_PILLAR,
    LIMIAR_K,
)
from lib.geometry.unit001_dataset_66_cases import (
    RANDOM_SEEDS,
    FREQUENCIES_THZ,
)
from lib.geometry.unit001_constantes import (SEEDS_ALVO, FREQS_ALVO_THZ, TOL_CONSISTENCIA, TOL_ESCALA, TOL_RESIDUO_SISTEMA, FATOR_TOL_DISCRETIZACAO, Q_TESTE_ESCALA, ALFA_ESCALA)


# ───────────────────────── CONFIGURAÇÃO ─────────────────────────
# Subconjunto de casos a processar (deve estar contido no dataset).
FREQS_THZ = FREQS_ALVO_THZ

for _s in SEEDS_ALVO:
    if _s not in RANDOM_SEEDS:
        raise ValueError(f"seed {_s} não pertence ao dataset RANDOM_SEEDS")
for _f in FREQS_THZ:
    if _f not in FREQUENCIES_THZ:
        raise ValueError(f"frequência {_f} não pertence ao dataset FREQUENCIES_THZ")

CASES_DIR = None                    # ex.: "/content/resultados_geometrias/casos_individuais"



def tol_autoteste(n: int) -> float:
    """Tolerância do autoteste do cubo, ligada ao erro O(dx²) da discretização."""
    return FATOR_TOL_DISCRETIZACAO * (1.0 / (n - 1)) ** 2


# ───────────────────────── LOCALIZAÇÃO DOS CASOS ─────────────────────────
def localizar_cases_dir():
    candidatos = []
    if CASES_DIR:
        candidatos.append(Path(CASES_DIR))
    if os.environ.get("UNIT001_CASES_DIR"):
        candidatos.insert(0, Path(os.environ["UNIT001_CASES_DIR"]))
    if os.environ.get("UNIT_CASES_DIR"):
        candidatos.append(Path(os.environ["UNIT_CASES_DIR"]))
    rel = Path("resultados_geometrias") / "casos_individuais"
    candidatos += [
        Path.cwd() / rel,
        Path("/content") / rel,
        Path("/content/UNIT-001_WORK") / rel,
        Path("/content/drive/MyDrive/Colab Notebooks/UNIT-001/WORK") / rel,
        Path("/content/drive/MyDrive/Colab Notebooks/UNIT-001") / rel,
    ]
    candidatos += list(Path("/content").glob("*/casos_individuais"))
    candidatos += list(Path("/content").glob("*/*/casos_individuais"))
    for c in candidatos:
        if c.is_dir() and any(c.glob("*.npz")):
            return c
    raise FileNotFoundError(
        "Pasta dos casos não encontrada. Procurei em:\n "
        + "\n ".join(str(c) for c in candidatos[:10])
        + "\nDefina CASES_DIR no topo do script ou a variável UNIT001_CASES_DIR."
    )


def achar_arquivo(cases_dir: Path, seed: int, freq_thz: float) -> Path:
    """Mesmo nome que o extrator grava: RANDOM_seed_{seed}_{freq:.0f}THz.npz."""
    freq_txt = f"{freq_thz:.0f}"
    achados = sorted(cases_dir.glob(f"RANDOM_seed_{seed}_{freq_txt}THz.npz"))
    if len(achados) != 1:
        raise FileNotFoundError(
            f"esperava 1 arquivo 'RANDOM_seed_{seed}_{freq_txt}THz.npz' em {cases_dir}, "
            f"achei {len(achados)}"
        )
    return achados[0]


def carregar_caso(path: Path):
    with np.load(path, allow_pickle=False) as z:
        QN = "q_abs" if "q_abs" in z.files else "q_abs_thermal"
        faltando = [k for k in (QN, "T", "k_field") if k not in z.files]
        if faltando:
            raise KeyError(f"{path.name}: faltam chaves {faltando}; disponíveis: {z.files}")
        q, T, k = (np.asarray(z[n], dtype=float) for n in (QN, "T", "k_field"))
    if not (q.shape == T.shape == k.shape and q.ndim == 3):
        raise ValueError(f"{path.name}: shapes incompatíveis q{q.shape} T{T.shape} k{k.shape}")
    for nome, a in (("q_abs", q), ("T", T), ("k_field", k)):
        if not np.all(np.isfinite(a)):
            raise ValueError(f"{path.name}: {nome} contém NaN/Inf")
    if k.min() <= 0:
        raise ValueError(f"{path.name}: k_field com valor não positivo")
    return q, T, k


# ───────────────────────── SOLVER TÉRMICO ─────────────────────────
def resolver_T(q, k, dx):
    """
    Resolve -div(k grad T) = q com T=0 nas faces do domínio (Dirichlet).
    k nas interfaces: média harmônica. Só os nós internos entram no sistema e
    cada linha é normalizada pela diagonal (evita mau condicionamento com
    k de 0,026 a 148 e dx de 25 nm).
    """
    nx, ny, nz = k.shape
    n = nx * ny * nz
    interior = np.zeros(k.shape, dtype=bool)
    interior[1:-1, 1:-1, 1:-1] = True
    mapa = -np.ones(n, dtype=np.int64)
    n_int = int(interior.sum())
    mapa[interior.ravel()] = np.arange(n_int)
    mapa = mapa.reshape(k.shape)
    diag = np.zeros(k.shape)
    rows, cols, vals = [], [], []
    for ax in range(3):
        for passo in (+1, -1):
            sa, sb = [slice(None)] * 3, [slice(None)] * 3
            if passo == 1:
                sa[ax], sb[ax] = slice(0, -1), slice(1, None)
            else:
                sa[ax], sb[ax] = slice(1, None), slice(0, -1)
            sa, sb = tuple(sa), tuple(sb)
            ka, kb = k[sa], k[sb]
            km = 2.0 * ka * kb / (ka + kb) / dx ** 2
            lin = interior[sa]
            diag[sa] += km * lin
            col_int = lin & interior[sb]
            rows.append(mapa[sa][col_int])
            cols.append(mapa[sb][col_int])
            vals.append(-km[col_int])
    d = diag[interior]
    rows.append(np.arange(n_int))
    cols.append(np.arange(n_int))
    vals.append(d)
    A = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n_int, n_int),
    ).tocsr()
    dinv = 1.0 / d
    As = (coo_matrix((dinv, (np.arange(n_int), np.arange(n_int))), shape=(n_int, n_int)) @ A).tocsc()
    bs = q[interior] * dinv
    Ti = spsolve(As, bs)
    if not np.all(np.isfinite(Ti)):
        raise RuntimeError("solver térmico devolveu NaN/Inf")
    res_rel = float(np.linalg.norm(As @ Ti - bs) / max(np.linalg.norm(bs), 1e-300))
    if res_rel > TOL_RESIDUO_SISTEMA:
        raise RuntimeError(f"resíduo do sistema térmico alto: {res_rel:.2e}")
    T = np.zeros(k.shape)
    T[interior] = Ti
    return T


def autoteste_solver(n=33):
    """Cubo de lado L=1, k e q uniformes, T=0 nas faces: compara com a série de Fourier."""
    dx = 1.0 / (n - 1)
    T = resolver_T(np.ones((n, n, n)), np.ones((n, n, n)), dx)
    num = T[n // 2, n // 2, n // 2]
    ref = 0.0
    for m in range(1, 120, 2):
        for p in range(1, 120, 2):
            for r in range(1, 120, 2):
                s = (-1) ** ((m - 1) // 2 + (p - 1) // 2 + (r - 1) // 2)
                ref += 64.0 / (np.pi ** 5 * m * p * r * (m * m + p * p + r * r)) * s
    erro = abs(num - ref) / ref
    return float(num), float(ref), float(erro)


def autoteste_escala():
    """Alto contraste: T(q, k, dx·a) deve ser a² · T(q, k, dx)  (T ~ q dx² / k)."""
    k = np.full((12, 12, 20), K_BACKGROUND)
    k[3:6, 3:6, 6:12] = K_PILLAR
    q = np.where(k > LIMIAR_K, Q_TESTE_ESCALA, 0.0)
    T1 = resolver_T(q, k, DX)
    T2 = resolver_T(q, k, DX * ALFA_ESCALA)
    return float(np.abs(T2 / ALFA_ESCALA ** 2 - T1).max() / T1.max())


# ───────────────────────── EXPERIMENTOS ─────────────────────────
def experimentos(q, k, T0):
    hx, hy, hz = np.unravel_index(np.argmax(T0), T0.shape)
    nx, ny, nz = k.shape
    tmax0 = float(T0.max())
    # Exp1: troca k só no voxel do hotspot
    k1 = k.copy()
    k1[hx, hy, hz] = K_PILLAR
    t1 = float(resolver_T(q, k1, DX).max())
    # Exp2: ponte de k=K_PILLAR do hotspot até a face mais próxima
    dist = {"-X": hx, "+X": nx - 1 - hx, "-Y": hy, "+Y": ny - 1 - hy, "-Z": hz, "+Z": nz - 1 - hz}
    direcao = min(dist, key=dist.get)
    k2 = k.copy()
    c = [hx, hy, hz]
    eixo = {"X": 0, "Y": 1, "Z": 2}[direcao[1]]
    passo = -1 if direcao[0] == "-" else 1
    while 0 <= c[0] < nx and 0 <= c[1] < ny and 0 <= c[2] < nz:
        k2[c[0], c[1], c[2]] = K_PILLAR
        c[eixo] += passo
    t2 = float(resolver_T(q, k2, DX).max())
    # Exp3: mesma potência total, espalhada uniformemente nas células de pilar
    pilar = k >= LIMIAR_K
    q3 = np.zeros_like(q)
    q3[pilar] = q.sum() / max(int(pilar.sum()), 1)
    t3 = float(resolver_T(q3, k, DX).max())
    pot_q3_rel = abs(q3.sum() - q.sum()) / max(abs(q.sum()), 1e-300)
    pct = lambda t: 100.0 * (t - tmax0) / tmax0
    return {
        "hotspot": [int(hx), int(hy), int(hz)],
        "k_hotspot": float(k[hx, hy, hz]),
        "hotspot_em_fundo": bool(k[hx, hy, hz] < LIMIAR_K),
        "direcao_ponte": direcao,
        "celulas_ponte": int(dist[direcao] + 1),
        "n_celulas_pilar": int(pilar.sum()),
        "T_max_exp1": t1, "exp1_delta_pct": pct(t1),
        "T_max_exp2": t2, "exp2_delta_pct": pct(t2),
        "T_max_exp3": t3, "exp3_delta_pct": pct(t3),
        "exp3_erro_potencia_rel": float(pot_q3_rel),
    }


def processar(cases_dir, seed, freq_thz):
    arq = achar_arquivo(cases_dir, seed, freq_thz)
    q, T_arq, k = carregar_caso(arq)
    t0 = time.time()
    T0 = resolver_T(q, k, DX)
    erro_L2 = float(np.linalg.norm(T0 - T_arq) / max(np.linalg.norm(T_arq), 1e-300))
    hot_arq = [int(i) for i in np.unravel_index(np.argmax(T_arq), T_arq.shape)]
    r = {
        "caso": arq.name, "seed": seed, "freq_THz": freq_thz, "shape": list(k.shape),
        "P_abs_W": float(q.sum() * DX ** 3), "q_abs_min": float(q.min()),
        "T_max_arquivo": float(T_arq.max()), "T_max_resolvido": float(T0.max()),
        "consistencia_L2_rel": erro_L2, "hotspot_arquivo": hot_arq,
        "consistente": bool(erro_L2 <= TOL_CONSISTENCIA),
    }
    r.update(experimentos(q, k, T0))
    r["hotspot_coincide_arquivo"] = r["hotspot"] == hot_arq
    r["tempo_s"] = round(time.time() - t0, 2)
    return r


def main():
    print("=" * 90)
    print("UNIT-001.5 — MODULAÇÃO TÉRMICA CONTRAFACTUAL (v2)")
    print("=" * 90)

    num, ref, err = autoteste_solver()
    tol = tol_autoteste(33)
    print(f"[autoteste solver] cubo analítico: numérico={num:.6f} referência={ref:.6f} "
          f"erro_rel={err:.2e} (tolerância {tol:.2e})")
    if err > tol:
        raise RuntimeError("autoteste do solver reprovado; resultados não seriam confiáveis")

    err_esc = autoteste_escala()
    print(f"[autoteste escala/contraste] erro_rel={err_esc:.2e} (tolerância {TOL_ESCALA:.0e})")
    if err_esc > TOL_ESCALA:
        raise RuntimeError("autoteste de escala reprovado; solver mal condicionado")

    cases_dir = localizar_cases_dir()
    print(f"[casos] {cases_dir}")

    resultados, falhas = [], []
    for seed in SEEDS_ALVO:
        for f in FREQS_THZ:
            try:
                r = processar(cases_dir, seed, f)
                resultados.append(r)
                print(f"RANDOM_{seed} {f:.0f}THz | T_max={r['T_max_resolvido']:.4e} K | "
                      f"hotspot={r['hotspot']} k={r['k_hotspot']:g} | "
                      f"consist.L2={r['consistencia_L2_rel']:.2e} | "
                      f"Exp1 {r['exp1_delta_pct']:+.2f}% Exp2 {r['exp2_delta_pct']:+.2f}% "
                      f"Exp3 {r['exp3_delta_pct']:+.2f}%")
            except Exception as e:
                falhas.append({"seed": seed, "freq_THz": f, "erro": f"{type(e).__name__}: {e}"})
                print(f"FALHA RANDOM_{seed} {f:.0f}THz: {type(e).__name__}: {e}")

    out_dir = Path(os.environ.get("UNIT_RUN_DIR", "."))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "modulacao_resultados.json").write_text(
        json.dumps({
            "config": {"DX_m": DX, "K_PILLAR": K_PILLAR, "K_BACKGROUND": K_BACKGROUND,
                       "LIMIAR_K": LIMIAR_K, "TOL_CONSISTENCIA": TOL_CONSISTENCIA},
            "autoteste": {"numerico": num, "referencia": ref, "erro_rel": err, "tolerancia": tol},
            "resultados": resultados, "falhas": falhas,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cols = ["seed", "freq_THz", "T_max_resolvido", "T_max_arquivo", "consistencia_L2_rel",
            "hotspot", "k_hotspot", "hotspot_em_fundo", "exp1_delta_pct", "exp2_delta_pct",
            "exp3_delta_pct", "exp3_erro_potencia_rel"]
    tabela = [{c: r[c] for c in cols} for r in resultados]
    escalares = {
        "n_casos": len(resultados), "n_falhas": len(falhas), "dx_m": DX,
        "autoteste_erro_rel": err, "autoteste_escala_erro_rel": err_esc,
        "n_inconsistentes_com_arquivo": sum(not r["consistente"] for r in resultados),
    }
    print("UNIT_RESULT_JSON: " + json.dumps({"tabela": tabela, "escalares": escalares},
                                           ensure_ascii=False))
    if not resultados:
        sys.exit("nenhum caso foi processado (veja as FALHAs acima)")


if __name__ == "__main__":
    main()
