"""Command handlers: thin glue between the data/perf/climate layers and the views."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from skyscope.data import filters as flt
from skyscope.data.search import search, suggest
from skyscope.shell.context import Context, ResultSet
from skyscope.shell.registry import (
    REGISTRY,
    CommandResult,
    UserError,
    command,
    parse_args,
    resolve,
    split,
    suggest_command,
)
from skyscope.views import help_view
from skyscope.views.results import results_view

RESULT_LIMIT = 25
RECORD_KEYS = ("ident", "code", "iata_code", "icao_code", "name", "municipality", "iso_country",
               "country_name", "type", "lat", "lon", "elevation_ft", "longest_ft",
               "longest_paved_ft", "runway_count", "scheduled")


# --------------------------------------------------------------------------- helpers


def resolve_airport(ctx: Context, token: str | None, required: bool = True) -> int | None:
    """Turn "PHX" / "KPHX" / "2" (row of last results) / None (current airport) into a row index."""
    if token is None or token == "":
        if ctx.airport_idx is not None:
            return ctx.airport_idx
        if not required:
            return None
        raise UserError("no airport selected", "name one (e.g. takeoff PHX) or open one first: open PHX")
    if token.isdigit() and ctx.results and 1 <= int(token) <= len(ctx.results.indices):
        return ctx.results.indices[int(token) - 1]
    idx = ctx.store.lookup_index(token)
    if idx is not None:
        return idx
    close = suggest(ctx.store, token)
    if close:
        names = ", ".join(f"{ctx.store.airports['code'].iat[i]} ({ctx.store.airports['name'].iat[i]})"
                          for i in close)
        raise UserError(f"no airport with code '{token}'", f"did you mean {names}?")
    raise UserError(f"no airport matches '{token}'", f"try: find {token}")


def airport_record(ctx: Context, idx: int) -> dict[str, Any]:
    """Store record for an airport row."""
    return ctx.store.record(idx)


def records_for(ctx: Context, indices: list[int], extra: dict[int, dict] | None = None) -> list[dict]:
    """Compact JSON-able records for result tables and --json output."""
    ap = ctx.store.airports
    rows = ap.loc[indices, list(RECORD_KEYS)].to_dict("records") if indices else []
    out = []
    for idx, row in zip(indices, rows, strict=False):
        clean = {k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()}
        if extra and idx in extra:
            clean.update(extra[idx])
        out.append(clean)
    return out


def show_results(ctx: Context, rs: ResultSet, hints: list[str] | None = None) -> CommandResult:
    """Render a result set (first RESULT_LIMIT rows) and package its data."""
    shown = rs.indices[:RESULT_LIMIT]
    recs = records_for(ctx, shown, rs.extra)
    first = recs[0]["code"] if recs else "PHX"
    view = results_view(recs, rs.title, rs.breadcrumb, len(rs.indices), ctx.units,
                        hints=hints or ["open 1", f"takeoff {first}", "filter elevation>5000"],
                        distance=bool(rs.extra))
    return CommandResult(view, data=records_for(ctx, rs.indices[:500], rs.extra), name="results")


def dispatch(ctx: Context, line: str) -> CommandResult | None:
    """Run one command line. Bare text that isn't a command becomes a search."""
    tokens = split(line.strip())
    if not tokens:
        return None
    cmd = resolve(tokens[0])
    if cmd is None:
        word = tokens[0]
        guess = suggest_command(word)
        if guess and len(tokens) > 1 and guess != "find":
            raise UserError(f"unknown command '{word}'", f"did you mean '{guess}'? (help lists all)")
        return REGISTRY["find"].handler(ctx, tokens)
    if cmd.shell_only and not ctx.interactive:
        raise UserError(f"'{cmd.name}' only works in the interactive shell", "run skyscope with no arguments")
    result = cmd.handler(ctx, tokens[1:])
    if result is not None and result.data is not None:
        ctx.last = result
    return result


# --------------------------------------------------------------------------- explore


@command("find", "Search airports by name, city or code", "find <text>",
         ["find phoenix", 'find "new york"', "find KDEN", "phoenix"], aliases=("search", "s"),
         details="Exact IATA/ICAO codes rank first, then name and city prefixes, then fuzzy "
                 "matches (typos are fine). Typing text that isn't a command also searches.")
