"""Extraction HTML configurable (BeautifulSoup + sélecteurs CSS).

Pour un site sans données structurées, on décrit dans ``options`` :

```yaml
options:
  sitemaps: [https://agence.example/sitemap.xml]     # ou list_pages: [...] + link_selector
  url_pattern: "/annonce/(?P<ref>\\d+)"
  fields:                                             # champ → sélecteur CSS (texte du nœud)
    title: "h1"
    price: ".price"
    surface: ".surface"
    city: ".city"
    postal_code: { selector: ".city", regex: "(\\d{5})" }
    description: ".description"
    image: { selector: "meta[property='og:image']", attr: "content" }
  features_selector: ".features li"                  # liste d'équipements (texte)
```

Les valeurs non trouvées restent nulles.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import ListingRef, RawListing
from ..textparse import (
    clean_text,
    parse_bedrooms,
    parse_energy_class,
    parse_features,
    parse_int,
    parse_land_surface,
    parse_number,
    parse_rooms,
)
from .sitemap import SitemapConnector

NUMERIC = {
    "price": parse_number,
    "surface": parse_number,
    "land_surface": parse_number,
    "latitude": parse_number,
    "longitude": parse_number,
}
INTEGER = {"rooms": parse_int, "bedrooms": parse_int}


def select_value(soup: BeautifulSoup, spec: str | dict[str, Any]) -> str | None:
    if isinstance(spec, str):
        spec = {"selector": spec}
    node = soup.select_one(spec["selector"])
    if node is None:
        return None
    value = node.get(spec["attr"]) if spec.get("attr") else node.get_text(" ", strip=True)
    if isinstance(value, list):
        value = " ".join(value)
    value = clean_text(value)
    if value and spec.get("regex"):
        m = re.search(spec["regex"], value)
        value = clean_text(m.group(1) if m.groups() else m.group(0)) if m else None
    return value


def extract_fields(soup: BeautifulSoup, fields: dict[str, Any]) -> dict[str, Any]:
    """Applique une configuration ``champ → sélecteur`` et convertit les valeurs numériques."""
    values: dict[str, Any] = {}
    for field, spec in fields.items():
        text = select_value(soup, spec)
        if text is None:
            continue
        if field in NUMERIC:
            values[field] = NUMERIC[field](text)
        elif field in INTEGER:
            values[field] = INTEGER[field](text)
        else:
            values[field] = text
    return {k: v for k, v in values.items() if v is not None}


class HtmlConnector(SitemapConnector):
    method = "html"

    def discover(self) -> Iterator[ListingRef]:
        if not self.options.get("list_pages"):
            yield from super().discover()
            return
        pattern = re.compile(self.options["url_pattern"])
        seen: set[str] = set()
        for page in self.options["list_pages"]:
            soup = BeautifulSoup(self.fetch_page(page), "lxml")
            for a in soup.select(self.options.get("link_selector", "a[href]")):
                href = urljoin(page, str(a.get("href", "")))
                m = pattern.search(href)
                if m and (ref := self.ref_from_match(href, m, None)) and ref.source_ref not in seen:
                    seen.add(ref.source_ref)
                    yield ref

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        soup = BeautifulSoup(html, "lxml")
        values = extract_fields(soup, self.options.get("fields") or {})
        parsed: list[str] = []
        title = values.get("title")
        if values.get("rooms") is None and (r := parse_rooms(title)) is not None:
            values["rooms"], parsed = r, [*parsed, "rooms"]
        if values.get("bedrooms") is None and (b := parse_bedrooms(title)) is not None:
            values["bedrooms"], parsed = b, [*parsed, "bedrooms"]
        features: dict[str, bool] = {}
        if sel := self.options.get("features_selector"):
            items = " · ".join(n.get_text(" ", strip=True) for n in soup.select(sel))
            features = parse_features(items)
            if values.get("land_surface") is None and (land := parse_land_surface(items)) is not None:
                values["land_surface"], parsed = land, [*parsed, "land_surface"]
        if values.get("dpe") is None and (dpe := parse_energy_class(soup.get_text(" "), "dpe")):
            values["dpe"], parsed = dpe, [*parsed, "dpe"]
        if not values.get("price") and not title:
            return None
        if values.get("transaction") is None and (tmap := self.options.get("transaction_from_url")):
            values["transaction"] = next((v for k, v in tmap.items() if k in ref.url), None)
        return RawListing(
            source_id=self.source.id,
            source_ref=ref.source_ref,
            url=ref.url,
            features=features,
            # Les équipements lus dans une liste HTML sont des mentions textuelles.
            parsed_fields=[*parsed, *[f"features.{k}" for k in features]],
            **{k: v for k, v in values.items() if k in RawListing.model_fields},
        )
