"""Takeoff verdict, all-aircraft table, temperature sweep and decades bars."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skyscope.perf.aircraft import Aircraft
from skyscope.perf.takeoff import OK, TakeoffResult, Threshold
from skyscope.views import format as fmt
from skyscope.views.theme import STATUS_ICON, STATUS_STYLE, hint_line


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
    text = Text(f"{when}, a fully loaded {ac.name} at {code} ")
    if res.status == OK:
        text.append("could take off with no restriction", style="bold green")
    elif res.status == "SEVERE":
        text.append("could not carry a useful payload", style="bold red")
    else:
        text.append(f"would leave ≈{res.passengers:,.0f} passengers behind", style="bold yellow")
    text.append(" (estimate).")
    return text


def verdict_panel(code: str, ac: Aircraft, res: TakeoffResult, runway_name: str, units: str,
                  oat_note: str, today: bool) -> Panel:
    """Coloured status panel with restriction, runway, DA and threshold margin."""
    style = STATUS_STYLE.get(res.status, "")
    body = Text()
    body.append(f"{STATUS_ICON.get(res.status, '')} {res.status}", style=style)
    if res.status == OK:
        body.append("   No restriction")
    else:
        body.append(f"   {ac.mark or '≈'}{fmt.mass(res.restriction_kg, units)} offloaded "
                    f"({fmt.pct(res.restriction_pct, 1)} of MTOW, ≈{res.passengers:,.0f} passengers)")
    body.append("\n")
    body.append(f"OAT {fmt.temp(res.oat_c, units)}", style="bold")
    body.append(f" {oat_note}", style="muted")
    body.append(f"\nRunway {runway_name} · {fmt.length_both(res.runway_m * fmt.FT_PER_M, units)}"
                f" · needs ≈{fmt.length_both(res.todr_mtow_m * fmt.FT_PER_M, units)} at MTOW today")
    body.append(f"\nDensity altitude ≈{fmt.feet(res.density_alt_ft)} · air density "
                f"{res.sigma * 100:.0f}% of sea-level standard · thrust ≈{res.tau * 100:.0f}%")
    body.append("\nRestriction begins at ")
    body.append(threshold_text(res.threshold, units), style="bold")
    if res.margin_c is not None:
        now = "today is" if today else "this is"
        if res.margin_c >= 0:
            body.append(f"; {now} {fmt.temp(res.oat_c, units)}, "
                        f"{fmt.dtemp(res.margin_c, units, 0).lstrip('+')} of margin")
        else:
            body.append(f"; {now} {fmt.dtemp(-res.margin_c, units, 0).lstrip('+')} past it")
    title = f"Takeoff · {code} · {ac.name}{' ≈' if ac.approx else ''}"
    return Panel(body, title=title, title_align="left", border_style=style or "cyan",
                 subtitle="estimate — not a flight manual", subtitle_align="right")


def all_aircraft_table(rows: list[tuple[Aircraft, TakeoffResult]], units: str) -> Table:
    """One row per type: status, restriction and threshold."""
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False,
                  title="All aircraft at this temperature (estimates)", title_justify="left",
                  title_style="muted")
    table.add_column("Aircraft", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Offload", justify="right", no_wrap=True)
    table.add_column("Pax", justify="right", no_wrap=True)
    table.add_column("Starts at", justify="right", no_wrap=True)
    for ac, res in rows:
        table.add_row(
            f"{ac.name}{' ≈' if ac.approx else ''}",
            Text(f"{STATUS_ICON[res.status]} {res.status}", style=STATUS_STYLE[res.status]),
            fmt.DASH if res.status == OK else fmt.mass(res.restriction_kg, units),
            fmt.DASH if res.status == OK else f"≈{res.passengers:,.0f}",
            threshold_text(res.threshold, units),
        )
    return table


def bar(value: float, maximum: float, width: int = 30) -> str:
    """Horizontal bar with eighth-block resolution."""
    if maximum <= 0 or value <= 0:
        return ""
    cells = value / maximum * width
    full = int(cells)
    rem = int((cells - full) * 8)
    return "█" * full + ("▏▎▍▌▋▊▉"[rem - 1] if rem else "")


def sweep_view(ac: Aircraft, rows: list[tuple[float, float, float]], today_c: float | None,
               record_c: float | None, units: str) -> RenderableType:
    """Allowable weight vs temperature as a bar table (rows: temp, allowable kg, passengers lost)."""
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False,
                  title=f"Payload lost vs temperature · {ac.name} (estimate)", title_justify="left",
                  title_style="muted")
    table.add_column("OAT", justify="right", no_wrap=True)
    table.add_column("Pax lost", justify="right", no_wrap=True)
    table.add_column("", no_wrap=True)
    table.add_column("", no_wrap=True, style="muted")
    worst = max((r[2] for r in rows), default=0) or 1
    for t, _allow, pax in rows:
        marks = []
        if today_c is not None and abs(t - today_c) < 1.25:
            marks.append("◀ today")
        if record_c is not None and abs(t - record_c) < 1.25:
            marks.append("◀ record high")
        style = "green" if pax <= 0 else "red" if pax > worst * 0.66 else "yellow"
        table.add_row(fmt.temp(t, units), "—" if pax <= 0 else f"≈{pax:,.0f}",
                      Text(bar(pax, worst, 28) or "·", style=style), " ".join(marks))
    return table


def decades_view(rows: list[tuple[str, float, float | None, float | None]], headline_text: str,
                 caveat: str) -> RenderableType:
    """Restricted days/yr per period. rows: (label, value, spread_lo, spread_hi)."""
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False,
                  title="Restricted days per year (daily max temp, estimate)", title_justify="left",
                  title_style="muted")
    table.add_column("Period", no_wrap=True)
    table.add_column("Days/yr", justify="right", no_wrap=True)
    table.add_column("", no_wrap=True)
    top = max([r[1] for r in rows] + [r[3] or 0 for r in rows] + [1])
    for label, value, lo, hi in rows:
        projected = lo is not None
        b = Text(bar(value, top, 32) or "·", style="red" if projected else "yellow")
        if projected and hi is not None:
            b.append(f"  range {lo:.0f}–{hi:.0f}", style="muted")
        table.add_row(Text(label, style="bold" if projected else ""), f"{value:,.0f}", b)
    return Group(Text(headline_text, style="bold"), table, Text(caveat, style="muted"))


def takeoff_page(head: Text, panel: Panel, table: Table, extra: RenderableType | None,
                 hints: list[str]) -> RenderableType:
    """Assemble the takeoff page."""
    parts: list[RenderableType] = [head, panel]
    if extra is not None:
        parts.append(extra)
    parts += [table, hint_line(hints)]
    return Group(*parts)
