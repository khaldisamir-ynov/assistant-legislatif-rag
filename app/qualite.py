"""Contrôle qualité des fiches, entre TRANSFORMER et STOCKER : à chaque nouvelle donnée entrante.

Pourquoi ici : stocker() supprime la collection avant de la reconstruire. Sans ce
contrôle, des données cassées (format AN modifié, ZIP tronqué...) remplaceraient
la base de production sans que personne ne s'en aperçoive.

Deux niveaux :
- BLOQUANT : la donnée est fausse ou inutilisable -> la base actuelle est conservée ;
- ALERTE   : la donnée est valide mais suspecte -> on indexe, un humain regarde le rapport.

Deux familles de contrôles :
- règles sur le lot seul (schéma, unicité, dates, cohérences) ;
- comparaison avec la RÉFÉRENCE = le dernier lot mis en production (volume, statuts,
  dossiers disparus, statuts qui reculent). La référence est mise à jour par stocker().

Seuils fixés à partir des données mesurées le 14/10/2026.

Lancer seul :  python pipeline.py --etape controler   (contrôle sans rien indexer)
"""
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

from app import config
from app.transform.fiches_dossiers import LIBELLES_STATUT

QUALITE_DIR = config.DATA_DIR / "qualite"
REFERENCE = QUALITE_DIR / "reference.json"

BLOQUANT, ALERTE = "bloquant", "alerte"

CLES_METADONNEES = {"titre": str, "statut": str, "url": str, "date_depot_int": int, "date_depot_an_int": int,
                    "date_derniere_etape_int": int, "date_promulgation_int": int}
DATES_OPTIONNELLES = {"date_depot_an_int", "date_promulgation_int"}  # 0 = absente (ChromaDB refuse None)
PREFIXE_URL = "https://www.assemblee-nationale.fr/dyn/17/dossiers/"

# --- Seuils (mesures du 14/10/2026 entre parenthèses) ---
MIN_FICHES_SANS_REFERENCE = 1000   # 1er lancement : (2 496 fiches)
BAISSE_VOLUME_MAX = 0.05           # -5 % de fiches = bloquant : un dossier ne disparaît pas de l'open data
HAUSSE_VOLUME_MAX = 0.10           # +10 % d'un coup = alerte (quelques fiches par jour d'habitude)
TAUX_RETENUES = (0.70, 0.85)       # part des dossiers bruts gardés comme lois (77 %)
ECART_STATUT_MAX = 0.03            # 3 points de variation d'un statut = alerte (en_cours : 91,5 %)
TEXTE_RECHERCHE_MAX = 1500         # caractères ; ~512 tokens, limite du modèle e5 (max 674)
FRAICHEUR_MAX_JOURS = 14           # dernière étape la plus récente (aujourd'hui) : sinon source figée ?


@dataclass
class Controle:
    nom: str
    niveau: str   # BLOQUANT ou ALERTE
    ok: bool
    detail: str


def _exemples(ids: list[str], n: int = 3) -> str:
    return ", ".join(ids[:n]) + (f" (+{len(ids) - n})" if len(ids) > n else "")


def _date(entier: int) -> date | None:
    """20260824 -> date(2026, 8, 24) ; None si ce n'est pas une date du calendrier."""
    try:
        return datetime.strptime(str(entier), "%Y%m%d").date()
    except ValueError:
        return None


def _regle(nom: str, niveau: str, fautifs: list[str], quoi: str) -> Controle:
    """Contrôle "aucune fiche ne doit..." : détail = nombre et exemples de fiches fautives."""
    detail = f"{len(fautifs)} fiche(s) {quoi} : {_exemples(fautifs)}" if fautifs else "OK"
    return Controle(nom, niveau, not fautifs, detail)


def statistiques(fiches: list[dict], nb_bruts: int | None) -> dict:
    """Indicateurs du lot, conservés dans le rapport et dans la référence."""
    metas = [f["metadonnees"] for f in fiches if isinstance(f.get("metadonnees"), dict)]
    statuts = Counter(m.get("statut") for m in metas)
    titres = Counter(m.get("titre") for m in metas)
    return {
        "fiches": len(fiches),
        "dossiers_bruts": nb_bruts,
        "statuts": dict(statuts.most_common()),
        "titres_partages": sum(n for n in titres.values() if n > 1),
        "derniere_etape_max": max((m.get("date_derniere_etape_int", 0) for m in metas), default=0),
    }


