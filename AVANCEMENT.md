# Assistant législatif : avancement du POC RAG

*Mis à jour le 13/10/2026*

## Étapes

| # | Étape | État | Fichiers |
|---|---|---|---|
| 0 | Environnement (venv, dépendances, `.env`) | ✅ | `requirements.txt`, `.env.example`, `.gitignore`, `app/config.py`, `check_env.py` |
| 1 | Exploration des données AN | ✅ | `app/an_data.py`, `explore.py` |
| 2 | Fiches texte + métadonnées | ✅ | `app/fiches.py` |
| 3 | Embeddings (e5, préfixes, cosinus) | ✅ | `app/embeddings.py`, `demo_embeddings.py` |
| 4 | Chargement ChromaDB | ✅ | `ingest.py`, `demo_chroma.py` |
| 5 | Retriever + filtres temporels | ✅ | `app/filters.py`, `app/retriever.py` |
| 6 | Prompt RAG + LLM (Mistral `ministral-14b-latest`) | ✅ | `app/prompt.py`, `app/llm_client.py`, `app/rag.py` |
| 7 | API FastAPI `/ask` | ✅ | `app/main.py` |
| 8 | Évaluation | ✅ | `evaluate.py` |

## Ce que les données contiennent vraiment

- 3 252 dossiers, dont 2 496 retenus (lois uniquement : résolutions, rapports, missions et motions sont exclus).
- Le ZIP « 17e législature » contient aussi 196 dossiers plus anciens, toujours actifs. On les garde.
- Pas de champ statut : il est **déduit** des actes (promulgué / adopté / rejeté / retiré / en cours).
- Pas de champ URL : il est construit à partir de `titreChemin`, ou de `uid` si `titreChemin` vaut null, toujours sous `/dyn/17/` (vérifié).
- Pas de texte de loi ni d'auteurs lisibles (les auteurs ne sont que des références `PA…`).

## Sources de données

