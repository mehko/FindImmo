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
| **Active, limitée au 92** (adaptateur `foncia`) | Foncia (`foncia`) | validée le 2026-11-09 : sous-sitemaps `achat-annonce` (~11 500) et `location-annonce` (~10 600) ; commune + code postal (ou département) dans l'URL → pré-filtrage sans requête ; la fiche complète (prix/loyer, surface, pièces, DPE/GES, équipements) est lue dans l'état serveur Angular de la page, le JSON-LD n'ayant pas le prix ; annonces non « active » retirées ; 613 annonces dans le 92 (294 testées, 0 échec). **Volontairement limitée au 92** : les départements configurés en contiennent 4 579 (~18 collectes de 250 pages) ; à élargir progressivement via `departments` |
| **Active** (adaptateur `era`) | ERA Immobilier (`eraimmobilier`) | validée le 2026-11-09 : le sitemap (~13 000 URL nationales sans localisation) est inutilisable ; les pages de résultats du département (`/achat/<région>/<dép>`, `/location/…`, `?page=N`) embarquent dans `ng-state` la réponse de recherche **avec les annonces complètes** → 451 annonces du 92 (428 ventes + 23 locations) en ~72 s, sans télécharger les fiches ; DPE présent, GES et GPS absents/ignorés |
| **Active** (`html`, sélecteurs seuls) | Les Agents de l'Immobilier (`lesagentsdelimmobilier`) | validée le 2026-11-09 : WordPress/Houzez sans données structurées ; 326 annonces dans le sous-sitemap `property` (les biens vendus sont dans `vendus`, non collectés) ; prix, surface, pièces, chambres, type, commune, CP, transaction extraits, DPE lu dans le texte ; pas de pré-filtrage géographique (URL sans commune) → couverture complète en ~3 collectes |
| **Actives** (adaptateur `hektor`) | Act'Immo 92 (`act-immo`), Coeuret Immobilier (`coeuretimmobilier`) | validées le 2026-11-09 : Hektor/LBI sans données structurées, un jeu de sélecteurs par thème ; commune dans l'URL → pré-filtrage sans requête. Sur Act'Immo le prix du bandeau est souvent vide : il est reconstitué depuis le prix net vendeur et le taux d'honoraires acquéreur (vérifié : 280 000 € × 1,0536 = 295 008 € pour 295 000 € affichés), arrondi à 100 € et marqué « parsed » ; sans taux lisible, le prix reste inconnu |
| **Active** (`sitemap_jsonld`, plateforme Netty) | Immodurand (`immodurand`) | validée le 2026-11-09 : `Product` dont le bien est dans `offers.itemOffered` ; code postal dans l'URL ; biens vendus (`price: 0`) retirés via `removed_if_no_price` ; parkings/garages (majorité des ~100 URL) écartés par le pipeline ; pages lourdes (~800 Ko) → collecte lente |
| **Actives** (`html` / `sitemap_jsonld`, configuration seule) | Gridimmo (`gridimmo`), Louzi (`louzi-immobilier`), ASM (`asm-immobilier`) | validées le 2026-11-10 (voir ci-dessous) |
| Non retenus (sites indépendants évalués le 2026-11-10) | Agence Centrale, I3G (WordPress : articles, 1 annonce / biens anciens), HF Conseil (page unique, 2-3 biens), Massiet (Wix, services), GIC (WordPress « coming soon »), KLH Conseil (blog), Your New Home (pages de recherche par ville), Montquartier (page d'accueil vide) | pas d'annonces exploitables ou volume négligeable |
| Protégés par AWS WAF (défi JavaScript) | Cabinet Vincent, Imax, Intérieur et Jardin, MonEden | non contournés ; leur « 202 » du premier contrôle était la page de défi |
| Déjà enregistrées | Laforêt (active), iad (en attente) | — |
| Interdites par robots.txt | House Immobilier (drhouse-immo.com) | exclue |
| Bloquées (403) | Capifrance, Efficity, Keymex, Stéphane Plaza | exclues (non contournées) |
| Inutilisables | AGS Immobilier (domaine abandonné), Orpi Action Immobilier (404) | à revérifier |

Pour ERA et HUMAN, dont les sitemaps étaient inexploitables, la découverte passe par les pages de résultats
(voir les adaptateurs `era` et `human`).

### Sites indépendants activés le 2026-11-10

* **Gridimmo** : sitemap en FR et EN pour chaque annonce (seule la version FR est retenue) ; HTML maison, sélecteurs par libellés ;
  vente et location (« /mois » → location) ; commune dans l'URL ; 40 annonces, toutes extraites.
* **Louzi** : annonces absentes du sitemap ; découverte par la liste complète paginée `/biens-immobiliers/tous/tous?page=N` (option
  générique `list_page_param`, arrêt à la première page sans nouveauté) ; code postal dans l'URL ; 38 annonces, toutes extraites.
* **ASM** (WordPress + Houzez) : le JSON-LD donne surface et adresse **du bien** (le code postal visible dans le texte est celui de
  l'agence) mais pas le prix, lu dans le HTML (option générique `supplement_fields`). Environ la moitié des ~500 pages `/bien/` sont
  vendues ou louées, en un bloc continu au milieu du sitemap (~220 biens actifs) : retirées d'après le « Statut de propriété » ou le fil d'Ariane (option `removed_if`). **Piège** : les étiquettes
  « Vendu » / « Déjà loué » de la page appartiennent aux fiches similaires, pas au bien ; un premier diagnostic fondé sur elles avait
  conclu à tort que 85 % des biens étaient vendus.
* Même thème Houzez ≠ mêmes sélecteurs : ASM et Les Agents de l'Immobilier ont des gabarits Elementor différents (libellés et
  structure du `<li>`), donc une configuration par site.

### Hosman (hosman.co) — activé en découverte partielle (2026-11-10)

Agence en ligne nationale. `robots.txt` autorise les pages publiques mais interdit `/api/`. Les fiches (`/a/…`) ne sont pas dans le
sitemap ; les pages de ville `/b/achat-<ville>` n'affichent que **9 fiches** (carrousel plafonné). La liste complète est chargée par
JavaScript depuis `/api/v1/properties`, route interdite : elle n'est **pas** utilisée.

* **Découverte** : les 25 pages `/b/achat-<ville>` du 92 donnent 62 fiches uniques. Les 200 pages `/t/achat-<type>-<ville>` du même
  département (8 types × 25 communes) n'en ajoutent **aucune** : 62 est très probablement le catalogue complet, sans en avoir la preuve.
* **Option `partial_discovery`** (générique) : la découverte n'est plus considérée comme exhaustive, donc une annonce absente n'est
  **jamais** marquée indisponible. Pour éviter qu'une annonce vendue reste affichée indéfiniment, les annonces connues mais non
  redécouvertes sont **revérifiées directement par leur page** (à la cadence `refresh_days`) ; une page supprimée, redirigée ou portant
  le bandeau « vendu » les retire, et seul ce retrait *confirmé* fait progresser le cycle de vie (`unavailable_unconfirmed` → `gone`).
* **Point non vérifié** : l'aspect d'une fiche Hosman vendue n'a pas pu être observé (aucune dans l'échantillon). La règle `removed_if`
  (bandeau rouge `div.bg-ih-red-80`, vide sur un bien disponible) est volontairement étroite ; si Hosman garde les fiches vendues en
  ligne sans ce mot, elles resteront actives jusqu'à suppression de la page. À surveiller au premier cas réel.
