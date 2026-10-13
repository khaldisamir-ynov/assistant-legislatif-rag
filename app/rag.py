"""Orchestration RAG : question -> retriever -> prompt -> LLM -> réponse + sources.

C'est cette fonction que l'API appellera (étape 7).

Test :  python -m app.rag "Quelles lois ont été promulguées récemment ?"
        python -m app.rag "..." --prompt     -> affiche le prompt sans appeler le LLM
"""
from app.llm_client import generer
from app.prompt import construire_messages
from app.retriever import rechercher


def repondre(question: str) -> dict:
    filtres, fiches = rechercher(question)
    messages = construire_messages(question, fiches, filtres)
    texte = generer(messages)  # peut lever ErreurLLM
    # Les sources sont construites par le CODE à partir des métadonnées,
    # pas recopiées par le LLM : elles sont donc toujours exactes.
    sources = [{"id": f["id"], "titre": f["metadonnees"]["titre"],
                "statut": f["metadonnees"]["statut"], "url": f["metadonnees"]["url"]} for f in fiches]
    # Si le LLM ne sait pas, les fiches trouvées étaient hors sujet : ne pas les afficher.
    if texte.startswith("Je ne sais pas"):
        sources = []
    # Les filtres appliqués sont renvoyés aussi : précieux pour déboguer et évaluer
    return {"reponse": texte, "sources": sources, "filtres": filtres.where()}


if __name__ == "__main__":
    import sys
    import time

    from app.llm_client import ErreurLLM

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
            print("\nSources :")
            for s in resultat["sources"]:
                print(f"  - [{s['statut']}] {s['titre'][:70]} : {s['url']}")
        print(f"\n({time.time() - debut:.1f} s)")
