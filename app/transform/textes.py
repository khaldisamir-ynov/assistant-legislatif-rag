"""Couche 2, TRANSFORMER : textes des documents -> chunks (un article ou un exposé, découpé si trop long).

1. Quels documents ? Les actes d'un dossier pointent vers eux (vérifié le 14/10/2026, 2 496 lois) :
   - AN1-DEPOT -> texteAssocie : texte DÉPOSÉ (exposé des motifs + articles), 2 002 dossiers ;
   - AN...-DEBATS-DEC -> textesAssocies : texte ADOPTÉ par l'Assemblée, 246 dossiers ;
   - 494 dossiers n'ont aucun texte à l'AN (déposés au Sénat, jamais transmis).
   Rapports, avis, études d'impact (~5 000 documents) : écartés, aucune question n'en a besoin.

2. Comment découper ? On suit la structure juridique : un chunk = un article (ou un exposé des
   motifs). Couper au milieu d'un article mélangerait deux règles ; regrouper plusieurs articles
   empêcherait de répondre "que dit l'article 3" sans renvoyer l'article voisin (question 16).
   Le modèle e5 lit au plus 512 tokens : un article trop long est coupé ENTRE deux alinéas.
   Chaque morceau commence par un en-tête (dossier, version du texte, article) : sans lui,
   "Le I de l'article L. 2315-92 est complété..." ne dirait pas de quel texte il s'agit.

Test :  python -m app.transform.textes PIONANR5L17B1847   -> chunks d'un document en cache
"""
import re

from app.sources.an_dossiers import actes_dates, en_liste
from app.transform.fiches_dossiers import en_entier, en_francais

TAILLE_MAX = 1000  # caractères hors en-tête. Mesuré : à 1 200, 15 chunks sur 4 327 dépassaient 512 tokens
TYPES_GARDES = {"Article": "article", "Exposé des motifs": "expose"}  # libellés RÉELS renvoyés par l'API
LIBELLES_ROLE = {"depose": "texte déposé", "adopte": "texte adopté par l'Assemblée nationale"}

MOTIF_DEPOT_AN = re.compile(r"^AN(\d|NLEC|LDEF)?-DEPOT$")  # AN1-DEPOT, AN2-DEPOT, ANNLEC-DEPOT...


def documents_cibles(dossier: dict) -> list[dict]:
    """Le 1er texte déposé à l'AN et le dernier texte adopté par l'AN, s'ils existent."""
    actes = actes_dates(dossier)
    cibles = []
    depot = next((a for a in actes if MOTIF_DEPOT_AN.match(a["code"]) and a["acte"].get("texteAssocie")), None)
    if depot:
        cibles.append({"uid": depot["acte"]["texteAssocie"], "dossier_uid": dossier["uid"],
                       "role": "depose", "date": depot["date"]})
    adoptes = [(a, t["refTexteAssocie"]) for a in actes
               if a["code"].startswith("AN") and a["code"].endswith("DEBATS-DEC")
               for t in en_liste((a["acte"].get("textesAssocies") or {}).get("texteAssocie"))]
    if adoptes:
        acte, uid = adoptes[-1]
        cibles.append({"uid": uid, "dossier_uid": dossier["uid"], "role": "adopte", "date": acte["date"]})
    return cibles


def _morceaux(alineas: list[str]) -> list[str]:
    """Regroupe les alinéas en morceaux de TAILLE_MAX caractères au plus, sans couper un alinéa.
    Exception : un alinéa seul plus long que TAILLE_MAX est coupé entre deux phrases."""
    morceaux, courant = [], ""
    for alinea in alineas:
        for bout in _couper_alinea(alinea):
            if courant and len(courant) + len(bout) + 1 > TAILLE_MAX:
                morceaux.append(courant)
                courant = ""
            courant = f"{courant}\n{bout}" if courant else bout
    if courant:
        morceaux.append(courant)
    return morceaux


