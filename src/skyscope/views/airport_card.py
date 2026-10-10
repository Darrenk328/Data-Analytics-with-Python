"""Airport card (open PHX) and weather view (wx PHX)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from skyscope.data.weather import Metar, WxLookup, describe
from skyscope.views import format as fmt
from skyscope.views.theme import FLIGHT_CAT_STYLE, page, panel, temp_style

TYPE_NAMES = {"large_airport": "Large airport", "medium_airport": "Medium airport",
              "small_airport": "Small airport", "heliport": "Heliport",
              "seaplane_base": "Seaplane base", "balloonport": "Balloonport", "closed": "Closed"}


def header(rec: dict[str, Any], utc_offset_s: int | None) -> Group:
    """Name, codes, place, type, elevation, local time, Wikipedia link."""
    codes = " · ".join(c for c in (rec.get("iata_code"), rec.get("icao_code") or rec.get("ident")) if c)
    title = Text()
    title.append(f"{rec['name']}", style="bold")
    title.append(f"  {codes}", style="code")
    place = ", ".join(p for p in (rec.get("municipality"), rec.get("region_name"), rec.get("country_name")) if p)
    now = datetime.now(timezone.utc)
    if utc_offset_s is not None:
        local = (now + timedelta(seconds=utc_offset_s)).strftime("%H:%M")
        tz = f"local {local} (UTC{utc_offset_s / 3600:+.0f})"
    else:  # solar time from longitude - approximate
        local = (now + timedelta(hours=rec["lon"] / 15)).strftime("%H:%M")
        tz = f"local ≈{local} (solar)"
    # (no flag emoji: regional-indicator pairs break panel borders in some terminals)
    line2 = Text(place, style="")
    line2.append(f"  ·  {TYPE_NAMES.get(rec['type'], rec['type'])}"
                 f"{' · scheduled service' if rec.get('scheduled') else ''}", style="muted")
    line3 = Text(f"Elevation {fmt.elevation(rec.get('elevation_ft'))}  ·  {tz}", style="muted")
    parts = [title, line2, line3]
    if rec.get("wikipedia_link"):
        parts.append(Text(rec["wikipedia_link"], style="dim underline"))
    return Group(*parts)


def weather_block(wx: WxLookup, units: str, da_ft: float | None) -> Group:
    """Right-now weather: flight-category badge, plain English, raw METAR dimmed, DA."""
    m = wx.metar
    if m is None:
        return Group(Text(wx.note or "No weather report available.", style="muted"))
    line = Text()
    if m.flight_category:
        line.append(f" {m.flight_category} ", style=FLIGHT_CAT_STYLE.get(m.flight_category, "reverse"))
        line.append("  ")
    line.append(fmt.temp(m.temp_c, units), style=f"bold {temp_style(m.temp_c)}")
    line.append(f" · {describe(m)}")
    sub = Text(f"observed {fmt.stamp(m.observed)} · {m.station}", style="muted")
    if m.altimeter_inhg:
        sub.append(f" · altimeter {m.altimeter_inhg:.2f} inHg", style="muted")
    if da_ft is not None:
        sub.append(f" · density altitude ≈{fmt.feet(da_ft)}", style="est")
    parts = [line, sub, Text(m.raw, style="dim")]
    if wx.note:
        parts.append(Text(wx.note, style="warn"))
    return Group(*parts)


def runways_table(runways: list[dict[str, Any]], units: str, active: str | None,
                  wind: tuple[float | None, float | None]) -> Table:
    """Runway list with wind components per end."""
    from skyscope.perf.wind import components

    table = Table(box=None, padding=(0, 1), header_style="bold", pad_edge=False)
    table.add_column("Runway", no_wrap=True, style="code")
    table.add_column("Length", justify="right", no_wrap=True)
    table.add_column("Surface", no_wrap=True)
    table.add_column("Wind (head/cross kt)", no_wrap=True)
    wdir, wspd = wind
    for rw in runways:
        comps = []
        for end, hdg in ((rw["le_ident"], rw["le_heading"]), (rw["he_ident"], rw["he_heading"])):
            if end and hdg is not None and wdir is not None and wspd:
                c = components(hdg, wdir, wspd)
                label = f"{end} {'+' if c.headwind >= 0 else '−'}{abs(c.headwind):.0f}/{abs(c.crosswind):.0f}"
                comps.append(label + (" ◀ active" if end == active else ""))
        name = rw["name"] + (" (closed)" if rw["closed"] else "")
        table.add_row(name, fmt.length(rw["length_ft"], units),
                      f"{rw['surface']}{'' if rw['lighted'] else ' · unlit'}",
                      "  ".join(comps) if comps else ("calm" if wspd == 0 else fmt.DASH))
    return table


def card(rec: dict[str, Any], wx: WxLookup, runways: list[dict[str, Any]], active: str | None,
         takeoff_line: Text | None, climate_line: RenderableType | None, units: str,
         utc_offset_s: int | None, da_ft: float | None, aircraft_label: str = "") -> RenderableType:
    """The full airport card: airport + weather, takeoff today, runways, climate."""
    m: Metar | None = wx.metar
    code = rec.get("code") or rec["ident"]
    top = panel(Group(header(rec, utc_offset_s), Text(""), Text("Right now", style="accent"),
                      weather_block(wx, units, da_ft)), f"{code} · Airport card")
    takeoff = panel(takeoff_line or Text("Performance not modelled here.", style="muted"),
                    f"Takeoff today{' · ' + aircraft_label if aircraft_label else ''}", "≈ estimate")
    rw_body: RenderableType = (runways_table(runways, units, active, (m.wind_dir, m.wind_kt) if m else (None, None))
                               if runways else Text("No runway data.", style="muted"))
    rw = panel(rw_body, f"Runways ({len(runways)})", "wind: + head / − tail, cross (kt)")
    climate = panel(climate_line, "Climate", "ERA5") if climate_line is not None else None
    return page(top, takeoff, rw, climate, hints=[f"takeoff {code}", f"heat {code}", f"wx {code}"])


def weather_view(code: str, wx: WxLookup, taf: str | None, units: str, da_ft: float | None) -> RenderableType:
    """Decoded METAR + raw TAF."""
    body: list[RenderableType] = [weather_block(wx, units, da_ft)]
    m = wx.metar
    if m is not None:
        t = Table(box=None, show_header=False, padding=(0, 1), pad_edge=False)
        t.add_column(style="muted")
        t.add_column()
        t.add_row("Temperature", f"{fmt.temp(m.temp_c, units)} (dew point {fmt.temp(m.dewpoint_c, units)})")
        t.add_row("Wind", "calm" if m.wind_kt == 0 else
                  f"{'variable' if m.wind_dir is None else f'{m.wind_dir:03.0f}°'} at {fmt.num(m.wind_kt)} kt"
                  + (f", gusts {m.gust_kt:.0f} kt" if m.gust_kt else ""))
        t.add_row("Visibility", f"{m.visibility or fmt.DASH} statute mi")
        t.add_row("Clouds", ", ".join(f"{c} {b:,} ft" if b else c for c, b in m.clouds) or "none reported")
        t.add_row("Altimeter", f"{m.altimeter_inhg:.2f} inHg" if m.altimeter_inhg else fmt.DASH)
        body += [Text(""), t]
    if taf:
        import re

        forecast: RenderableType = Group(*[Text(chunk, style="dim")
                                           for chunk in re.split(r"\s(?=FM\d|TEMPO|BECMG|PROB\d)", taf)])
    else:
        forecast = Text("No TAF available.", style="muted")
    return page(panel(Group(*body), f"Weather · {code}", "NOAA AWC METAR"),
                panel(forecast, "Forecast (TAF)"),
                hints=[f"takeoff {code}", f"runways {code}", f"open {code}"])


def runways_view(code: str, wind_text: str, runways: list[dict[str, Any]], units: str,
                 wind: tuple[float | None, float | None], hints: list[str]) -> RenderableType:
    """Runway list with wind components, in a panel."""
    body = Group(Text(f"Wind {wind_text}", style="bold"), runways_table(runways, units, None, wind))
    return page(panel(body, f"Runways · {code}", "+ head / − tail, then cross (kt)"), hints=hints)
