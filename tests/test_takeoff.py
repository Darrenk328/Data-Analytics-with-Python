import numpy as np
import pytest

from skyscope.perf.aircraft import AircraftError, get_aircraft, load_aircraft
from skyscope.perf.takeoff import (
    OK,
    RESTRICTED,
    SEVERE,
    evaluate,
    restriction_kg,
    sweep,
    threshold_temp,
)

AC = get_aircraft("737-800")


def test_table_loads_and_is_sourced() -> None:
    table = load_aircraft()
    assert len(table) == 6
    for ac in table:
        assert ac.source, ac.id
        assert ac.oew_kg + ac.max_payload_kg <= ac.mtow_kg


def test_aliases() -> None:
    assert get_aircraft("a320").id == "A320neo"
    assert get_aircraft("B789").id == "787-9"
    with pytest.raises(AircraftError) as err:
        get_aircraft("concorde")
    assert err.value.hint


@pytest.mark.parametrize("ac", load_aircraft(), ids=lambda a: a.id)
def test_sea_level_isa_reference_runway_no_restriction(ac) -> None:
    res = evaluate(ac, 0, ac.tofl_ref_m, 15.0)
    assert res.restriction_kg == pytest.approx(0, abs=1)
    assert res.status == OK


def test_monotonic_in_temperature() -> None:
    temps = np.linspace(-10, 55, 200)
    r = restriction_kg(AC, 1135, 3000, temps)
    assert np.all(np.diff(r) >= -1e-9)
    assert r[-1] > r[0]


def test_monotonic_in_elevation() -> None:
    elevs = np.linspace(0, 14000, 100)
    r = restriction_kg(AC, elevs, 3000, 30.0)
    assert np.all(np.diff(r) >= -1e-9)
    assert r[-1] > r[0]


def test_decreasing_in_runway_length() -> None:
    runways = np.linspace(1500, 4500, 100)
    r = restriction_kg(AC, 5000, runways, 35.0)
    assert np.all(np.diff(r) <= 1e-9)
    assert r[0] > r[-1]


def test_hot_high_short_restricted_cool_low_long_not() -> None:
    hot = evaluate(AC, 8000, 2500, 38)
    cool = evaluate(AC, 0, 4000, 10)
    assert hot.status in (RESTRICTED, SEVERE) and hot.restriction_kg > 1000
    assert cool.status == OK and cool.restriction_kg == 0


@pytest.mark.parametrize("ac", load_aircraft(), ids=lambda a: a.id)
@pytest.mark.parametrize("elev,runway", [(1135, 3502), (5431, 4877), (13355, 4000), (0, 2500)])
def test_threshold_round_trips(ac, elev, runway) -> None:
    th = threshold_temp(ac, elev, runway)
    if th.kind != "normal":
        return
    assert evaluate(ac, elev, runway, th.temp_c - 0.1).restriction_kg == pytest.approx(0, abs=1)
    assert evaluate(ac, elev, runway, th.temp_c + 0.1).restriction_kg > 0


def test_threshold_edge_cases() -> None:
    assert threshold_temp(AC, 0, 500).kind == "always"
    assert threshold_temp(get_aircraft("ATR72-600"), 0, 4000).kind == "never"


def test_severe_when_restriction_exceeds_payload() -> None:
    res = evaluate(AC, 13355, 2000, 25)
    assert res.status == SEVERE


def test_passengers_and_sweep() -> None:
    res = evaluate(AC, 8000, 2500, 38, kg_per_passenger=100)
    assert res.passengers == pytest.approx(res.restriction_kg / 100)
    w = sweep(AC, 1135, 3502, np.arange(20, 51))
    assert w.max() == pytest.approx(AC.mtow_kg) and np.all(np.diff(w) <= 1e-9)
    assert res.to_dict()["estimate"] is True
