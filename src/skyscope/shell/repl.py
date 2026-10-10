"""The interactive shell loop, plus the shared 'run one line safely' boundary."""

from __future__ import annotations

import json
import logging
import time
import traceback
from typing import Any

from rich.text import Text

from skyscope.config import RUNTIME, cache_dir, config_dir
from skyscope.data.sources import FetchError, OfflineError
from skyscope.data.store import DataUnavailable
from skyscope.shell import commands  # noqa: F401  (registers commands)
from skyscope.shell.context import Context
from skyscope.shell.registry import CommandResult, UserError

QUIT_WORDS = {"quit", "exit", "q", ":q", "bye"}

log = logging.getLogger("skyscope")


def _setup_log() -> None:
    if log.handlers:
        return
    try:
        handler = logging.FileHandler(cache_dir() / "skyscope.log", encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def error_line(ctx: Context, message: str, hint: str = "") -> None:
    """Print a one-line error with an optional dim hint."""
    text = Text("✖ ", style="bold red")
    text.append(message)
    if hint:
        text.append(f"\n  {hint}", style="hint")
    ctx.console.print(text)


def run_line(ctx: Context, line: str, as_json: bool = False) -> CommandResult | None:
    """Execute one command line, rendering the result. Never raises (except SystemExit)."""
    from skyscope.shell.commands import dispatch

    _setup_log()
    try:
        result = dispatch(ctx, line)
    except UserError as exc:
        error_line(ctx, str(exc), exc.hint)
        return None
    except KeyboardInterrupt:
        ctx.console.print(Text("cancelled", style="muted"))
        return None
    except OfflineError:
        error_line(ctx, "that needs the network, and SkyScope is in offline mode",
                   "run without --offline, or use data already cached")
        return None
    except FetchError as exc:
        error_line(ctx, f"network problem: {exc}", "check your connection and try again")
        return None
    except DataUnavailable as exc:
        error_line(ctx, str(exc))
        return None
    except Exception as exc:  # the REPL boundary: never show a traceback
        log.error("command failed: %r\n%s", line, traceback.format_exc())
        if RUNTIME.debug:
            ctx.console.print_exception()
        else:
            error_line(ctx, f"something went wrong ({type(exc).__name__}: {exc})",
                       f"details logged to {cache_dir() / 'skyscope.log'} · --debug shows tracebacks")
        return None
    if result is None:
        return None
    if as_json:
        ctx.console.print_json(json.dumps(result.data if result.data is not None else {}, default=_json_default))
    elif result.renderable is not None:
        ctx.console.print(result.renderable)
    return result


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def run_shell(ctx: Context) -> None:
    """Interactive loop with history, completion and a context-aware prompt."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory, InMemoryHistory

    from skyscope.shell.completer import SkyCompleter

    ctx.interactive = True
    try:
        history = FileHistory(str(config_dir() / "history"))
    except OSError:
        history = InMemoryHistory()
    session: PromptSession[str] = PromptSession(history=history, completer=SkyCompleter(ctx),
                                                complete_while_typing=False)
    _wait_for_width()
    run_line(ctx, "__banner__")
    while True:
        try:
            line = session.prompt(_prompt_html(ctx))
        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        if line.strip().lower() in QUIT_WORDS:
            break
        if not line.strip():
            continue
        t0 = time.perf_counter()
        run_line(ctx, line)
        log.info("ran %r in %.2fs", line, time.perf_counter() - t0)
        ctx.console.print()
    ctx.console.print(Text("Clear skies. ✈", style="muted"))


def _prompt_html(ctx: Context):
    """skyscope  PHX  737-800 ›  — airport in sky blue, aircraft as an orange badge."""
    from prompt_toolkit.formatted_text import HTML

    from skyscope.views.theme import SKY, SUN

    code, aircraft = ctx.prompt_parts()
    airport = f' <style fg="{SKY}"><b>{_escape(code)}</b></style>' if code else ""
    badge = f' <style bg="{SUN}" fg="#000000"><b> {_escape(aircraft)} </b></style>'
    return HTML(f"<b>skyscope</b>{airport}{badge} › ")


def _wait_for_width(min_cols: int = 40, timeout_s: float = 1.0) -> None:
    """Browser terminals (e.g. ttyd) start at a tiny size and resize a moment later; wait for it."""
    import shutil

    deadline = time.monotonic() + timeout_s
    while shutil.get_terminal_size((80, 24)).columns < min_cols and time.monotonic() < deadline:
        time.sleep(0.05)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
