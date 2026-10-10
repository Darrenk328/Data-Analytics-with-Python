"""Takeoff verdict, all-aircraft table, temperature sweep and decades bars."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skyscope.perf.aircraft import Aircraft
from skyscope.perf.takeoff import OK, TakeoffResult, Threshold
from skyscope.views import format as fmt
from skyscope.views.theme import (
    BORDER_STYLE,
    OK_COLOR,
    RESTRICTED_COLOR,
    SEVERE_COLOR,
    STATUS_STYLE,
    badge,
    page,
    panel,
)


def threshold_text(th: Threshold, units: str) -> str:
    """"47 °C", "any temperature", "above 60 °C"."""
    if th.kind == "always":
        return "any temperature"
    if th.kind == "never":
        return f"none up to {fmt.temp(60, units)}"
    return fmt.temp(th.temp_c, units)


def headline(code: str, ac: Aircraft, res: TakeoffResult, units: str, today: bool) -> Text:
    """One human sentence summarising the verdict."""
    when = "On a day like today" if today else f"At {fmt.temp(res.oat_c, units)}"
    text = Text(f"{when}, a fully loaded {ac.name} at {code} ", style="bold")
    if res.status == OK:
        text.append("could take off with no restriction", style=STATUS_STYLE["OK"])
    elif res.status == "SEVERE":
        text.append("could not carry a useful payload", style=STATUS_STYLE["SEVERE"])
    else:
        text.append(f"would leave ≈{res.passengers:,.0f} passengers behind", style=STATUS_STYLE[res.status])
    text.append(".")
    return text


def verdict_panel(code: str, ac: Aircraft, res: TakeoffResult, runway_name: str, units: str,
                  oat_note: str, today: bool, head: Text | None = None) -> Panel:
    """Status badge, restriction, runway, DA and threshold margin, bordered in the status colour."""
    body = Text()
    if head is not None:
        body.append_text(head)
        body.append("\n\n")
    body.append_text(badge(res.status))
    if res.status == OK:
        body.append("  No restriction")
    else:
        body.append(f"  ≈{fmt.mass(res.restriction_kg, units)} offloaded · "
                    f"{fmt.pct(res.restriction_pct, 1)} of MTOW · ≈{res.passengers:,.0f} passengers",
                    style=STATUS_STYLE[res.status])
    body.append("\n\nOAT ")
    body.append(fmt.temp(res.oat_c, units), style="bold")
    body.append(f" {oat_note}", style="muted")
    body.append(f"\nRunway {runway_name} · {fmt.length_both(res.runway_m * fmt.FT_PER_M, units)}")
    body.append(f" · needs ≈{fmt.length(res.todr_mtow_m * fmt.FT_PER_M, units)} at MTOW", style="est")
    body.append(f"\nDensity altitude ≈{fmt.feet(res.density_alt_ft)}", style="est")
    body.append(f" · air {res.sigma * 100:.0f}% of sea-level density · thrust ≈{res.tau * 100:.0f}%",
                style="est")
    body.append("\nRestriction begins at ")
    body.append("≈" + threshold_text(res.threshold, units), style="bold")
    if res.margin_c is not None:
        now = "today is" if today else "this is"
        if res.margin_c >= 0:
            body.append(f"; {now} {fmt.temp(res.oat_c, units)}, "
                        f"{fmt.dtemp(res.margin_c, units, 0).lstrip('+')} of margin")
        else:
            body.append(f"; {now} {fmt.dtemp(-res.margin_c, units, 0).lstrip('+')} past it")
    title = f"✈ Takeoff · {code} · {ac.name}{' ≈' if ac.approx else ''}"
    return panel(body, title, "≈ estimate — not a flight manual", border=BORDER_STYLE.get(res.status, "border"))


def all_aircraft_table(rows: list[tuple[Aircraft, TakeoffResult]], units: str) -> Panel:
    """One row per type: status badge, restriction and threshold."""
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    table.add_column("Aircraft", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Offload", justify="right", no_wrap=True)
    table.add_column("Pax", justify="right", no_wrap=True)
    table.add_column("Starts at", justify="right", no_wrap=True)
    for ac, res in rows:
        table.add_row(
            f"{ac.name}{' ≈' if ac.approx else ''}", badge(res.status),
            fmt.DASH if res.status == OK else Text("≈" + fmt.mass(res.restriction_kg, units), style=STATUS_STYLE[res.status]),
            fmt.DASH if res.status == OK else f"≈{res.passengers:,.0f}",
            "≈" + threshold_text(res.threshold, units) if res.threshold.kind == "normal" else threshold_text(res.threshold, units),
        )
    oat = rows[0][1].oat_c if rows else None
    return panel(table, f"All aircraft at {fmt.temp(oat, units)}", "≈ estimates")


def bar(value: float, maximum: float, width: int = 30) -> str:
    """Horizontal bar with eighth-block resolution."""
    if maximum <= 0 or value <= 0:
        return ""
    cells = value / maximum * width
    full = int(cells)
    rem = int((cells - full) * 8)
    return "█" * full + ("▏▎▍▌▋▊▉"[rem - 1] if rem else "")


def sweep_view(ac: Aircraft, rows: list[tuple[float, float, float]], today_c: float | None,
               record_c: float | None, units: str) -> Panel:
    """Passengers lost vs temperature as a bar table (rows: temp, allowable kg, passengers lost)."""
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    table.add_column("OAT", justify="right", no_wrap=True)
    table.add_column("Pax lost", justify="right", no_wrap=True)
    table.add_column("", no_wrap=True)
    table.add_column("", no_wrap=True, style="muted")
    worst = max((r[2] for r in rows), default=0) or 1
    for t, _allow, pax in rows:
        marks = []
        if today_c is not None and abs(t - today_c) < 1:
            marks.append("◀ today")
        if record_c is not None and abs(t - record_c) < 1:
            marks.append("◀ record high")
        style = OK_COLOR if pax <= 0 else SEVERE_COLOR if pax > worst * 0.66 else RESTRICTED_COLOR
        table.add_row(fmt.temp(t, units), "—" if pax <= 0 else f"≈{pax:,.0f}",
                      Text(bar(pax, worst, 28) or "·", style=style), " ".join(marks))
    return panel(table, f"Passengers lost vs temperature · {ac.name}", "≈ estimate")


def decades_view(rows: list[tuple[str, float, float | None, float | None]], headline_text: str,
                 caveat: str) -> Panel:
    """Restricted days/yr per period. rows: (label, value, spread_lo, spread_hi)."""
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    table.add_column("Period", no_wrap=True)
    table.add_column("Days/yr", justify="right", no_wrap=True)
    table.add_column("", no_wrap=True)
    top = max([r[1] for r in rows] + [r[3] or 0 for r in rows] + [1])
    for label, value, lo, hi in rows:
        projected = lo is not None
        b = Text(bar(value, top, 32) or "·", style=SEVERE_COLOR if projected else RESTRICTED_COLOR)
        if projected and hi is not None:
            b.append(f"  range {lo:.0f}–{hi:.0f}", style="muted")
        table.add_row(Text(label, style="bold" if projected else ""), f"≈{value:,.0f}", b)
    body = Group(Text(headline_text, style="bold"), Text(""), table, Text(""), Text(caveat, style="est"))
    return panel(body, "Restricted days per year", "≈ estimate · daily max temperature")


def takeoff_page(head: Text, verdict: Panel, table: Panel, extra: RenderableType | None,
                 hints: list[str]) -> RenderableType:
    """Verdict, optional sweep/decades, all-aircraft panel, hint line."""
    return page(verdict, extra, table, hints=hints)
