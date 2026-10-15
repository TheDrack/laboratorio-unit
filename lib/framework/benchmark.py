"""benchmark.py — mede tempo e memória de UM ponto, pelo MESMO caminho isolado e vigiado do motor (sentinela).

Uso pelo chat: /medir ppw=60 backend=iterative geometria=ORDERED freq=300
Gera um experimento UNIT-L de um ponto, executa com o motor (processo filho + sentinela) e devolve tempo e pico de RAM.
"""
import json
import time

from lib.framework import registry as R
from lib.framework import progress as PG


def _unl(ppw, backend, geometria, freq):
    return f"""EXPERIMENT Medir {{
    CASE    geometry = [{geometria}]
    FIX     frequency_thz = {float(freq)}, n_bg = N_FUNDO_ESTUDO, n_inclusion = N_INCLUSAO_ESTUDO, pml_nm = PML_NM_ESTUDO, buffer_nm = BUFFER_NM_ESTUDO, ppw = {float(ppw)}
    SOLVE   fdfd3d_te_y, backend={backend}
    MEASURE R = R_power, T = T_power
    OUTPUT  tables=[cases]
}}
"""


def medir(ppw, backend="iterative", geometria="ORDERED", freq=300.0, reserva_gb=1.0, timeout_s=3600):
    from lib.framework import experiment as X
    from lib.framework import aop_dsl
    from lib.framework.specs import DEFAULT_SPEC
    R.ensure_loaded()
    texto = _unl(ppw, backend, geometria, freq).replace("SOLVE   fdfd3d_te_y, backend=", f"SOLVE   fdfd3d_te_y, reserva_gb={float(reserva_gb)}, timeout_s={float(timeout_s)}, backend=")
    exp = X.parse(texto)
    rt = aop_dsl.AOPRuntime(aop_dsl.parse(DEFAULT_SPEC))
    t0 = time.time()
    PG.emit(None, "bench", f"ppw={ppw} backend={backend} {geometria} {freq} THz: iniciando (processo isolado)")
    res = X.run_experiment(exp, rt, log=lambda m: PG.emit(None, "bench", m), fail_fast=True)
    row = res["rows"][0] if res["rows"] else {}
    out = {"ppw": float(ppw), "backend": backend, "geometria": geometria, "freq_thz": float(freq),
           "status": row.get("_status", "sem_resultado"), "tempo_s": row.get("tempo_s", round(time.time() - t0, 1)),
           "rss_pico_gb": row.get("rss_pico_gb"), "R": row.get("R"), "T": row.get("T"),
           "nota": "" if row.get("_status") == "ok" else res["provenance"]["points"][0].get("status", "")}
    PG.emit(None, "bench", f"{out['status']} · {out['tempo_s']} s · pico {out['rss_pico_gb']} GB")
    if out["status"] != "ok":
        raise RuntimeError(f"/medir não concluiu: status={out['status']}. {out['nota']}")
    return out
