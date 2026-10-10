# NOTES — deviations from PLAN.md and things learned from real data

Each entry: what the plan assumed → what reality is → what SkyScope does.

## Data sources

- **OurAirports `NA` values.** Namibia's ISO code is `NA` and North America's continent code
  is `NA`; pandas' default CSV reader turns both into NaN. → All CSVs are read with
  `keep_default_na=False` and only empty strings are treated as missing.
- **OurAirports columns** match the plan. Runways also carry `id`, per-end lat/lon/elevation
  and displaced thresholds; ~65% of runways have no `*_heading_degT`, so headings are derived
  from the runway ident (`09L` → 90°) as planned.
- **Surfaces** are free text with ~670 distinct spellings (`ASP`, `ASPH-G`, `CONC`, `PEM`,
  `TURF-F`, `GRS`, `PIÇARRA`, …). `normalize.py` maps them to paved / grass / gravel-dirt /
  water / unknown with ordered keyword rules.
- **airport-frequencies.csv** is not used by any view, so it is not bundled in the snapshot.
- **METAR JSON `altim` is in hectopascals**, not inHg (KPHX `A2971` → `"altim": 1006.2`).
  The bulk CSV has `altim_in_hg`. `weather.py` converts hPa → inHg for the JSON API.
- **Bulk METAR CSV has repeated column names** (`sky_cover`, `cloud_base_ft_agl` ×4). Pandas
  suffixes them `.1`, `.2`, `.3`; the decoder reads them in order. The bulk file carried
  ~5,000 stations when inspected (it holds reports from roughly the last hour or so, not
  "every station ever").
- **METAR `ids=ZZZZ` returns HTTP 204** with an empty body, as the plan says → "no report".
- **Open-Meteo accepts `elevation=`** on both the ERA5 archive and the climate API; SkyScope
  passes the airport's field elevation so temperatures are lapse-rate adjusted to the field
  rather than to the grid cell's mean height.
- **CMIP6 multi-model responses** use per-model suffixed keys (`temperature_2m_max_MRI_AGCM3_2_S`),
  as the plan suspected; occasional `null` values occur (e.g. one per series) and are skipped.

## Method

- **Delta-method reference period.** The plan says: compute each model's change from
  baseline 1951–1980 to future 2031–2050 and apply it to the recent ERA5 record (1996–2025).
  That double-counts the warming that already happened between 1951–1980 and 1996–2025
  (it is already in the recent ERA5 record). → SkyScope computes each model's change from
  **its own 1996–2025 to its 2031–2050** distribution and applies it to ERA5 1996–2025.
  The 1951–1980 baseline is still used for anomalies, the warming stripes, and the "unusually
  hot" percentile threshold. CMIP6 data is therefore only requested from 1991 onward, which
  also keeps the snapshot small and the API cheaper.
- The delta is applied per calendar month and per quantile (quantile delta mapping), so a
  model that warms hot days more than average days is represented.

## Dev environment

- On this macOS + Python 3.14 setup, the editable-install `.pth` file came out with the
  macOS `hidden` flag, and Python 3.14 skips hidden `.pth` files, so `import skyscope` failed
  after `pip install -e .`. Fix: `chflags nohidden .venv/lib/python3.*/site-packages/*.pth`.
  The flag is re-applied by the OS (the Desktop folder is synced), so for development here
  commands are run with `PYTHONPATH=src`; pytest sets `pythonpath = ["src"]` itself.

## Aircraft table

- Values were researched from manufacturer documents where readable (ATR 72-600 brochure,
  Embraer E175 spec sheet, Airbus A320 "Aircraft Characteristics" Rev 44). The Boeing
  airport-planning PDFs were too large to read in this environment, so Boeing weights and
  field lengths come from published spec tables that cite those documents (Wikipedia,
  ICAO/Boeing presentations) and are marked `approx = true` (shown as "≈" in the UI).
- The 737-800's 2,316 m field length is quoted for ISA+20 °C, so it likely overstates the ISA
  figure; SkyScope keeps it (conservative) and says so in `aircraft.toml` and `explain takeoff`.
- No maximum certified takeoff temperature could be confirmed for any type, so `max_oat_c` is
  omitted and the ABOVE LIMIT status never triggers with the current table.
- `flat_rate_dc` (15 °C) and `thrust_lapse` (1 %/°C) are the plan's model assumptions for every
  type, not manufacturer data.
- Thrust ∝ δ makes high-elevation airports very restrictive for big jets (e.g. a full
  777-300ER is restricted at any temperature at Mexico City). That matches the direction of
  real-world operations (MEX/BOG/LPB long-haul departures are weight-limited), but the exact
  numbers are estimates.