def controler(fiches: list[dict], nb_bruts: int | None = None, reference: dict | None = None,
              aujourd_hui: date | None = None) -> list[Controle]:
    aujourd_hui = aujourd_hui or date.today()
    controles = []

    # --- 1. Schéma : sans lui, ChromaDB ou le retriever plantent ---
    schema_ko = []
    for f in fiches:
        m = f.get("metadonnees")
        if (not isinstance(f.get("id"), str) or not f.get("texte") or not f.get("texte_recherche")
                or not isinstance(m, dict) or set(m) != set(CLES_METADONNEES)
                or any(not isinstance(m[k], t) for k, t in CLES_METADONNEES.items())):
            schema_ko.append(str(f.get("id")))
    controles.append(_regle("Schéma des fiches", BLOQUANT, schema_ko, "mal formée(s)"))
    if schema_ko:
        return controles  # les contrôles suivants supposent un schéma correct
    metas = {f["id"]: f["metadonnees"] for f in fiches}

    # --- 2. Intégrité : règles que chaque fiche doit respecter ---
    ids = [f["id"] for f in fiches]
    doublons = [i for i, n in Counter(ids).items() if n > 1]
    controles.append(_regle("Identifiants uniques", BLOQUANT, doublons, "en double"))

    controles.append(_regle("Statut connu", BLOQUANT,
                            [i for i, m in metas.items() if m["statut"] not in LIBELLES_STATUT], "au statut inconnu"))

    dates_ko = []
    for i, m in metas.items():
        for cle in (k for k in CLES_METADONNEES if k.endswith("_int")):
            if m[cle] == 0 and cle in DATES_OPTIONNELLES:
                continue
            d = _date(m[cle])
            if d is None or d > aujourd_hui:
                dates_ko.append(i)
                break
    controles.append(_regle("Dates valides et non futures", BLOQUANT, dates_ko, "avec une date invalide ou future"))

    controles.append(_regle("Chronologie (dépôt ≤ dernière étape, dépôt ≤ promulgation)", BLOQUANT,
                            [i for i, m in metas.items() if m["date_depot_int"] > m["date_derniere_etape_int"]
                             or 0 < m["date_promulgation_int"] < m["date_depot_int"]], "incohérente(s)"))

    controles.append(_regle("Promulgué ⇔ date de promulgation", BLOQUANT,
                            [i for i, m in metas.items()
                             if (m["statut"] == "promulgue") != bool(m["date_promulgation_int"])], "incohérente(s)"))

    # Le LLM cite le lien lu dans la fiche, la source affichée vient des métadonnées : les deux doivent concorder
    controles.append(_regle("URL bien formée et présente dans la fiche", BLOQUANT,
                            [f["id"] for f in fiches if not f["metadonnees"]["url"].startswith(PREFIXE_URL)
                             or f"Lien : {f['metadonnees']['url']}" not in f["texte"]], "fautive(s)"))

    controles.append(_regle("Aucune valeur « None » dans le texte", BLOQUANT,
                            [f["id"] for f in fiches if "None" in f["texte"]], "concernée(s)"))

    # Au-delà de 512 tokens, le modèle tronque : la fin du texte vectorisé serait ignorée
    controles.append(_regle("Texte vectorisé assez court", ALERTE,
                            [f["id"] for f in fiches if len(f["texte_recherche"]) > TEXTE_RECHERCHE_MAX],
                            f"de plus de {TEXTE_RECHERCHE_MAX} caractères"))

    # --- 3. Pertinence : le lot permet-il de répondre aux questions cibles ? ---
    stats = statistiques(fiches, nb_bruts)
    if nb_bruts:
        taux = len(fiches) / nb_bruts
        bas, haut = TAUX_RETENUES
        controles.append(Controle("Part des dossiers retenus comme lois", ALERTE, bas <= taux <= haut,
                                  f"{taux:.0%} ({len(fiches)}/{nb_bruts}), attendu {bas:.0%}–{haut:.0%}"))

    recente = _date(stats["derniere_etape_max"])
    age = (aujourd_hui - recente).days if recente else None
    controles.append(Controle("Fraîcheur de la source", ALERTE, age is not None and age <= FRAICHEUR_MAX_JOURS,
                              f"dernière étape la plus récente il y a {age} j (max {FRAICHEUR_MAX_JOURS})"))

    il_y_a_90_j = int((aujourd_hui - timedelta(days=90)).strftime("%Y%m%d"))
    for question, champ in [("lois promulguées récemment", "date_promulgation_int"),
                            ("textes déposés récemment", "date_depot_int")]:
        n = sum(m[champ] >= il_y_a_90_j for m in metas.values())
        controles.append(Controle(f"Question cible « {question} » : données sur 90 j", ALERTE, n > 0,
                                  f"{n} dossier(s)"))

    # --- 4. Comparaison avec le dernier lot mis en production ---
    if reference is None:
        controles.append(Controle("Volume minimal (pas encore de référence)", BLOQUANT,
                                  len(fiches) >= MIN_FICHES_SANS_REFERENCE,
                                  f"{len(fiches)} fiches, minimum {MIN_FICHES_SANS_REFERENCE}"))
        return controles

    avant = reference["statistiques"]["fiches"]
    variation = (len(fiches) - avant) / avant
    controles.append(Controle("Pas de chute du volume", BLOQUANT, variation >= -BAISSE_VOLUME_MAX,
                              f"{avant} → {len(fiches)} ({variation:+.1%}), baisse max {BAISSE_VOLUME_MAX:.0%}"))
    controles.append(Controle("Pas de hausse brutale du volume", ALERTE, variation <= HAUSSE_VOLUME_MAX,
                              f"{variation:+.1%}, hausse max {HAUSSE_VOLUME_MAX:.0%}"))

    # Un dossier ne disparaît pas de l'open data : sinon, changement de format ou de filtre
    disparus = [i for i in reference["statuts"] if i not in metas]
    controles.append(_regle("Aucun dossier disparu", ALERTE, disparus, "présente(s) hier, absente(s) aujourd'hui"))

    # Un texte promulgué ou retiré ne change plus de statut : sinon, règle de statut cassée
    reculs = [i for i, s in reference["statuts"].items()
              if i in metas and s in ("promulgue", "retire") and metas[i]["statut"] != s]
    controles.append(_regle("Aucun statut définitif qui recule", ALERTE, reculs,
                            "promulguée(s) ou retirée(s) hier, plus aujourd'hui"))

    ecarts = []
    for statut in LIBELLES_STATUT:
        part_avant = reference["statistiques"]["statuts"].get(statut, 0) / avant
        part = stats["statuts"].get(statut, 0) / len(fiches)
        if abs(part - part_avant) > ECART_STATUT_MAX:
            ecarts.append(f"{statut} {part_avant:.1%} → {part:.1%}")
    controles.append(Controle("Répartition des statuts stable", ALERTE, not ecarts,
                              "; ".join(ecarts) or f"écarts ≤ {ECART_STATUT_MAX:.0%}"))
    return controles


