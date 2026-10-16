"""Journal des questions posées en production (API et Chainlit), pour évaluer les réponses.

Un fichier JSONL (une ligne JSON par événement), en ajout seul : lisible à l'œil,
avec `grep`, ou par analyse_logs.py. Deux types d'événements, reliés par `id` :
- "question" : question, réponse, sources, filtres, confiance, latence, tokens, alertes du filtre de sortie (ou erreur LLM) ;
- "avis"     : 👍/👎 donné ensuite par l'utilisateur sur cette réponse.

Pas d'adresse IP ni d'identifiant d'utilisateur : seulement ce qui sert à évaluer.
Le journal est dans data/ : volume Docker, jamais dans l'image ni dans git.
"""
import json
import threading
import uuid
from datetime import datetime, timezone

from app import config

FICHIER = config.LOG_DIR / "questions.jsonl"
_verrou = threading.Lock()  # l'API traite plusieurs requêtes en parallèle (threads)


def _ecrire(evenement: dict) -> None:
    evenement = {"horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"), **evenement}
    ligne = json.dumps(evenement, ensure_ascii=False)
    try:
        with _verrou:
            FICHIER.parent.mkdir(parents=True, exist_ok=True)
            with open(FICHIER, "a", encoding="utf-8") as f:
                f.write(ligne + "\n")
    except OSError as e:
        # Un journal en panne (disque plein, droits) ne doit jamais empêcher de répondre
        print(f"Journal : écriture impossible ({e})")


def journaliser_question(canal: str, question: str, latence_ms: int,
                         resultat: dict | None = None, erreur: str | None = None) -> str:
    """Enregistre une question et sa réponse (ou l'erreur). Renvoie l'id, à réutiliser pour l'avis."""
    identifiant = uuid.uuid4().hex
    evenement = {"type": "question", "id": identifiant, "canal": canal,
                 "question": question, "latence_ms": latence_ms}
    if resultat is not None:
        evenement |= {"reponse": resultat["reponse"],
                      "confiance": resultat["confiance"]["niveau"],
                      "raisons": resultat["confiance"]["raisons"],
                      "sources": [s["id"] for s in resultat["sources"]],
                      "filtres": resultat["filtres"],
                      "tokens": resultat["tokens"],
                      "alertes": resultat["alertes"]}
    if erreur is not None:
        evenement["erreur"] = erreur
    _ecrire(evenement)
    return identifiant


def journaliser_avis(identifiant: str, utile: bool, commentaire: str = "") -> None:
    """Enregistre l'avis de l'utilisateur (👍 = utile) sur une réponse déjà journalisée."""
    _ecrire({"type": "avis", "id": identifiant, "utile": utile, "commentaire": commentaire})


def lire() -> list[dict]:
    """Tous les événements du journal (liste vide s'il n'existe pas encore)."""
    if not FICHIER.exists():
        return []
    with open(FICHIER, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]
