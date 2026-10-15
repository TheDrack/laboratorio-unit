# versao: 11
# inicio/10_llm_cliente.py — cliente de LLM (OpenRouter/Gemini/Groq, cache, fallback)
# Gerado a partir do código do laboratório. Pode editar: o runner executa este arquivo como uma célula.

# ═══════════════════════════════════════════════════════════════
# CÉLULA 2 · CLIENTE DE LLM
# OpenRouter / Gemini / Groq
# Fallback automático + retries
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# 1. EXCEÇÃO ESPECÍFICA
# ═══════════════════════════════════════════════════════════════

class ErroLLM(Exception):
    """
    Erro operacional de comunicação com um provedor/modelo LLM.
    """
    pass


# ═══════════════════════════════════════════════════════════════
# 2. ENDPOINTS
# ═══════════════════════════════════════════════════════════════

ENDPOINTS = {

    "openrouter":
        "https://openrouter.ai/api/v1/chat/completions",

    "groq":
        "https://api.groq.com/openai/v1/chat/completions",

    "gemini":
        "https://generativelanguage.googleapis.com/v1beta/models",
}


# ═══════════════════════════════════════════════════════════════
# 3. CONFIGURAÇÃO DE REDE
# ═══════════════════════════════════════════════════════════════

LLM_TIMEOUT = 240

LLM_TENTATIVAS = 2

LLM_ESPERA_INICIAL = 5

LLM_BACKOFF = 2

HTTP_RETRY_STATUS = {
    408,
    409,
    425,
    429,
    500,
    502,
    503,
    504,
}


# ═══════════════════════════════════════════════════════════════
# 4. POST GENÉRICO
# ═══════════════════════════════════════════════════════════════

def _post(
    url,
    headers,
    payload,
    tentativas=LLM_TENTATIVAS,
    timeout=LLM_TIMEOUT,
):
    """
    POST com retry exponencial para erros transitórios.

    Retorna:
        dict JSON

    Levanta:
        ErroLLM
    """

    espera = LLM_ESPERA_INICIAL
    ultimo = ""

    for tentativa in range(1, tentativas + 1):

        try:

            resposta = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

        except requests.RequestException as erro:

            ultimo = (
                f"{type(erro).__name__}: {erro}"
            )

            if tentativa < tentativas:

                time.sleep(espera)
                espera *= LLM_BACKOFF
                continue

            break

        # ------------------------------------------------------
        # HTTP transitório
        # ------------------------------------------------------

        if resposta.status_code in HTTP_RETRY_STATUS:

            ultimo = (
                f"HTTP {resposta.status_code}: "
                f"{resposta.text[:300]}"
            )

            if tentativa < tentativas:

                time.sleep(espera)
                espera *= LLM_BACKOFF
                continue

            break

        # ------------------------------------------------------
        # HTTP permanente
        # ------------------------------------------------------

        if resposta.status_code >= 400:

            raise ErroLLM(
                f"HTTP {resposta.status_code}: "
                f"{resposta.text[:1000]}"
            )

        # ------------------------------------------------------
        # JSON
        # ------------------------------------------------------

        try:

            return resposta.json()

        except ValueError as erro:

            raise ErroLLM(
                "Resposta HTTP válida, mas não é JSON. "
                f"HTTP {resposta.status_code}: "
                f"{resposta.text[:500]}"
            ) from erro

    raise ErroLLM(
        f"Sem resposta após {tentativas} tentativas. "
        f"Último erro: {ultimo}"
    )


# ═══════════════════════════════════════════════════════════════
# 5. LIMPEZA DE RESPOSTA
# ═══════════════════════════════════════════════════════════════

def _limpar_resposta(texto):
    """
    Remove blocos <think>...</think> quando presentes.

    Não modifica o conteúdo normal da resposta.
    """

    if texto is None:
        return ""

    texto = str(texto)

    texto = re.sub(
        r"<think>.*?</think>",
        "",
        texto,
        flags=re.S | re.I,
    )

    return texto.strip()


# ═══════════════════════════════════════════════════════════════
# 6. OPENAI-COMPATÍVEL
# OpenRouter / Groq
# ═══════════════════════════════════════════════════════════════

