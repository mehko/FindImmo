"""Jeu de données de DÉMONSTRATION (annonces fictives) pour développer et tester la PWA hors ligne.

Les annonces générées ici n'existent pas : URL en ``.invalid``, source marquée ``is_demo`` et
manifest ``demo: true`` (la PWA affiche alors un bandeau « données fictives »).
Deux collectes sont simulées pour produire de vrais événements (nouveautés, baisses, doublons).
"""

from __future__ import annotations

import json
import random
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .collect import run_collect
from .config import SourceConfig, load_departments, load_settings
from .geo import GeoIndex
from .pipeline.state import State
from .process import run_process

TYPES = [("apartment", "Appartement"), ("house", "Maison"), ("land", "Terrain")]
FEATURES = ["garden", "terrace", "balcony", "garage", "parking", "pool", "cellar", "elevator"]
ADJ = ["lumineux", "au calme", "rénové", "familial", "proche gare", "avec vue", "traversant", "à rafraîchir"]


def _listing(rng: random.Random, i: int, commune: Any, source: str) -> dict[str, Any]:
    ptype, label = rng.choices(TYPES, weights=[6, 4, 1])[0]
    rent = ptype == "apartment" and rng.random() < 0.25
    rooms = rng.randint(1, 3) if ptype == "apartment" else rng.randint(3, 7)
    surface = round(rng.uniform(18, 35) * rooms + rng.uniform(-5, 10), 1) if ptype != "land" else None
    base_m2 = {"75": 10500, "92": 7200, "94": 5600, "93": 4300, "78": 5200, "91": 3500, "95": 3400, "77": 3100, "83": 4600}
    m2 = base_m2.get(commune.department, 4000) * rng.uniform(0.8, 1.25)
    if ptype == "land":
        land = rng.randint(300, 1500)
        price = round(land * rng.uniform(150, 400), -3)
    else:
        land = rng.randint(150, 1200) if ptype == "house" else None
        price = round(surface * m2, -3) if not rent else round(surface * m2 / 230, 0)
    feats = {f: True for f in rng.sample(FEATURES, rng.randint(0, 4))}
    if ptype == "apartment":
        feats.pop("pool", None)
        feats.pop("garden", None)
    cp = commune.postal_codes[0] if commune.postal_codes else None
    adj = rng.choice(ADJ)
    title = f"{label} {rooms} pièces {surface or ''} m² — {commune.name}" if ptype != "land" else f"Terrain {land} m² — {commune.name}"
    return {
        "source_ref": f"D{i:04d}",
        "url": f"https://{source}.findimmo.invalid/annonce/D{i:04d}",
        "title": title.replace(" None", ""),
        "description": f"[ANNONCE FICTIVE] {label} {adj} à {commune.name}. "
        + ("Jardin arboré. " if feats.get("garden") else "")
        + ("Belle terrasse. " if feats.get("terrace") else ""),
        "transaction": "rent" if rent else "sale",
        "property_type": ptype,
        "price": price,
        "surface": surface,
        "land_surface": land,
        "rooms": rooms if ptype != "land" else None,
        "bedrooms": max(0, rooms - 1) if ptype != "land" and rng.random() < 0.8 else None,
        "city": commune.name,
        "postal_code": cp,
        "dpe": rng.choice("ABCDEFG") if ptype != "land" and rng.random() < 0.85 else None,
        "features": feats,
        "published_at": None,
    }


def build_demo(out_dir: Path, count: int = 160, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    geo = GeoIndex.load()
    departments = load_departments()
    settings = load_settings()
    communes = [c for c in geo.communes if c.postal_codes]
    weights = [3 if c.department in ("75", "92", "83") else 1 for c in communes]
    picked = rng.choices(communes, weights=weights, k=count)
    listings = [_listing(rng, i, c, "demo") for i, c in enumerate(picked)]

    # Doublons inter-sources : 8 biens republiés par une seconde agence fictive (prix légèrement différent)
    dupes = []
    for j, item in enumerate(rng.sample([x for x in listings if x["surface"]], 8)):
        d = dict(item, source_ref=f"B{j:03d}", url=f"https://demo-bis.findimmo.invalid/bien/B{j:03d}")
        d["price"] = round(item["price"] * rng.uniform(0.99, 1.02), -2 if item["transaction"] == "rent" else -3)
        dupes.append(d)

    work = Path(tempfile.mkdtemp(prefix="findimmo-demo-"))
    try:
        def source(sid: str, name: str, feed: Path) -> SourceConfig:
            return SourceConfig(id=sid, name=name, domain=f"{sid}.findimmo.invalid", url=f"https://{sid}.findimmo.invalid",
                                method="feed", enabled=True, compatibility="fixture", is_demo=True,
                                options={"feed_url": f"file://{feed}", "items_path": "listings"},
                                publish={"image": False, "description_chars": 400})

        def cycle(items: list[dict], items_bis: list[dict], now: str) -> dict[str, Any]:
            (work / "a.json").write_text(json.dumps({"listings": items}, ensure_ascii=False))
            (work / "b.json").write_text(json.dumps({"listings": items_bis}, ensure_ascii=False))
            sources = [source("demo", "Agence Démo (fictive)", work / "a.json"),
                       source("demo-bis", "Agence Démo Bis (fictive)", work / "b.json")]
            raw = work / "raw"
            if raw.exists():
                shutil.rmtree(raw)
            run_collect(sources, geo, {d.code for d in departments}, State.load(work / "state"), settings, raw, workers=1)
            return run_process(raw, work / "state", out_dir, sources, departments, geo, settings, now=now)

        cycle(listings[: count - 25], dupes, "2026-11-01T08:00:00Z")
        # Seconde collecte : 25 nouveautés, ~10 % de baisses de prix, quelques annonces retirées
        second = []
        for x in listings:
            x = dict(x)
            if rng.random() < 0.1:
                x["price"] = round(x["price"] * rng.uniform(0.9, 0.97), -2 if x["transaction"] == "rent" else -3)
            if rng.random() > 0.04:
                second.append(x)
        return cycle(second, dupes, "2026-11-07T08:00:00Z")
    finally:
        shutil.rmtree(work, ignore_errors=True)
