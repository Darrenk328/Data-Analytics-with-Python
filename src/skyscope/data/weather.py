"""NOAA AWC METAR/TAF: single-station JSON, worldwide bulk CSV, and plain-English decoding.

Field names follow the real responses saved in tests/fixtures (metar.json, metars.csv, taf.json).
Note: the JSON API reports ``altim`` in hPa; the bulk CSV reports ``altim_in_hg``.
"""

from __future__ import annotations

import gzip
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from skyscope.config import RUNTIME
from skyscope.data import sources
from skyscope.data.geo import compass, haversine_nm_many
from skyscope.data.normalize import clean_float, clean_str
from skyscope.perf.atmosphere import hpa_to_inhg

WX_WORDS = {"TS": "thunderstorm", "SH": "showers", "RA": "rain", "SN": "snow", "DZ": "drizzle",
            "FG": "fog", "BR": "mist", "HZ": "haze", "FU": "smoke", "DU": "dust", "SA": "sand",
            "GR": "hail", "GS": "small hail", "PL": "ice pellets", "SQ": "squalls",
            "FZ": "freezing", "VC": "nearby", "BL": "blowing", "MI": "shallow", "UP": "precipitation"}
COVER_WORDS = {"SKC": "clear", "CLR": "clear", "NSC": "no significant cloud", "CAVOK": "clear",
               "FEW": "a few clouds", "SCT": "scattered clouds", "BKN": "broken clouds",
               "OVC": "overcast", "OVX": "sky obscured"}


@dataclass
class Metar:
    """One decoded observation."""

    station: str
    observed: datetime | None
    raw: str
    temp_c: float | None = None
    dewpoint_c: float | None = None
    wind_dir: float | None = None  # None when calm or variable
    wind_kt: float | None = None
    gust_kt: float | None = None
    visibility: str = ""
    altimeter_inhg: float | None = None
    flight_category: str = ""
    wx: str = ""
    clouds: list[tuple[str, int | None]] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None


@dataclass
class WxLookup:
    """Result of asking for a station's weather: the report (if any) and where it came from."""

    metar: Metar | None
    origin: str  # "live" | "cache" | "bulk" | "nearby" | "none"
    note: str = ""


