# FindImmo — Plan d'implémentation

## 1. État initial

Dépôt vide (aucun commit). Environnement : Python 3.12+ (testé en 3.13), Node 22, pnpm 10.
Accès réseau vérifié vers plusieurs sites d'agences (robots.txt, sitemaps, pages détail) et vers
`geo.api.gouv.fr` (référentiel des communes, gratuit, sans clé).

## 2. Architecture

```
                        ┌──────────── GitHub Actions (cron 3 h / manuel) ───────────┐
config/*.yaml ──► collect (shards matrix) ──► raw/*.json ──► process ──► public/   │
                   │  connecteurs génériques      (artefacts)   normalise           │
                   │  + adaptateurs réseau                       déduplique          │
                   │  HTTP poli (robots.txt,                     événements prix     │
                   │  délai/hôte, retries)                       publication atomique│
                   └──────────────────────────────────────────────────┬──────────────┘
                            état persistant : branche `data` (1 commit, force-push)
                                                                     │
                                         GitHub Pages (JSON statiques hashés + manifest)
                                                                     │ fetch (CORS *)
             Netlify (PWA React, build uniquement si apps/web change) ┘
                         └─ IndexedDB (Dexie) : recherches, favoris, notes, alertes, cache catalogue
```

* **Collector** (`collector/`, Python) : `collect` (découverte + détails par source, incrémental,
  budgeté) → `process` (normalisation, dédoublonnage 3 niveaux, cycle de vie, événements, publication).
* **Contrat de données** (`packages/shared/`) : types TypeScript + JSON Schema exporté depuis les
  modèles Pydantic (`python -m collector schema`). Version de format `FORMAT_VERSION`.
* **PWA** (`apps/web/`) : React + Vite + TS strict + Tailwind + composants style shadcn/ui,
  Dexie, vite-plugin-pwa. Moteur de recherche/pertinence 100 % local et déterministe.

## 3. Risques et dépendances

| Risque | Mesure |
|---|---|
| Sites protégés (Cloudflare, DataDome) ou robots.txt restrictif | Registre de sources avec statut de compatibilité ; robots.txt toujours respecté ; aucun contournement anti-bot. Sources bloquées marquées `blocked`. |
| Changement de structure HTML d'un site | Priorité JSON-LD / données structurées ; tests sur fixtures ; erreurs isolées par source ; rapport de collecte. |
| Volume (sitemaps nationaux de 30 000 URL) | Pré-filtrage par code postal / slug de commune dans l'URL ; budget de pages détail par exécution ; rafraîchissement incrémental (`lastmod`, ancienneté). |
| Quotas GitHub Actions (2 000 min/mois en dépôt privé) | Budget temps par source, cron 3 h configurable ; dépôt public = minutes illimitées. |
| Croissance de l'historique Git | Données hors `main` : état sur branche `data` réécrite (1 commit), publication via artefact Pages. |
| Faux positifs de dédoublonnage | Fusion automatique seulement au-dessus d'un seuil élevé ; zone grise publiée comme « doublon possible » sans fusion. |
| Données manquantes | Valeurs nulles, provenance par champ (`extracted`, `parsed`, `computed`, `estimated`), état « inconnu » explicite dans le filtrage. |
| Publication de données tierces | Extrait de description tronqué, 1 vignette (lien, pas de copie), lien vers l'annonce d'origine. Configurable par source. |

## 4. Jalons

1. **Initialisation** — monorepo, outillage Python/TS, docs. ✅
2. **Collector** — modèles, registre, HTTP poli, connecteurs (sitemap, JSON-LD, HTML, feed,
   Playwright optionnel), adaptateur Laforêt, normalisation, dédoublonnage, événements, publication. ✅
3. **PWA** — 4 onglets, fiche bien, filtres, recherches, pertinence explicable. ✅
4. **IndexedDB** — favoris, notes, statuts, ignorés, paramètres, alertes lues, export/import. ✅
5. **Automatisation** — CI, collecte planifiée + publication Pages, Netlify séparé. ✅ (activation
   Pages/Netlify à faire par le propriétaire, voir `docs/DEPLOYMENT.md`)
6. **Validation** — tests unitaires/intégration, build, vérification hors ligne, limites connues. ✅

## 5. Suite possible (hors MVP)

* Ajouter des sources (voir `docs/SOURCES.md`, commande `discover`).
* Notifications push (nécessite un service d'envoi : non inclus, budget 0 €).
* Extension de pertinence par modèle IA (interface `ScoreExtension` prévue côté PWA).
