"""DataStore: load, clean and join OurAirports airports + runways (with a pickle cache).

Load order for each CSV: user cache (written by ``skyscope update``) → bundled snapshot.
The cleaned tables are pickled in the cache dir, keyed on the source files' size/mtime,
so a warm start is a single fast unpickle.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from skyscope.config import cache_dir
from skyscope.data import sources
from skyscope.data.normalize import (
    PAVED,
    clean_float,
    clean_str,
    heading_from_ident,
    normalize_surface,
)

PICKLE_VERSION = 3
TYPE_RANK = {"large_airport": 0, "medium_airport": 1, "small_airport": 2, "seaplane_base": 3,
             "heliport": 4, "balloonport": 5, "closed": 6}
TYPE_LABEL = {"large_airport": "large airport", "medium_airport": "medium airport",
              "small_airport": "small airport", "seaplane_base": "seaplane base",
              "heliport": "heliport", "balloonport": "balloonport", "closed": "closed"}
NO_PERF_TYPES = {"heliport", "balloonport", "seaplane_base", "closed"}

_STR_COLS = ["ident", "type", "name", "continent", "iso_country", "iso_region", "municipality",
             "icao_code", "iata_code", "gps_code", "local_code", "home_link", "wikipedia_link",
             "keywords"]


class DataUnavailable(RuntimeError):
    """No airport data in the cache or the bundled snapshot."""


def _read_csv(path: Path) -> pd.DataFrame:
    # keep_default_na=False: Namibia ("NA") and North America ("NA") are real values.
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[], encoding="utf-8")


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("", np.nan), errors="coerce")


def clean_runways(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise surfaces, flags and headings; derive missing headings from idents."""
    rw = pd.DataFrame({
        "airport_ident": raw["airport_ident"].str.strip(),
        "length_ft": _num(raw["length_ft"]),
        "width_ft": _num(raw["width_ft"]),
        "surface_raw": raw["surface"].str.strip(),
        "lighted": raw["lighted"].str.strip() == "1",
        "closed": raw["closed"].str.strip() == "1",
        "le_ident": raw["le_ident"].str.strip(),
        "he_ident": raw["he_ident"].str.strip(),
        "le_heading": _num(raw["le_heading_degT"]),
        "he_heading": _num(raw["he_heading_degT"]),
        "le_elevation_ft": _num(raw["le_elevation_ft"]),
        "he_elevation_ft": _num(raw["he_elevation_ft"]),
    })
    rw["surface"] = rw["surface_raw"].map(normalize_surface)
    rw["le_heading_derived"] = rw["le_heading"].isna()
    rw["he_heading_derived"] = rw["he_heading"].isna()
    le_from_ident = rw["le_ident"].map(heading_from_ident).astype(float)
    he_from_ident = rw["he_ident"].map(heading_from_ident).astype(float)
    rw["le_heading"] = rw["le_heading"].fillna(le_from_ident)
    rw["he_heading"] = rw["he_heading"].fillna(he_from_ident)
    # One end known → the other is its reciprocal.
    rw["le_heading"] = rw["le_heading"].fillna((rw["he_heading"] + 180) % 360)
    rw["he_heading"] = rw["he_heading"].fillna((rw["le_heading"] + 180) % 360)
    rw["name"] = np.where(rw["he_ident"] != "", rw["le_ident"] + "/" + rw["he_ident"], rw["le_ident"])
    return rw


def _runway_summary(rw: pd.DataFrame) -> pd.DataFrame:
    open_rw = rw[~rw["closed"] & rw["length_ft"].notna()]
    count = open_rw.groupby("airport_ident").size().rename("runway_count")
    longest = open_rw.groupby("airport_ident")["length_ft"].max().rename("longest_ft")
    paved = open_rw[open_rw["surface"] == PAVED].sort_values("length_ft", ascending=False)
    best = paved.drop_duplicates("airport_ident").set_index("airport_ident")
    best = best[["length_ft", "name", "width_ft"]].rename(columns={
        "length_ft": "longest_paved_ft", "name": "longest_paved_name", "width_ft": "longest_paved_width_ft"})
    shortest = paved.groupby("airport_ident")["length_ft"].min().rename("shortest_paved_ft")
    return pd.concat([count, longest, best, shortest], axis=1)


