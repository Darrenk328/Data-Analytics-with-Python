"""Standard-atmosphere helpers (PLAN.md §3.1). Work on floats or numpy arrays; no I/O."""

from __future__ import annotations

import numpy as np

STD_ALTIMETER_INHG = 29.92
HPA_PER_INHG = 33.8639


def pressure_altitude_ft(elevation_ft, altimeter_inhg=STD_ALTIMETER_INHG):
    """PA = elevation + (29.92 − altimeter) × 1000."""
    return elevation_ft + (STD_ALTIMETER_INHG - altimeter_inhg) * 1000.0


def isa_temp_c(pressure_alt_ft):
    """ISA temperature at a pressure altitude: 15 − 0.0019812 × PA (°C)."""
    return 15.0 - 0.0019812 * pressure_alt_ft


def density_altitude_ft(pressure_alt_ft, oat_c):
    """DA = PA + 118.8 × (OAT − T_isa)."""
    return pressure_alt_ft + 118.8 * (oat_c - isa_temp_c(pressure_alt_ft))


def density_ratio(density_alt_ft):
    """σ = (1 − 6.8756e-6 × DA)^4.2559."""
    return np.power(1.0 - 6.8756e-6 * np.asarray(density_alt_ft, dtype=float), 4.2559)


def pressure_ratio(pressure_alt_ft):
    """δ = (1 − 6.8756e-6 × PA)^5.2559."""
    return np.power(1.0 - 6.8756e-6 * np.asarray(pressure_alt_ft, dtype=float), 5.2559)


def hpa_to_inhg(hpa: float) -> float:
    """Convert hectopascals to inches of mercury."""
    return hpa / HPA_PER_INHG
