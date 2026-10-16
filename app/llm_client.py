"""Client LLM compatible OpenAI.

Le même code parle à l'API Mistral, à Hugging Face, à vLLM ou à Ollama :
seules LLM_BASE_URL, LLM_API_KEY et LLM_MODEL changent (dans .env).
"""
from functools import lru_cache

from openai import NOT_GIVEN, APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app import config


TEMPERATURE = 0.1  # faible : on veut des réponses factuelles et stables
MAX_TOKENS = 800


class ErreurLLM(Exception):
    """Erreur lisible, remontée à l'API au lieu d'une trace Python."""


# Codes HTTP fréquents -> explication en français
MESSAGES_HTTP = {
    400: "requête refusée (modèle inconnu chez ce fournisseur ? vérifier LLM_MODEL)",
    401: "clé API invalide (vérifier LLM_API_KEY)",
    402: "plus de crédits sur le compte facturé",
    403: "droits insuffisants pour cette clé ou ce modèle",
    404: "modèle ou URL introuvable (vérifier LLM_MODEL et LLM_BASE_URL)",
    429: "trop de requêtes : quota du fournisseur atteint, réessayer plus tard",
}


@lru_cache(maxsize=1)
def client() -> OpenAI:
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        timeout=60,       # secondes : au-delà, on abandonne
        max_retries=2,    # nouvelles tentatives automatiques (erreurs réseau, 429, 5xx)
        default_headers={"X-HF-Bill-To": config.HF_BILL_TO} if config.HF_BILL_TO else None,
    )


def generer(messages: list[dict]) -> str:
    if not config.LLM_API_KEY or not config.LLM_MODEL:
        raise ErreurLLM("configuration incomplète : renseigner LLM_MODEL et LLM_API_KEY dans .env")
    try:
        reponse = client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            reasoning_effort=config.LLM_REASONING_EFFORT or NOT_GIVEN,  # Mistral refuserait ce paramètre
        )
    except APIStatusError as e:
        explication = MESSAGES_HTTP.get(e.status_code, "erreur du fournisseur")
        raise ErreurLLM(f"LLM indisponible ({e.status_code}) : {explication}") from e
    except (APIConnectionError, APITimeoutError) as e:
        raise ErreurLLM("LLM injoignable (réseau ou délai dépassé)") from e
    texte = reponse.choices[0].message.content
    if not texte:  # None possible (filtre de contenu, coupure) : 503 lisible plutôt qu'un 500
        raise ErreurLLM("le LLM a renvoyé une réponse vide")
    return texte.strip()
