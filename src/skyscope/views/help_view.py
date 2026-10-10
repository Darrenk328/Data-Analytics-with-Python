"""Help pages (overview + per command)."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from skyscope.views.theme import page, panel

CATEGORY_ORDER = ("Explore", "Heat & takeoff", "Compare & rank", "Session")


def help_overview(commands: list) -> RenderableType:
    """All commands grouped by category, one line each."""
    parts: list[RenderableType] = [
        Text("Type text to search · Tab completes · ↑ history", style="muted"),
    ]
    by_cat: dict[str, list] = {}
    for cmd in commands:
        by_cat.setdefault(cmd.category, []).append(cmd)
    for cat in CATEGORY_ORDER + tuple(c for c in by_cat if c not in CATEGORY_ORDER):
        cmds = by_cat.get(cat)
        if not cmds:
            continue
        parts.append(Text(""))
        parts.append(Text(cat, style="accent"))
        table = Table(box=None, show_header=False, padding=(0, 1), pad_edge=False)
        table.add_column(no_wrap=True, style="code", min_width=10)
        table.add_column(ratio=1)
        table.add_column(no_wrap=True, style="muted")
        for cmd in cmds:
            alias = f"({', '.join(cmd.aliases)})" if cmd.aliases else ""
            table.add_row(cmd.name, cmd.summary, alias)
        parts.append(table)
    return page(panel(Group(*parts), "SkyScope commands"), hints=["help takeoff", "open PHX", "aircraft"])


def command_help(cmd) -> RenderableType:
    """Usage, description and examples for one command."""
    parts: list[RenderableType] = [
        Text(cmd.summary),
        Text.assemble(("usage: ", "muted"), (cmd.usage, "bold")),
    ]
    if cmd.aliases:
        parts.append(Text.assemble(("aliases: ", "muted"), (", ".join(cmd.aliases), "")))
    if cmd.details:
        parts.append(Text(""))
        parts.append(Text(cmd.details))
    if cmd.examples:
        parts.append(Text(""))
        parts.append(Text("examples", style="muted"))
        for ex in cmd.examples:
            parts.append(Text.assemble(("  ", ""), (ex, "cyan")))
    return page(panel(Group(*parts), f"help · {cmd.name}"), hints=["help"])
