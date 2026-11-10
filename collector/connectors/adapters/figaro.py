"""Adaptateur pour Le Figaro Immobilier (immobilier.lefigaro.fr) — **sous autorisation écrite**.

⚠ Les conditions d'utilisation du site (article 6) interdisent toute collecte automatisée et toute extraction
substantielle de leurs bases sans autorisation écrite préalable de Figaro Classifieds. Cette source ne doit être
activée que dans le cadre d'un accord écrit dont les termes (périmètre, fréquence, publication) sont respectés ;
voir ``docs/SOURCES.md``. ``robots.txt`` reste appliqué (listes et pagination ``?page=N`` autorisées ;
``/api/``, ``/recherche/`` et les URL à paramètres interdits : jamais utilisés).

Méthode (vérifiée le 2026-11-10) :

* découverte : pages de liste d'une commune (``/annonces/immobilier-vente-bien-<commune>+<cp>.html``, et ``-location-``),
  paginées par ``?page=N``. Le site est une application Nuxt : chaque page embarque, dans
  ``<script id="__NUXT_DATA__">`` (format « devalue »), la réponse de sa liste (``classifiedsListResponse``) avec les
  annonces **complètes** (prix, surface, pièces, DPE, agence, photos…) : aucune fiche n'est téléchargée ;
* ⚠ au-delà de la dernière page annoncée (``pagination.totalPage`` de la 1re page), le site renvoie une liste générique :
  on s'arrête strictement à ce total ;
* les éléments sponsorisés réapparaissent sur plusieurs pages : dédoublonnage par identifiant ;
* pages lourdes (~1,9 Mo décompressées) : délai poli élevé et périmètre limité par configuration.

Options : ``list_pages`` (URL de liste), ``max_pages`` (garde-fou, défaut 60).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup

from ...models import ListingRef, RawListing
from ...textparse import clean_text
from ..base import BaseConnector

TAGS = {"ShallowReactive", "Reactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef"}
FEATURES = {
    "terrasse": "terrace", "ascenseur": "elevator", "parking": "parking", "balcon": "balcony",
    "garage": "garage", "jardin": "garden", "cave": "cellar", "piscine": "pool",
}
ENERGY_LETTERS = set("ABCDEFG")
TYPE_MAP = {  # types du site que la normalisation ne reconnaîtrait pas ; les autres (« appartement neuf », « maison neuve »…) passent tels quels
    "locaux professionnels": "commercial",
    "chambre": "other",
    "propriété": "house",
    "viager": "other",
}


def decode_nuxt(raw: str) -> Any:
    """Décode le format « devalue » de Nuxt (tableau de valeurs dont les objets pointent par indice)."""
    data = json.loads(raw)
    cache: dict[int, Any] = {}

    def resolve(index: int) -> Any:
        if index in cache:
            return cache[index]
        value = data[index]
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            cache[index] = out
            for key, ref in value.items():
                out[key] = resolve(ref) if isinstance(ref, int) and ref >= 0 else None
            return out
        if isinstance(value, list):
            if value and isinstance(value[0], str) and value[0] in TAGS:
                cache[index] = resolve(value[1])
                return cache[index]
            items: list[Any] = []
            cache[index] = items
            items.extend(resolve(ref) if isinstance(ref, int) and ref >= 0 else None for ref in value)
            return items
        cache[index] = value
        return value

    return resolve(0)


def parse_list(html: str) -> tuple[list[dict[str, Any]], int | None, int | None] | None:
    """(annonces, page courante, nombre total de pages) d'une page de liste, ou ``None`` si la structure a changé."""
    node = BeautifulSoup(html, "lxml").find("script", id="__NUXT_DATA__")
    if node is None or not node.string:
        return None
    try:
        response = decode_nuxt(node.string)["data"]["classifiedsListResponse"]
        items = [i for i in response["classifieds"] if isinstance(i, dict)]
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    pagination = response.get("pagination") if isinstance(response.get("pagination"), dict) else {}
    return items, pagination.get("currentPage"), pagination.get("totalPage")


def _letter(value: Any) -> str | None:
    letter = str(value or "").strip().upper()
    return letter if letter in ENERGY_LETTERS else None


def _positive(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and value > 0 else None


def raw_from_item(item: dict[str, Any], source_id: str) -> RawListing | None:
    if not item.get("id") or not item.get("recordLink"):
        return None
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    client = item.get("client") if isinstance(item.get("client"), dict) else {}
    dpe = item.get("dpe") if isinstance(item.get("dpe"), dict) else {}
    rooms = item.get("roomCount")
    rooms = rooms[0] if isinstance(rooms, list) and rooms else rooms
    photos = ((item.get("images") or {}).get("photos") or []) if isinstance(item.get("images"), dict) else []
    first = photos[0] if photos and isinstance(photos[0], dict) else {}
    image = (first.get("url") or {}).get("medium") if isinstance(first.get("url"), dict) else None
    features = {FEATURES[o]: True for o in (item.get("options") or []) if isinstance(o, str) and o in FEATURES}
    city = re.sub(r"\s*\(\d{2,3}\)\s*$", "", str(location.get("city") or "")) or None
    description = item.get("description")
    kind = str(item.get("type") or "")
    area = _positive(item.get("area"))
    title = clean_text(" ".join(x for x in (kind, str(item.get("roomCountLabel") or ""), f"{area:g} m²" if area else "") if x)
                       + (f" - {city}" if city else ""))
    return RawListing(
        source_id=source_id,
        source_ref=str(item["id"]),
        url=str(item["recordLink"]),
        title=title,
        description=clean_text(description) if isinstance(description, str) else None,
        transaction=item.get("transaction"),
        property_type=TYPE_MAP.get(kind, kind) or None,
        price=_positive(item.get("price")),
        surface=area,
        rooms=int(rooms) if isinstance(rooms, int | float) and rooms > 0 else None,
        bedrooms=int(item["bedRoomCount"]) if isinstance(item.get("bedRoomCount"), int) and item["bedRoomCount"] > 0 else None,
        city=clean_text(city),
        postal_code=str(location["postalCode"]) if location.get("postalCode") else None,
        dpe=_letter(dpe.get("energyCategory")),
        ges=_letter(dpe.get("gesCategory")),
        features=features,
        published_at=str(item["firstPublicationDate"])[:10] if item.get("firstPublicationDate") else None,
        image=image if isinstance(image, str) else None,
        agency=clean_text(client.get("brandName") or client.get("name")),
    )


class FigaroConnector(BaseConnector):
    method = "adapter:figaro"

    def discover(self) -> Iterator[ListingRef]:
        max_pages = int(self.options.get("max_pages", 60))
        seen: set[str] = set()
        for base in self.options["list_pages"]:
            total: int | None = None
            for page in range(1, max_pages + 1):
                parsed = parse_list(self.ctx.client.get(base if page == 1 else f"{base}?page={page}").text)
                if parsed is None:
                    # Structure inattendue : la découverte ne doit pas passer pour exhaustive.
                    raise ValueError(f"liste introuvable dans {base} (page {page})")
                items, current, page_total = parsed
                if page == 1:
                    total = page_total  # seul le total de la 1re page fait foi (la page « 29 » annonce 100 pages)
                elif current != page:
                    break
                for item in items:
                    raw = raw_from_item(item, self.source.id)
                    if raw is not None and raw.source_ref not in seen:
                        seen.add(raw.source_ref)
                        yield self.make_ref(raw.source_ref, raw.url, postal_code_hint=raw.postal_code, raw=raw)
                if not total or page >= total:
                    break