def _chat_openai(
    prov,
    modelo,
    system,
    user,
    max_tokens,
    temperature,
):
    """
    Interface comum para OpenRouter e Groq.
    """

    if prov not in (
        "openrouter",
        "groq",
    ):
        raise ErroLLM(
            f"Provedor OpenAI-compatible inválido: {prov}"
        )

    chave = KEYS.get(prov)

    if not chave:
        raise ErroLLM(
            f"Chave não configurada: {prov}"
        )

    payload = {
        "model": modelo,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": user,
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }

    # OpenRouter aceita estes headers e eles ajudam
    # na identificação da aplicação.
    if prov == "openrouter":

        headers.update({
            "HTTP-Referer": (
                "https://colab.research.google.com/"
            ),
            "X-Title": "UNIT-001 Multi-Agent Lab",
        })

    dados = _post(
        ENDPOINTS[prov],
        headers,
        payload,
    )

    try:

        escolhas = dados["choices"]

        if not escolhas:
            raise KeyError("choices vazio")

        mensagem = escolhas[0]["message"]

        texto = mensagem.get(
            "content",
            "",
        )

    except (
        KeyError,
        IndexError,
        TypeError,
    ) as erro:

        raise ErroLLM(
            "Resposta inesperada de "
            f"{prov}/{modelo}: "
            f"{str(dados)[:1000]}"
        ) from erro

    texto = _limpar_resposta(texto)

    if not texto:

        raise ErroLLM(
            f"{prov}/{modelo}: resposta vazia"
        )

    return texto


# ═══════════════════════════════════════════════════════════════
# 7. GEMINI
# ═══════════════════════════════════════════════════════════════

def _chat_gemini(
    modelo,
    system,
    user,
    max_tokens,
    temperature,
):
    """
    Interface Gemini generateContent.
    """

    chave = KEYS.get("gemini")

    if not chave:
        raise ErroLLM(
            "Chave Gemini não configurada."
        )

    url = (
        f"{ENDPOINTS['gemini']}/"
        f"{modelo}:generateContent"
    )

    headers = {
        "x-goog-api-key": chave,
        "Content-Type": "application/json",
    }

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": system,
                }
            ]
        },

        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": user,
                    }
                ],
            }
        ],

        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    dados = _post(
        url,
        headers,
        payload,
    )

    # ----------------------------------------------------------
    # Extrair candidates
    # ----------------------------------------------------------

    try:

        candidates = dados["candidates"]

        if not candidates:
            raise KeyError(
                "candidates vazio"
            )

        candidate = candidates[0]

        content = candidate.get(
            "content",
            {},
        )

        parts = content.get(
            "parts",
            [],
        )

    except (
        KeyError,
        IndexError,
        TypeError,
    ) as erro:

        raise ErroLLM(
            "Resposta inesperada do Gemini "
            f"{modelo}: "
            f"{str(dados)[:1000]}"
        ) from erro

    # ----------------------------------------------------------
    # Concatenar partes de texto
    # ----------------------------------------------------------

    textos = []

    for parte in parts:

        if not isinstance(
            parte,
            dict,
        ):
            continue

        # Ignora partes marcadas como thought.
        if parte.get(
            "thought",
            False,
        ):
            continue

        texto = parte.get(
            "text",
            "",
        )

        if texto:
            textos.append(
                texto
            )

    resposta = _limpar_resposta(
        "".join(textos)
    )

    if not resposta:

        raise ErroLLM(
            f"gemini/{modelo}: resposta vazia"
        )

    return resposta


# ═══════════════════════════════════════════════════════════════
# 8. DESCOBERTA AUTOMÁTICA DE MODELOS  (substitui a lista fixa PAPEIS)
#
# Os provedores descontinuam modelos o tempo todo. Em vez de nomes fixos:
#   1. consulta o catálogo REAL de cada provedor com chave (cache de 12 h);
#   2. ranqueia por papel (família, versão, contexto) e descarta embeddings/áudio/imagem etc.;
#   3. se uma chamada voltar "descontinuado / não encontrado / sem endpoints", marca o modelo
#      como MORTO (persistido), e passa ao próximo candidato — e, esgotados os candidatos,
#      redescobre o catálogo uma vez antes de desistir.
# Fixar manualmente (opcional):  PAPEIS_FIXOS["codificador"] = [("gemini", "nome-exato")]
# ═══════════════════════════════════════════════════════════════

