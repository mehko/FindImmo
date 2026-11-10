"""Extraction générique de données structurées schema.org (JSON-LD).

Gère les formes rencontrées sur les sites d'agences : ``RealEstateListing`` → ``Offer`` →
``itemOffered`` (House/Apartment/…), ``Offer`` seul, ``Product`` avec ``offers``, ``@graph``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from bs4 import BeautifulSoup

from ..http import ListingRemoved
from ..models import ListingRef, RawListing
from ..textparse import (
    clean_text,
    parse_bedrooms,
    parse_int,
    parse_number,
    parse_rooms,
    parse_surface,
)
from .sitemap import SitemapConnector

PROPERTY_TYPES = {
    "house": "house",
    "singlefamilyresidence": "house",
    "apartment": "apartment",
    "apartmentcomplex": "building",
    "residence": "other",
    "accommodation": "other",
    "landform": "land",
    "place": "other",
}

AMENITY_MAP = {
    "parking": "parking",
    "parkingfacility": "parking",
    "garage": "garage",
    "cellar": "cellar",
    "cave": "cellar",
    "balcony": "balcony",
    "balcon": "balcony",
    "terrace": "terrace",
    "terrasse": "terrace",
    "garden": "garden",
    "jardin": "garden",
    "swimmingpool": "pool",
    "pool": "pool",
    "piscine": "pool",
    "elevator": "elevator",
    "lift": "elevator",
    "ascenseur": "elevator",
    "furnished": "furnished",
}


def extract_jsonld(html: str) -> list[dict[str, Any]]:
    """Tous les objets JSON-LD d'une page, ``@graph`` et listes aplatis."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, list):
            for o in obj:
                walk(o)
        elif isinstance(obj, dict):
            if "@graph" in obj:
                walk(obj["@graph"])
            if "@type" in obj:
                out.append(obj)

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.string or tag.get_text() or ""
        try:
            walk(json.loads(text))
        except json.JSONDecodeError:
            # Certains sites insèrent des retours à la ligne non échappés : seconde chance.
            try:
                walk(json.loads(re.sub(r"[\r\n\t]+", " ", text)))
            except json.JSONDecodeError:
                continue
    return out


