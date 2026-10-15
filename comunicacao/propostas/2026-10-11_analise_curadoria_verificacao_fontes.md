de: ia-externa
para: pesquisador e agentes locais
tipo: análise de curadoria
acao_permitida: propor
data: 2026-10-11
fonte_curadoria: "Curadoria científica UNIT-001, 11/10/2026 (janela 4-11/10), colada pelo pesquisador"

# Análise da curadoria de 11/10/2026: o que foi verificado e o que não foi

Nada aqui é validação física. Nenhum LIMIT foi escolhido. O solver segue FDFD escalar TE_y, que exige checagem full-vector antes de resultados finais.

## 1. Status das fontes citadas na curadoria

| Fonte | Verificação nesta sessão | Classe UNIT |
|---|---|---|
| Kim e Torquato, "Predictive Formulas for Scattering Mean Free Path...", Advanced Optical Materials (2026) | Título e resumo confirmados por busca (página do Princeton). Abstract diz: fórmulas de forte contraste, dependem da densidade espectral, validadas por FDTD para k1/s em determinado regime, e fornecem ℓ_s. Página do Wiley bloqueada (bot). DOI e Zenodo NÃO verificados. Data de 25/04/2026 NÃO verificada. | (A) para T5; desfecho é ℓ_s, não χ95/χ99 |
| Campaniello et al., PNAS (ondas de água, correlação) | NÃO verificada nesta sessão. Só a descrição da curadoria. | (B) analogia experimental; confirmar antes de citar |
| AutoSciBench, arXiv 2610.05140 (4/10/2026) | Verificado: autores, data de submissão, v1, cs.AI, resumo. Quedas de 22,4 e 25,5 pp confirmadas no resumo. Preprint, não revisado por pares. | (B) método de avaliação de agentes; não é evidência física |
| Wiedmann et al., "Agents Are Systems, Not Models", arXiv 2610.01618 (1/10/2026) | Verificado: autores, data, resumo. Confirma ~54% da variância vindo da repetição da mesma configuração, e que pedir verificação tem pouco efeito enquanto ferramenta dedicada muda o comportamento. | (B) método de avaliação de agentes |
| Vagin e Gorlach, PRL (aceito 5/10/2026) | NÃO verificada. Só a descrição da curadoria. A própria curadoria a classifica como fora do regime UNIT-001. | fora de escopo atual |

Regra: a curadoria não deve ser citada como fonte primária. Cada item acima precisa de DOI ou URL verificado antes de entrar em documento.

## 2. Dados úteis que a busca trouxe além da curadoria

- Kim e Torquato (arXiv 2312.05095, anisotrópicos): a fórmula de segunda ordem depende da densidade espectral e foi validada contra FDTD para meios hiperuniformes em camadas. Classe (A) para T5, mas ainda sem desfecho χ95.
- Kim e Torquato (Optica 10, 965, 2023; resumo de APS): meios SHU em camadas predizem transparência em intervalos de número de onda. Relevante para qualquer leitura de T5 em geometria em camadas; as geometrias atuais são pilares, não camadas.
- Torquato e Kim, PRX 11, 021002 (2021): origem do formalismo de forte contraste não local. Citada pelas fontes acima; não lida diretamente.

## 3. Pontos que a curadoria não destacou e que afetam T7

- O resumo de Kim e Torquato coloca a área superficial específica s dentro da condição de validade do modelo (k1/s). Isso dá a s um papel de variável de regime, e não só de descritor. Justificativa física para tratar s como controle de regime, com o cuidado de que a desigualdade exata não foi lida (o snippet foi truncado).
- Consequência prática: para o UNIT-001, s é quase constante nas 22 geometrias (pilares iguais, pouco contato). Logo o regime k1/s é praticamente o mesmo em todos os casos, e o T7 só ganha poder se geometrias com s variando forem geradas. Isso é o que já está em comunicacao/propostas/2026-10-10_1947_proposta_testes_pendentes.md.

## 4. Ações propostas (ainda não executadas)

1. Ler o artigo completo de Kim e Torquato (acesso institucional ou via autores) e extrair: definição de s, desigualdade de validade, forma das fórmulas de ordem 2. Registrar DOI verificado.
2. Verificar Campaniello et al. no PNAS (DOI/PubMed) e o Zenodo antes de citar.
3. Registrar T5 como: H0 candidata = fórmula de forte contraste de ℓ_s, com desfecho secundário declarado como não previsto diretamente. Comparação com χ95/χ99 fica como limitação.
4. Calcular s e S(q) para as 22 máscaras existentes (sem solver). Serve a T7 e T8 e não altera resultados anteriores.
5. Acrescentar ao relatório de cada run o nível de evidência em cinco estados: execução concluída; numericamente consistente; fisicamente validado; hipótese sustentada; não discriminada pelas referências.
6. Para a seção 4 da curadoria (agentes): registrar a configuração de cada execução do laboratório e repetir condições idênticas para estimar variabilidade. O resultado de Wiedmann et al. sugere que essa variância é grande e precisa ser medida antes de comparar configurações.

## 5. Itens que dependem de primitiva ausente (ver blocos falta já emitidos)

- ℓ_s como medida; s como medida; S(q) como medida; referência de forte contraste como comparador.
