"""specs.py — especificação AOP-DSL padrão (também gravada em specs/unit001_padrao.aop).
Todos os valores vêm de lib/geometry/unit001_constantes.py (início do processo)."""
from lib.geometry.unit001_constantes import (
    DX, N_FUNDO_ESTUDO, N_INCLUSAO_ESTUDO, K_FUNDO_ESTUDO, K_INCLUSAO_ESTUDO,
    NPML_CELLS, BUFFER_CELLS, FREQUENCIES_THZ,
)


def _complexo(z):
    """Formata no estilo do AOP (ex.: 2.0+0.05j)."""
    return f"{z.real!r}{z.imag:+}j"


DEFAULT_SPEC = f"""# UNIT-001 — especificação padrão (AOP-DSL)
STATE Dataset {{
  geometry_provider: "unit001_pillars"
  frequencies_thz: [{", ".join(repr(f) for f in FREQUENCIES_THZ)}]
  mesh_dx: {DX!r}
  n_bg: {_complexo(N_FUNDO_ESTUDO)}
  n_inclusion: {_complexo(N_INCLUSAO_ESTUDO)}
  k_bg: {K_FUNDO_ESTUDO!r}
  k_inclusion: {K_INCLUSAO_ESTUDO!r}
  npml_cells: {NPML_CELLS}
  buffer_cells: {BUFFER_CELLS}
}}

CAPABILITY Padrao {{
  solver: "fdfd3d_te_y"
  fields: ["thermal", "q_metrics"]
  allowed_modules: ["lib.framework", "lib.solvers", "lib.core", "lib.coupling", "lib.geometry", "lib.adapters"]
}}

AGENT Executor {{
  role: "executor"
  authority_level: 0
  allow_autocorrect: true
  max_retries: 2
}}

CONSTRAINT Limites {{
  max_volume_fraction: 0.125
  required_authority_level: 0
}}

VERIFICATION Estrutural {{
  assert_npz_finite: true
  assert_shapes_consistent: true
  assert_geometry_identity: true
  assert_q_outside_zero: true
  assert_power_balance: 1e-9
}}

ACTION Pipeline {{
  run: "pipeline"
  fail_fast: true
}}

PROVENANCE Auditoria {{
  track_hashes: ["lib/"]
  immutable_library: true
}}
"""
