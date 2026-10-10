"""Colours, styles and the shared Console factory.

Rich already honours NO_COLOR and drops styling when stdout is not a terminal, so views can
use styles freely and still degrade to clean plain text.
"""

from __future__ import annotations

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# One palette everywhere: OK = green, RESTRICTED = orange, SEVERE / ABOVE LIMIT = red.
OK_COLOR, RESTRICTED_COLOR, SEVERE_COLOR = "green", "dark_orange", "red"
SKY, SUN = "#38bdf8", "#fb923c"  # wordmark gradient + panel borders

STATUS_STYLE = {
    "OK": f"bold {OK_COLOR}",
    "RESTRICTED": f"bold {RESTRICTED_COLOR}",
    "SEVERE": f"bold {SEVERE_COLOR}",
    "ABOVE LIMIT": f"bold {SEVERE_COLOR}",
    "NO DATA": "dim",
}
# Explicit hex foregrounds: "bold black" renders as grey in many terminals.
BADGE_STYLE = {
    "OK": f"bold #000000 on {OK_COLOR}",
    "RESTRICTED": f"bold #000000 on {RESTRICTED_COLOR}",
    "SEVERE": f"bold #ffffff on {SEVERE_COLOR}",
    "ABOVE LIMIT": f"bold #ffffff on {SEVERE_COLOR}",
    "NO DATA": "reverse",
}
BORDER_STYLE = {"OK": OK_COLOR, "RESTRICTED": RESTRICTED_COLOR, "SEVERE": SEVERE_COLOR,
                "ABOVE LIMIT": SEVERE_COLOR}
STATUS_ICON = {"OK": "✓", "RESTRICTED": "▲", "SEVERE": "✖", "ABOVE LIMIT": "!", "NO DATA": "·"}
FLIGHT_CAT_STYLE = {"VFR": "bold #000000 on green", "MVFR": "bold #ffffff on blue",
                    "IFR": "bold #ffffff on red", "LIFR": "bold #ffffff on magenta"}

THEME = Theme({
    "title": "bold",
    "accent": f"bold {SKY}",
    "code": f"bold {SKY}",
    "hint": "dim",
    "muted": "dim",
    "est": "dim italic",
    "good": OK_COLOR,
    "warn": RESTRICTED_COLOR,
    "bad": SEVERE_COLOR,
    "best": f"bold {OK_COLOR}",
    "border": SKY,
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


def badge(status: str) -> Text:
    """Status as a coloured badge: " RESTRICTED " on orange."""
    text = Text()  # unstyled base, so table padding around the badge stays uncoloured
    text.append(f" {status} ", style=BADGE_STYLE.get(status, "reverse"))
    return text


def est(text: str) -> Text:
    """An estimate note in the shared dim-italic style."""
    return Text(text, style="est")


def panel(body: RenderableType, title: str | Text, subtitle: str | Text | None = None,
          border: str = "border") -> Panel:
    """The one panel style: rounded border, bold left-aligned title, dim-italic subtitle."""
    title_text = title if isinstance(title, Text) else Text(f" {title} ", style="bold")
    sub = None
    if subtitle:
        sub = subtitle if isinstance(subtitle, Text) else Text(f" {subtitle} ", style="est")
    return Panel(body, title=title_text, title_align="left", subtitle=sub, subtitle_align="right",
                 box=box.ROUNDED, border_style=border, padding=(0, 1))


def page(*blocks: RenderableType | None, hints: list[str] | None = None) -> Group:
    """Panels separated by one blank line, with the hint line at the bottom."""
    parts: list[RenderableType] = []
    for block in blocks:
        if block is None:
            continue
        if parts:
            parts.append(Text(""))
        parts.append(block)
    if hints:
        parts.append(hint_line(hints))
    return Group(*parts)
