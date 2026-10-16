"""Contrôle de la sortie du LLM par le code : ce que le prompt demande, le code l'impose,
que le LLM ait été manipulé (injection de prompt) ou non.

- fuite des consignes (canari ou règle recopiée) : la réponse entière est remplacée par le refus ;
- image Markdown : retirée, car son URL serait chargée à l'affichage (fuite vers un site tiers) ;
- lien absent des fiches : retiré (site piège glissé dans la question, lien inventé).
Chaque intervention est une alerte, journalisée et suivie dans MLflow.
"""
import re

from app.confiance import MOTIF_URL
from app.prompt import CANARI, CONSIGNES, REFUS

MOTIF_IMAGE_MARKDOWN = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LIEN_RETIRE = "[lien retiré]"
# Règles du prompt système, repérées par leurs 40 premiers caractères
_REGLES = [ligne.strip()[:40] for ligne in CONSIGNES.splitlines() if len(ligne.strip()) > 40]


def fuite_consignes(reponse: str) -> bool:
    """Vrai si la réponse contient le canari du prompt système (fuite même traduite, constatée le
    16/10/2026), ou recopie une règle."""
    return CANARI in reponse or any(regle in reponse for regle in _REGLES)


def filtrer(reponse: str, fiches: str) -> tuple[str, list[str]]:
    """Réponse nettoyée et alertes. `fiches` : leur seul texte, sans la question, pour qu'un lien
    fourni par l'utilisateur ne compte pas comme une source."""
    if fuite_consignes(reponse):
        return REFUS, ["consignes du prompt dans la réponse : remplacée par le refus"]
    alertes = []
    texte, nb_images = MOTIF_IMAGE_MARKDOWN.subn("", reponse)
    if nb_images:
        alertes.append(f"{nb_images} image(s) Markdown retirée(s)")
    connus = set(MOTIF_URL.findall(fiches))

    def retirer_inconnu(m: re.Match) -> str:
        url = m.group().rstrip(".,;:")
        if url in connus:
            return m.group()
        alertes.append(f"lien absent des fiches retiré : {url}")
        return LIEN_RETIRE + m.group()[len(url):]

    return MOTIF_URL.sub(retirer_inconnu, texte).strip(), alertes
