"""A tiny filter language: ``country=US elevation>5000 runway<8000 name~intl``.

Terms are AND-ed. Operators: ``=`` (one value or ``v1,v2``), ``!=``, ``>``, ``>=``, ``<``,
``<=``, ``~`` (contains). Friendly aliases: ``type=big``, ``country=Iceland``,
``runway>=3km``, ``elevation>2000m``.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

import numpy as np
import pandas as pd
from rapidfuzz import process

from skyscope.data.normalize import SURFACES
from skyscope.data.store import DataStore

KEYS = ("country", "region", "continent", "type", "runway", "surface", "elevation", "service",
        "iata", "name", "city")
KEY_ALIASES = {"rwy": "runway", "runways": "runway", "length": "runway", "elev": "elevation",
               "alt": "elevation", "altitude": "elevation", "municipality": "city", "town": "city",
               "state": "region", "province": "region", "scheduled": "service", "kind": "type"}
NUMERIC = {"runway", "elevation"}

TYPE_ALIASES = {
    "large": "large_airport", "big": "large_airport", "major": "large_airport", "hub": "large_airport",
    "medium": "medium_airport", "mid": "medium_airport", "small": "small_airport",
    "tiny": "small_airport", "heliport": "heliport", "helipad": "heliport", "heli": "heliport",
    "seaplane": "seaplane_base", "seaplane_base": "seaplane_base", "water": "seaplane_base",
    "balloon": "balloonport", "balloonport": "balloonport", "closed": "closed",
    "large_airport": "large_airport", "medium_airport": "medium_airport",
    "small_airport": "small_airport", "airport": "airport",
}
CONTINENTS = {"af": "AF", "africa": "AF", "an": "AN", "antarctica": "AN", "as": "AS", "asia": "AS",
              "eu": "EU", "europe": "EU", "na": "NA", "north america": "NA",
              "northamerica": "NA", "oc": "OC", "oceania": "OC", "australia": "OC",
              "sa": "SA", "south america": "SA", "southamerica": "SA"}
COUNTRY_ALIASES = {"usa": "US", "america": "US", "uk": "GB", "britain": "GB", "england": "GB",
                   "uae": "AE", "emirates": "AE", "russia": "RU", "korea": "KR",
                   "south korea": "KR", "iran": "IR", "vietnam": "VN", "bolivia": "BO",
                   "tanzania": "TZ", "laos": "LA", "syria": "SY", "venezuela": "VE"}
YES = {"yes", "y", "true", "1", "scheduled"}
NO = {"no", "n", "false", "0", "none"}

_TERM = re.compile(r"^\s*([A-Za-z_]+)\s*(>=|<=|!=|=|>|<|~)\s*(.*?)\s*$")
_LENGTH = re.compile(r"^(-?[\d,]*\.?\d+)\s*(ft|feet|'|m|meters?|metres?|km|k)?$", re.IGNORECASE)


class FilterError(ValueError):
    """A filter expression could not be understood; message is user-facing."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


@dataclass(frozen=True)
class Term:
    """One parsed condition."""

    key: str
    op: str
    values: tuple[str, ...]
    number: float | None = None  # numeric value, already converted to feet

    def describe(self) -> str:
        """Human-readable form for breadcrumbs ("elevation > 10,000 ft")."""
        if self.number is not None:
            return f"{self.key} {self.op} {self.number:,.0f} ft"
        sep = " ~ " if self.op == "~" else f" {self.op} "
        return f"{self.key}{sep}{', '.join(self.values)}"


def parse_length_ft(text: str) -> float:
    """Parse "8000", "8,000ft", "2000m", "3km", "3k" → feet."""
    match = _LENGTH.match(text.strip())
    if not match:
        raise FilterError(f"'{text}' is not a length", "examples: 8000, 2500m, 3km")
    value = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "ft").lower()
    # Round metric conversions to whole feet: OurAirports stores e.g. a 4,000 m runway as 13,123 ft.
    if unit.startswith("m"):
        return float(round(value * 3.28084))
    if unit == "km":
        return float(round(value * 3280.84))
    if unit == "k":
        return value * 1000
    return value


