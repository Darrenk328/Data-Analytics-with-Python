"""Results table for find / filter / near."""

from __future__ import annotations

from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from skyscope.views import format as fmt
from skyscope.views.theme import Responsive, hint_line

TYPE_SHORT = {"large_airport": "large", "medium_airport": "medium", "small_airport": "small",
              "seaplane_base": "seaplane", "heliport": "heliport", "balloonport": "balloon",
              "closed": "closed"}


def results_view(records: list[dict[str, Any]], title: str, breadcrumb: list[str], total: int,
                 units: str = "metric", hints: list[str] | None = None,
                 distance: bool = False) -> RenderableType:
    """Numbered airport table with a headline and breadcrumb."""
    parts: list[RenderableType] = []
    head = Text()
    head.append(title, style="title")
    head.append(f"  ·  {fmt.plural(total, 'airport')}", style="muted")
    parts.append(head)
    if breadcrumb:
        crumb = Text("  ", style="muted")
        for i, step in enumerate(breadcrumb):
            if i:
                crumb.append("  ›  ", style="muted")
            crumb.append(step, style="cyan")
        parts.append(crumb)

    if not records:
        parts.append(Text("  No airports match.", style="warn"))
    else:
        parts.append(Responsive(lambda width: _table(records, units, distance, width)))
        if total > len(records):
            parts.append(Text(f"  … and {fmt.num(total - len(records))} more — narrow it with "
                              "filter, e.g. filter type=large", style="muted"))
    if hints:
        parts.append(hint_line(hints))
    return Group(*parts)


def _table(records: list[dict[str, Any]], units: str, distance: bool, width: int) -> Table:
    wide = width >= 100
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    table.add_column("#", justify="right", style="muted", no_wrap=True)
    table.add_column("Code", style="code", no_wrap=True, min_width=4)
    table.add_column("Name", overflow="ellipsis", no_wrap=True, max_width=44 if wide else 34)
    if wide:
        table.add_column("City", overflow="ellipsis", no_wrap=True, max_width=20)
    table.add_column("Ctry", no_wrap=True)
    table.add_column("Type", no_wrap=True, style="muted")
    table.add_column("Elev ft", justify="right", no_wrap=True)
    table.add_column("Rwy " + ("ft" if units == "imperial" else "m"), justify="right", no_wrap=True)
    if distance:
        table.add_column("Dist nm", justify="right", no_wrap=True)
    for i, rec in enumerate(records, start=1):
        row = [str(i), fmt.text(rec.get("code")), fmt.text(rec.get("name"))]
        if wide:
            row.append(fmt.text(rec.get("municipality")))
        rwy = rec.get("longest_ft")
        row += [
            fmt.text(rec.get("iso_country")),
            TYPE_SHORT.get(rec.get("type") or "", fmt.text(rec.get("type"))),
            fmt.num(rec.get("elevation_ft")),
            fmt.num(rwy if units == "imperial" or rwy is None else rwy / fmt.FT_PER_M),
        ]
        if distance:
            d = rec.get("distance_nm")
            row.append(f"{fmt.num(d)} {rec.get('bearing_compass') or ''}".strip() if d is not None else fmt.DASH)
        table.add_row(*row)
    return table
