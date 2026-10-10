"""Matplotlib PNG export for `heat --plot` and `takeoff --decades --plot`.

Every chart has a title, labelled axes with units, a legend and a source footnote. This
module writes files, so it lives outside views/ (views never do I/O). Matplotlib is imported
lazily; :class:`PlotUnavailable` is raised with a friendly message if it's missing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

PLOTS_DIR = "plots"
ERA5_CREDIT = "ERA5 reanalysis (Copernicus/ECMWF) via Open-Meteo.com (CC BY 4.0)"
CMIP6_CREDIT = "CMIP6 HighResMIP, high-emissions scenario, to 2050 (delta method)"


class PlotUnavailable(RuntimeError):
    """Matplotlib can't be used; the message says how to fix it."""


def _pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")  # no display needed
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise PlotUnavailable("matplotlib isn't installed — run: pip install matplotlib") from exc
    return plt


def _out_path(name: str, out_dir: Path | None) -> Path:
    folder = out_dir or Path.cwd() / PLOTS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{name}.png"


def _footnote(fig, text: str) -> None:
    fig.text(0.01, 0.01, text, fontsize=7.5, color="#555555", ha="left", va="bottom", wrap=True)


def plot_heat(code: str, name: str, warm: dict[int, float], baseline: float, slope_per_decade: float,
              projected: dict[int, float], months: str, units: str = "metric",
              out_dir: Path | None = None) -> Path:
    """Warm-season Tmax by year + linear trend + 1951–1980 baseline (+ projected median)."""
    plt = _pyplot()

    def conv(c):
        return np.asarray(c) * 9 / 5 + 32 if units == "imperial" else np.asarray(c)

    unit = "°F" if units == "imperial" else "°C"
    years = np.array(sorted(warm))
    vals = np.array([warm[y] for y in years])
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(years, conv(vals), color="#c0392b", marker="o", markersize=3, linewidth=1.2,
            label=f"Warm-season ({months}) mean daily max, ERA5")
    coef = np.polyfit(years, vals, 1)
    slope = slope_per_decade * (9 / 5 if units == "imperial" else 1)
    ax.plot(years, conv(np.polyval(coef, years)), color="#2c3e50", linewidth=2,
            label=f"Linear trend ({slope:+.2f} {unit}/decade)")
    ax.axhline(float(conv(baseline)), color="#2980b9", linestyle="--", linewidth=1.5,
               label=f"1951–1980 baseline ({float(conv(baseline)):.1f} {unit})")
    if projected:
        py = np.array(sorted(projected))
        ax.plot(py, conv([projected[y] for y in py]), color="#e67e22", linestyle=":", linewidth=2,
                label="Projected median of CMIP6 models (high emissions)")
    ax.set_title(f"{code} · {name}\nWarm-season daily maximum temperature, {years[0]}–"
                 f"{(max(projected) if projected else years[-1])}")
    ax.set_xlabel("Year")
    ax.set_ylabel(f"Mean daily max temperature ({unit})")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    _footnote(fig, f"Source: {ERA5_CREDIT}" + (f"; projections: {CMIP6_CREDIT}" if projected else "")
              + ". ERA5 is a ~9–25 km grid adjusted to field elevation, not the runway sensor. Estimates.")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = _out_path(f"heat_{code}", out_dir)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_decades(code: str, aircraft_name: str, aircraft_id: str, periods: list[tuple[str, float]],
                 projected: tuple[float, float, float] | None, out_dir: Path | None = None) -> Path:
    """Bars of restricted days/yr per period; projection bar with a min–max error bar.

    ``projected`` is (median, min, max) for 2031–2050, or None.
    """
    plt = _pyplot()
    labels = [p[0] for p in periods]
    values = [p[1] for p in periods]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    x = np.arange(len(labels))
    recent = [i for i, lab in enumerate(labels) if "–" in lab]
    decade = [i for i in range(len(labels)) if i not in recent]
    ax.bar(x[decade], [values[i] for i in decade], color="#f39c12",
           label="Observed decade mean (ERA5 daily max temperature)")
    if recent:
        ax.bar(x[recent], [values[i] for i in recent], color="#d35400", hatch="//", edgecolor="white",
               label="Observed 30-year mean, 1996–2025")
    if projected is not None:
        med, lo, hi = projected
        px = len(labels)
        ax.bar([px], [med], color="#c0392b", label="Projected 2031–2050, CMIP6 multi-model median")
        ax.errorbar([px], [med], yerr=[[med - lo], [hi - med]], fmt="none", ecolor="black",
                    capsize=8, linewidth=1.5, label="Model range (min–max)")
        labels = labels + ["2031–2050\n(projected)"]
        x = np.arange(len(labels))
    top = max(values + ([projected[2]] if projected is not None else []) + [1.0])
    ax.set_ylim(0, top * 1.45)  # headroom so the legend never covers a bar
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_title(f"{code} · days per year a fully loaded {aircraft_name} would be weight-restricted")
    ax.set_xlabel("Period")
    ax.set_ylabel("Restricted days per year (days/yr)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    _footnote(fig, f"Source: {ERA5_CREDIT}" + (f"; {CMIP6_CREDIT}" if projected else "")
              + ". SkyScope takeoff model (estimate, not a flight manual); each day's max temperature, "
              "standard pressure, longest paved runway. * = partial decade.")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    path = _out_path(f"decades_{code}_{aircraft_id}", out_dir)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
