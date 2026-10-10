"""Load and validate the aircraft table (perf/aircraft.toml)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rapidfuzz import process

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

TABLE = Path(__file__).with_name("aircraft.toml")
CATEGORIES = ("turboprop", "regional", "narrowbody", "widebody")


@dataclass(frozen=True)
class Aircraft:
    """One aircraft type's model inputs."""

    id: str
    name: str
    category: str
    mtow_kg: float
    oew_kg: float
    max_payload_kg: float
    tofl_ref_m: float
    flat_rate_dc: float = 15.0
    thrust_lapse: float = 0.01
    max_oat_c: float | None = None
    approx: bool = True
    source: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mark(self) -> str:
        """"≈" when any input could not be sourced, else ""."""
        return "≈" if self.approx else ""


class AircraftError(ValueError):
    """Unknown aircraft id (message + hint are user-facing)."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def _validate(raw: dict) -> Aircraft:
    for key in ("id", "name", "category", "mtow_kg", "oew_kg", "max_payload_kg", "tofl_ref_m"):
        if key not in raw:
            raise ValueError(f"aircraft.toml: {raw.get('id', '?')} missing '{key}'")
    if raw["category"] not in CATEGORIES:
        raise ValueError(f"aircraft.toml: {raw['id']} has unknown category {raw['category']!r}")
    ac = Aircraft(
        id=raw["id"], name=raw["name"], category=raw["category"],
        mtow_kg=float(raw["mtow_kg"]), oew_kg=float(raw["oew_kg"]),
        max_payload_kg=float(raw["max_payload_kg"]), tofl_ref_m=float(raw["tofl_ref_m"]),
        flat_rate_dc=float(raw.get("flat_rate_dc", 15.0)),
        thrust_lapse=float(raw.get("thrust_lapse", 0.01)),
        max_oat_c=float(raw["max_oat_c"]) if "max_oat_c" in raw else None,
        approx=bool(raw.get("approx", True)), source=str(raw.get("source", "")),
        aliases=tuple(str(a).lower() for a in raw.get("aliases", [])),
    )
    if not (ac.oew_kg < ac.mtow_kg and ac.max_payload_kg > 0 and ac.tofl_ref_m > 0):
        raise ValueError(f"aircraft.toml: {ac.id} has inconsistent weights/lengths")
    return ac


@lru_cache(maxsize=1)
def load_aircraft() -> tuple[Aircraft, ...]:
    """All aircraft types, in table order (small → large)."""
    with TABLE.open("rb") as fh:
        data = tomllib.load(fh)
    return tuple(_validate(row) for row in data.get("aircraft", []))


def get_aircraft(key: str) -> Aircraft:
    """Find an aircraft by id or alias, case-insensitively ("737", "a320neo", "B789")."""
    want = key.strip().lower()
    table = load_aircraft()
    for ac in table:
        if want == ac.id.lower() or want in ac.aliases:
            return ac
    names = {ac.id: ac for ac in table}
    guess = process.extractOne(key, list(names), score_cutoff=55)
    hint = f"did you mean {guess[0]}?" if guess else "types: " + ", ".join(names)
    raise AircraftError(f"unknown aircraft '{key}'", hint)
