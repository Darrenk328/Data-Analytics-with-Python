"""Airport search: exact codes, then name/city prefixes, then fuzzy matching.

Ranking (highest first): exact IATA > exact ICAO/ident/GPS > local code > name/city prefix >
keyword prefix > fuzzy. Within a tier, larger and scheduled-service airports are boosted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from skyscope.data.store import DataStore

TYPE_BOOST = {"large_airport": 150, "medium_airport": 80, "small_airport": 20}
SCHEDULED_BOOST = 40


@dataclass(frozen=True)
class Hit:
    """One search result."""

    idx: int
    score: float
    why: str  # "IATA code", "name", "city", "keyword", "fuzzy"


def _boost(ap: pd.DataFrame) -> np.ndarray:
    return (ap["type"].map(TYPE_BOOST).fillna(0).to_numpy()
            + np.where(ap["scheduled"].to_numpy(), SCHEDULED_BOOST, 0))


def _search_frame(store: DataStore) -> pd.DataFrame:
    """Lower-cased search columns, computed once per store."""
    cached = getattr(store, "_search_cache", None)
    if cached is not None:
        return cached
    ap = store.airports
    frame = pd.DataFrame({
        "name": ap["name"].str.lower(),
        "city": ap["municipality"].str.lower(),
        "keywords": ap["keywords"].str.lower(),
        "boost": _boost(ap),
    })
    frame["fuzzy_text"] = frame["name"] + " " + frame["city"]
    store._search_cache = frame  # type: ignore[attr-defined]
    return frame


def search(store: DataStore, text: str, limit: int = 20, include_closed: bool = False,
           pool: list[int] | None = None) -> list[Hit]:
    """Search airports by code, name, city or keyword. ``pool`` restricts to given rows."""
    query = " ".join(text.strip().split())
    if not query:
        return []
    ap = store.airports
    frame = _search_frame(store)
    best: dict[int, Hit] = {}

    def offer(idx: int, score: float, why: str) -> None:
        if idx not in best or best[idx].score < score:
            best[idx] = Hit(idx, score, why)

    upper = query.upper()
    for col, base, why in (("iata_code", 1000, "IATA code"), ("ident", 900, "ident"),
                           ("icao_code", 900, "ICAO code"), ("gps_code", 850, "GPS code"),
                           ("local_code", 800, "local code")):
        idx = store.index[col].get(upper)
        if idx is not None:
            offer(idx, base + frame["boost"].iat[idx], why)

    allowed = np.ones(len(ap), dtype=bool)
    if not include_closed:
        allowed &= (ap["type"] != "closed").to_numpy()
    if pool is not None:
        mask = np.zeros(len(ap), dtype=bool)
        mask[np.asarray(pool, dtype=int)] = True
        allowed &= mask

    q = query.lower()
    boost = frame["boost"].to_numpy()
    for col, base, why in (("name", 600, "name"), ("city", 600, "city")):
        hits = np.flatnonzero(frame[col].str.startswith(q, na=False).to_numpy() & allowed)
        for i in hits:
            offer(int(i), base + boost[i], why)
    # word-start inside the name ("harbor" → "Phoenix Sky Harbor ...")
    word_hits = np.flatnonzero(frame["name"].str.contains(rf"\b{re.escape(q)}", regex=True, na=False).to_numpy() & allowed)
    for i in word_hits:
        offer(int(i), 520 + boost[i], "name")
    kw_hits = np.flatnonzero(frame["keywords"].str.contains(rf"(?:^|,\s*){re.escape(q)}", regex=True, na=False).to_numpy() & allowed)
    for i in kw_hits:
        offer(int(i), 500 + boost[i], "keyword")

    if len(best) < limit and len(q) >= 3:
        for col in ("name", "city"):
            choices = frame[col].where(allowed, "")
            for _text, score, i in process.extract(q, choices, scorer=fuzz.WRatio,
                                                   limit=limit * 4, score_cutoff=75):
                offer(int(i), score * 4 + boost[int(i)], "fuzzy")

    ranked = sorted(best.values(), key=lambda h: (-h.score, int(ap["type_rank"].iat[h.idx])))
    if pool is not None:
        ranked = [h for h in ranked if allowed[h.idx]]
    return ranked[:limit]


def suggest(store: DataStore, text: str, limit: int = 3) -> list[int]:
    """Close matches for a code or name that wasn't found (for "did you mean")."""
    query = text.strip()
    if not query:
        return []
    out: list[int] = []
    upper = query.upper()
    if 3 <= len(upper) <= 4:
        codes = store.index["iata_code" if len(upper) == 3 else "ident"]
        rank = store.airports["type_rank"].to_numpy()
        matches = process.extract(upper, list(codes.keys()), scorer=fuzz.ratio, limit=None,
                                  score_cutoff=66)
        def prefix(code: str) -> int:
            return next((i for i, (a, b) in enumerate(zip(code, upper, strict=False)) if a != b),
                        min(len(code), len(upper)))

        ranked = sorted(((score, prefix(code), codes[code]) for code, score, _ in matches),
                        key=lambda m: (-m[0], -m[1], rank[m[2]]))
        out = [idx for _score, _pre, idx in ranked if rank[idx] <= 1][:limit]
        if out:
            return out
    for hit in search(store, query, limit=limit):
        if hit.idx not in out:
            out.append(hit.idx)
    return out[:limit]