def _couper_alinea(alinea: str) -> list[str]:
    """Alinéa trop long -> morceaux coupés en fin de phrase, ou entre deux mots en dernier recours
    (constaté : des tableaux budgétaires forment un seul "alinéa" de plusieurs milliers de caractères)."""
    if len(alinea) <= TAILLE_MAX:
        return [alinea]
    bouts, courant = [], ""
    for unite in re.split(r"(?<=[.;:])\s+", alinea):  # fin de phrase ou d'énumération
        mots = unite.split(" ") if len(unite) > TAILLE_MAX else [unite]
        for mot in mots:
            if courant and len(courant) + len(mot) + 1 > TAILLE_MAX:
                bouts.append(courant)
                courant = ""
            courant = f"{courant} {mot}" if courant else mot
    return bouts + [courant] if courant else bouts


def decouper(document: dict, cible: dict, fiche: dict) -> list[dict]:
    """Document en cache (app.sources.an_textes) -> chunks {id, texte, texte_recherche, metadonnees}.

    cible : sortie de documents_cibles() (rôle, date) ; fiche : métadonnées du dossier (titre, url).
    """
    titre_dossier, chunks, article_precedent = fiche["titre"], [], None
    version = f"{LIBELLES_ROLE[cible['role']]} le {en_francais(cible['date'])}"
    for sub in document["subdivisions"]:
        type_chunk = TYPES_GARDES.get(sub["type"])
        if type_chunk == "article":
            article_precedent = sub["titre"]
        # Titres, chapitres, sections : simples intitulés sans alinéa, ignorés
        if not type_chunk or not sub.get("alineas"):
            continue
        intitule = sub["titre"]
        if type_chunk == "expose" and article_precedent:
            # Projets de loi de finances : un exposé des motifs APRÈS chaque article (vérifié : PLFSS 2027)
            intitule = f"Exposé des motifs de l'{article_precedent[0].lower()}{article_precedent[1:]}"
        alineas = [a["texte"] for a in sorted(sub["alineas"], key=lambda a: int(a["numero"])) if a["texte"]]
        morceaux = _morceaux(alineas)
        for k, morceau in enumerate(morceaux, start=1):
            partie = f" (partie {k}/{len(morceaux)})" if len(morceaux) > 1 else ""
            texte = f"{titre_dossier} | {version} | {intitule}{partie}\n{morceau}"
            chunks.append({
                "id": f"{document['uid']}-{sub['sequence']}-{k}",
                "texte": texte,
                "texte_recherche": texte,  # court par construction : on vectorise tout le chunk
                "metadonnees": {
                    "dossier_uid": cible["dossier_uid"],
                    "document_uid": document["uid"],
                    "role": cible["role"],
                    "type": type_chunk,
                    "numero": sub["numero"] or "",   # "3", "1 bis"... ; "" pour un exposé
                    "intitule": intitule,
                    "partie": k,
                    "titre": titre_dossier,
                    "url": fiche["url"],
                    "date_int": en_entier(cible["date"]),
                    "source": document["source"],  # provenance : "tricoteuses"
                },
            })
    return chunks


if __name__ == "__main__":
    import sys
    from collections import Counter

    from app import config
    from app.sources import an_dossiers, an_textes
    from app.transform import jsonl
    from app.transform.fiches_dossiers import est_une_loi

    fiches = {f["id"]: f["metadonnees"] for f in jsonl.lire(config.PROCESSED_DIR / "dossiers.jsonl")}
    cibles = [c for d in an_dossiers.iter_dossiers() if est_une_loi(d) for c in documents_cibles(d)]
    if len(sys.argv) > 1:
        cible = next(c for c in cibles if c["uid"] == sys.argv[1])
        for ch in decouper(an_textes.lire(cible["uid"]), cible, fiches[cible["dossier_uid"]]):
            print(f"--- {ch['id']}  ({len(ch['texte'])} car.)\n{ch['texte'][:300]}\n")
    else:
        chunks, docs = [], 0
        for c in cibles:
            doc = an_textes.lire(c["uid"])
            if doc and c["dossier_uid"] in fiches:
                docs += 1
                chunks += decouper(doc, c, fiches[c["dossier_uid"]])
        longueurs = sorted(len(ch["texte"]) for ch in chunks)
        print(f"Documents en cache : {docs}/{len(cibles)} ; chunks : {len(chunks)}")
        print("Par type :", Counter(ch["metadonnees"]["type"] for ch in chunks).most_common())
        print(f"Longueur (car.) : médiane {longueurs[len(longueurs) // 2]}, max {longueurs[-1]}")
        print(f"Identifiants uniques : {len({ch['id'] for ch in chunks}) == len(chunks)}")
