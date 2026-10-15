# Laboratório UNIT-001

Pipeline multiagente em Colab para a Teoria UNIT.

## Estrutura
- `lib/`: framework, solvers, núcleo, acoplamento e validação
- `inicio/`: scripts que rodam ao abrir o laboratório (em ordem pelo nome)
- `experimentos/`: experimentos em UNIT-L (.unl)
- `specs/`, `scripts_prontos/`, `validacao/`, `docs/`
- `comunicacao/`: protocolo e equipe de agentes

## Dados
Casos NPZ, execuções (`runs/`) e registros variáveis ficam fora do repositório, no Drive.

## Segredos
Chaves ficam no Colab Secrets (OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID). Nunca commitar chaves.
