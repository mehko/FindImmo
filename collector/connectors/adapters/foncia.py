"""Adaptateur pour le site national Foncia (fr.foncia.com).

Méthode (vérifiée le 2026-11-09, robots.txt respecté) :

* découverte : sous-sitemaps ``achat-annonce.xml`` (~11 500 annonces) et ``location-annonce.xml``
  (~10 600). L'URL contient la commune et le code postal (``/achat/colombes-92700/appartement/00839272.htm``)
  ou seulement le département pour les villes multi-codes (``/achat/paris-75/…``) : le pré-filtrage
  géographique se fait donc sans aucune requête ;
* détail : la page Angular embarque, dans ``<script id="serverApp-state">``, la réponse JSON de l'API
  d'annonce du site (clé ``GET.…/annonces/annonces/<transaction|location>/<réf>``), au format d'échappement
  Angular (``&q;`` pour ``"``…). C'est la source la plus complète (prix/loyer, surface, pièces, DPE/GES,
  équipements) : le JSON-LD de la page n'a pas le prix. Aucun appel direct à l'API : seule la page
  publique est lue ;
* les annonces dont le statut n'est plus ``active`` (le sitemap en contient) sont signalées retirées ;
* GPS ignoré : la précision des coordonnées n'est pas documentée ; chambres non fournies par le site.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from ...http import ListingRemoved
from ...models import ListingRef, RawListing
from ...textparse import clean_text, parse_number
from ..sitemap import SitemapConnector

DEFAULT_SITEMAPS = ["https://fr.foncia.com/achat-annonce.xml", "https://fr.foncia.com/location-annonce.xml"]
DEFAULT_URL_PATTERN = (
    r"/(?P<transaction>achat|location)/(?P<city>[^/]+?)-(?:(?P<postal_code>\d{5})|(?P<department>\d{2,3}))/"
    r"(?P<type>[^/]+)/(?P<ref>\d+)\.htm$"
)
TYPE_MAP = {
    "appartement": "apartment",
    "appartement-meuble": "apartment",
    "maison": "house",
    "terrain": "land",
    "immeuble": "building",
    "parking": "parking",
    "local-commercial": "commercial",
}
FEATURE_KEYS = {
    "ascenseur": "elevator",
    "cave": "cellar",
    "balcon": "balcony",
    "jardin": "garden",
    "piscine": "pool",
    "garage": "garage",
}
ENERGY_LETTERS = set("ABCDEFG")
_ANGULAR_ESCAPES = (("&q;", '"'), ("&s;", "'"), ("&l;", "<"), ("&g;", ">"), ("&a;", "&"))  # « &a; » en dernier
_ANNONCE_KEY = re.compile(r"^GET\..*/annonces/annonces/[a-z]+/\d+\.?$")


def parse_annonce(html: str) -> dict[str, Any] | None:
    """Décode la fiche annonce embarquée dans ``serverApp-state``."""
    node = BeautifulSoup(html, "lxml").find("script", id="serverApp-state")
    if node is None or not node.string:
        return None
    text = node.string
    for escaped, char in _ANGULAR_ESCAPES:
        text = text.replace(escaped, char)
    try:
        state = json.loads(text)
    except ValueError:
        return None
    for key, value in state.items():
        if _ANNONCE_KEY.match(key.split("?")[0]) and isinstance(value, dict) and isinstance(value.get("body"), dict):
            return value["body"]
    return None


def _positive(value: Any) -> float | None:
    number = parse_number(value)
    return number if number and number > 0 else None


def _letter(value: Any) -> str | None:
    letter = str(value or "").strip().upper()
    return letter if letter in ENERGY_LETTERS else None


class FonciaConnector(SitemapConnector):
    method = "adapter:foncia"

    def sitemap_urls(self) -> list[str]:
        return list(self.options.get("sitemaps") or DEFAULT_SITEMAPS)

    def discover(self):  # type: ignore[override]
        self.options.setdefault("url_pattern", DEFAULT_URL_PATTERN)
        yield from super().discover()

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        item = parse_annonce(html)
        if item is None:
            return None
        if item.get("status") != "active" or item.get("isPrivate"):
            raise ListingRemoved(ref.url, f"annonce non active ({item.get('status')})")

        rent = item.get("typeAnnonce") == "location" or "/location/" in ref.url
        slug = re.search(r"/(?:achat|location)/[^/]+/([^/]+)/", ref.url)
        type_slug = slug[1] if slug else str(item.get("typeBien") or "")
        place = item.get("localisation") if isinstance(item.get("localisation"), dict) else {}
        surface = item.get("surface") if isinstance(item.get("surface"), dict) else {}
        carac = item.get("caracteristiques") if isinstance(item.get("caracteristiques"), dict) else {}

        features = {
            name: True for key, name in FEATURE_KEYS.items()
            if isinstance(carac.get(key), dict) and carac[key].get("available") is True
        }
        if type_slug == "appartement-meuble":
            features["furnished"] = True
        titles = item.get("titles") if isinstance(item.get("titles"), dict) else {}
        description = item.get("description")
        og = BeautifulSoup(html, "lxml").find("meta", attrs={"property": "og:image"})
        rooms = item.get("nbPiece")
        postal = place.get("codePostal")

        return RawListing(
            source_id=self.source.id,
            source_ref=ref.source_ref,
            url=ref.url,
            title=clean_text(titles.get("main")),
            description=clean_text(description) if isinstance(description, str) else None,
            transaction="rent" if rent else "sale",
            property_type=TYPE_MAP.get(type_slug, "other"),
            price=_positive(item.get("loyer") if rent else item.get("prixVente")),
            surface=_positive(surface.get("habitable")) or _positive(surface.get("totale")),
            rooms=int(rooms) if isinstance(rooms, int | float) and rooms > 0 else None,
            city=clean_text(place.get("ville")),
            postal_code=str(postal) if postal else None,
            dpe=_letter(item.get("noteConsoEnergie")),
            ges=_letter(item.get("noteEmissionGES")),
            features=features,
            published_at=str(item["datePublication"])[:10] if item.get("datePublication") else None,
            image=str(og["content"]) if og and og.get("content") else None,
        )
