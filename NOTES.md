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
