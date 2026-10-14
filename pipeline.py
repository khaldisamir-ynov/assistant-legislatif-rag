"""Pipeline de données (lancé chaque nuit) : EXTRAIRE -> TRANSFORMER -> STOCKER.

Chaque couche lit ce que la précédente a écrit sur le disque : on peut en relancer
une seule (ex. corriger une transformation sans retélécharger).

Usage :  python pipeline.py                        -> les 3 couches, avec téléchargement du jour
         python pipeline.py --sans-telechargement  -> réutilise les fichiers bruts déjà présents
         python pipeline.py --etape transformer    -> une seule couche (extraire | transformer | stocker)
"""
import argparse
import time
from collections import Counter

from app import config
from app.sources import an_dossiers
from app.stockage import chroma
from app.transform import jsonl
from app.transform.fiches_dossiers import construire_fiche

FICHES_JSONL = config.PROCESSED_DIR / "dossiers.jsonl"


def extraire(telecharger: bool) -> None:
    dossier = an_dossiers.telecharger_et_extraire(force=telecharger)
    print(f"[extraire]    {len(list(dossier.glob('*.json')))} dossiers bruts dans {dossier}")


def transformer() -> None:
    fiches = [f for f in map(construire_fiche, an_dossiers.iter_dossiers()) if f]  # None = hors périmètre
    jsonl.ecrire(FICHES_JSONL, fiches)
    statuts = Counter(f["metadonnees"]["statut"] for f in fiches)
    print(f"[transformer] {len(fiches)} fiches -> {FICHES_JSONL}  {dict(statuts.most_common())}")


def stocker() -> None:
    nb = chroma.indexer(config.CHROMA_COLLECTION, jsonl.lire(FICHES_JSONL))
    print(f"[stocker]     {nb} documents dans la collection '{config.CHROMA_COLLECTION}'")


def main():
    parser = argparse.ArgumentParser(description="Pipeline de données de l'assistant législatif")
    parser.add_argument("--etape", choices=["extraire", "transformer", "stocker"],
                        help="ne lancer qu'une couche (par défaut : les trois)")
    parser.add_argument("--sans-telechargement", action="store_true",
                        help="réutiliser les fichiers bruts déjà présents dans data/raw/")
    args = parser.parse_args()

    debut = time.time()
    if args.etape in (None, "extraire"):
        extraire(telecharger=not args.sans_telechargement)
    if args.etape in (None, "transformer"):
        transformer()
    if args.etape in (None, "stocker"):
        stocker()
    print(f"Terminé en {time.time() - debut:.0f} s")


if __name__ == "__main__":
    main()
