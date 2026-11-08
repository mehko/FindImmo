"""Génération des fichiers JSON publics (GitHub Pages).

Publication atomique :

1. tout est écrit dans un répertoire temporaire voisin ;
2. les fichiers de données portent un hash de contenu dans leur nom (``listings/77.3fa2c1d0.json``) ;
3. ``manifest.json`` (seul fichier à nom fixe, non mis en cache) est écrit en dernier et référence
   exactement les fichiers de sa génération ; le répertoire temporaire remplace l'ancien d'un coup.

La PWA lit le manifest puis les fichiers hashés : elle ne peut pas mélanger deux générations.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..config import Department, Settings, SourceConfig
from ..geo import GEO_FILE
from ..models import FORMAT_VERSION, DuplicateCandidate, Listing, ListingStatus
from .state import State
from .tracker import parse_iso

# Champs internes non publiés
PRIVATE_FIELDS = {"unseen_count", "last_fetched_at", "is_demo"}


def _dump(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write_hashed(root: Path, rel_dir: str, stem: str, data: Any) -> dict[str, Any]:
    payload = _dump(data)
    digest = hashlib.sha256(payload).hexdigest()[:10]
    rel = f"{rel_dir}/{stem}.{digest}.json" if rel_dir else f"{stem}.{digest}.json"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": rel, "bytes": len(payload), "sha256": digest}


def public_listing(x: Listing, source: SourceConfig | None, maybe_same: list[str]) -> dict[str, Any]:
    d = x.model_dump(mode="json", exclude_none=True, exclude=PRIVATE_FIELDS)
    policy = source.publish if source else None
    if policy is not None:
        if not policy.image:
            d.pop("image", None)
        if policy.description_chars <= 0:
            d.pop("description", None)
        elif d.get("description") and len(d["description"]) > policy.description_chars:
            d["description"] = d["description"][: policy.description_chars].rsplit(" ", 1)[0] + "…"
    if not d.get("features"):
        d.pop("features", None)
    if not d.get("provenance"):
        d.pop("provenance", None)
    if maybe_same:
        d["maybe_same"] = maybe_same
    return d


def publish(
    state: State,
    out_dir: Path,
    departments: list[Department],
    sources: list[SourceConfig],
    candidates: list[DuplicateCandidate],
    settings: Settings,
    report: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    tmp = out_dir.with_name(out_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    src_by_id = {s.id: s for s in sources}

    maybe: dict[str, list[str]] = defaultdict(list)
    for c in candidates:
        maybe[c.a].append(c.b)
        maybe[c.b].append(c.a)

    by_dep: dict[str, list[dict[str, Any]]] = defaultdict(list)
    demo = False
    for x in sorted(state.listings.values(), key=lambda x: x.first_seen_at, reverse=True):
        if x.status == ListingStatus.GONE or not x.department:
            continue
        demo = demo or x.is_demo
        by_dep[x.department].append(public_listing(x, src_by_id.get(x.source_id), maybe.get(x.id, [])))

    dep_entries = []
    for dep in departments:
        items = by_dep.get(dep.code, [])
        entry = _write_hashed(tmp, "listings", dep.code, {"department": dep.code, "generated_at": now, "listings": items})
        dep_entries.append({"code": dep.code, "name": dep.name, "region": dep.region, "count": len(items), **entry})

    cutoff = parse_iso(now) - timedelta(days=settings.published_events_days)
    events = [e.model_dump(mode="json", exclude_none=True) for e in state.events if parse_iso(e.at) >= cutoff]
    events.sort(key=lambda e: e["at"], reverse=True)
    events_entry = _write_hashed(tmp, "events", "recent", {"generated_at": now, "events": events})

    sources_public = []
    for s in sources:
        st = state.sources.get(s.id)
        sources_public.append(
            {
                "id": s.id, "name": s.name, "domain": s.domain, "url": s.url, "cms": s.cms, "network": s.network,
                "departments": s.departments, "method": s.method if s.method != "adapter" else f"adapter:{s.adapter}",
                "enabled": s.enabled, "compatibility": s.compatibility.value, "is_demo": s.is_demo,
                "last_attempt_at": st.last_attempt_at if st else None,
                "last_success_at": st.last_success_at if st else None,
                "last_status": st.last_status if st else None,
                "listings_count": st.listings_count if st else 0,
                "errors": st.last_errors[-3:] if st else [],
            }
        )
    sources_entry = _write_hashed(tmp, "", "sources", {"generated_at": now, "sources": sources_public})

    files: dict[str, Any] = {"events": events_entry, "sources": sources_entry}
    if GEO_FILE.exists():
        geo = json.loads(GEO_FILE.read_text(encoding="utf-8"))
        files["communes"] = _write_hashed(tmp, "geo", "communes", {"communes": geo["communes"]})
    files["report"] = _write_hashed(tmp, "", "report", report)

    data_version = hashlib.sha256(
        _dump([d["sha256"] for d in dep_entries] + [f["sha256"] for f in files.values()])
    ).hexdigest()[:12]
    manifest = {
        "format_version": FORMAT_VERSION,
        "data_version": data_version,
        "generated_at": now,
        "demo": demo,
        "total_listings": sum(d["count"] for d in dep_entries),
        "departments": dep_entries,
        "files": files,
    }
    (tmp / "manifest.json").write_bytes(_dump(manifest))
    (tmp / ".nojekyll").write_text("")
    (tmp / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>FindImmo data</title>"
        "<p>Données FindImmo. Point d'entrée : <a href='manifest.json'>manifest.json</a>.</p>",
        encoding="utf-8",
    )

    old = out_dir.with_name(out_dir.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out_dir.exists():
        out_dir.rename(old)
    tmp.rename(out_dir)
    if old.exists():
        shutil.rmtree(old)
    return manifest
