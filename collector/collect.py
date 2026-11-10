"""Étape « collect » : exécute les connecteurs et produit un lot (``SourceBatch``) par source.

Stratégie incrémentale et budgetée, par source :

1. découverte complète des références (sitemap, flux…) avec pré-filtrage géographique ;
2. sélection des pages détail à récupérer : nouvelles > modifiées (``lastmod``) > les plus anciennes
   (au-delà de ``refresh_days``), dans la limite de ``max_details_per_run`` et ``max_run_seconds`` ;
3. une erreur isolée n'arrête pas la source ; un blocage anti-bot l'arrête immédiatement.
"""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from .config import Settings, SourceConfig
from .connectors.base import ConnectorContext
from .connectors.registry import build_connector
from .geo import GeoIndex
from .http import BlockedError, FetchError, PoliteClient
from .log import get_logger, log
from .models import ListingRef, ListingStatus, SourceBatch, SourceRunStatus
from .pipeline.normalize import listing_id
from .pipeline.state import State, write_json_atomic
from .pipeline.tracker import now_iso, parse_iso

logger = get_logger(__name__)

MAX_CONSECUTIVE_EMPTY = 10


def shard_of(source_id: str, total: int) -> int:
    return int(hashlib.sha1(source_id.encode()).hexdigest(), 16) % total


def _priority(ref: ListingRef, state: State, refresh_before: str) -> tuple[int, str] | None:
    lid = listing_id(ref.source_id, ref.source_ref)
    info = state.source_refs(ref.source_id).fetched.get(ref.source_ref)
    if lid not in state.listings or info is None:
        return (0, "")
    if ref.lastmod and info.lastmod and ref.lastmod != info.lastmod:
        return (1, info.fetched_at or "")
    if not info.fetched_at or info.fetched_at < refresh_before:
        return (2, info.fetched_at or "")
    return None


def _due(source: SourceConfig, state: State) -> bool:
    """Option ``min_interval_hours`` : écart minimal entre deux tentatives sur une source lourde ou sensible.

    Une source ignorée n'a pas de lot : le traitement ne la voit pas et ses annonces ne changent pas de statut."""
    hours = source.options.get("min_interval_hours")
    known = state.sources.get(source.id)
    attempt = known.last_attempt_at if known else None
    if not hours or not attempt:
        return True
    elapsed = parse_iso(now_iso()) - parse_iso(attempt)
    if elapsed >= timedelta(hours=float(hours)):
        return True
    log(logger, logging.INFO, "source ignorée : intervalle minimal non écoulé", source=source.id,
        hours_since_last=round(elapsed.total_seconds() / 3600, 1), min_interval_hours=hours)
    return False