def lire_reference() -> dict | None:
    if not REFERENCE.exists():
        return None
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def enregistrer_reference(fiches: list[dict], nb_bruts: int | None) -> None:
    """Appelé par stocker() une fois le lot indexé : il devient la référence du prochain."""
    QUALITE_DIR.mkdir(parents=True, exist_ok=True)
    reference = {"date": date.today().isoformat(), "statistiques": statistiques(fiches, nb_bruts),
                 "statuts": {f["id"]: f["metadonnees"]["statut"] for f in fiches}}
    REFERENCE.write_text(json.dumps(reference, ensure_ascii=False), encoding="utf-8")


def valider(fiches: list[dict], nb_bruts: int | None = None) -> bool:
    """Lance les contrôles, affiche et enregistre le rapport. Renvoie False si un contrôle bloquant échoue."""
    reference = lire_reference()
    controles = controler(fiches, nb_bruts, reference)
    stats = statistiques(fiches, nb_bruts)

    print(f"[qualité]     référence : {reference['date'] if reference else 'aucune (1er lancement)'}")
    for c in controles:
        symbole = "✅" if c.ok else ("❌" if c.niveau == BLOQUANT else "⚠️ ")
        print(f"  {symbole} {c.nom} : {c.detail}")
    bloquants = [c for c in controles if not c.ok and c.niveau == BLOQUANT]
    alertes = [c for c in controles if not c.ok and c.niveau == ALERTE]
    print(f"  → {len(bloquants)} bloquant(s), {len(alertes)} alerte(s), {stats['titres_partages']} fiches "
          f"partagent un titre avec une autre")

    QUALITE_DIR.mkdir(parents=True, exist_ok=True)
    rapport = QUALITE_DIR / f"rapport_{datetime.now():%Y-%m-%d_%H%M}.json"
    rapport.write_text(json.dumps({"valide": not bloquants, "statistiques": stats,
                                   "controles": [asdict(c) for c in controles]},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Rapport : {rapport}")
    return not bloquants

