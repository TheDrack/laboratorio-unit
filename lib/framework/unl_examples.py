"""unl_examples.py — experimentos de referência em UNIT-L (instalados em experimentos/)."""

T2_CONVERGENCIA = """# T2 — calibração de convergência numérica (piso de erro e E_crit operacional)
EXPERIMENT T2_convergencia {
    GOAL    "Piso numérico de R, T e chi95 por refinamento de malha (PPW 15, 30, 60) e E_crit operacional"

    CASE    geometry = [ORDERED, CLUSTERED, RANDOM_1000]

    # invariantes físicos: o motor confere que NADA além da resolução mudou.
    # PML/buffer em nm: múltiplos exatos de dx nos três níveis (200 nm = 6/12/24 células; 300 nm = 9/18/36)
    FIX     frequency_thz = 300.0, n_bg = N_FUNDO_ESTUDO, n_inclusion = N_INCLUSAO_ESTUDO, pml_nm = PML_NM_ESTUDO, buffer_nm = BUFFER_NM_ESTUDO

    VARY    ppw = [15, 30, 60]

    SOLVE   fdfd3d_te_y

    MEASURE R = R_power, T = T_power, A = A_volume, chi95, A_flux = A_flux_power, f_discreta, ppw_efetivo

    # fechamento independente: A vem da integral de q no volume, não de 1-R-T
    DERIVE  closure = 1 - R - T - A
    LIMIT   closure_tol = pending
    CHECK   fechamento_energia : abs(closure) <= closure_tol

    COMPARE passos = successive_diff(of=[R, T, chi95], along=ppw, group_by=[geometry])
    ANALYZE conv   = convergence(of=[R, T, chi95], along=ppw, group_by=[geometry], safety_factor=3, working_ppw=20)

    OUTPUT  tables=[cases, passos, conv], scalars=[conv]
}
"""

T2_LEVE = """# T2 (variante leve): níveis que cabem em ~8 GB. Mesma física do T2; só os níveis de ppw mudam.
EXPERIMENT T2_leve {
    GOAL    "Piso numérico de R, T e chi95 com PPW 15, 20, 30 (viável sem memória extra)"
    CASE    geometry = [ORDERED, CLUSTERED, RANDOM_1000]
    FIX     frequency_thz = 300.0, n_bg = N_FUNDO_ESTUDO, n_inclusion = N_INCLUSAO_ESTUDO, pml_nm = PML_NM_ESTUDO, buffer_nm = BUFFER_NM_ESTUDO
    VARY    ppw = [15, 20, 30]
    SOLVE   fdfd3d_te_y
    MEASURE R = R_power, T = T_power, A = A_volume, chi95, f_discreta, ppw_efetivo
    DERIVE  closure = 1 - R - T - A
    LIMIT   closure_tol = pending
    CHECK   fechamento_energia : abs(closure) <= closure_tol
    COMPARE passos = successive_diff(of=[R, T, chi95], along=ppw, group_by=[geometry])
    ANALYZE conv   = convergence(of=[R, T, chi95], along=ppw, group_by=[geometry], safety_factor=3, working_ppw=20)
    OUTPUT  tables=[cases, passos, conv], scalars=[conv]
}
"""
