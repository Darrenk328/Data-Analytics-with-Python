"""Typer entry point. Phase 0: help + echo REPL."""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, help="SkyScope: Heat & Takeoff", invoke_without_command=True)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Open the interactive shell when no command is given."""
    if ctx.invoked_subcommand is None:
        from prompt_toolkit import PromptSession

        session: PromptSession[str] = PromptSession()
        while True:
            try:
                line = session.prompt("skyscope › ")
            except (EOFError, KeyboardInterrupt):
                break
            if line.strip() in {"quit", "exit"}:
                break
            print(line)


@app.command()
def version() -> None:
    """Print the SkyScope version."""
    from skyscope import __version__

    print(__version__)
