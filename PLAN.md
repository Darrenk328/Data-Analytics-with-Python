# SkyScope: Heat & Takeoff — Build Plan for Claude Code

An interactive terminal app that explores the world's airports and asks one sharp question: how is a warming climate changing whether airplanes can take off fully loaded? Users find and filter 80k+ airports, read live weather, then see 85 years of heat history, today's takeoff limits, and 2050 projections for any airport and aircraft.

Drop this file into an empty repo as PLAN.md, and copy section 11 ("Rules for Claude Code") into CLAUDE.md. Build phase by phase; don't start a phase until the previous phase's acceptance checks pass.

## 1. Product concept

Judging criteria: data presentation, usability, functionality ("can someone do something useful with the data?").

The story: hot air is thin air. Thinner air means less lift and less engine thrust, so on hot days an airplane needs more runway. When it doesn't have enough, the airline must offload passengers, bags, or fuel ("weight restriction"). Peer-reviewed work (Coffel & Horton, Climatic Change, 2017) found 10–30% of flights departing at the daily temperature peak may need some weight restriction by mid-to-late century, with short-runway, hot, and high-elevation airports hit hardest. SkyScope lets anyone explore that at any airport.

| User question | Feature |
|---|---|
| "Find hot, high, or short-runway airports." | `find`, `filter`, `near` |
| "Tell me about Phoenix airport right now." | `open` → airport card with live weather |
| "Could a full 737 take off here today?" | `takeoff` (live METAR + performance model) |
| "How much hotter has this airport gotten since the 1950s?" | `heat` (85-year history, warming stripes) |
| "How many restricted days per year then, now, and by 2050?" | `takeoff --decades` |
| "At what temperature does this flight start losing passengers?" | `takeoff --sweep` |
| "Where in the world is takeoff restricted right now?" | `hotspots` |
| "Which airports are most exposed?" | `rank heat-risk` |
| "Compare Phoenix, Denver and Dubai." | `vs` (with climate rows) |
| "How does the model work? Can I trust it?" | `explain` |

Personality: clear and honest, never a wall of numbers. Every view leads with a one-line human summary ("On a day like today, a fully loaded 737-800 would leave ~6 passengers behind at PHX"), then details and visuals, then a dim "next steps" hint line. Every modeled number is visibly labeled as an estimate.

## 2. Data sources (all free, no API key)

### 2.1 OurAirports — airports & runways (public domain, nightly)

Base: https://davidmegginson.github.io/ourairports-data/ → airports.csv, runways.csv, airport-frequencies.csv, countries.csv, regions.csv.

Expected columns (VERIFY against real headers first):

- airports: id, ident, type, name, latitude_deg, longitude_deg, elevation_ft, continent, iso_country, iso_region, municipality, scheduled_service, icao_code, iata_code, gps_code, local_code, home_link, wikipedia_link, keywords
- runways: airport_ref, airport_ident, length_ft, width_ft, surface, lighted, closed, le_ident, le_heading_degT, he_ident, he_heading_degT, ...

Data cleaning: normalize messy surface text into paved / grass / gravel-dirt / water / unknown; derive missing headings from idents (09 → 90°); never display nan; hide closed airports by default. Elevation and runway length are core model inputs — flag airports where they are missing and exclude them from performance calculations with a visible note.

### 2.2 NOAA Aviation Weather Center — live observations (no key)

- Bulk: https://aviationweather.gov/data/cache/metars.cache.csv.gz — all current METARs worldwide, refreshed every minute. Powers hotspots, map colouring, and badges.
- Single: https://aviationweather.gov/api/data/metar?ids=KPHX&format=json
- TAF: https://aviationweather.gov/api/data/taf?ids=KPHX&format=json
- Rules: custom User-Agent, ≤100 req/min, cache ≥5 min, HTTP 204 = "no report" (not an error), max 400 results per request.
- Use METAR temperature and altimeter setting for live density altitude. Record real responses into tests/fixtures/ and code against observed field names.

### 2.3 Open-Meteo Historical (ERA5 reanalysis) — 1940 → 2 days ago (no key)

`https://archive-api.open-meteo.com/v1/archive?latitude=..&longitude=..&start_date=1940-01-01&end_date=<today-2>&daily=temperature_2m_max,temperature_2m_mean&timezone=auto`

