"""Retriever : question -> les 5 fiches les plus utiles.

Trois stratégies selon la question (filtres extraits par app/filters.py) :
1. thème explicite ("... sur les retraites")   -> recherche sémantique sur le thème, + filtres
2. liste temporelle sans thème ("récemment")    -> TOUS les dossiers filtrés, triés par date
3. sinon                                        -> recherche sémantique sur la question entière

Test :  python -m app.retriever "Quelles lois ont été promulguées récemment ?"
"""
from functools import lru_cache

import chromadb

from app import config
from app.embeddings import encoder_requete
from app.filters import Filtres, extraire_filtres

NB_RESULTATS = 5


@lru_cache(maxsize=1)
def collection():
    """Ouvre la collection une seule fois (réutilisée entre les requêtes de l'API)."""
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_collection(config.CHROMA_COLLECTION)


def _semantique(texte: str, where: dict | None) -> list[dict]:
    r = collection().query(query_embeddings=[encoder_requete(texte)], n_results=NB_RESULTATS, where=where)
    # query() renvoie une liste de résultats PAR question : on prend [0]
    return [{"id": i, "texte": doc, "metadonnees": meta, "score": round(1 - dist, 3)}
            for i, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])]


def _plus_recents(filtres: Filtres) -> list[dict]:
    # get() = filtrage pur, sans vecteur : on récupère tout ce qui passe le filtre
    r = collection().get(where=filtres.where(), include=["documents", "metadatas"])
    fiches = [{"id": i, "texte": doc, "metadonnees": meta, "score": None}
              for i, doc, meta in zip(r["ids"], r["documents"], r["metadatas"])]
    fiches.sort(key=lambda f: f["metadonnees"][filtres.champ_date], reverse=True)
    return fiches[:NB_RESULTATS]


def rechercher(question: str) -> tuple[Filtres, list[dict]]:
    """Renvoie les filtres appliqués (utile pour déboguer/expliquer) et les fiches."""
    filtres = extraire_filtres(question)
    if filtres.theme:
        fiches = _semantique(filtres.theme, filtres.where())
    elif filtres.date_min:
        fiches = _plus_recents(filtres)
    else:
        fiches = _semantique(question, filtres.where())
    return filtres, fiches


if __name__ == "__main__":
    import sys
    filtres, fiches = rechercher(sys.argv[1])
    print(filtres)
    print("where =", filtres.where())
    for f in fiches:
        m = f["metadonnees"]
        score = f"{f['score']:.3f}" if f["score"] is not None else "  -  "
        print(f"  {score}  [{m['statut']:<9}] {m[filtres.champ_date]}  {m['titre'][:70]}")
