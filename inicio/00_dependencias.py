# versao: 11
# inicio/00_dependencias.py — dependências
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'numpy', 'scipy', 'matplotlib', 'ipywidgets', 'requests'], check=False)
print('dependências verificadas')
