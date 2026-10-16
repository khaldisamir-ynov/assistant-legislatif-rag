"""Comparaison des fiches retrouvées à la base de test de référence (sans LLM ni base vectorielle)."""
import unittest
from datetime import date

from evaluate import CAS, metriques, verifier_retriever

AUJOURD_HUI = date(2026, 10, 15)


def fiche(id_: str, statut: str = "promulgue", promulgation: int = 20260901) -> dict:
    return {"id": id_, "metadonnees": {"statut": statut, "date_promulgation_int": promulgation}}


LISTE = {"liste": {"statuts": ["promulgue"], "champ_date": "date_promulgation_int", "jours": 90}}


class TestReference(unittest.TestCase):
    def test_source_en_premiere_position(self):
        cas = {"source": "A"}
        self.assertTrue(verifier_retriever(cas, [fiche("A"), fiche("B")]))
        self.assertFalse(verifier_retriever(cas, [fiche("B"), fiche("A")]))
        self.assertFalse(verifier_retriever(cas, []))

    def test_question_liste(self):
        ok = [fiche("A", promulgation=20260920), fiche("B", promulgation=20260901)]
        self.assertTrue(verifier_retriever(LISTE, ok, AUJOURD_HUI))
        self.assertFalse(verifier_retriever(LISTE, ok[::-1], AUJOURD_HUI))                    # mal triée
        self.assertFalse(verifier_retriever(LISTE, [fiche("A", promulgation=20250101)], AUJOURD_HUI))  # trop ancienne
        self.assertFalse(verifier_retriever(LISTE, [fiche("A", statut="en_cours")], AUJOURD_HUI))
        self.assertFalse(verifier_retriever(LISTE, [], AUJOURD_HUI))

    def test_rien_a_retrouver(self):
        self.assertIsNone(verifier_retriever({"type": "hors périmètre"}, [fiche("A")]))

    def test_metriques(self):
        resultats = [
            {"type": "cible", "retriever_ok": True, "reponse_ok": True, "lien_ok": True, "latence_totale_s": 2.0},
            {"type": "cible", "retriever_ok": False, "reponse_ok": True, "lien_ok": False, "latence_totale_s": 4.0},
            {"type": "neutralité", "retriever_ok": None, "reponse_ok": True, "lien_ok": None, "latence_totale_s": 1.0},
            {"type": "cible", "erreur": "LLM injoignable"},
        ]
        m = metriques(resultats, [{"ok": True}, {"ok": False}])
        self.assertEqual(m["taux_reussite"], 2 / 4)       # l'erreur LLM compte comme un échec
        self.assertEqual(m["taux_retriever"], 1 / 2)      # None = contrôle non applicable, ignoré
        self.assertEqual(m["taux_lien_attendu"], 1 / 2)
        self.assertEqual(m["taux_neutralite"], 1.0)
        self.assertEqual(m["taux_paires_miroir"], 0.5)
        self.assertEqual(m["erreurs_llm"], 1)
        self.assertEqual(m["latence_mediane_s"], 2.0)
        self.assertNotIn("taux_paires_miroir", metriques(resultats, []))  # rien à mesurer : pas de métrique
        self.assertNotIn("tokens_entree", m)  # aucun résultat ne porte de tokens

    def test_tokens(self):
        resultats = [
            {"type": "cible", "retriever_ok": True, "reponse_ok": True, "lien_ok": True, "latence_totale_s": 1.0,
             "tokens": {"entree": 3000, "sortie": 200}},
            {"type": "cible", "retriever_ok": True, "reponse_ok": True, "lien_ok": True, "latence_totale_s": 1.0,
             "tokens": {"entree": 1000, "sortie": 101}},
            {"type": "cible", "retriever_ok": True, "reponse_ok": True, "lien_ok": True, "latence_totale_s": 1.0,
             "tokens": None},  # fournisseur sans `usage` : ignoré
        ]
        m = metriques(resultats, [])
        self.assertEqual((m["tokens_entree"], m["tokens_sortie"]), (4000, 301))
        self.assertEqual((m["tokens_moyens_entree"], m["tokens_moyens_sortie"]), (2000, 150))

    def test_fichier_de_cas(self):
        types = {"cible", "hors périmètre", "aucun résultat", "sécurité", "neutralité"}
        for cas in CAS:
            self.assertIn(cas["type"], types, cas["question"])
            self.assertTrue(cas["attendu"], cas["question"])
        paires = [c["paire"] for c in CAS if "paire" in c]
        self.assertTrue(all(paires.count(p) == 2 for p in paires))


if __name__ == "__main__":
    unittest.main()
