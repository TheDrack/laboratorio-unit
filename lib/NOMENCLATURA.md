# NOMENCLATURA — padrão de escrita do projeto UNIT-001

Regra geral: tudo em minúsculas, sem acento, sem espaço, separado por underscore. Exceções são só as que o código depende.

## Arquivos de código (.py)
- snake_case: `fdfd3d.py`, `thermal_coupling.py`, `wave_state.py`.
- Módulo = o que ele faz, em uma ou duas palavras.
- Versões: sufixo numérico (`_v2`) só quando a versão anterior foi substituída e a nova é a referência. Não manter duas versões no laboratório: a anterior vai para a lixeira.

## Documentos gerados e de referência (.md)
- MAIÚSCULAS com underscore: `REFERENCIA_UNL.md`, `PADRAO_ESTUDO.md`, `CONTEXTO_IA.md`, `NOMENCLATURA.md`.
- Documentos de estudo copiados de fora: minúsculas (`barreira_termica_periferica.md.txt`).

## Dados, parâmetros e saídas
- Parâmetros de estudo e de validação: `parametros_estudo.json` (minúsculas, em `lib/geometry/`).
- Casos NPZ: `<GEOMETRIA>_seed_<n>_<freq>THz.npz` (padrão já usado pelo pipeline).
- Relatórios de validação: `validacao/relatorios/AAAA-MM-DD_HHMMSS_testes.json`.
- Mapas e status automáticos: minúsculas (`mapa.json`, `inicio_status.json`).

## Constantes e grandezas
- Constantes físicas fundamentais: `C_LIGHT`, `EPS0`, `MU0`, `Z0` (impedância do vácuo). São da física eletromagnética; não usar esses nomes para outras grandezas.
- Origem do eixo z dos pilares no dataset: `Z_ORIGEM`. Não usar `Z0` para isso, porque colide com a impedância.
- Parâmetros de estudo: prefixo ou sufixo que diga o papel (`N_INCLUSAO_ESTUDO`, `K_FUNDO_ESTUDO`, `PPW_FDTD`).
- Presets de validação: prefixo `LAMINA_TESTE_`, `NIVEIS_PPW_`, `TOL_`.
- Nenhuma constante é escrita dentro de função nem em arquivo de execução: todo valor de estudo vem do JSON, via `unit001_constantes.py`.

## Pastas
- Minúsculas, sem acento: `lib`, `solvers`, `core`, `coupling`, `geometry`, `validation`, `research`, `adapters`, `config`, `inicio`, `experimentos`, `scripts_prontos`, `validacao`, `docs`, `runs`.
- Exceções (não renomear; o código depende do caminho): `UNIT-001_AGENTES` (raiz), `dados/UNIT001`, `dados/UNIT001/resultados/extrator/cases`.

## Não renomear (o código importa o nome)
- `lib/framework/*.py`, `lib/framework/lang/*`, `lib/solvers/*.py`, `lib/core/*.py`, `lib/coupling/*.py`, `lib/adapters/*.py`, `lib/validation/*.py`.
- `lib/geometry/unit001_dataset_66_cases.py`, `lib/geometry/unit001_constantes.py`, `lib/geometry/parametros_estudo.json`.
- `inicio/*.py`: a ordem é dada pelo prefixo numérico (`00_`, `10_`...). Não mudar os prefixos sem revisar a sequência.
- Notebook `UNIT001_laboratorio.ipynb`: nome fixo da entrada do usuário.

## Ao criar algo novo
1. Escolher o nome pelo que o arquivo faz, não pelo número da versão.
2. Não criar cópias com sufixo (`_novo`, `_copia`, `_final`): substituir o arquivo.
3. Se um nome precisar mudar e o código importa, mudar primeiro o código e depois o nome, numa mesma atualização.
