"""Contrat du format publié (manifest + fichiers) et export JSON Schema vers ``packages/shared``."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import FORMAT_VERSION, Listing, ListingEvent


class FileRef(BaseModel):
    path: str
    bytes: int
    sha256: str


class DepartmentEntry(FileRef):
    code: str
    name: str
    region: str
    count: int


class ManifestFiles(BaseModel):
    events: FileRef
    sources: FileRef
    report: FileRef
    communes: FileRef | None = None


class Manifest(BaseModel):
    format_version: int
    data_version: str
    generated_at: str
    demo: bool
    total_listings: int
    departments: list[DepartmentEntry]
    files: ManifestFiles


class PublicListing(Listing):
    """Annonce publiée : ``maybe_same`` liste les doublons possibles (non fusionnés)."""

    maybe_same: list[str] = []


class DepartmentFile(BaseModel):
    department: str
    generated_at: str
    listings: list[PublicListing]


class EventsFile(BaseModel):
    generated_at: str
    events: list[ListingEvent]


def export_schema(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in {"manifest": Manifest, "department-file": DepartmentFile, "events-file": EventsFile}.items():
        schema = model.model_json_schema()
        schema["$comment"] = f"Généré par `python -m collector schema` — format_version {FORMAT_VERSION}"
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written
