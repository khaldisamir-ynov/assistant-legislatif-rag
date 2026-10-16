# Roadmap : assistant législatif (RAG, 17e législature)

Suit les itérations 6 à 9 du sujet. **Ordre conseillé : 8 → 6 → 7 → 9.** MLflow (8) vient en premier parce qu'il mesure l'effet des optimisations (6) et fournit la latence et les tokens nécessaires au budget (9).

## ✅ Réalisé

| Domaine | Ce qui existe |
|---|---|
| Données | Pipeline nocturne : extraire (open data AN) → transformer (fiches JSONL) → **contrôler** (qualité, blocage si données cassées) → stocker (ChromaDB) |
| Recherche | Embeddings e5 en ONNX, filtres de date et de statut par regex, tri par date pour « récemment », sigles PLF/PLFSS développés, `ef_search` HNSW relevé (rappel 0,95 → 0,98) |
| Réponse | Prompt à 7 règles (fiches seules, « Je ne sais pas », liens, neutralité), Qwen3.8-27B via Hugging Face (Academia Hub, facturé à l'école ; Mistral `ministral-14b-latest` avant le 16/10), sources construites par le code |
| Confiance | Indicateur d'ancrage : lien, date ou n° de loi absent des fiches = inventé |
| Interfaces | API FastAPI (`/ask`, `/feedback`, `/health`), chat Chainlit avec avis 👍/👎 |
| Suivi | Journal des questions en production, `analyse_logs.py` ; MLflow : un run par question (« production ») et par évaluation (« evaluation »), avec les hyperparamètres |
| Évaluation | Base de test de référence `cas_evaluation.json` (31 questions : 15 générales, 16 orientées), tests unitaires. Résultat : 29/31 (16/10/2026, Qwen3.8-27B ; 29/31 avec Mistral le 15/10) |
| Livraison | Image Docker unique (API, Chainlit, pipeline), 2,73 Go, clé et données hors image |

## Itération 6 : Optimisation (faire mieux avec moins)

| # | Travail | Mesure avant / après |
|---|---|---|
| 6.1 | **Quantifier le modèle e5 en INT8** (`onnxruntime.quantization`, ou fichier INT8 déjà publié s'il existe), puis ré-indexer | Taille du modèle et de l'image, RAM du conteneur, temps d'embedding, rangs sur `cas_evaluation.json` |
| 6.2 | Streaming de la réponse : moins urgent depuis Qwen via Cerebras (médiane 0,6 s le 16/10, contre 2,1 s et jusqu'à 6,5 s avec Mistral le 15/10) | Temps avant le 1er mot affiché |
| 6.3 | Ingestion sans coupure : la base n'est plus vide pendant ~3 min (bascule entre deux collections) | Requêtes en échec pendant l'ingestion |
| 6.4 | Limite de débit Cerebras (via Hugging Face) : des questions en rafale reçoivent une erreur 429 (jusqu'à 6 sur 31 dans un passage d'`evaluate.py`, 16/10). Attente plus longue entre les tentatives, ou autre fournisseur (suffixe `:fournisseur` de `LLM_MODEL`) | Erreurs 429 par passage d'`evaluate.py` |

Le LLM est hébergé via Hugging Face (Cerebras) : on ne le quantifie pas. Ce serait possible avec un modèle auto-hébergé (Ollama, vLLM), où seul `.env` change.

## Itération 7 : La barrière (sécurité et RGPD)

| # | Travail | Livrable |
|---|---|---|
| 7.1 | **Authentification** : clé API dans un en-tête pour `/ask` et `/feedback` (`/health` reste ouvert à la sonde) ; mot de passe pour Chainlit | `app/main.py`, `chainlit_app.py` |
| 7.2 | **Filtre de données personnelles** : n° de sécu, e-mail, téléphone, IBAN. Question refusée **avant le LLM et avant le journal** | Module de filtre et ses tests |
| 7.3 | Journal : durée de conservation, rotation de `questions.jsonl` | `app/journal.py` |
| 7.4 | Secrets et accès en production : clé LLM en secret Azure, HTTPS, droits minimaux | Configuration du déploiement |

## Itération 8 : Le rétroviseur (MLOps avec MLflow)

| # | Travail | Livrable |
|---|---|---|
| 8.1 ✅ | **Tracking des requêtes de production** : question, latence, confiance, nombre de fiches, filtres, modèles | `app/suivi.py`, expérience « production » |
| 8.2 ✅ | **Chaque lancement d'`evaluate.py` = une expérience** : paramètres (texte vectorisé, `ef_search`, nombre de fiches, LLM, modèle d'embeddings) et métriques (retriever, réponse, neutralité, latence) | `app/suivi.py`, expérience « evaluation » |
| 8.3 ✅ | **1re expérience : vectoriser le titre seul** au lieu de titre + type + statut (cas « Sécu » ajouté d'abord). **Rejeté** (15/10/2026, 31 questions) : retriever 84 % contre 92 %, réussite 26/31 contre 29/31. Sans le statut, la loi promulguée sur les mineurs passe derrière une proposition en cours au titre quasi identique | Runs « evaluation » comparés, paramètre `lignes_vectorisees` (3 conservé) |
| 8.4 | Enrichir la base de test : questions 👎 du journal, statuts déduits vérifiés sur un échantillon | `cas_evaluation.json` |
| 8.5 | Qualité des réponses : confiance date + étape, suivi de la neutralité, éventuellement un LLM juge | Nouvelles métriques suivies |
| 8.6 ✅ | **2e expérience : embeddings calculés par l'API Hugging Face** (plus de modèle local, image ~1,1 Go plus légère). e5-base n'y est pas servi en vecteurs ; e5-large l'est. **Rejeté** (16/10/2026) : 20/31 contre 29/31, paires miroir 3/5 contre 5/5. La fiche « Fin de vie » passe 3e derrière des titres proches | Run « evaluation », e5-base local conservé |

**Livrable du sujet :** un tableau de bord MLflow avec l'historique des requêtes et des métriques.

## Itération 9 : La facture (FinOps et documentation)

| # | Travail | Livrable |
|---|---|---|
| 9.1 ✅ | Mesurer les tokens par question (`usage` renvoyé par l'API) : journal, MLflow (`tokens_entree`, `tokens_sortie`), `evaluate.py`, `analyse_logs.py`. Mesuré le 16/10/2026 (Qwen3.8-27B, 23 réponses) : **~1 700 tokens en entrée + ~170 en sortie par question** | Tokens moyens par question |
| 9.2 | **Estimation budgétaire pour 1 000 utilisateurs par jour** : tokens LLM (Hugging Face Inference Providers, budget de l'école), hébergement Azure (API, Chainlit, pipeline), stockage, MLflow. Hypothèses écrites (questions par utilisateur, pics) | Fichier d'estimation |
| 9.3 ✅ | **`README.md`** : objectif, architecture, installation, lancement, évaluation, limites | `README.md` |
| 9.4 | Optionnel : comparer coût et qualité de plusieurs LLM (MLflow + base de test). **En partie** (16/10/2026) : Mistral `ministral-14b-latest` et Qwen3.8-27B, tous deux à 29/31, latence médiane 2,1 s contre 0,6 s ; reste le coût | Tableau comparatif |

**Livrable final du sujet :** un dépôt Git complet (code, Dockerfile, README.md, estimation budgétaire).

## Transverse : déploiement Azure

Publier l'image Docker déjà construite (API, Chainlit, pipeline planifié). Requis pour 7.4 et pour chiffrer 9.2 sur des coûts réels.

## Hors périmètre pour l'instant

- **Seconde source** (Sénat, Légifrance) et **reformulation des questions** : à reconsidérer si des ratés subsistent après 8.3.
- **Texte intégral des lois** : ~58 000 extraits, ~3 h 45 d'embeddings. Il faudrait découper par article, avec un en-tête de contexte. Pour reprendre : 3 derniers mois seulement (~18 min).
- **Agenda de l'AN** : 70 % des réunions sans ordre du jour structuré.
- **Agent à outils** : fonctionne, mais les dates doivent être calculées par le code, pas par le LLM.
