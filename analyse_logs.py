"""Synthèse du journal des questions posées en production (data/logs/questions.jsonl).

Usage :  python analyse_logs.py            -> synthèse + réponses à relire en priorité
         python analyse_logs.py --jours 7  -> seulement les 7 derniers jours

Complète evaluate.py : evaluate.py rejoue 15 questions connues, ce script regarde
les VRAIES questions des utilisateurs et leurs avis.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median

from app.confiance import LIBELLES_NIVEAU
from app.journal import FICHIER, lire


def centile(valeurs: list[int], p: float) -> int:
    valeurs = sorted(valeurs)
    return valeurs[min(len(valeurs) - 1, int(p * len(valeurs)))]


def pourcentage(n: int, total: int) -> str:
    return f"{n:>4}  ({100 * n / total:.0f} %)" if total else f"{n:>4}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jours", type=int, help="ne garder que les N derniers jours")
    args = parser.parse_args()

    evenements = lire()
    if args.jours:
        limite = datetime.now(timezone.utc) - timedelta(days=args.jours)
        evenements = [e for e in evenements if datetime.fromisoformat(e["horodatage"]) >= limite]
    questions = [e for e in evenements if e["type"] == "question"]
    if not questions:
        print(f"Aucune question dans le journal ({FICHIER}).")
        return

    # Avis : le dernier donné pour une réponse l'emporte
    avis = {e["id"]: e for e in evenements if e["type"] == "avis"}
    for q in questions:
        q["utile"] = avis[q["id"]]["utile"] if q["id"] in avis else None
        q["commentaire"] = avis[q["id"]].get("commentaire", "") if q["id"] in avis else ""

    reussies = [q for q in questions if "erreur" not in q]
    print(f"Journal : {FICHIER}")
    print(f"Période : {questions[0]['horodatage'][:10]} → {questions[-1]['horodatage'][:10]}")
    print(f"\nQuestions : {len(questions)}   "
          + "   ".join(f"{canal} {n}" for canal, n in Counter(q["canal"] for q in questions).items()))
    print(f"Erreurs LLM : {pourcentage(len(questions) - len(reussies), len(questions))}")

    print("\nConfiance (calculée par le code) :")
    niveaux = Counter(q["confiance"] for q in reussies)
    for niveau, libelle in LIBELLES_NIVEAU.items():
        print(f"  {libelle:<42}{pourcentage(niveaux[niveau], len(reussies))}")

    notees = [q for q in reussies if q["utile"] is not None]
    utiles = sum(q["utile"] for q in notees)
    print(f"\nAvis utilisateurs : {len(notees)} sur {len(reussies)} réponses")
    if notees:
        print(f"  👍 utile      {pourcentage(utiles, len(notees))}")
        print(f"  👎 pas utile  {pourcentage(len(notees) - utiles, len(notees))}")
        # Croisement : la confiance calculée prédit-elle l'avis des utilisateurs ?
        print("  Taux de 👍 par niveau de confiance :")
        for niveau, libelle in LIBELLES_NIVEAU.items():
            groupe = [q["utile"] for q in notees if q["confiance"] == niveau]
            if groupe:
                print(f"    {libelle:<40}{100 * sum(groupe) / len(groupe):>4.0f} %  ({len(groupe)} avis)")

    latences = [q["latence_ms"] for q in reussies]
    if latences:
        print(f"\nLatence : médiane {median(latences) / 1000:.1f} s, "
              f"90e centile {centile(latences, 0.9) / 1000:.1f} s, max {max(latences) / 1000:.1f} s")

    # À relire en priorité : avis négatif, puis confiance faible, puis refus (= trou dans les données ?)
    priorite = {"faible": 1, "refus": 2, "a_verifier": 3}
    a_relire = sorted((q for q in reussies if q["utile"] is False or q["confiance"] in priorite),
                      key=lambda q: (q["utile"] is not False, priorite.get(q["confiance"], 9)))
    if a_relire:
        print(f"\nÀ relire ({len(a_relire)}) :")
        for q in a_relire[:20]:
            marque = "👎" if q["utile"] is False else "  "
            print(f"  {marque} {LIBELLES_NIVEAU[q['confiance']][:1]} {q['horodatage'][:16]}  {q['question'][:70]}")
            if q["confiance"] == "faible":
                print(f"       → {'; '.join(q['raisons'])}")
            if q["commentaire"]:
                print(f"       « {q['commentaire'][:100]} »")
        if len(a_relire) > 20:
            print(f"  ... et {len(a_relire) - 20} autres (voir le journal)")


if __name__ == "__main__":
    main()