def _resolve_key(raw: str) -> str:
    key = raw.lower()
    key = KEY_ALIASES.get(key, key)
    if key in KEYS:
        return key
    guess = process.extractOne(key, KEYS + tuple(KEY_ALIASES), score_cutoff=60)
    hint = f"did you mean '{KEY_ALIASES.get(guess[0], guess[0])}'?" if guess else ""
    raise FilterError(f"unknown filter key '{raw}'", hint or f"keys: {', '.join(KEYS)}")


def _resolve_country(store: DataStore, value: str) -> str:
    alias = COUNTRY_ALIASES.get(value.lower())
    if alias:
        return alias
    code = store.country_code(value)
    if code:
        return code
    names = list(store.countries["name"])
    guess = process.extractOne(value, names, score_cutoff=60)
    if guess and guess[1] >= 88:
        return store.country_code(guess[0]) or value.upper()
    hint = f"did you mean '{guess[0]}'?" if guess else "use a name (Bolivia) or ISO code (BO)"
    raise FilterError(f"unknown country '{value}'", hint)


def _resolve_type(value: str) -> str:
    key = value.lower().replace(" ", "_")
    if key in TYPE_ALIASES:
        return TYPE_ALIASES[key]
    guess = process.extractOne(key, list(TYPE_ALIASES), score_cutoff=60)
    hint = f"did you mean '{guess[0]}'?" if guess else "types: large, medium, small, heliport, seaplane, closed"
    raise FilterError(f"unknown airport type '{value}'", hint)


def parse(expr: str, store: DataStore) -> list[Term]:
    """Parse a filter expression into terms (raises FilterError with a hint)."""
    try:
        parts = shlex.split(expr)
    except ValueError as exc:
        raise FilterError(f"could not read filter: {exc}", 'quote values with spaces: name~"san jose"') from exc
    # Re-attach loose words to the previous term: "country=united states" → one term.
    merged: list[str] = []
    for part in parts:
        if merged and not _TERM.match(part):
            merged[-1] += " " + part
        else:
            merged.append(part)
    terms: list[Term] = []
    for part in merged:
        match = _TERM.match(part)
        if not match:
            raise FilterError(f"'{part}' is not a filter term",
                              "form is key=value, key>number or key~text, e.g. elevation>5000")
        key, op, raw_value = _resolve_key(match.group(1)), match.group(2), match.group(3)
        if not raw_value:
            raise FilterError(f"'{part}' has no value", "e.g. country=US")
        if key in NUMERIC:
            if op == "~":
                raise FilterError(f"'{key}' is numeric; use =, >, <, >= or <=")
            terms.append(Term(key, op, (raw_value,), parse_length_ft(raw_value)))
            continue
        if op in (">", "<", ">=", "<="):
            raise FilterError(f"'{key}' is text; use =, != or ~", f"e.g. {key}=...")
        values = tuple(v.strip() for v in raw_value.split(",") if v.strip())
        if key == "country":
            values = tuple(_resolve_country(store, v) for v in values)
        elif key == "continent":
            resolved = []
            for v in values:
                code = CONTINENTS.get(v.lower())
                if not code:
                    raise FilterError(f"unknown continent '{v}'", "AF, AN, AS, EU, NA, OC, SA")
                resolved.append(code)
            values = tuple(resolved)
        elif key == "type":
            values = tuple(_resolve_type(v) for v in values)
        elif key == "surface":
            resolved = []
            for v in values:
                low = {"asphalt": "paved", "concrete": "paved", "hard": "paved", "turf": "grass",
                       "gravel": "gravel-dirt", "dirt": "gravel-dirt"}.get(v.lower(), v.lower())
                if low not in SURFACES:
                    raise FilterError(f"unknown surface '{v}'", f"surfaces: {', '.join(SURFACES)}")
                resolved.append(low)
            values = tuple(resolved)
        elif key == "service" and values[0].lower() not in YES | NO:
            raise FilterError("service is yes or no", "e.g. service=yes")
        terms.append(Term(key, op, values))
    return terms


