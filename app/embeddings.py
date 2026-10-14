"""Modèle d'embeddings : transforme un texte en vecteur.

Utilisé par l'ingestion (fiches = "passages") ET par l'API (questions = "queries").
Le nom du modèle vient de config.EMBEDDING_MODEL : impossible d'en utiliser
deux différents par erreur.

On exécute la version ONNX officielle du modèle (mêmes poids, publiée dans le dépôt du
modèle) avec onnxruntime, au lieu de sentence-transformers + torch : image Docker
plus légère d'environ 1,2 Go. Vérifié le 14/10/2026 sur 315 textes : mêmes vecteurs
qu'avec sentence-transformers (écart max 5,5e-7, cosinus min 0,99999988).

Le calcul d'un embedding, en 4 étapes visibles :
1. tokenisation : texte -> numéros de tokens (512 au plus) ;
2. modèle (transformer) : un vecteur de 768 nombres PAR token ;
3. pooling : moyenne des vecteurs des tokens réels (le remplissage est ignoré) ;
4. normalisation : norme 1, donc similarité cosinus = produit scalaire.
"""
from functools import lru_cache

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from app import config

TAILLE_MAX = 512  # tokens : limite du modèle e5 ; au-delà, le texte est tronqué
TAILLE_LOT = 32


@lru_cache(maxsize=1)
def charger_modele() -> tuple[Tokenizer, ort.InferenceSession]:
    """Charge tokenizer et modèle UNE seule fois (~1 Go, quelques secondes), puis les réutilise.
    Téléchargés au 1er appel dans le cache Hugging Face, ensuite lus sur le disque."""
    tokenizer = Tokenizer.from_file(hf_hub_download(config.EMBEDDING_MODEL, "onnx/tokenizer.json"))
    tokenizer.enable_truncation(TAILLE_MAX)
    tokenizer.enable_padding()  # dans un lot, les textes courts sont complétés à la longueur du plus long
    session = ort.InferenceSession(hf_hub_download(config.EMBEDDING_MODEL, "onnx/model.onnx"),
                                   providers=["CPUExecutionProvider"])
    return tokenizer, session


def _encoder(textes: list[str]) -> np.ndarray:
    tokenizer, session = charger_modele()
    vecteurs = []
    for i in range(0, len(textes), TAILLE_LOT):
        encodages = tokenizer.encode_batch(textes[i:i + TAILLE_LOT])                          # 1. tokens
        ids = np.array([e.ids for e in encodages], dtype=np.int64)
        masque = np.array([e.attention_mask for e in encodages], dtype=np.int64)            # 1 = vrai token, 0 = remplissage
        etats = session.run(None, {"input_ids": ids, "attention_mask": masque})[0]          # 2. (lot, tokens, 768)
        poids = masque[..., None].astype(np.float32)
        moyennes = (etats * poids).sum(axis=1) / poids.sum(axis=1)                          # 3. pooling
        vecteurs.append(moyennes / np.linalg.norm(moyennes, axis=1, keepdims=True))         # 4. norme 1
    return np.vstack(vecteurs)


def encoder_passages(textes: list[str]) -> list[list[float]]:
    """Vecteurs des documents à indexer. Les modèles e5 exigent le préfixe 'passage: '."""
    return _encoder([f"passage: {t}" for t in textes]).tolist()


def encoder_requete(question: str) -> list[float]:
    """Vecteur d'une question d'utilisateur. Les modèles e5 exigent le préfixe 'query: '."""
    return _encoder([f"query: {question}"])[0].tolist()
