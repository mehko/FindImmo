"""Adaptateur pour la plateforme du réseau Laforêt (www.laforet.com).

Toutes les agences du réseau partagent le même moteur de site : un seul adaptateur couvre
l'ensemble des agences. Méthode (vérifiée le 2026-11-08, robots.txt respecté) :

* découverte : sitemap ``/storage/sitemaps/produits.xml`` ; l'URL contient la transaction
  (``acheter``/``louer``) et le slug de la commune → pré-filtrage géographique sans requête ;
* détail : objet ``viewItem`` du ``dataLayer`` (prix, surface, pièces, CP, ville, équipements),
  section « Caractéristiques » (terrain, chambres, équipements), carte (coordonnées).

Les booléens ``false`` du dataLayer sont ignorés (valeur par défaut non fiable).
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from ...models import ListingRef, RawListing
from ...textparse import clean_text, parse_bedrooms, parse_features, parse_land_surface, parse_number
from ..sitemap import SitemapConnector

DEFAULT_URL_PATTERN = (
    r"laforet\.com/agence-immobiliere/(?P<agency>[^/]+)/(?P<transaction>acheter|louer)/"
    r"(?P<city>[^/]+)/(?P<slug>[^/]+)-(?P<ref>\d+)$"
)

TYPE_MAP = {
    "maison": "house",
    "appartement": "apartment",
    "terrain": "land",
    "parking": "parking",
    "box": "parking",
    "immeuble": "building",
    "bureau": "commercial",
    "local commercial": "commercial",
    "fonds de commerce": "commercial",
}

FLAG_MAP = {
    "itemPiscine": "pool",
    "itemCave": "cellar",
    "itemBalcon": "balcony",
    "itemParking": "parking",
    "itemGarage": "garage",
    "itemAscenseur": "elevator",
    "itemMeuble": "furnished",
}

_DATALAYER = re.compile(r"dataLayer\.push\(\.\.\.(\[.*?\])\);", re.S)


def parse_view_item(html: str) -> dict[str, Any] | None:
    for m in _DATALAYER.finditer(html):
        try:
            events = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for ev in events:
            if isinstance(ev, dict) and ev.get("event") == "viewItem":
                return ev
    return None


class LaforetConnector(SitemapConnector):
    method = "adapter:laforet"

    def sitemap_urls(self) -> list[str]:
        return self.options.get("sitemaps") or ["https://www.laforet.com/storage/sitemaps/produits.xml"]

    def discover(self):  # type: ignore[override]
        self.options.setdefault("url_pattern", DEFAULT_URL_PATTERN)
        yield from super().discover()

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        item = parse_view_item(html)
        if item is None:
            return None
        soup = BeautifulSoup(html, "lxml")
        parsed: list[str] = []

        features: dict[str, bool] = {k2: True for k, k2 in FLAG_MAP.items() if item.get(k) is True}
        section = soup.find(id="section-features")
        section_text = section.get_text(" · ", strip=True) if section else ""
        for key in parse_features(section_text):
            features[key] = True
        land = parse_land_surface(section_text)
        bedrooms = parse_bedrooms(section_text) or parse_bedrooms(item.get("itemCriteria"))
        if bedrooms is not None and "chambre" not in str(item.get("itemCriteria", "")):
            parsed.append("bedrooms")

        lat = lon = None
        marker = soup.find(attrs={"data-map-markers-value": True})
        if marker is not None:
            try:
                coords = json.loads(unescape(str(marker["data-map-markers-value"])))[0]["coordinates"]
                lat, lon = float(coords["lat"]), float(coords["lng"])
            except (ValueError, KeyError, IndexError, TypeError):
                pass

        desc_node = soup.find(id="section-description")
        description = None
        if desc_node is not None:
            heading = desc_node.find(["h2", "h3"])
            if heading:
                heading.extract()
            description = clean_text(desc_node.get_text(" ", strip=True))

        title_tag = soup.find("title")
        title = clean_text(title_tag.get_text().split("|")[0]) if title_tag else item.get("itemName")
        og = soup.find("meta", attrs={"property": "og:image"})
        agency = soup.find(attrs={"data-gtm-agency-name-param": True})

        transaction = item.get("transactionType") or ("acheter" if "/acheter/" in ref.url else "louer")
        return RawListing(
            source_id=self.source.id,
            source_ref=ref.source_ref,
            url=ref.url,
            title=title,
            description=description,
            transaction="sale" if transaction == "acheter" else "rent",
            property_type=TYPE_MAP.get(str(item.get("itemType", "")).lower(), "other"),
            price=parse_number(item.get("itemPrice")),
            surface=parse_number(item.get("itemSize")),
            land_surface=land,
            rooms=item.get("itemRoomsNb") if isinstance(item.get("itemRoomsNb"), int) else None,
            bedrooms=bedrooms,
            city=clean_text(item.get("itemCity")),
            postal_code=str(item["itemZipcode"]) if item.get("itemZipcode") else None,
            latitude=lat,
            longitude=lon,
            features=features,
            image=str(og["content"]) if og and og.get("content") else None,
            agency=str(agency["data-gtm-agency-name-param"]) if agency else None,
            parsed_fields=parsed,
        )