One call per airport returns ~85 years of daily data. Cache permanently (history doesn't change); only append new days on refresh.

Caveat to surface in explain: ERA5 is a ~9–25 km gridded reanalysis, not the runway thermometer; it can read a little cooler/warmer than the airport sensor.

### 2.4 Open-Meteo Climate API (CMIP6 HighResMIP) — 1950 → 2050 (no key)

`https://climate-api.open-meteo.com/v1/climate?latitude=..&longitude=..&start_date=1950-01-01&end_date=2050-01-01&models=<list>&daily=temperature_2m_max`

Models: CMCC_CM2_VHR4, FGOALS_f3_H, HiRAM_SIT_HR, MRI_AGCM3_2_S, EC_Earth3P_HR, MPI_ESM1_2_XR, NICAM16_8S. VERIFY the response shape (multi-model responses use per-model suffixed keys; check before parsing).

Scenario is close to RCP8.5/high-emissions; data ends 2050. State both facts in the UI.

Do not splice raw model output onto ERA5. Use the delta method: for each model, compute the change in the temperature distribution between baseline (1951–1980) and future (2031–2050), apply that shift to the recent ERA5 record (1996–2025), and report the multi-model median with min–max spread.

Fair use: free tier is ~10k calls/day, and long multi-model requests may count as several calls. Cache permanently.

### 2.5 Offline reliability (critical for judging)

scripts/make_snapshot.py builds a bundled snapshot in src/skyscope/snapshot/:

- gzipped OurAirports CSVs,
- a timestamped bulk METAR sample,
- ERA5 + CMIP6 climate caches for ~22 showcase airports: hot (PHX, LAS, DFW, IAH, DXB, DOH, KWI, RUH, DEL, BKK), high (DEN, MEX, BOG, UIO, LPB, ADD, NBO, JNB), and contrast/control (LHR, JFK, SIN, OSL).

Load order: user cache → bundled snapshot. `--offline` disables all network calls and shows a clear notice on live features. Climate for non-showcase airports is fetched on demand (with spinner) and then cached.

## 3. The takeoff performance model (heart of the app)

Keep it simple, physically grounded, transparent, and unit-tested. It is an educational estimate, not an Airplane Flight Manual. Put it in pure functions in perf/ with no I/O.

### 3.1 Atmosphere

- Pressure altitude: PA_ft = elevation_ft + (29.92 − altimeter_inHg) × 1000 (use altimeter = 29.92 when unknown, e.g. climate data).
- ISA temperature at PA: T_isa = 15 − 0.0019812 × PA_ft (°C).
- Density altitude: DA_ft = PA_ft + 118.8 × (OAT − T_isa).
- Density ratio: σ = (1 − 6.8756e-6 × DA_ft) ^ 4.2559.
- Pressure ratio: δ = (1 − 6.8756e-6 × PA_ft) ^ 5.2559.

### 3.2 Takeoff distance scaling

Ground roll scales as s ∝ V² / a, where V² ∝ W/σ (lift) and a ∝ T/W (thrust), so:

    TODR(W) = TODR_ref × (W / MTOW)² / (σ × τ)

- TODR_ref = published takeoff field length at MTOW, sea level, ISA.
- τ = thrust ratio = δ × flat(OAT), where jets are flat-rated: flat = 1 if OAT ≤ T_isa + ΔT_flat, else 1 − λ × (OAT − (T_isa + ΔT_flat)). Defaults: ΔT_flat = 15 °C, λ = 0.01 /°C (≈1% thrust per °C above flat rating), overridable per aircraft type. Turboprops use the same form with their own params.

### 3.3 Weight restriction for runway length R

    W_allow = min(MTOW, MTOW × sqrt(R × σ × τ / TODR_ref))
    restriction_kg = MTOW − W_allow
    passengers_lost ≈ restriction_kg / 100   (passenger + bag; configurable)

Status levels: OK (no restriction) · RESTRICTED (show kg, % and passengers) · SEVERE (restriction exceeds max payload, so the mission isn't viable) · ABOVE LIMIT (OAT above the type's max certified operating temperature, if known).

Default runway = airport's longest open paved runway; `--runway 08` overrides.

Also compute the threshold temperature: the OAT at which restriction begins (solve numerically with bisection). This is the single most intuitive number in the app ("At PHX a full A320neo starts losing payload above 44 °C").

### 3.4 Aircraft table (src/skyscope/perf/aircraft.toml)

Fields per type: id, name, category (turboprop|regional|narrowbody|widebody), mtow_kg, oew_kg, max_payload_kg, tofl_ref_m, flat_rate_dc, thrust_lapse, max_oat_c (optional), source.

Initial types: ATR 72-600, Embraer E175, Airbus A320neo, Boeing 737-800, Boeing 787-9, Boeing 777-300ER. Fill values from manufacturer airport-planning documents (Airbus "Aircraft Characteristics – Airport and Maintenance Planning"; Boeing "Airplane Characteristics for Airport Planning") and record the source per row. If a value can't be sourced, mark it approx = true; the UI shows "≈" next to results for that type. Never present invented numbers as official.

### 3.5 Required sanity tests

- Sea level, ISA, runway = TODR_ref → restriction ≈ 0.
- Restriction increases monotonically with temperature and elevation, and decreases with runway length.
- A hot, high, short-runway case is restricted; a cool, sea-level, long-runway case is not.
- Threshold-temperature solver round-trips with the restriction function (±0.1 °C).
- σ at DA 0 = 1.0; σ at DA 10,000 ft ≈ 0.738.

## 4. Climate metrics (computed in climate/metrics.py)

Per airport, from daily Tmax (ERA5 history; delta-method future):

- Warm-season Tmax: annual mean of daily max for the hottest 3 consecutive months (detect per airport, so hemispheres and tropics work automatically).
- Hot days: days ≥ the airport's own 1951–1980 95th-percentile Tmax ("unusually hot for this airport"), plus days ≥ an absolute threshold (default 35 °C).
- Peak density altitude: from daily Tmax and field elevation.
- Restricted days/year per aircraft type at the chosen runway, plus mean payload lost on those days (in kg and passengers). Daily Tmax ≈ the worst departure of the day, the same framing as the published study; state that departures at cooler hours fare better.
- Periods: decades from the 1940s, plus baseline 1951–1980, recent 1996–2025, and projected 2031–2050 (median and model spread).
- Trend: linear slope (°C/decade) on warm-season Tmax with a simple t-statistic (numpy; no scipy needed). Say "clear trend" vs "noisy / not distinguishable".

## 5. Tech stack

Python 3.10+, typer (entry + one-shot commands), rich (all rendering), prompt_toolkit (interactive shell), pandas + numpy, rapidfuzz (fuzzy search), httpx (HTTP), platformdirs (cache/config), tomli on 3.10 (aircraft table). Optional: plotext for line charts, wrapped behind views/charts.py with a pure-Rich fallback (plotext isn't actively maintained). Dev: pytest, ruff.

Console script: `skyscope = skyscope.cli:app`. Running `skyscope` with no args opens the shell.

## 6. Repository layout

```
skyscope/
├── pyproject.toml   README.md   CLAUDE.md   NOTES.md
├── scripts/make_snapshot.py
├── src/skyscope/
│   ├── cli.py                  # Typer: one-shot commands, --json, --offline, --debug
│   ├── config.py               # paths, settings, units, favourites
│   ├── data/
│   │   ├── sources.py          # URLs, downloads, cache freshness, offline flag
│   │   ├── store.py            # DataStore: load/clean/join airports+runways (pickle cache)
│   │   ├── normalize.py        # surfaces, headings, nulls
│   │   ├── search.py           # fuzzy + exact-code search, ranking
│   │   ├── filters.py          # "country=US elevation>5000 runway<8000" parser
│   │   ├── geo.py              # haversine, bearing, bbox, compass words
│   │   └── weather.py          # METAR single/bulk, decode, flight category, TAF
│   ├── perf/
│   │   ├── atmosphere.py       # PA, ISA, DA, σ, δ
│   │   ├── takeoff.py          # TODR, W_allow, status, threshold temp
│   │   ├── aircraft.py         # load/validate aircraft.toml
│   │   ├── aircraft.toml
│   │   └── wind.py             # headwind/crosswind per runway end
│   ├── climate/
│   │   ├── history.py          # ERA5 fetch + cache
│   │   ├── projections.py      # CMIP6 fetch + cache, delta method
│   │   └── metrics.py          # warm season, hot days, restricted days, trends
│   ├── shell/
│   │   ├── repl.py  registry.py  commands.py  completer.py  context.py
│   ├── views/
│   │   ├── theme.py  format.py  results.py  airport_card.py  weather_view.py
│   │   ├── takeoff_view.py     # today's verdict, sweep curve, decades table
│   │   ├── heat_view.py        # warming stripes, trend chart, hot-day bars
│   │   ├── hotspots_view.py    # live global restriction list + map
│   │   ├── rank_view.py  compare_view.py  charts.py  braille_map.py
│   │   └── help_view.py        # help, explain, tour
│   └── snapshot/               # generated bundled data
└── tests/
    ├── fixtures/               # tiny CSVs, metar.json, metars.csv, era5.json, cmip6.json
    └── test_atmosphere.py  test_takeoff.py  test_metrics.py  test_search.py
        test_filters.py  test_weather.py  test_wind.py  test_commands.py
```

Architecture rule: data/perf/climate layers never print; views never fetch. Commands are thin glue. Every view returns a Rich renderable, tested by rendering to `Console(record=True, width=100)`.

## 7. Interactive shell

### 7.1 Launch screen

```
$ skyscope
  ✈  SKYSCOPE · Heat & Takeoff
  84,512 airports · live weather updated 2 min ago · climate data 1940–2050

  Right now: a fully loaded 737-800 would be weight-restricted at 17 airports
  worldwide — hottest: Kuwait (KWI) 47°C.   → type  hotspots

  Try:  open PHX  ·  takeoff PHX  ·  heat PHX  ·  rank heat-risk  ·  tour
  help for all commands · Tab to autocomplete · ↑ for history

skyscope ›
```

The launch headline is computed live from the bulk METAR + performance model (falls back to the snapshot with its timestamp). Startup target < 1.5 s on a warm cache.

The prompt shows context (`skyscope [KPHX · 737-800] ›`), so takeoff, heat, wx work with no arguments. `aircraft <id>` sets the session's default aircraft.

### 7.2 Commands

| Command | Aliases | Purpose | Example |
|---|---|---|---|
| find <text> | search, bare text | fuzzy search | find phoenix |
| filter <expr> | where | structured filter, refines current results | filter elevation>6000 type=large |
| open <n\|code> | o | airport card | open 2 |
| wx [code] | weather | decoded METAR + TAF | wx KPHX |
| runways [code] | rwy | runways + wind components | rwy |
| takeoff [code] [--aircraft] [--runway] [--temp] [--sweep] [--decades] | to | performance verdicts | to PHX --decades |
| heat [code] | climate | 1940–2050 heat history | heat DXB |
| hotspots [--aircraft] | | where restriction is happening right now | hotspots --aircraft A320neo |
| rank <metric> [in <area>] | top | leaderboards | rank heat-risk in US |
| vs <A> <B> [C] [D] | compare | side-by-side incl. climate rows | vs PHX DEN DXB |
| near [code\|lat,lon] [nm] | | nearby airports | near 40.35,-74.66 50 |
| map [filter] [--weather\|--risk] | | braille map | map --risk |
| aircraft [id] | ac | list types / set default | ac 787-9 |
| explain [takeoff\|climate\|data] | why | model + caveats in plain English | explain takeoff |
| export <csv\|json\|md> [file] | | export last result | export csv risk.csv |
| fav [code] / favs | | favourites (persisted) | |
| units <metric\|imperial> | | display units | |
| back · help [cmd] · tour · quit | | | |

Metrics for rank: heat-risk (projected restricted days/yr for the default aircraft in 2031–2050), warming (°C change baseline→recent), threshold (lowest threshold temperature, i.e. most fragile), density-altitude (peak DA today), elevation, runway, shortest-runway (scheduled-service only). Climate-based ranks run over cached airports (showcase + anything the user has opened) and say so in the header; live ranks (density-altitude, hotspots) cover every airport with a current METAR.

### 7.3 Filter language

key=value, key=v1,v2, key>=n, key<n, key~text, AND-ed with spaces. Keys: country, region, continent, type, runway, surface, elevation, service, iata, name, city. Friendly aliases (type=big, country=Iceland, runway>=3km, elevation>2000m). Unknown key → "did you mean" via rapidfuzz. Breadcrumb shows the refinement chain; `filter clear` resets.

### 7.4 Usability guarantees

- Never show a traceback; catch at the REPL boundary, print a one-line message + hint, log details to the cache dir (`--debug` shows tracebacks).
- Every "not found" suggests close matches.
- Every view ends with 2–3 suggested next commands.
- Long fetches show a spinner and are cancellable with Ctrl-C (cancels the command, not the app).
- Works at 80 columns, honors NO_COLOR, and prints plain text when not a TTY.

## 8. Key views

### 8.1 Airport card (open PHX)

Header (name, codes, city, flag, type, elevation, local time, Wikipedia link) · Right now (flight-category badge, plain-English weather, raw METAR dimmed, density altitude) · Takeoff today mini-verdict for the session aircraft · Runways (table + likely active runway from wind) · Climate snapshot (one-row warming stripes + "+2.1 °C warm-season highs since the 1950s") · hint line.

### 8.2 Takeoff (takeoff PHX)

- Verdict panel: status colour, "≈6 passengers / 610 kg offloaded" or "No restriction", using live OAT (or --temp), runway used, DA, and threshold temperature with margin ("restriction begins at 44 °C; today is 41 °C, 3 °C of margin").
- All aircraft table: one row per type with status, restriction, and threshold temp, so users can see that small turboprops and widebodies behave differently.
- --sweep: chart of allowed weight (or passengers lost) vs temperature from 20–50 °C, with today's temperature and the record high marked.
- --decades: restricted days/yr per decade as horizontal bars (1950s → 2010s → recent → 2031–2050 projected with spread whisker), plus the headline ("restricted days have roughly tripled since the 1960s; models project ~2× more by the 2040s").

### 8.3 Heat (heat DXB)

- Warming stripes: one coloured block per year (1940→now), blue→red scale on warm-season Tmax anomaly vs 1951–1980, then a dimmer projected segment to 2050.
- Line chart of warm-season Tmax with trend line and slope label.
- Hot-day counts by decade (bars) and the airport's record hottest day.
- Plain-language summary + caveats footnote (ERA5 grid vs runway sensor; projections are high-emissions, end 2050).

### 8.4 Hotspots (hotspots)

From bulk METARs joined to airports with scheduled service: every airport where the chosen aircraft is restricted right now, sorted by severity, plus a braille world map with restricted airports in red/orange. Headline: "17 airports restricting a full 737-800 right now; 12 of them are in the Middle East and South Asia."

### 8.5 Rank, compare, map

- rank: table with inline bars scaled to the top value + one-line headline fact.
- vs: per-airport columns; rows include elevation, longest runway, today's temperature and DA, threshold temp, warming since the 1950s, restricted days now vs 2040s; best per row highlighted; verdict line.
- map: custom braille canvas (2×4 dots per cell, equirectangular, auto-fit). Plotting all airports as a dim background draws the continents with no map dataset. Layers: results, --weather (flight category colours), --risk (live restriction colours).

### 8.6 Explain (explain takeoff)

A short, readable page: the physics in three sentences, the formulas from section 3, the aircraft parameters in use with sources and "≈" flags, and what the model ignores (wind, runway slope and contamination, obstacles, flap settings, reduced-thrust policies, actual loads). This is a credibility feature; judges will look for it.

## 9. One-shot (scriptable) mode

```
skyscope takeoff PHX --aircraft 737-800 --json
skyscope heat DXB
skyscope hotspots --aircraft A320neo
skyscope rank heat-risk --limit 10
skyscope filter "elevation>6000 type=large" --json
skyscope update            # refresh airports + METARs
```

`--json` emits machine-readable output. Shell and one-shot share implementations via registry.py.

## 10. Build phases & acceptance checks

Priority note: Phases 0–6 are a complete, strong submission. Phases 7–8 are polish.

### Phase 0 — Scaffold
pyproject, layout, Typer entry, echo REPL, ruff/pytest config, make_snapshot.py (airports + METAR sample; climate added in Phase 5).
✅ `pip install -e .`, `skyscope --help`, `pytest` all work.

### Phase 1 — Airport data layer
sources.py, store.py, normalize.py, geo.py. Join longest open paved runway and runway count onto airports.
✅ Haversine JFK→LHR ≈ 2,999 nm (±1%). ✅ No nan in display fields. ✅ Warm load < 1 s.

### Phase 2 — Search, filter, shell core
Ranking: exact IATA > ICAO/ident > name/city prefix > fuzzy; boost large > medium > small. Registry, REPL, completer, context, results table, help, back.
✅ `find phoenix` → PHX first; `find "new york"` → JFK/LGA/EWR near top; `filter country=Bolivia elevation>10000` works; typos give suggestions; junk-input fuzz list produces no tracebacks.

### Phase 3 — Performance model (pure + tested)
atmosphere.py, takeoff.py, aircraft.py + aircraft.toml (sourced values), wind.py.
✅ All section 3.5 tests pass. ✅ Wind: rwy 22, wind 220@10 → headwind 10, crosswind 0; 040@10 → tailwind 10.

### Phase 4 — Live weather, airport card, takeoff today
weather.py (single + bulk + decode), airport_card.py, weather_view.py, takeoff_view.py (verdict, all-aircraft table, --temp, --sweep).
✅ Card renders at 80 and 120 cols for a large airport, a no-METAR grass strip, and a heliport (performance section hidden with a note). ✅ `takeoff PHX --temp 48` shows a restriction; `--temp 15` shows none.

### Phase 5 — Climate
history.py, projections.py (delta method), metrics.py, heat_view.py, takeoff --decades. Extend make_snapshot.py to bundle the ~22 showcase airports.
✅ `heat PHX` offline from snapshot in < 1 s. ✅ Metrics tests on a synthetic series (known trend recovered; percentile thresholds correct; hemisphere-aware warm season works for JNB and SIN). ✅ Projection shows median + spread and the "high-emissions, to 2050" label.

### Phase 6 — Hotspots, rank, compare, map
✅ hotspots runs over the bulk METAR in < 2 s. ✅ `rank heat-risk` lists cached airports with header note. ✅ `vs PHX DEN DXB` highlights best per row. ✅ map shows a recognizable world; --risk colours restricted airports.

### Phase 7 — Polish
explain, export, favourites, units, near, --json everywhere, launch headline. tour: scripted 7 steps, pausing for Enter, one-line narration each: find phoenix → open 1 → takeoff → takeoff --sweep → heat → takeoff --decades → hotspots. README: install, 60-second quick-start, screenshots (vhs/asciinema), and the data credits: OurAirports (public domain), NOAA AWC (US public data), Open-Meteo (CC BY 4.0; "Weather data by Open-Meteo.com"), ERA5 (Copernicus/ECMWF), CMIP6 HighResMIP, and a citation of Coffel & Horton (2017) for the motivating research.

### Phase 8 — Final QA
- Fresh venv install works; first run with no network uses the snapshot.
- Every help example works as written.
- 80-col layout clean; NO_COLOR=1 readable; --offline makes zero network calls.
- pytest green, ruff check clean.
- Every modeled number in the UI carries an "estimate" label or "≈".
- A new user can answer "Could a full 737 take off from Denver today, and how often will it be restricted by the 2040s?" in ≤3 commands.

## 11. Rules for Claude Code (copy into CLAUDE.md)

- Build in phase order. After each phase run pytest and ruff check, fix failures, then summarise what works before continuing.
- Inspect real data before coding against it: print CSV headers, save real METAR, ERA5 and CMIP6 responses to tests/fixtures/. Never invent field names.
- Aircraft parameters must come from cited manufacturer documents; mark anything unsourced approx = true. Never present invented numbers as official.
- data/perf/climate layers never print; views never do I/O; commands are thin glue.
- All network calls: 10 s timeout, custom User-Agent, caching, friendly error panels, respect --offline, never crash.
- Display: no nan/None (use —), thousands separators, units always labelled, UTC times with "Z" plus relative age, modeled values marked as estimates.
- Don't splice CMIP6 output directly onto ERA5; use the delta method in section 2.4.
- Keep the bundled snapshot under ~15 MB compressed; never commit raw uncompressed CSVs.
- Type hints throughout; docstrings on public functions; clarity over cleverness.
- If anything in this plan conflicts with real data or API behaviour, follow reality and record the deviation in NOTES.md.
