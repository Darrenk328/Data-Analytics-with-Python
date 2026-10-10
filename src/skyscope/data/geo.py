"""Great-circle geometry: distances in nautical miles, bearings and compass words."""

from __future__ import annotations

import math

import numpy as np

EARTH_RADIUS_NM = 3440.065
_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
_COMPASS_WORDS = {"N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
                  "S": "south", "SW": "southwest", "W": "west", "NW": "northwest"}


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in nautical miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(a)))


def haversine_nm_many(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Vectorised distance (nm) from one point to arrays of points."""
    p1, p2 = np.radians(lat), np.radians(lats)
    dp, dl = p2 - p1, np.radians(lons - lon)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_NM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial true bearing from point 1 to point 2, in degrees [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(bearing: float) -> str:
    """16-point compass abbreviation for a bearing ("NNE")."""
    return _COMPASS[int((bearing % 360) / 22.5 + 0.5) % 16]


def compass_word(bearing: float) -> str:
    """8-point compass word for a bearing ("northeast")."""
    eight = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[int((bearing % 360) / 45 + 0.5) % 8]
    return _COMPASS_WORDS[eight]


def bbox(lat: float, lon: float, radius_nm: float) -> tuple[float, float, float, float]:
    """Rough (min_lat, max_lat, min_lon, max_lon) box containing a circle of ``radius_nm``."""
    dlat = radius_nm / 60.0
    coslat = max(0.01, math.cos(math.radians(lat)))
    dlon = min(180.0, radius_nm / (60.0 * coslat))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon
