"""Session state: current airport, aircraft, last results (with a back stack), settings."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from skyscope.config import Settings
from skyscope.data.store import DataStore, get_store


@dataclass
class ResultSet:
    """A list of airport row indices plus how we got there."""

    indices: list[int]
    title: str
    breadcrumb: list[str]
    extra: dict[int, dict[str, Any]] = field(default_factory=dict)  # e.g. distances for `near`


@dataclass
class Context:
    """Everything a command may need. One per shell session / one-shot invocation."""

    console: Console
    settings: Settings = field(default_factory=Settings.load)
    interactive: bool = False
    airport_idx: int | None = None
    results: ResultSet | None = None
    back_stack: list[ResultSet | None] = field(default_factory=list)
    last: Any = None  # last CommandResult (for export)
    _store: DataStore | None = None

    @property
    def store(self) -> DataStore:
        """The airport DataStore (loaded on first use)."""
        if self._store is None:
            self._store = get_store()
        return self._store

    @property
    def units(self) -> str:
        """Display units ("metric" or "imperial")."""
        return self.settings.units

    def push_results(self, results: ResultSet) -> None:
        """Replace the current results, remembering the previous set for `back`."""
        self.back_stack.append(self.results)
        del self.back_stack[:-20]
        self.results = results

    def pop_results(self) -> ResultSet | None:
        """Go back to the previous result set (returns it, or None if there is none)."""
        if not self.back_stack:
            return None
        self.results = self.back_stack.pop()
        return self.results

    @contextlib.contextmanager
    def spinner(self, message: str) -> Iterator[None]:
        """Show a spinner while a slow fetch runs (only on a real terminal)."""
        if self.console.is_terminal:
            with self.console.status(message, spinner="dots"):
                yield
        else:
            yield

    def prompt_parts(self) -> tuple[str | None, str]:
        """(current airport code or None, aircraft id) for the coloured prompt."""
        code = None
        if self.airport_idx is not None:
            code = str(self.store.airports["code"].iat[self.airport_idx])
        return code, self.settings.aircraft

    def prompt_label(self) -> str:
        """Context shown in the shell prompt: "KPHX · 737-800"."""
        parts = []
        if self.airport_idx is not None:
            parts.append(str(self.store.airports["ident"].iat[self.airport_idx]))
        parts.append(self.settings.aircraft)
        return " · ".join(parts)
