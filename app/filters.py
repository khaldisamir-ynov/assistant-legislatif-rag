"""Extraction de filtres depuis la question, par règles simples (regex).

Le modèle d'embeddings ne comprend pas "récemment" (constaté à l'étape 4) :
on traduit donc les indices de temps et de statut en filtres ChromaDB.

Test :  python -m app.filters "Quelles lois ont été promulguées récemment ?"
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

# Période -> nombre de jours en arrière. Choix arbitraire assumé : "récemment" = 90 jours.
PERIODES = [
    (r"aujourd'hui", 0),
    (r"cette semaine", 7),
    (r"ce mois", 30),
    (r"recemment|recents?|recentes?|dernierement|ces derniers temps", 90),
]
# Mot-clé -> statuts acceptés. "adopté" inclut "promulgué" : une loi promulguée a été adoptée.
STATUTS = [
    (r"promulgu", ["promulgue"]),
    (r"adopt|vote", ["adopte", "promulgue"]),
    (r"rejet", ["rejete"]),
    (r"retir", ["retire"]),
    (r"en cours|en discussion|en examen", ["en_cours"]),
]
# "Où en est le texte SUR les retraites ?" -> thème = "les retraites"
# Appliqué à la question ORIGINALE (on garde les accents, utiles au modèle).
MOTIF_THEME = r"\b(?:sur|contre|concernant|relatifs? à|relatives? à|à propos d[eu]?|en matière d[e'’])\s*(.+)"
# Le thème s'arrête à la fin de la proposition. Constaté le 14/10/2026 (paires miroir) : sinon
# « la fin de vie est une dérive dangereuse : où en est-elle » était vectorisé tel quel, et le
# jugement de la question changeait les dossiers retrouvés.
FIN_THEME = r"\s*(?:[,:;?!.]|\s(?:est|sont|a|ont|qui|ki)\b).*"


@dataclass
class Filtres:
    statuts: list[str] | None = None     # None = pas de filtre de statut
    champ_date: str = "date_derniere_etape_int"
    date_min: int | None = None          # AAAAMMJJ ; None = pas de filtre de date
    theme: str | None = None             # sujet explicite de la question

    def where(self) -> dict | None:
        """Traduit les filtres en clause `where` ChromaDB."""
        conditions = []
        if self.statuts:
            conditions.append({"statut": {"$in": self.statuts}})
        if self.date_min:
            conditions.append({self.champ_date: {"$gte": self.date_min}})
        if not conditions:
            return None                  # Chroma refuse un where vide {}
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def normaliser(texte: str) -> str:
    """Minuscules, sans accents : 'Promulguées' -> 'promulguees'. Simplifie les regex."""
    sans_accents = unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode()
    return sans_accents.lower()


def extraire_filtres(question: str, aujourd_hui: date | None = None) -> Filtres:
    q = normaliser(question)
    aujourd_hui = aujourd_hui or date.today()
    f = Filtres()

    # 1. Période : "récemment", "cette semaine", ou "les 30 derniers jours / 6 derniers mois"
    jours = next((n for motif, n in PERIODES if re.search(motif, q)), None)
    m = re.search(r"(\d+) derni\w* (jours?|semaines?|mois)", q)
    if m:
        jours = int(m.group(1)) * {"j": 1, "s": 7, "m": 30}[m.group(2)[0]]
    if jours is not None:
        f.date_min = int((aujourd_hui - timedelta(days=jours)).strftime("%Y%m%d"))

    # 2. Quelle date filtrer ? Dépend de l'événement évoqué.
    if "promulgu" in q:
        f.champ_date = "date_promulgation_int"
    elif re.search(r"depos|depot", q):
        f.champ_date = "date_depot_an_int"

    # 3. Statut : SEULEMENT pour les questions-listes ("Quelles lois ont été adoptées ?").
    #    Pour "Le budget a-t-il été voté ?", filtrer sur "adopté" cacherait le texte
    #    s'il ne l'est pas, alors que la bonne réponse est "non, il est en cours".
    if re.search(r"\bquel(le)?s\b|\bliste", q):
        f.statuts = next((s for motif, s in STATUTS if re.search(motif, q)), None)

    # 4. Thème explicite
    m = re.search(MOTIF_THEME, question, flags=re.IGNORECASE)
    if m:
        f.theme = re.sub(FIN_THEME, "", m.group(1)).strip() or None
    return f


if __name__ == "__main__":
    import sys
    f = extraire_filtres(sys.argv[1])
    print(f)
    print("where =", f.where())
