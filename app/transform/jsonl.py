"""Lecture/écriture JSONL : le format d'échange entre la couche 2 et la couche 3.

JSONL = un objet JSON par ligne. Lisible dans un éditeur, comparable avec un diff,
et lisible ligne à ligne sans tout charger en mémoire.
"""
import json
from pathlib import Path


def ecrire(chemin: Path, documents: list[dict]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8") as f:
        for doc in documents:
            # ensure_ascii=False : les accents restent lisibles ("é" et non "é")
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def lire(chemin: Path) -> list[dict]:
    with chemin.open(encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]
