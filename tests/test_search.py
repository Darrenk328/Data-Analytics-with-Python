from skyscope.data.search import search, suggest


def codes(store, hits, n):
    return [store.airports["code"].iat[h.idx] for h in hits[:n]]


def test_phoenix_first(store) -> None:
    assert codes(store, search(store, "phoenix"), 1) == ["PHX"]


def test_new_york_big_three_near_top(store) -> None:
    top = codes(store, search(store, "new york"), 5)
    assert {"JFK", "LGA", "EWR"} <= set(top)


def test_exact_codes_win(store) -> None:
    assert codes(store, search(store, "PHX"), 1) == ["PHX"]
    assert codes(store, search(store, "kden"), 1) == ["DEN"]
    assert codes(store, search(store, "EGLL"), 1) == ["LHR"]


def test_typos_still_find(store) -> None:
    assert "PHX" in codes(store, search(store, "phonix"), 3)
    assert "DEN" in codes(store, search(store, "denvr"), 3)


def test_suggestions_for_bad_codes(store) -> None:
    sug = [store.airports["code"].iat[i] for i in suggest(store, "PHZ")]
    assert "PHX" in sug
    assert suggest(store, "") == []


def test_closed_hidden_by_default(store) -> None:
    hits = search(store, "airport", limit=200)
    assert all(store.airports["type"].iat[h.idx] != "closed" for h in hits)
