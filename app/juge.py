"""LLM juge : un second modèle, d'une autre famille, relit chaque réponse d'evaluate.py.

Il reçoit exactement ce que l'assistant a reçu (consignes, date du jour, fiches, question) et sa
réponse, et rend trois verdicts oui / non, plus faciles à fiabiliser qu'une note de 1 à 5 :
- fidèle     : chaque fait cité figure dans les fiches ET est attribué à la bonne étape. C'est ce que
               app/confiance.py ne voit pas (date réelle mise sur la mauvaise étape, mauvais comptage) ;
- pertinente : la réponse répond à la question ; « Je ne sais pas » ne l'est que si les fiches ne
               permettent pas de répondre ;
- neutre     : ni avis, ni jugement, ni recommandation, ni présupposé de la question repris.
Le juge peut se tromper : ses verdicts sont suivis à part et ne changent pas le score d'evaluate.py.

Modèle : config.LLM_JUGE_MODEL, chez le même fournisseur que le LLM de l'assistant.
"""
import json
import re

from app import config
from app.llm_client import generer

CRITERES = ("fidele", "pertinente", "neutre")

CONSIGNES_JUGE = """Tu es un évaluateur exigeant. Un assistant a reçu des consignes, des fiches de dossiers législatifs et une question ; tu dois juger sa réponse.

Pour chaque critère, réponds true ou false :
- "fidele" : chaque fait cité (date, statut, étape, vote, nombre, lien) figure dans les fiches ET est attribué au bon dossier et à la bonne étape. Un fait absent des fiches, une date mise sur la mauvaise étape ou un comptage faux = false. Une réponse « Je ne sais pas » est fidèle.
- "pertinente" : la réponse répond à la question posée, en tenant compte de la date du jour. « Je ne sais pas » n'est pertinent que si les fiches ne permettent pas de répondre.
- "neutre" : aucun avis, jugement de valeur, recommandation ou parti pris, et aucun présupposé chargé de la question n'est repris à son compte.

Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"fidele": true|false, "pertinente": true|false, "neutre": true|false, "justification": "une phrase ; cite l'erreur précise s'il y en a une"}"""


def construire_messages_juge(messages_assistant: list[dict], reponse: str) -> list[dict]:
    recu = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages_assistant)
    contenu = (f"<recu_par_l_assistant>\n{recu}\n</recu_par_l_assistant>\n\n"
               f"<reponse_de_l_assistant>\n{reponse}\n</reponse_de_l_assistant>")
    return [{"role": "system", "content": CONSIGNES_JUGE}, {"role": "user", "content": contenu}]


def lire_verdict(texte: str) -> dict | None:
    """Objet JSON du verdict, même entouré de ```json ... ``` ; None s'il est illisible ou incomplet."""
    trouve = re.search(r"\{.*\}", texte, re.DOTALL)
    try:
        verdict = json.loads(trouve.group(0)) if trouve else None
    except json.JSONDecodeError:
        return None
    if not isinstance(verdict, dict) or not all(isinstance(verdict.get(c), bool) for c in CRITERES):
        return None
    return {**{c: verdict[c] for c in CRITERES}, "justification": str(verdict.get("justification", ""))}


def juger(messages_assistant: list[dict], reponse: str) -> dict:
    """Verdict du juge, avec ses tokens. Peut lever ErreurLLM (quota, réseau)."""
    texte, tokens = generer(construire_messages_juge(messages_assistant, reponse), modele=config.LLM_JUGE_MODEL)
    verdict = lire_verdict(texte)
    if verdict is None:
        return {"erreur": f"verdict illisible : {texte[:200]}", "tokens": tokens}
    return {**verdict, "tokens": tokens}
