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


# --------------------------------------------------------------------------- airport + weather


def _runway_records(ctx: Context, ident: str) -> list[dict[str, Any]]:
    rw = ctx.store.runways_for(ident)
    recs = []
    for row in rw.to_dict("records"):
        recs.append({k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()})
    return recs


def pick_runway(ctx: Context, rec: dict[str, Any], want: str | None) -> tuple[str, float]:
    """(runway name, length ft): longest open paved by default, or the one asked for."""
    if want:
        key = want.upper().lstrip("RWY").strip()
        for rw in _runway_records(ctx, rec["ident"]):
            if key in (rw["le_ident"].upper(), rw["he_ident"].upper(), rw["name"].upper()) and rw["length_ft"]:
                return rw["name"], rw["length_ft"]
        names = ", ".join(r["name"] for r in _runway_records(ctx, rec["ident"])) or "none"
        raise UserError(f"{rec['code']} has no runway '{want}'", f"runways: {names}")
    if not rec.get("longest_paved_ft"):
        raise UserError(f"{rec['code']} has no open paved runway, so takeoff performance isn't modelled",
                        "try a larger airport, e.g. takeoff PHX")
    return rec["longest_paved_name"] or "longest", rec["longest_paved_ft"]


def _perf_check(rec: dict[str, Any]) -> None:
    if rec["type"] in ("heliport", "balloonport", "seaplane_base", "closed"):
        raise UserError(f"{rec['code']} is a {rec['type'].replace('_', ' ')} — no takeoff runway to model")
    if rec.get("elevation_ft") is None:
        raise UserError(f"{rec['code']} has no elevation on record, so takeoff performance isn't modelled")


def _aircraft(ctx: Context, key: str | None):
    from skyscope.perf.aircraft import AircraftError, get_aircraft

    try:
        return get_aircraft(key or ctx.settings.aircraft)
    except AircraftError as exc:
        raise UserError(str(exc), exc.hint) from exc


def _wx(ctx: Context, rec: dict[str, Any]):
    from skyscope.data.weather import get_metar

    with ctx.spinner(f"Fetching weather for {rec['station']}…"):
        return get_metar(rec["station"], rec["lat"], rec["lon"])


def _da(rec: dict[str, Any], m) -> float | None:
    from skyscope.perf.atmosphere import density_altitude_ft, pressure_altitude_ft

    if m is None or m.temp_c is None or rec.get("elevation_ft") is None:
        return None
    return float(density_altitude_ft(pressure_altitude_ft(rec["elevation_ft"], m.altimeter_inhg or 29.92), m.temp_c))


@command("open", "Airport card: weather, takeoff today, runways, climate", "open <n|code>",
         ["open PHX", "open 1", "open KDEN"], aliases=("o", "card"))
def cmd_open(ctx: Context, args: list[str]) -> CommandResult:
    from skyscope.perf.takeoff import evaluate
    from skyscope.perf.wind import RunwayEnd, best_end
    from skyscope.views import format as fmt
    from skyscope.views.airport_card import card
    from skyscope.views.takeoff_view import threshold_text
    from skyscope.views.theme import STATUS_STYLE

    pos, _ = parse_args(args, {})
    idx = resolve_airport(ctx, pos[0] if pos else None)
    ctx.airport_idx = idx
    rec = airport_record(ctx, idx)
    wx = _wx(ctx, rec)
    m = wx.metar
    runways = _runway_records(ctx, rec["ident"])
    ends = [RunwayEnd(r[f"{e}_ident"], r[f"{e}_heading"], r["length_ft"] or 0)
            for r in runways if not r["closed"] for e in ("le", "he") if r[f"{e}_ident"] and r[f"{e}_heading"] is not None]
    active = best_end(ends, m.wind_dir if m else None, m.wind_kt if m else None)

    ac = _aircraft(ctx, None)
    line = None
    data: dict[str, Any] = {"airport": records_for(ctx, [idx])[0], "metar": m.raw if m else None}
    if rec["perf_ok"] and m is not None and m.temp_c is not None:
        res = evaluate(ac, rec["elevation_ft"], rec["longest_paved_ft"] / fmt.FT_PER_M, m.temp_c,
                       m.altimeter_inhg, ctx.settings.kg_per_passenger)
        line = Text("  ")
        line.append(res.status, style=STATUS_STYLE[res.status])
        line.append(f"  full {ac.name}{' ≈' if ac.approx else ''} at {fmt.temp(m.temp_c, ctx.units)}: ")
        line.append("no restriction" if res.status == "OK" else
                    f"≈{fmt.mass(res.restriction_kg, ctx.units)} / ≈{res.passengers:,.0f} passengers offloaded")
        line.append(f" · restriction begins at {threshold_text(res.threshold, ctx.units)} (estimate)", style="muted")
        data["takeoff"] = res.to_dict()
    elif not rec["perf_ok"]:
        why = ("no paved runway" if rec.get("longest_paved_ft") is None else "no elevation on record") \
            if rec["type"] not in ("heliport", "seaplane_base", "balloonport", "closed") \
            else f"it's a {rec['type'].replace('_', ' ')}"
        line = Text(f"  Not modelled here ({why}).", style="muted")
    else:
        line = Text("  No live temperature — try: takeoff " + rec["code"] + " --temp 35", style="muted")
    climate_line, offset = _climate_card_line(ctx, rec)
    view = card(rec, wx, runways, active.ident if active else None, line, climate_line, ctx.units,
                offset, _da(rec, m))
    return CommandResult(view, data=data, name=f"airport_{rec['code']}")


