"""ERA5 daily history from Open-Meteo (1940 → 2 days ago), cached permanently as compact .npz.

Load order: user cache → bundled snapshot → network (unless --offline).
Temperatures are stored as int16 tenths of °C (missing = -32768) to keep the snapshot small.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from skyscope.config import RUNTIME, SNAPSHOT_DIR, cache_dir
from skyscope.data import sources

MISSING = -32768
START = "1940-01-01"


@dataclass
class Era5:
    """Daily Tmax (°C, NaN = missing) for one airport."""

    ident: str
    dates: np.ndarray  # datetime64[D]
    tmax: np.ndarray
    utc_offset_s: int | None = None
    timezone: str = ""
    origin: str = "cache"


def user_climate_dir() -> Path:
    """Folder for downloaded climate caches."""
    path = cache_dir() / "climate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pack(values: list[float | None]) -> np.ndarray:
    """Floats → int16 tenths with a missing sentinel."""
    arr = np.array([np.nan if v is None else v for v in values], dtype=float)
    out = np.where(np.isnan(arr), MISSING, np.round(arr * 10))
    return out.astype(np.int16)


def unpack(arr: np.ndarray) -> np.ndarray:
    """int16 tenths → float °C with NaN."""
    out = arr.astype(float) / 10.0
    out[arr == MISSING] = np.nan
    return out


def _find(name: str) -> tuple[Path, str] | None:
    for folder, origin in ((user_climate_dir(), "cache"), (SNAPSHOT_DIR / "climate", "snapshot")):
        path = folder / name
        if path.exists():
            return path, origin
    return None


def fetch_era5(row: dict[str, Any], target_dir: Path | None = None) -> Era5:
    """Download the full ERA5 daily record for an airport and save it as .npz."""
    end = (date.today() - timedelta(days=2)).isoformat()
    params = {"latitude": row["lat"], "longitude": row["lon"], "start_date": START, "end_date": end,
              "daily": "temperature_2m_max", "timezone": "auto"}
    if row.get("elevation_ft") is not None:
        params["elevation"] = round(row["elevation_ft"] / 3.28084)
    resp = sources.http_get(sources.ERA5_URL, params, timeout=30)
    payload = resp.json()
    daily = payload["daily"]
    first = np.datetime64(daily["time"][0], "D")
    tmax = pack(daily["temperature_2m_max"])
    meta = {"utc_offset_seconds": payload.get("utc_offset_seconds"), "timezone": payload.get("timezone", "")}
    out = (target_dir or user_climate_dir()) / f"era5_{row['ident']}.npz"
    np.savez_compressed(out, start=np.array(str(first)), tmax=tmax, meta=np.array(json.dumps(meta)))
    return load_file(row["ident"], out, "download")


def load_file(ident: str, path: Path, origin: str) -> Era5:
    """Read an ERA5 .npz cache file."""
    with np.load(path) as z:
        start = np.datetime64(str(z["start"]), "D")
        tmax = unpack(z["tmax"])
        meta = json.loads(str(z["meta"]))
    dates = start + np.arange(len(tmax))
    return Era5(ident, dates, tmax, meta.get("utc_offset_seconds"), meta.get("timezone", ""), origin)


def load_era5(row: dict[str, Any], allow_fetch: bool = True) -> Era5 | None:
    """ERA5 for an airport from cache/snapshot, fetching once if allowed and online."""
    found = _find(f"era5_{row['ident']}.npz")
    if found is not None:
        return load_file(row["ident"], *found)
    if allow_fetch and not RUNTIME.offline:
        return fetch_era5(row)
    return None


def cached_idents() -> list[str]:
    """Airports with ERA5 data available locally (cache + snapshot)."""
    out = set()
    for folder in (user_climate_dir(), SNAPSHOT_DIR / "climate"):
        if folder.exists():
            out |= {p.stem.removeprefix("era5_") for p in folder.glob("era5_*.npz")}
    return sorted(out)
