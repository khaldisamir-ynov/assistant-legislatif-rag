"""Extraction du thème : le jugement porté par la question ne doit pas entrer dans le thème vectorisé.

Lancer :  python -m unittest discover tests -v
"""
import unittest

from app.filters import extraire_filtres


class TestTheme(unittest.TestCase):
    def test_theme(self):
        for question, theme in [
            ("Où en est le texte sur la fin de vie ?", "la fin de vie"),
            ("La loi sur la fin de vie est une avancée historique : où en est-elle ?", "la fin de vie"),
            ("La loi sur la fin de vie est une dérive dangereuse : où en est-elle ?", "la fin de vie"),
            ("La loi sur la fin de vie a-t-elle été promulguée ?", "la fin de vie"),
            ("Cette loi liberticide sur les réseaux sociaux et les mineurs a-t-elle été promulguée ?",
             "les réseaux sociaux et les mineurs"),
            ("Le texte qui protège enfin les Français contre les troubles à l'ordre public, où en est-il ?",
             "les troubles à l'ordre public"),
            ("c koi la loi sur la fin de vie ki a été voté ?", "la fin de vie"),
            ("Où en est le projet de loi de finances pour 2027 ?", None),
        ]:
            self.assertEqual(extraire_filtres(question).theme, theme, question)


if __name__ == "__main__":
    unittest.main()
