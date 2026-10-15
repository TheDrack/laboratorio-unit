de: ia-externa
para: pesquisador
tipo: proposta
prioridade: normal
acao_permitida: propor
data: 2026-10-10 19:47

# Testes pendentes (Apêndice B, Documento de Estado Atual v0.8) e pendências da CALIBRACAO_T2_leve

Nenhum LIMIT foi escolhido: todos estão `pending` (decisão do pesquisador). PASS não é física correta.

## O que já está em experimentos/ (rodar nesta ordem, um por vez)

| Ordem | Arquivo | Responde | Custo |
|---|---|---|---|
| 1 | T2_pendencia_fluxo.unl | Pendências 2 e 3 da calibração: R/T por Poynting vs ordem especular; A_volume vs 1-R-T | igual ao T2_leve (9 pontos) |
| 2 | T6_sumidouro_z.unl | T6 parcial: Tmax, Tmax/P_abs e razão entre geometrias vs distância ao sumidouro em z | 20 pontos, PPW 20; buffer 600 nm é o mais pesado |
| 3 | T2_ppw40.unl | Pendência 4: quarto nível de PPW | 12 pontos; PPW 40 pode exigir backend iterativo; rodar /validar antes |

Comandos: `/validar` e depois `/rodar` (ou `/experimento nome`). Se o /validar acusar que `successive_diff` não aceita eixo físico (buffer_nm) no T6_sumidouro_z, me envie a mensagem exata.

## O que depende de primitiva que não existe no registro (não inventei)

Estado por teste do Apêndice B:

| Teste | Situação |
|---|---|
| T1 (escala de graus) | Manual: avaliação do pesquisador, não é simulação |
| T2 (E_crit e desfecho primário) | Feito (CALIBRACAO_T2_leve.md); pendências 2, 3 e 4 acima; pendência 1 abaixo |
| T3, T4, T5, T6 lateral/substrato, T7, T8, T9 | Faltam primitivas, blocos abaixo |

```falta
Pendência 1 da calibração (checagem independente de R e T).
Falta: geometria homogênea (lâmina) selecionável em CASE e um comparador/medida contra a solução analítica de Fabry-Pérot (hoje só existe em lib/validation/validate_fdfd3d.py, fora do UNIT-L). Sem isso R_power e R_specular são duas extrações do mesmo solver, não uma checagem independente.
```

```falta
T6 (parte lateral e substrato).
Falta: (a) parâmetro de tamanho lateral do domínio térmico (réplicas laterais ou padding), pois o hotspot estava a 3 células de uma face lateral e buffer_nm só move as faces em z; (b) condição de contorno térmica alternativa (substrato como sumidouro em vez de theta=0 nas seis faces); (c) comparador de razão de uma medida entre duas geometrias (ex.: Tmax de RANDOM_1003 sobre RANDOM_1018) por nível de um eixo.
```

```falta
T7 (A_s: controle ou descritor).
Falta: medida de área superficial específica A_s e geometrias com A_s diferente e f igual (hoje CASE só aceita as 22 geometrias do catálogo).
```

```falta
T8 (cobertura do espaço de descritores DG).
Falta: medidas de descritores geométricos calculadas das máscaras (S(q) em vetores relevantes, número médio de contatos Z, A_s, distância do material ao sumidouro, números de Betti) e um analisador de cobertura/variância por descritor sobre as 22 geometrias. Não precisa de solver.
```

```falta
T9 (par isoespectral).
Falta: um par de geometrias isoespectrais registrado em CASE e uma medida dos autovalores do Laplaciano {lambda_n}. Sem isso o teste falsificável de {lambda_n} como descritor único não pode ser escrito.
```

```falta
T3 (limiar de estabilidade) e T4 (tamanho amostral).
Falta: (T3) gerador de resposta sintética a partir de d_G* conhecido (2 descritores + ruído) e analisador de seleção de descritores com validação cruzada aninhada; (T4) analisador de curva de aprendizado (erro de teste vs n) e geração de mais de 22 geometrias para n = 50, 100, 200.
```

```falta
T5 (referência de H0).
Falta: medidas de referência Maxwell-Garnett, Bruggeman e QCA/S(q) para as geometrias do catálogo e um comparador contra o FDFD fora da amostra. geometry.py tem Maxwell-Garnett em Python, mas não está registrado como medida.
```