| Source | Producteur | Type | Usage |
|---|---|---|---|
| [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr) | Assemblée nationale | Fichiers ZIP (JSON/XML), pas une API | ✅ source du POC (dossiers législatifs, 17e législature) |
| [data.senat.fr](https://data.senat.fr) | Sénat | Fichiers et bases | Piste : parcours des textes côté Sénat |
| API Légifrance (portail PISTE) | DILA (État) | Vraie API, inscription et clé | Piste : texte des lois promulguées |
| [data.gouv.fr](https://www.data.gouv.fr) | Etalab (État) | Catalogue national | Référence ces jeux de données |

Téléchargement en masse, sans interrogation à la demande : d'où l'ingestion nocturne.
Licence : probablement Licence Ouverte (Etalab), **non vérifiée** : à confirmer sur la page « conditions de réutilisation » du portail AN.

## Problèmes rencontrés et solutions

| Problème | Cause | Solution |
|---|---|---|
| `check_env` : venv non actif | Paquets installés dans Anaconda `base` | `conda deactivate` puis création de `.venv` |
| Clé API non prise en compte | `.env` non enregistré | Ctrl+S ; `check_env` détecte maintenant la valeur d'exemple |
| `acteLegislatif` tantôt dict, tantôt liste | Conversion XML → JSON | Fonction `en_liste()` |
| ~48 % des actes sans date | Actes « conteneurs » (ex. 1ère lecture) | Seules les feuilles datées sont gardées |
| 150 actes datés dans le futur | Séances programmées | Exclus du statut, affichés en « prochaine étape » |
| Faux statut « adopté » sur 3 vieux textes | « Sans modification » voté en 1re chambre | Ne compte que s'il est voté dans la 2e chambre |
| Date de dépôt fausse (PLFSS 2027) | Rapporteur nommé avant le dépôt | Recherche du 1er acte `-DEPOT` (`premier_depot()`) |
| Votes CMP attribués à la « CMP » | Codes `CMP-DEBATS-AN/SN` | Attribués à la bonne chambre |
| « Sécu » ne retrouve pas le PLFSS | Les étapes clés diluent le thème | On vectorise titre + type + statut, on stocke la fiche complète |
| 2 fiches > 512 tokens | Longues listes d'étapes | Même solution |
| « Récemment » ignoré (lois de 2025 en tête) | Le vecteur ne contient pas le temps | Filtres par regex + tri par date (`get()`) pour les listes |
| Filtre statut sur « a-t-il été voté ? » | Cacherait les textes non votés | Statut filtré seulement pour les questions-listes |
| Mistral : 429 sur `mistral-small-latest` | Limite de débit du compte | Modèle `ministral-14b-latest` |
| LLM présente 5 lois comme une liste complète | Il ignore qu'on lui en donne 5 au max | Prompt : « liste non exhaustive » |
| LLM parle des « Fiche 4 et 5 » | Vocabulaire interne du prompt | Consigne : ne jamais mentionner les fiches |
| JSON « error parsing the body » avec curl Windows | Accents non encodés en UTF-8 | Tester via Swagger ou forcer `charset=utf-8` |
| Lien 404 pour le dossier de la 8e législature | URL construite avec `/dyn/8/` | Toujours `/dyn/17/` (le site y redirige les anciens dossiers) ; réingestion |
| Site AN : 503 par intermittence | Protection anti-robots | Requêtes espacées ; aucun impact pour un utilisateur humain |
| Sources hors sujet sur « je ne sais pas » | Il y a toujours un plus proche voisin | Sources vidées si la réponse commence par « Je ne sais pas » |
| Avertissement « symlinks » sous Windows | Cache local du modèle d'embeddings | Sans gravité, masqué par `HF_HUB_DISABLE_SYMLINKS_WARNING=1` |

## Évaluation (13/10/2026, `ministral-14b-latest`)

| Question | Retriever | Réponse | Liens | Latence |
|---|---|---|---|---|
| Lois promulguées récemment | ✅ | ✅ | 5/5 | 14 s |
| Où en est le texte sur la fin de vie ? | ✅ | ✅ | 3/5 * | 12 s |
| Textes déposés récemment à l'AN | ✅ | ✅ | 5/5 | 17 s |
| Tarte tatin (hors domaine) | — | ✅ « je ne sais pas » | — | 2 s |
| Article 2 de la loi fin de vie (donnée absente) | — | ✅ « je ne sais pas » | — | 1 s |

\* les 2 sources non citées étaient hors sujet (ex. peine de mort), ignorées à juste titre.
Hors grille : « La loi fin de vie est-elle une bonne loi ? » → pas d'opinion (neutralité respectée).
Latence : retriever < 0,2 s ; le LLM représente ~99 % du temps.

## Limites du POC

| Domaine | Limite | Piste d'amélioration |
|---|---|---|
| Données | Pas de texte des lois, pas d'auteurs, agenda partiel | Ajouter Légifrance (avec chunking) et le référentiel des acteurs AN |
| Données | Statut déduit par heuristique (seulement 4 « adopté ») | Comparer à un échantillon vérifié à la main |
| Filtres | Regex : « l'été dernier », « depuis mars » non compris ; « récemment » = 90 j (arbitraire) | Extraction des filtres par le LLM (sortie JSON) |
| Filtres | 5 résultats max : listes jamais exhaustives | Paramètre `n` ou lien vers une liste complète |
| Recherche | Scores tassés (0,73–0,82) : pas de seuil anti hors-sujet ; voisins parasites (« peine de mort » pour « fin de vie ») | Le LLM fait office de garde-fou |
| LLM | Latence 10–17 s (~99 % du temps total) | Réponses plus courtes, streaming, modèle plus petit |
| LLM | Lien pas toujours cité ; incohérences (« deux textes » puis trois) ; **dates mélangées** (Conseil constitutionnel daté du 30/06 au lieu du 14/08) | Sources jointes par le code ; relecture ; modèle plus grand |
| LLM | Quota Mistral (429), dépendance à un service externe | Bascule vers un modèle auto-hébergé (vLLM, Ollama) : seul `.env` change |
| Évaluation | 5 questions ; « lien présent » ≠ réponse juste ; neutralité testée sur 1 seul cas | Jeu de 30–50 questions avec réponses de référence |
| Exploitation | Base vide ~2 min pendant l'ingestion nocturne | `upsert` ou bascule entre deux collections |

## Actions en attente

- Aucune (clé Mistral régénérée le 13/10/2026).
