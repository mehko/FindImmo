"""Dédoublonnage progressif.

* Niveau 1 — identité : même (source, identifiant d'origine) → même ``Listing`` (ID stable), et
  même URL normalisée entre sources → même bien.
* Niveau 2 — caractéristiques : même commune, même type, surfaces/prix/pièces très proches.
* Niveau 3 — score probabiliste : somme pondérée d'indices ; fusion automatique uniquement au-delà
  de ``AUTO_MERGE``. Entre ``CANDIDATE`` et ``AUTO_MERGE`` : « doublon possible », non fusionné.

Les annonces d'une même source ne sont jamais fusionnées par score (une agence publie rarement
deux fois le même bien, et deux lots identiques d'un même programme sont des biens distincts).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from ..geo import haversine_km
from ..models import DuplicateCandidate, Listing, ListingStatus, PropertyGroup, Provenance
from .normalize import normalize_url

AUTO_MERGE = 0.8
CANDIDATE = 0.55


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(a, b)


def score_pair(a: Listing, b: Listing) -> tuple[float, list[str]] | None:
    """Score de similarité dans [0, 1], ou ``None`` si incompatibilité certaine."""
    if a.source_id == b.source_id:
        return None
    if a.transaction and b.transaction and a.transaction != b.transaction:
        return None
    if a.property_type and b.property_type and a.property_type != b.property_type:
        return None
    if a.insee_code and b.insee_code and a.insee_code != b.insee_code:
        return None
    if not (a.surface and b.surface):
        return None  # sans surface des deux côtés, aucun rapprochement fiable n'est possible

    score, reasons = 0.0, []
    s = _rel(a.surface, b.surface)
    if s > 0.08:
        return None
    if s <= 0.02:
        score, reasons = score + 0.35, [*reasons, "surface identique"]
    else:
        score, reasons = score + 0.2, [*reasons, "surface proche"]

    if a.price and b.price:
        p = _rel(a.price, b.price)
        if p > 0.2:
            return None
        if p <= 0.03:
            score, reasons = score + 0.2, [*reasons, "prix identique"]
        elif p <= 0.1:
            score, reasons = score + 0.1, [*reasons, "prix proche"]

    if a.rooms and b.rooms:
        if abs(a.rooms - b.rooms) > 1:
            return None
        if a.rooms == b.rooms:
            score, reasons = score + 0.15, [*reasons, "même nombre de pièces"]
        else:
            score -= 0.1
    if a.bedrooms is not None and b.bedrooms is not None:
        if a.bedrooms == b.bedrooms:
            score, reasons = score + 0.05, [*reasons, "même nombre de chambres"]
        else:
            score -= 0.15
    if a.land_surface and b.land_surface:
        land = _rel(a.land_surface, b.land_surface)
        if land > 0.2:
            return None
        if land <= 0.05:
            score, reasons = score + 0.15, [*reasons, "terrain identique"]
    if a.dpe and b.dpe:
        if a.dpe == b.dpe:
            score, reasons = score + 0.05, [*reasons, "même DPE"]
        else:
            score -= 0.25

    exact_a = a.latitude is not None and a.provenance.get("latitude") != Provenance.ESTIMATED
    exact_b = b.latitude is not None and b.provenance.get("latitude") != Provenance.ESTIMATED
    if exact_a and exact_b:
        d = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)  # type: ignore[arg-type]
        if d > 3:
            return None
        if d < 0.15:
            score, reasons = score + 0.15, [*reasons, "coordonnées très proches"]
    if a.insee_code and a.insee_code == b.insee_code:
        score, reasons = score + 0.1, [*reasons, "même commune"]
    return round(min(score, 1.0), 3), reasons


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def deduplicate(listings: Iterable[Listing]) -> tuple[list[PropertyGroup], list[DuplicateCandidate]]:
    """Regroupe les annonces en biens. Modifie ``listing.property_id`` en place."""
    pool = [x for x in listings if x.status != ListingStatus.GONE]
    uf = _UnionFind()
    level: dict[str, int] = {}
    conf: dict[str, float] = {}

    by_url: dict[str, list[Listing]] = defaultdict(list)
    for x in pool:
        uf.find(x.id)
        by_url[normalize_url(x.url)].append(x)
    for group in by_url.values():
        for other in group[1:]:
            uf.union(group[0].id, other.id)
            level[other.id] = level[group[0].id] = 1

    # Blocage : on ne compare que les annonces d'une même commune (ou CP) et même transaction.
    blocks: dict[tuple[str | None, str | None], list[Listing]] = defaultdict(list)
    for x in pool:
        key = x.insee_code or x.postal_code
        if key and x.surface:
            blocks[(key, x.transaction)].append(x)

    candidates: list[DuplicateCandidate] = []
    for block in blocks.values():
        block.sort(key=lambda x: x.surface or 0)
        for i, a in enumerate(block):
            for b in block[i + 1 :]:
                if b.surface and a.surface and b.surface > a.surface * 1.09:
                    break  # trié par surface : les suivants sont trop grands
                res = score_pair(a, b)
                if res is None:
                    continue
                score, reasons = res
                if score >= AUTO_MERGE:
                    uf.union(a.id, b.id)
                    for lid in (a.id, b.id):
                        level.setdefault(lid, 2 if score >= 0.9 else 3)
                        conf[lid] = min(conf.get(lid, 1.0), score)
                elif score >= CANDIDATE:
                    candidates.append(DuplicateCandidate(a=a.id, b=b.id, score=score, reasons=reasons))

    members: dict[str, list[Listing]] = defaultdict(list)
    for x in pool:
        members[uf.find(x.id)].append(x)
    groups: list[PropertyGroup] = []
    for items in members.values():
        # ID de bien stable : l'annonce détectée en premier (puis ordre lexical) donne son ID.
        items.sort(key=lambda x: (x.first_seen_at, x.id))
        pid = "bien_" + items[0].id.removeprefix("fi_")
        for x in items:
            x.property_id = pid
        if len(items) > 1:
            groups.append(
                PropertyGroup(
                    id=pid,
                    listing_ids=[x.id for x in items],
                    confidence=min((conf.get(x.id, 1.0) for x in items), default=1.0),
                    level=max(level.get(x.id, 1) for x in items),
                )
            )
    for x in listings:
        if x.status == ListingStatus.GONE and x.property_id is None:
            x.property_id = "bien_" + x.id.removeprefix("fi_")
    # Les doublons possibles déjà fusionnés par transitivité n'ont plus lieu d'être signalés.
    candidates = [c for c in candidates if uf.find(c.a) != uf.find(c.b)]
    return groups, candidates
