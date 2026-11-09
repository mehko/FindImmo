# Sources

## Évaluation du 2026-11-08

| Source | robots.txt | Méthode | Statut |
|---|---|---|---|
| Citya (`citya.com`) | `/annonces/` autorisé | sitemaps vente/location (CP dans l'URL) + JSON-LD `RealEstateListing` | **active**, compatible |
| Laforêt (`laforet.com`) | autorisé (hors recherche, PDF) | sitemap `produits.xml` (commune dans l'URL) + dataLayer | **active**, partielle (pas de DPE) |
| Century 21 | détails autorisés | sitemap national sans localisation, pas de JSON-LD | incompatible en l'état |
| Capifrance | — | challenge Cloudflare | bloquée |
| Stéphane Plaza, SAFTI | 403 | — | bloquées |
| iad, Guy Hoquet | sitemaps accessibles | non évaluées en détail | en attente |

Les pages détail réelles n'ont pas été copiées dans le dépôt : les tests utilisent des fixtures
**fictives** reproduisant la structure observée (`collector/tests/fixtures/`).

## Ajouter une source

1. `python -m collector discover https://www.agence-exemple.fr` : robots.txt, sitemaps, CMS,
   présence de JSON-LD ; l'entrée est ajoutée à `config/sources.candidates.yaml` avec
   `enabled: false`, `compatibility: pending_validation`.
2. Vérifier manuellement (conditions d'utilisation, robots.txt, volume), compléter `url_pattern`
   (groupe `ref` obligatoire ; `postal_code` ou `city` pour le pré-filtrage) et les champs.
3. Tester : `python -m collector run --sources <id> --max-details 5`.
4. Déplacer l'entrée dans `config/sources.yaml`, `enabled: true`, `compatibility: compatible`.

Une source découverte n'est **jamais** activée automatiquement et robots.txt est toujours appliqué.

### Exemple : site avec JSON-LD

```yaml
- id: agence-x
  name: Agence X
  domain: www.agence-x.fr
  url: https://www.agence-x.fr
  method: sitemap_jsonld
  enabled: true
  compatibility: compatible
  departments: ["77"]
  options:
    sitemaps: [https://www.agence-x.fr/sitemap.xml]
    url_pattern: '/annonce/(?P<city>[a-z-]+)-(?P<ref>\d+)$'
    transaction_from_url: { /vente/: sale, /location/: rent }
```

### Exemple : site HTML sans données structurées

Voir la docstring de `collector/connectors/html.py` (sélecteurs CSS, regex, `features_selector`).

### Nouvel adaptateur

Pour un moteur partagé par plusieurs agences : sous-classe de `SitemapConnector` dans
`collector/connectors/adapters/`, implémenter `parse_detail`, l'enregistrer dans
`connectors/registry.py`, ajouter une fixture fictive et des tests.

## Agences de Colombes (92700) — découverte du 2026-11-09

Liste de 37 agences vérifiée par requêtes HTTP (code, redirections), puis `python -m collector discover`
sur les 31 sites joignables. Résultats dans `config/sources.candidates.yaml` (`enabled: false`,
`pending_validation`) : **aucune source n'est activée**, la validation reste manuelle (étapes ci-dessus).

| Catégorie | Agences | Suite |
|---|---|---|
| JSON-LD détecté (méthode `sitemap_jsonld` probable) | Century 21 Beaurepaire, Human Immobilier, Re/Max | candidats prioritaires : renseigner `url_pattern` |
| HTML sans JSON-LD, moteur connu (adaptateur partagé possible) | Apimo : Arthurimmo, Impact Immo, NCI+, Futur Transactions · Hektor : Act'immo, Coeuret · Netty : Immodurand · Immo-facile : Les Agents de l'Immobilier | un adaptateur par moteur |
| HTML sans JSON-LD, moteur inconnu ou peu d'annonces dans le sitemap | ASM, Agence Centrale, Cabinet Vincent, GIC, Gridimmo, HF Conseil, I3G, Imax, Intérieur et Jardin, Louzi, MonEden, Montquartier, KLH Conseil, Your New Home, Massiet, ERA, Foncia | sélecteurs à définir au cas par cas |
| Déjà enregistrées | Laforêt (active), iad (en attente) | — |
| Interdites par robots.txt | House Immobilier (drhouse-immo.com) | exclue |
| Bloquées (403) | Capifrance, Efficity, Keymex, Stéphane Plaza | exclues (non contournées) |
| Inutilisables | AGS Immobilier (domaine abandonné), Orpi Action Immobilier (404) | à revérifier |

Les sitemaps de Foncia, ERA et Human sont nationaux : le pré-filtrage par commune/code postal est
indispensable avant toute activation.
