"""Couche 2, TRANSFORMER : réunion brute -> points de l'ordre du jour (une ligne par point).

Le point est la bonne granularité : une séance traite souvent plusieurs textes
(ex. questions au Gouvernement, puis discussion d'un projet de loi).

Constats de l'exploration (14/10/2026), qui justifient les règles ci-dessous :
- 8 046 réunions : 6 743 de commission, 1 112 séances, 191 réunions diverses ;
- 70 % des réunions n'ont AUCUN point structuré (surtout des commissions, dont
  l'ordre du jour n'existe qu'en texte libre) : on les ignore ;
- états des points : Confirmé 2 873, Supprimé 2 407, Éventuel 546, Annulé 330 ;
- 48 % des points citent un dossier (dossierRef), dont 90 % sont dans nos fiches ;
- séances : 963 à l'Assemblée (lieuRef "AN"), 149 au Sénat (lieuRef "S").

Test :  python -m app.transform.agenda   -> statistiques + programme de la semaine prochaine
"""
from app.sources.an_dossiers import en_liste

ETATS_GARDES = {"Confirmé", "Eventuel"}  # "Annulé" et "Supprimé" n'auront pas lieu
TYPES_REUNION = {
    "seance_type": "seance",
    "reunionCommission_type": "commission",
    "reunionInitParlementaire_type": "autre",
}
CHAMBRES = {"AN": "Assemblée nationale", "S": "Sénat"}


def points_de_reunion(reunion: dict) -> list[dict]:
    """Renvoie les points maintenus de la réunion (liste vide si réunion annulée ou sans point)."""
    etat_reunion = reunion["cycleDeVie"]["etat"]
    if etat_reunion not in ETATS_GARDES:
        return []
    debut = reunion["timeStampDebut"]  # "2026-10-19T15:00:00.000+02:00" (heure de Paris)
    lieu = reunion.get("lieu") or {}   # absent sur 12 réunions de commission
    odj = reunion.get("ODJ") or {}
    points = []
    for point in en_liste((odj.get("pointsODJ") or {}).get("pointODJ")):
        etat_point = point["cycleDeVie"]["etat"]
        if etat_point not in ETATS_GARDES:
            continue
        points.append({
            "uid": point["uid"],
            "reunion_uid": reunion["uid"],
            "date": debut[:10],
            "heure": debut[11:16],
            "type_reunion": TYPES_REUNION.get(reunion["@xsi:type"], "autre"),
            "chambre": CHAMBRES.get(lieu.get("lieuRef")),  # None hors séance publique
            "organe_ref": reunion.get("organeReuniRef"),
            # "Éventuel" = inscrit sous réserve : à présenter comme tel, jamais comme certain
            "eventuel": "Eventuel" in (etat_reunion, etat_point),
            "type_point": point.get("typePointODJ"),
            "objet": point["objet"],
            # 81 points citent plusieurs dossiers : on les garde tous
            "dossiers": en_liste((point.get("dossiersLegislatifsRefs") or {}).get("dossierRef")),
        })
    return points


if __name__ == "__main__":
    from collections import Counter

    from app.sources.an_agenda import iter_reunions

    points = [p for r in iter_reunions() for p in points_de_reunion(r)]
    print(f"Points gardés : {len(points)}")
    print("Par type de réunion :", Counter(p["type_reunion"] for p in points).most_common())
    print(f"Avec au moins un dossier : {sum(1 for p in points if p['dossiers'])}")
    print("\nSéances à l'Assemblée du 19/10 au 25/10/2026 :")
    for p in sorted(points, key=lambda p: (p["date"], p["heure"])):
        if "2026-10-19" <= p["date"] <= "2026-10-25" and p["chambre"] == "Assemblée nationale":
            print(f"  {p['date']} {p['heure']}  {p['objet'][:70]}  {p['dossiers']}")
