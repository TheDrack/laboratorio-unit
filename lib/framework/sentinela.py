"""sentinela.py — vigia de memória em tempo real.

Por que existe: a memória disponível depende da máquina que está rodando AGORA (Colab tem ~12 GB, sandbox 3 GB,
e o próprio Colab pode ter outros processos). Decidir uma vez no planejamento não basta.

Como funciona:
- memoria_disponivel_gb(): menor valor entre MemAvailable e o limite do container (cgroup), lido na hora.
- run_isolated(payload, ...): executa UM ponto num processo filho (spawn). O pai observa o filho a cada ~1 s:
  se a memória disponível cair abaixo da reserva, encerra o filho e devolve 'abortado_memoria'.
  O laboratório (e o Colab) continuam vivos; o ponto é declarado, não perdido em silêncio.
"""
import multiprocessing as mp
import os
import queue
import sys
import time
import types

from lib.framework import progress as PG


def memoria_disponivel_gb():
    vals = []
    try:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:"):
                vals.append(int(ln.split()[1]) / 1e6)
    except Exception:
        pass
    # limite de container (cgroup v2, depois v1)
    for lim_p, cur_p in (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
                         ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes")):
        try:
            lim = open(lim_p).read().strip()
            cur = int(open(cur_p).read().strip())
            if lim != "max" and int(lim) < 1 << 60:
                vals.append((int(lim) - cur) / 1e9)
            break
        except Exception:
            continue
    try:
        import resource
        soft = resource.getrlimit(resource.RLIMIT_AS)[0]
        if soft not in (-1, resource.RLIM_INFINITY):
            vals.append(soft / 1e9)
    except Exception:
        pass
    return min(vals) if vals else float("nan")


def rss_gb(pid):
    try:
        for ln in open(f"/proc/{pid}/status"):
            if ln.startswith("VmRSS:"):
                return int(ln.split()[1]) / 1e6
    except Exception:
        pass
    return float("nan")


def run_isolated(target, payload, *, reserva_gb=1.0, timeout_s=1800, label="", sample_s=1.0):
    """Roda target(payload, q) num processo filho sob vigilância.
    Devolve {'status': 'ok'|'erro'|'abortado_memoria'|'timeout'|'morto', 'data': ..., 'pico_gb': ..., 'min_disp_gb': ...}."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=target, args=(payload, q), daemon=True)
    t0 = time.time()
    # O 'spawn' reexecuta o script principal no filho (__main__.__file__). Num run do laboratório o script principal
    # é o code.py, que chama o próprio benchmark: o filho entraria em recursão. Durante o start, o __main__ é trocado
    # por um módulo sem __file__ (o filho só precisa de target importável, que é 'lib.framework.experiment._point_worker').
    _main_saved = sys.modules.get("__main__")
    sys.modules["__main__"] = types.ModuleType("__main__")
    try:
        p.start()
    finally:
        if _main_saved is not None:
            sys.modules["__main__"] = _main_saved
    pico, min_disp, last_emit = 0.0, float("inf"), 0.0
    while True:
        try:
            kind, data = q.get(timeout=sample_s)
            p.join(10)
            return {"status": kind, "data": data, "pico_gb": pico, "min_disp_gb": min_disp, "tempo_s": time.time() - t0}
        except queue.Empty:
            pass
        if not p.is_alive():
            return {"status": "morto", "data": f"processo terminou sem resultado (código {p.exitcode}); provável falta de memória",
                    "pico_gb": pico, "min_disp_gb": min_disp, "tempo_s": time.time() - t0}
        rss, disp = rss_gb(p.pid), memoria_disponivel_gb()
        if rss == rss:
            pico = max(pico, rss)
        if disp == disp:
            min_disp = min(min_disp, disp)
        now = time.time()
        if now - last_emit >= 5:
            PG.emit(None, "sentinela", f"{label}: RSS do ponto {rss:.2f} GB · disponível {disp:.2f} GB · reserva {reserva_gb:.2f} GB")
            last_emit = now
        if disp == disp and disp < reserva_gb:
            p.terminate(); p.join(10)
            PG.emit(None, "sentinela", f"{label}: ABORTADO — disponível {disp:.2f} GB < reserva {reserva_gb:.2f} GB")
            return {"status": "abortado_memoria", "data": f"memória disponível caiu para {disp:.2f} GB (reserva {reserva_gb:.2f} GB)",
                    "pico_gb": pico, "min_disp_gb": min_disp, "tempo_s": time.time() - t0}
        if now - t0 > timeout_s:
            p.terminate(); p.join(10)
            return {"status": "timeout", "data": f"excedeu {timeout_s} s", "pico_gb": pico, "min_disp_gb": min_disp, "tempo_s": time.time() - t0}