import json as _json

PAPEIS_FIXOS = {}

CACHE_MODELOS = (MAP_DIR / "modelos_llm.json") if "MAP_DIR" in globals() else Path("modelos_llm.json")
CACHE_TTL_S = 12 * 3600
TOP_POR_PROVEDOR = 4

ORDEM_PROVEDORES = {
    "codificador": ["gemini", "openrouter", "groq"],
    "revisor": ["gemini", "openrouter", "groq"],
    "relator": ["groq", "gemini", "openrouter"],
}

_EXCLUIR = re.compile(
    r"embed|whisper|tts|speech|audio|image|imagen|veo\b|vision|-vl\b|guard|moderat|safety|rerank|transcri|playai|"
    r"\blive\b|robotics|aqa|learnlm|distil|-ocr|computer-use|gemma-3n|\bnano\b|banana", re.I)

# (regex, pontos) — primeira que casar vale. Mais pontos = preferido.
_FAMILIAS = {
    "codificador": [(r"coder", 11), (r"gemini-[\d\.]+-flash(?!-lite)", 10), (r"gemini-[\d\.]+-pro", 9.5), (r"deepseek", 9),
                    (r"gpt-oss-120b", 9), (r"qwen3|qwen-?3", 8.5), (r"llama-?3\.3-70b|llama-?4", 8), (r"kimi|glm", 7.5),
                    (r"mistral-(large|medium)|devstral", 7), (r"llama", 5), (r"gemma", 4), (r"gemini", 6)],
    "revisor": [(r"gemini-[\d\.]+-pro", 10), (r"gemini-[\d\.]+-flash(?!-lite)", 9.5), (r"deepseek", 9.5), (r"gpt-oss-120b", 9),
                (r"qwen3|qwen-?3", 8.5), (r"llama-?3\.3-70b|llama-?4", 8), (r"kimi|glm", 7.5), (r"mistral", 6), (r"llama", 5), (r"gemini", 6)],
    "relator": [(r"gemini-[\d\.]+-flash(?!-lite)", 10), (r"llama-?3\.3-70b|llama-?4", 9.5), (r"gpt-oss", 9), (r"qwen3|qwen-?3", 8.5),
                (r"deepseek", 8), (r"gemini", 7), (r"llama", 6), (r"mistral", 5), (r"gemma", 4)],
}


def _agora():
    return time.time()


def _ler_cache():
    try:
        return _json.loads(CACHE_MODELOS.read_text(encoding="utf-8"))
    except Exception:
        return {"ts": 0, "provedores": {}, "mortos": {}, "erros": {}}


