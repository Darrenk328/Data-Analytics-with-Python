"""Headwind / crosswind components per runway end. Pure functions; no I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class WindComponents:
    """Headwind (negative = tailwind) and crosswind (positive = from the right), in knots."""

    headwind: float
    crosswind: float

    @property
    def tailwind(self) -> float:
        """Tailwind component (0 if there's a headwind)."""
        return max(0.0, -self.headwind)


def components(runway_heading_deg: float, wind_dir_deg: float, wind_speed_kt: float) -> WindComponents:
    """Resolve a wind (direction it blows FROM) onto a runway heading."""
    diff = math.radians(wind_dir_deg - runway_heading_deg)
    head = wind_speed_kt * math.cos(diff)
    cross = wind_speed_kt * math.sin(diff)
    return WindComponents(round(head, 6) + 0.0, round(cross, 6) + 0.0)


@dataclass(frozen=True)
class RunwayEnd:
    """One usable direction of a runway."""

    ident: str
    heading_deg: float
    length_ft: float


def best_end(ends: list[RunwayEnd], wind_dir_deg: float | None, wind_speed_kt: float | None) -> RunwayEnd | None:
    """Likely active runway: the longest end with the most headwind (calm → longest)."""
    usable = [e for e in ends if e.heading_deg is not None]
    if not usable:
        return None
    if wind_dir_deg is None or not wind_speed_kt:
        return max(usable, key=lambda e: e.length_ft)
    return max(usable, key=lambda e: (round(components(e.heading_deg, wind_dir_deg, wind_speed_kt).headwind, 0),
                                      e.length_ft))
