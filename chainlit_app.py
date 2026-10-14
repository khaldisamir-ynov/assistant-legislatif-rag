"""Interface de chat Chainlit, branchée directement sur repondre() (pas de framework RAG).

Lancer :  chainlit run chainlit_app.py -w --port 8001
Ouvrir :  http://localhost:8001
(port 8001 pour ne pas entrer en conflit avec l'API FastAPI, sur 8000)
"""
import time

import chainlit as cl

from app.embeddings import charger_modele
from app.journal import journaliser_avis, journaliser_question
from app.llm_client import ErreurLLM
from app.rag import repondre
from app.retriever import collection

LIBELLES_STATUT_COURTS = {
    "promulgue": "promulguée",
    "adopte": "adoptée",
    "rejete": "rejetée",
    "retire": "retirée",
    "en_cours": "en cours",
}


@cl.set_starters
async def suggestions():
    """Les 3 questions cibles du POC, proposées en boutons sur l'écran d'accueil."""
    return [
        cl.Starter(label="Lois promulguées récemment",
                   message="Quelles lois ont été promulguées récemment ?"),
        cl.Starter(label="Où en est le texte sur la fin de vie ?",
                   message="Où en est le texte sur la fin de vie ?"),
        cl.Starter(label="Textes déposés récemment",
                   message="Quels textes ont été déposés récemment à l'Assemblée ?"),
    ]


@cl.on_chat_start
async def demarrage():
    # Même rôle que le lifespan de l'API : charger modèle et base avant la 1re question.
    # make_async : ces appels sont bloquants, on les exécute dans un thread séparé.
    await cl.make_async(charger_modele)()
    await cl.make_async(collection)()


def mise_en_forme(resultat: dict) -> str:
    """Réponse du LLM + bloc confiance + sources (construites par le code, donc exactes)."""
    confiance = resultat["confiance"]
    lignes = [resultat["reponse"], "", "---", f"**{confiance['libelle']}**"]
    lignes += [f"- {raison}" for raison in confiance["raisons"]]
    if resultat["sources"]:
        lignes += ["", "**Dossiers consultés :**"]
        lignes += [f"- [{s['titre']}]({s['url']}) ({LIBELLES_STATUT_COURTS[s['statut']]})"
                   for s in resultat["sources"]]
    return "\n".join(lignes)


@cl.on_message
async def question(message: cl.Message):
    texte = message.content.strip()
    if not 3 <= len(texte) <= 500:  # mêmes limites que l'API (modèle Question)
        await cl.Message(content="Merci de poser une question de 3 à 500 caractères.").send()
        return
    debut = time.perf_counter()
    try:
        resultat = await cl.make_async(repondre)(texte)
    except ErreurLLM as e:
        journaliser_question("chainlit", texte, int((time.perf_counter() - debut) * 1000), erreur=str(e))
        await cl.Message(content=f"⚠️ Service momentanément indisponible : {e}").send()
        return
    identifiant = journaliser_question("chainlit", texte, int((time.perf_counter() - debut) * 1000), resultat)
    # Boutons d'avis sous la réponse : l'id relie l'avis à la question dans le journal
    boutons = [cl.Action(name="avis", label="👍 Utile", payload={"id": identifiant, "utile": True}),
               cl.Action(name="avis", label="👎 Pas utile", payload={"id": identifiant, "utile": False})]
    cl.user_session.set(f"avis_{identifiant}", boutons)
    await cl.Message(content=mise_en_forme(resultat), actions=boutons).send()


@cl.action_callback("avis")
async def avis(action: cl.Action):
    journaliser_avis(action.payload["id"], action.payload["utile"])
    # Un seul avis par réponse : les deux boutons disparaissent
    for bouton in cl.user_session.get(f"avis_{action.payload['id']}", [action]):
        await bouton.remove()
    await cl.Message(content="Merci pour votre avis !").send()
