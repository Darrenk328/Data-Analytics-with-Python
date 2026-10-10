"""Climate metrics from daily Tmax: warm season, anomalies, trend, hot days, restricted days.

Pure numpy; no I/O. Daily Tmax ≈ the hottest (worst) departure of the day — the same framing
as Coffel & Horton (2017); departures at cooler hours fare better.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from skyscope.perf.aircraft import Aircraft
from skyscope.perf.takeoff import RESTRICTION_EPS_KG, restriction_kg

BASELINE = (1951, 1980)
RECENT = (1996, 2025)


def years_of(dates: np.ndarray) -> np.ndarray:
    """Calendar year of each datetime64[D]."""
    return dates.astype("datetime64[Y]").astype(int) + 1970


def months_of(dates: np.ndarray) -> np.ndarray:
    """Calendar month (1–12) of each datetime64[D]."""
    return dates.astype("datetime64[M]").astype(int) % 12 + 1


def warm_season(dates: np.ndarray, tmax: np.ndarray) -> tuple[int, int, int]:
    """The hottest 3 consecutive months (circular), e.g. (6, 7, 8) or (12, 1, 2)."""
    m = months_of(dates)
    clim = np.array([np.nanmean(tmax[m == k]) if np.any(m == k) else -np.inf for k in range(1, 13)])
    sums = [clim[i] + clim[(i + 1) % 12] + clim[(i + 2) % 12] for i in range(12)]
    start = int(np.argmax(sums))
    return tuple(((start + j) % 12) + 1 for j in range(3))  # type: ignore[return-value]


def warm_season_by_year(dates: np.ndarray, tmax: np.ndarray, months: tuple[int, int, int] | None = None,
                        min_days: int = 80) -> dict[int, float]:
    """Mean daily max over the warm-season months, per (season) year; incomplete seasons dropped."""
    months = months or warm_season(dates, tmax)
    y, m = years_of(dates), months_of(dates)
    wraps = months[0] > months[2]  # e.g. Dec–Feb: December counts toward the next year
    season_year = np.where(wraps & (m >= months[0]), y + 1, y)
    sel = np.isin(m, months) & ~np.isnan(tmax)
    out: dict[int, float] = {}
    for year in np.unique(season_year[sel]):
        vals = tmax[sel & (season_year == year)]
        if len(vals) >= min_days:
            out[int(year)] = float(vals.mean())
    return out


@dataclass(frozen=True)
class Trend:
    """Linear trend of a yearly series."""

    slope_per_decade: float
    t_stat: float
    n: int

    @property
    def clear(self) -> bool:
        """|t| > 2 → a trend clearly distinguishable from year-to-year noise."""
        return abs(self.t_stat) > 2.0

    @property
    def label(self) -> str:
        """"clear trend" or "noisy / not distinguishable"."""
        return "clear trend" if self.clear else "noisy / not distinguishable"


def trend(series: dict[int, float]) -> Trend:
    """OLS slope (°C/decade) with a t-statistic (numpy only)."""
    x = np.array(list(series.keys()), dtype=float)
    y = np.array(list(series.values()), dtype=float)
    n = len(x)
    if n < 3:
        return Trend(0.0, 0.0, n)
    xm = x - x.mean()
    slope = float((xm * (y - y.mean())).sum() / (xm ** 2).sum())
    resid = y - (y.mean() + slope * xm)
    se = float(np.sqrt((resid ** 2).sum() / (n - 2) / (xm ** 2).sum()))
    t = slope / se if se > 0 else float("inf")
    return Trend(slope * 10, t, n)


def period_mean(series: dict[int, float], period: tuple[int, int]) -> float | None:
    """Mean of a yearly series over an inclusive period."""
    vals = [v for k, v in series.items() if period[0] <= k <= period[1]]
    return float(np.mean(vals)) if vals else None


def baseline_p95(dates: np.ndarray, tmax: np.ndarray) -> float:
    """95th percentile of daily Tmax over 1951–1980 ("unusually hot for this airport")."""
    y = years_of(dates)
    vals = tmax[(y >= BASELINE[0]) & (y <= BASELINE[1]) & ~np.isnan(tmax)]
    return float(np.percentile(vals if len(vals) else tmax[~np.isnan(tmax)], 95))


def per_year_counts(dates: np.ndarray, flags: np.ndarray, valid: np.ndarray) -> dict[int, float]:
    """Count of flagged days per complete-ish year (≥ 330 valid days)."""
    y = years_of(dates)
    out = {}
    for year in np.unique(y):
        sel = y == year
        if valid[sel].sum() >= 330:
            out[int(year)] = float(flags[sel & valid].sum())
    return out


def decade_means(per_year: dict[int, float], first: int = 1940, last_complete: int | None = None) -> list[tuple[str, float]]:
    """("1950s", mean) rows for each decade with data; partial decades marked with *."""
    rows = []
    for start in range(first, 2030, 10):
        vals = [v for k, v in per_year.items() if start <= k < start + 10]
        if vals:
            partial = len(vals) < 10
            rows.append((f"{start}s{'*' if partial else ''}", float(np.mean(vals))))
    return rows


@dataclass
class RestrictionStats:
    """Restricted days per year + mean payload lost, for one airport/aircraft/runway."""

    per_year: dict[int, float]
    decades: list[tuple[str, float]]
    recent: float
    mean_loss_kg: float
    projected: dict[str, float] = field(default_factory=dict)  # model → days/yr in 2031–2050

    @property
    def projected_median(self) -> float | None:
        """Multi-model median days/yr (2031–2050)."""
        return float(np.median(list(self.projected.values()))) if self.projected else None

    @property
    def projected_range(self) -> tuple[float, float] | None:
        """Min–max across models."""
        vals = list(self.projected.values())
        return (min(vals), max(vals)) if vals else None


def restricted_days(ac: Aircraft, elevation_ft: float, runway_m: float, dates: np.ndarray,
                    tmax: np.ndarray, projected: dict[str, np.ndarray] | None = None) -> RestrictionStats:
    """Restricted days/yr (per decade, recent, projected) using daily Tmax and standard pressure."""
    valid = ~np.isnan(tmax)
    loss = np.where(valid, restriction_kg(ac, elevation_ft, runway_m, np.nan_to_num(tmax)), 0.0)
    flags = loss > RESTRICTION_EPS_KG
    per_year = per_year_counts(dates, flags, valid)
    y = years_of(dates)
    recent_sel = (y >= RECENT[0]) & (y <= RECENT[1])
    recent = period_mean(per_year, RECENT) or 0.0
    hit = flags & recent_sel
    mean_loss = float(loss[hit].mean()) if hit.any() else 0.0
    proj = {}
    for model, series in (projected or {}).items():
        ok = ~np.isnan(series)
        if ok.sum() < 3000:
            continue
        ploss = restriction_kg(ac, elevation_ft, runway_m, series[ok])
        proj[model] = float((ploss > RESTRICTION_EPS_KG).sum() / ok.sum() * 365.25)
    return RestrictionStats(per_year, decade_means(per_year), recent, mean_loss, proj)


@dataclass
class HeatSummary:
    """Everything the heat view needs."""

    months: tuple[int, int, int]
    warm: dict[int, float]  # warm-season Tmax per year
    anomalies: dict[int, float]  # vs 1951–1980
    baseline: float
    recent: float | None
    warming: float | None  # recent − baseline
    trend: Trend
    p95: float
    hot_p95_decades: list[tuple[str, float]]
    hot_35_decades: list[tuple[str, float]]
    record_c: float
    record_date: str
    projected_warm: dict[int, float] = field(default_factory=dict)  # median, 2026–2050
    projected_warming: dict[str, float] = field(default_factory=dict)  # model → °C vs recent


def heat_summary(dates: np.ndarray, tmax: np.ndarray, hot_abs_c: float = 35.0) -> HeatSummary:
    """Warm season, anomalies, trend, hot days and record for an ERA5 series."""
    months = warm_season(dates, tmax)
    warm = warm_season_by_year(dates, tmax, months)
    base = period_mean(warm, BASELINE)
    if base is None:
        base = float(np.mean(list(warm.values())))
    recent = period_mean(warm, RECENT)
    valid = ~np.isnan(tmax)
    p95 = baseline_p95(dates, tmax)
    hot95 = per_year_counts(dates, np.nan_to_num(tmax, nan=-99) >= p95, valid)
    hot35 = per_year_counts(dates, np.nan_to_num(tmax, nan=-99) >= hot_abs_c, valid)
    i = int(np.nanargmax(tmax))
    return HeatSummary(
        months=months, warm=warm, anomalies={k: v - base for k, v in warm.items()}, baseline=base,
        recent=recent, warming=None if recent is None else recent - base, trend=trend(warm), p95=p95,
        hot_p95_decades=decade_means(hot95), hot_35_decades=decade_means(hot35),
        record_c=float(tmax[i]), record_date=str(dates[i]),
    )


def add_projection(summary: HeatSummary, cm_dates: np.ndarray, cm_tmax: np.ndarray, models: list[str]) -> None:
    """Bias-corrected projected warm-season Tmax (median of models) for 2026–2050."""
    per_model = []
    for k, model in enumerate(models):
        ws = warm_season_by_year(cm_dates, cm_tmax[k], summary.months)
        ref = period_mean(ws, RECENT)
        if ref is None or summary.recent is None:
            continue
        per_model.append({y: v - ref + summary.recent for y, v in ws.items() if 2026 <= y <= 2050})
        fut = period_mean(ws, (2031, 2050))
        if fut is not None:
            summary.projected_warming[model] = fut - ref
    for year in range(2026, 2051):
        vals = [pm[year] for pm in per_model if year in pm]
        if vals:
            summary.projected_warm[year] = float(np.median(vals))
