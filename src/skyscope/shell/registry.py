"""Command registry shared by the interactive shell and one-shot CLI mode.

A command is a function ``handler(ctx, args) -> CommandResult``. It parses its own
arguments with :func:`parse_args`, calls the data/perf/climate layers, and hands plain data
to a view. Commands never print; the REPL or CLI renders the result.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rapidfuzz import process
from rich.console import RenderableType

if TYPE_CHECKING:
    from skyscope.shell.context import Context


class UserError(Exception):
    """A problem the user can fix. Shown as one line plus a hint — never a traceback."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


@dataclass
class CommandResult:
    """What a command produced: something to render plus machine-readable data."""

    renderable: RenderableType | None = None
    data: Any = None  # JSON-able payload for --json and export
    name: str = ""  # used for export file names
    pager: bool = False


Handler = Callable[["Context", list[str]], CommandResult]


@dataclass
class Command:
    """Metadata + handler for one command."""

    name: str
    handler: Handler
    summary: str
    usage: str
    examples: list[str] = field(default_factory=list)
    aliases: tuple[str, ...] = ()
    category: str = "Explore"
    shell_only: bool = False
    details: str = ""


REGISTRY: dict[str, Command] = {}
ALIASES: dict[str, str] = {}


def command(name: str, summary: str, usage: str, examples: list[str] | None = None,
            aliases: tuple[str, ...] = (), category: str = "Explore", shell_only: bool = False,
            details: str = "") -> Callable[[Handler], Handler]:
    """Decorator registering a command handler."""

    def wrap(fn: Handler) -> Handler:
        REGISTRY[name] = Command(name, fn, summary, usage, examples or [], aliases, category,
                                 shell_only, details)
        for alias in aliases:
            ALIASES[alias] = name
        return fn

    return wrap


def resolve(word: str) -> Command | None:
    """Find a command by name or alias (case-insensitive)."""
    key = word.lower()
    key = ALIASES.get(key, key)
    return REGISTRY.get(key)


def suggest_command(word: str) -> str | None:
    """Closest command name for a typo."""
    names = list(REGISTRY) + list(ALIASES)
    guess = process.extractOne(word.lower(), names, score_cutoff=70)
    return ALIASES.get(guess[0], guess[0]) if guess else None


def split(line: str) -> list[str]:
    """Shell-like split that tolerates unbalanced quotes."""
    try:
        return shlex.split(line)
    except ValueError:
        return line.replace('"', " ").replace("'", " ").split()


def parse_args(args: list[str], spec: dict[str, type | None]) -> tuple[list[str], dict[str, Any]]:
    """Split args into positionals and ``--options``.

    ``spec`` maps option names (without dashes) to a type, or ``None`` for boolean flags.
    Accepts ``--opt value`` and ``--opt=value``. Unknown options raise UserError with a
    suggestion.
    """
    positionals: list[str] = []
    opts: dict[str, Any] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("--") and len(token) > 2:
            name, _, inline = token[2:].partition("=")
            name = name.lower()
            if name not in spec:
                guess = process.extractOne(name, list(spec), score_cutoff=60) if spec else None
                hint = f"did you mean --{guess[0]}?" if guess else (
                    "options: " + " ".join(f"--{k}" for k in spec) if spec else "this command takes no options")
                raise UserError(f"unknown option --{name}", hint)
            kind = spec[name]
            if kind is None:
                opts[name] = True
            else:
                if inline:
                    raw = inline
                elif i + 1 < len(args):
                    i += 1
                    raw = args[i]
                else:
                    raise UserError(f"--{name} needs a value")
                try:
                    opts[name] = kind(raw)
                except ValueError as exc:
                    raise UserError(f"--{name}: '{raw}' is not a valid {kind.__name__}") from exc
        else:
            positionals.append(token)
        i += 1
    return positionals, opts
