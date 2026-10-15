"""
rodar_testes.py — bateria unificada de validação do UNIT-001.

Todos os parâmetros vêm de lib/geometry/parametros_estudo.json (via unit001_constantes).
Critérios derivados da física, aplicados igualmente a todos os solvers:
  1) Ordem de convergência p = log(e_first / e_last) / log(ppw_last / ppw_first) ≈ ordem teórica.
  2) Conservação: |R + T + A - 1| <= erro de discretização em cada malha.

Uso (Colab):
    from lib.validation.rodar_testes import rodar_tudo
    rodar_tudo()
"""
import datetime
import json
import math
import pathlib
import re
import traceback

from lib.geometry import unit001_constantes as C

RAIZ = pathlib.Path(C.__file__).resolve().parents[2]


def _criterio(casos):
    e_first = max(casos[0]["errR"], casos[0]["errT"])
    e_last = max(casos[-1]["errR"], casos[-1]["errT"])
    ratio = casos[-1]["ppw"] / casos[0]["ppw"]
    p = math.log(e_first / e_last) / math.log(ratio)
    ok_ordem = abs(p - C.ORDEM_TEORICA_2A) <= C.TOL_ORDEM_CONVERGENCIA
    ok_cons = all(c["cons"] <= max(c["errR"], c["errT"]) for c in casos)
    return {"p": p, "ok_ordem": ok_ordem, "ok_conservacao": ok_cons,
            "status": "PASS" if (ok_ordem and ok_cons) else "FAIL"}


def _teste_fdfd2d_lamina():
    from lib.solvers.fdfd2d import validate_homogeneous_slab
    lam, n_bg, n_slab, thk = (C.LAMINA_TESTE_LAMBDA0, C.LAMINA_TESTE_N_BG,
                              C.LAMINA_TESTE_N_SLAB, C.LAMINA_TESTE_ESPESSURA)
    casos = []
    for ppw in C.NIVEIS_PPW_CONVERGENCIA:
        dz = lam / (max(abs(n_bg), abs(n_slab)) * ppw)
        buffer = math.ceil(lam / dz)
        r = validate_homogeneous_slab(wavelength=lam, n_bg=n_bg, n_slab=n_slab, thickness=thk,
                                      resolution_ppw=ppw, npml_cells=C.NPML_COMPARADOR_FDFD,
                                      buffer_cells=buffer, nx=C.NX_COMPARADOR_FDFD)
        casos.append({"ppw": ppw, "errR": r["dR"], "errT": r["dT"],
                      "cons": r["A_difference"]})
        print(f"  ppw={ppw}: |dR|={r['dR']:.2e} |dT|={r['dT']:.2e} "
              f"|A_flux-A_vol|={r['A_difference']:.2e}")
    out = _criterio(casos)
    out["casos"] = casos
    return out


def _teste_fdfd3d():
    from lib.validation import validate_fdfd3d as V
    return V.main()


def _teste_fdtd3d_cw():
    from lib.validation import validate_fdtd3d as V
    return V.main()


def _teste_parser():
    from lib.framework.lang import parser as P
    exp = P.parse("EXPERIMENT Teste {\n  FIX n_inclusion = N_INCLUSAO_ESTUDO, "
                  "n_bg = N_FUNDO_ESTUDO\n}\n")
    v = exp.of("FIX")[0].data
    ok = v["n_inclusion"] == C.N_INCLUSAO_ESTUDO and v["n_bg"] == C.N_FUNDO_ESTUDO
    return {"status": "PASS" if ok else "FAIL", "valores": {k: str(x) for k, x in v.items()}}


def _teste_constantes():
    d_max = round(C.MONITOR_OFFSET_FRAC * C.LAMBDA0_MAX / C.DX)
    ok = (C.BUFFER_CELLS >= 2 * d_max and C.NPML_CELLS >= 1
          and C.K_BACKGROUND < C.LIMIAR_K < C.K_PILLAR)
    return {"status": "PASS" if ok else "FAIL", "NPML": C.NPML_CELLS,
            "BUFFER": C.BUFFER_CELLS, "d_max": d_max}


def _teste_copias_de_constantes():
    padrao = re.compile(r"^(C_LIGHT|EPS0|MU0|Z0) = ", re.M)
    achados = []
    for p in RAIZ.rglob("*.py"):
        rel = p.relative_to(RAIZ).as_posix()
        if ("__pycache__" in rel or rel.startswith(("dados/", "runs/", "comunicacao/", "validacao/"))
                or rel == "lib/geometry/unit001_constantes.py"):
            continue
        for m in padrao.finditer(p.read_text(encoding="utf-8")):
            achados.append(f"{rel}: {m.group(0).strip()}")
    return {"status": "PASS" if not achados else "FAIL", "achados": achados}


def _executar(nome, fn, resultados):
    print("=" * 90)
    print(nome)
    print("=" * 90)
    try:
        out = fn()
    except Exception as e:
        out = {"status": "ERRO", "erro": f"{type(e).__name__}: {e}",
               "traceback": traceback.format_exc()}
        traceback.print_exc()
    resultados[nome] = out
    print(f"--> {nome}: {out.get('status')}\n")


def rodar_tudo(gravar=True):
    resultados = {}
    _executar("constantes", _teste_constantes, resultados)
    _executar("parser_unl", _teste_parser, resultados)
    _executar("copias_de_constantes", _teste_copias_de_constantes, resultados)
    _executar("fdfd2d_lamina", _teste_fdfd2d_lamina, resultados)
    _executar("fdfd3d_lamina", _teste_fdfd3d, resultados)
    _executar("fdtd3d_cw_lamina", _teste_fdtd3d_cw, resultados)

    agora = datetime.datetime.now()
    relatorio = {
        "data": agora.isoformat(timespec="seconds"),
        "parametros_arquivo": "lib/geometry/parametros_estudo.json",
        "parametros": json.loads((C.__file__ and pathlib.Path(C.__file__).with_name(
            "parametros_estudo.json")).read_text(encoding="utf-8")),
        "resultados": resultados,
        "resumo": {k: v.get("status") for k, v in resultados.items()},
    }
    if gravar:
        pasta = RAIZ / "validacao" / "relatorios"
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / f"{agora:%Y-%m-%d_%H%M%S}_testes.json"
        arq.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        print(f"relatório gravado: {arq}")

    print("=" * 90)
    print("RESUMO")
    print("=" * 90)
    for k, v in relatorio["resumo"].items():
        print(f"  {str(v):<6} {k}")
    return relatorio