def _text_mask(series: pd.Series, term: Term) -> np.ndarray:
    low = series.str.lower()
    if term.op == "~" or term.key in ("name", "city"):
        mask = np.zeros(len(series), dtype=bool)
        for v in term.values:
            mask |= low.str.contains(v.lower(), regex=False, na=False).to_numpy()
    else:
        mask = low.isin([v.lower() for v in term.values]).to_numpy()
    return ~mask if term.op == "!=" else mask


def apply(terms: list[Term], store: DataStore, pool: list[int] | None = None) -> list[int]:
    """Row indices matching all terms (closed airports excluded unless asked for)."""
    ap = store.airports
    mask = np.ones(len(ap), dtype=bool)
    if pool is not None:
        sub = np.zeros(len(ap), dtype=bool)
        sub[np.asarray(pool, dtype=int)] = True
        mask &= sub
    wants_closed = any(t.key == "type" and "closed" in t.values and t.op != "!=" for t in terms)
    if not wants_closed:
        mask &= (ap["type"] != "closed").to_numpy()
    for term in terms:
        mask &= _term_mask(term, store)
    idx = np.flatnonzero(mask)
    order = np.lexsort((-ap["longest_ft"].fillna(0).to_numpy()[idx], ap["type_rank"].to_numpy()[idx]))
    return [int(i) for i in idx[order]]


def _term_mask(term: Term, store: DataStore) -> np.ndarray:
    ap = store.airports
    if term.number is not None:
        col = ap["longest_ft"] if term.key == "runway" else ap["elevation_ft"]
        values = col.to_numpy(dtype=float)
        ops = {">": np.greater, ">=": np.greater_equal, "<": np.less, "<=": np.less_equal,
               "=": lambda a, b: np.abs(a - b) < 0.5, "!=": lambda a, b: np.abs(a - b) >= 0.5}
        with np.errstate(invalid="ignore"):
            return ops[term.op](values, term.number) & ~np.isnan(values)
    if term.key == "country":
        return _text_mask(ap["iso_country"], term)
    if term.key == "continent":
        return _text_mask(ap["continent"], term)
    if term.key == "region":
        by_code = _text_mask(ap["iso_region"], Term(term.key, "=", term.values))
        by_name = _text_mask(ap["region_name"], Term(term.key, "~", term.values))
        mask = by_code | by_name
        return ~mask if term.op == "!=" else mask
    if term.key == "type":
        if "airport" in term.values:
            mask = ap["type"].isin(["large_airport", "medium_airport", "small_airport"]).to_numpy()
            return ~mask if term.op == "!=" else mask
        return _text_mask(ap["type"], Term(term.key, "!=" if term.op == "!=" else "=", term.values))
    if term.key == "surface":
        rw = store.runways
        idents = rw.loc[~rw["closed"] & rw["surface"].isin(term.values), "airport_ident"].unique()
        mask = ap["ident"].isin(idents).to_numpy()
        return ~mask if term.op == "!=" else mask
    if term.key == "service":
        want = term.values[0].lower() in YES
        if term.op == "!=":
            want = not want
        return (ap["scheduled"] == want).to_numpy()
    if term.key == "iata":
        if term.values[0].lower() in YES | {"any"}:
            return (ap["iata_code"] != "").to_numpy()
        if term.values[0].lower() in NO:
            return (ap["iata_code"] == "").to_numpy()
        return _text_mask(ap["iata_code"], Term(term.key, term.op if term.op != "~" else "=", term.values))
    if term.key == "name":
        return _text_mask(ap["name"], term)
    if term.key == "city":
        return _text_mask(ap["municipality"], term)
    raise FilterError(f"unsupported filter key '{term.key}'")
