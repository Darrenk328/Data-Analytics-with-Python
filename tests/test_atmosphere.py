import numpy as np
import pytest

from skyscope.perf.atmosphere import (
    density_altitude_ft,
    density_ratio,
    hpa_to_inhg,
    isa_temp_c,
    pressure_altitude_ft,
    pressure_ratio,
)


def test_sigma_at_sea_level_and_10000ft() -> None:
    assert float(density_ratio(0)) == pytest.approx(1.0)
    assert float(density_ratio(10_000)) == pytest.approx(0.738, abs=0.002)


def test_pressure_altitude_and_isa() -> None:
    assert pressure_altitude_ft(1000, 29.92) == pytest.approx(1000)
    assert pressure_altitude_ft(1000, 29.42) == pytest.approx(1500)
    assert isa_temp_c(0) == pytest.approx(15)
    assert isa_temp_c(5000) == pytest.approx(5.094, abs=0.01)


def test_density_altitude_isa_equals_pa() -> None:
    assert density_altitude_ft(5000, isa_temp_c(5000)) == pytest.approx(5000)
    # hot day: PHX 1,135 ft at 45 °C → DA near 5,000 ft
    assert density_altitude_ft(1135, 45) == pytest.approx(4966, abs=10)


def test_pressure_ratio_and_vectorised() -> None:
    assert float(pressure_ratio(0)) == pytest.approx(1.0)
    arr = density_ratio(np.array([0, 5000, 10000]))
    assert arr.shape == (3,) and np.all(np.diff(arr) < 0)


def test_hpa_conversion() -> None:
    assert hpa_to_inhg(1013.25) == pytest.approx(29.92, abs=0.01)
