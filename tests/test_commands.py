"""Commands through the REPL boundary: rendered with Console(record=True), never a traceback."""

from __future__ import annotations

import pytest

from skyscope.shell.context import Context
from skyscope.shell.repl import run_line
from skyscope.views.theme import make_console


def make_ctx(store, width=100):
    ctx = Context(console=make_console(width=width, record=True), interactive=True)
    ctx._store = store
    return ctx


def output(ctx) -> str:
    return ctx.console.export_text()


def test_find_then_filter_then_back(store) -> None:
    ctx = make_ctx(store)
    run_line(ctx, "find phoenix")
    assert "PHX" in output(ctx)
    run_line(ctx, "filter type=large")
    out = output(ctx)
    assert "find phoenix" in out and "type = large_airport" in out
    run_line(ctx, "back")
    assert ctx.results.title.startswith("Search")


def test_bare_text_searches(store) -> None:
    ctx = make_ctx(store)
    run_line(ctx, "denver")
    assert "DEN" in output(ctx)


def test_unknown_command_suggests(store) -> None:
    ctx = make_ctx(store)
    run_line(ctx, "fitler country=US")
    assert "did you mean 'filter'" in output(ctx)


JUNK = ["", "   ", "\x00", "'", '"', "find", "filter", "filter =", "filter ===", "open",
        "open 999", "open ZZZZZ", "back", "back", "help nosuch", "find " + "x" * 500,
        "filter elevation>1e999", "filter runway<-5", "--json", "find --nope phoenix",
        "filter country=US;rm -rf /", "🙂", "help help", "results", "find 12345",
        "takeoff", "takeoff ZZZZ", "takeoff PHX --temp hot", "heat", "vs", "vs PHX",
        "rank", "rank nonsense", "near", "near 999,999", "map --nope", "aircraft nope",
        "explain nope", "export", "export xls", "units furlongs", "fav ZZZZ", "wx ZZZZ",
        "runways ZZZZ", "hotspots --aircraft nope"]


@pytest.mark.parametrize("line", JUNK)
def test_junk_input_never_crashes(store, line) -> None:
    ctx = make_ctx(store, width=80)
    run_line(ctx, line)
    out = output(ctx)
    assert "Traceback" not in out
    assert "something went wrong" not in out, out
