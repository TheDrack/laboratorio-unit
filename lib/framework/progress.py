"""progress.py — canal de eventos de execução. O laboratório lê este arquivo para mostrar o estado em tempo real.

Cada linha de <run>/progress.jsonl é um evento: {t, nivel, fonte, msg, mem_gb, extra}.
Sem UNIT_RUN_DIR (testes), vira no-op silencioso."""
import json
import os
import time
from pathlib import Path


def mem_rss_gb():
    try:
        for ln in open("/proc/self/status"):
            if ln.startswith("VmRSS:"):
                return int(ln.split()[1]) / 1e6
    except Exception:
        pass
    return float("nan")


def mem_avail_gb():
    try:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:"):
                return int(ln.split()[1]) / 1e6
    except Exception:
        pass
    return float("nan")


def emit(ctx_or_none, fonte, msg, **extra):
    d = os.environ.get("UNIT_RUN_DIR")
    if not d:
        return
    ev = {"t": round(time.time(), 2), "fonte": fonte, "msg": str(msg), "mem_gb": round(mem_rss_gb(), 3),
          "mem_disp_gb": round(mem_avail_gb(), 3), "extra": extra}
    try:
        with open(Path(d) / "progress.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