def _types(obj: dict[str, Any]) -> set[str]:
    t = obj.get("@type", [])
    return {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _value(q: Any) -> Any:
    if isinstance(q, dict):
        return q.get("value")
    return q


def find_offer(objects: Iterable[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Retourne (listing, offer, item) en suivant les imbrications usuelles.

    Les références de graphe JSON-LD (``{"@id": "..."}``) sont résolues vers l'objet correspondant."""
    objects = list(objects)
    index = {o["@id"]: o for o in objects if isinstance(o.get("@id"), str)}

    def deref(value: Any) -> Any:
        value = _first(value)
        if isinstance(value, dict) and set(value) == {"@id"}:
            return index.get(value["@id"], value)
        return value

    def listing_score(obj: dict[str, Any]) -> int:
        # Plusieurs RealEstateListing peuvent coexister (enveloppe WebPage + fiche détaillée) : on prend la plus riche.
        return 3 if any(k in obj for k in ("mainEntity", "offers", "about")) else 2 if any(k in obj for k in ("address", "floorSize")) else 1

    listings = sorted((o for o in objects if "realestatelisting" in _types(o)), key=listing_score, reverse=True)
    for obj in listings[:1]:
        offer = deref(obj.get("mainEntity") or obj.get("offers") or obj.get("about"))
        if isinstance(offer, dict):
            if "itemOffered" in offer:
                item = deref(offer.get("itemOffered"))
            else:
                item = offer
                # Variante (plateformes Apimo) : le bien est dans « about », l'offre dans « offers ».
                about = deref(obj.get("about"))
                if offer is not about and isinstance(about, dict) and "offer" in _types(offer):
                    item = about
            return obj, offer, item if isinstance(item, dict) else None
        # Fiche sans offre (prix absent du JSON-LD) mais décrivant le bien elle-même (surface, adresse…).
        return (obj, None, obj) if listing_score(obj) == 2 else (obj, None, None)
    for obj in objects:
        types = _types(obj)
        if "offer" in types and isinstance(deref(obj.get("itemOffered")), dict):
            return None, obj, deref(obj["itemOffered"])
        if types & {"product", "house", "apartment", "singlefamilyresidence", "residence"} and obj.get("offers"):
            offer = deref(obj["offers"])
            offer = offer if isinstance(offer, dict) else None
            # Variante (Netty) : le bien détaillé est dans offers.itemOffered, le Product n'est qu'une enveloppe.
            offered = deref(offer.get("itemOffered")) if offer else None
            if isinstance(offered, dict):
                return obj, offer, offered  # l'enveloppe fournit nom, description et image de repli
            return None, offer, obj
    return None, None, None


def raw_from_jsonld(objects: list[dict[str, Any]], source_id: str, source_ref: str, url: str) -> RawListing | None:
    listing, offer, item = find_offer(objects)
    if offer is None and item is None:
        return None
    listing = listing or {}
    offer = offer or {}
    item = item or {}
    parsed: list[str] = []

    price = parse_number(offer.get("price") or _value(offer.get("priceSpecification")))
    business = str(offer.get("businessFunction") or "").lower()
    transaction = "rent" if ("lease" in business or "rent" in business) else ("sale" if "sell" in business else None)

    # Plusieurs types peuvent coexister (ex. ["Apartment", "Accommodation"]) : on retient le plus
    # précis, indépendamment de l'ordre (``_types`` renvoie un ensemble).
    candidates = {PROPERTY_TYPES[t] for t in _types(item) if t in PROPERTY_TYPES}
    ptype = next(iter(sorted(candidates - {"other"})), "other" if candidates else None)

    name = clean_text(item.get("name") or listing.get("name") or offer.get("name"))
    description = clean_text(item.get("description") or listing.get("description") or offer.get("description"))

    surface = parse_number(_value(item.get("floorSize")))
    if surface is None and name and (surface := parse_surface(name)) is not None:
        parsed.append("surface")
    rooms = parse_int(_value(item.get("numberOfRooms")))
    if rooms is None and name and (rooms := parse_rooms(name)) is not None:
        parsed.append("rooms")
    bedrooms = parse_int(_value(item.get("numberOfBedrooms")))
    if bedrooms is None and name and (bedrooms := parse_bedrooms(name)) is not None:
        parsed.append("bedrooms")

    address = _first(item.get("address")) or {}
    geo = _first(item.get("geo")) or {}

    features: dict[str, bool] = {}
    for a in item.get("amenityFeature") or []:
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            key = AMENITY_MAP.get(re.sub(r"[^a-z]", "", a["name"].lower()))
            val = a.get("value")
            if key and isinstance(val, bool):
                features[key] = val
    props: dict[str, Any] = {}
    for p in item.get("additionalProperty") or []:
        if isinstance(p, dict) and isinstance(p.get("name"), str):
            props[re.sub(r"[^a-z]", "", p["name"].lower())] = p.get("value")
    if isinstance(props.get("furnished"), bool):
        features["furnished"] = props["furnished"]

    dpe = props.get("energyclass") or props.get("dpe") or props.get("classeenergie")
    ges = props.get("gesclass") or props.get("ges") or props.get("classeges")
    land = parse_number(_value(item.get("lotSize")) or props.get("landsurface") or props.get("surfaceterrain"))

    image = _first(item.get("image") or listing.get("image") or offer.get("image"))
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")

    return RawListing(
        source_id=source_id,
        source_ref=source_ref,
        url=next((str(u) for u in (listing.get("url"), offer.get("url")) if str(u or "").startswith(("http://", "https://"))), url),
        title=name,
        description=description,
        transaction=transaction,
        property_type=ptype,
        price=price,
        surface=surface,
        land_surface=land,
        rooms=rooms,
        bedrooms=bedrooms,
        city=clean_text(address.get("addressLocality")) if isinstance(address, dict) else None,
        postal_code=str(address.get("postalCode")).strip() if isinstance(address, dict) and address.get("postalCode") else None,
        latitude=parse_number(geo.get("latitude")) if isinstance(geo, dict) else None,
        longitude=parse_number(geo.get("longitude")) if isinstance(geo, dict) else None,
        dpe=str(dpe).strip().upper() if dpe else None,
        ges=str(ges).strip().upper() if ges else None,
        features=features,
        published_at=listing.get("datePosted") or offer.get("validFrom"),
        image=image if isinstance(image, str) else None,
        parsed_fields=parsed,
    )


class JsonLdConnector(SitemapConnector):
    """Sitemap → pages détail → JSON-LD schema.org. Fonctionne pour tout site exposant
    ``RealEstateListing``/``Offer`` sans code spécifique : seule la configuration change."""

    method = "sitemap_jsonld"

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        raw = raw_from_jsonld(extract_jsonld(html), self.source.id, ref.source_ref, ref.url)
        if raw is None:
            raw = self._fallback(html, ref)
        if raw is None:
            return None
        soup = None
        if self.options.get("removed_if") or self.options.get("supplement_fields"):
            from .html import extract_fields, raise_if_removed  # import local : évite un cycle jsonld ↔ html

            soup = BeautifulSoup(html, "lxml")
            raise_if_removed(soup, self.options.get("removed_if"), ref.url)
            # Champs que le JSON-LD ne donne pas (ex. prix) lus dans le HTML ; le JSON-LD reste prioritaire.
            for field, value in extract_fields(soup, self.options.get("supplement_fields") or {}).items():
                if field in RawListing.model_fields and getattr(raw, field, None) in (None, "", {}):
                    setattr(raw, field, value)
                    raw.parsed_fields = [*raw.parsed_fields, field]
        # Mention « vendu » dans le titre/la description (option ``removed_markers``, regex).
        markers = self.options.get("removed_markers") or []
        texts = (raw.title or "", raw.description or "")
        if any(re.search(rx, text, re.I) for rx in markers for text in texts):
            raise ListingRemoved(ref.url, "annonce marquée vendue")
        if self.options.get("removed_if_no_price") and not raw.price:
            # Netty : un bien vendu reste dans le sitemap avec « price: 0 » et un bandeau « Vendu ».
            raise ListingRemoved(ref.url, "annonce sans prix (bien vendu)")
        # Transaction déduite de l'URL quand le JSON-LD ne la précise pas.
        if raw.transaction is None and (tmap := self.options.get("transaction_from_url")):
            for needle, value in tmap.items():
                if needle in ref.url:
                    raw.transaction = value
                    break
        # … ou du titre (ex. « Appartement F2 à vendre »), quand l'URL ne la contient pas.
        if raw.transaction is None and (tmap := self.options.get("transaction_from_title")) and raw.title:
            title = raw.title.lower()
            for needle, value in tmap.items():
                if needle.lower() in title:
                    raw.transaction = value
                    break
        if raw.transaction is None and (default := self.options.get("default_transaction")):
            raw.transaction = default  # site ne proposant qu'un seul type de transaction
        if raw.property_type is None and (pmap := self.options.get("property_type_from_url")):
            raw.property_type = next((v for k, v in pmap.items() if k in ref.url), None)
        return raw


    def fetch_detail(self, ref: ListingRef) -> RawListing | None:
        """Certains sites servent par intermittence une page de liste à la place de l'annonce
        (observé chez Citya, HTTP 200). Ce n'est pas une preuve de retrait : on retente une fois ;
        en cas de nouvel échec, l'annonce sera retentée à la collecte suivante, sans changer son statut."""
        html = self.fetch_page(ref.url)
        raw = self.parse_detail(html, ref)
        if raw is None and _is_listing_page(html):
            self.ctx.client._sleep(float(self.options.get("retry_delay_seconds", 5)))
            html = self.fetch_page(ref.url)
            raw = self.parse_detail(html, ref)
            if raw is None and _is_listing_page(html):
                self.last_page_info = f"page de liste reçue à la place de l'annonce (2 essais) — {self.last_page_info}"
        return raw

    def _fallback(self, html: str, ref: ListingRef) -> RawListing | None:
        """Repli HTML (``options.fallback_fields``) pour les pages sans JSON-LD.

        Tous les champs obtenus ainsi sont marqués ``parsed`` (lus dans le texte de la page)."""
        from .html import extract_fields  # import local : évite un cycle jsonld ↔ html

        fields = self.options.get("fallback_fields")
        if not fields:
            return None
        values = extract_fields(BeautifulSoup(html, "lxml"), fields)
        title = values.get("title")
        if not title or values.get("price") is None:
            return None
        values.setdefault("surface", parse_surface(title))
        values.setdefault("rooms", parse_rooms(title))
        values.setdefault("bedrooms", parse_bedrooms(title))
        values.setdefault("property_type", title)
        values.setdefault("postal_code", ref.postal_code_hint)
        values = {k: v for k, v in values.items() if v is not None and k in RawListing.model_fields}
        return RawListing(
            source_id=self.source.id,
            source_ref=ref.source_ref,
            url=ref.url,
            parsed_fields=[k for k in values if k not in ("title", "image", "description", "postal_code")],
            **values,
        )


def _is_listing_page(html: str) -> bool:
    return any(_types(o) & {"offercatalog", "itemlist", "searchresultspage"} for o in extract_jsonld(html))
