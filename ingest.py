"""Ingestion (lancée chaque nuit) : ZIP AN -> fiches -> embeddings -> ChromaDB.

Usage :  python ingest.py                     -> télécharge le ZIP du jour puis recharge la base
         python ingest.py --sans-telechargement -> réutilise le ZIP déjà présent dans data/
"""
import sys
import time

import chromadb

from app import config
from app.an_data import iter_dossiers, telecharger_et_extraire
from app.embeddings import encoder_passages
from app.fiches import construire_fiche

TAILLE_LOT = 500  # ChromaDB limite le nombre d'éléments par appel à add()


def main():
    debut = time.time()

    # 1. EXTRACT : la nuit, on force le téléchargement pour avoir les données du jour
    telecharger_et_extraire(force="--sans-telechargement" not in sys.argv)

    # 2. TRANSFORM : JSON -> fiches (None = hors périmètre)
    fiches = [f for f in map(construire_fiche, iter_dossiers()) if f]
    print(f"{len(fiches)} fiches construites")

    # 3. TRANSFORM : fiches -> vecteurs. On vectorise le texte COURT,
    #    mais c'est la fiche complète qui sera stockée et lue par le LLM.
    vecteurs = encoder_passages([f["texte_recherche"] for f in fiches])

    # 4. LOAD : on reconstruit la collection de zéro (simple, et aucun dossier
    #    obsolète ne peut subsister). Limite : la base est vide pendant ~1 min.
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    if config.CHROMA_COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(config.CHROMA_COLLECTION)
    collection = client.create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},  # distance = 1 - similarité cosinus
        embedding_function=None,  # on fournit NOS vecteurs e5 ; Chroma ne doit rien calculer
    )
    for i in range(0, len(fiches), TAILLE_LOT):
        lot = fiches[i:i + TAILLE_LOT]
        collection.add(
            ids=[f["id"] for f in lot],
            documents=[f["texte"] for f in lot],
            embeddings=vecteurs[i:i + TAILLE_LOT],
            metadatas=[f["metadonnees"] for f in lot],
        )
    print(f"{collection.count()} documents dans '{config.CHROMA_COLLECTION}' "
          f"({time.time() - debut:.0f} s)")


if __name__ == "__main__":
    main()
