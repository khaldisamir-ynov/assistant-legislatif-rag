"""Modèle d'embeddings : transforme un texte en vecteur.

Utilisé par l'ingestion (fiches = "passages") ET par l'API (questions = "queries").
Le nom du modèle vient de config.EMBEDDING_MODEL : impossible d'en utiliser
deux différents par erreur.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app import config


@lru_cache(maxsize=1)
def charger_modele() -> SentenceTransformer:
    """Charge le modèle UNE seule fois (~1 Go, quelques secondes), puis le réutilise."""
    return SentenceTransformer(config.EMBEDDING_MODEL)


def encoder_passages(textes: list[str]) -> list[list[float]]:
    """Vecteurs des documents à indexer. Les modèles e5 exigent le préfixe 'passage: '."""
    vecteurs = charger_modele().encode(
        [f"passage: {t}" for t in textes],
        normalize_embeddings=True,  # norme 1 => similarité cosinus = produit scalaire
        batch_size=32,
        show_progress_bar=len(textes) > 100,
    )
    return vecteurs.tolist()


def encoder_requete(question: str) -> list[float]:
    """Vecteur d'une question d'utilisateur. Les modèles e5 exigent le préfixe 'query: '."""
    vecteur = charger_modele().encode(f"query: {question}", normalize_embeddings=True)
    return vecteur.tolist()
