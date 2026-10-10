"""Build the bundled offline snapshot in src/skyscope/snapshot/.

Usage:
    python scripts/make_snapshot.py              # airports + METAR sample + showcase climate
    python scripts/make_snapshot.py --no-climate # skip the (slower) climate downloads

The snapshot is what SkyScope falls back to with no network (and with --offline):
gzipped OurAirports CSVs, a timestamped bulk METAR sample, and ERA5 + CMIP6 caches for
the showcase airports. Keep it under ~15 MB.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skyscope.config import SNAPSHOT_DIR  # noqa: E402
from skyscope.data import sources  # noqa: E402

#: Showcase airports bundled with climate data (IATA codes), grouped as in PLAN.md §2.5.
SHOWCASE = {
    "hot": ["PHX", "LAS", "DFW", "IAH", "DXB", "DOH", "KWI", "RUH", "DEL", "BKK"],
    "high": ["DEN", "MEX", "BOG", "UIO", "LPB", "ADD", "NBO", "JNB"],
    "control": ["LHR", "JFK", "SIN", "OSL"],
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_airports(manifest: dict) -> None:
    """Download OurAirports CSVs and store them gzipped."""
    for stem in sources.AIRPORT_FILES:
        resp = sources.http_get(sources.airport_file_url(stem))
        out = SNAPSHOT_DIR / f"{stem}.csv.gz"
        out.write_bytes(gzip.compress(resp.content, compresslevel=9))
        manifest["fetched"][f"{stem}.csv.gz"] = _now()
        print(f"  {stem:<10} {len(resp.content) / 1e6:6.1f} MB → {out.stat().st_size / 1e6:5.1f} MB")


def build_metars(manifest: dict) -> None:
    """Save the current worldwide bulk METAR file as a timestamped sample."""
    resp = sources.http_get(sources.METAR_BULK_URL)
    out = SNAPSHOT_DIR / "metars.cache.csv.gz"
    out.write_bytes(resp.content)
    manifest["fetched"]["metars.cache.csv.gz"] = _now()
    print(f"  metars     {out.stat().st_size / 1e6:5.2f} MB")


def build_climate(manifest: dict) -> None:
    """Fetch ERA5 history and CMIP6 projections for the showcase airports."""
    from skyscope.data.store import get_store

    from skyscope.climate import history, projections

    store = get_store()
    climate_dir = SNAPSHOT_DIR / "climate"
    climate_dir.mkdir(exist_ok=True)
    idents: list[str] = []
    for group, codes in SHOWCASE.items():
        for code in codes:
            row = store.lookup(code)
            if row is None:
                print(f"  ! {code} not found in airports data; skipped")
                continue
            ident = row["ident"]
            for attempt in range(3):
                try:
                    era = history.fetch_era5(row, target_dir=climate_dir)
                    cm = projections.fetch_cmip6(row, target_dir=climate_dir)
                    break
                except sources.FetchError as exc:
                    print(f"  ! {code}: {exc}; retrying")
                    time.sleep(5 * (attempt + 1))
            else:
                continue
            idents.append(ident)
            print(f"  {group:<8} {code} {ident:<5} ERA5 {len(era.dates):>6} days · CMIP6 {len(cm.models)} models")
            time.sleep(1)  # be gentle with the free API
    manifest["climate_airports"] = idents
    manifest["fetched"]["climate"] = _now()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-climate", action="store_true", help="skip climate downloads")
    parser.add_argument("--only-climate", action="store_true", help="only rebuild climate data")
    args = parser.parse_args()

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = sources.snapshot_manifest() or {}
    manifest.setdefault("fetched", {})
    if not args.only_climate:
        print("OurAirports:")
        build_airports(manifest)
        print("NOAA bulk METAR:")
        build_metars(manifest)
    if not args.no_climate:
        print("Climate (ERA5 + CMIP6):")
        build_climate(manifest)
    (SNAPSHOT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    total = sum(p.stat().st_size for p in SNAPSHOT_DIR.rglob("*") if p.is_file())
    print(f"Snapshot size: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
