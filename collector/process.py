"""Étape « process » : lots bruts + état → état mis à jour, événements, JSON publics, rapport."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import Department, Settings, SourceConfig
from .geo import GeoIndex
from .models import ListingStatus, SourceBatch
from .pipeline.dedup import deduplicate
from .pipeline.publish import publish
from .pipeline.state import State, write_json_atomic
from .pipeline.tracker import Tracker, now_iso, parse_iso


def load_batches(raw_dir: Path) -> list[SourceBatch]:
    if not raw_dir.exists():
        return []
    return [
        SourceBatch.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(raw_dir.rglob("*.json"))
    ]


def build_report(batches: list[SourceBatch], tracker: Tracker, groups: int, candidates: int, started: float, state: State) -> dict[str, Any]:
    stats = tracker.stats
    starts = [parse_iso(b.status.started_at) for b in batches]
    ends = [parse_iso(b.status.finished_at) for b in batches if b.status.finished_at]
    collect_s = (max(ends) - min(starts)).total_seconds() if starts and ends else 0.0
    return {
        "generated_at": tracker.now,
        "duration_seconds": round(collect_s + (time.monotonic() - started), 1),
        "sources_analyzed": len(batches),
        "sources_ok": sum(1 for b in batches if b.status.ok and not b.status.errors),
        "sources_partial": sum(1 for b in batches if b.status.ok and b.status.errors),
        "sources_error": sum(1 for b in batches if not b.status.ok),
        "listings_observed": stats.observed,
        "new_listings": stats.new,
        "price_drops": stats.price_drops,
        "price_increases": stats.price_increases,
        "features_changed": stats.features_changed,
        "unavailable": stats.unavailable,
        "reappeared": stats.reappeared,
        "gone": stats.gone,
        "duplicate_groups": groups,
        "possible_duplicates": candidates,
        "active_listings": sum(1 for x in state.listings.values() if x.status == ListingStatus.ACTIVE),
        "sources": [
            {
                **b.status.model_dump(mode="json", exclude={"errors"}),
                "errors": b.status.errors[:5],
                "events": stats.per_source.get(b.status.source_id, {}),
            }
            for b in batches
        ],
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Rapport de collecte FindImmo",
        "",
        f"* Généré : {report['generated_at']} — durée {report['duration_seconds']} s",
        f"* Sources : {report['sources_analyzed']} analysées, {report['sources_ok']} OK, "
        f"{report['sources_partial']} partielles, {report['sources_error']} en erreur",
        f"* Annonces observées : {report['listings_observed']} (actives : {report['active_listings']})",
        f"* Nouvelles : {report['new_listings']} — baisses : {report['price_drops']} — hausses : {report['price_increases']}",
        f"* Non retrouvées : {report['unavailable']} — réapparues : {report['reappeared']} — retirées : {report['gone']}",
        f"* Doublons : {report['duplicate_groups']} groupes fusionnés, {report['possible_duplicates']} possibles",
        "",
        "| Source | OK | Découvertes | Dans la zone | Détails | Retirées | Échecs | En attente | Erreurs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in report["sources"]:
        err = (s["errors"][0][:80] + "…") if s["errors"] else ""
        lines.append(
            f"| {s['source_id']} | {'✅' if s['ok'] else '❌'} | {s['refs_discovered']} | {s['refs_in_scope']} | "
            f"{s['details_fetched']} | {s.get('removed', 0)} | {s['details_failed']} | {s['backlog']} | {err} |"
        )
    return "\n".join(lines) + "\n"


def run_process(
    raw_dir: Path,
    state_dir: Path,
    public_dir: Path,
    sources: list[SourceConfig],
    departments: list[Department],
    geo: GeoIndex,
    settings: Settings,
    now: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    state = State.load(state_dir)
    batches = load_batches(raw_dir)
    tracker = Tracker(state, {s.id: s for s in sources}, geo, {d.code for d in departments}, settings, now=now or now_iso())
    for batch in batches:
        tracker.apply(batch)
    tracker.prune()
    groups, candidates = deduplicate(state.listings.values())
    # Les événements reçoivent l'identifiant de bien final.
    for e in state.events:
        if e.at == tracker.now and (x := state.listings.get(e.listing_id)) is not None:
            e.property_id = x.property_id
    report = build_report(batches, tracker, len(groups), len(candidates), started, state)
    state.save()
    write_json_atomic(state_dir / "last-report.json", report, compact=False)
    publish(state, public_dir, departments, sources, candidates, settings, report, tracker.now)
    return report
