"""Indicateur de confiance : la réponse du LLM est-elle ancrée dans ce qu'on lui a fourni ?

Principe : tout fait vérifiable cité dans la réponse (lien, date, numéro de loi)
doit figurer dans le prompt envoyé au LLM (fiches + date du jour + période).
Un fait absent du prompt a forcément été inventé.

Ce que ce contrôle NE détecte PAS (vérifié à l'étape 8) : une date bien présente
dans les fiches mais attribuée à la mauvaise étape (Conseil constitutionnel daté
du 30/06, date d'un autre vote). Il mesure la fidélité aux fiches, pas leur justesse.

Test :  python -m app.confiance
"""
import re

# Faits vérifiables, repérés par expression régulière
MOTIF_URL = re.compile(r"https?://[^\s)\]>*]+")
MOTIF_DATE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
MOTIF_NUMERO_LOI = re.compile(r"n°\s?(\d{4}-\d+)")

LIBELLES_NIVEAU = {
    "elevee": "🟢 Confiance élevée",
    "a_verifier": "🟠 À vérifier",
    "faible": "🔴 Confiance faible",
    "refus": "⚪ Pas de réponse (information absente)",
}


def _inconnus(motif: re.Pattern, reponse: str, contexte: str) -> list[str]:
    """Éléments trouvés dans la réponse mais absents du contexte (sans doublons, dans l'ordre)."""
    connus = set(motif.findall(contexte))
    trouves = [m.rstrip(".,;:") for m in motif.findall(reponse)]
    return list(dict.fromkeys(t for t in trouves if t not in connus))


def est_un_refus(reponse: str) -> bool:
    """« Je ne sais pas » sans aucun lien. Constaté le 14/10/2026 sur les questions orientées :
    le LLM refuse parfois la partie jugement (« ce budget courageux ») puis donne les faits et
    leurs liens. Cette réponse hybride est une vraie réponse, pas un refus."""
    return reponse.startswith("Je ne sais pas") and not MOTIF_URL.search(reponse)


def evaluer(reponse: str, contexte: str) -> dict:
    """Renvoie {"niveau", "libelle", "raisons"}.

    reponse  : texte généré par le LLM
    contexte : tout le texte envoyé au LLM (consignes, date du jour, fiches, question)
    """
    if est_un_refus(reponse):
        return {"niveau": "refus", "libelle": LIBELLES_NIVEAU["refus"], "raisons": []}

    raisons = []
    liens = _inconnus(MOTIF_URL, reponse, contexte)
    dates = _inconnus(MOTIF_DATE, reponse, contexte)
    numeros = _inconnus(MOTIF_NUMERO_LOI, reponse, contexte)
    if liens:
        raisons.append(f"{len(liens)} lien(s) absent(s) des sources : {', '.join(liens)}")
    if dates:
        raisons.append(f"{len(dates)} date(s) absente(s) des sources : {', '.join(dates)}")
    if numeros:
        raisons.append(f"{len(numeros)} numéro(s) de loi absent(s) des sources : {', '.join(numeros)}")

    # Règle 3 du prompt : chaque dossier mentionné doit être cité avec son lien
    aucun_lien = not MOTIF_URL.search(reponse)
    if aucun_lien:
        raisons.append("aucun lien cité : impossible de vérifier à quel dossier la réponse se rapporte")

    # Un fait inventé est plus grave qu'un lien oublié
    niveau = "faible" if (liens or dates or numeros) else "a_verifier" if aucun_lien else "elevee"
    return {"niveau": niveau, "libelle": LIBELLES_NIVEAU[niveau], "raisons": raisons}


if __name__ == "__main__":
    # Contexte factice, au format des vraies fiches
    contexte = (
        "Date du jour : 13/10/2026\n"
        "Loi promulguée le 18/08/2026 (n° 2026-794) : loi relative au droit à l'aide à mourir\n"
        "- 30/06/2026, Assemblée nationale : Décision : adoptée\n"
        "- 14/08/2026, Conseil constitutionnel : Conforme\n"
        "Lien : https://www.assemblee-nationale.fr/dyn/17/dossiers/fin_de_vie_17e"
    )
    lien = "https://www.assemblee-nationale.fr/dyn/17/dossiers/fin_de_vie_17e"
    cas = [
        ("fidèle", f"Loi n° 2026-794 promulguée le **18/08/2026**. [Lien]({lien}).", "elevee"),
        ("lien oublié", "La loi n° 2026-794 a été promulguée le 18/08/2026.", "a_verifier"),
        ("date inventée", f"Promulguée le 20/08/2026. Lien : {lien}", "faible"),
        ("numéro inventé", f"Loi n° 2026-999 du 18/08/2026. {lien}", "faible"),
        ("lien inventé", "Voir https://www.assemblee-nationale.fr/dyn/17/dossiers/invente.", "faible"),
        ("mauvaise date existante", f"Validée par le Conseil constitutionnel le 30/06/2026. {lien}", "elevee"),
        ("refus", "Je ne sais pas : cette information n'est pas dans les dossiers.", "refus"),
    ]
    for nom, reponse, attendu in cas:
        r = evaluer(reponse, contexte)
        verdict = "OK " if r["niveau"] == attendu else "KO "
        print(f"{verdict} {nom:<24} -> {r['libelle']}")
        for raison in r["raisons"]:
            print(f"       - {raison}")
    print("\nLe cas 'mauvaise date existante' est une LIMITE CONNUE : la date existe dans la fiche.")
