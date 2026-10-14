"""Couche 2, TRANSFORMER : dossier législatif (JSON brut) -> "fiche texte" + métadonnées.

Fonctions pures : pas de téléchargement, pas de base de données.
- la fiche (texte) est vectorisée (en-tête seulement) et lue par le LLM ;
- les métadonnées servent aux filtres ChromaDB (dates, statut).

Test :  python -m app.transform.fiches_dossiers                 -> statistiques sur tous les dossiers
        python -m app.transform.fiches_dossiers DLR5L17N53187   -> fiche d'un dossier
"""
from datetime import date

from app.sources.an_dossiers import actes_dates

LIBELLES_STATUT = {
    "promulgue": "promulgué (loi publiée au Journal officiel)",
    "adopte": "adopté définitivement par le Parlement, en attente de promulgation",
    "rejete": "rejeté lors du dernier vote",
    "retire": "retiré par son auteur",
    "en_cours": "en cours d'examen au Parlement",
}

# Codes d'actes repris dans la liste des "étapes clés" de la fiche.
# Les réunions de commission, nominations de rapporteurs... sont du bruit ici.
SUFFIXES_CLES = ("-DEPOT", "-DEC", "-CONCLUSION", "-RTRINI", "-PROCACC", "PROM-PUB", "CMP-SAISIE")


def est_une_loi(dossier: dict) -> bool:
    """Garde les projets/propositions de loi, exclut résolutions, rapports, missions, motions."""
    procedure = dossier["procedureParlementaire"]["libelle"].lower()
    return "loi" in procedure or "ratification" in procedure


def institution(code_acte: str) -> str:
    """Le préfixe du code d'acte indique où l'acte a lieu (vérifié à l'étape 1)."""
    # Après une CMP, chaque chambre vote le texte commun : CMP-DEBATS-AN-..., CMP-DEBATS-SN-...
    if code_acte.startswith("CMP-DEBATS-AN"):
        return "Assemblée nationale (texte de la CMP)"
    if code_acte.startswith("CMP-DEBATS-SN"):
        return "Sénat (texte de la CMP)"
    for prefixe, nom in [("CMP", "Commission mixte paritaire"), ("CC", "Conseil constitutionnel"),
                         ("PROM", "Gouvernement"), ("AN", "Assemblée nationale"), ("SN", "Sénat")]:
        if code_acte.startswith(prefixe):
            return nom
    return "?"


def en_francais(date_iso: str) -> str:
    """'2026-08-24' -> '24/08/2026'"""
    a, m, j = date_iso.split("-")
    return f"{j}/{m}/{a}"


def en_entier(date_iso: str | None) -> int:
    """'2026-08-24' -> 20260824 ; None -> 0 (ChromaDB refuse les métadonnées None)."""
    return int(date_iso.replace("-", "")) if date_iso else 0


def premier_depot(actes: list[dict]) -> dict:
    """Premier acte de dépôt. Attention : ce n'est pas toujours le 1er acte daté,
    le rapporteur peut être nommé avant le dépôt officiel (cas vérifié : PLFSS 2027)."""
    return next((a for a in actes if a["code"].endswith("-DEPOT")), actes[0])


def calculer_statut(actes_passes: list[dict]) -> str:
    """Déduit le statut, absent des données, à partir des actes déjà réalisés.

    Règles simples, dans l'ordre (la première qui s'applique gagne) :
    1. un acte PROM-PUB                                    -> promulgue
    2. un acte de retrait (...-RTRINI)                     -> retire
    3. adoption définitive sans promulgation, signalée par :
       - un vote "sans modification" dans la 2e chambre (elle vote le texte
         conforme ; dans la 1re chambre, "sans modification" ne clôt rien),
       - le texte de CMP adopté par les deux chambres,
       - un vote en lecture définitive (ANLDEF) adopté,
       - une saisine du Conseil constitutionnel (n'intervient qu'après adoption)
                                                           -> adopte
    4. le dernier vote est un rejet et rien ne s'est passé depuis -> rejete
    5. sinon                                               -> en_cours
    Limite connue : c'est une heuristique, à valider sur des exemples.
    """
    codes = [a["code"] for a in actes_passes]
    if "PROM-PUB" in codes:
        return "promulgue"
    if any(c.endswith("RTRINI") for c in codes):
        return "retire"

    votes = [a for a in actes_passes if a["decision"]]
    adoptes = {a["code"] for a in votes if "adopt" in a["decision"].lower()}
    chambre_depot = premier_depot(actes_passes)["code"][:2]  # "AN" ou "SN"
    if (any("sans modification" in a["decision"] and a["code"][:2] != chambre_depot for a in votes)
            or {"CMP-DEBATS-AN-DEC", "CMP-DEBATS-SN-DEC"} <= adoptes
            or "ANLDEF-DEBATS-DEC" in adoptes
            or any(c.startswith("CC-") for c in codes)):
        return "adopte"

    if votes and "rejet" in votes[-1]["decision"].lower() and votes[-1]["date"] == actes_passes[-1]["date"]:
        return "rejete"
    return "en_cours"


