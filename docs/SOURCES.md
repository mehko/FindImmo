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
| **Active** (`sitemap_jsonld`) | Century 21 Beaurepaire (`century21-beaurepaire-colombes`) | validée le 2026-11-09 : 36 annonces, 8/8 extraites (JSON-LD en graphe `@id`, transaction lue dans le titre) |
| **Active** (adaptateur `remax`) | Re/Max (`remax`) | validée le 2026-11-09 : le sitemap n'a que ~3 100 annonces utiles (le reste = pages de recherche, jamais téléchargées) ; département/commune dans l'URL → pré-filtrage sans requête ; détail via `__NEXT_DATA__` ; mandats vendus (très nombreux) retirés ; ~220 annonces dans les départements configurés |
| **Active** (adaptateur `human`) | HUMAN Immobilier (`human-immobilier`) | validée le 2026-11-09 : sitemap sans annonces → découverte par les pages de résultats de la commune ; détail via JSON-LD `RealEstateListing` ; annonces « Vendu » retirées ; 35 annonces à Colombes, vente uniquement |
| **Actives** (`sitemap_jsonld`, plateforme Apimo) | Impact Immo (`impact-immo`), NCI+ (`nciplus`), Futur Transactions (`futurtransactions-colombes`) | validées le 2026-11-09 : le JSON-LD `RealEstateListing` place le bien dans `about` (lu par `find_offer`) ; type, surface, pièces, commune, CP et GPS extraits ; DPE absent. Futur Transactions : vente seule, annonces « VENDU » retirées (`removed_markers`). Impact Immo : ~530 annonces en zone (92), collectées par lots de 100 |
| **Active** (`html`, sélecteurs seuls) | Arthurimmo Colombes (`arthurimmo-colombes`) | validée le 2026-11-09 : 17 annonces extraites depuis le titre OpenGraph et la liste libellé/valeur ; DPE et GPS non extraits |
| **Active** (adaptateur `era`) | ERA Immobilier (`eraimmobilier`) | validée le 2026-11-09 : le sitemap (~13 000 URL nationales sans localisation) est inutilisable ; les pages de résultats du département (`/achat/<région>/<dép>`, `/location/…`, `?page=N`) embarquent dans `ng-state` la réponse de recherche **avec les annonces complètes** → 451 annonces du 92 (428 ventes + 23 locations) en ~72 s, sans télécharger les fiches ; DPE présent, GES et GPS absents/ignorés |
| **Active** (`html`, sélecteurs seuls) | Les Agents de l'Immobilier (`lesagentsdelimmobilier`) | validée le 2026-11-09 : WordPress/Houzez sans données structurées ; 326 annonces dans le sous-sitemap `property` (les biens vendus sont dans `vendus`, non collectés) ; prix, surface, pièces, chambres, type, commune, CP, transaction extraits, DPE lu dans le texte ; pas de pré-filtrage géographique (URL sans commune) → couverture complète en ~3 collectes |
| **Actives** (adaptateur `hektor`) | Act'Immo 92 (`act-immo`), Coeuret Immobilier (`coeuretimmobilier`) | validées le 2026-11-09 : Hektor/LBI sans données structurées, un jeu de sélecteurs par thème ; commune dans l'URL → pré-filtrage sans requête. Sur Act'Immo le prix du bandeau est souvent vide : il est reconstitué depuis le prix net vendeur et le taux d'honoraires acquéreur (vérifié : 280 000 € × 1,0536 = 295 008 € pour 295 000 € affichés), arrondi à 100 € et marqué « parsed » ; sans taux lisible, le prix reste inconnu |
| **Active** (`sitemap_jsonld`, plateforme Netty) | Immodurand (`immodurand`) | validée le 2026-11-09 : `Product` dont le bien est dans `offers.itemOffered` ; code postal dans l'URL ; biens vendus (`price: 0`) retirés via `removed_if_no_price` ; parkings/garages (majorité des ~100 URL) écartés par le pipeline ; pages lourdes (~800 Ko) → collecte lente |
| HTML sans JSON-LD, moteur inconnu ou peu d'annonces dans le sitemap | ASM, Agence Centrale, Cabinet Vincent, GIC, Gridimmo, HF Conseil, I3G, Imax, Intérieur et Jardin, Louzi, MonEden, Montquartier, KLH Conseil, Your New Home, Massiet, Foncia | sélecteurs à définir au cas par cas |
| Déjà enregistrées | Laforêt (active), iad (en attente) | — |
| Interdites par robots.txt | House Immobilier (drhouse-immo.com) | exclue |
| Bloquées (403) | Capifrance, Efficity, Keymex, Stéphane Plaza | exclues (non contournées) |
| Inutilisables | AGS Immobilier (domaine abandonné), Orpi Action Immobilier (404) | à revérifier |

Le sitemap de Foncia est national : un pré-filtrage par commune/code postal est indispensable avant toute
activation. Pour ERA et HUMAN, dont les sitemaps étaient inexploitables, la découverte passe par les pages de
résultats (voir les adaptateurs `era` et `human`).