def _epoch(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso(value) -> datetime | None:
    text = clean_str(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def metar_from_json(d: dict) -> Metar:
    """Decode one element of the METAR JSON API response."""
    wdir = d.get("wdir")
    altim = clean_float(d.get("altim"))
    return Metar(
        station=clean_str(d.get("icaoId")), observed=_epoch(d.get("obsTime")),
        raw=clean_str(d.get("rawOb")), temp_c=clean_float(d.get("temp")),
        dewpoint_c=clean_float(d.get("dewp")),
        wind_dir=clean_float(wdir) if not isinstance(wdir, str) else None,
        wind_kt=clean_float(d.get("wspd")), gust_kt=clean_float(d.get("wgst")),
        visibility=clean_str(d.get("visib")),
        altimeter_inhg=round(hpa_to_inhg(altim), 2) if altim else None,
        flight_category=clean_str(d.get("fltCat")), wx=clean_str(d.get("wxString")),
        clouds=[(clean_str(c.get("cover")), c.get("base")) for c in d.get("clouds") or []],
        lat=clean_float(d.get("lat")), lon=clean_float(d.get("lon")),
    )


def metar_from_bulk(row: dict) -> Metar:
    """Decode one row of the bulk METAR CSV (repeated sky columns come suffixed .1/.2/.3)."""
    clouds = []
    for suffix in ("", ".1", ".2", ".3"):
        cover = clean_str(row.get(f"sky_cover{suffix}"))
        if cover:
            base = clean_float(row.get(f"cloud_base_ft_agl{suffix}"))
            clouds.append((cover, int(base) if base is not None else None))
    wdir = clean_str(row.get("wind_dir_degrees"))
    return Metar(
        station=clean_str(row.get("station_id")), observed=_iso(row.get("observation_time")),
        raw=clean_str(row.get("raw_text")), temp_c=clean_float(row.get("temp_c")),
        dewpoint_c=clean_float(row.get("dewpoint_c")),
        wind_dir=clean_float(wdir) if wdir and wdir != "VRB" else None,
        wind_kt=clean_float(row.get("wind_speed_kt")), gust_kt=clean_float(row.get("wind_gust_kt")),
        visibility=clean_str(row.get("visibility_statute_mi")),
        altimeter_inhg=clean_float(row.get("altim_in_hg")),
        flight_category=clean_str(row.get("flight_category")), wx=clean_str(row.get("wx_string")),
        clouds=clouds, lat=clean_float(row.get("latitude")), lon=clean_float(row.get("longitude")),
    )


# ---------------------------------------------------------------------------- bulk


@dataclass
class Bulk:
    """All current METARs worldwide."""

    frame: pd.DataFrame
    fetched: datetime | None
    origin: str


_BULK: Bulk | None = None


def parse_bulk(data: bytes) -> pd.DataFrame:
    """Parse the (possibly gzipped) bulk CSV."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    for col in ("temp_c", "altim_in_hg", "latitude", "longitude", "wind_speed_kt"):
        df[col] = pd.to_numeric(df[col].replace("", np.nan), errors="coerce")
    df["observed"] = pd.to_datetime(df["observation_time"], utc=True, errors="coerce")
    # newest report per station
    return df.sort_values("observed").drop_duplicates("station_id", keep="last").reset_index(drop=True)


def load_bulk(max_age_s: float = sources.WX_MAX_AGE_S) -> Bulk | None:
    """Bulk METARs: fresh download if online (cached 5 min), else cache/snapshot."""
    global _BULK
    if _BULK is not None and _BULK.fetched is not None:
        age = (datetime.now(timezone.utc) - _BULK.fetched).total_seconds()
        if age < max_age_s or RUNTIME.offline:
            return _BULK
    found = sources.ensure("metars.cache.csv.gz", sources.METAR_BULK_URL, max_age_s, compress=False)
    if found is None:
        return None
    try:
        frame = parse_bulk(found.path.read_bytes())
    except (OSError, ValueError, KeyError):
        return None
    fetched = found.fetched
    if not frame.empty and frame["observed"].notna().any():
        fetched = min(fetched, frame["observed"].max().to_pydatetime())
    _BULK = Bulk(frame, fetched, found.origin)
    return _BULK


def from_bulk(bulk: Bulk | None, station: str) -> Metar | None:
    """A station's report from the bulk file, if present."""
    if bulk is None or not station:
        return None
    rows = bulk.frame[bulk.frame["station_id"] == station.upper()]
    return None if rows.empty else metar_from_bulk(rows.iloc[-1].to_dict())


def nearest(bulk: Bulk | None, lat: float, lon: float, max_nm: float = 25) -> tuple[Metar, float, str] | None:
    """Closest bulk report within ``max_nm`` (report, distance nm, compass direction)."""
    if bulk is None or bulk.frame.empty:
        return None
    f = bulk.frame
    d = haversine_nm_many(lat, lon, f["latitude"].to_numpy(dtype=float), f["longitude"].to_numpy(dtype=float))
    d = np.where(np.isnan(d), np.inf, d)
    i = int(np.argmin(d))
    if d[i] > max_nm:
        return None
    from skyscope.data.geo import bearing_deg

    row = f.iloc[i].to_dict()
    brg = bearing_deg(lat, lon, float(row["latitude"]), float(row["longitude"]))
    return metar_from_bulk(row), float(d[i]), compass(brg)


# --------------------------------------------------------------------------- single


def get_metar(station: str, lat: float | None = None, lon: float | None = None) -> WxLookup:
    """Current METAR for a station: 5-min cache → live API → stale cache → bulk → nearby."""
    station = station.upper()
    cached = sources.json_cache_get("metar", station, sources.WX_MAX_AGE_S)
    if cached is not None:
        payload, _ = cached
        return WxLookup(metar_from_json(payload[0]) if payload else None, "cache")
    note = ""
    if not RUNTIME.offline:
        try:
            resp = sources.http_get(sources.METAR_URL, {"ids": station, "format": "json"})
            payload = resp.json() if resp.status_code != 204 and resp.content.strip() else []
            sources.json_cache_put("metar", station, payload)
            if payload:
                return WxLookup(metar_from_json(payload[0]), "live")
        except (sources.FetchError, ValueError) as exc:
            note = f"live weather unavailable ({exc})"
    else:
        note = "offline mode — showing the most recent saved report"
    stale = sources.json_cache_get("metar", station, None)
    if stale is not None and stale[0]:
        return WxLookup(metar_from_json(stale[0][0]), "cache", note)  # type: ignore[index]
    bulk = load_bulk()
    m = from_bulk(bulk, station)
    if m is not None:
        return WxLookup(m, "bulk", note)
    if lat is not None and lon is not None:
        near = nearest(bulk, lat, lon)
        if near is not None:
            m, dist, direction = near
            return WxLookup(m, "nearby", f"no report from {station}; nearest is {m.station}, "
                                          f"{dist:.0f} nm {direction}")
    return WxLookup(None, "none", note or f"no current weather report for {station}")


def get_taf(station: str) -> str | None:
    """Raw TAF text (cached 5 min; None if none / offline with no cache)."""
    station = station.upper()
    cached = sources.json_cache_get("taf", station, None if RUNTIME.offline else sources.WX_MAX_AGE_S)
    if cached is None and not RUNTIME.offline:
        try:
            resp = sources.http_get(sources.TAF_URL, {"ids": station, "format": "json"})
            payload = resp.json() if resp.status_code != 204 and resp.content.strip() else []
            sources.json_cache_put("taf", station, payload)
            cached = (payload, datetime.now(timezone.utc))
        except (sources.FetchError, ValueError):
            return None
    if not cached or not cached[0]:
        return None
    return clean_str(cached[0][0].get("rawTAF")) or None  # type: ignore[index]


# --------------------------------------------------------------------------- decode


def describe(m: Metar) -> str:
    """Plain-English one-liner: "Broken clouds at 25,000 ft · wind SE 11 kt · visibility 10+ mi"."""
    parts = []
    if m.wx:
        parts.append(decode_wx(m.wx).capitalize())
    if m.clouds:
        cover, base = max(m.clouds, key=lambda c: ["FEW", "SCT", "BKN", "OVC", "OVX"].index(c[0])
                          if c[0] in ("FEW", "SCT", "BKN", "OVC", "OVX") else -1)
        words = COVER_WORDS.get(cover, cover.lower())
        parts.append(f"{words.capitalize()}" + (f" at {base:,} ft" if base and words != "clear" else ""))
    elif "CAVOK" in m.raw:
        parts.append("Clear, visibility OK")
    else:
        parts.append("Clear skies")
    if m.wind_kt is not None:
        if m.wind_kt == 0:
            parts.append("calm wind")
        elif m.wind_dir is None:
            parts.append(f"variable wind {m.wind_kt:.0f} kt")
        else:
            gust = f", gusting {m.gust_kt:.0f}" if m.gust_kt else ""
            parts.append(f"wind {compass(m.wind_dir)} {m.wind_kt:.0f} kt{gust}")
    if m.visibility:
        parts.append(f"visibility {m.visibility} mi")
    return " · ".join(parts)


def decode_wx(code: str) -> str:
    """"-TSRA BR" → "light thunderstorm rain, mist"."""
    out = []
    for token in code.split():
        prefix = "light " if token.startswith("-") else "heavy " if token.startswith("+") else ""
        body = token.lstrip("+-")
        words = [WX_WORDS.get(body[i:i + 2], body[i:i + 2]) for i in range(0, len(body), 2)]
        out.append(prefix + " ".join(words))
    return ", ".join(out)
