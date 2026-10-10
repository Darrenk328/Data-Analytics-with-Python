"""Source URLs, polite HTTP, and the user-cache → bundled-snapshot lookup order.

Nothing in this module prints. Every network call goes through :func:`http_get`, which
enforces the 10 s timeout, the custom User-Agent, a simple per-host rate limit and the
``--offline`` flag.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from skyscope import __version__
from skyscope.config import RUNTIME, SNAPSHOT_DIR, cache_dir

USER_AGENT = (
    f"SkyScope/{__version__} (educational climate/aviation explorer; "
    "+https://github.com/Darrenk328/Data-Analytics-with-Python)"
)
TIMEOUT_S = 10.0

OURAIRPORTS_BASE = "https://davidmegginson.github.io/ourairports-data"
AIRPORT_FILES = ("airports", "runways", "countries", "regions")

METAR_BULK_URL = "https://aviationweather.gov/data/cache/metars.cache.csv.gz"
METAR_URL = "https://aviationweather.gov/api/data/metar"
TAF_URL = "https://aviationweather.gov/api/data/taf"
ERA5_URL = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_URL = "https://climate-api.open-meteo.com/v1/climate"

WX_MAX_AGE_S = 5 * 60  # NOAA asks clients to cache for at least 5 minutes
_RATE_LIMITS = {"aviationweather.gov": 100}  # requests per minute

#: Count of real HTTP requests made by this process (used by tests and --offline QA).
NETWORK_CALLS = 0
_lock = threading.Lock()
_recent: dict[str, deque[float]] = {}


class OfflineError(RuntimeError):
    """Raised instead of making a network call when ``--offline`` is set."""


class FetchError(RuntimeError):
    """A network request failed (timeout, DNS, HTTP error). The message is user-friendly."""


def _throttle(host: str) -> None:
    limit = _RATE_LIMITS.get(host)
    if not limit:
        return
    with _lock:
        stamps = _recent.setdefault(host, deque())
        now = time.monotonic()
        while stamps and now - stamps[0] > 60:
            stamps.popleft()
        if len(stamps) >= limit:
            time.sleep(max(0.0, 60 - (now - stamps[0])))
        stamps.append(time.monotonic())


def http_get(url: str, params: dict | None = None, timeout: float = TIMEOUT_S) -> httpx.Response:
    """GET ``url`` politely. Returns the response for 2xx (incl. 204); raises otherwise."""
    global NETWORK_CALLS
    if RUNTIME.offline:
        raise OfflineError("offline mode: network access is disabled")
    host = urlparse(url).hostname or ""
    _throttle(host)
    NETWORK_CALLS += 1
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.TimeoutException as exc:
        raise FetchError(f"{host} did not answer within {timeout:.0f} s") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"could not reach {host} ({type(exc).__name__})") from exc
    if resp.status_code >= 400:
        raise FetchError(f"{host} returned HTTP {resp.status_code}")
    return resp


# --------------------------------------------------------------------------- file lookup


@dataclass(frozen=True)
class DataFile:
    """A located data file and where it came from."""

    path: Path
    origin: str  # "cache" | "snapshot" | "download"
    fetched: datetime  # when the content was fetched (UTC)


def user_data_dir() -> Path:
    """Directory holding downloaded copies that override the bundled snapshot."""
    path = cache_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def snapshot_manifest() -> dict:
    """Metadata written by scripts/make_snapshot.py (fetch timestamps, airport list)."""
    try:
        return json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    except (OSError, ValueError):
        return {}


def _snapshot_time(name: str, path: Path) -> datetime:
    stamp = snapshot_manifest().get("fetched", {}).get(name)
    if stamp:
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            pass
    return _mtime(path)


def locate(name: str) -> DataFile | None:
    """Find ``name`` in the user cache, then in the bundled snapshot."""
    cached = user_data_dir() / name
    if cached.exists():
        return DataFile(cached, "cache", _mtime(cached))
    snap = SNAPSHOT_DIR / name
    if snap.exists():
        return DataFile(snap, "snapshot", _snapshot_time(name, snap))
    return None


def download(url: str, name: str, compress: bool = True) -> DataFile:
    """Download ``url`` into the user cache as ``name`` (gzipping if ``compress``)."""
    resp = http_get(url)
    target = user_data_dir() / name
    tmp = target.with_suffix(target.suffix + ".part")
    body = resp.content
    if compress and not url.endswith(".gz"):
        body = gzip.compress(body, compresslevel=6)
    tmp.write_bytes(body)
    shutil.move(tmp, target)
    return DataFile(target, "download", _mtime(target))


def ensure(name: str, url: str, max_age_s: float | None, compress: bool = True) -> DataFile | None:
    """Return a usable copy of ``name``: fresh cache, else download, else stale cache/snapshot.

    ``max_age_s=None`` means "any cached or bundled copy is fine; never auto-download".
    Network failures are swallowed here — the caller gets the best copy available (or None).
    """
    found = locate(name)
    if found is not None and max_age_s is None:
        return found
    if found is not None and found.origin == "cache":
        age = (datetime.now(timezone.utc) - found.fetched).total_seconds()
        if age < (max_age_s or 0):
            return found
    if not RUNTIME.offline:
        try:
            return download(url, name, compress=compress)
        except (FetchError, OSError):
            pass
    return found


def airport_file_url(stem: str) -> str:
    """URL of an OurAirports CSV by stem (``airports``, ``runways``, ...)."""
    return f"{OURAIRPORTS_BASE}/{stem}.csv"


def json_cache_get(kind: str, key: str, max_age_s: float | None) -> tuple[object, datetime] | None:
    """Read a cached JSON API response if present and (when ``max_age_s`` given) fresh enough."""
    path = cache_dir() / kind / f"{key}.json"
    if not path.exists():
        return None
    fetched = _mtime(path)
    if max_age_s is not None and (datetime.now(timezone.utc) - fetched).total_seconds() > max_age_s:
        return None
    try:
        return json.loads(path.read_text()), fetched
    except (OSError, ValueError):
        return None


def json_cache_put(kind: str, key: str, payload: object) -> None:
    """Store a JSON API response in the cache (best effort)."""
    folder = cache_dir() / kind
    folder.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        (folder / f"{key}.json").write_text(json.dumps(payload))
