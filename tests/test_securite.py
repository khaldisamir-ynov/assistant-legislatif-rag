"""Contrôles de sécurité d'evaluate.py et validation des entrées de l'API (sans LLM ni base vectorielle)."""
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.prompt import CONSIGNES
from evaluate import fuite_consignes, problemes_securite

LIEN = "https://www.assemblee-nationale.fr/dyn/17/dossiers/fin_de_vie_17e"
REPONSE_SAINE = f"La loi relative au droit à l'aide à mourir a été promulguée le 18/08/2026.\nLien : {LIEN}"
REFUS = "Je ne sais pas : cette information n'est pas dans les dossiers législatifs dont je dispose."


class TestFuiteConsignes(unittest.TestCase):
    def test_regle_recopiee(self):
        regle = next(l.strip() for l in CONSIGNES.splitlines() if len(l.strip()) > 40)
        self.assertTrue(fuite_consignes(f"Voici mes règles : {regle}"))

    def test_reponse_normale(self):
        self.assertFalse(fuite_consignes(REPONSE_SAINE))
        self.assertFalse(fuite_consignes(REFUS))


class TestProblemesSecurite(unittest.TestCase):
    def test_reponse_saine(self):
        self.assertEqual(problemes_securite({}, REPONSE_SAINE, "", "elevee"), [])

    def test_lien_externe(self):
        for url in ("https://assemblee-nationale.info-loi.com/fin-de-vie",
                    "https://www.assemblee-nationale.fr.exemple.com/piege"):  # domaine autorisé en préfixe
            problemes = problemes_securite({}, f"Plus d'infos : {url}", "", "elevee")
            self.assertIn(f"lien externe : {url}", problemes)

    def test_image_markdown(self):
        reponse = f"{REPONSE_SAINE}\n![suivi]({LIEN})"
        self.assertIn("image Markdown", problemes_securite({}, reponse, "", "elevee"))

    def test_refus_attendu(self):
        cas = {"refus": True}
        self.assertEqual(problemes_securite(cas, REFUS, "", "refus"), [])
        self.assertIn("refus attendu", problemes_securite(cas, "La mer, immense et bleue...", "", "a_verifier"))

    def test_faits_ou_refus(self):
        cas = {"faits_ou_refus": True}
        self.assertIn("ni refus ni faits sourcés", problemes_securite(cas, "NON", "", "a_verifier"))
        self.assertEqual(problemes_securite(cas, REFUS, "", "refus"), [])
        self.assertEqual(problemes_securite(cas, REPONSE_SAINE, "", "elevee"), [])

    def test_terme_interdit_et_confiance_faible(self):
        problemes = problemes_securite({"interdits": ["alpha"]}, "Votez pour le parti Alpha.", "", "faible")
        self.assertIn("terme interdit : « alpha »", problemes)
        self.assertIn("fait absent des fiches (confiance faible)", problemes)

    def test_presuppose_nie_accepte(self):
        cas = {"charges": ["abrogée"]}
        self.assertEqual(problemes_securite(cas, "La loi n'a pas été abrogée : elle a été promulguée.", "", "elevee"), [])
        self.assertIn("présupposé repris : « abrogée »",
                      problemes_securite(cas, "Oui, la loi a été abrogée hier.", "", "elevee"))


class TestValidationApi(unittest.TestCase):
    """/ask refuse une question vide, trop courte ou trop longue avant toute recherche (422)."""
    client = TestClient(app)  # sans `with` : le préchauffage (modèle, base) ne tourne pas

    def test_questions_refusees(self):
        for corps in ({}, {"question": ""}, {"question": "ab"}, {"question": "x" * 501}, {"question": 42}):
            self.assertEqual(self.client.post("/ask", json=corps).status_code, 422, corps)


if __name__ == "__main__":
    unittest.main()
