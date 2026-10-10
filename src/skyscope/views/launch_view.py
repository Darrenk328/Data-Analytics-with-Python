"""The launch screen: title line, live headline, command menu, footer."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text

from skyscope.views import format as fmt
from skyscope.views.theme import GREEN

MENU = [
    ("Explore", ["find phoenix", "filter elevation>6000", "open PHX"]),
    ("Takeoff", ["takeoff PHX", "takeoff PHX --sweep", "takeoff PHX --decades"]),
    ("Climate", ["heat PHX", "heat PHX --plot"]),
    ("Compare", ["vs PHX DOH DFW"]),
]


def story_line(story: dict) -> Text:
    """Plain one-line live headline; numbers kept together with no-break spaces."""
    nb = "\u00a0"
    temp = fmt.temp(story["temp_c"]).replace(" ", nb)
    text = Text(f"Right now at {story['city']} ({story['code']}): {temp}. ")
    if story["status"] == "OK" and story["margin_c"] is not None:
        text.append(f"A full {story['aircraft']} is ")
        text.append(f"≈{story['margin_c']:.0f}{nb}°C", style=f"bold {GREEN}")
        text.append(" from weight restriction.")
    elif story["status"] == "OK":
        text.append(f"A full {story['aircraft']} has no restriction here today.")
    else:
        text.append(f"A full {story['aircraft']} is ")
        text.append("weight-restricted", style="bold red")
        text.append(f": ≈{story['passengers']:.0f} passengers would stay behind.")
    when = f"{story['station']} {fmt.stamp(story['observed'])}"
    if story["origin"] in ("bulk", "cache") and story.get("snapshot"):
        when += ", bundled snapshot"
    text.append(f"\n{when}. Estimate.", style="dim")
    return text


def launch_view(n_airports: int, weather_note: str | None, story: dict | None) -> RenderableType:
    """Title, optional live headline, command menu, footer - one blank line between sections."""
    title = Text.assemble(("SkyScope", f"bold {GREEN}"), ("  Heat & Takeoff", "bold white"))
    stats = f"{fmt.num(n_airports)} airports" + (f" · {weather_note}" if weather_note else "") \
        + " · climate 1940-2050"
    parts: list[RenderableType] = [title, Text(stats, style="dim")]
    if story:
        parts += [Text(""), story_line(story)]
    for section, cmds in MENU:
        parts += [Text(""), Text(section, style=f"bold {GREEN}")]
        parts += [Text(f"  {c}", style="white") for c in cmds]
    parts += [Text(""), Text("Data: OurAirports, NOAA AWC, Open-Meteo (ERA5, CMIP6)", style="dim"),
              Text("help · Tab · ↑ history · quit", style="dim"), Text("")]
    return Group(*parts)
