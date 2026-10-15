"""Comparaison des fiches retrouvées à la base de test de référence (sans LLM ni base vectorielle)."""
import unittest
from datetime import date

from evaluate import CAS, verifier_retriever

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

    def test_fichier_de_cas(self):
        types = {"cible", "hors périmètre", "aucun résultat", "sécurité", "neutralité"}
        for cas in CAS:
            self.assertIn(cas["type"], types, cas["question"])
            self.assertTrue(cas["attendu"], cas["question"])
        paires = [c["paire"] for c in CAS if "paire" in c]
        self.assertTrue(all(paires.count(p) == 2 for p in paires))


if __name__ == "__main__":
    unittest.main()