def _gravar_cache(c):
    try:
        CACHE_MODELOS.parent.mkdir(parents=True, exist_ok=True)
        CACHE_MODELOS.write_text(_json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _get(url, headers, timeout=60):
    r = requests.get(url, headers=headers, timeout=timeout)
    if r.status_code >= 400:
        raise ErroLLM(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _catalogo(prov):
    """Lista [{'id','ctx','gratis'}] realmente disponível agora para a chave do provedor."""
    k = KEYS.get(prov)
    out = []
    if prov == "openrouter":
        d = _get("https://openrouter.ai/api/v1/models", {"Authorization": f"Bearer {k}"})
        for m in d.get("data", []):
            p = m.get("pricing") or {}
            gratis = str(m.get("id", "")).endswith(":free") or (str(p.get("prompt", "1")) in ("0", "0.0") and str(p.get("completion", "1")) in ("0", "0.0"))
            if m.get("id") and gratis:
                out.append({"id": m["id"], "ctx": m.get("context_length") or 0})
    elif prov == "gemini":
        d = _get(ENDPOINTS["gemini"] + "?pageSize=200", {"x-goog-api-key": k})
        for m in d.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                out.append({"id": m.get("name", "").replace("models/", ""), "ctx": m.get("inputTokenLimit") or 0})
    elif prov == "groq":
        d = _get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {k}"})
        for m in d.get("data", []):
            if m.get("id") and m.get("active", True):
                out.append({"id": m["id"], "ctx": m.get("context_window") or 0})
    return out


def descobrir_modelos(forcar=False):
    """Atualiza (se preciso) o cache de catálogos. Retorna o cache."""
    c = _ler_cache()
    vivo = (_agora() - c.get("ts", 0)) < CACHE_TTL_S
    provs_ok = all(p in c.get("provedores", {}) for p, k in KEYS.items() if k and p in ENDPOINTS)
    if vivo and provs_ok and not forcar:
        return c
    c["provedores"], c["erros"] = {}, {}
    for prov, k in KEYS.items():
        if not k or prov not in ENDPOINTS:
            continue
        try:
            c["provedores"][prov] = _catalogo(prov)
        except Exception as e:
            c["erros"][prov] = f"{type(e).__name__}: {e}"[:300]
    c["ts"] = _agora()
    _gravar_cache(c)
    return c


def _pontuar(papel, mid, ctx):
    m = mid.lower()
    base = 0.0
    for rx, pts in _FAMILIAS[papel]:
        if re.search(rx, m):
            base = pts
            break
    if base == 0.0:
        return -1.0
    v = re.search(r"(?:gemini|llama|qwen|gpt-oss|deepseek[-\w]*?|kimi-k|glm|mistral[-\w]*?)[-v]*(\d+(?:\.\d+)?)", m)
    base += min(float(v.group(1)), 10) * 0.25 if v else 0
    base += min(ctx or 0, 1_000_000) / 1_000_000 * 1.5
    if re.search(r"preview|\bexp\b|experimental", m):
        base -= 1.5
    if re.search(r"lite|mini|\b[0-9]b\b|instant|small|flash-8b", m) and not re.search(r"\d{2,}b", m):
        base -= 3
    return base


def candidatos(papel):
    """Lista ordenada [(prov, modelo)] para o papel, já sem modelos mortos."""
    if papel not in _FAMILIAS:
        raise ErroLLM(f"Papel LLM desconhecido: {papel!r}. Disponíveis: {list(_FAMILIAS)}")
    c = descobrir_modelos()
    mortos = c.get("mortos", {})
    fixos = [(p, m) for p, m in PAPEIS_FIXOS.get(papel, []) if KEYS.get(p) and f"{p}/{m}" not in mortos]
    por_prov = {}
    for prov, lista in c["provedores"].items():
        pont = []
        for it in lista:
            if f"{prov}/{it['id']}" in mortos or _EXCLUIR.search(it["id"]):
                continue
            s = _pontuar(papel, it["id"], it.get("ctx"))
            if s > 0:
                pont.append((s, it["id"]))
        pont.sort(reverse=True)
        por_prov[prov] = [(prov, mid) for _, mid in pont[:TOP_POR_PROVEDOR]]
    ordem = [p for p in ORDEM_PROVEDORES[papel] if p in por_prov]
    out, i = list(fixos), 0
    while any(por_prov[p][i:] for p in ordem):
        for p in ordem:
            if i < len(por_prov[p]):
                out.append(por_prov[p][i])
        i += 1
    return list(dict.fromkeys(out))


_MORTO_RX = re.compile(r"no longer available|deprecat|decommission|discontinu|not found|does not exist|no endpoints|model_not_found|"
                       r"not supported for|unsupported model|HTTP 404|HTTP 410|has been (removed|retired)|sunset", re.I)


def _marcar_morto(prov, modelo, motivo):
    c = _ler_cache()
    c.setdefault("mortos", {})[f"{prov}/{modelo}"] = {"motivo": motivo[:200], "quando": time.strftime("%Y-%m-%d %H:%M")}
    _gravar_cache(c)


def _chamar_um(prov, modelo, system, user, max_tokens, temperature):
    if prov == "gemini":
        return _chat_gemini(modelo=modelo, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
    return _chat_openai(prov=prov, modelo=modelo, system=system, user=user, max_tokens=max_tokens, temperature=temperature)


def chamar(papel, system, user, max_tokens=8000, temperature=0.2):
    """(texto, "provedor/modelo"). Usa catálogo real, pula/marca modelos descontinuados, redescobre se esgotar."""
    falhas, tentados = [], set()
    for rodada in (1, 2):
        try:
            cands = candidatos(papel)
        except ErroLLM:
            raise
        novos = [x for x in cands if x not in tentados]
        if not novos and rodada == 1:
            novos = []
        for prov, modelo in novos:
            tentados.add((prov, modelo))
            try:
                texto = _chamar_um(prov, modelo, system, user, max_tokens, temperature)
                if texto:
                    return texto, f"{prov}/{modelo}"
                falhas.append(f"{prov}/{modelo}: resposta vazia")
            except ErroLLM as e:
                falhas.append(f"{prov}/{modelo}: {str(e)[:220]}")
                if _MORTO_RX.search(str(e)):
                    _marcar_morto(prov, modelo, str(e))
            except Exception as e:
                falhas.append(f"{prov}/{modelo}: {type(e).__name__}: {str(e)[:200]}")
        if rodada == 1:
            descobrir_modelos(forcar=True)   # esgotou: o catálogo pode ter mudado
    c = _ler_cache()
    if not any(KEYS.values()):
        raise ErroLLM("Nenhuma chave de LLM configurada (OPENROUTER_API_KEY / GEMINI_API_KEY / GROQ_API_KEY).")
    erros = "; ".join(f"{p}: {e}" for p, e in c.get("erros", {}).items())
    raise ErroLLM(f"Todos os candidatos do papel '{papel}' falharam.\n  - " + "\n  - ".join(falhas or ["nenhum candidato descoberto"])
                  + (f"\n  Erros ao listar catálogo: {erros}" if erros else ""))


def diagnostico_modelos(testar=False):
    c = descobrir_modelos(forcar=testar)
    linhas = []
    for prov in KEYS:
        if not KEYS[prov]:
            linhas.append(f"{prov}: sem chave")
            continue
        n = len(c["provedores"].get(prov, []))
        linhas.append(f"{prov}: {n} modelos no catálogo" + (f"  ⚠ {c['erros'][prov]}" if prov in c.get("erros", {}) else ""))
    for papel in _FAMILIAS:
        try:
            linhas.append(f"  {papel:<11} → " + ", ".join(f"{p}/{m}" for p, m in candidatos(papel)[:5]))
        except Exception as e:
            linhas.append(f"  {papel}: {e}")
    if c.get("mortos"):
        linhas.append("descontinuados detectados: " + ", ".join(c["mortos"]))
    if testar:
        for papel in _FAMILIAS:
            try:
                t, m = chamar(papel, "Responda apenas: OK", "ping", max_tokens=20)
                linhas.append(f"  teste {papel}: {m} → {t[:30]!r}")
            except ErroLLM as e:
                linhas.append(f"  teste {papel}: FALHOU — {str(e)[:300]}")
    return "\n".join(linhas)


def listar_modelos(max_itens=40):
    print(diagnostico_modelos())


# ═══════════════════════════════════════════════════════════════
# 10. TELEGRAM
# ═══════════════════════════════════════════════════════════════

def notificar(msg):
    """
    Envia uma notificação Telegram.

    Falha de Telegram nunca interrompe o laboratório.
    """

    if not (
        TELEGRAM_TOKEN
        and TELEGRAM_CHAT_ID
    ):
        return False

    try:

        resposta = requests.post(
            (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/sendMessage"
            ),
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": str(msg)[:3500],
            },
            timeout=20,
        )

        resposta.raise_for_status()

        return True

    except requests.RequestException:

        return False


# ═══════════════════════════════════════════════════════════════
# 11. DIAGNÓSTICO DA CÉLULA
# ═══════════════════════════════════════════════════════════════

print("\nCliente LLM V3 (descoberta automática de modelos) carregado.")
print("Provedores com chave:", [p for p, k in KEYS.items() if k] or "NENHUM")
print("Papéis:", ", ".join(_FAMILIAS))
print("Telegram:", "ATIVO" if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID else "DESLIGADO")