* Vente uniquement ; DPE non exposé.

### Le Figaro Immobilier (immobilier.lefigaro.fr) — intégration complète du 92, sous accord écrit (2026-11-11)

Portail d'annonces de Figaro Classifieds. Ses conditions d'utilisation (art. 6) interdisent toute collecte automatisée sans accord écrit
préalable ; `robots.txt` autorise les pages de liste (`/annonces/…`, pagination `?page=N`) mais interdit `/api/`, `/recherche/` et les
URL à paramètres (jamais utilisés). Le propriétaire du projet a fourni l'« Accord de licence et d'accès aux données » Figaro Classifieds ×
FindImmo (copie non conservée dans le dépôt). **Dans la copie remise au 2026-11-11, les annexes (zones, rubriques, publication, débit,
plages horaires, conditions économiques) et l'identité des parties sont encore en blanc** : le périmètre ci-dessous est donc celui choisi
par le propriétaire (« intégrer complètement Figaro Immobilier »), à rapprocher des annexes dès qu'elles seront remplies.

**Obligations lisibles dans le texte de l'accord, mises en œuvre dans le code**

| Clause | Mise en œuvre |
|---|---|
| § 4 — mention « Source : Figaro Immobilier » + lien cliquable vers l'annonce d'origine | `attribution` de la source, publiée dans `sources.json` ; affichée sur chaque carte et, avec lien vers l'annonce d'origine, dans la section « Sources » de la fiche |
| § 6 — annonce retirée de la source : retirée de l'affichage sous 48 h | `hide_unavailable: true` : une annonce qui n'est plus `active` n'est plus publiée ; une lecture par jour → retrait sous ~24 h |
| § 5 — débit, cadence, plages horaires, pas de contournement | 1 requête / 3 s ; 1 lecture par jour et par lot (`min_interval_hours: 20`) ; plages nocturnes (`run_hours_utc`) ; aucun contournement |
| § 7 — pas de revente / API / export massif à des tiers, pas d'entraînement d'IA | aucun accès à l'API du site ; les données ne sont pas revendues. ⚠ Les fichiers JSON publiés par FindImmo étant publics, à confronter à l'annexe « Publication publique » |
| § 5 / annexe 2 — robot identifié avec un contact | User-Agent actuel `FindImmoBot/0.1 (+https://github.com/mehko/FindImmo; usage personnel)` : le contact (e-mail) est à ajouter par le propriétaire |
| § 8 — pas de données personnelles | aucun champ personnel collecté (ni noms, ni téléphone des agents) |

