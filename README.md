# FindImmo

Moteur de recherche et de veille immobilière **personnel**, à 0 € d'infrastructure :
collecte automatisée d'annonces d'agences (Île-de-France et Var), dédoublonnage, suivi des prix,
et PWA mobile-first installable sur Android.

```
collector/ (Python)  ──GitHub Actions (3 h)──►  GitHub Pages (JSON statiques)  ◄──  PWA React (Netlify)
                                                                                       └─ IndexedDB : recherches, favoris, notes
```

## Démarrage rapide (machine neuve)

Prérequis : Python ≥ 3.12, Node ≥ 20, pnpm 10 (`corepack enable`).

```bash
make setup        # venv Python + dépendances pnpm
make test         # pytest + vitest
make web          # PWA sur http://localhost:5173 avec le jeu de démo FICTIF
```

Collecte réelle en local (petit budget, respecte robots.txt et un délai par site) :

```bash
.venv/bin/python -m collector run --max-details 20      # → data/public/
VITE_DATA_URL=http://localhost:8000/ pnpm dev            # après: python -m http.server -d data/public 8000
```

## Commandes du collector

| Commande | Rôle |
|---|---|
| `python -m collector run` | `collect` puis `process` |
| `python -m collector collect --shard 0/2` | exécuter les connecteurs → `data/raw/` |
| `python -m collector process` | normaliser, dédoublonner, détecter les changements, publier `data/public/` |
| `python -m collector sources` | lister le registre des sources |
| `python -m collector discover <url>…` | évaluer des domaines candidats → `config/sources.candidates.yaml` |
| `python -m collector refresh-geo` | régénérer le référentiel des communes (geo.api.gouv.fr) |
| `python -m collector demo` | régénérer le jeu de démonstration fictif |
| `python -m collector schema` | exporter le JSON Schema vers `packages/shared/schema/` |

Options utiles : `--sources citya,laforet`, `--departments 77,83`, `--max-details 50`.

## Structure

| Chemin | Contenu |
|---|---|
| `collector/` | moteur Python : `connectors/` (sitemap, JSON-LD, HTML, flux, adaptateurs), `pipeline/` (normalisation, dédoublonnage, suivi, publication) |
| `config/` | départements, registre des sources, référentiel des communes |
| `packages/shared/` | types TypeScript et JSON Schema du format publié |
| `apps/web/` | PWA React + Vite + Tailwind + Dexie |
| `.github/workflows/` | CI, collecte planifiée et publication Pages |
| `docs/` | [architecture](docs/ARCHITECTURE.md), [sources](docs/SOURCES.md), [déploiement](docs/DEPLOYMENT.md) |

## État du MVP

* Sources réelles intégrées et vérifiées le 2026-11-08 : **Citya** (JSON-LD) et **Laforêt** (adaptateur réseau).
  Couverture limitée à ces sources : FindImmo n'est pas une vue exhaustive du marché.
* Le jeu de démonstration de la PWA est **fictif** (bandeau affiché dans l'application).
* Déploiement GitHub Pages / Netlify : configuration prête, activation à faire par le propriétaire
  du dépôt (voir [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

Limites connues : [docs/ARCHITECTURE.md#limites-connues](docs/ARCHITECTURE.md#limites-connues).
