"""Étape 1 : exploration des dossiers législatifs.

Usage (depuis la racine du projet, venv activé) :
    python explore.py                  -> statistiques globales
    python explore.py DLR5L17N53187    -> chronologie d'un dossier
"""
import sys
from collections import Counter
from datetime import date

from app.an_data import DOSSIERS_DIR, actes_dates, iter_dossiers, lire_dossier, telecharger_et_extraire

AUJOURD_HUI = date.today().isoformat()  # "AAAA-MM-JJ" : comparable à nos dates texte


def statistiques():
    """Vue d'ensemble : combien de dossiers, de quels types, quels statuts possibles."""
    legislatures, procedures, derniers_codes = Counter(), Counter(), Counter()
    nb_promulgues = nb_actes_futurs = 0
    for d in iter_dossiers():
        legislatures[d["legislature"]] += 1
        procedures[d["procedureParlementaire"]["libelle"]] += 1
        actes = actes_dates(d)
        codes = [a["code"] for a in actes]
        if "PROM-PUB" in codes:
            nb_promulgues += 1
        nb_actes_futurs += sum(1 for a in actes if a["date"] > AUJOURD_HUI)
        if actes:
            derniers_codes[codes[-1]] += 1

    print(f"Dossiers : {sum(legislatures.values())}")
    print(f"Par législature : {sorted(legislatures.items())}")
    print("\nPar procédure :")
    for libelle, n in procedures.most_common():
        print(f"  {n:5}  {libelle}")
    print(f"\nDossiers avec promulgation (PROM-PUB) : {nb_promulgues}")
    print(f"Actes datés APRÈS aujourd'hui ({AUJOURD_HUI}) : {nb_actes_futurs}")
    print("\nCode du dernier acte daté (top 10) :")
    for code, n in derniers_codes.most_common(10):
        print(f"  {n:5}  {code}")


def chronologie(uid: str):
    """Affiche l'arbre des actes d'un dossier sous forme de frise chronologique."""
    d = lire_dossier(DOSSIERS_DIR / f"{uid}.json")
    titre = d["titreDossier"]
    print(f"{d['uid']}  (législature {d['legislature']})")
    print(f"Titre      : {titre['titre']}")
    print(f"Procédure  : {d['procedureParlementaire']['libelle']}")
    print(f"titreChemin: {titre.get('titreChemin')}")
    print()
    for a in actes_dates(d):
        futur = "  [PROGRAMMÉ]" if a["date"] > AUJOURD_HUI else ""
        decision = f"  => {a['decision']}" if a["decision"] else ""
        print(f"{a['date']}  {a['code']:<24} {a['libelle']}{decision}{futur}")
        if a["code"] == "PROM-PUB":
            print(f"            titreLoi : {a['acte'].get('titreLoi')}")
            print(f"            Légifrance : {(a['acte'].get('infoJO') or {}).get('urlLegifrance')}")


if __name__ == "__main__":
    telecharger_et_extraire()
    if len(sys.argv) > 1:
        chronologie(sys.argv[1])
    else:
        statistiques()