def cmd_find(ctx: Context, args: list[str]) -> CommandResult:
    pos, opts = parse_args(args, {"all": None})
    text = " ".join(pos).strip()
    if not text:
        raise UserError("find needs some text", "e.g. find phoenix")
    hits = search(ctx.store, text, limit=200, include_closed=bool(opts.get("all")))
    if not hits:
        raise UserError(f"nothing matches '{text}'", "check the spelling, or try a city or a 3-letter code")
    rs = ResultSet([h.idx for h in hits], f"Search: {text}", [f"find {text}"])
    ctx.push_results(rs)
    return show_results(ctx, rs)


@command("filter", "Filter airports (refines current results)", "filter <expr> | filter clear",
         ["filter country=Bolivia elevation>10000", "filter type=large runway>=3km",
          'filter "elevation>6000 type=large"', "filter name~intl continent=EU", "filter clear"],
         aliases=("where",),
         details="Terms are AND-ed: key=value, key=v1,v2, key!=v, key>n, key>=n, key<n, key~text.\n"
                 "Keys: country, region, continent, type, runway, surface, elevation, service, "
                 "iata, name, city.\nFriendly values: type=big, country=Iceland, runway>=3km, "
                 "elevation>2000m, surface=grass, service=yes.\nWhen results are showing, "
                 "filter narrows them; `filter clear` starts over from all airports.")
def cmd_filter(ctx: Context, args: list[str]) -> CommandResult:
    expr = " ".join(args).strip()
    if not expr:
        raise UserError("filter needs an expression", "e.g. filter country=US elevation>5000")
    if expr.lower() in {"clear", "reset", "none"}:
        ctx.push_results(None)  # type: ignore[arg-type]
        return CommandResult(Text("Filters cleared — the next filter searches all airports.", style="muted"))
    try:
        terms = flt.parse(expr, ctx.store)
    except flt.FilterError as exc:
        raise UserError(str(exc), exc.hint) from exc
    base = ctx.results
    pool = base.indices if base else None
    indices = flt.apply(terms, ctx.store, pool=pool)
    crumb = (base.breadcrumb if base else ["all airports"]) + [" ".join(t.describe() for t in terms)]
    rs = ResultSet(indices, "Filter", crumb)
    ctx.push_results(rs)
    hints = ["open 1", "back", "filter clear"] if indices else ["back", "filter clear", "help filter"]
    return show_results(ctx, rs, hints)


@command("back", "Return to the previous results", "back", ["back"], category="Session")
def cmd_back(ctx: Context, args: list[str]) -> CommandResult:
    rs = ctx.pop_results()
    if rs is None:
        return CommandResult(Text("Nothing to go back to — the next filter searches all airports.", style="muted"))
    return show_results(ctx, rs)


@command("results", "Show the current results again", "results", ["results"], aliases=("ls",),
         category="Session")
def cmd_results(ctx: Context, args: list[str]) -> CommandResult:
    if not ctx.results:
        raise UserError("no results yet", "try: find phoenix")
    return show_results(ctx, ctx.results)


# --------------------------------------------------------------------------- session


@command("help", "List commands, or explain one", "help [command]", ["help", "help takeoff"],
         aliases=("?", "h"), category="Session")
def cmd_help(ctx: Context, args: list[str]) -> CommandResult:
    if args:
        cmd = resolve(args[0])
        if cmd is None:
            guess = suggest_command(args[0])
            raise UserError(f"no command '{args[0]}'", f"did you mean '{guess}'?" if guess else "type help")
        return CommandResult(help_view.command_help(cmd))
    visible = [c for c in REGISTRY.values()
               if c.category != "_hidden" and (ctx.interactive or not c.shell_only)]
    return CommandResult(help_view.help_overview(visible))


@command("quit", "Leave SkyScope", "quit", ["quit"], aliases=("exit",), category="Session",
         shell_only=True)
def cmd_quit(ctx: Context, args: list[str]) -> CommandResult:  # handled by the REPL loop
    return CommandResult()


@command("__banner__", "Launch screen", "__banner__", category="_hidden", shell_only=True)
def cmd_banner(ctx: Context, args: list[str]) -> CommandResult:
    from skyscope.views.launch_view import launch_view

    return CommandResult(launch_view(ctx.store.size, None, None))
