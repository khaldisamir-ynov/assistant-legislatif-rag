"""Couche 1, EXTRAIRE : agenda de l'Assemblée nationale (séances et réunions de commission).

Vérifié le 14/10/2026 : le ZIP contient ~8 000 fichiers json/reunion/*.json,
du 01/07/2024 à environ un mois dans le futur, mis à jour chaque nuit.
On lit les JSON directement dans le ZIP : pas besoin de 8 000 fichiers sur le disque.

Test :  python -m app.sources.an_agenda   -> télécharge le ZIP du jour
"""
import json
import zipfile

import requests

from app import config

SOURCE_DIR = config.RAW_DIR / "an_agenda"
ZIP_PATH = SOURCE_DIR / "Agenda.json.zip"


def telecharger(force: bool = False) -> None:
    """Télécharge le ZIP s'il est absent (ou toujours si force=True)."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if force or not ZIP_PATH.exists():
        print(f"Téléchargement de {config.AN_AGENDA_URL} ...")
        reponse = requests.get(config.AN_AGENDA_URL, timeout=120)
        reponse.raise_for_status()
        ZIP_PATH.write_bytes(reponse.content)


def iter_reunions():
    """Parcourt les réunions une par une, sous la clé racine 'reunion'."""
    with zipfile.ZipFile(ZIP_PATH) as z:
        for nom in sorted(z.namelist()):
            if nom.endswith(".json"):
                yield json.loads(z.read(nom))["reunion"]


if __name__ == "__main__":
    telecharger(force=True)
    print(f"{sum(1 for _ in iter_reunions())} réunions dans {ZIP_PATH}")
