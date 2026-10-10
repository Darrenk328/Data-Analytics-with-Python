"""Cleaning helpers for messy OurAirports fields: surfaces, headings, nulls."""

from __future__ import annotations

import math
import re
from typing import Any

PAVED, GRASS, GRAVEL, WATER, UNKNOWN = "paved", "grass", "gravel-dirt", "water", "unknown"
SURFACES = (PAVED, GRASS, GRAVEL, WATER, UNKNOWN)

# First-token lookup (after upper-casing and splitting on - / , space). Order of the checks
# below matters: the *first* recognised token wins, so "ASPH-TURF" counts as paved.
_TOKENS: dict[str, str] = {}
for _cat, _words in {
    PAVED: "ASP ASPH ASPHALT ASFALT ASPHALTIC CON CONC CONCRETE PEM BIT BITUMEN BITUMINOUS PAVED "
    "TARMAC TAR MAC MACADAM SEALED HARD B PAD COP COM PER CEMENT",
    GRASS: "TURF GRS GRASS GRAS GRE GRASSED SOD G GR",
    GRAVEL: "GVL GRVL GRAVEL GRAV GRV DIRT EARTH SAND SAN SOIL CLAY CLA RED BROWN LATERITE LAT "
    "PIÇARRA PICARRA SAIBRO CORAL COR CALICHE CRUSHED ROCK GROUND TER UNPAVED OILGRAVEL "
    "TRTD TREATED GRADED COMPACTED ROUGH CINDERS SHALE C X N S L XUG",
    WATER: "WATER WAT W",
}.items():
    for _w in _words.split():
        _TOKENS[_w] = _cat

_SPLIT = re.compile(r"[\s\-/,()&+]+")


def normalize_surface(raw: Any) -> str:
    """Map a free-text runway surface ("ASPH-G", "Grassed brown clay", "PEM") to a category."""
    text = clean_str(raw)
    if not text:
        return UNKNOWN
    tokens = [t for t in _SPLIT.split(text.upper()) if t]
    for token in tokens:
        if token in _TOKENS:
            return _TOKENS[token]
    upper = text.upper()
    for needle, cat in (("ASPH", PAVED), ("CONC", PAVED), ("WATER", WATER), ("GRASS", GRASS),
                        ("TURF", GRASS), ("GRAV", GRAVEL), ("DIRT", GRAVEL), ("CLAY", GRAVEL)):
        if needle in upper:
            return cat
    return UNKNOWN


_IDENT = re.compile(r"^\s*(\d{1,2})\s*[LRCTW]?\s*$", re.IGNORECASE)


def heading_from_ident(ident: Any) -> float | None:
    """Derive a heading from a runway designator: "09" → 90.0, "27L" → 270.0, "H1"/"N" → None.

    The designator is the *magnetic* heading rounded to 10°, so the result is approximate.
    """
    text = clean_str(ident)
    if not text:
        return None
    match = _IDENT.match(text)
    if not match:
        return None
    number = int(match.group(1))
    if not 1 <= number <= 36:
        return None
    return float(number * 10)


def clean_str(value: Any) -> str:
    """Return a stripped string, or "" for None/NaN/empty."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def clean_float(value: Any) -> float | None:
    """Return a float, or None for missing/unparseable values."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out
