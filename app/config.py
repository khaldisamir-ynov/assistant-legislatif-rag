"""Configuration centralisée du projet.

Toutes les valeurs variables (secrets, URL, noms de modèles) viennent de
l'environnement. Les autres modules importent ce fichier au lieu de lire
os.environ eux-mêmes : un seul endroit à modifier, aucun secret dans le code.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Racine du projet = dossier parent de app/
BASE_DIR = Path(__file__).resolve().parent.parent

# Charge .env s'il existe. Une variable déjà définie dans le système
# (ex. sur le serveur en production) reste prioritaire sur le fichier.
load_dotenv(BASE_DIR / ".env")

# --- Source de données (open data Assemblée nationale, 17e législature) ---
AN_ZIP_URL = (
    "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/"
    "dossiers_legislatifs/Dossiers_Legislatifs.json.zip"
)
AN_AGENDA_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/vp/reunions/Agenda.json.zip"
DATA_DIR = BASE_DIR / "data"
# Architecture en 3 couches : chaque couche écrit dans son propre dossier
RAW_DIR = DATA_DIR / "raw"              # 1. EXTRAIRE    : fichiers bruts, tels que téléchargés
PROCESSED_DIR = DATA_DIR / "processed"  # 2. TRANSFORMER : JSONL nettoyés, prêts à indexer

# --- ChromaDB (base vectorielle persistée sur disque) : 3. STOCKER ---
CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_COLLECTION = "dossiers"

# --- SQLite (données structurées : agenda) : 3. STOCKER ---
SQLITE_PATH = BASE_DIR / "assistant.db"

# --- Embeddings ---
# Défini UNE seule fois ici : ingest.py et l'API l'importent tous les deux,
# ce qui garantit le même modèle à l'ingestion et à la requête.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")

# --- LLM via une API compatible OpenAI ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.mistral.ai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "ministral-14b-latest")