def _climate_card_line(ctx: Context, rec: dict[str, Any]):
    """(renderable, utc offset) from cached climate only — never fetches on the card."""
    from skyscope.climate.history import load_era5
    from skyscope.climate.metrics import heat_summary
    from skyscope.views.heat_view import climate_line

    era = load_era5(rec, allow_fetch=False)
    if era is None:
        return Text(f"  Not downloaded yet — heat {rec['code']} fetches 85 years of history.", style="muted"), None
    return climate_line(heat_summary(era.dates, era.tmax), ctx.units), era.utc_offset_s


def _climate(ctx: Context, rec: dict[str, Any], projections: bool = True):
    """(Era5, Cmip6 | None, note) — fetching on demand with a spinner, cached afterwards."""
    from skyscope.climate.history import load_era5
    from skyscope.climate.projections import load_cmip6
    from skyscope.data.sources import FetchError, OfflineError

    if rec.get("elevation_ft") is None and rec["type"] in ("heliport", "closed"):
        raise UserError(f"no climate analysis for {rec['code']} ({rec['type']})")
    try:
        with ctx.spinner(f"Downloading 85 years of daily highs for {rec['code']} (once)…"):
            era = load_era5(rec)
    except (FetchError, OfflineError) as exc:
        raise UserError(f"climate history for {rec['code']} isn't cached and can't be downloaded ({exc})",
                        "showcase airports work offline: heat PHX, heat DXB, heat DEN …") from exc
    if era is None:
        raise UserError(f"climate history for {rec['code']} isn't cached (offline)",
                        "showcase airports work offline: heat PHX, heat DXB, heat DEN …")
    cm, note = None, None
    if projections:
        try:
            with ctx.spinner(f"Downloading CMIP6 projections for {rec['code']} (once)…"):
                cm = load_cmip6(rec)
            if cm is None:
                note = "Projections not cached (offline) — showing history only."
        except (FetchError, OfflineError, KeyError, ValueError) as exc:
            note = f"Projections unavailable ({exc}) — showing history only."
    return era, cm, note


@command("wx", "Decoded METAR + TAF", "wx [code]", ["wx KPHX", "wx"], aliases=("weather", "metar"))
def cmd_wx(ctx: Context, args: list[str]) -> CommandResult:
    from skyscope.data.weather import get_taf
    from skyscope.views.airport_card import weather_view

    pos, _ = parse_args(args, {})
    idx = resolve_airport(ctx, pos[0] if pos else None)
    ctx.airport_idx = idx
    rec = airport_record(ctx, idx)
    wx = _wx(ctx, rec)
    taf = get_taf(rec["station"])
    m = wx.metar
    data = {"station": rec["station"], "origin": wx.origin, "raw": m.raw if m else None,
            "temp_c": m.temp_c if m else None, "altimeter_inhg": m.altimeter_inhg if m else None,
            "flight_category": m.flight_category if m else None, "taf": taf}
    return CommandResult(weather_view(rec["code"], wx, taf, ctx.units, _da(rec, m)), data=data, name="wx")


@command("runways", "Runways with headwind/crosswind", "runways [code]", ["runways PHX", "rwy"],
         aliases=("rwy",))
