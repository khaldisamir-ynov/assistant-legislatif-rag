"""Tests du contrôle qualité : chaque panne connue doit être détectée, au bon niveau.

Lancer :  python -m unittest discover tests -v

Les fiches sont fabriquées ici (pas de dépendance à data/) : les tests passent
sur n'importe quelle machine, sans téléchargement.
"""
import copy
import unittest
from datetime import date

from app.qualite import ALERTE, BLOQUANT, controler, statistiques

AUJOURD_HUI = date(2026, 10, 14)


def fiche(numero: int, statut: str = "en_cours", depot: int = 20260901, promulgation: int = 0) -> dict:
    url = f"https://www.assemblee-nationale.fr/dyn/17/dossiers/dossier_{numero}"
    return {
        "id": f"DLR5L17N{numero}",
        "texte": f"Dossier législatif : Texte {numero}\nStatut : {statut}\nLien : {url}",
        "texte_recherche": f"Dossier législatif : Texte {numero}",
        "metadonnees": {"titre": f"Texte {numero}", "statut": statut, "url": url,
                        "date_depot_int": depot, "date_depot_an_int": 0,
                        "date_derniere_etape_int": promulgation or 20261010,
                        "date_promulgation_int": promulgation},
    }


def lot_sain() -> list[dict]:
    """1 200 fiches dont 60 lois promulguées récemment (au-dessus du volume minimal de 1 000)."""
    return ([fiche(i) for i in range(1140)]
            + [fiche(i, "promulgue", promulgation=20260920) for i in range(1140, 1200)])


def reference_de(fiches: list[dict]) -> dict:
    return {"date": "2026-10-13", "statistiques": statistiques(fiches, 1500),
            "statuts": {f["id"]: f["metadonnees"]["statut"] for f in fiches}}


