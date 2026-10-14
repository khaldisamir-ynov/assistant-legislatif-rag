"""API FastAPI : POST /ask (question) et POST /feedback (avis sur une réponse).

Lancer :  uvicorn app.main:app --reload
Swagger : http://127.0.0.1:8000/docs
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.embeddings import charger_modele
from app.journal import journaliser_avis, journaliser_question
from app.llm_client import ErreurLLM
from app.rag import repondre
from app.retriever import collection


# --- Schémas Pydantic : le "contrat" de l'API, validé automatiquement ---
class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500,
                          examples=["Quelles lois ont été promulguées récemment ?"])


class Source(BaseModel):
    id: str
    titre: str
    statut: str
    url: str


class Confiance(BaseModel):
    niveau: str = Field(description="elevee | a_verifier | faible | refus")
    libelle: str
    raisons: list[str]


class Reponse(BaseModel):
    id: str = Field(description="Identifiant de la réponse dans le journal, à renvoyer à /feedback")
    reponse: str
    sources: list[Source]
    confiance: Confiance
    filtres: dict | None = Field(description="Clause `where` ChromaDB appliquée (débogage)")
    latence_ms: int


class Avis(BaseModel):
    id: str = Field(min_length=32, max_length=32, description="`id` renvoyé par /ask")
    utile: bool
    commentaire: str = Field(default="", max_length=1000)


# --- Démarrage : on charge le modèle et la base UNE fois, avant la 1re requête ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    charger_modele()  # ~5 s : mieux au démarrage que pendant la 1re question
    print(f"Collection prête : {collection().count()} dossiers")
    yield


app = FastAPI(
    title="Assistant législatif",
    description="Questions sur les dossiers législatifs de la 17e législature (open data AN).",
    version="0.3.0",
    lifespan=lifespan,
)


# `def` (et non `async def`) : nos appels (modèle, ChromaDB, LLM) sont bloquants.
# FastAPI les exécute alors dans un thread séparé, sans figer le serveur.
@app.post("/ask", response_model=Reponse)
def ask(entree: Question) -> Reponse:
    debut = time.perf_counter()
    try:
        resultat = repondre(entree.question)
    except ErreurLLM as e:
        latence_ms = int((time.perf_counter() - debut) * 1000)
        journaliser_question("api", entree.question, latence_ms, erreur=str(e))
        # 503 = service dépendant indisponible : le client sait qu'il peut réessayer
        raise HTTPException(status_code=503, detail=str(e)) from e
    latence_ms = int((time.perf_counter() - debut) * 1000)
    identifiant = journaliser_question("api", entree.question, latence_ms, resultat)
    return Reponse(**resultat, id=identifiant, latence_ms=latence_ms)


@app.post("/feedback", status_code=204)
def feedback(avis: Avis) -> None:
    """Avis de l'utilisateur sur une réponse (utile ou non), ajouté au journal."""
    journaliser_avis(avis.id, avis.utile, avis.commentaire)


@app.get("/health")
def health() -> dict:
    """Sonde de santé (Docker HEALTHCHECK, cloud) : le service répond et la base est chargée.
    N'appelle PAS le LLM : une panne Mistral ne doit pas faire redémarrer le conteneur."""
    return {"statut": "ok", "dossiers": collection().count()}
