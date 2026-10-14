"""Construction du prompt RAG : consignes + date du jour + fiches + question."""
from datetime import date

from app.filters import Filtres

# Les consignes de la contrainte projet, traduites en règles explicites pour le modèle.
CONSIGNES = """Tu es un assistant d'information sur les textes de loi examinés par le Parlement français.

Règles impératives :
1. Réponds UNIQUEMENT à partir des fiches fournies entre les balises <fiches>. N'utilise jamais tes connaissances générales.
2. Si les fiches ne permettent pas de répondre, réponds exactement : "Je ne sais pas : cette information n'est pas dans les dossiers législatifs dont je dispose." Ne devine jamais.
3. Pour chaque dossier que tu mentionnes, cite son lien (ligne "Lien :" de la fiche).
4. Reste strictement neutre : décris les faits (dates, étapes, votes, statut) sans jugement, sans opinion et sans qualifier les textes ou leurs auteurs.
5. Utilise les dates pour situer les événements par rapport à la date du jour. Une "prochaine étape programmée" n'a pas encore eu lieu.
6. Ignore les fiches sans rapport avec la question, sans les mentionner. Ne parle jamais de "fiches" ni de leurs numéros : l'utilisateur ne les voit pas.
7. Réponds en français, de façon concise (quelques phrases ou une courte liste)."""


def en_francais(aaaammjj: int) -> str:
    s = str(aaaammjj)
    return f"{s[6:]}/{s[4:6]}/{s[:4]}"


# Libellés lisibles : le LLM recopie ce qu'on lui donne. Constaté le 14/10/2026 : avec les noms
# techniques ("date_derniere_etape", "retire"), la réponse affichait ce jargon à l'utilisateur.
LIBELLES_CHAMP_DATE = {
    "date_promulgation_int": "date de promulgation",
    "date_depot_an_int": "date de dépôt à l'Assemblée nationale",
    "date_derniere_etape_int": "date de la dernière étape",
}
LIBELLES_STATUT = {"promulgue": "promulgué", "adopte": "adopté", "rejete": "rejeté",
                   "retire": "retiré", "en_cours": "en cours d'examen"}


def decrire_recherche(filtres: Filtres) -> str:
    """Explique au modèle COMMENT les fiches ont été choisies (utile pour "récemment")."""
    parties = []
    if filtres.statuts:
        parties.append("statut : " + ", ".join(LIBELLES_STATUT[s] for s in filtres.statuts))
    if filtres.date_min:
        parties.append(f"{LIBELLES_CHAMP_DATE[filtres.champ_date]} à partir du {en_francais(filtres.date_min)}")
    if filtres.theme:
        parties.append(f"thème : {filtres.theme}")
    if not parties:
        return "Fiches choisies par proximité de sens avec la question."
    tri = (" Seules les 5 fiches les plus récentes répondant à ces critères sont fournies, de la plus"
           " récente à la plus ancienne. D'autres textes de la même période peuvent exister :"
           " précise que ta liste n'est pas exhaustive.") \
        if filtres.date_min and not filtres.theme else ""
    return "Critères de sélection des fiches : " + " ; ".join(parties) + "." + tri


def construire_messages(question: str, fiches: list[dict], filtres: Filtres) -> list[dict]:
    """Format "messages" standard des API compatibles OpenAI : system + user."""
    bloc_fiches = "\n\n".join(f"[Fiche {i}]\n{f['texte']}" for i, f in enumerate(fiches, start=1))
    contenu = (
        f"Date du jour : {date.today().strftime('%d/%m/%Y')}\n"
        f"{decrire_recherche(filtres)}\n\n"
        f"<fiches>\n{bloc_fiches or '(aucune fiche trouvée)'}\n</fiches>\n\n"
        f"Question : {question}"
    )
    return [{"role": "system", "content": CONSIGNES}, {"role": "user", "content": contenu}]
