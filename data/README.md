# data/

Répertoire de travail local du collector (ignoré par Git) :

| Dossier | Contenu | En production |
|---|---|---|
| `data/state/` | état persistant : annonces suivies, événements, statut des sources, références | branche Git `data` (1 commit réécrit à chaque collecte) |
| `data/raw/` | lots bruts produits par `collect` (un fichier par source) | artefacts GitHub Actions (3 jours) |
| `data/public/` | JSON publiables (manifest + fichiers hashés) | GitHub Pages |

Le jeu de données **fictif** de démonstration est généré dans `apps/web/public/demo-data/`
(`python -m collector demo`).
