# ✈ SkyScope: Heat & Takeoff

**Hot air is thin air.** On hot days an airplane needs more runway. When there isn't enough,
the airline has to leave passengers, bags or fuel behind (a "weight restriction"). SkyScope is
an interactive terminal app that lets anyone explore that at any of the world's 86,000
airports. It combines live weather, 85 years of temperature history and 2050 climate
projections.

> ⚠️ **Estimates, not a flight manual.** SkyScope uses a simple, physically grounded,
> unit-tested model (PLAN.md §3) for education and exploration. It is not an Airplane Flight
> Manual calculation and must never be used for real flight planning. Every modelled number is
> marked "≈" or "estimate".

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/Darrenk328/Data-Analytics-with-Python.git skyscope
cd skyscope
python -m venv .venv
source .venv/bin/activate
pip install -e .            # or: pip install -e ".[dev]" for pytest + ruff
```

Airport data, a METAR sample and climate history for 8 showcase airports (PHX, DFW, IAH, DXB,
DOH, KWI, DEL, BKK; projections for PHX, DFW, DOH) are bundled, so
SkyScope works on first run with no network (`--offline` guarantees zero network calls).

## Run

```bash
skyscope            # interactive shell: Tab completes, ↑ recalls history, `help` lists commands
skyscope --help     # one-shot commands
```

## 60-second quick start

```text
skyscope › find phoenix               # fuzzy search; PHX first
skyscope › open 1                     # airport card: live weather, takeoff today, runways, climate
skyscope › takeoff                    # could a full 737-800 take off right now?
skyscope › takeoff --temp 48          # what-if: a 48 °C afternoon
skyscope › takeoff --sweep            # passengers lost vs temperature, 20–50 °C
skyscope › heat                       # 1940→today warming stripes, trend, hot days, 2050 projection
skyscope › takeoff --decades          # restricted days/yr per decade → 2031–2050
skyscope › aircraft A320neo           # change the session aircraft
```

"Could a full 737 take off from Phoenix today, and how often will it be restricted by the
2040s?" takes one command: `takeoff PHX --decades`.

## Example commands

| Command | What it does |
|---|---|
| `find "new york"` | Search by name, city, code or keyword (typos OK) |
| `filter country=Bolivia elevation>10000` | Structured filter; refines current results (`back`, `filter clear`) |
| `filter type=big runway>=4km elevation>2000m` | Friendly units and aliases |
| `open PHX` | Airport card |
| `wx KPHX` | Decoded METAR + TAF |
| `runways DFW` | Runways with headwind/crosswind components |
| `takeoff PHX --aircraft 787-9 --runway 07L` | Verdict for a specific type and runway, plus all six types |
| `takeoff PHX --temp 48 --sweep` | What-if temperature and sweep chart |
| `takeoff PHX --aircraft 787-9 --decades` | Restricted days/yr: 1940s → 1996–2025 → 2031–2050 (median + model range) |
| `heat DOH` | Heat history and projection |
| `vs PHX DOH DFW` | Side-by-side comparison: best value per row in green, one-line verdict |
| `vs PHX DFW --aircraft 787-9` | Compare for a different aircraft type |
| `aircraft` | Aircraft table with sources (≈ = not confirmed in a manufacturer document) |
| `units imperial` | °F / ft / lb |

One-shot and scriptable, the same commands work from your shell. Add `--json` for
machine-readable output:

```bash
skyscope takeoff PHX --aircraft 737-800 --json
skyscope heat DOH
skyscope filter "elevation>6000 type=large" --json
skyscope update     # refresh airports + METARs from the network
```

## How the model works (short version)

- Atmosphere: pressure altitude from field elevation and altimeter, then density altitude,
  density ratio σ and pressure ratio δ.
- Takeoff distance ∝ (W/MTOW)² / (σ·τ), where τ = δ × a flat-rating factor (full thrust up to
  ISA+15 °C, then −1 %/°C).
- Allowable weight = MTOW × √(runway·σ·τ / reference field length), capped at MTOW. The
  shortfall is the restriction, shown in kg and as ≈passengers at 100 kg each including bags.
- Threshold temperature: the temperature at which the restriction begins (bisection).
- Climate: ERA5 daily maxima give restricted days per year (each day's max is the worst
  departure of the day). Future days come from the delta method: each CMIP6 model's
  1996–2025 → 2031–2050 change, per month and per quantile, is added to the observed record.
  Output is the multi-model median with min–max range.

The model ignores wind, runway slope and contamination, obstacles, flap settings,
reduced-thrust policies and actual loads. Aircraft inputs and their sources are in
`src/skyscope/perf/aircraft.toml`. Deviations from the plan and data quirks are in `NOTES.md`.

## Development

```bash
pip install -e ".[dev]"
pytest              # model sanity tests, metrics on synthetic series, search/filter, commands
ruff check .
python scripts/make_snapshot.py               # rebuild bundled data (network)
python scripts/make_snapshot.py --only-climate --no-cmip6
```

## Troubleshooting

**`ModuleNotFoundError: No module named 'skyscope'` on macOS after `pip install -e .`**

If the project is in a synced folder (Desktop or Documents with iCloud), macOS can mark the
venv's editable-install `.pth` file as hidden, and Python 3.14+ skips hidden `.pth` files.
Either:

- run with the source folder on the path:

  ```bash
  PYTHONPATH=src python -m skyscope
  ```

- or create the venv outside the Desktop/iCloud folder:

  ```bash
  python -m venv ~/venvs/skyscope
  ~/venvs/skyscope/bin/pip install -e .
  ```

  Then activate it with `source ~/venvs/skyscope/bin/activate`.

## Data credits

- **Airports and runways:** [OurAirports](https://ourairports.com/data/) (public domain).
- **Live weather (METAR/TAF):** [NOAA Aviation Weather Center](https://aviationweather.gov/)
  (US government public data).
- **Weather data by [Open-Meteo.com](https://open-meteo.com/)** (CC BY 4.0):
  - historical reanalysis **ERA5** (Copernicus Climate Change Service / ECMWF);
  - climate projections **CMIP6 HighResMIP** (CMCC-CM2-VHR4, FGOALS-f3-H, HiRAM-SIT-HR,
    MRI-AGCM3-2-S, EC-Earth3P-HR, MPI-ESM1-2-XR, NICAM16-8S). The scenario is close to
    high-emissions (RCP8.5-like), and the data ends in 2050.
- **Aircraft parameters:** ATR 72-600 brochure, Embraer E175 specification sheet, Airbus A320
  "Aircraft Characteristics – Airport and Maintenance Planning"; Boeing values from published
  tables citing Boeing "Airplane Characteristics for Airport Planning" (marked ≈).
- **Motivating research:** Coffel, E. & Horton, R. (2017). *Climate change and the impact of
  extreme temperatures on aviation.* Climatic Change, 144, 381–388.
  https://doi.org/10.1007/s10584-017-2018-9

## Status

Phases 0–5 of `PLAN.md` are built: data layer, search and filters, the shell, the
performance model, live weather, the airport card, takeoff verdicts and sweep, and climate
history with projections, plus `vs` (compare). Hotspots, rank, map, explain, export and
the tour (Phases 6–7) are not built yet.