def cmd_runways(ctx: Context, args: list[str]) -> CommandResult:
    from rich.console import Group

    from skyscope.views.airport_card import runways_table
    from skyscope.views.theme import hint_line

    pos, _ = parse_args(args, {})
    idx = resolve_airport(ctx, pos[0] if pos else None)
    ctx.airport_idx = idx
    rec = airport_record(ctx, idx)
    m = _wx(ctx, rec).metar
    runways = _runway_records(ctx, rec["ident"])
    head = Text(f"Runways at {rec['code']} · wind "
                + (f"{m.wind_dir:03.0f}° {m.wind_kt:.0f} kt" if m and m.wind_dir is not None and m.wind_kt
                   else "calm/variable" if m else "unknown"), style="bold")
    view = Group(head, runways_table(runways, ctx.units, None, (m.wind_dir, m.wind_kt) if m else (None, None)),
                 Text("+ headwind / − tailwind, then crosswind (kt)", style="muted"),
                 hint_line([f"takeoff {rec['code']}", f"takeoff {rec['code']} --runway {runways[0]['le_ident']}"
                            if runways else "", f"wx {rec['code']}"]))
    return CommandResult(view, data=[{k: r[k] for k in ("name", "length_ft", "width_ft", "surface",
                                                         "closed", "le_heading", "he_heading")} for r in runways],
                         name="runways")


@command("takeoff", "Could a full aircraft take off here? (live or --temp)",
         "takeoff [code] [--aircraft ID] [--runway ID] [--temp C] [--sweep] [--decades]",
         ["takeoff PHX", "takeoff PHX --temp 48", "takeoff DEN --aircraft A320neo",
          "takeoff PHX --sweep", "takeoff PHX --decades", "to LPB --runway 10"],
         aliases=("to",), category="Heat & takeoff",
         details="Uses the live METAR temperature and altimeter (or --temp), the longest open "
                 "paved runway (or --runway) and the session aircraft (or --aircraft). Results "
                 "are educational estimates — see the README and NOTES.md.")
def cmd_takeoff(ctx: Context, args: list[str]) -> CommandResult:
    import numpy as np

    from skyscope.perf.aircraft import load_aircraft
    from skyscope.perf.takeoff import evaluate, sweep
    from skyscope.views import format as fmt
    from skyscope.views.takeoff_view import (
        all_aircraft_table,
        headline,
        sweep_view,
        takeoff_page,
        verdict_panel,
    )

    pos, opts = parse_args(args, {"aircraft": str, "runway": str, "temp": float, "sweep": None,
                                  "decades": None})
    idx = resolve_airport(ctx, pos[0] if pos else None)
    ctx.airport_idx = idx
    rec = airport_record(ctx, idx)
    _perf_check(rec)
    ac = _aircraft(ctx, opts.get("aircraft"))
    rwy_name, rwy_ft = pick_runway(ctx, rec, opts.get("runway"))
    runway_m = rwy_ft / fmt.FT_PER_M
    altim = None
    today = "temp" not in opts
    if not today:
        oat = opts["temp"]
        if not -60 <= oat <= 60:
            raise UserError("--temp must be between −60 and 60 °C")
        note = "(what-if, --temp)"
    else:
        wx = _wx(ctx, rec)
        if wx.metar is None or wx.metar.temp_c is None:
            raise UserError(f"no current temperature for {rec['code']}" + (f" ({wx.note})" if wx.note else ""),
                            f"use a what-if temperature: takeoff {rec['code']} --temp 35")
        oat, altim = wx.metar.temp_c, wx.metar.altimeter_inhg
        note = f"({wx.metar.station} {fmt.stamp(wx.metar.observed)}{', ' + wx.origin if wx.origin != 'live' else ''})"
    kg_pax = ctx.settings.kg_per_passenger
    res = evaluate(ac, rec["elevation_ft"], runway_m, oat, altim, kg_pax)
    rows = [(a, evaluate(a, rec["elevation_ft"], runway_m, oat, altim, kg_pax)) for a in load_aircraft()]
    extra = None
    data: dict[str, Any] = {"airport": rec["code"], "aircraft": ac.id, "runway": rwy_name,
                            "result": res.to_dict(),
                            "all_aircraft": {a.id: r.to_dict() for a, r in rows}}
    if opts.get("sweep"):
        temps = np.arange(20, 51, 2)
        allow = sweep(ac, rec["elevation_ft"], runway_m, temps, altim or 29.92)
        srows = [(float(t), float(w), float((ac.mtow_kg - w) / kg_pax)) for t, w in zip(temps, allow, strict=False)]
        record = _record_high(ctx, rec)
        extra = sweep_view(ac, srows, oat if today else None, record, ctx.units)
        data["sweep"] = [{"oat_c": t, "allowable_kg": round(w), "passengers_lost": round(p, 1)} for t, w, p in srows]
    if opts.get("decades"):
        extra, data["decades"] = _decades(ctx, rec, ac, runway_m)
    code = rec["code"]
    hints = [f"takeoff {code} --sweep", f"takeoff {code} --decades", f"heat {code}"]
    view = takeoff_page(headline(code, ac, res, ctx.units, today),
                        verdict_panel(code, ac, res, rwy_name, ctx.units, note, today),
                        all_aircraft_table(rows, ctx.units), extra, hints)
    return CommandResult(view, data=data, name=f"takeoff_{code}")


