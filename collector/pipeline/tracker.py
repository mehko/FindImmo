"""Application d'un lot de collecte à l'état : création/mise à jour, historique de prix, cycle de vie.

Cycle de vie d'une annonce :

``active`` ──(absente d'une découverte exhaustive)──► ``unavailable_unconfirmed``
     ▲                                                    │ (absente ≥ N fois et ≥ X jours)
     └──────────────(revue)─── ``reappeared`` ◄──────── ``gone``

Une source en échec (ou dont la découverte est partielle) ne modifie jamais le statut de ses annonces.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import Settings, SourceConfig
from ..geo import GeoIndex
from ..models import (
    EventType,
    Listing,
    ListingEvent,
    ListingStatus,
    PricePoint,
    SourceBatch,
)
from .normalize import TRACKED_FIELDS, listing_id, normalize
from .state import RefInfo, State


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class RunStats:
    observed: int = 0
    new: int = 0
    price_drops: int = 0
    price_increases: int = 0
    features_changed: int = 0
    unavailable: int = 0
    reappeared: int = 0
    gone: int = 0
    out_of_scope: int = 0
    per_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def bump(self, source_id: str, key: str, n: int = 1) -> None:
        setattr(self, key, getattr(self, key) + n)
        self.per_source.setdefault(source_id, {}).setdefault(key, 0)
        self.per_source[source_id][key] += n


class Tracker:
    def __init__(self, state: State, sources: dict[str, SourceConfig], geo: GeoIndex, departments: set[str], settings: Settings, now: str | None = None):
        self.state = state
        self.sources = sources
        self.geo = geo
        self.departments = departments
        self.settings = settings
        self.now = now or now_iso()
        self.stats = RunStats()

    # ------------------------------------------------------------------ événements
    def _event(self, type_: EventType, listing: Listing, old: Any = None, new: Any = None) -> None:
        eid = hashlib.sha1(f"{listing.id}:{type_}:{self.now}".encode()).hexdigest()[:14]
        self.state.events.append(
            ListingEvent(id=eid, type=type_, at=self.now, listing_id=listing.id, property_id=listing.property_id,
                         department=listing.department, old=old, new=new)
        )
        key = {
            EventType.NEW: "new",
            EventType.PRICE_DROP: "price_drops",
            EventType.PRICE_INCREASE: "price_increases",
            EventType.FEATURES_CHANGED: "features_changed",
            EventType.UNAVAILABLE: "unavailable",
            EventType.REAPPEARED: "reappeared",
            EventType.GONE: "gone",
        }[type_]
        self.stats.bump(listing.source_id, key)

    def _mark_seen(self, listing: Listing) -> None:
        if listing.status != ListingStatus.ACTIVE:
            self._event(EventType.REAPPEARED, listing, old=listing.status.value, new=ListingStatus.ACTIVE.value)
        listing.status = ListingStatus.ACTIVE
        listing.last_seen_at = self.now
        listing.unseen_count = 0
        listing.unseen_since = None

    # ------------------------------------------------------------------ application d'un lot
    def apply(self, batch: SourceBatch) -> None:
        sid = batch.status.source_id
        source = self.sources.get(sid)
        if source is None:
            return
        src_state = self.state.source_state(sid)
        refs = self.state.source_refs(sid)
        src_state.last_attempt_at = batch.status.started_at
        src_state.backlog = batch.status.backlog
        src_state.last_errors = batch.status.errors[-10:]
        if batch.status.ok:
            src_state.last_success_at = batch.status.finished_at or self.now
            src_state.consecutive_failures = 0
            src_state.last_status = "ok" if batch.status.discovery_complete and not batch.status.details_failed else "partial"
        else:
            src_state.consecutive_failures += 1
            src_state.last_status = "error"

        scope = self.departments & set(source.departments or self.departments)
        for ref in batch.out_of_scope_refs:
            refs.out_of_scope[ref] = self.now[:10]
        for raw in batch.listings:
            values = normalize(raw, source, self.geo)
            if values["department"] not in scope:
                refs.out_of_scope[raw.source_ref] = self.now[:10]
                self.stats.bump(sid, "out_of_scope")
                continue
            self._upsert(values)
            refs.fetched[raw.source_ref] = RefInfo(lastmod=batch.lastmods.get(raw.source_ref), fetched_at=self.now)

        seen_ids = {listing_id(sid, r) for r in batch.seen_refs}
        for lid in seen_ids:
            if (listing := self.state.listings.get(lid)) is not None:
                self._mark_seen(listing)
                self.stats.bump(sid, "observed")

        if batch.status.ok and batch.status.discovery_complete:
            self._mark_unseen(sid, seen_ids)
        src_state.listings_count = sum(
            1 for x in self.state.listings.values() if x.source_id == sid and x.status != ListingStatus.GONE
        )

    def _upsert(self, values: dict[str, Any]) -> None:
        lid = listing_id(values["source_id"], values["source_ref"])
        existing = self.state.listings.get(lid)
        provenance = {k: v for k, v in values["provenance"].items() if self._has_value(values, k)}
        values = {**values, "provenance": provenance}
        if existing is None:
            listing = Listing(
                id=lid,
                first_seen_at=self.now,
                last_seen_at=self.now,
                last_fetched_at=self.now,
                price_history=[PricePoint(at=self.now, price=values["price"])] if values["price"] else [],
                **values,
            )
            self.state.listings[lid] = listing
            self._event(EventType.NEW, listing, new=listing.price)
            return

        old_price, new_price = existing.price, values["price"]
        changed = {
            f: {"old": getattr(existing, f), "new": values[f]}
            for f in TRACKED_FIELDS
            if values[f] is not None and getattr(existing, f) != values[f]
            and not (f == "features" and not self._features_changed(existing.features, values[f]))
        }
        for key, value in values.items():
            if key == "features":
                # Une information connue n'est pas effacée par une collecte qui ne la mentionne plus.
                existing.features = {**existing.features, **value}
            elif value is not None or key in ("price_per_m2",):
                setattr(existing, key, value)
        existing.last_fetched_at = self.now
        if new_price and old_price and new_price != old_price:
            existing.price_history.append(PricePoint(at=self.now, price=new_price))
            self._event(EventType.PRICE_DROP if new_price < old_price else EventType.PRICE_INCREASE, existing, old_price, new_price)
        elif new_price and not existing.price_history:
            existing.price_history.append(PricePoint(at=self.now, price=new_price))
        if changed:
            self._event(EventType.FEATURES_CHANGED, existing, old={k: v["old"] for k, v in changed.items()},
                        new={k: v["new"] for k, v in changed.items()})
        self._mark_seen(existing)

    @staticmethod
    def _has_value(values: dict[str, Any], key: str) -> bool:
        if key.startswith("features."):
            return key.split(".", 1)[1] in values["features"]
        return values.get(key) is not None

    @staticmethod
    def _features_changed(old: dict[str, bool], new: dict[str, bool]) -> bool:
        return any(k in old and old[k] != v for k, v in new.items())

    def _mark_unseen(self, sid: str, seen_ids: set[str]) -> None:
        now = parse_iso(self.now)
        for listing in self.state.listings.values():
            if listing.source_id != sid or listing.id in seen_ids or listing.status == ListingStatus.GONE:
                continue
            listing.unseen_count += 1
            if listing.unseen_since is None:
                listing.unseen_since = self.now
            if listing.status == ListingStatus.ACTIVE:
                listing.status = ListingStatus.UNAVAILABLE_UNCONFIRMED
                self._event(EventType.UNAVAILABLE, listing, old="active", new=listing.status.value)
            elif (
                listing.unseen_count >= self.settings.gone_after_misses
                and now - parse_iso(listing.unseen_since) >= timedelta(days=self.settings.gone_after_days)
            ):
                listing.status = ListingStatus.GONE
                self._event(EventType.GONE, listing, old=ListingStatus.UNAVAILABLE_UNCONFIRMED.value, new="gone")

    # ------------------------------------------------------------------ maintenance
    def prune(self) -> None:
        now = parse_iso(self.now)
        prune_before = now - timedelta(days=self.settings.prune_gone_after_days)
        for lid in [
            lid for lid, x in self.state.listings.items()
            if x.status == ListingStatus.GONE and x.unseen_since and parse_iso(x.unseen_since) < prune_before
        ]:
            del self.state.listings[lid]
        events_before = now - timedelta(days=self.settings.events_retention_days)
        self.state.events = [e for e in self.state.events if parse_iso(e.at) >= events_before]
        for refs in self.state.refs.values():
            refs.out_of_scope = {
                r: d for r, d in refs.out_of_scope.items() if parse_iso(d + "T00:00:00Z") >= now - timedelta(days=30)
            }
