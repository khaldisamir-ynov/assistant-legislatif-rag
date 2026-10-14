"""Couche 1, EXTRAIRE : texte intégral des documents (exposé des motifs, articles, alinéas).

L'open data AN ne fournit que les métadonnées des documents. Le texte vient de l'API
publique, sans clé, du projet Tricoteuses, qui le sert déjà découpé :
    GET /subdivisions/json?documentRefUid=<uid>&include=alineas
Vérifié le 14/10/2026 : mêmes articles et alinéas que le HTML officiel (/dyn/docs/<uid>.raw).

Un document publié ne change plus : chaque réponse est gardée dans data/raw/an_textes/<uid>.json
et n'est jamais retéléchargée. Le pipeline peut donc s'interrompre et reprendre.

Test :  python -m app.sources.an_textes PIONANR5L17B1847
"""
import json
import time
from datetime import datetime

import requests

from app import config

SOURCE_DIR = config.RAW_DIR / "an_textes"
PAUSE = 1.0             # secondes entre deux appels : aucune limite annoncée, on reste poli
PAR_PAGE = 500          # subdivisions par page (un projet de loi de finances en compte ~110)
ATTENTES = [5, 15, 45]  # nouvelles tentatives en cas d'erreur réseau ou serveur (5xx)


def uid_api(uid: str) -> str:
    """Les textes adoptés "TAP" (provisoires) n'existent que sous la forme "BTA".
    Vérifié sur 5 cas sur 5, côté AN comme côté API : PIONANR5L17TAP0098 -> PIONANR5L17BTA0098."""
    return uid.replace("TAP", "BTA")


def chemin(uid: str):
    return SOURCE_DIR / f"{uid}.json"


def _appel(session: requests.Session, params: dict) -> list[dict]:
    for attente in ATTENTES + [None]:
        try:
            reponse = session.get(f"{config.TRICOTEUSES_API_URL}/subdivisions/json", params=params, timeout=60)
            if reponse.status_code < 500:
                reponse.raise_for_status()  # 4xx : erreur de notre requête, inutile de réessayer
                return reponse.json()["data"]
        except (requests.ConnectionError, requests.Timeout):
            pass
        if attente is None:
            raise RuntimeError(f"API Tricoteuses indisponible pour {params['documentRefUid']}")
        time.sleep(attente)


def recuperer(session: requests.Session, uid: str) -> list[dict]:
    """Toutes les subdivisions du document (avec leurs alinéas), page par page. [] si absent."""
    subdivisions, page = [], 1
    while True:
        lot = _appel(session, {
            "documentRefUid": uid_api(uid), "include": "alineas",
            "perPage": PAR_PAGE, "page": page, "sort": "sequence",
        })
        # Le vecteur calculé par l'API (autre modèle que le nôtre) est inutile : on le jette.
        # (Vérifié : l'API refuse "unselect=embedding", d'où le retrait côté client.)
        subdivisions += [{k: v for k, v in s.items() if k != "embedding"} for s in lot]
        if len(lot) < PAR_PAGE:
            return subdivisions
        page += 1
        time.sleep(PAUSE)


def telecharger(uids: list[str]) -> dict:
    """Télécharge les documents absents du cache. Renvoie des compteurs pour le suivi."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    a_faire = [u for u in uids if not chemin(u).exists()]
    compteurs = {"deja_en_cache": len(uids) - len(a_faire), "recuperes": 0, "absents_api": 0}
    session = requests.Session()
    session.headers["User-Agent"] = "assistant-legislatif (projet étudiant, POC RAG)"
    for i, uid in enumerate(a_faire, start=1):
        subdivisions = recuperer(session, uid)
        if subdivisions:
            chemin(uid).write_text(json.dumps({
                "uid": uid,
                "source": "tricoteuses",  # provenance, à citer
                "recupere_le": datetime.now().isoformat(timespec="seconds"),
                "subdivisions": subdivisions,
            }, ensure_ascii=False), encoding="utf-8")
            compteurs["recuperes"] += 1
        else:
            # Pas mis en cache : le document sera redemandé la nuit suivante (traitement en retard ?)
            compteurs["absents_api"] += 1
        if i % 50 == 0:
            print(f"  {i}/{len(a_faire)} ... {compteurs}")
        time.sleep(PAUSE)
    return compteurs


def lire(uid: str) -> dict | None:
    """Le document mis en cache, ou None s'il n'a pas (encore) été récupéré."""
    return json.loads(chemin(uid).read_text(encoding="utf-8")) if chemin(uid).exists() else None


if __name__ == "__main__":
    import sys

    print(telecharger(sys.argv[1:]))
    for uid in sys.argv[1:]:
        doc = lire(uid)
        if doc:
            print(uid, [(s["type"], s["numero"], len(s.get("alineas") or [])) for s in doc["subdivisions"]][:6])
