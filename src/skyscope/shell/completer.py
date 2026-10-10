"""Tab completion: command names, options, airport codes, aircraft ids, metrics, topics."""

from __future__ import annotations

import re
from collections.abc import Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from skyscope.shell.context import Context
from skyscope.shell.registry import ALIASES, REGISTRY, resolve

SHOWCASE_CODES = ("PHX", "LAS", "DFW", "IAH", "DXB", "DOH", "KWI", "RUH", "DEL", "BKK", "DEN",
                  "MEX", "BOG", "UIO", "LPB", "ADD", "NBO", "JNB", "LHR", "JFK", "SIN", "OSL")
WORD_ARGS = {
    "explain": ("takeoff", "climate", "data"),
    "units": ("metric", "imperial"),
    "export": ("csv", "json", "md"),
    "rank": ("heat-risk", "warming", "threshold", "density-altitude", "elevation", "runway",
             "shortest-runway"),
    "filter": ("country=", "region=", "continent=", "type=", "runway>", "surface=", "elevation>",
               "service=yes", "iata=", "name~", "city~", "clear"),
}
_OPT = re.compile(r"--[a-z][a-z-]*")


class SkyCompleter(Completer):
    """Context-aware completer for the SkyScope shell."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    def _codes(self) -> list[str]:
        codes: list[str] = list(self.ctx.settings.favourites)
        ap = self.ctx.store.airports
        if self.ctx.results:
            codes += [str(ap["code"].iat[i]) for i in self.ctx.results.indices[:30]]
        if self.ctx.airport_idx is not None:
            codes.append(str(ap["code"].iat[self.ctx.airport_idx]))
        codes += SHOWCASE_CODES
        seen: dict[str, None] = {}
        for c in codes:
            seen.setdefault(c, None)
        return list(seen)

    def _aircraft(self) -> list[str]:
        try:
            from skyscope.perf.aircraft import load_aircraft

            return [a.id for a in load_aircraft()]
        except Exception:
            return []

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        text = document.text_before_cursor
        words = text.split()
        current = "" if text.endswith(" ") else (words[-1] if words else "")
        if len(words) == 0 or (len(words) == 1 and not text.endswith(" ")):
            for name in sorted(list(REGISTRY) + list(ALIASES)):
                cmd = REGISTRY.get(ALIASES.get(name, name))
                if name.startswith(current.lower()) and cmd and cmd.category != "_hidden":
                    yield Completion(name, -len(current), display_meta=cmd.summary)
            return
        cmd = resolve(words[0])
        if cmd is None:
            return
        previous = words[-2] if not text.endswith(" ") and len(words) >= 2 else words[-1]
        if current.startswith("--"):
            for opt in sorted(set(_OPT.findall(cmd.usage))):
                if opt.startswith(current):
                    yield Completion(opt, -len(current))
            return
        if previous == "--aircraft" or cmd.name == "aircraft":
            options = self._aircraft()
        elif cmd.name in WORD_ARGS:
            options = list(WORD_ARGS[cmd.name])
        else:
            options = self._codes()
        for opt in options:
            if opt.lower().startswith(current.lower()):
                yield Completion(opt, -len(current))
