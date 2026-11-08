"""État persistant du collector (fichiers JSON dans ``data/state/``).

En production, ce répertoire vit sur la branche Git ``data`` (réécrite à chaque collecte, donc sans
croissance d'historique). Les écritures sont atomiques (fichier temporaire + ``os.replace``).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..models import FORMAT_VERSION, Listing, ListingEvent


class RefInfo(BaseModel):
    lastmod: str | None = None
    fetched_at: str | None = None


class SourceRefs(BaseModel):
    fetched: dict[str, RefInfo] = Field(default_factory=dict)
    out_of_scope: dict[str, str] = Field(default_factory=dict)  # ref → date de constat
    removed: dict[str, str] = Field(default_factory=dict)  # annonces retirées (page supprimée/redirigée)


class SourceState(BaseModel):
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_status: str | None = None  # ok | partial | error
    consecutive_failures: int = 0
    listings_count: int = 0
    last_errors: list[str] = Field(default_factory=list)
    backlog: int = 0


def write_json_atomic(path: Path, data: Any, compact: bool = True) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":") if compact else None, indent=None if compact else 1)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return len(text.encode("utf-8"))


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class State:
    def __init__(self, root: Path):
        self.root = root
        self.listings: dict[str, Listing] = {}
        self.events: list[ListingEvent] = []
        self.sources: dict[str, SourceState] = {}
        self.refs: dict[str, SourceRefs] = {}

    @classmethod
    def load(cls, root: Path) -> State:
        st = cls(root)
        data = _read(root / "listings.json", {"listings": {}})
        st.listings = {k: Listing.model_validate(v) for k, v in data.get("listings", {}).items()}
        st.events = [ListingEvent.model_validate(e) for e in _read(root / "events.json", {"events": []})["events"]]
        st.sources = {k: SourceState.model_validate(v) for k, v in _read(root / "sources.json", {}).items()}
        st.refs = {k: SourceRefs.model_validate(v) for k, v in _read(root / "refs.json", {}).items()}
        return st

    def save(self) -> None:
        write_json_atomic(
            self.root / "listings.json",
            {
                "format_version": FORMAT_VERSION,
                "listings": {k: v.model_dump(mode="json", exclude_none=True) for k, v in sorted(self.listings.items())},
            },
        )
        write_json_atomic(self.root / "events.json", {"events": [e.model_dump(mode="json") for e in self.events]})
        write_json_atomic(self.root / "sources.json", {k: v.model_dump(mode="json") for k, v in sorted(self.sources.items())})
        write_json_atomic(self.root / "refs.json", {k: v.model_dump(mode="json") for k, v in sorted(self.refs.items())})

    def source_refs(self, source_id: str) -> SourceRefs:
        return self.refs.setdefault(source_id, SourceRefs())

    def source_state(self, source_id: str) -> SourceState:
        return self.sources.setdefault(source_id, SourceState())
