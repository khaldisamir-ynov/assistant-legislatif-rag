"""Étape 8 : évaluation du POC sur 3 questions cibles + 2 hors périmètre.

Usage :  python evaluate.py      -> tableau de synthèse + evaluation_resultats.json

Pour chaque question on mesure :
- la latence (totale, et part du retriever) ;
- la pertinence du RETRIEVER, par des vérifications automatiques sur les sources ;
- la qualité de la RÉPONSE : liens cités, ou "Je ne sais pas" attendu.
La lecture humaine des réponses reste indispensable (exactitude, neutralité).
"""
import json
import time
from datetime import date, timedelta

from app.llm_client import ErreurLLM
from app.rag import repondre
from app.retriever import rechercher

IL_Y_A_90_JOURS = int((date.today() - timedelta(days=90)).strftime("%Y%m%d"))


def tries_par_date(sources, metas, champ):
    dates = [metas[s["id"]][champ] for s in sources]
    return dates == sorted(dates, reverse=True)


# Chaque cas : question, type, et une vérification du retriever (sources, métadonnées) -> bool
CAS = [
    {"question": "Quelles lois ont été promulguées récemment ?", "type": "cible",
     "attendu": "5 lois promulguées < 90 j, triées par date",
     "verif": lambda s, m: len(s) > 0 and all(m[x["id"]]["statut"] == "promulgue"
                                              and m[x["id"]]["date_promulgation_int"] >= IL_Y_A_90_JOURS for x in s)
                           and tries_par_date(s, m, "date_promulgation_int")},
    {"question": "Où en est le texte sur la fin de vie ?", "type": "cible",
     "attendu": "dossier 'Fin de vie' (DLR5L17N51670) en 1re position",
     "verif": lambda s, m: len(s) > 0 and s[0]["id"] == "DLR5L17N51670"},
    {"question": "Quels textes ont été déposés récemment à l'Assemblée ?", "type": "cible",
     "attendu": "5 textes déposés à l'AN < 90 j, triés par date",
     "verif": lambda s, m: len(s) > 0 and all(m[x["id"]]["date_depot_an_int"] >= IL_Y_A_90_JOURS for x in s)
                           and tries_par_date(s, m, "date_depot_an_int")},
    {"question": "Quelle est la recette de la tarte tatin ?", "type": "hors périmètre",
     "attendu": "Je ne sais pas, aucune source", "verif": None},
    {"question": "Que dit l'article 2 de la loi sur la fin de vie ?", "type": "hors périmètre",
     "attendu": "Je ne sais pas (le texte des lois n'est pas dans les données)", "verif": None},
]


def evaluer(cas):
    q = cas["question"]
    t0 = time.perf_counter()
    _, fiches = rechercher(q)                      # mesuré seul : part du retriever
    t_retriever = time.perf_counter() - t0
    metas = {f["id"]: f["metadonnees"] for f in fiches}

    t0 = time.perf_counter()
    try:
        r = repondre(q)                            # chaîne complète (retriever + LLM)
    except ErreurLLM as e:
        return {**cas, "verif": None, "erreur": str(e)}
    t_total = time.perf_counter() - t0

    ne_sait_pas = r["reponse"].startswith("Je ne sais pas")
    if cas["type"] == "hors périmètre":
        retriever_ok = None                        # rien à retrouver
        reponse_ok = ne_sait_pas and not r["sources"]
        liens = None
    else:
        retriever_ok = cas["verif"](r["sources"], metas)
        # Part des sources dont le lien apparaît dans le texte de la réponse
        cites = sum(1 for s in r["sources"] if s["url"] in r["reponse"])
        liens = f"{cites}/{len(r['sources'])}"
        reponse_ok = not ne_sait_pas
    return {"question": q, "type": cas["type"], "attendu": cas["attendu"],
            "retriever_ok": retriever_ok, "reponse_ok": reponse_ok, "liens_cites": liens,
            "latence_retriever_s": round(t_retriever, 2), "latence_totale_s": round(t_total, 1),
            "reponse": r["reponse"], "sources": [s["id"] for s in r["sources"]], "filtres": r["filtres"]}


def symbole(v):
    return {True: "OK", False: "ECHEC", None: "-"}[v]


if __name__ == "__main__":
    resultats = []
    for cas in CAS:
        resultats.append(evaluer(cas))
        time.sleep(2)  # ménage la limite de débit de l'API Mistral

    print(f"\n{'Question':<55} {'Type':<15} {'Retriever':<10} {'Réponse':<8} {'Liens':<6} {'Latence'}")
    for r in resultats:
        if "erreur" in r:
            print(f"{r['question'][:54]:<55} ERREUR : {r['erreur']}")
            continue
        print(f"{r['question'][:54]:<55} {r['type']:<15} {symbole(r['retriever_ok']):<10} "
              f"{symbole(r['reponse_ok']):<8} {r['liens_cites'] or '-':<6} "
              f"{r['latence_totale_s']} s (retriever {r['latence_retriever_s']} s)")

    with open("evaluation_resultats.json", "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    print("\nRéponses complètes : evaluation_resultats.json (à relire : exactitude, neutralité)")
