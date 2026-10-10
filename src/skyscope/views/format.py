"""Formatting helpers: never 'nan'/'None' (use —), thousands separators, labelled units."""

from __future__ import annotations

import math
from datetime import datetime, timezone

DASH = "—"
EST = "≈"
FT_PER_M = 3.28084
LB_PER_KG = 2.20462


def _missing(value: float | int | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def num(value: float | int | None, decimals: int = 0) -> str:
    """1135.0 → "1,135"; None → "—"."""
    if _missing(value):
        return DASH
    return f"{value:,.{decimals}f}"


def signed(value: float | None, decimals: int = 1) -> str:
    """+2.1 / −0.4 (true minus sign)."""
    if _missing(value):
        return DASH
    text = f"{value:+,.{decimals}f}"
    return text.replace("-", "−")


def temp(celsius: float | None, units: str = "metric", decimals: int = 0) -> str:
    """Temperature with unit: "41 °C" or "106 °F"."""
    if _missing(celsius):
        return DASH
    if units == "imperial":
        return f"{celsius * 9 / 5 + 32:.{decimals}f} °F".replace("-", "−")
    return f"{celsius:.{decimals}f} °C".replace("-", "−")


def dtemp(delta_c: float | None, units: str = "metric", decimals: int = 1) -> str:
    """Temperature *difference*: "+2.1 °C" or "+3.8 °F"."""
    if _missing(delta_c):
        return DASH
    value = delta_c * 9 / 5 if units == "imperial" else delta_c
    return f"{signed(value, decimals)} {'°F' if units == 'imperial' else '°C'}"


def feet(ft: float | None) -> str:
    """"1,135 ft"."""
    return DASH if _missing(ft) else f"{ft:,.0f} ft"


def elevation(ft: float | None) -> str:
    """Elevation with both units: "1,135 ft (346 m)"."""
    if _missing(ft):
        return DASH
    return f"{ft:,.0f} ft ({ft / FT_PER_M:,.0f} m)"


def length(ft: float | None, units: str = "metric") -> str:
    """Runway length in the display unit: "3,502 m" / "11,489 ft"."""
    if _missing(ft):
        return DASH
    if units == "imperial":
        return f"{ft:,.0f} ft"
    return f"{ft / FT_PER_M:,.0f} m"


def length_both(ft: float | None, units: str = "metric") -> str:
    """"3,502 m (11,489 ft)" — primary unit first."""
    if _missing(ft):
        return DASH
    if units == "imperial":
        return f"{ft:,.0f} ft ({ft / FT_PER_M:,.0f} m)"
    return f"{ft / FT_PER_M:,.0f} m ({ft:,.0f} ft)"


def mass(kg: float | None, units: str = "metric") -> str:
    """"610 kg" / "1,345 lb"."""
    if _missing(kg):
        return DASH
    if units == "imperial":
        return f"{kg * LB_PER_KG:,.0f} lb"
    return f"{kg:,.0f} kg"


def pct(value: float | None, decimals: int = 0) -> str:
    """0.123 → "12%"."""
    return DASH if _missing(value) else f"{value * 100:.{decimals}f}%"


def utc(dt: datetime | None) -> str:
    """"17:51Z" (date added when not today)."""
    if dt is None:
        return DASH
    dt = dt.astimezone(timezone.utc)
    if dt.date() == datetime.now(timezone.utc).date():
        return dt.strftime("%H:%MZ")
    return dt.strftime("%Y-%m-%d %H:%MZ")


def age(dt: datetime | None, now: datetime | None = None) -> str:
    """Relative age: "just now", "4 min ago", "3 h ago", "2 days ago"."""
    if dt is None:
        return DASH
    now = now or datetime.now(timezone.utc)
    secs = (now - dt).total_seconds()
    if secs < 0:
        return "just now"
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs / 60:.0f} min ago"
    if secs < 48 * 3600:
        return f"{secs / 3600:.0f} h ago"
    return f"{secs / 86400:.0f} days ago"


def stamp(dt: datetime | None) -> str:
    """UTC time plus relative age: "17:51Z (4 min ago)"."""
    return DASH if dt is None else f"{utc(dt)} ({age(dt)})"


def flag(iso: str | None) -> str:
    """Country flag emoji from an ISO-3166 alpha-2 code ("" if not a valid code)."""
    if not iso or len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso.upper())


def text(value: object) -> str:
    """Any value as display text, with — for missing."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return DASH
    s = str(value).strip()
    return s if s and s.lower() not in {"nan", "none"} else DASH


def plural(n: float, word: str, plural_word: str | None = None) -> str:
    """"1 airport" / "17 airports"."""
    whole = round(n)
    return f"{num(n)} {word if whole == 1 else (plural_word or word + 's')}"
