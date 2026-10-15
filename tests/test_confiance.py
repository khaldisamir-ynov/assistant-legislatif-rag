"""Refus ou réponse hybride : une réponse qui commence par « Je ne sais pas » mais cite des liens n'est pas un refus."""
import unittest

from app.confiance import est_un_refus

REFUS = "Je ne sais pas : cette information n'est pas dans les dossiers législatifs dont je dispose."


class TestRefus(unittest.TestCase):
    def test_refus(self):
        self.assertTrue(est_un_refus(REFUS))
        self.assertFalse(est_un_refus(REFUS + "\n\nLe PLFSS 2027 est en cours d'examen. "
                                      "Lien : https://www.assemblee-nationale.fr/dyn/17/dossiers/PLFSS_2027"))
        self.assertFalse(est_un_refus("La loi a été promulguée le 18/08/2026."))


if __name__ == "__main__":
    unittest.main()
