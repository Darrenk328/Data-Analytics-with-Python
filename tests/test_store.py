import math
import time

import pytest

from skyscope.data.geo import bearing_deg, compass, haversine_nm
from skyscope.data.normalize import heading_from_ident, normalize_surface


def test_haversine_jfk_lhr(mini_store) -> None:
    a, b = mini_store.lookup("JFK"), mini_store.lookup("LHR")
    assert haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"]) == pytest.approx(2999, rel=0.01)


def test_bearing_and_compass() -> None:
    assert bearing_deg(0, 0, 1, 0) == pytest.approx(0)
    assert bearing_deg(0, 0, 0, 1) == pytest.approx(90)
    assert compass(10) == "N" and compass(45) == "NE" and compass(200) == "SSW"


@pytest.mark.parametrize("raw,cat", [
    ("ASP", "paved"), ("ASPH-G", "paved"), ("CONC", "paved"), ("PEM", "paved"),
    ("ASPH-TURF", "paved"), ("TURF", "grass"), ("Grassed brown clay", "grass"),
    ("GRVL", "gravel-dirt"), ("DIRT", "gravel-dirt"), ("PIÇARRA", "gravel-dirt"),
    ("WATER", "water"), ("", "unknown"), (None, "unknown"), ("???", "unknown"),
])
def test_surface_normalization(raw, cat) -> None:
    assert normalize_surface(raw) == cat


@pytest.mark.parametrize("ident,heading", [("09", 90.0), ("27L", 270.0), ("36", 360.0),
                                           ("4", 40.0), ("H1", None), ("N", None), ("", None)])
def test_heading_from_ident(ident, heading) -> None:
    assert heading_from_ident(ident) == heading


def test_lookup_codes(mini_store) -> None:
    for code in ("PHX", "KPHX", "phx"):
        assert mini_store.lookup(code)["ident"] == "KPHX"
    assert mini_store.lookup("ZZZZZ") is None
    assert mini_store.lookup("FYWH")["iso_country"] == "NA"  # Namibia must not become NaN


def test_runway_join(mini_store) -> None:
    phx = mini_store.lookup("PHX")
    assert phx["longest_paved_ft"] == 11489
    assert phx["runway_count"] == 3
    assert phx["perf_ok"] is True
    heli = mini_store.lookup("00A")
    assert heli["perf_ok"] is False


def test_no_nan_in_display_fields(mini_store) -> None:
    for idx in mini_store.airports.index:
        rec = mini_store.record(idx)
        for key, value in rec.items():
            assert not (isinstance(value, float) and math.isnan(value)), (rec["ident"], key)
            assert value != "nan"


def test_missing_headings_derived(mini_store) -> None:
    rw = mini_store.runways
    named = rw[rw["le_ident"].str.fullmatch(r"\d{2}[LRC]?")]
    assert named["le_heading"].notna().all()


def test_warm_load_fast(store) -> None:
    import skyscope.data.store as st

    st._STORE = None
    t0 = time.perf_counter()
    st.get_store()
    assert time.perf_counter() - t0 < 1.0
