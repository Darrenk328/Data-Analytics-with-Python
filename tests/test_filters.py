import pytest

from skyscope.data import filters as flt


def run(store, expr, pool=None):
    return flt.apply(flt.parse(expr, store), store, pool)


def test_bolivia_high(store) -> None:
    idx = run(store, "country=Bolivia elevation>10000")
    ap = store.airports.loc[idx]
    assert len(idx) > 5
    assert (ap["iso_country"] == "BO").all() and (ap["elevation_ft"] > 10000).all()
    assert ap["code"].iloc[0] == "LPB"  # large airports first


def test_units_and_aliases(store) -> None:
    ap = store.airports.loc[run(store, "type=big runway>=4km elevation>2000m")]
    assert (ap["type"] == "large_airport").all()
    assert (ap["longest_ft"] >= 13123).all() and (ap["elevation_ft"] > 6561).all()
    assert "DEN" not in set(ap["code"])  # Denver is 5,431 ft
    assert "LPB" in set(ap["code"])


def test_multi_value_and_contains(store) -> None:
    ap = store.airports.loc[run(store, "country=US,CA type=large name~intl")]
    assert set(ap["iso_country"]) <= {"US", "CA"}
    assert ap["name"].str.lower().str.contains("intl").all()


def test_namibia_and_multiword_country(store) -> None:
    assert len(run(store, "country=Namibia type=large")) >= 1
    assert len(run(store, "country=united states type=large")) > 50


def test_refines_pool(store) -> None:
    pool = run(store, "country=US")
    sub = run(store, "elevation>8000", pool)
    assert set(sub) <= set(pool)


def test_surface_and_service(store) -> None:
    ap = store.airports.loc[run(store, "service=yes surface=grass country=GB")]
    assert ap["scheduled"].all()


@pytest.mark.parametrize("expr,hint", [
    ("elevaton>5000", "elevation"),
    ("country=Bolivai", "Bolivia"),
    ("type=hugeport", "heliport"),
])
def test_did_you_mean(store, expr, hint) -> None:
    with pytest.raises(flt.FilterError) as err:
        flt.parse(expr, store)
    assert hint in err.value.hint


@pytest.mark.parametrize("expr", ["foo", "elevation>abc", "runway~x", 'name="oops', "country=",
                                  "service=maybe", "continent=Atlantis", "=5", ">>>"])
def test_bad_expressions_raise_cleanly(store, expr) -> None:
    with pytest.raises(flt.FilterError):
        flt.parse(expr, store)