def _record_high(ctx: Context, rec: dict[str, Any]) -> float | None:
    """Record daily max from cached climate data (None if not cached)."""
    import numpy as np

    from skyscope.climate.history import load_era5

    era = load_era5(rec, allow_fetch=False)
    return None if era is None else float(np.nanmax(era.tmax))


def _decades(ctx: Context, rec: dict[str, Any], ac, runway_m: float):
    """Restricted days/yr per decade + projection (view, data)."""
    from skyscope.climate.metrics import restricted_days
    from skyscope.climate.projections import delta_projection
    from skyscope.views.takeoff_view import decades_view

    era, cm, note = _climate(ctx, rec)
    projected = delta_projection(era.dates, era.tmax, cm) if cm is not None else None
    st = restricted_days(ac, rec["elevation_ft"], runway_m, era.dates, era.tmax, projected)
    rows: list[tuple[str, float, float | None, float | None]] = [(d, v, None, None) for d, v in st.decades]
    rows.append(("1996–2025", st.recent, None, None))
    med, rng = st.projected_median, st.projected_range
    if med is not None and rng is not None:
        rows.append(("2031–2050 proj.", med, rng[0], rng[1]))
    early = next((v for d, v in st.decades if d.startswith("196")), None)
    msg = f"A full {ac.name} at {rec['code']}: ≈{st.recent:.0f} restricted days/yr in 1996–2025"
    if early is not None and early > 0.5:
        msg += f" (×{st.recent / early:.1f} vs the 1960s)"
    elif early is not None:
        msg += f" (vs ≈{early:.0f} in the 1960s)"
    if med is not None:
        msg += f"; models project ≈{med:.0f}/yr by 2031–2050"
        if st.recent > 0.5:
            msg += f" (≈{med / st.recent:.1f}×)"
    msg += "."
    caveat = ("Uses each day's ERA5 maximum temperature at standard pressure — the worst departure of "
              "the day; cooler-hour departures fare better. Projections: CMIP6 HighResMIP, high-emissions, "
              "to 2050, multi-model median with min–max range.")
    if note:
        caveat = note + " " + caveat
    if st.mean_loss_kg:
        caveat = (f"On restricted days in 1996–2025 the average offload was ≈{st.mean_loss_kg:,.0f} kg "
                  f"(≈{st.mean_loss_kg / ctx.settings.kg_per_passenger:.0f} passengers). ") + caveat
    data = {"decades": dict(st.decades), "recent_1996_2025": round(st.recent, 1),
            "projected_2031_2050": {"median": med, "range": rng, "models": st.projected},
            "mean_offload_kg": round(st.mean_loss_kg), "estimate": True}
    return decades_view(rows, msg, caveat), data


@command("heat", "85 years of heat history + 2050 projection", "heat [code]",
         ["heat PHX", "heat DXB", "heat"], aliases=("climate",), category="Heat & takeoff")
