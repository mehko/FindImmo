"""Normalisation : ``RawListing`` → champs normalisés d'un ``Listing`` + provenance par champ."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..config import SourceConfig
from ..geo import GeoIndex, department_from_postal_code
from ..models import DPE_CLASSES, FEATURE_KEYS, PropertyType, Provenance, RawListing, TransactionType
from ..textparse import clean_text, parse_bedrooms, parse_energy_class, parse_features, parse_land_surface

TRANSACTION_SYNONYMS = {
    "sale": TransactionType.SALE,
    "vente": TransactionType.SALE,
    "vendre": TransactionType.SALE,  # « A vendre »
    "achat": TransactionType.SALE,
    "acheter": TransactionType.SALE,
    "sell": TransactionType.SALE,
    "rent": TransactionType.RENT,
    "location": TransactionType.RENT,
    "louer": TransactionType.RENT,
    "lease": TransactionType.RENT,
}

PROPERTY_SYNONYMS = {
    "apartment": PropertyType.APARTMENT,
    "appartement": PropertyType.APARTMENT,
    "studio": PropertyType.APARTMENT,
    "duplex": PropertyType.APARTMENT,
    "loft": PropertyType.APARTMENT,
    "house": PropertyType.HOUSE,
    "maison": PropertyType.HOUSE,
    "villa": PropertyType.HOUSE,
    "propriete": PropertyType.HOUSE,
    "land": PropertyType.LAND,
    "terrain": PropertyType.LAND,
    "parking": PropertyType.PARKING,
    "garage": PropertyType.PARKING,
    "box": PropertyType.PARKING,
    "commercial": PropertyType.COMMERCIAL,
    "bureau": PropertyType.COMMERCIAL,
    "local": PropertyType.COMMERCIAL,
    "building": PropertyType.BUILDING,
    "immeuble": PropertyType.BUILDING,
    "other": PropertyType.OTHER,
}

FRANCE_BBOX = (41.0, 51.6, -5.8, 10.0)


def listing_id(source_id: str, source_ref: str) -> str:
    """Identifiant FindImmo stable : ne dépend que de la source et de l'identifiant d'origine."""
    return "fi_" + hashlib.sha1(f"{source_id}:{source_ref}".encode()).hexdigest()[:12]


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), path, "", ""))


def _map(value: str | None, table: dict[str, Any]) -> Any:
    if not value:
        return None
    v = value.strip().lower()
    if v in table:
        return table[v]
    for key, mapped in table.items():
        if key in v:
            return mapped
    return None


def _range(value: float | int | None, lo: float, hi: float) -> Any:
    return value if value is not None and lo <= value <= hi else None


def normalize(raw: RawListing, source: SourceConfig, geo: GeoIndex) -> dict[str, Any]:
    prov: dict[str, Provenance] = {}
    for f in raw.parsed_fields:
        prov[f] = Provenance.PARSED

    description = clean_text(raw.description)
    title = clean_text(raw.title)

    commune = geo.resolve(raw.city, raw.postal_code, raw.insee_code)
    postal = raw.postal_code if raw.postal_code and re.fullmatch(r"\d{5}", raw.postal_code) else None
    if commune:
        department, city, insee = commune.department, commune.name, commune.insee
        if postal is not None and commune.postal_codes and postal not in commune.postal_codes:
            postal = None  # code incohérent avec la commune (souvent un code INSEE)
        if postal is None and len(commune.postal_codes) == 1:
            postal = commune.postal_codes[0]
            prov["postal_code"] = Provenance.COMPUTED
    else:
        department, city, insee = department_from_postal_code(postal), clean_text(raw.city), raw.insee_code
    if department:
        prov["department"] = Provenance.COMPUTED

    lat, lon = raw.latitude, raw.longitude
    if not (lat is not None and lon is not None and FRANCE_BBOX[0] <= lat <= FRANCE_BBOX[1] and FRANCE_BBOX[2] <= lon <= FRANCE_BBOX[3]):
        lat = lon = None
        if commune and commune.lat is not None:
            lat, lon = commune.lat, commune.lon
            prov["latitude"] = prov["longitude"] = Provenance.ESTIMATED

    features: dict[str, bool] = {}
    for key, value in raw.features.items():
        if key not in FEATURE_KEYS:
            continue
        if value or source.trust_false_features:
            features[key] = bool(value)
    for key in parse_features(description):
        if key not in features:
            features[key] = True
            prov[f"features.{key}"] = Provenance.PARSED

    land = _range(raw.land_surface, 1, 1_000_000)
    if land is None and (land := _range(parse_land_surface(description), 1, 1_000_000)) is not None:
        prov["land_surface"] = Provenance.PARSED
    bedrooms = _range(raw.bedrooms, 0, 50)
    if bedrooms is None and (bedrooms := _range(parse_bedrooms(description), 1, 50)) is not None:
        prov["bedrooms"] = Provenance.PARSED

    dpe = raw.dpe.strip().upper()[:1] if raw.dpe else None
    if dpe not in DPE_CLASSES:
        dpe = None
    if dpe is None and (dpe := parse_energy_class(description, "dpe")):
        prov["dpe"] = Provenance.PARSED
    ges = raw.ges.strip().upper()[:1] if raw.ges else None
    if ges not in DPE_CLASSES:
        ges = None

    price = _range(raw.price, 1, 1_000_000_000)
    surface = _range(raw.surface, 1, 100_000)
    transaction = _map(raw.transaction, TRANSACTION_SYNONYMS)
    ppm2 = None
    if price and surface and surface >= 9:
        ppm2 = round(price / surface, 2 if transaction == TransactionType.RENT else 0)
        prov["price_per_m2"] = Provenance.COMPUTED

    return {
        "source_id": raw.source_id,
        "source_ref": raw.source_ref,
        "url": raw.url,
        "transaction": transaction,
        "property_type": _map(raw.property_type, PROPERTY_SYNONYMS),
        "title": title,
        "description": description[:1000] if description else None,
        "price": price,
        "price_per_m2": ppm2,
        "surface": surface,
        "land_surface": land,
        "rooms": _range(raw.rooms, 1, 100),
        "bedrooms": bedrooms,
        "city": city,
        "postal_code": postal,
        "insee_code": insee,
        "department": department,
        "latitude": lat,
        "longitude": lon,
        "dpe": dpe,
        "ges": ges,
        "features": features,
        "provenance": {k: v for k, v in prov.items()},
        "image": raw.image,
        "agency": raw.agency,
        "published_at": raw.published_at,
        "is_demo": source.is_demo,
    }


# Champs dont la modification constitue un « changement de caractéristiques »
TRACKED_FIELDS = ("surface", "land_surface", "rooms", "bedrooms", "dpe", "property_type", "features")
