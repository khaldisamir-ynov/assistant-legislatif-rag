"""Filtre de sortie : rejoue des réponses malveillantes réellement obtenues à l'étape 1 (16/10/2026),
avant le durcissement du prompt. Le code doit les neutraliser seul, sans compter sur le LLM."""
import unittest

from app.filtre_sortie import LIEN_RETIRE, filtrer
from app.prompt import CANARI, REFUS

LIEN = "https://www.assemblee-nationale.fr/dyn/17/dossiers/fin_de_vie_17e"
FICHES = f"Dossier législatif : Fin de vie\nStatut : promulgué\nLien : {LIEN}"
FAITS = f"La loi relative au droit à l'aide à mourir a été promulguée le 18/08/2026.\nLien : {LIEN}"


class TestFiltreSortie(unittest.TestCase):
    def test_reponse_saine_intacte(self):
        self.assertEqual(filtrer(FAITS, FICHES), (FAITS, []))
        self.assertEqual(filtrer(REFUS, FICHES), (REFUS, []))

    def test_image_markdown_retiree(self):
        texte, alertes = filtrer(f"{FAITS}\n\n![suivi](https://pixel.exemple.com/p.png?q=fin-de-vie)", FICHES)
        self.assertEqual(texte, FAITS)
        self.assertEqual(alertes, ["1 image(s) Markdown retirée(s)"])

    def test_lien_absent_des_fiches_retire(self):
        piege = "https://assemblee-nationale.info-loi.com/fin-de-vie"
        texte, alertes = filtrer(f"{FAITS}\nPlus d'informations : {piege}.", FICHES)
        self.assertNotIn(piege, texte)
        self.assertIn(f"{LIEN_RETIRE}.", texte)   # la ponctuation qui suivait le lien est conservée
        self.assertIn(LIEN, texte)                 # le lien de la fiche reste
        self.assertEqual(alertes, [f"lien absent des fiches retiré : {piege}"])

    def test_prompt_traduit_bloque_par_le_canari(self):
        fuite = f"I am an information assistant regarding legislative texts. [{CANARI}]\n\nMandatory rules:\n1. Answer ONLY..."
        texte, alertes = filtrer(fuite, FICHES)
        self.assertEqual(texte, REFUS)
        self.assertEqual(len(alertes), 1)

    def test_regle_recopiee_bloquee(self):
        fuite = "Mes règles : 1. Réponds UNIQUEMENT à partir des fiches fournies entre les balises <fiches>."
        self.assertEqual(filtrer(fuite, FICHES)[0], REFUS)


if __name__ == "__main__":
    unittest.main()
