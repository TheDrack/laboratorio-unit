de: ia-externa
para: pesquisador (aprovação)
tipo: proposta
prioridade: alta
acao_permitida: propor
data: 2026-10-12 19:55

# Proposta: remoção do extrator, eliminação de duplicatas e materiais como conjuntos

Esta proposta não aplica nenhuma alteração. Ela reúne o que foi verificado no código lido, o que ainda não foi lido e as decisões que cabem ao pesquisador.

## 1. Verificado (arquivos lidos)

### 1.1 Quem importa o extrator

Lidos: `pipeline.py`, `builtin_core.py`, `parser.py`, `modulacao_termica.py`. Nenhum deles importa `extrator.py` ou `extrator_legado.py`.

- `builtin_core.py` usa o provedor `unit001_pillars`, que importa `lib.geometry.unit001_dataset_66_cases`.
- `parser.py` importa `lib.geometry.unit001_constantes`.
- `modulacao_termica.py` importa `unit001_constantes` e `unit001_dataset_66_cases`.

Dependência real que existe: `modulacao_termica.py` lê arquivos NPZ com o padrão `RANDOM_seed_{seed}_{f}THz.npz`. O pipeline canônico grava com o mesmo padrão (`case.key`), então trocar a origem não muda o nome dos arquivos.

Dependência de caminho: `project_paths.py` define `EXTRACTOR_RESULTS_DIR` e `EXTRACTOR_CASES_DIR`, apontando para `dados/UNIT001/resultados/extrator/cases`. Isso é só um caminho de dados, mas o nome carrega o extrator.

Não lidos ainda: `12_configuracao.py`, `90_chat.py`, `experiment.py`, `aplicar_correcao.py`, `mapa.py` e `contrafactual_termico.py` (em `scripts_prontos`). A busca textual achou "extrator" nesses arquivos, mas não distingue importação de caminho ou comentário.

Comando para conferir o restante (rodar na raiz do projeto):

```
grep -rn --include=*.py -E "import extrator|from extrator|extrator_legado|geometry_random|add_pillar|build_all_geometries" .
```

### 1.2 Duplicatas de função

| Função | Cópias | Evidência |
|---|---|---|
| Geração RANDOM | `extrator.py` (`rng.integers` com rejeição) e `unit001_dataset_66_cases.py` (`rng.shuffle` sobre candidatos) | Mesma seed, geometrias diferentes. O canônico proíbe a versão do extrator. |
| Catálogo de geometrias | `unit001_dataset_66_cases.py` (v2, fonte única declarada) e `geometry_generator.py` (lógica v1, z = 0 fixo) | Mesmo algoritmo, versão antiga ainda presente |
| `gerar_catalogo_geometrico.py` | Duas cópias: pasta raiz de `UNIT-001_AGENTES` (1419 bytes) e `scripts_prontos` (1529 bytes) | Mesmo nome, conteúdo diferente |
| Extrator legado | `scripts_prontos/extrator_legado.py` (43 KB) | Terceira cópia de geometria e de rotina de extração |
| Solver térmico | `thermal_coupling.py` (usado pelo framework) e `modulacao_termica.resolver_T` (7 pontos, média harmônica, reimplementado) | Dois solvers para o mesmo problema. Relacionado ao achado A5/A7 do inventário. |
| Silício | `material_state.MATERIAL_LIBRARY` (ε = 11,7; κ = 150; ρ = 2330; c = 700), `parametros_estudo.json` (n = 3,6 + 5e-4 i; κ = 148; ρ = 2329; c = 712) e o pilar do extrator (n = 2,0 + 0,05 i; κ = 150) | Três definições para o mesmo nome |

Arquivos `.bak` no framework: `experiment.py.bak`, `pipeline.py.bak`, `aop_dsl.py.bak`, `builtin_core.py.bak`, `benchmark.py.bak`, `registry.py.bak`, `sentinela.py.bak`, `__init__.py.bak`. Contrariam D4 (sem backup) e a regra de que a versão anterior vai para a lixeira.

Divergência de documentação: o docstring de `modulacao_termica.py` diz que as constantes vêm de `lib/geometry/unit001_fisica.py`, arquivo que não aparece em nenhuma listagem do projeto. O código importa `unit001_constantes`.

### 1.3 Valores fixos em código (fora do JSON)