def cmd_heat(ctx: Context, args: list[str]) -> CommandResult:
    import numpy as np

    from skyscope.climate.metrics import add_projection, heat_summary
    from skyscope.views.heat_view import heat_view

    pos, _ = parse_args(args, {})
    idx = resolve_airport(ctx, pos[0] if pos else None)
    ctx.airport_idx = idx
    rec = airport_record(ctx, idx)
    era, cm, note = _climate(ctx, rec)
    if np.isnan(era.tmax).all():
        raise UserError(f"no temperature history for {rec['code']}")
    summary = heat_summary(era.dates, era.tmax)
    if cm is not None:
        add_projection(summary, cm.dates, cm.tmax, cm.models)
    data = {"airport": rec["code"], "warm_season_months": summary.months,
            "warming_c_1951_1980_to_1996_2025": summary.warming,
            "trend_c_per_decade": summary.trend.slope_per_decade, "trend_t": summary.trend.t_stat,
            "record_c": summary.record_c, "record_date": summary.record_date,
            "warm_season_tmax_by_year": summary.warm, "projected_warm_season_median": summary.projected_warm,
            "projected_warming_by_model": summary.projected_warming, "source": "ERA5 via Open-Meteo; CMIP6 HighResMIP"}
    return CommandResult(heat_view(rec["code"], rec["name"], summary, ctx.units, note), data=data,
                         name=f"heat_{rec['code']}")


@command("aircraft", "List aircraft types, or set the session default", "aircraft [id]",
         ["aircraft", "aircraft 787-9", "ac A320neo"], aliases=("ac",), category="Heat & takeoff")
def cmd_aircraft(ctx: Context, args: list[str]) -> CommandResult:
    from rich.console import Group
    from rich.table import Table

    from skyscope.perf.aircraft import load_aircraft
    from skyscope.views import format as fmt

    if args:
        ac = _aircraft(ctx, args[0])
        ctx.settings.aircraft = ac.id
        ctx.settings.save()
        return CommandResult(Text(f"Default aircraft set to {ac.name}{' (≈ some inputs approximate)' if ac.approx else ''}.",
                                  style="green"), data={"aircraft": ac.id})
    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    for col, just in (("ID", "left"), ("Name", "left"), ("MTOW", "right"), ("Max payload", "right"),
                      ("Field length*", "right"), ("Src", "left")):
        table.add_column(col, justify=just, no_wrap=True)
    data = []
    for ac in load_aircraft():
        star = "◀" if ac.id == ctx.settings.aircraft else ""
        table.add_row(Text(ac.id, style="code"), f"{ac.name} {star}", fmt.mass(ac.mtow_kg, ctx.units),
                      fmt.mass(ac.max_payload_kg, ctx.units), f"{ac.tofl_ref_m:,.0f} m",
                      "≈ approx" if ac.approx else "sourced")
        data.append({"id": ac.id, "name": ac.name, "mtow_kg": ac.mtow_kg, "max_payload_kg": ac.max_payload_kg,
                     "tofl_ref_m": ac.tofl_ref_m, "approx": ac.approx, "source": ac.source})
    from skyscope.views.theme import hint_line

    view = Group(table, Text("* takeoff field length at MTOW, sea level, ISA. ≈ = a value could not be "
                             "confirmed in a manufacturer document (sources in perf/aircraft.toml).", style="muted"),
                 hint_line(["aircraft A320neo", "takeoff PHX"]))
    return CommandResult(view, data=data, name="aircraft")


@command("units", "Switch display units", "units <metric|imperial>", ["units imperial"],
         category="Session")
def cmd_units(ctx: Context, args: list[str]) -> CommandResult:
    if not args or args[0].lower() not in ("metric", "imperial"):
        raise UserError("units is metric or imperial", f"currently {ctx.units}")
    ctx.settings.units = args[0].lower()
    ctx.settings.save()
    return CommandResult(Text(f"Units: {ctx.settings.units}.", style="green"), data={"units": ctx.units})


@command("update", "Refresh airports + live METARs from the network", "update", ["update"],
         category="Session")
def cmd_update(ctx: Context, args: list[str]) -> CommandResult:
    from skyscope.data import sources
    from skyscope.data.store import update_airports
    from skyscope.data.weather import load_bulk

    with ctx.spinner("Downloading OurAirports data…"):
        update_airports()
    ctx._store = None
    with ctx.spinner("Downloading worldwide METARs…"):
        bulk = load_bulk(max_age_s=0)
    if bulk is None:
        raise UserError("METAR download failed", "airports were updated; try again later for weather")
    msg = f"Updated {ctx.store.size:,} airports and {len(bulk.frame):,} METARs ({sources.NETWORK_CALLS} downloads)."
    return CommandResult(Text(msg, style="green"), data={"airports": ctx.store.size, "metars": len(bulk.frame)})
