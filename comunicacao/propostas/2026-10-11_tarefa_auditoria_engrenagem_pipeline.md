de: ia-externa
para: agentes do laboratório (Codificador, Executor, Relator)
tipo: tarefa
acao_permitida: executar
data: 2026-10-11
regra_de_projeto: cada grandeza tem uma única definição, em um único módulo; mudança só por função nomeada com operação, unidade e entrada declaradas (ver preferências do projeto)

# Tarefa: auditoria de engrenagem do pipeline e correção rastreável

A IA externa não roda cálculos e não decide física. O pesquisador autorizou a regeneração completa dos dados quando necessária para corrigir, mas a escolha da convenção correta é dele.

## Regras de execução

- Preservar tudo o que já foi gerado. Dados novos vão para uma pasta versionada (ex.: `resultados_v2_<data>/`), nunca sobrescrevendo a versão anterior. Assim o impacto de cada correção pode ser comparado.
- Cada resultado novo registra: versão do código (hash), convenção de posição dos pilares, fonte da máscara, data e a lista de achados desta auditoria que ele resolve.
- Nenhum LIMIT é escolhido. Tolerâncias ficam `pending`.

## Achados a verificar (um por item, com evidência)

A1 — Posição dos pilares em z. `extrator.py` usa z = 4 a 12 (`add_pillar`, z0 = 4). `geometry_generator.py` usa z = 0 a 8. Tarefa: rastrear qual das duas máscaras chega ao `build_domain_3d` e ao solver, e confirmar que a outra não é usada em nenhum cálculo de resultado. Emitir relatório com o caminho completo de dados (de qual arquivo para qual função). NÃO decidir a convenção correta: apenas apresentar as duas opções com consequências para o solver, para o `z_struct_start` e para a comparação com s/S(q).

A2 — Constante inexistente. `thermal_qk_investigation.py` importa `K_THERMAL_REFERENCE` de `thermal_coupling.py`, que não define esse nome. Tarefa: confirmar com `grep` e reportar. Não criar a constante sem decisão de valor (os valores de κ já estão em `extrator.py`: 0,026 e 150 W/(m·K)).

A3 — Assinatura inconsistente. `thermal_qk_investigation.py` chama `solve_steady_state_temperature(..., structural_mask=...)`, parâmetro que a função não aceita. Tarefa: confirmar e reportar o ponto exato da chamada.

A4 — Chaves de resultado. `thermal_qk_investigation.py` lê `T_max_global` e `T_max_struct`; `thermal_coupling.py` devolve `temperature_max_K` e chaves relacionadas. Tarefa: listar cada chave usada em qualquer script e a chave real devolvida. Não renomear sem registro.

A5 — Duas definições térmicas. `energy_state.compute_thermal_channels` monta um Laplaciano próprio (`build_D2` com `periodic=False, npml=0`), com contorno diferente do de `thermal_coupling.py` (T = 0 nas seis faces, média harmônica de κ). Tarefa: comparar as duas soluções para a mesma q e κ de um caso pequeno e reportar a diferença. Só isso. Qual está correta é decisão do pesquisador.

## Verificação mínima por achado

Cada achado é verificado por execução, não só por leitura. O Executor roda o menor caso possível (uma geometria, uma frequência, PPW baixo) para confirmar o erro ou a ausência dele. Nenhuma execução conta como validação física.

## Saídas

- `auditoria_engrenagem.md`: para cada A1 a A5, status (confirmado / não confirmado / não executado), evidência (linha de código, saída de comando) e impacto nos dados existentes.
- `impacto_dados_existentes.csv`: quais conjuntos de resultados anteriores são afetados por cada achado confirmado.
- Lista de correções propostas, sem aplicá-las. Cada correção indica os arquivos alterados e o hash antes e depois.

## Fora do escopo

- Aplicar correção sem aprovação do pesquisador.
- Apagar ou sobrescrever resultados anteriores.
- Interpretar física ou declarar qual versão está certa.

## Critério de conclusão

A tarefa termina quando A1 a A5 tiverem status definido, com evidência, e a lista de correções estiver pronta para aprovação. A regeneração de dados só começa depois da decisão do pesquisador sobre A1 e A5.
