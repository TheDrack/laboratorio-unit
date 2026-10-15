# PROTOCOLO DE COMUNICAÇÃO — laboratório UNIT-001

Canal assíncrono entre o pesquisador, as IAs externas e os agentes do laboratório. Tudo fica registrado em arquivo.

## Pastas
- entrada/: mensagens PARA o agente (tarefas, perguntas, revisões).
- saida/: respostas DO agente.
- propostas/: propostas de experimento em UNIT-L. Nunca executadas sem /rodar do pesquisador.
- log.md: histórico legível de tudo (o pesquisador acompanha por aqui).
- status.json: sinal de vida do agente (última leitura, estado).

## Cabeçalho obrigatório de cada mensagem (primeiras linhas do arquivo)
de: <autor: pesquisador | coordenador | ia-externa | agente-lab>
para: <destinatário>
tipo: <tarefa | pergunta | revisao | resposta | proposta | aviso>
prioridade: <baixa | normal | alta>
acao_permitida: <ler | responder | propor | aplicar_correcao>
modo: <simular | aplicar>            (obrigatório só quando acao_permitida = aplicar_correcao)
data: <AAAA-MM-DD HH:MM>

## Nome do arquivo
AAAA-MM-DD_HHMM_<tipo>_<assunto>.md (ex.: 2026-10-10_1600_tarefa_revisar_T2.md)

## Permissões do agente
- Pode ler todo o laboratório.
- Pode escrever somente em saida/, propostas/, log.md e status.json.
- Pode propor experimentos (propostas/). NÃO executa experimentos: a execução exige /rodar do pesquisador ou de um coordenador.
- Pode aplicar correção (acao_permitida: aplicar_correcao) somente por meio da skill_correcao_rapida, com ordem do pesquisador ou de um coordenador, e somente depois de uma simulação (modo: simular) cujo diff foi conferido. Nenhuma edição manual de arquivo.
- Não define tolerâncias nem LIMIT: são decisões do pesquisador.
- Não altera dados, runs ou inicio/ sem tarefa explícita aprovada.

## Regras
1. Toda ação do agente gera uma linha no log.md (data, tipo, arquivo, resultado).
2. Resposta sempre em saida/ com o mesmo assunto da entrada, referenciando o arquivo original.
3. Quando não souber, o agente escreve pergunta em saida/ em vez de supor.
4. Afirmações científicas citam a checagem usada (PADRAO_ESTUDO.md). PASS não é física correta.
5. Constantes e parâmetros de estudo são declarados no início do processo (lib/geometry/unit001_constantes.py). Nenhum agente define constante dentro de função ou durante a execução.