**Périmètre : tous les Hauts-de-Seine, vente et location.** 36 communes en vente (16 083 annonces, 538 pages) et 35 en location
(1 642 annonces, 69 pages) : **607 pages de ~1,9 Mo** par lecture complète. La page du département plafonne à 100 pages (3 100 annonces) :
seules les pages communales (`immobilier-<vente|location>-bien-<commune>+<cp>.html`) sont exhaustives. Pour ne pas dépasser le
débit poli ni la limite de 30 minutes d'un job, le travail est réparti en **4 lots de ~152 pages** (`figaro-immobilier`, `-2`, `-3`, `-4`),
chacun lu une fois par jour dans sa propre plage de 3 h UTC (0-2 h, 3-5 h, 6-8 h, 9-11 h). Colombes reste dans le lot 1
(identifiant historique, pour conserver ses annonces).

* **Méthode** : le site est une application Nuxt ; chaque page embarque dans `__NUXT_DATA__` (format « devalue ») sa liste avec les annonces
  **complètes** (prix, surface, pièces, DPE, agence, photos) : aucune fiche n'est téléchargée. Les sitemaps de fiches (~600 000, sans
  localisation) ne sont pas utilisés.
* **Pièges** : (1) au-delà de la dernière page annoncée, le site renvoie une liste générique (`totalPage` passe à 100) : lecture arrêtée au
  total de la 1re page ; (2) une commune **sans** annonce d'un type (ex. aucune location à Marnes-la-Coquette) reçoit une liste générique de
  milliers de résultats d'autres communes : reconnue à la part de codes postaux différents de celui de l'URL (< 50 %) et ignorée ;
  (3) les annonces sponsorisées se répètent d'une page à l'autre : dédoublonnage par identifiant.
* **Calendrier** : options génériques `run_hours_utc` (plage d'heures UTC) et `min_interval_hours` ; une source ignorée n'a pas de lot et ses
  annonces ne changent pas de statut ; une exécution explicite (`--sources`) ignore le calendrier.
* **Doublons** : un portail reprend les annonces d'agences déjà collectées en direct ; le dédoublonnage du pipeline les fusionne.
* GPS ignoré (2 décimales : niveau commune). Étendre à d'autres départements = ajouter leurs pages communales en lots, en tenant
  compte du poids (Paris ou la Seine-et-Marne représenteraient chacun plusieurs centaines de pages).
