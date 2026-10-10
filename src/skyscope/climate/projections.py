"""CMIP6 HighResMIP projections (Open-Meteo climate API) and the delta method.

Projections are NOT spliced onto ERA5. For each model we take the change in its daily-Tmax
distribution (per calendar month, per quantile) between its own 1996–2025 and 2031–2050,
and add that change to the observed ERA5 1996–2025 record. See NOTES.md for why the
reference period is 1996–2025 rather than 1951–1980.
Scenario: close to RCP8.5 / high emissions; data ends 2050.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from skyscope.climate.history import _find, pack, unpack, user_climate_dir
from skyscope.config import RUNTIME
from skyscope.data import sources

MODELS = ("CMCC_CM2_VHR4", "FGOALS_f3_H", "HiRAM_SIT_HR", "MRI_AGCM3_2_S", "EC_Earth3P_HR",
          "MPI_ESM1_2_XR", "NICAM16_8S")
START, END = "1991-01-01", "2050-01-01"
RECENT = (1996, 2025)
FUTURE = (2031, 2050)
QUANTILES = np.linspace(0.02, 0.98, 25)


@dataclass
class Cmip6:
    """Daily Tmax per model (models × days, °C)."""

    ident: str
    dates: np.ndarray
    models: list[str]
    tmax: np.ndarray
    origin: str = "cache"


def fetch_cmip6(row: dict[str, Any], target_dir: Path | None = None) -> Cmip6:
    """Download all models' daily Tmax 1991–2050 for an airport and save it as .npz."""
    params = {"latitude": row["lat"], "longitude": row["lon"], "start_date": START, "end_date": END,
              "models": ",".join(MODELS), "daily": "temperature_2m_max"}
    if row.get("elevation_ft") is not None:
        params["elevation"] = round(row["elevation_ft"] / 3.28084)
    resp = sources.http_get(sources.CLIMATE_URL, params, timeout=60)
    daily = resp.json()["daily"]
    models = [m for m in MODELS if f"temperature_2m_max_{m}" in daily]
    data = np.stack([pack(daily[f"temperature_2m_max_{m}"]) for m in models])
    out = (target_dir or user_climate_dir()) / f"cmip6_{row['ident']}.npz"
    np.savez_compressed(out, start=np.array(daily["time"][0]), models=np.array(models), tmax=data)
    return load_file(row["ident"], out, "download")


def load_file(ident: str, path: Path, origin: str) -> Cmip6:
    """Read a CMIP6 .npz cache file."""
    with np.load(path) as z:
        start = np.datetime64(str(z["start"]), "D")
        models = [str(m) for m in z["models"]]
        tmax = unpack(z["tmax"])
    return Cmip6(ident, start + np.arange(tmax.shape[1]), models, tmax, origin)


def load_cmip6(row: dict[str, Any], allow_fetch: bool = True) -> Cmip6 | None:
    """CMIP6 for an airport from cache/snapshot, fetching once if allowed and online."""
    found = _find(f"cmip6_{row['ident']}.npz")
    if found is not None:
        return load_file(row["ident"], *found)
    if allow_fetch and not RUNTIME.offline:
        return fetch_cmip6(row)
    return None


def _years(dates: np.ndarray) -> np.ndarray:
    return dates.astype("datetime64[Y]").astype(int) + 1970


def _months(dates: np.ndarray) -> np.ndarray:
    return dates.astype("datetime64[M]").astype(int) % 12 + 1


def delta_projection(obs_dates: np.ndarray, obs_tmax: np.ndarray, cm: Cmip6) -> dict[str, np.ndarray]:
    """Per model: ERA5 1996–2025 daily Tmax shifted by the model's quantile change → 2031–2050 climate."""
    oy, om = _years(obs_dates), _months(obs_dates)
    obs_mask = (oy >= RECENT[0]) & (oy <= RECENT[1]) & ~np.isnan(obs_tmax)
    my, mm = _years(cm.dates), _months(cm.dates)
    out: dict[str, np.ndarray] = {}
    for k, model in enumerate(cm.models):
        series = cm.tmax[k]
        projected = np.full(obs_mask.sum(), np.nan)
        obs_vals = obs_tmax[obs_mask]
        obs_mon = om[obs_mask]
        for month in range(1, 13):
            rec = series[(my >= RECENT[0]) & (my <= RECENT[1]) & (mm == month)]
            fut = series[(my >= FUTURE[0]) & (my <= FUTURE[1]) & (mm == month)]
            rec, fut = rec[~np.isnan(rec)], fut[~np.isnan(fut)]
            sel = obs_mon == month
            if len(rec) < 100 or len(fut) < 100 or not sel.any():
                continue
            delta = np.quantile(fut, QUANTILES) - np.quantile(rec, QUANTILES)
            vals = obs_vals[sel]
            ranks = (np.argsort(np.argsort(vals)) + 0.5) / len(vals)
            projected[sel] = vals + np.interp(ranks, QUANTILES, delta)
        out[model] = projected
    return out


def model_warming(cm: Cmip6) -> dict[str, float]:
    """Each model's mean Tmax change (°C) from 1996–2025 to 2031–2050."""
    my = _years(cm.dates)
    rec = (my >= RECENT[0]) & (my <= RECENT[1])
    fut = (my >= FUTURE[0]) & (my <= FUTURE[1])
    return {m: float(np.nanmean(cm.tmax[k][fut]) - np.nanmean(cm.tmax[k][rec])) for k, m in enumerate(cm.models)}