def clean_airports(raw: pd.DataFrame, runways: pd.DataFrame, countries: pd.DataFrame,
                   regions: pd.DataFrame) -> pd.DataFrame:
    """Clean airports and join country/region names and runway summaries."""
    ap = pd.DataFrame({c: raw[c].str.strip() for c in _STR_COLS})
    ap["id"] = _num(raw["id"]).astype("Int64")
    ap["lat"] = _num(raw["latitude_deg"])
    ap["lon"] = _num(raw["longitude_deg"])
    ap["elevation_ft"] = _num(raw["elevation_ft"])
    ap["scheduled"] = raw["scheduled_service"].str.strip().str.lower() == "yes"
    ap = ap[ap["lat"].notna() & ap["lon"].notna()].copy()

    cmap = dict(zip(countries["code"], countries["name"], strict=False))
    rmap = dict(zip(regions["code"], regions["name"], strict=False))
    ap["country_name"] = ap["iso_country"].map(cmap).fillna("")
    ap["region_name"] = ap["iso_region"].map(rmap).fillna("")

    summary = _runway_summary(runways)
    ap = ap.join(summary, on="ident")
    ap["runway_count"] = ap["runway_count"].fillna(0).astype(int)
    ap["longest_paved_name"] = ap["longest_paved_name"].fillna("")
    ap["type_rank"] = ap["type"].map(TYPE_RANK).fillna(9).astype(int)
    ap["code"] = np.where(ap["iata_code"] != "", ap["iata_code"],
                          np.where(ap["icao_code"] != "", ap["icao_code"], ap["ident"]))
    ap["station"] = np.where(ap["icao_code"] != "", ap["icao_code"],
                             np.where(ap["gps_code"] != "", ap["gps_code"], ap["ident"]))
    ap["perf_ok"] = (~ap["type"].isin(NO_PERF_TYPES) & ap["elevation_ft"].notna()
                     & ap["longest_paved_ft"].notna())
    ap = ap.reset_index(drop=True)
    return ap


