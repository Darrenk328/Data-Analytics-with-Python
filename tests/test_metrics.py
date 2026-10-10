"""Climate metrics on synthetic series with known answers."""

import numpy as np
import pytest

from skyscope.climate.metrics import (
    baseline_p95,
    heat_summary,
    restricted_days,
    trend,
    warm_season,
    warm_season_by_year,
)
from skyscope.climate.projections import Cmip6, delta_projection
from skyscope.perf.aircraft import get_aircraft

DATES = np.arange(np.datetime64("1940-01-01"), np.datetime64("2026-01-01"))
DOY = (DATES - DATES.astype("datetime64[Y]")).astype(int)
YEARS = DATES.astype("datetime64[Y]").astype(int) + 1970


def seasonal(peak_doy: int, mean=25.0, amp=10.0, trend_per_decade=0.0, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = mean + amp * np.cos(2 * np.pi * (DOY - peak_doy) / 365.25)
    t += trend_per_decade * (YEARS - 1940) / 10
    return t + rng.normal(0, noise, len(t))


def test_known_trend_recovered() -> None:
    tmax = seasonal(200, trend_per_decade=0.3, noise=1.0)
    tr = trend(warm_season_by_year(DATES, tmax))
    assert tr.slope_per_decade == pytest.approx(0.3, abs=0.05)
    assert tr.clear


def test_flat_noisy_series_not_clear() -> None:
    tmax = seasonal(200, noise=3.0, seed=3)
    assert not trend(warm_season_by_year(DATES, tmax)).clear


def test_hemisphere_aware_warm_season() -> None:
    assert warm_season(DATES, seasonal(200)) == (6, 7, 8)  # northern summer (e.g. PHX)
    jnb = warm_season(DATES, seasonal(15))  # southern summer: peak mid-January
    assert jnb in ((12, 1, 2), (11, 12, 1), (1, 2, 3)) and 1 in jnb
    # tropics: tiny amplitude still yields a valid 3-month window (e.g. SIN)
    assert len(warm_season(DATES, seasonal(100, amp=0.5))) == 3


def test_dec_feb_season_spans_year_boundary() -> None:
    by_year = warm_season_by_year(DATES, seasonal(15), (12, 1, 2))
    assert 1940 not in by_year  # Dec 1939 missing → incomplete first season dropped
    assert 1941 in by_year


def test_percentile_threshold() -> None:
    tmax = np.tile(np.arange(100, dtype=float), len(DATES) // 100 + 1)[: len(DATES)]
    assert baseline_p95(DATES, tmax) == pytest.approx(94.05, abs=0.2)


def test_restricted_days_and_delta_method() -> None:
    ac = get_aircraft("737-800")
    tmax = seasonal(200, mean=33, amp=10)  # Phoenix-like
    st = restricted_days(ac, 1135, 3000, DATES, tmax)
    assert st.recent > 0
    # a model that warms uniformly by 2 °C must shift ERA5 by ~2 °C
    cm_dates = np.arange(np.datetime64("1991-01-01"), np.datetime64("2050-01-02"))
    cm_doy = (cm_dates - cm_dates.astype("datetime64[Y]")).astype(int)
    cm_years = cm_dates.astype("datetime64[Y]").astype(int) + 1970
    base = 30 + 8 * np.cos(2 * np.pi * (cm_doy - 200) / 365.25)
    model = base + np.where(cm_years >= 2031, 2.0, 0.0)
    cm = Cmip6("TEST", cm_dates, ["M1"], model[None, :])
    proj = delta_projection(DATES, tmax, cm)["M1"]
    recent = tmax[(YEARS >= 1996) & (YEARS <= 2025)]
    assert np.nanmean(proj) - recent.mean() == pytest.approx(2.0, abs=0.05)
    st2 = restricted_days(ac, 1135, 3000, DATES, tmax, {"M1": proj})
    assert st2.projected_median > st2.recent


def test_heat_summary_record() -> None:
    tmax = seasonal(200)
    tmax[5000] = 60.0
    s = heat_summary(DATES, tmax)
    assert s.record_c == 60.0 and s.record_date == str(DATES[5000])
