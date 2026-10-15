"""Couche 3, STOCKER : accès à ChromaDB, en écriture (pipeline) comme en lecture (retriever).

Un seul endroit connaît les réglages de la base (cosinus, vecteurs fournis par nous),
quel que soit le nombre de collections (dossiers aujourd'hui, articles de loi demain).
"""
from functools import lru_cache

import chromadb

from app import config
from app.embeddings import encoder_passages

TAILLE_LOT = 500  # ChromaDB limite le nombre d'éléments par appel à add()


@lru_cache(maxsize=1)
def client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


@lru_cache(maxsize=None)
def collection(nom: str):
    """Ouvre une collection une seule fois (réutilisée entre les requêtes de l'API)."""
    return client().get_collection(nom)


def indexer(nom: str, documents: list[dict]) -> int:
    """Reconstruit la collection `nom` à partir de documents {id, texte, texte_recherche, metadonnees}.

    On vectorise `texte_recherche` (court), on stocke `texte` (complet, lu par le LLM).
    On repart de zéro : simple, et aucun document obsolète ne peut subsister.
    Limite connue : la collection est vide pendant la reconstruction (~1 à 2 min).
    """
    vecteurs = encoder_passages([d["texte_recherche"] for d in documents])
    if nom in [c.name for c in client().list_collections()]:
        client().delete_collection(nom)
    collection.cache_clear()  # l'ancienne collection n'existe plus
    nouvelle = client().create_collection(
        name=nom,
        # cosine : distance = 1 - similarité cosinus. ef_search 500 au lieu de 100 : les scores e5 sont
        # si tassés que la recherche approximative ratait 5 % des vrais voisins (mesuré le 15/10/2026)
        configuration={"hnsw": {"space": "cosine", "ef_search": 500}},
        embedding_function=None,  # on fournit NOS vecteurs e5 ; Chroma ne doit rien calculer
    )
    for i in range(0, len(documents), TAILLE_LOT):
        lot = documents[i:i + TAILLE_LOT]
        nouvelle.add(
            ids=[d["id"] for d in lot],
            documents=[d["texte"] for d in lot],
            embeddings=vecteurs[i:i + TAILLE_LOT],
            metadatas=[d["metadonnees"] for d in lot],
        )
    return nouvelle.count()
