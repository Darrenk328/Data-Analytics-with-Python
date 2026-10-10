"""Matplotlib export: files are written, and a missing matplotlib gives a friendly message."""

from __future__ import annotations

import sys

import pytest

from skyscope.plots import PlotUnavailable, plot_decades, plot_heat


def test_heat_plot_written(tmp_path) -> None:
    warm = {y: 39 + 0.015 * (y - 1940) for y in range(1940, 2026)}
    path = plot_heat("PHX", "Phoenix", warm, 39.5, 0.15, {2030: 41.0, 2031: 41.2}, "Jun–Aug", out_dir=tmp_path)
    assert path.exists() and path.stat().st_size > 10_000


def test_decades_plot_written(tmp_path) -> None:
    periods = [("1960s", 3.0), ("2010s", 8.0), ("1996–2025", 6.0)]
    path = plot_decades("PHX", "Boeing 787-9", "787-9", periods, (12.0, 9.0, 15.0), out_dir=tmp_path)
    assert path.exists() and path.name == "decades_PHX_787-9.png"
    assert plot_decades("DOH", "B", "b", periods, None, out_dir=tmp_path).exists()


def test_missing_matplotlib_is_friendly(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib", None)  # makes `import matplotlib` fail
    with pytest.raises(PlotUnavailable, match="pip install matplotlib"):
        plot_decades("PHX", "B", "b", [("1960s", 1.0)], None, out_dir=tmp_path)


def test_plot_flag_through_commands(store, tmp_path, monkeypatch) -> None:
    from skyscope.config import RUNTIME
    from skyscope.shell.context import Context
    from skyscope.shell.repl import run_line
    from skyscope.views.theme import make_console

    RUNTIME.offline = True
    monkeypatch.chdir(tmp_path)
    ctx = Context(console=make_console(width=100, record=True), interactive=True)
    ctx._store = store
    res = run_line(ctx, "takeoff PHX --decades --plot")
    assert res.data["plot"] and (tmp_path / "plots" / "decades_PHX_737-800.png").exists()
    res = run_line(ctx, "heat PHX --plot")
    assert (tmp_path / "plots" / "heat_PHX.png").exists()
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.delitem(sys.modules, "matplotlib.pyplot", raising=False)
    res = run_line(ctx, "heat PHX --plot")
    out = ctx.console.export_text()
    assert res is not None and "Plot not saved" in out and "pip install matplotlib" in out