def collect_source(source: SourceConfig, client: PoliteClient, geo: GeoIndex, departments: set[str], state: State) -> SourceBatch:
    started = time.monotonic()
    status = SourceRunStatus(source_id=source.id, started_at=now_iso())
    batch = SourceBatch(status=status)
    scope = departments & set(source.departments or departments)
    ctx = ConnectorContext(client=client, geo=geo, departments=scope, deadline=started + source.max_run_seconds)
    client.set_delay(source.domain, source.rate_limit_seconds)
    refs_state = state.source_refs(source.id)
    skip = refs_state.out_of_scope.keys() | refs_state.removed.keys()

    try:
        connector = build_connector(source, ctx)
    except ValueError as exc:
        status.errors.append(str(exc))
        status.finished_at = now_iso()
        return batch

    in_scope: list[ListingRef] = []
    discovered: set[str] = set()
    # Option ``partial_discovery`` : la source ne peut pas énumérer toutes ses annonces (liste plafonnée, route
    # interdite par robots.txt…). On ne conclut alors JAMAIS d'une absence ; en contrepartie les annonces
    # connues mais non redécouvertes sont revérifiées directement par leur page (voir plus bas).
    partial = bool(source.options.get("partial_discovery"))
    try:
        discovery_complete = True
        for ref in connector.discover():
            status.refs_discovered += 1
            discovered.add(ref.source_ref)
            if ref.source_ref in skip or connector.ref_in_scope(ref) is False:
                continue
            in_scope.append(ref)
            if ctx.time_left() < source.max_run_seconds * 0.5:
                discovery_complete = False
                status.errors.append("découverte interrompue : budget de temps atteint")
                break
        status.discovery_complete = discovery_complete and not partial
    except BlockedError as exc:
        status.errors.append(f"bloqué : {exc}")
        status.finished_at = now_iso()
        log(logger, logging.WARNING, "source bloquée", source=source.id, error=str(exc))
        return batch
    except Exception as exc:  # noqa: BLE001 - toute erreur d'une source est isolée
        status.errors.append(f"découverte : {type(exc).__name__}: {exc}")
        log(logger, logging.ERROR, "échec de découverte", source=source.id, error=str(exc))
    revalidate: set[str] = set()
    if partial:
        # Annonces actives connues mais absentes de la découverte partielle : on les remet dans la file avec l'URL
        # mémorisée. Si leur page a disparu, été redirigée ou affiche « vendu », elles seront marquées retirées ;
        # sinon elles sont simplement rafraîchies à la cadence ``refresh_days``.
        for listing in state.listings.values():
            if (listing.source_id == source.id and listing.status != ListingStatus.GONE
                    and listing.source_ref not in discovered and listing.source_ref not in skip):
                in_scope.append(connector.make_ref(listing.source_ref, listing.url, department_hint=listing.department))
                revalidate.add(listing.source_ref)
    status.refs_in_scope = len(in_scope)

    refresh_before = (parse_iso(now_iso()) - timedelta(days=source.refresh_days)).isoformat().replace("+00:00", "Z")
    queue: list[tuple[tuple[int, str], ListingRef]] = []
    gone_refs: set[str] = set()
    for ref in in_scope:
        if ref.raw is not None:
            batch.listings.append(ref.raw)
            continue
        prio = _priority(ref, state, refresh_before)
        if prio is not None:
            queue.append((prio, ref))
    queue.sort(key=lambda item: item[0])

    fetched = 0
    consecutive_empty = 0
    for _prio, ref in queue:
        if fetched >= source.max_details_per_run or ctx.time_left() <= 0:
            break
        fetched += 1
        try:
            raw = connector.fetch_detail(ref)
        except BlockedError as exc:
            status.errors.append(f"bloqué : {exc}")
            break
        except FetchError as exc:
            if exc.status in (404, 410):
                # Page détail supprimée ou redirigée : l'annonce n'est plus « vue » et n'est plus
                # retéléchargée pendant 30 jours (le sitemap de la source peut être en retard).
                gone_refs.add(ref.source_ref)
                status.removed += 1
            else:
                status.details_failed += 1
                status.errors.append(str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            status.details_failed += 1
            status.errors.append(f"{ref.url} : {type(exc).__name__}: {exc}")
            continue
        if raw is None:
            status.details_failed += 1
            consecutive_empty += 1
            status.errors.append(f"aucune donnée exploitable : {ref.url} [{connector.last_page_info}]")
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                # Pages systématiquement inexploitables : blocage probable ou refonte du site.
                status.errors.insert(0, f"arrêt : {consecutive_empty} pages inexploitables consécutives")
                log(logger, logging.WARNING, "source interrompue", source=source.id, last_page=connector.last_page_info)
                break
            continue
        consecutive_empty = 0
        batch.listings.append(raw)
        if ref.lastmod:
            batch.lastmods[ref.source_ref] = ref.lastmod
        status.details_fetched += 1

    known = {r.source_ref for r in in_scope if r.source_ref not in revalidate and listing_id(source.id, r.source_ref) in state.listings}
    fetched_refs = {r.source_ref for r in batch.listings}
    batch.seen_refs = sorted((known | fetched_refs) - gone_refs)
    batch.removed_refs = sorted(gone_refs)
    status.backlog = sum(
        1 for r in in_scope
        if r.source_ref not in known and r.source_ref not in fetched_refs and r.source_ref not in gone_refs
        and (r.source_ref not in revalidate or _priority(r, state, refresh_before) is not None)
    )
    status.ok = status.refs_discovered > 0 or status.discovery_complete
    if status.refs_discovered == 0 and not status.errors:
        status.errors.append("aucune référence découverte")
    status.errors = status.errors[:50]
    status.finished_at = now_iso()
    log(logger, logging.INFO, "source collectée", source=source.id, **status.model_dump(exclude={"errors"}),
        errors=len(status.errors), duration_s=round(time.monotonic() - started, 1))
    return batch


def run_collect(
    sources: list[SourceConfig],
    geo: GeoIndex,
    departments: set[str],
    state: State,
    settings: Settings,
    out_dir: Path,
    shard: tuple[int, int] = (0, 1),
    workers: int = 4,
    client: PoliteClient | None = None,
) -> list[SourceBatch]:
    index, total = shard
    selected = [s for s in sources if s.enabled and shard_of(s.id, total) == index]
    selected = [s for s in selected if _due(s, state)]
    own_client = client is None
    client = client or PoliteClient(settings.user_agent)
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            batches = list(pool.map(lambda s: collect_source(s, client, geo, departments, state), selected))
    finally:
        if own_client:
            client.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    for b in batches:
        write_json_atomic(out_dir / f"{b.status.source_id}.json", b.model_dump(mode="json", exclude_none=True))
    return batches
