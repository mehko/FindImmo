# Architecture

## Vue d'ensemble

1. **collect** (par lot de sources, en parallèle dans GitHub Actions) : chaque connecteur découvre
   toutes les références d'annonces (sitemap, flux…), pré-filtre géographiquement (code postal ou slug
   de commune dans l'URL), puis télécharge un nombre **budgeté** de pages détail : nouvelles d'abord,
   puis modifiées (`lastmod`), puis les plus anciennes. Sortie : un `SourceBatch` JSON par source.
2. **process** : applique les lots à l'état (`data/state/`), normalise, dédoublonne, produit les
   événements, puis publie `public/` de façon atomique.
3. **PWA** : lit `manifest.json` puis les fichiers hashés des départements choisis ; tout le filtrage
   et le score sont calculés sur l'appareil.

## Connecteurs

| Classe | Méthode (`config/sources.yaml`) | Usage |
|---|---|---|
| `SitemapConnector` | — (base) | découverte par sitemap, regex d'URL avec groupes `ref`, `postal_code`, `city`… |
| `JsonLdConnector` | `sitemap_jsonld` | tout site exposant `RealEstateListing`/`Offer` schema.org ; repli `fallback_fields` |
| `HtmlConnector` | `html` | sélecteurs CSS déclarés en configuration, pages de liste ou sitemap |
| `FeedConnector` | `feed` | flux JSON documentés (`file://` pour les fixtures) |
| `LaforetConnector` | `adapter: laforet` | adaptateur réutilisable pour toutes les agences du réseau Laforêt |
| `PlaywrightRenderer` | `render: playwright` | rendu JS optionnel (dépendance `.[browser]`), robots.txt vérifié |

Ordre de préférence : flux > sitemap + JSON-LD > HTML > Playwright. Ajouter une agence utilisant
un CMS déjà couvert = ajouter une entrée de configuration, sans code.

Le client HTTP (`collector/http.py`) respecte robots.txt (règles avec jokers via Protego, 403 sur
robots.txt = tout interdit), applique un délai par hôte (et `Crawl-delay`), réessaie sur 429/5xx et
**s'arrête** sur une protection anti-bot (aucun contournement).

## Modèle et provenance

`RawListing` (brut) → `Listing` (normalisé). Chaque champ non nul peut avoir une provenance :
`extracted` (implicite), `parsed` (lu dans un texte), `computed` (prix/m², département),
`estimated` (coordonnées du centre de la commune). Les booléens `false` des sources sont ignorés par
défaut (`trust_false_features`) car souvent faux (observé chez Citya : « cave: false » alors que la
description mentionne une cave). Un équipement non mentionné reste **inconnu**.

Identifiant stable : `fi_` + sha1(source, identifiant d'origine)[:12]. Identifiant de bien
(`property_id`) : celui de l'annonce du groupe détectée en premier.

## Dédoublonnage

* Niveau 1 : même source+référence (même ID) ; même URL normalisée.
* Niveaux 2/3 : comparaison au sein d'une même commune et transaction (blocage), sources différentes
  uniquement, surface obligatoire des deux côtés. Score : surface, prix, pièces, chambres, terrain,
  DPE, distance GPS exacte. Incompatibilités franches (surface > 8 %, prix > 20 %, DPE différent…)
  ⇒ pas de rapprochement. ≥ 0,8 : fusion ; 0,55–0,8 : `maybe_same` (affiché, **non fusionné**).
  Chaque annonce garde sa source et son prix.

## Cycle de vie et événements

`new`, `price_drop`, `price_increase`, `features_changed`, `unavailable` (absente d'une découverte
**complète** ⇒ `unavailable_unconfirmed`), `reappeared`, `gone` (absente ≥ 3 collectes et ≥ 7 jours).
Une source en erreur ou une découverte partielle ne modifie jamais le statut de ses annonces.
L'historique des prix n'enregistre que les changements. Les annonces `gone` sont purgées après
30 jours, les événements après 120 jours (60 jours publiés).

## Publication

```
manifest.json                     # seul fichier à nom fixe ; écrit en dernier
listings/<dep>.<sha>.json         # annonces actives + non confirmées, par département
events/recent.<sha>.json          # événements des 60 derniers jours
sources.<sha>.json, report.<sha>.json, geo/communes.<sha>.json
```

Les noms hashés rendent la mise à jour atomique côté client et permettent un cache sans
revalidation. Si un fichier a disparu (publication intervenue pendant un chargement), la PWA relit le
manifest une fois.

## PWA

* Dexie (`findimmo`) : `searches`, `favorites` (avec copie de l'annonce), `ignored`, `settings`,
  `alertsRead`, `catalogFiles` (cache hors ligne du catalogue, purgé selon le manifest).
  Le cache catalogue est indépendant des données personnelles : une mise à jour ne les touche pas.
* Moteur (`src/lib/match.ts`) : critères obligatoires → `pass`/`fail`/`unknown` ; politique
  « garder à vérifier » ou « exclure » pour les données manquantes. Score 0–100 = composantes
  pondérées actives (proximité 20, budget 20, surface 20, chambres 10, équipements 15, énergie 10,
  fraîcheur 5), une donnée manquante vaut 50 % de sa composante et est signalée.
  `ScoreExtension` permet d'ajouter une composante (ex. modèle local) sans dépendance.
* Alertes calculées localement depuis les événements publiés (pas de push : nécessiterait un serveur).
* Service worker (Workbox) : shell pré-caché, vignettes en cache ; données via IndexedDB.

## Limites connues

* Couverture : 2 sources réelles (Citya, Laforêt). Century 21 (pas de localisation dans le sitemap ni
  de JSON-LD), Capifrance (Cloudflare), Stéphane Plaza et SAFTI (robots.txt en 403) non intégrées.
* Laforêt : DPE publié uniquement en image → non extrait. Pré-filtrage par slug de commune : les
  communes homonymes hors zone sont téléchargées puis écartées (mises en cache 30 jours).
* Montée en charge initiale : ~7 900 annonces Laforêt et ~1 500 Citya dans la zone ; avec 250 pages
  détail par source et par collecte (8 collectes/jour), l'amorçage complet prend environ 4 jours.
* Les prix ne sont vérifiés que lors d'un retéléchargement (nouveau `lastmod` ou tous les 3–4 jours) :
  une baisse peut être détectée avec retard.
* Les sélecteurs/regex dépendent de la structure des sites : une refonte casse le connecteur (visible
  dans le rapport de collecte et `sources.json`).
* Pas de notifications push, pas de synchronisation entre téléphones (export/import manuel).
