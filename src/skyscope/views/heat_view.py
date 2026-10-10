"""Heat history view: warming stripes, warm-season decades, hot days, projection, caveats."""

from __future__ import annotations

import calendar

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from skyscope.climate.metrics import HeatSummary
from skyscope.views import format as fmt
from skyscope.views.takeoff_view import bar
from skyscope.views.theme import Responsive, anomaly_rgb, page, panel

CAVEAT = ("History: ERA5 reanalysis (Copernicus/ECMWF) via Open-Meteo - a ~9–25 km grid adjusted to "
          "field elevation, not the runway thermometer. Projections: CMIP6 HighResMIP, close to a "
          "high-emissions (RCP8.5-like) scenario, ending 2050; applied to the observed record with "
          "the delta method. All values are estimates.")


def stripes(s: HeatSummary, width: int) -> Group:
    """One coloured block per year (projected years dimmer), compressed to fit the width."""
    years = sorted(s.anomalies)
    proj = sorted(y for y in s.projected_warm if y > (years[-1] if years else 0))
    total = len(years) + len(proj)
    step = max(1, -(-total // max(20, width - 4)))
    line = Text("  ")
    seq = [(y, s.anomalies[y], False) for y in years] + [(y, s.projected_warm[y] - s.baseline, True) for y in proj]
    for i in range(0, len(seq), step):
        chunk = seq[i:i + step]
        anom = sum(c[1] for c in chunk) / len(chunk)
        projected = chunk[0][2]
        line.append("▒" if projected else "█", style=f"{anomaly_rgb(anom)}" + (" dim" if projected else ""))
    first = years[0] if years else ""
    last_obs = years[-1] if years else ""
    label = Text(f"  {first}–{last_obs} observed", style="muted")
    if proj:
        label.append(f" · ▒ {proj[0]}–{proj[-1]} projected", style="muted")
    label.append(" · colour vs 1951–1980", style="muted")
    return Group(line, label)


def _decade_table(title: str, rows: list[tuple[str, float]], fmt_value) -> Group:
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False, show_header=False)
    table.add_column(no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    table.add_column(no_wrap=True)
    top = max([abs(v) for _, v in rows] + [1e-9])
    for label, value in rows:
        table.add_row(label, fmt_value(value), Text(bar(abs(value), top, 28) or "·", style="red" if value > 0 else "cyan"))
    return Group(Text(title, style="bold"), table)


def heat_view(code: str, name: str, s: HeatSummary, units: str, proj_note: str | None,
              plot_note: Text | None = None) -> RenderableType:
    """The full heat page."""
    months = "–".join(calendar.month_abbr[m] for m in (s.months[0], s.months[2]))
    head = Text()
    if s.warming is not None:
        head.append(f"{code}'s warm-season highs ({months}) are ", style="bold")
        head.append(f"{fmt.dtemp(s.warming, units)}", style="bold red" if s.warming > 0 else "bold cyan")
        head.append(" warmer in 1996–2025 than in 1951–1980", style="bold")
    else:
        head.append(f"{code} warm-season highs ({months})", style="bold")
    if s.projected_warming:
        vals = sorted(s.projected_warming.values())
        med = vals[len(vals) // 2]
        head.append(f"; models add another ≈{fmt.dtemp(med, units)} by 2031–2050 "
                    f"(range {fmt.dtemp(vals[0], units)} to {fmt.dtemp(vals[-1], units)}).")
    else:
        head.append(".")
    tr = s.trend
    trend_line = Text(f"Trend {fmt.dtemp(tr.slope_per_decade, units, 2)}/decade over {tr.n} years "
                      f"(t = {tr.t_stat:.1f}: {tr.label}).", style="muted")
    warm_rows = []
    for start in range(1940, 2030, 10):
        vals = [v for y, v in s.warm.items() if start <= y < start + 10]
        if vals:
            warm_rows.append((f"{start}s{'*' if len(vals) < 10 else ''}", sum(vals) / len(vals) - s.baseline))
    if s.projected_warm:
        vals = [v for y, v in s.projected_warm.items() if 2041 <= y <= 2050]
        if vals:
            warm_rows.append(("2040s (proj.)", sum(vals) / len(vals) - s.baseline))
    warm_table = _decade_table(f"Warm-season high vs 1951–1980 (baseline {fmt.temp(s.baseline, units, 1)})",
                               warm_rows, lambda v: fmt.dtemp(v, units))
    hot_table = _decade_table(f"Unusually hot days/yr (≥ {fmt.temp(s.p95, units, 1)}, this airport's "
                              "1951–80 95th pct.)", s.hot_p95_decades, lambda v: f"{v:.0f}")
    story = panel(Group(head, Text(""), Responsive(lambda w: stripes(s, w)), Text(""), trend_line),
                  f"Heat history · {code} · {name}", "ERA5 1940→now · CMIP6 to 2050")
    decades: list[RenderableType] = [warm_table, Text(""), hot_table]
    if any(v > 0 for _, v in s.hot_35_decades):
        decades += [Text(""), _decade_table(f"Days per year ≥ {fmt.temp(35, units)}", s.hot_35_decades,
                                            lambda v: f"{v:.0f}")]
    decades += [Text(""), Text(f"Record hottest day: {fmt.temp(s.record_c, units, 1)} on {s.record_date} (ERA5 grid).")]
    if proj_note:
        decades.append(Text(proj_note, style="warn"))
    if plot_note is not None:
        decades.append(plot_note)
    decades += [Text(""), Text(CAVEAT, style="est")]
    return page(story, panel(Group(*decades), "By decade", "≈ estimates"),
                hints=[f"takeoff {code} --decades", f"heat {code} --plot", f"open {code}"])


def climate_line(s: HeatSummary, units: str) -> RenderableType:
    """One-row stripes + headline for the airport card."""
    text = Text("  ")
    if s.warming is not None:
        text.append(f"{fmt.dtemp(s.warming, units)} warm-season highs since the 1950s–70s", style="bold")
    text.append(f" · record {fmt.temp(s.record_c, units)} ({s.record_date[:4]})", style="muted")
    return Group(Responsive(lambda w: stripes(s, min(w, 90)).renderables[0]), text)
