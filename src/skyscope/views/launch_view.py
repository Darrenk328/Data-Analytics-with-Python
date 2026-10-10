"""The launch screen."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text

from skyscope.views import format as fmt


def launch_view(n_airports: int, weather_note: str | None, headline: Text | None) -> RenderableType:
    """Title, data summary, live headline and suggested first commands."""
    parts: list[RenderableType] = [
        Text(""),
        Text.assemble(("  ✈  SKYSCOPE", "bold cyan"), (" · Heat & Takeoff", "bold")),
        Text(f"  {fmt.num(n_airports)} airports"
             + (f" · {weather_note}" if weather_note else "")
             + " · climate data 1940–2050", style="muted"),
        Text(""),
    ]
    if headline is not None:
        parts += [headline, Text("")]
    parts += [
        Text.assemble(("  Try:  ", "muted"), ("open PHX", "cyan"), ("  ·  ", "muted"),
                      ("takeoff PHX", "cyan"), ("  ·  ", "muted"), ("heat PHX", "cyan"),
                      ("  ·  ", "muted"), ("rank heat-risk", "cyan"), ("  ·  ", "muted"),
                      ("tour", "cyan")),
        Text("  help for all commands · Tab to autocomplete · ↑ for history", style="muted"),
        Text(""),
    ]
    return Group(*parts)
