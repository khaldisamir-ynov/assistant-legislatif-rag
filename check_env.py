"""Vérifie que l'environnement de l'étape 0 est prêt.

Lancer depuis la racine du projet, venv activé :  python check_env.py
"""
import sys
from importlib.metadata import version, PackageNotFoundError

ok = True

# 1. Version de Python
print(f"Python      : {sys.version.split()[0]}  ({sys.executable})")
if sys.version_info[:2] != (3, 12):
    print("  /!\\ Python 3.12 attendu")
    ok = False
if ".venv" not in sys.executable:
    print("  /!\\ Le venv ne semble pas activé")
    ok = False

# 2. Bibliothèques installées (nom du paquet pip)
for paquet in ["fastapi", "uvicorn", "pydantic", "chromadb",
               "onnxruntime", "tokenizers", "openai", "python-dotenv", "requests"]:
    try:
        print(f"{paquet:<22}: {version(paquet)}")
    except PackageNotFoundError:
        print(f"{paquet:<22}: MANQUANT")
        ok = False

# 3. Configuration lue depuis .env (on n'affiche jamais le secret en entier)
from app import config

cle = config.LLM_API_KEY
print(f"\nLLM_BASE_URL    : {config.LLM_BASE_URL}")
print(f"LLM_API_KEY     : {cle[:5] + '...' if cle else 'ABSENTE'}")
print(f"LLM_MODEL       : {config.LLM_MODEL or '(vide, à choisir étape 6)'}")
print(f"EMBEDDING_MODEL : {config.EMBEDDING_MODEL}")
if not cle or cle.startswith("xxx"):
    print("  /!\\ Clé absente ou encore égale à la valeur d'exemple de .env.example")
    ok = False

print("\nOK, environnement prêt" if ok else "\nÀ corriger avant l'étape 1")
