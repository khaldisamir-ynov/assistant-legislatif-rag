# Image unique de l'assistant législatif : la MÊME image sert trois usages,
# seule la commande change (principe "build once, run anywhere") :
#   API FastAPI (défaut) : docker run ... assistant-legislatif
#   Interface Chainlit   : docker run --no-healthcheck ... assistant-legislatif chainlit run chainlit_app.py --host 0.0.0.0 --port 8001 --headless
#   Pipeline de données  : docker run --no-healthcheck ... assistant-legislatif python pipeline.py
# (--no-healthcheck : la sonde ci-dessous interroge l'API sur le port 8000, absente de ces deux usages)
#
# Contenu de l'image : code + dépendances + modèle d'embeddings.
# PAS dans l'image : la clé API (fournie au lancement) et les données (volume),
# qui changent sans que le code change.

FROM python:3.12-slim

# Python : pas de fichiers .pyc, logs affichés immédiatement (sinon retardés par le tampon)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# 1. Dépendances AVANT le code : Docker met chaque étape en cache. Tant que
#    requirements.txt ne change pas, modifier le code ne réinstalle rien.
#    torch en version CPU : la version par défaut sous Linux embarque CUDA (~4 Go inutiles ici).
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r requirements.txt

# 2. Modèle d'embeddings téléchargé AU BUILD (~1 Go) : le conteneur démarre sans
#    réseau vers Hugging Face, toujours avec la même version du modèle.
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-base
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"
ENV HF_HUB_OFFLINE=1

# 3. Le code, en dernier : c'est ce qui change le plus souvent
COPY . .

# Utilisateur non-root : si l'application est compromise, l'attaquant n'est pas root.
# Les dossiers de données lui appartiennent (les volumes nommés héritent de ces droits).
RUN useradd --create-home app \
 && mkdir -p data chroma_db .files \
 && chown -R app:app /app
USER app

EXPOSE 8000 8001

# Docker vérifie toutes les 30 s que l'API répond (python plutôt que curl, absent de l'image slim)
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
