"""Étape 3 : comprendre les embeddings par l'expérience.

Usage :  python demo_embeddings.py
(1er lancement : téléchargement du modèle ~1 Go dans le cache Hugging Face)
"""
import math

from app.an_data import DOSSIERS_DIR, iter_dossiers, lire_dossier
from app.embeddings import charger_modele, encoder_passages, encoder_requete
from app.fiches import construire_fiche

# 4 vraies fiches, sur des thèmes bien distincts
DOSSIERS = {
    "DLR5L17N53187": "réseaux sociaux/mineurs",
    "DLR5L17N54951": "PLFSS 2027",
    "DLR5L17N54608": "logement",
    "DLR5L17N54096": "CREPS Vichy (sport)",
}
# Des questions formulées SANS reprendre les mots exacts des titres
QUESTIONS = [
    "Où en est le texte sur les enfants et les plateformes en ligne ?",
    "Le budget de la Sécu a-t-il été voté ?",
    "Y a-t-il une loi pour construire plus d'appartements ?",
    "Quelle est la recette de la tarte tatin ?",  # hors sujet
]


def cosinus(a, b):
    """Similarité cosinus "à la main" : produit scalaire / (norme a * norme b)."""
    produit = sum(x * y for x, y in zip(a, b))
    return produit / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def tableau(titre, vecteurs_q, vecteurs_p):
    print(f"\n{titre}")
    print(" " * 46 + "".join(f"{nom[:12]:>14}" for nom in DOSSIERS.values()))
    for q, vq in zip(QUESTIONS, vecteurs_q):
        scores = [cosinus(vq, vp) for vp in vecteurs_p]
        meilleur = scores.index(max(scores))
        cellules = "".join(f"{s:>13.3f}{'*' if i == meilleur else ' '}" for i, s in enumerate(scores))
        print(f"{q[:44]:<46}{cellules}")


modele = charger_modele()
fiches = [construire_fiche(lire_dossier(DOSSIERS_DIR / f"{uid}.json"))["texte"] for uid in DOSSIERS]

# 1. Un vecteur, c'est quoi ?
v = encoder_requete("Bonjour")
print(f"Dimension du vecteur : {len(v)}   5 premières valeurs : {[round(x, 3) for x in v[:5]]}")
print(f"Norme : {math.sqrt(sum(x * x for x in v)):.3f}  (normalisé => cosinus = produit scalaire)")

# 2. Similarités AVEC les préfixes e5 (la bonne pratique)
tableau("AVEC préfixes query:/passage:  (* = fiche la plus proche)",
        [encoder_requete(q) for q in QUESTIONS], encoder_passages(fiches))

# 3. Même chose SANS préfixes, pour comparer
sans = modele.encode(QUESTIONS + fiches, normalize_embeddings=True).tolist()
tableau("SANS préfixes (mauvaise pratique)", sans[:len(QUESTIONS)], sans[len(QUESTIONS):])

# 4. Les fiches tiennent-elles dans la fenêtre du modèle ?
longueurs = sorted(len(modele.tokenizer("passage: " + f["texte"])["input_ids"])
                   for f in map(construire_fiche, iter_dossiers()) if f)
print(f"\nFenêtre max du modèle : {modele.max_seq_length} tokens")
print(f"Tokens par fiche : médiane {longueurs[len(longueurs) // 2]}, max {longueurs[-1]}, "
      f"fiches tronquées : {sum(1 for n in longueurs if n > modele.max_seq_length)}")
