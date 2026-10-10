"""Typer entry point: `skyscope` opens the shell; `skyscope <command> ...` runs one command.

One-shot commands are generated from the shell's command registry, so both modes share the
exact same implementation. Global flags (--json, --offline, --debug) may appear anywhere.
"""

from __future__ import annotations

import sys

import typer

from skyscope.config import RUNTIME
from skyscope.shell import commands as _commands  # noqa: F401  (registers commands)
from skyscope.shell.registry import REGISTRY

GLOBAL_FLAGS = {"--json", "--offline", "--debug"}

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode=None,
    help="SkyScope: Heat & Takeoff — how a warming climate limits takeoff weight at the "
         "world's airports. Run with no command to open the interactive shell.",
)


def _make_context():
    from skyscope.shell.context import Context
    from skyscope.views.theme import make_console

    return Context(console=make_console())


@app.callback()
def main(
    ctx: typer.Context,
    offline: bool = typer.Option(False, "--offline", help="Never use the network (bundled/cached data only)."),
    debug: bool = typer.Option(False, "--debug", help="Show full tracebacks on errors."),
) -> None:
    """Open the interactive shell when no command is given."""
    RUNTIME.offline = RUNTIME.offline or offline
    RUNTIME.debug = RUNTIME.debug or debug
    if ctx.invoked_subcommand is None:
        from skyscope.shell.repl import run_shell

        run_shell(_make_context())


def _run_one(name: str, args: list[str]) -> None:
    from skyscope.shell.registry import split
    from skyscope.shell.repl import run_line

    as_json = "--json" in args
    RUNTIME.offline = RUNTIME.offline or "--offline" in args
    RUNTIME.debug = RUNTIME.debug or "--debug" in args
    rest = [a for a in args if a not in GLOBAL_FLAGS]
    # A single quoted argument like "elevation>6000 type=large" is split like the shell would.
    if len(rest) == 1 and " " in rest[0] and name in {"filter", "find"}:
        rest = split(rest[0])
    ctx = _make_context()
    line = " ".join([name] + [_quote(a) for a in rest])
    result = run_line(ctx, line, as_json=as_json)
    if result is None:
        raise typer.Exit(code=1)


def _quote(arg: str) -> str:
    return f'"{arg}"' if (" " in arg and '"' not in arg) else arg


def _register(name: str) -> None:
    cmd = REGISTRY[name]
    help_text = cmd.summary + ".\n\nUsage: " + cmd.usage
    if cmd.examples:
        help_text += "\n\nExamples:\n\n" + "\n\n".join(f"  {e}" for e in cmd.examples)
    help_text += "\n\nAdd --json for machine-readable output."

    def run(args: list[str] = typer.Argument(None, help="Arguments and options, as in the shell.")) -> None:
        _run_one(name, list(args or []))

    run.__doc__ = help_text
    app.command(name=name, help=help_text, context_settings={
        "allow_extra_args": True, "ignore_unknown_options": True})(run)


for _name, _cmd in list(REGISTRY.items()):
    if not _cmd.shell_only and _cmd.category != "_hidden":
        _register(_name)


def entry() -> None:  # pragma: no cover - convenience for `python -m skyscope`
    """Run the app (used by __main__)."""
    app(prog_name="skyscope", args=sys.argv[1:])