def construire_url(dossier: dict) -> str:
    """Vérifié le 13/10/2026 (titre de la page contrôlé, inexistant -> 404) :
    - titreChemin et uid fonctionnent tous les deux ;
    - toujours /dyn/17/ : le site y redirige les dossiers des anciennes législatures,
      et le seul dossier de la 8e législature renvoie 404 sous /dyn/8/.
    """
    chemin = dossier["titreDossier"].get("titreChemin") or dossier["uid"]
    return f"https://www.assemblee-nationale.fr/dyn/17/dossiers/{chemin}"


def construire_fiche(dossier: dict, aujourd_hui: str | None = None) -> dict | None:
    """Renvoie {"id", "texte", "metadonnees"} ou None si le dossier est hors périmètre."""
    if not est_une_loi(dossier):
        return None
    aujourd_hui = aujourd_hui or date.today().isoformat()

    # Les actes datés dans le futur sont des séances PROGRAMMÉES, pas des étapes franchies.
    tous = actes_dates(dossier)
    passes = [a for a in tous if a["date"] <= aujourd_hui]
    futurs = [a for a in tous if a["date"] > aujourd_hui]
    if not passes:
        return None

    titre = dossier["titreDossier"]["titre"]
    statut = calculer_statut(passes)
    depot = premier_depot(passes)
    depot_an = next((a for a in passes if a["code"].startswith("AN") and a["code"].endswith("-DEPOT")), None)
    derniere = passes[-1]
    promulgation = next((a for a in passes if a["code"] == "PROM-PUB"), None)
    url = construire_url(dossier)

    # --- Texte de la fiche : phrases courtes, lisibles par un humain ET par le modèle ---
    lignes = [
        f"Dossier législatif : {titre}",
        f"Type : {dossier['procedureParlementaire']['libelle']}",
        f"Statut : {LIBELLES_STATUT[statut]}",
        f"Déposé le {en_francais(depot['date'])} ({institution(depot['code'])}).",
    ]
    if depot_an and depot_an is not depot:
        lignes.append(f"Transmis à l'Assemblée nationale le {en_francais(depot_an['date'])}.")
    if promulgation:
        acte = promulgation["acte"]
        lignes.append(f"Loi promulguée le {en_francais(promulgation['date'])} "
                      f"(n° {acte.get('codeLoi')}) : {acte.get('titreLoi')}")
    decision = f" : {derniere['decision']}" if derniere["decision"] else ""
    lignes.append(f"Dernière étape : {derniere['libelle']}{decision} ({institution(derniere['code'])}), "
                  f"le {en_francais(derniere['date'])}.")
    if futurs:
        lignes.append(f"Prochaine étape programmée : {futurs[0]['libelle']} "
                      f"({institution(futurs[0]['code'])}), le {en_francais(futurs[0]['date'])}.")
    lignes.append("Étapes clés :")
    for a in passes:
        if a["code"].endswith(SUFFIXES_CLES):
            decision = f" : {a['decision']}" if a["decision"] else ""
            lignes.append(f"- {en_francais(a['date'])}, {institution(a['code'])} : {a['libelle']}{decision}")
    lignes.append(f"Lien : {url}")

    # --- Métadonnées : uniquement str / int (contrainte ChromaDB), jamais None ---
    metadonnees = {
        "titre": titre,
        "statut": statut,
        "url": url,
        "date_depot_int": en_entier(depot["date"]),
        "date_depot_an_int": en_entier(depot_an["date"] if depot_an else None),
        "date_derniere_etape_int": en_entier(derniere["date"]),
        "date_promulgation_int": en_entier(promulgation["date"] if promulgation else None),
    }
    return {
        "id": dossier["uid"],
        "texte": "\n".join(lignes),             # fiche complète : lue par le LLM
        # Texte court, VECTORISÉ : titre + type + statut. Les étapes clés, communes à
        # toutes les fiches, diluaient le thème (constaté à l'étape 3 : "Sécu").
        "texte_recherche": "\n".join(lignes[:3]),
        "metadonnees": metadonnees,
    }


if __name__ == "__main__":
    import sys
    from collections import Counter

    from app.sources.an_dossiers import DOSSIERS_DIR, iter_dossiers, lire_dossier

    if len(sys.argv) > 1:
        fiche = construire_fiche(lire_dossier(DOSSIERS_DIR / f"{sys.argv[1]}.json"))
        if fiche is None:
            print("Hors périmètre (pas une loi, ou aucun acte passé)")
        else:
            print(fiche["texte"])
            print("\nMétadonnées :", fiche["metadonnees"])
    else:
        fiches = [f for f in map(construire_fiche, iter_dossiers()) if f]
        print(f"Fiches générées : {len(fiches)}")
        print("Statuts :", Counter(f["metadonnees"]["statut"] for f in fiches).most_common())
        longueurs = sorted(len(f["texte"]) for f in fiches)
        print(f"Longueur (caractères) : médiane {longueurs[len(longueurs) // 2]}, max {longueurs[-1]}")
        print("Exemples 'adopte' :", [f["id"] for f in fiches if f["metadonnees"]["statut"] == "adopte"][:5])
