"""Accès aux données open data de l'Assemblée nationale (dossiers législatifs).

Une seule responsabilité : télécharger le ZIP, l'extraire et lire l'arbre des
actes. La transformation en "fiche texte" viendra à l'étape 2.
"""
import json
import zipfile
from pathlib import Path

import requests

from app import config

ZIP_PATH = config.DATA_DIR / "Dossiers_Legislatifs.json.zip"
RAW_DIR = config.DATA_DIR / "raw"
# Vérifié : le ZIP contient json/dossierParlementaire/ (les dossiers)
# et json/document/ (métadonnées des textes déposés, pas leur contenu).
DOSSIERS_DIR = RAW_DIR / "json" / "dossierParlementaire"


def telecharger_et_extraire(force: bool = False) -> Path:
    """Télécharge le ZIP (si absent ou force=True), l'extrait, renvoie le dossier des JSON."""
    config.DATA_DIR.mkdir(exist_ok=True)
    if force or not ZIP_PATH.exists():
        print(f"Téléchargement de {config.AN_ZIP_URL} ...")
        reponse = requests.get(config.AN_ZIP_URL, timeout=120)
        reponse.raise_for_status()  # erreur explicite si HTTP 4xx/5xx
        ZIP_PATH.write_bytes(reponse.content)
        force = True  # nouveau ZIP => on ré-extrait
    if force or not DOSSIERS_DIR.exists():
        with zipfile.ZipFile(ZIP_PATH) as z:
            z.extractall(RAW_DIR)
    return DOSSIERS_DIR


def lire_dossier(chemin: Path) -> dict:
    """Lit un fichier JSON et renvoie le contenu sous la clé racine 'dossierParlementaire'."""
    return json.loads(chemin.read_text(encoding="utf-8"))["dossierParlementaire"]


def iter_dossiers(dossiers_dir: Path = DOSSIERS_DIR):
    """Parcourt tous les dossiers, un par un (générateur : pas tout en mémoire)."""
    for chemin in sorted(dossiers_dir.glob("*.json")):
        yield lire_dossier(chemin)


def en_liste(valeur) -> list:
    """Normalise un champ issu d'une conversion XML -> JSON.

    Piège vérifié : 'acteLegislatif' vaut un dict s'il n'y a qu'un acte,
    une liste s'il y en a plusieurs, et le parent vaut None s'il n'y en a aucun.
    """
    if valeur is None:
        return []
    return valeur if isinstance(valeur, list) else [valeur]


def actes_dates(dossier: dict) -> list[dict]:
    """Aplatit l'arbre des actes et renvoie les actes datés, triés chronologiquement.

    Les actes "conteneurs" (1ère lecture, Travaux des commissions...) n'ont pas
    de date (dateActe = null) : on ne garde que les feuilles datées, en notant
    l'étape de premier niveau à laquelle elles appartiennent.
    """
    resultat = []

    def parcourir(noeud, etape):
        for acte in en_liste(noeud):
            # Au premier niveau, l'acte EST l'étape (ex. "1ère lecture")
            etape_courante = etape or acte["libelleActe"]["nomCanonique"]
            if acte.get("dateActe"):
                resultat.append({
                    "date": acte["dateActe"][:10],  # "2026-08-24T00:00..." -> "2026-08-24"
                    "code": acte["codeActe"],
                    "libelle": acte["libelleActe"]["nomCanonique"],
                    "etape": etape_courante,
                    # Présent sur les votes : "adoptée", "rejeté", "modifiée"...
                    "decision": (acte.get("statutConclusion") or {}).get("libelle"),
                    "acte": acte,  # l'acte brut, pour les champs spécifiques
                })
            enfants = acte.get("actesLegislatifs")
            if enfants:
                parcourir(enfants["acteLegislatif"], etape_courante)

    racine = dossier.get("actesLegislatifs")
    if racine:
        parcourir(racine["acteLegislatif"], None)
    return sorted(resultat, key=lambda a: a["date"])
