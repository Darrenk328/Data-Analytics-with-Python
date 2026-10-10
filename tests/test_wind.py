import pytest

from skyscope.perf.wind import RunwayEnd, best_end, components


def test_rwy22_wind_220_at_10() -> None:
    wc = components(220, 220, 10)
    assert wc.headwind == pytest.approx(10) and wc.crosswind == pytest.approx(0, abs=1e-9)


def test_rwy22_wind_040_is_tailwind() -> None:
    wc = components(220, 40, 10)
    assert wc.headwind == pytest.approx(-10) and wc.tailwind == pytest.approx(10)


def test_crosswind_sign() -> None:
    assert components(360, 90, 10).crosswind == pytest.approx(10)
    assert components(360, 270, 10).crosswind == pytest.approx(-10)


def test_best_end() -> None:
    ends = [RunwayEnd("08", 80, 11000), RunwayEnd("26", 260, 11000), RunwayEnd("07L", 70, 9000)]
    assert best_end(ends, 250, 12).ident == "26"
    assert best_end(ends, None, None).length_ft == 11000