- `builtin_core.py`: coeficientes do estimador de memória (`1.63`, `1.3`, `22.9`, `1.9`, `48384.0`); tolerâncias e parâmetros do GMRES (`rtol=1e-8`, `restart=40`, `maxiter=200`, `drop_tol=1e-4`, `fill_factor=10`).
- `modulacao_termica.py`: 120 termos na série do cubo analítico; tolerância `5·(1/(n−1))²`; `n=33` no autoteste.

Esses valores devem ser declarados no JSON ou em um bloco de configuração de solver, com nome.

## 2. Ordem proposta de ação

Todas dependem de aprovação do pesquisador. Nenhuma foi executada.

1. **Conferir o restante dos importadores** com o `grep` acima e ler os arquivos da seção 1.1 que faltam.
2. **Remover `extrator.py` e `extrator_legado.py`** para a lixeira, depois do passo 1.
3. **Remover `geometry_generator.py`** (v1) e uma das duas cópias de `gerar_catalogo_geometrico.py`, após comparar o conteúdo com `unit001_dataset_66_cases.py`.
4. **Remover os arquivos `.bak`** do framework, para a lixeira.
5. **Renomear os caminhos `EXTRACTOR_*`** para um nome neutro (por exemplo `CASOS_DIR`). Isso muda código e caminho ao mesmo tempo, conforme a NOMENCLATURA.
6. **Regenerar os casos RANDOM** com o pipeline canônico. Os NPZ atuais de RANDOM foram gerados com a geometria do extrator. Como D4 proíbe backup, a regeneração sobrescreve os arquivos. Esta é a correção que você autorizou ao pedir regeneração para corrigir.
7. **Trocar `resolver_T` de `modulacao_termica.py` por `thermal_coupling`**. Baixa prioridade. Se o script não for mais usado, pode ir para a lixeira.
8. **Materiais como conjuntos** (ver seção 3).

Observação: `lib/solvers/` e `lib/coupling/` exigem revisão conjunta do coordenador e do pesquisador (D3). Os passos 2 a 5 não tocam esses diretórios.

## 3. Materiais como conjuntos

Proposta de estrutura no `parametros_estudo.json`, substituindo o bloco `presets_materiais`:

```json
"materiais": {
  "silicio": {
    "fonte_optica": "Green 2008, 300 K [verificar DOI e tabela antes de usar]",
    "n_k_por_frequencia_thz": {
      "280": {"n": 3.56, "k": 0.0, "nota": "[verificar: tabela só até 1040 nm]"},
      "300": {"n": 3.57, "k": 0.001},
      "320": {"n": 3.60, "k": 0.001}
    },
    "k_termica_w_mk": 148.0,
    "rho_kg_m3": 2329.0,
    "cp_j_kgk": 712.0
  },
  "ar": {
    "n": [1.0, 0.0],
    "k_termica_w_mk": 0.026
  }
}
```

Os valores de n e k para 300 e 320 THz vêm da tabela de Green (2008) a 300 K, interpolada: 300 THz ≈ 999 nm, 320 THz ≈ 937 nm. O valor de 280 THz (≈ 1071 nm) está além do limite da tabela que consultei, por isso fica marcado. Esses números não foram conferidos contra o artigo original.

Como o estudo escolheria o material: no bloco `FIX`, o nome `material = silicio` substituiria `n_inclusion`, `k_inclusion` e afins. Isso exige uma primitiva nova no UNIT-L, porque hoje `FIX` aceita apenas números. Essa mudança fica em `lib/framework/`, e a decisão é sua.

Consequências para o material já usado:

- O pilar de n = 2,0 + 0,05 i não é silício. Se o estudo modela silício, a absorção cai cerca de 50 vezes, e os resultados térmicos precisam ser reavaliados.
- Se o pilar é um dielétrico genérico, o material deve ser renomeado e a κ precisa ser justificada para ele.

## 4. Decisões necessárias

1. Aprovar a remoção dos passos 2 a 4 e a regeneração do passo 6.
2. Escolher o material do pilar: silício (com o conjunto de Green) ou dielétrico genérico (com nome próprio).
3. Aprovar o formato de conjunto de materiais e a nova primitiva `material = ...` no UNIT-L.
4. Decidir se `modulacao_termica.py` continua existindo.

## 5. Limites desta proposta

- Nenhum código foi alterado, nenhum arquivo foi movido e nenhum experimento foi executado.
- Não foram lidos: `12_configuracao.py`, `90_chat.py`, `experiment.py`, `aplicar_correcao.py`, `mapa.py` e `contrafactual_termico.py`.
- Os valores de Green (2008) não foram verificados contra a fonte original.
