"""Étape 4 : interroger ChromaDB, sans puis avec filtres de métadonnées.

Usage :  python demo_chroma.py   (après python ingest.py)
"""
import chromadb

from app import config
from app.embeddings import encoder_requete


def chercher(titre, question, where=None, n=5):
    """Recherche sémantique (top n), éventuellement restreinte par un filtre `where`."""
    resultats = collection.query(
        query_embeddings=[encoder_requete(question)],  # JAMAIS query_texts (cf. erreurs fréquentes)
        n_results=n,
        where=where,
    )
    print(f"\n=== {titre}\nQuestion : {question}\nFiltre   : {where}")
    # query() renvoie des listes de listes : une liste de résultats PAR question posée
    for meta, distance in zip(resultats["metadatas"][0], resultats["distances"][0]):
        print(f"  {1 - distance:.3f}  [{meta['statut']:<9}] dernière étape {meta['date_derniere_etape_int']}"
              f"  promulg. {meta['date_promulgation_int']}  {meta['titre'][:60]}")


client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
collection = client.get_collection(config.CHROMA_COLLECTION)
print(f"{collection.count()} documents dans la collection")

# 1. Recherche purement sémantique : le thème fonctionne...
chercher("Sémantique seule (thème)", "Où en est le texte sur les réseaux sociaux et les enfants ?")

# 2. ... mais "récemment" n'est pas compris : les dates ne sont pas dans le vecteur
chercher("Sémantique seule (temps)", "Quelles lois ont été promulguées récemment ?")

# 3. Même question + filtre d'égalité sur le statut
chercher("Filtre statut", "Quelles lois ont été promulguées récemment ?",
         where={"statut": "promulgue"})

# 4. Filtre combiné : statut ET date >= 01/07/2026  ($and obligatoire dès 2 conditions)
chercher("Filtre statut + date", "Quelles lois ont été promulguées récemment ?",
         where={"$and": [{"statut": "promulgue"},
                         {"date_promulgation_int": {"$gte": 20260701}}]})

# 5. Question 3 : textes déposés à l'Assemblée depuis le 01/09/2026
chercher("Filtre date de dépôt AN", "Quels textes ont été déposés récemment à l'Assemblée ?",
         where={"date_depot_an_int": {"$gte": 20260901}})
