# Roadmap : assistant législatif (RAG, 17e législature)

Principe : **mesurer d'abord, renforcer ensuite, étendre enfin.** Chaque phase s'appuie sur la précédente, sauf le déploiement (phase 3), qui peut démarrer tout de suite.

## ✅ Réalisé : le POC

| Domaine | Ce qui existe |
|---|---|
| Données | Pipeline nocturne en 3 couches : extraire (open data AN) → transformer (fiches JSONL) → **contrôler** (qualité, blocage si données cassées) → stocker (ChromaDB) |
| Recherche | Embeddings e5 en ONNX, filtres de date et de statut par regex, tri par date pour « récemment », sigles PLF/PLFSS développés |
| Réponse | Prompt à 7 règles (fiches seules, « Je ne sais pas », liens, neutralité), Mistral `ministral-14b-latest`, sources construites par le code |
| Confiance | Indicateur d'ancrage : lien, date ou n° de loi absent des fiches = inventé |
| Interfaces | API FastAPI (`/ask`, `/feedback`, `/health`), chat Chainlit avec avis 👍/👎 |
| Suivi | Journal des questions en production, `analyse_logs.py` |
| Évaluation | 14 questions générales + 16 questions orientées (neutralité, paires miroir), tests unitaires |
| Livraison | Image Docker unique (API, Chainlit, pipeline), 2,73 Go, clé et données hors image |

## Phase 1 : Mesurer (socle de tout le reste)

| # | Travail | Livrable |
|---|---|---|
| 1.1 ✅ | **Base de test de référence** : pour chaque question, la source, les faits et le comportement attendus (réponse, refus, neutralité) | `cas_evaluation.json`, lu par `evaluate.py` |
| 1.2 | Enrichir la base avec les questions 👎 et les échecs du journal | Cas ajoutés en 1.1 |
| 1.3 | Vérifier le statut déduit sur un échantillon de dossiers réels ; lister les questions sans réponse possible (texte de loi, auteurs) | Tableau de vérification |
| 1.4 | Documenter les ratés du retriever (mauvais dossier, voisin parasite, filtre manqué). 1er raté connu : « troubles à l'ordre public » ramène le droit de grève ; la loi promulguée DLR5L17N53980 est 7e (score 0,820 contre 0,823 pour le 1er), et le LLM répond qu'« aucune proposition n'a abouti » | Rapport de ratés, qui alimente 4.2 |

## Phase 2 : Renforcer

| # | Travail | Livrable |
|---|---|---|
| 2.1 | Confiance : une date citée doit correspondre à la bonne étape, pas seulement figurer dans les fiches | `app/confiance.py` |
| 2.2 | Neutralité : suivre les échecs instables et les biais par omission | `evaluate.py` |
| 2.3 | Journal : durée de conservation, rotation du fichier (RGPD) | `app/journal.py` |
| 2.4 | Ingestion sans coupure : la base n'est plus vide pendant ~2 min | Bascule entre deux collections |
| 2.5 | Latence perçue (10–17 s, LLM ≈ 99 %) | Streaming de la réponse |

## Phase 3 : Déployer (démarrable dès maintenant)

| # | Travail | Livrable |
|---|---|---|
| 3.1 | Publier l'image Docker sur Azure : API, Chainlit, pipeline planifié | Service en ligne, clé en secret, données en volume |

## Phase 4 : Étendre

| # | Travail | Dépend de |
|---|---|---|
| 4.1 | Ajouter une 2e source (Sénat ou Légifrance) et mesurer si le bon document remonte mieux | 1.1, 1.3 |
| 4.2 | Reformuler la question avant l'embedding (orthographe, « sécu », synonymes) | 1.4 |
| 4.3 | LLM juge : fidélité aux fiches, exactitude, neutralité, en plus des contrôles automatiques | 1.1, 2.2 |
| 4.4 | Routage multi-LLM : comparer modèles sur coût et qualité | 1.1, 4.3 |

## Hors périmètre pour l'instant

Pistes déjà explorées, mises de côté (branche `perspective-textes-integraux`) :
- **Texte intégral des lois** : ~58 000 extraits, ~3 h 45 d'embeddings. Pour reprendre : 3 derniers mois seulement (~18 min).
- **Agenda de l'AN** : 70 % des réunions sans ordre du jour structuré.
- **Agent à outils** : fonctionne, mais les dates doivent être calculées par le code, pas par le LLM.
