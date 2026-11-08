"""Référentiel géographique : communes, codes postaux, départements, distances.

Les données proviennent de l'API publique et gratuite geo.api.gouv.fr (``refresh-geo``) et sont
versionnées dans ``config/geo/communes.json`` pour que la collecte ne dépende pas d'un service tiers.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import CONFIG_DIR

GEO_FILE = CONFIG_DIR / "geo" / "communes.json"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("'", "-").replace("’", "-")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def compact_slug(value: str) -> str:
    """Slug sans séparateurs ni articles initiaux : « Le Vésinet » → « vesinet »."""
    s = slugify(value)
    s = re.sub(r"^(le|la|les|l)-", "", s)
    return s.replace("-", "")


def department_from_postal_code(postal_code: str | None) -> str | None:
    if not postal_code or not re.fullmatch(r"\d{5}", postal_code):
        return None
    if postal_code.startswith("97") or postal_code.startswith("98"):
        return postal_code[:3]
    if postal_code.startswith("20"):
        return "2A" if int(postal_code) < 20200 else "2B"
    return postal_code[:2]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Commune:
    insee: str
    name: str
    department: str
    postal_codes: tuple[str, ...]
    lat: float | None
    lon: float | None

    @property
    def slug(self) -> str:
        return slugify(self.name)


class GeoIndex:
    def __init__(self, communes: list[Commune]):
        self.communes = communes
        self.by_insee = {c.insee: c for c in communes}
        self.by_postal: dict[str, list[Commune]] = {}
        self.by_slug: dict[str, list[Commune]] = {}
        self.by_compact: dict[str, list[Commune]] = {}
        for c in communes:
            for cp in c.postal_codes:
                self.by_postal.setdefault(cp, []).append(c)
            self.by_slug.setdefault(c.slug, []).append(c)
            self.by_compact.setdefault(compact_slug(c.name), []).append(c)
            # Alias usuels des arrondissements : « paris-15 », « paris-15e », « paris »
            m = re.fullmatch(r"(paris|marseille|lyon)-(\d+)(?:er|e)-arrondissement", c.slug)
            if m:
                for alias in {f"{m[1]}-{int(m[2])}", f"{m[1]}-{int(m[2])}e", f"{m[1]}-{int(m[2]):02d}", m[1]}:
                    if alias != c.slug:
                        self.by_slug.setdefault(alias, []).append(c)
        self.departments = {c.department for c in communes}

    @classmethod
    def load(cls, path: Path = GEO_FILE) -> GeoIndex:
        if not path.exists():
            return cls([])
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            [
                Commune(
                    insee=r["insee"],
                    name=r["name"],
                    department=r["dep"],
                    postal_codes=tuple(r.get("cps", [])),
                    lat=r.get("lat"),
                    lon=r.get("lon"),
                )
                for r in raw["communes"]
            ]
        )

    def communes_for_slug(self, slug: str) -> list[Commune]:
        slug = slugify(slug)
        return self.by_slug.get(slug) or self.by_compact.get(compact_slug(slug), [])

    def resolve(self, city: str | None, postal_code: str | None, insee: str | None = None) -> Commune | None:
        """Retrouve la commune la plus probable. Ne devine pas en cas d'ambiguïté non résolue."""
        if insee and insee in self.by_insee:
            return self.by_insee[insee]
        candidates = self.by_postal.get(postal_code or "", [])
        if not candidates and postal_code in self.by_insee:
            # Certains sites placent le code INSEE là où l'on attend un code postal.
            return self.by_insee[postal_code]  # type: ignore[index]
        if city:
            s = compact_slug(city)
            # « Paris 15e Arrondissement » / « PARIS 15 » → arrondissement via code postal
            named = [c for c in candidates if compact_slug(c.name) == s]
            if named:
                return named[0]
            if len(candidates) > 1:
                partial = [c for c in candidates if s and (s in compact_slug(c.name) or compact_slug(c.name) in s)]
                if len(partial) == 1:
                    return partial[0]
        if len(candidates) == 1:
            return candidates[0]
        if candidates and postal_code and postal_code.startswith("75"):
            return candidates[0]
        if city and not candidates:
            matches = self.communes_for_slug(city)
            dep = department_from_postal_code(postal_code)
            if dep:
                matches = [c for c in matches if c.department == dep]
            if len({c.insee for c in matches}) == 1:
                return matches[0]
        return None
