"""
EXEMPLO de plugin (começa com _ => não é carregado). Copie para plugins/meu_teste.py e edite.
Tudo que for registrado aqui aparece sozinho em /testes, /campos, /solvers e pode ser citado na spec AOP.
"""
import numpy as np
from lib.framework import test, field, solver, verifier


@test("razao_Tmax_ordenado_vs_aleatorio", description="Tmax médio RANDOM / ORDERED por frequência")
def t_razao(ds, params):
    rows = []
    for f in ds.frequencies():
        o = [c.scalars["Tmax_K"] for c in ds.select(geometry="ORDERED", frequency_thz=f).cases]
        r = [c.scalars["Tmax_K"] for c in ds.select(geometry="RANDOM", frequency_thz=f).cases]
        if o and r:
            rows.append({"f_THz": f, "razao": float(np.mean(r) / o[0])})
    return {"tabela": rows, "escalares": {"n_frequencias": len(rows)}}


# @field("minha_metrica", requires=("T", "domain_material_mask"), provides=("T_gradiente_max",))
# def f_grad(ctx):
#     T = ctx["arrays"]["T"]; ctx["scalars"]["T_gradmax"] = float(np.abs(np.gradient(T)[0]).max())

# @solver("meu_solver")           # contrato: devolve {"arrays": {"epsilon","Etotal"}, "grid": {dx,dy,dz,z_struct_start,z_struct_end,omega}, "scalars": {...}}
# def meu_solver(ctx): ...

# @verifier("assert_minha_regra")  # (runtime, valor_da_spec, ctx) -> [("OK"|"AVISO"|"FALHA", nome, detalhe)]
# def v(rt, val, ctx): return [("OK", "aop:minha_regra", "ok")]
