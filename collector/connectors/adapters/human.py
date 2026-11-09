"""Adaptateur pour la plateforme du réseau HUMAN Immobilier (www.human-immobilier.fr).

Particularité : le sitemap du site ne contient aucune URL d'annonce (agences et pages
territoriales seulement). Méthode (vérifiée le 2026-11-09, robots.txt respecté) :

* découverte : pages de résultats par commune (``/achat-immobilier-<commune>?page=N``). Au-delà de
  la dernière page, le site redirige vers la recherche nationale : on s'arrête dès qu'une page est
  redirigée, et on ne retient que les annonces dont l'URL porte une commune de ``options.cities``
  (``/annonce-achat-appartement-colombes_415-1149``) ;
* détail : JSON-LD ``RealEstateListing`` (prix, surface, pièces, CP, DPE/GES) ;
  équipements lus dans la description. Les annonces marquées « Vendu » sont signalées retirées.
  Les coordonnées GPS de la page sont celles de l'agence : elles sont volontairement ignorées.

Options : ``list_pages`` (URL de résultats), ``cities`` (slugs acceptés), ``max_pages`` (défaut 10).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from html import unescape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ...http import ListingRemoved
from ...models import ListingRef, RawListing
from ...textparse import parse_features
from ..jsonld import JsonLdConnector

LINK_PATTERN = re.compile(
    r"/annonce-(?P<transaction>achat|location)-(?P<type>[a-z-]+?)-(?P<city>[a-z0-9-]+)_(?P<ref>\d+-\d+)$"
)
TRANSACTIONS = {"achat": "sale", "location": "rent"}


class HumanConnector(JsonLdConnector):
    method = "adapter"

    def discover(self) -> Iterator[ListingRef]:
        cities = set(self.options.get("cities") or [])
        max_pages = int(self.options.get("max_pages", 10))
        seen: set[str] = set()
        for base in self.options["list_pages"]:
            for page in range(1, max_pages + 1):
                url = base if page == 1 else f"{base}?page={page}"
                result = self.ctx.client.get(url)
                if urlsplit(result.url).path.rstrip("/") != urlsplit(url).path.rstrip("/"):
                    break  # page inexistante : redirection vers la recherche nationale
                found = 0
                for a in BeautifulSoup(result.text, "lxml").select("a[href]"):
                    href = str(a.get("href", ""))
                    m = LINK_PATTERN.search(urlsplit(href).path)
                    if not m or m["ref"] in seen or (cities and m["city"] not in cities):
                        continue
                    seen.add(m["ref"])
                    found += 1
                    if ref := self.ref_from_match(urljoin(base, href), m, None):
                        yield ref
                if not found:
                    break

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        if re.search(r'<span class="prix">\s*Vendu\s*</span>', html):
            raise ListingRemoved(ref.url, "annonce vendue")
        raw = super().parse_detail(html, ref)
        if raw is None:
            return None
        if raw.description:
            raw.description = unescape(raw.description)
            raw.features = parse_features(raw.description)
            raw.parsed_fields = [*raw.parsed_fields, *[f"features.{k}" for k in raw.features]]
        if raw.title:
            raw.title = unescape(raw.title)
        if raw.transaction is None and (m := LINK_PATTERN.search(urlsplit(ref.url).path)):
            raw.transaction = TRANSACTIONS[m["transaction"]]
        return raw