def _build_index(ap: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Code → row maps. Where codes collide, keep the most important airport."""
    order = ap.sort_values(["type_rank", "scheduled"], ascending=[False, True]).index
    maps: dict[str, dict[str, int]] = {}
    for col in ("iata_code", "icao_code", "ident", "gps_code", "local_code"):
        values = ap.loc[order, col].str.upper()
        # Later (more important) rows overwrite earlier ones.
        maps[col] = {code: int(i) for code, i in zip(values, order, strict=False) if code}
    return maps


@dataclass
class DataStore:
    """Cleaned airports/runways tables with code lookup."""

    airports: pd.DataFrame
    runways: pd.DataFrame
    countries: pd.DataFrame
    regions: pd.DataFrame
    index: dict[str, dict[str, int]]
    origin: str = "snapshot"
    fetched: datetime | None = None
    _runways_by_ident: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ lookup
    def lookup_index(self, code: str) -> int | None:
        """Row index for an IATA/ICAO/ident/GPS/local code, or None."""
        key = clean_str(code).upper()
        if not key:
            return None
        if len(key) == 3 and key.isalpha():
            order = ("iata_code", "ident", "icao_code", "gps_code", "local_code")
        else:
            order = ("ident", "icao_code", "gps_code", "iata_code", "local_code")
        for col in order:
            idx = self.index[col].get(key)
            if idx is not None:
                return idx
        return None

    def lookup(self, code: str) -> dict[str, Any] | None:
        """Airport record (dict, missing values as None) for a code, or None."""
        idx = self.lookup_index(code)
        return None if idx is None else self.record(idx)

    def record(self, idx: int) -> dict[str, Any]:
        """Airport record by row index, with NaN converted to None and an ``idx`` key."""
        row = self.airports.loc[idx].to_dict()
        out: dict[str, Any] = {"idx": int(idx)}
        for key, value in row.items():
            if isinstance(value, float):
                out[key] = clean_float(value)
            elif value is pd.NA:
                out[key] = None
            elif isinstance(value, np.generic):
                out[key] = value.item()
            else:
                out[key] = value
        return out

    def runways_for(self, ident: str) -> pd.DataFrame:
        """All runways of an airport (open first, longest first)."""
        if not self._runways_by_ident:
            for key, grp in self.runways.groupby("airport_ident"):
                self._runways_by_ident[str(key)] = grp
        grp = self._runways_by_ident.get(ident)
        if grp is None:
            return self.runways.iloc[0:0]
        return grp.sort_values(["closed", "length_ft"], ascending=[True, False])

    def country_code(self, text: str) -> str | None:
        """Resolve a country name or ISO code ("Bolivia", "bo") to an ISO code."""
        key = clean_str(text)
        if not key:
            return None
        codes = set(self.countries["code"])
        if key.upper() in codes:
            return key.upper()
        names = {n.lower(): c for c, n in zip(self.countries["code"], self.countries["name"], strict=False)}
        return names.get(key.lower())

    @property
    def size(self) -> int:
        """Number of airports (all types)."""
        return len(self.airports)


# ---------------------------------------------------------------------- loading

_STORE: DataStore | None = None


def _source_files() -> dict[str, sources.DataFile]:
    found: dict[str, sources.DataFile] = {}
    for stem in sources.AIRPORT_FILES:
        df = sources.locate(f"{stem}.csv.gz")
        if df is None:
            raise DataUnavailable(
                f"no {stem} data found — run `skyscope update` (needs network) or reinstall SkyScope")
        found[stem] = df
    return found


def _signature(files: dict[str, sources.DataFile]) -> tuple:
    return (PICKLE_VERSION,) + tuple(
        (str(f.path), f.path.stat().st_size, f.path.stat().st_mtime_ns) for f in files.values())


def build_store(files: dict[str, Path]) -> DataStore:
    """Build a DataStore from explicit CSV paths (gzipped or plain). Used by tests too."""
    raw_ap = _read_csv(files["airports"])
    rw = clean_runways(_read_csv(files["runways"]))
    countries = _read_csv(files["countries"])[["code", "name", "continent"]]
    regions = _read_csv(files["regions"])[["code", "name", "iso_country"]]
    ap = clean_airports(raw_ap, rw, countries, regions)
    return DataStore(ap, rw, countries, regions, _build_index(ap))


def get_store(reload: bool = False) -> DataStore:
    """Process-wide DataStore (cached in memory and as a pickle on disk)."""
    global _STORE
    if _STORE is not None and not reload:
        return _STORE
    files = _source_files()
    sig = _signature(files)
    pkl = cache_dir() / "store.pkl"
    store: DataStore | None = None
    if pkl.exists() and not reload:
        try:
            with pkl.open("rb") as fh:
                saved_sig, store = pickle.load(fh)
            if saved_sig != sig:
                store = None
        except Exception:  # corrupt/old pickle: just rebuild
            store = None
    if store is None:
        store = build_store({k: v.path for k, v in files.items()})
        try:
            with pkl.open("wb") as fh:
                pickle.dump((sig, store), fh, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass
    ap_file = files["airports"]
    store.origin, store.fetched = ap_file.origin, ap_file.fetched
    _STORE = store
    return store


def update_airports() -> list[str]:
    """Download fresh OurAirports CSVs into the user cache. Returns the files updated."""
    done = []
    for stem in sources.AIRPORT_FILES:
        sources.download(sources.airport_file_url(stem), f"{stem}.csv.gz", compress=True)
        done.append(stem)
    get_store(reload=True)
    return done
