"""Lecture du verdict du LLM juge et métriques associées (sans appel au LLM)."""
import unittest

from app.juge import lire_verdict
from evaluate import metriques


class TestJuge(unittest.TestCase):
    def test_verdict_entoure_de_balises(self):
        texte = '```json\n{"fidele": false, "pertinente": true, "neutre": true, "justification": "date fausse"}\n```'
        self.assertEqual(lire_verdict(texte),
                         {"fidele": False, "pertinente": True, "neutre": True, "justification": "date fausse"})

    def test_verdict_illisible_ou_incomplet(self):
        self.assertIsNone(lire_verdict("Je pense que la réponse est fidèle."))
        self.assertIsNone(lire_verdict('{"fidele": true, "pertinente": true'))          # JSON coupé
        self.assertIsNone(lire_verdict('{"fidele": "oui", "pertinente": true, "neutre": true}'))  # pas un booléen
        self.assertIsNone(lire_verdict('{"fidele": true, "neutre": true}'))             # critère manquant

    def test_metriques_du_juge(self):
        base = {"type": "cible", "retriever_ok": True, "reponse_ok": True, "lien_ok": True, "latence_totale_s": 1.0}
        resultats = [
            {**base, "juge": {"fidele": True, "pertinente": True, "neutre": True, "tokens": {"entree": 900, "sortie": 50}}},
            {**base, "juge": {"fidele": False, "pertinente": True, "neutre": True, "tokens": {"entree": 1000, "sortie": 50}}},
            {**base, "juge": {"erreur": "LLM indisponible (429)"}},
        ]
        m = metriques(resultats, [])
        self.assertEqual(m["taux_juge_fidele"], 0.5)      # l'erreur du juge n'est pas comptée comme un échec
        self.assertEqual(m["taux_juge_neutre"], 1.0)
        self.assertEqual(m["erreurs_juge"], 1)
        self.assertEqual(m["tokens_juge"], 2000)
        self.assertEqual(m["taux_reussite"], 1.0)         # le juge ne change pas le score d'evaluate.py
        self.assertNotIn("erreurs_juge", metriques([base], []))  # sans --juge : aucune métrique du juge


if __name__ == "__main__":
    unittest.main()
