"""Analyse de texte en français : nombres, surfaces, pièces, équipements mentionnés.

Tout ce qui sort d'ici est marqué ``parsed`` (déduit d'un texte), jamais ``extracted``.
"""

from __future__ import annotations

import re
import unicodedata

_NBSP = re.compile(r"[   ]")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = _NBSP.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()


def parse_number(value: object) -> float | None:
    """« 699 000 € » → 699000 ; « 50,62 m² » → 50.62 ; 1.5e3 → 1500."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    s = _NBSP.sub(" ", str(value))
    m = re.search(r"\d[\d .,]*", s)
    if not m:
        return None
    num = m.group(0).strip().replace(" ", "")
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".")
    elif "," in num:
        num = num.replace(",", ".")
    elif num.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", num):
        num = num.replace(".", "")
    try:
        return float(num)
    except ValueError:
        return None


def parse_int(value: object) -> int | None:
    n = parse_number(value)
    return int(n) if n is not None and n == int(n) else None


_ROOMS = re.compile(r"(\d+)\s*(?:pi[eè]ces?|p\b)", re.I)
_BEDROOMS = re.compile(r"(\d+)\s*(?:chambres?|chbres?|ch\b)", re.I)
_SURFACE = re.compile(r"(\d[\d\s.,]*)\s*m(?:²|2)\b", re.I)
_LAND = re.compile(
    r"(?:terrain|parcelle|jardin)\s+(?:de\s+|d'environ\s+|d’environ\s+|:\s*)?(\d[\d\s.,]*)\s*m(?:²|2)", re.I
)
_LAND_LABEL = re.compile(r"surf(?:ace|\.)?\s*(?:du\s+)?terrain\s*:?\s*(\d[\d\s.,]*)\s*m", re.I)


def parse_rooms(text: str | None) -> int | None:
    m = _ROOMS.search(text or "")
    return int(m.group(1)) if m else None


def parse_bedrooms(text: str | None) -> int | None:
    m = _BEDROOMS.search(text or "")
    return int(m.group(1)) if m else None


def parse_surface(text: str | None) -> float | None:
    m = _SURFACE.search(text or "")
    return parse_number(m.group(1)) if m else None


def parse_land_surface(text: str | None) -> float | None:
    for rx in (_LAND_LABEL, _LAND):
        m = rx.search(text or "")
        if m:
            return parse_number(m.group(1))
    return None


# Mots-clés (forme repliée sans accents) → équipement
FEATURE_PATTERNS: dict[str, str] = {
    "garden": r"\bjardin(?:et)?s?\b",
    "terrace": r"\bterrasses?\b",
    "balcony": r"\bbalcons?\b",
    "garage": r"\bgarages?\b|\bbox\b",
    "parking": r"\bparkings?\b|\bplaces? de stationnement\b",
    "pool": r"\bpiscines?\b",
    "cellar": r"\bcaves?\b|\bcellier\b",
    "elevator": r"\bascenseurs?\b",
}
_NEGATION = re.compile(r"(?:\bsans\b|\bpas de\b|\bpas d'|\baucune?\b|\bni\b)\s*(?:\w+\s+){0,2}$")


def parse_features(text: str | None) -> dict[str, bool]:
    """Équipements mentionnés positivement dans un texte. Une absence de mention n'implique rien."""
    if not text:
        return {}
    folded = _fold(text)
    found: dict[str, bool] = {}
    for key, pattern in FEATURE_PATTERNS.items():
        for m in re.finditer(pattern, folded):
            before = folded[max(0, m.start() - 30) : m.start()]
            if not _NEGATION.search(before):
                found[key] = True
                break
    return found


def parse_energy_class(text: str | None, label: str = "dpe") -> str | None:
    if not text:
        return None
    folded = _fold(text)
    if label == "dpe":
        rx = r"(?:\bdpe\b|classe\s+(?:energie|energetique)|performance energetique)\s*(?:\(?[^)]{0,15}\)?)?\s*[:=]?\s*(?:classe\s+)?\b([a-g])\b"
    else:
        rx = r"(?:\bges\b|emissions?\s+de\s+gaz|classe\s+climat)\s*[:=]?\s*(?:classe\s+)?\b([a-g])\b"
    m = re.search(rx, folded)
    return m.group(1).upper() if m else None
