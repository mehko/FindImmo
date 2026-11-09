"""Adaptateur pour le site national RE/MAX France (remax.fr).

Méthode (vérifiée le 2026-11-09, robots.txt respecté) :

* découverte : l'index ``/sitemap.xml`` compte ~8 millions d'URL, mais presque toutes sont des
  pages de **recherche**. Seul le sous-sitemap ``listings_details_fr_*`` liste les annonces
  (~3 100). On le cible avec ``include_sitemaps``. Chaque annonce y figure sous deux URL ; seule la
  forme longue (``/fr/mandats/<vente|location>-<type>-ch<N>-<région>---<dép>-<commune>/<ref>``)
  est retenue : elle porte le département et la commune, ce qui permet le pré-filtrage
  géographique sans aucune requête ;
* détail : la page est rendue par Next.js. Le JSON-LD est pauvre (prix et image seulement) ; les
  données complètes sont dans ``__NEXT_DATA__`` → ``listingEncoded`` (JSON encodé en base64).
  Les annonces ``isSold`` (très nombreuses : le site conserve les mandats vendus) sont signalées
  retirées. Les coordonnées ne sont reprises que si l'adresse est exacte (``isExactAddress``) ;
  sinon elles sont approximatives et ignorées.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from bs4 import BeautifulSoup

from ...http import ListingRemoved
from ...models import ListingRef, RawListing
from ...textparse import clean_text, parse_number
from ..sitemap import SitemapConnector

DEFAULT_SITEMAPS = ["https://remax.fr/sitemap.xml"]
DEFAULT_INCLUDE = r"listings_details_fr"
DEFAULT_URL_PATTERN = (
    r"/fr/mandats/(?P<transaction>vente|location)-(?P<type>[a-z]+)-ch[^/]*?---"
    r"(?P<department>\d{2,3}|2[AB])-(?P<city>[^/]+)/(?P<ref>\d+-\d+)$"
)
TYPE_MAP = {
    "appartement": "apartment",
    "maison": "house",
    "terrain": "land",
    "immeuble": "building",
    "stationnement": "parking",
    "local": "commercial",
    "commerce": "commercial",
    "bureau": "commercial",
}
ENERGY_LETTERS = "ABCDEFG"  # niveaux 1 à 7 ; les autres valeurs (ex. 14) = non renseigné
IMAGE_BASE = "https://i.maxwork.fr/ds-l/"


def parse_listing(html: str) -> dict[str, Any] | None:
    """Décode la fiche annonce embarquée dans ``__NEXT_DATA__``."""
    node = BeautifulSoup(html, "lxml").find("script", id="__NEXT_DATA__")
    if node is None or not node.string:
        return None
    try:
        encoded = json.loads(node.string)["props"]["pageProps"]["listingEncoded"]
        listing = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, KeyError, TypeError):
        return None
    return listing if isinstance(listing, dict) else None


def _letter(level: Any) -> str | None:
    return ENERGY_LETTERS[level - 1] if isinstance(level, int) and 1 <= level <= len(ENERGY_LETTERS) else None


class RemaxConnector(SitemapConnector):
    method = "adapter:remax"

    def sitemap_urls(self) -> list[str]:
        return list(self.options.get("sitemaps") or DEFAULT_SITEMAPS)

    def discover(self):  # type: ignore[override]
        self.options.setdefault("url_pattern", DEFAULT_URL_PATTERN)
        self.options.setdefault("include_sitemaps", DEFAULT_INCLUDE)
        yield from super().discover()

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        item = parse_listing(html)
        if item is None:
            return None
        if item.get("isSold") or item.get("isOnline") is False or item.get("isActive") is False:
            raise ListingRemoved(ref.url, "mandat vendu ou hors ligne")

        slug = re.search(r"/mandats/(vente|location)-([a-z]+)-", ref.url)
        transaction = "rent" if (slug and slug[1] == "location") or item.get("businessTypeID") == 2 else "sale"
        ptype = TYPE_MAP.get(slug[2], "other") if slug else "other"

        features = {k2: True for k, k2 in (("parking", "parking"), ("garage", "garage"), ("elevator", "elevator"))
                    if item.get(k) is True}
        description = None
        for d in item.get("descriptions") or []:
            if isinstance(d, dict) and d.get("languageCode") == "FR" and d.get("description"):
                description = clean_text(BeautifulSoup(d["description"], "lxml").get_text(" ", strip=True))
                break

        title_tag = BeautifulSoup(html, "lxml").find("meta", attrs={"property": "og:title"})
        title = clean_text(str(title_tag["content"]).split("|")[0]) if title_tag and title_tag.get("content") else None
        picture = item.get("listingPictureUrl")
        exact = item.get("isExactAddress") is True
        rooms = item.get("totalRooms")

        return RawListing(
            source_id=self.source.id,
            source_ref=ref.source_ref,
            url=ref.url,
            title=title,
            description=description,
            transaction=transaction,
            property_type=ptype,
            price=parse_number(item.get("listingPrice")),
            surface=parse_number(item.get("livingArea") or item.get("totalArea")),
            land_surface=parse_number(item.get("lotSize")),
            rooms=rooms if isinstance(rooms, int) and rooms > 0 else None,
            bedrooms=item["numberOfBedrooms"] if isinstance(item.get("numberOfBedrooms"), int) and item["numberOfBedrooms"] > 0 else None,
            city=clean_text(item.get("localZone")),
            postal_code=str(item["zipCode"]) if item.get("zipCode") else None,
            latitude=parse_number(item.get("latitude")) if exact else None,
            longitude=parse_number(item.get("longitude")) if exact else None,
            dpe=_letter(item.get("energyEfficiencyLevelID")),
            ges=_letter(item.get("emissionEfficiencyLevelID")),
            features=features,
            published_at=str(item["publishDate"])[:10] if item.get("publishDate") else None,
            image=IMAGE_BASE + picture if picture else None,
            agency=clean_text(item.get("officeName")),
        )
