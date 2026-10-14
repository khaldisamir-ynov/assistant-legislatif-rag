"""Pipeline de données (lancé chaque nuit) : EXTRAIRE -> TRANSFORMER -> CONTRÔLER -> STOCKER.

Chaque couche lit ce que la précédente a écrit sur le disque : on peut en relancer
une seule (ex. corriger une transformation sans retélécharger).
Le contrôle qualité (app/qualite.py) précède TOUJOURS le stockage : si un contrôle
bloquant échoue, la base actuelle est conservée et le pipeline sort en erreur (code 1).

Usage :  python pipeline.py                        -> tout, avec téléchargement du jour
         python pipeline.py --sans-telechargement  -> réutilise les fichiers bruts déjà présents
         python pipeline.py --etape controler      -> une seule couche (extraire | transformer | controler | stocker)
         python pipeline.py --forcer               -> indexe malgré un contrôle bloquant (après vérification humaine)
"""
import argparse
import sys
import time
from collections import Counter

from app import config, qualite
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


def nb_dossiers_bruts() -> int:
    return len(list(an_dossiers.DOSSIERS_DIR.glob("*.json")))


def controler() -> bool:
    return qualite.valider(jsonl.lire(FICHES_JSONL), nb_dossiers_bruts())


def stocker(forcer: bool) -> None:
    if not controler():
        if not forcer:
            print("[stocker]     ANNULÉ : contrôle bloquant en échec, la base actuelle est conservée")
            sys.exit(1)
        print("[stocker]     --forcer : indexation malgré le contrôle bloquant")
    fiches = jsonl.lire(FICHES_JSONL)
    nb = chroma.indexer(config.CHROMA_COLLECTION, fiches)
    qualite.enregistrer_reference(fiches, nb_dossiers_bruts())  # ce lot devient la référence du suivant
    print(f"[stocker]     {nb} documents dans la collection '{config.CHROMA_COLLECTION}'")


def main():
    parser = argparse.ArgumentParser(description="Pipeline de données de l'assistant législatif")
    parser.add_argument("--etape", choices=["extraire", "transformer", "controler", "stocker"],
                        help="ne lancer qu'une couche (par défaut : les trois)")
    parser.add_argument("--sans-telechargement", action="store_true",
                        help="réutiliser les fichiers bruts déjà présents dans data/raw/")
    parser.add_argument("--forcer", action="store_true",
                        help="indexer même si un contrôle qualité bloquant échoue")
    args = parser.parse_args()

    debut = time.time()
    if args.etape in (None, "extraire"):
        extraire(telecharger=not args.sans_telechargement)
    if args.etape in (None, "transformer"):
        transformer()
    if args.etape == "controler" and not controler():
        sys.exit(1)
    if args.etape in (None, "stocker"):
        stocker(args.forcer)  # contrôle qualité inclus
    print(f"Terminé en {time.time() - debut:.0f} s")


if __name__ == "__main__":
    main()
