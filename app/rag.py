"""Orchestration RAG : question -> retriever -> prompt -> LLM -> réponse + sources.

Point d'entrée commun à l'API (app/main.py) et au chat (chainlit_app.py).

Test :  python -m app.rag "Quelles lois ont été promulguées récemment ?"
        python -m app.rag "..." --prompt     -> affiche le prompt sans appeler le LLM
"""
import time

from app.confiance import est_un_refus, evaluer
from app.embeddings import charger_modele
from app.journal import journaliser_question
from app.llm_client import ErreurLLM, generer
from app.prompt import construire_messages
from app.retriever import collection, rechercher
from app.suivi import enregistrer_requete


def prechauffer() -> None:
    """Charge le modèle d'embeddings et ouvre la base avant la 1re question (~5 s)."""
    charger_modele()
    collection()


def repondre(question: str) -> dict:
    filtres, fiches = rechercher(question)
    messages = construire_messages(question, fiches, filtres)
    texte, tokens = generer(messages)  # peut lever ErreurLLM
    # Les sources sont construites par le CODE à partir des métadonnées,
    # pas recopiées par le LLM : elles sont donc toujours exactes.
    sources = [{"id": f["id"], "titre": f["metadonnees"]["titre"],
                "statut": f["metadonnees"]["statut"], "url": f["metadonnees"]["url"]} for f in fiches]
    # Si le LLM ne sait pas, les fiches trouvées étaient hors sujet : ne pas les afficher.
    if est_un_refus(texte):
        sources = []
    # Confiance : chaque fait cité doit figurer dans ce qu'on a envoyé au LLM
    confiance = evaluer(texte, "\n".join(m["content"] for m in messages))
    # Les filtres appliqués sont renvoyés aussi : précieux pour déboguer et évaluer
    return {"reponse": texte, "sources": sources, "filtres": filtres.where(), "confiance": confiance,
            "tokens": tokens}


def repondre_et_journaliser(question: str, canal: str) -> dict:
    """repondre() + journal des questions + suivi MLflow. Ajoute "id" (à renvoyer avec l'avis) et
    "latence_ms". Une panne du LLM est enregistrée, puis l'ErreurLLM est relancée pour l'appelant."""
    debut = time.perf_counter()
    try:
        resultat = repondre(question)
    except ErreurLLM as e:
        latence_ms = int((time.perf_counter() - debut) * 1000)
        identifiant = journaliser_question(canal, question, latence_ms, erreur=str(e))
        enregistrer_requete(canal, question, latence_ms, identifiant, erreur=str(e))
        raise
    latence_ms = int((time.perf_counter() - debut) * 1000)
    identifiant = journaliser_question(canal, question, latence_ms, resultat)
    enregistrer_requete(canal, question, latence_ms, identifiant, resultat)
    return {**resultat, "id": identifiant, "latence_ms": latence_ms}


if __name__ == "__main__":
    import sys

    question = sys.argv[1]
    if "--prompt" in sys.argv:
        filtres, fiches = rechercher(question)
        for m in construire_messages(question, fiches, filtres):
            print(f"----- {m['role'].upper()} -----\n{m['content']}\n")
    else:
        debut = time.time()
        try:
            resultat = repondre(question)
        except ErreurLLM as e:
            print(f"ERREUR : {e}")
        else:
            print(resultat["reponse"])
            print(f"\n{resultat['confiance']['libelle']}")
            for raison in resultat["confiance"]["raisons"]:
                print(f"  - {raison}")
            print("\nSources :")
            for s in resultat["sources"]:
                print(f"  - [{s['statut']}] {s['titre'][:70]} : {s['url']}")
        print(f"\n({time.time() - debut:.1f} s)")
