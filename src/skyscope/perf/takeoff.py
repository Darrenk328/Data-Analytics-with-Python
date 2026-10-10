"""Takeoff weight-restriction model (PLAN.md §3.2–3.3). Pure functions; no I/O.

    TODR(W)  = TODR_ref × (W / MTOW)² / (σ × τ)
    W_allow  = min(MTOW, MTOW × sqrt(R × σ × τ / TODR_ref))
    τ        = δ × flat(OAT);  flat = 1 − λ × max(0, OAT − (T_isa + ΔT_flat))

An educational estimate, not an Airplane Flight Manual calculation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from skyscope.perf.aircraft import Aircraft
from skyscope.perf.atmosphere import (
    STD_ALTIMETER_INHG,
    density_altitude_ft,
    density_ratio,
    isa_temp_c,
    pressure_altitude_ft,
    pressure_ratio,
)

OK, RESTRICTED, SEVERE, ABOVE_LIMIT = "OK", "RESTRICTED", "SEVERE", "ABOVE LIMIT"
RESTRICTION_EPS_KG = 1.0  # below this the restriction is numerical noise
T_MIN_C, T_MAX_C = -60.0, 60.0


def thrust_ratio(ac: Aircraft, oat_c, pressure_alt_ft):
    """τ = δ × flat-rating factor (floored at 0.05 so it stays physical)."""
    t_flat = isa_temp_c(pressure_alt_ft) + ac.flat_rate_dc
    flat = 1.0 - ac.thrust_lapse * np.maximum(0.0, np.asarray(oat_c, dtype=float) - t_flat)
    return pressure_ratio(pressure_alt_ft) * np.maximum(flat, 0.05)


def todr_m(ac: Aircraft, weight_kg, sigma, tau):
    """Takeoff distance required (m) at a weight, density ratio and thrust ratio."""
    return ac.tofl_ref_m * (np.asarray(weight_kg, dtype=float) / ac.mtow_kg) ** 2 / (sigma * tau)


def allowable_weight_kg(ac: Aircraft, runway_m, sigma, tau):
    """Heaviest weight whose TODR fits the runway, capped at MTOW."""
    ratio = np.maximum(np.asarray(runway_m, dtype=float) * sigma * tau / ac.tofl_ref_m, 0.0)
    return np.minimum(ac.mtow_kg, ac.mtow_kg * np.sqrt(ratio))


def restriction_kg(ac: Aircraft, elevation_ft, runway_m, oat_c, altimeter_inhg=STD_ALTIMETER_INHG):
    """Weight that must be offloaded (kg); vectorised over any argument."""
    pa = pressure_altitude_ft(elevation_ft, altimeter_inhg)
    sigma = density_ratio(density_altitude_ft(pa, oat_c))
    tau = thrust_ratio(ac, oat_c, pa)
    return ac.mtow_kg - allowable_weight_kg(ac, runway_m, sigma, tau)


@dataclass(frozen=True)
class Threshold:
    """Temperature at which restriction begins.

    kind: "normal" (value is the threshold), "always" (restricted even at −60 °C),
    "never" (no restriction up to 60 °C).
    """

    kind: str
    temp_c: float | None


def threshold_temp(ac: Aircraft, elevation_ft: float, runway_m: float,
                   altimeter_inhg: float = STD_ALTIMETER_INHG, tol: float = 0.01) -> Threshold:
    """OAT where W_allow first drops below MTOW, by bisection on [−60, 60] °C."""

    def margin(t: float) -> float:  # > 0 → not restricted
        pa = pressure_altitude_ft(elevation_ft, altimeter_inhg)
        sigma = float(density_ratio(density_altitude_ft(pa, t)))
        tau = float(thrust_ratio(ac, t, pa))
        return runway_m * sigma * tau - ac.tofl_ref_m

    lo, hi = T_MIN_C, T_MAX_C
    if margin(lo) < 0:
        return Threshold("always", None)
    if margin(hi) >= 0:
        return Threshold("never", None)
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if margin(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return Threshold("normal", round((lo + hi) / 2, 2))


@dataclass(frozen=True)
class TakeoffResult:
    """Everything the views need for one airport / aircraft / temperature."""

    aircraft_id: str
    status: str
    oat_c: float
    elevation_ft: float
    runway_m: float
    altimeter_inhg: float
    pressure_alt_ft: float
    density_alt_ft: float
    sigma: float
    tau: float
    todr_mtow_m: float  # distance needed at MTOW today
    allowable_kg: float
    restriction_kg: float
    restriction_pct: float  # of MTOW
    payload_pct: float  # of max payload
    passengers: float
    threshold: Threshold
    approx: bool

    @property
    def margin_c(self) -> float | None:
        """Degrees between today's OAT and the threshold (positive = still OK)."""
        if self.threshold.kind != "normal" or self.threshold.temp_c is None:
            return None
        return self.threshold.temp_c - self.oat_c

    def to_dict(self) -> dict:
        """JSON-friendly dict (rounded)."""
        out = asdict(self)
        out["threshold"] = {"kind": self.threshold.kind, "temp_c": self.threshold.temp_c}
        for key, value in out.items():
            if isinstance(value, float):
                out[key] = round(value, 4 if key in ("sigma", "tau") else 1)
        out["estimate"] = True
        return out


def evaluate(ac: Aircraft, elevation_ft: float, runway_m: float, oat_c: float,
             altimeter_inhg: float | None = None, kg_per_passenger: float = 100.0) -> TakeoffResult:
    """Full takeoff verdict for one case."""
    alt = STD_ALTIMETER_INHG if altimeter_inhg is None else altimeter_inhg
    pa = float(pressure_altitude_ft(elevation_ft, alt))
    da = float(density_altitude_ft(pa, oat_c))
    sigma = float(density_ratio(da))
    tau = float(thrust_ratio(ac, oat_c, pa))
    allow = float(allowable_weight_kg(ac, runway_m, sigma, tau))
    restr = max(0.0, ac.mtow_kg - allow)
    if restr < RESTRICTION_EPS_KG:
        restr = 0.0
    if ac.max_oat_c is not None and oat_c > ac.max_oat_c:
        status = ABOVE_LIMIT
    elif restr == 0.0:
        status = OK
    elif restr > ac.max_payload_kg:
        status = SEVERE
    else:
        status = RESTRICTED
    return TakeoffResult(
        aircraft_id=ac.id, status=status, oat_c=float(oat_c), elevation_ft=float(elevation_ft),
        runway_m=float(runway_m), altimeter_inhg=alt, pressure_alt_ft=pa, density_alt_ft=da,
        sigma=sigma, tau=tau, todr_mtow_m=float(todr_m(ac, ac.mtow_kg, sigma, tau)),
        allowable_kg=allow, restriction_kg=restr, restriction_pct=restr / ac.mtow_kg,
        payload_pct=min(1.0, restr / ac.max_payload_kg), passengers=restr / kg_per_passenger,
        threshold=threshold_temp(ac, elevation_ft, runway_m, alt), approx=ac.approx,
    )


def sweep(ac: Aircraft, elevation_ft: float, runway_m: float, temps_c: np.ndarray,
          altimeter_inhg: float = STD_ALTIMETER_INHG) -> np.ndarray:
    """Allowable weight (kg) across a range of temperatures (for the --sweep chart)."""
    return ac.mtow_kg - restriction_kg(ac, elevation_ft, runway_m, temps_c, altimeter_inhg)
