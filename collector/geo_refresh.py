"""Téléchargement du référentiel des communes depuis geo.api.gouv.fr (service public gratuit)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from .config import Department
from .geo import GEO_FILE

API = "https://geo.api.gouv.fr"
FIELDS = "nom,code,codesPostaux,centre,codeDepartement"


def _get(client: httpx.Client, url: str) -> list[dict]:
    last: Exception | None = None
    for attempt in range(5):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"geo.api.gouv.fr indisponible : {url} ({last})")


def refresh_geo(departments: list[Department], path: Path = GEO_FILE) -> int:
    communes: list[dict] = []
    with httpx.Client(timeout=60) as client:
        for dep in departments:
            rows = _get(client, f"{API}/departements/{dep.code}/communes?fields={FIELDS}&format=json")
            if dep.code == "75":
                # Paris : on utilise les arrondissements, plus précis pour la localisation.
                rows = _get(
                    client,
                    f"{API}/communes?codeDepartement=75&type=arrondissement-municipal&fields={FIELDS}&format=json",
                )
            for r in rows:
                coords = (r.get("centre") or {}).get("coordinates") or [None, None]
                communes.append(
                    {
                        "insee": r["code"],
                        "name": r["nom"],
                        "dep": dep.code,
                        "cps": sorted(r.get("codesPostaux") or []),
                        "lat": round(coords[1], 5) if coords[1] is not None else None,
                        "lon": round(coords[0], 5) if coords[0] is not None else None,
                    }
                )
    communes.sort(key=lambda c: c["insee"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": "geo.api.gouv.fr", "departments": [d.code for d in departments], "communes": communes}
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(communes)
