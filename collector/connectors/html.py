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
  removed_if: [{ selector: ".statut", regex: "Vendu|Loué" }]   # texte d'un nœud → annonce retirée
  list_page_param: page                              # pagination des list_pages (?page=2…), arrêt à la première page sans nouveauté
  transaction_from_url: { /vente/: sale }            # ou transaction_from_text (règles regex sur un texte de la page)
```

Les valeurs non trouvées restent nulles.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import ListingRemoved
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


def raise_if_removed(soup: BeautifulSoup, specs: list[dict[str, str]] | None, url: str) -> None:
    """Option ``removed_if`` : liste de ``{selector, regex}``. Si un nœud correspondant a un texte qui satisfait la
    regex (sensible à la casse), l'annonce est considérée comme retirée (vendue, louée…)."""
    for spec in specs or []:
        for node in soup.select(spec["selector"]):
            if re.search(spec["regex"], node.get_text(" ", strip=True)):
                raise ListingRemoved(url, f"annonce marquée « {spec['regex']} »")


class HtmlConnector(SitemapConnector):
    method = "html"

    def discover(self) -> Iterator[ListingRef]:
        if not self.options.get("list_pages"):
            yield from super().discover()
            return
        pattern = re.compile(self.options["url_pattern"])
        param = self.options.get("list_page_param")  # ex. « page » → ?page=2, ?page=3…
        max_pages = int(self.options.get("max_list_pages", 30)) if param else 1
        seen: set[str] = set()
        for base in self.options["list_pages"]:
            for number in range(1, max_pages + 1):
                page = base if number == 1 else f"{base}{'&' if '?' in base else '?'}{param}={number}"
                soup = BeautifulSoup(self.fetch_page(page), "lxml")
                new = 0
                for a in soup.select(self.options.get("link_selector", "a[href]")):
                    href = urljoin(page, str(a.get("href", "")))
                    m = pattern.search(href)
                    if m and (ref := self.ref_from_match(href, m, None)) and ref.source_ref not in seen:
                        seen.add(ref.source_ref)
                        new += 1
                        yield ref
                if not new:
                    break  # page vide ou sans nouveauté : fin de la pagination

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        soup = BeautifulSoup(html, "lxml")
        raise_if_removed(soup, self.options.get("removed_if"), ref.url)
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
        if isinstance(values.get("image"), str) and values["image"].startswith("//"):
            values["image"] = "https:" + values["image"]  # URL sans schéma (ex. og:image Hektor)
        if not values.get("price") and not title:
            return None
        if values.get("transaction") is None and (tmap := self.options.get("transaction_from_url")):
            values["transaction"] = next((v for k, v in tmap.items() if k in ref.url), None)
        if values.get("transaction") is None and (spec := self.options.get("transaction_from_text")):
            # Ex. { selector: "p.prix", rules: { "/\\s*mois": rent }, default: sale } : « 90 € /mois » → location.
            text = select_value(soup, spec["selector"]) or ""
            values["transaction"] = next((v for rx, v in spec["rules"].items() if re.search(rx, text, re.I)), spec.get("default"))
        return RawListing(
            source_id=self.source.id,
            source_ref=ref.source_ref,
            url=ref.url,
            features=features,
            # Les équipements lus dans une liste HTML sont des mentions textuelles.
            parsed_fields=[*parsed, *[f"features.{k}" for k in features]],
            **{k: v for k, v in values.items() if k in RawListing.model_fields},
        )
