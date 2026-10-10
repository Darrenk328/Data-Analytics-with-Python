"""Side-by-side comparison (vs PHX DOH DFW): best value per row in green, one-line verdict."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from skyscope.views import format as fmt
from skyscope.views.theme import Responsive, page, panel


@dataclass
class Row:
    """One comparison row: raw values (None = missing), display strings, and which way is better."""

    label: str
    values: list[float | None]
    shown: list[str]
    better: str | None = None  # "low" | "high" | None (no highlight)


def best_index(row: Row) -> int | None:
    """Index of the best value (ties → none highlighted; fewer than 2 values → none)."""
    present = [(v, i) for i, v in enumerate(row.values) if v is not None]
    if row.better is None or len(present) < 2:
        return None
    pick = min(present) if row.better == "low" else max(present)
    if sum(1 for v, _ in present if abs(v - pick[0]) < 1e-9) > 1:
        return None
    return pick[1]


def compare_view(codes: list[str], names: list[str], rows: list[Row], verdict: str,
                 aircraft_name: str, notes: list[str]) -> RenderableType:
    """Per-airport columns; best per row highlighted green."""
    table = Responsive(lambda width: _table(codes, names, rows, width))
    parts: list[RenderableType] = [table, Text("")]
    parts += [Text(n, style="muted") for n in notes]
    parts.append(Text(verdict, style="bold"))
    return page(panel(Group(*parts), f"⇄ Compare · {' vs '.join(codes)} · {aircraft_name}",
                      "green = best in row · ≈ estimates"),
                hints=[f"takeoff {codes[0]} --decades", f"heat {codes[-1]}", f"open {codes[0]}"])


def cell(value: float | None, render) -> str:
    """Format a value or —."""
    return fmt.DASH if value is None else render(value)


def _table(codes: list[str], names: list[str], rows: list[Row], width: int) -> Table:
    label_w = max(len(r.label) for r in rows)
    col_w = max(9, (width - label_w - 1) // len(codes) - 1)
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    table.add_column("", no_wrap=True, style="muted", width=label_w)
    for code in codes:
        table.add_column(code, justify="right", no_wrap=True, width=col_w)
    short = [n if len(n) <= col_w else n[: col_w - 1] + "…" for n in names]
    table.add_row("", *[Text(n, style="muted") for n in short])
    for row in rows:
        best = best_index(row)
        table.add_row(row.label, *[Text(s, style="best" if i == best else "") for i, s in enumerate(row.shown)])
    return table
