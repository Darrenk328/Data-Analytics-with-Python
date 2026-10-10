# CLAUDE.md — SkyScope: Heat & Takeoff

The full build plan is in `PLAN.md`; deviations from it are recorded in `NOTES.md`.

## Rules for Claude Code

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

## Commands

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/python scripts/make_snapshot.py   # rebuild bundled offline data (network)
```
