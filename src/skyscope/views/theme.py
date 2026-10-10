"""Colours, styles and the shared Console factory.

Rich already honours NO_COLOR and drops styling when stdout is not a terminal, so views can
use styles freely and still degrade to clean plain text.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text
from rich.theme import Theme

STATUS_STYLE = {
    "OK": "bold green",
    "RESTRICTED": "bold yellow",
    "SEVERE": "bold red",
    "ABOVE LIMIT": "bold magenta",
    "NO DATA": "dim",
}
STATUS_ICON = {"OK": "✓", "RESTRICTED": "▲", "SEVERE": "✖", "ABOVE LIMIT": "!", "NO DATA": "·"}
FLIGHT_CAT_STYLE = {"VFR": "bold green", "MVFR": "bold blue", "IFR": "bold red",
                    "LIFR": "bold magenta"}

THEME = Theme({
    "title": "bold",
    "accent": "bold cyan",
    "code": "bold cyan",
    "hint": "dim",
    "muted": "dim",
    "est": "italic",
    "good": "green",
    "warn": "yellow",
    "bad": "red",
    "best": "bold green",
})


def make_console(width: int | None = None, record: bool = False, force_terminal: bool | None = None) -> Console:
    """Console used by the app and the tests (``Console(record=True, width=100)``)."""
    return Console(theme=THEME, width=width, record=record, highlight=False,
                   force_terminal=force_terminal, soft_wrap=False)


def hint_line(commands: list[str]) -> Text:
    """The dim 'next steps' line that ends every view."""
    text = Text("next → ", style="hint")
    for i, cmd in enumerate(c for c in commands if c):
        if i:
            text.append("  ·  ", style="hint")
        text.append(cmd, style="dim cyan")
    return text


def anomaly_rgb(anomaly: float, span: float = 2.5) -> str:
    """Blue → white → red colour (hex) for a temperature anomaly in °C (warming stripes)."""
    x = max(-1.0, min(1.0, anomaly / span))
    if x < 0:  # blue side: (33,102,172) at -1 → (247,247,247) at 0
        lo, hi, t = (33, 102, 172), (247, 247, 247), x + 1
    else:  # red side: (247,247,247) at 0 → (178,24,43) at +1
        lo, hi, t = (247, 247, 247), (178, 24, 43), x
    r, g, b = (round(lo[i] + (hi[i] - lo[i]) * t) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def temp_style(temp_c: float | None) -> str:
    """Style for a temperature reading (cool → hot)."""
    if temp_c is None:
        return "dim"
    if temp_c >= 40:
        return "bold red"
    if temp_c >= 32:
        return "red"
    if temp_c >= 25:
        return "yellow"
    if temp_c <= 0:
        return "cyan"
    return "default"


class Responsive:
    """A renderable built at render time for the available width (for 80-col layouts)."""

    def __init__(self, build) -> None:  # build: Callable[[int], RenderableType]
        self.build = build

    def __rich_console__(self, console, options):
        yield self.build(options.max_width)
