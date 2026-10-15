"""Suivi MLflow : historique des requêtes et des évaluations, avec les hyperparamètres du RAG.

Deux expériences MLflow :
- "production" : un run par question posée (API ou Chainlit) ;
- "evaluation" : un run par lancement d'evaluate.py, pour comparer des réglages entre eux.
Chaque run porte les mêmes paramètres (modèles, nombre de fiches, ef_search...) : quand un
réglage change, l'historique montre son effet sur les métriques.

Le serveur MLflow tourne dans son propre conteneur (voir .env.example). Sans MLFLOW_TRACKING_URI,
le suivi est désactivé. Un serveur arrêté ou lent n'empêche jamais de répondre.
Le journal JSONL (app/journal.py) reste la référence pour les avis 👍/👎 et analyse_logs.py.
"""
import os
from concurrent.futures import ThreadPoolExecutor

# Serveur arrêté : 1 essai de 5 s au lieu de 7 essais de 120 s max, qui bloqueraient la file d'envoi
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")  # message affiché à chaque import de mlflow
os.environ.setdefault("MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT", "1")  # sinon 2 liens dans les logs à chaque question
import mlflow  # noqa: E402  (après les réglages ci-dessus)

from app import config, llm_client  # noqa: E402
from app.retriever import NB_RESULTATS, collection  # noqa: E402

ACTIF = bool(config.MLFLOW_TRACKING_URI)
if ACTIF:
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)

# Envoi hors du chemin de la réponse, une écriture à la fois
_envoi = ThreadPoolExecutor(max_workers=1)


def parametres() -> dict:
    """Hyperparamètres du pipeline RAG, lus là où ils sont définis (ef_search : dans la base elle-même)."""
    return {"modele_embeddings": config.EMBEDDING_MODEL, "modele_llm": config.LLM_MODEL,
            "temperature": llm_client.TEMPERATURE, "max_tokens": llm_client.MAX_TOKENS,
            "nb_fiches": NB_RESULTATS, "ef_search": collection().configuration["hnsw"]["ef_search"]}


def _envoyer_requete(canal: str, question: str, latence_ms: int, identifiant: str,
                     resultat: dict | None, erreur: str | None) -> None:
    try:
        mlflow.set_experiment("production")
        with mlflow.start_run(run_name=question[:60]):
            mlflow.log_params(parametres())
            mlflow.set_tags({"canal": canal, "journal_id": identifiant,
                             "confiance": resultat["confiance"]["niveau"] if resultat else "erreur_llm"})
            mlflow.log_metrics({"latence_ms": latence_ms,
                                "nb_sources": len(resultat["sources"]) if resultat else 0,
                                "erreur_llm": int(erreur is not None)})
            mlflow.log_dict({"question": question, "erreur": erreur, **(resultat or {})}, "requete.json")
    except Exception as e:  # noqa: BLE001  le suivi ne doit jamais faire tomber l'application
        print(f"MLflow : envoi impossible ({e})")


def enregistrer_requete(canal: str, question: str, latence_ms: int, identifiant: str,
                        resultat: dict | None = None, erreur: str | None = None) -> None:
    """Un run dans l'expérience "production", envoyé en arrière-plan."""
    if ACTIF:
        _envoi.submit(_envoyer_requete, canal, question, latence_ms, identifiant, resultat, erreur)


def enregistrer_evaluation(jeu: str, metriques: dict, fichiers: list[str]) -> None:
    """Un run dans l'expérience "evaluation". Synchrone : evaluate.py est lancé à la main."""
    if not ACTIF:
        print("MLflow : MLFLOW_TRACKING_URI absent, évaluation non suivie")
        return
    mlflow.set_experiment("evaluation")
    with mlflow.start_run(run_name=jeu):
        mlflow.log_params({**parametres(), "jeu": jeu})
        mlflow.log_metrics(metriques)
        for fichier in fichiers:
            mlflow.log_artifact(fichier)
    print(f"MLflow : évaluation enregistrée ({config.MLFLOW_TRACKING_URI}, expérience « evaluation »)")
