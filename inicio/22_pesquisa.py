# versao: 11
# inicio/22_pesquisa.py — experimentos de pesquisa
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 5b · SCRIPTS PRONTOS (escritos/testados fora do loop dos modelos gratuitos)
# ═══════════════════════════════════════════════════════════════
SCRIPTS_DIR = BASE / "scripts_prontos"
SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# SCRIPTS_EMBUTIDOS removido: a fonte única dos scripts prontos é scripts_prontos/ no Drive

def listar_scripts_prontos():
    return sorted(p.stem for p in SCRIPTS_DIR.glob("*.py"))

def carregar_script_pronto(nome):
    texto = (SCRIPTS_DIR / f"{nome}.py").read_text(encoding="utf-8")
    return texto, hashlib.sha256(texto.encode()).hexdigest()

print("Scripts prontos:", listar_scripts_prontos())
