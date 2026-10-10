"""The launch screen: wordmark, live story panel, command menu, footer."""

from __future__ import annotations

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from skyscope.views import format as fmt
from skyscope.views.theme import SKY, SUN, Responsive, panel

# Bold 5-row block glyphs (each line is the same width within a letter).
GLYPHS = {
    "S": ["███████", "██     ", "███████", "     ██", "███████"],
    "K": ["██   ██", "██  ██ ", "█████  ", "██  ██ ", "██   ██"],
    "Y": ["██    ██", " ██  ██ ", "  ████  ", "   ██   ", "   ██   "],
    "C": [" ██████", "██     ", "██     ", "██     ", " ██████"],
    "O": [" ██████ ", "██    ██", "██    ██", "██    ██", " ██████ "],
    "P": ["██████ ", "██   ██", "██████ ", "██     ", "██     "],
    "E": ["███████", "██     ", "█████  ", "██     ", "███████"],
}
TAGLINE = "Hot air is thin air. See how heat grounds airplanes."

MENU = [
    ("◎ Explore", [("find phoenix", "Search 86k airports by name or code"),
                   ("filter elevation>6000", "Narrow results: country, runway…"),
                   ("open PHX", "Airport card: weather, runways, heat")]),
    ("✈ Takeoff", [("takeoff PHX", "Could a full jet take off right now?"),
                   ("takeoff PHX --sweep", "Passengers lost from 20 °C to 50 °C"),
                   ("takeoff PHX --decades", "Restricted days a year, 1940s→2050")]),
    ("☀ Climate", [("heat PHX", "85 years of heat + 2050 projection"),
                   ("heat PHX --plot", "Save the chart as a PNG (Matplotlib)")]),
    ("⇄ Compare", [("vs PHX DOH DFW", "Side by side; best value in green")]),
]
SOURCES = "Data: OurAirports · NOAA AWC · Open-Meteo (ERA5, CMIP6)"
KEYS = "help · Tab · ↑ history · quit"


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb, strict=True))


def wordmark(word: str = "SKYSCOPE") -> Text:
    """Block-letter wordmark with a sky-blue → orange gradient (66 columns for SKYSCOPE)."""
    lines = [" ".join(GLYPHS[ch][r] for ch in word) for r in range(5)]
    width = max(len(line) for line in lines)
    text = Text()
    for r, line in enumerate(lines):
        for x, char in enumerate(line.ljust(width)):
            text.append(char, style=f"bold {_mix(SKY, SUN, x / max(1, width - 1))}" if char != " " else "")
        if r < len(lines) - 1:
            text.append("\n")
    return text


def compact_wordmark(word: str = "SKYSCOPE") -> Text:
    """Spaced-letter gradient wordmark for narrow terminals."""
    spaced = " ".join(word)
    text = Text()
    for x, ch in enumerate(spaced):
        text.append(ch, style=f"bold {_mix(SKY, SUN, x / max(1, len(spaced) - 1))}")
    return text


def _header(n_airports: int, weather_note: str | None, width: int) -> RenderableType:
    stats = f"{fmt.num(n_airports)} airports" + (f" · {weather_note}" if weather_note else "") \
        + " · climate 1940–2050"
    mark = wordmark() if width >= 72 else compact_wordmark()
    body = Group(Align.center(mark), Text(""), Text(TAGLINE, style="italic", justify="center"),
                 Text(stats, style="dim", justify="center"))
    return panel(body, Text(" ✈ Heat & Takeoff ", style=f"bold {SKY}"))


def story_panel(story: dict) -> RenderableType:
    """The live headline ("Right now at Phoenix…") in a highlighted panel."""
    body = Text()
    body.append(f"Right now at {story['city']} ({story['code']}): ", style="bold")
    body.append(fmt.temp(story["temp_c"]), style="bold")
    body.append(". ")
    if story["status"] == "OK" and story["margin_c"] is not None:
        body.append(f"A full {story['aircraft']} is ")
        body.append(f"≈{story['margin_c']:.0f} °C", style=f"bold {SUN}")
        body.append(" from weight restriction.")
    elif story["status"] == "OK":
        body.append(f"A full {story['aircraft']} has no restriction here today.")
    else:
        body.append(f"A full {story['aircraft']} is ")
        body.append("weight-restricted", style=f"bold {SUN}")
        body.append(f": ≈{story['passengers']:.0f} passengers would stay behind.")
    when = f"{story['station']} {fmt.stamp(story['observed'])}"
    if story["origin"] in ("bulk", "cache") and story.get("snapshot"):
        when += " · bundled snapshot"
    body.append(f"\n{when} · estimate", style="est")
    return panel(body, "✈ Right now", border=SUN)


def _menu() -> Table:
    table = Table(box=box.ROUNDED, border_style=SKY, show_header=False, padding=(0, 1), expand=True,
                  title=Text(" What you can do ", style="bold"), title_justify="left")
    table.add_column(no_wrap=True, style=f"bold {SKY}", width=9)
    table.add_column(no_wrap=True, style="cyan", width=21)
    table.add_column(no_wrap=True, overflow="ellipsis", ratio=1)
    for s, (section, rows) in enumerate(MENU):
        for i, (cmd, desc) in enumerate(rows):
            table.add_row(section if i == 0 else "", cmd, desc, end_section=(i == len(rows) - 1 and s < len(MENU) - 1))
    return table


def _footer(width: int) -> Text:
    if len(SOURCES) + len(KEYS) + 6 <= width:
        return Text.assemble((SOURCES, "dim"), ("   ·   ", "dim"), (KEYS, "dim"))
    return Text.assemble((SOURCES, "dim"), ("\n", ""), (KEYS, "dim"))


def launch_view(n_airports: int, weather_note: str | None, story: dict | None) -> RenderableType:
    """Wordmark + tagline, optional live story panel, command menu, footer."""
    header = Responsive(lambda width: _header(n_airports, weather_note, width))
    parts: list[RenderableType] = [header]
    if story:
        parts += [Text(""), story_panel(story)]
    parts += [Text(""), _menu(), Responsive(_footer), Text("")]
    return Group(*parts)