class TestQualite(unittest.TestCase):
    def echecs(self, fiches, reference=None, nb_bruts=1500, aujourd_hui=AUJOURD_HUI) -> dict[str, str]:
        """{nom du contrôle en échec: niveau}"""
        return {c.nom: c.niveau for c in controler(fiches, nb_bruts, reference, aujourd_hui) if not c.ok}

    def test_lot_sain_sans_reference(self):
        self.assertEqual(self.echecs(lot_sain()), {})

    def test_lot_sain_identique_a_la_reference(self):
        lot = lot_sain()
        self.assertEqual(self.echecs(lot, reference_de(lot)), {})

    def test_champ_manquant_bloque(self):
        lot = lot_sain()
        del lot[0]["metadonnees"]["url"]
        self.assertEqual(self.echecs(lot), {"Schéma des fiches": BLOQUANT})

    def test_type_incorrect_bloque(self):
        lot = lot_sain()
        lot[0]["metadonnees"]["date_depot_int"] = "2026-09-01"
        self.assertIn("Schéma des fiches", self.echecs(lot))

    def test_identifiant_en_double_bloque(self):
        lot = lot_sain() + [fiche(0)]
        self.assertEqual(self.echecs(lot)["Identifiants uniques"], BLOQUANT)

    def test_statut_inconnu_bloque(self):
        lot = lot_sain()
        lot[0]["metadonnees"]["statut"] = "suspendu"
        self.assertEqual(self.echecs(lot)["Statut connu"], BLOQUANT)

    def test_date_impossible_ou_future_bloque(self):
        for valeur in (20261332, 20270101):
            lot = lot_sain()
            lot[0]["metadonnees"]["date_depot_int"] = valeur
            self.assertEqual(self.echecs(lot)["Dates valides et non futures"], BLOQUANT, valeur)

    def test_date_optionnelle_a_zero_acceptee(self):
        lot = lot_sain()  # date_depot_an_int et date_promulgation_int valent 0 sur les fiches en cours
        self.assertNotIn("Dates valides et non futures", self.echecs(lot))

    def test_chronologie_inversee_bloque(self):
        lot = lot_sain()
        lot[0]["metadonnees"]["date_depot_int"] = 20261012  # après la dernière étape (10/10)
        self.assertIn("Chronologie (dépôt ≤ dernière étape, dépôt ≤ promulgation)", self.echecs(lot))

    def test_promulgue_sans_date_bloque(self):
        lot = lot_sain()
        lot[0]["metadonnees"]["statut"] = "promulgue"
        self.assertEqual(self.echecs(lot)["Promulgué ⇔ date de promulgation"], BLOQUANT)

    def test_lien_absent_de_la_fiche_bloque(self):
        lot = lot_sain()
        lot[0]["texte"] = lot[0]["texte"].replace("Lien :", "Voir :")
        self.assertIn("URL bien formée et présente dans la fiche", self.echecs(lot))

    def test_none_dans_le_texte_bloque(self):
        lot = lot_sain()
        lot[0]["texte"] += "\nLoi promulguée (n° None)"
        self.assertEqual(self.echecs(lot)["Aucune valeur « None » dans le texte"], BLOQUANT)

    def test_texte_vectorise_trop_long_alerte(self):
        lot = lot_sain()
        lot[0]["texte_recherche"] = "x" * 2000
        self.assertEqual(self.echecs(lot), {"Texte vectorisé assez court": ALERTE})

    def test_volume_trop_faible_au_premier_lancement_bloque(self):
        self.assertEqual(self.echecs(lot_sain()[:500], nb_bruts=650)["Volume minimal (pas encore de référence)"],
                         BLOQUANT)

    def test_chute_du_volume_bloque(self):
        lot = lot_sain()
        echecs = self.echecs(lot[:1000], reference_de(lot), nb_bruts=1250)
        self.assertEqual(echecs["Pas de chute du volume"], BLOQUANT)
        self.assertEqual(echecs["Aucun dossier disparu"], ALERTE)

    def test_hausse_brutale_alerte(self):
        lot = lot_sain()
        plus = lot + [fiche(i) for i in range(2000, 2200)]
        self.assertEqual(self.echecs(plus, reference_de(lot), nb_bruts=1750),
                         {"Pas de hausse brutale du volume": ALERTE})

    def test_statut_definitif_qui_recule_alerte(self):
        hier = lot_sain()
        hier[5] = fiche(5, "retire")
        reference = reference_de(hier)
        lot = lot_sain()  # aujourd'hui, le dossier 5 est de nouveau « en cours »
        self.assertEqual(self.echecs(lot, reference), {"Aucun statut définitif qui recule": ALERTE})

    def test_repartition_des_statuts_alerte(self):
        lot = lot_sain()
        reference = reference_de(lot)
        for i in range(100):
            lot[i] = fiche(i, "rejete")
        self.assertEqual(self.echecs(lot, reference), {"Répartition des statuts stable": ALERTE})

    def test_source_figee_alerte(self):
        self.assertEqual(self.echecs(lot_sain(), aujourd_hui=date(2026, 11, 14)),
                         {"Fraîcheur de la source": ALERTE})

    def test_part_des_dossiers_retenus_alerte(self):
        self.assertEqual(self.echecs(lot_sain(), nb_bruts=1250),  # 96 % : le filtre « loi » ne filtre plus
                         {"Part des dossiers retenus comme lois": ALERTE})

    def test_aucune_promulgation_recente_alerte(self):
        lot = [fiche(i) for i in range(1200)]
        self.assertEqual(self.echecs(lot),
                         {"Question cible « lois promulguées récemment » : données sur 90 j": ALERTE})

    def test_le_controle_ne_modifie_pas_les_fiches(self):
        lot = lot_sain()
        copie = copy.deepcopy(lot)
        controler(lot, 1500, reference_de(lot), AUJOURD_HUI)
        self.assertEqual(lot, copie)


if __name__ == "__main__":
    unittest.main()
