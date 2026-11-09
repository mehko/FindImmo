"""Adaptateur pour le site national ERA Immobilier (www.eraimmobilier.com).

Méthode (vérifiée le 2026-11-09, robots.txt respecté) :

* Le sitemap ne se prête pas à la collecte : ~13 000 URL ``/annonces/<id>`` nationales, sans
  localisation. On passe par les **pages de résultats** d'un département ou d'une commune
  (``/achat/<région>/<département>`` et ``/location/…``, paginées par ``?page=N``, 10 annonces par page) ;
* ces pages Angular embarquent, dans le bloc ``<script id="ng-state">``, la réponse JSON de la
  recherche du site (``…/api/v2/annonces/search?page=N…``), **annonces complètes incluses** : une
  requête couvre 10 annonces, sans télécharger les fiches. Le site filtre lui-même les mandats
  vendus (``statut=0,1,11``). Aucun appel direct à l'API : seules les pages publiques sont lues ;
* GPS ignoré : les coordonnées sont celles du centre de la commune.

Options : ``list_pages`` (URL de résultats), ``max_pages`` (défaut 60).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup

from ...models import ListingRef, RawListing
from ...textparse import clean_text, parse_number
from ..base import BaseConnector

BASE_URL = "https://www.eraimmobilier.com"
SEARCH_MARKER = "/annonces/search?page="
FEATURE_FLAGS = {
    "critere_ascenseur": "elevator",
    "critere_balcon": "balcony",
    "critere_terrasse": "terrace",
    "critere_garage": "garage",
    "critere_cave": "cellar",
    "critere_piscine": "pool",
    "critere_jardin": "garden",
}
ENERGY_LETTERS = set("ABCDEFG")


def search_state(html: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Extrait (méta de pagination, annonces) de la recherche embarquée dans la page."""
    node = BeautifulSoup(html, "lxml").find("script", id="ng-state")
    if node is None or not node.string:
        return None
    try:
        state = json.loads(node.string)
    except ValueError:
        return None
    for key, value in state.items():
        if key.startswith("ssr-cache:") and SEARCH_MARKER in key and isinstance(value, dict):
            items = value.get("data")
            if isinstance(items, list):
                return value.get("meta") or {}, [i for i in items if isinstance(i, dict)]
    return None


def _positive(value: Any) -> float | None:
    number = parse_number(value)
    return number if number and number > 0 else None


def _plain_text(html: str) -> str | None:
    """Texte brut d'une description HTML, sans espace parasite avant la ponctuation."""
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    return clean_text(re.sub(r"\s+([.,;:!?])", r"\1", text))


def _letter(value: Any) -> str | None:
    letter = str(value or "").strip().upper()
    return letter if letter in ENERGY_LETTERS else None


def raw_from_item(item: dict[str, Any], source_id: str) -> RawListing | None:
    if item.get("id") is None:
        return None
    ref = str(item["id"])
    photos = item.get("photo")
    image = photos[0] if isinstance(photos, list) and photos else None
    agency = item.get("agence")
    description = item.get("descriptif")
    features = {name: True for key, name in FEATURE_FLAGS.items() if item.get(key) in (1, "1", True)}
    if _positive(item.get("nb_parkings")) or _positive(item.get("nb_boxes")):
        features["parking"] = True
    rooms, bedrooms = _positive(item.get("nb_pieces")), _positive(item.get("nb_chambres"))
    return RawListing(
        source_id=source_id,
        source_ref=ref,
        url=f"{BASE_URL}/annonces/{ref}",
        title=clean_text(item.get("libelle")),
        description=_plain_text(description) if description else None,
        transaction=item.get("type_annonce"),
        property_type=item.get("type_bien"),
        price=_positive(item.get("prix")),
        surface=_positive(item.get("surface_habitable")),
        land_surface=_positive(item.get("surface_terrain")),
        rooms=int(rooms) if rooms else None,
        bedrooms=int(bedrooms) if bedrooms else None,
        city=clean_text(item.get("ville")),
        postal_code=str(item["code_postal"]) if item.get("code_postal") else None,
        dpe=_letter(item.get("bilan_dpe")),
        ges=_letter(item.get("bilan_ges")),
        features=features,
        published_at=str(item["date_publication"])[:10] if item.get("date_publication") else None,
        image=image if isinstance(image, str) else None,
        agency=clean_text(agency.get("enseigne")) if isinstance(agency, dict) else None,
    )


class EraConnector(BaseConnector):
    method = "adapter:era"

    def discover(self) -> Iterator[ListingRef]:
        max_pages = int(self.options.get("max_pages", 60))
        seen: set[str] = set()
        for base in self.options["list_pages"]:
            for page in range(1, max_pages + 1):
                html = self.ctx.client.get(base if page == 1 else f"{base}?page={page}").text
                parsed = search_state(html)
                if parsed is None:
                    # Structure inattendue : la découverte ne doit pas être considérée comme exhaustive.
                    raise ValueError(f"résultats de recherche introuvables dans {base} (page {page})")
                meta, items = parsed
                if not items:
                    break
                for item in items:
                    raw = raw_from_item(item, self.source.id)
                    if raw is not None and raw.source_ref not in seen:
                        seen.add(raw.source_ref)
                        yield self.make_ref(raw.source_ref, raw.url, postal_code_hint=raw.postal_code, raw=raw)
                per_page, total = meta.get("per_page"), meta.get("total")
                if isinstance(per_page, int) and isinstance(total, int) and page * per_page >= total:
                    break
