# Déploiement (0 €)

## 1. GitHub Actions + Pages (données)

1. Dépôt public recommandé : minutes Actions illimitées. En dépôt privé (2 000 min/mois), une
   collecte toutes les 3 h consomme ~8 min × 240 = ~1 900 min : réduire `max_details_per_run` ou
   passer le cron à 4–6 h dans `.github/workflows/collect.yml`.
2. *Settings → Pages → Build and deployment → Source* : **GitHub Actions**.
3. *Settings → Actions → General → Workflow permissions* : lecture/écriture (pousse la branche `data`).
4. Lancer *Actions → Collecte → Run workflow* (optionnellement `sources=citya`, `max_details=20`).
5. Les données sont servies sur `https://<utilisateur>.github.io/<dépôt>/manifest.json`
   (GitHub Pages ajoute `Access-Control-Allow-Origin: *`, la PWA peut donc les lire depuis Netlify).

Garanties : `concurrency: collect` (pas de collectes concurrentes), lots `fail-fast: false`, une
source en échec ne retire aucune annonce, l'état est réécrit en un seul commit sur `data`.

## 2. Netlify (PWA)

1. *Add new site → Import from Git* ; `netlify.toml` fournit commande et dossier de publication.
2. *Site configuration → Environment variables* : `VITE_DATA_URL=https://<utilisateur>.github.io/<dépôt>/`.
3. Les collectes ne modifient pas `main` : elles ne déclenchent aucun build Netlify ; la commande
   `ignore` évite aussi les builds quand seul le collector change.

Sans `VITE_DATA_URL`, la PWA affiche le jeu de démonstration fictif ; l'adresse peut aussi être
saisie dans *Paramètres* de l'application.

## 3. Installation sur Android

Ouvrir l'URL Netlify dans Chrome → menu ⋮ → *Installer l'application*. Pour transférer recherches
et favoris vers le second téléphone : *Paramètres → Exporter*, puis *Importer* sur l'autre appareil.

## Non vérifié dans cette session

Le déploiement réel (Pages, Netlify) et l'exécution des workflows sur GitHub n'ont pas pu être
testés depuis l'environnement de développement : ils nécessitent les réglages ci-dessus.
