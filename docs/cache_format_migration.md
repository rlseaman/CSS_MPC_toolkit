# Cache Format Migration: CSV to Parquet

**Date:** 2026-03-28

## Background

The Planetary Defense Dashboard (`app/discovery_stats.py`) uses cached
query results to avoid hitting the MPC PostgreSQL database on every
startup.  Three large queries are run during `--refresh` (typically via
daily cron), and the results are written to hidden cache files in `app/`.
The app then loads these caches at startup and holds everything in memory.

Until today, all caches were stored as CSV.  This document records the
migration to Apache Parquet for the three large caches.

## Database Access Audit

A full review of how and when `mpc_sbn` is accessed across the project
identified two distinct patterns:

### Cached/refresh-only (daily, via `--refresh` or 24h TTL expiry)

These queries only run during cache generation.  The running app never
contacts the database for these:

| Query | Tables | Result size | Typical time |
|---|---|---|---|
| `LOAD_SQL` | obs_sbn, mpc_orbits, numbered_identifications, obscodes | ~43K rows | ~1 min |
| `APPARITION_SQL` | obs_sbn + joins | ~362K rows | ~1 min |
| `BOXSCORE_SQL` | mpc_orbits, numbered_identifications | ~1.5M rows | ~13 min |
| NEA.txt resolver | numbered_identifications | ~876K rows | ~1 s |
| PHA catalog | (downloads PHA.txt, queries numbered_identifications) | ~2.5K rows | seconds |
| SBDB MOID | (downloads from JPL API, queries numbered_identifications) | ~41K rows | seconds |

### Live/on-demand (per-request, process-cached)

| Module | Tables | Purpose |
|---|---|---|
| `lib/identifications.py` | numbered_identifications, current_identifications, mpc_orbits | Designation resolution |
| `lib/orbits.py` | mpc_orbits | Parameterized orbit queries |
| `lib/ades_export.py` | neocp_obs, neocp_obs_archive | ADES export (CLI only) |

### Not database access (external APIs only)

The MPEC browser tab, enrichment polling, and service health checks
query external HTTP APIs (SBDB, Sentry, NEOfixer, NEOCC, MPC website)
and never touch the PostgreSQL database.

## Cache File Inventory (pre-migration)

All files in `app/`, all CSV format:

| File | Size | Content |
|---|---|---|
| `.neo_cache_32e8951a.csv` | 9.4 MB | NEO discovery tracklets |
| `.apparition_cache_b5a21c5f.csv` | 47 MB | Apparition observations |
| `.boxscore_cache_ee6e794d.csv` | 176 MB | Full mpc_orbits catalog |
| `.nea_h_cache.csv` | 600 KB | NEA.txt H magnitude overrides |
| `.pha_cache.csv` | 23 KB | PHA designation set |
| `.sbdb_moid_cache.csv` | 648 KB | SBDB Earth MOID values |
| `.apparition_cache_7343c9f2.csv` | 31 MB | Orphaned (SQL hash changed) |
| `.mpec_cache/` (1,714 files) | 106 MB | Scraped MPEC text + nav |
| **Total** | **~370 MB** | |

The orphaned `_7343c9f2` file was left behind when `APPARITION_SQL`
changed, producing a new hash.  Safe to delete.

## Why Parquet over CSV

The decision criteria were **robustness** and **indefinite
maintainability**, not ecosystem trendiness.

### Parquet strengths

- **Self-describing format.** Schema (column names, types, nullability)
  is embedded in the file footer.  A Parquet file written today can be
  read in 2036 by any tool that speaks Parquet.
- **Stable specification.** Apache Parquet 2.x has been frozen for years.
  The format is versioned and backwards-compatible.
- **Built-in compression.** Default Snappy codec gives ~70-80% reduction
  over CSV with fast decompression.  Expected sizes:
  - Boxscore: 176 MB CSV -> ~35-50 MB Parquet
  - Apparition: 47 MB CSV -> ~10-15 MB Parquet
  - Neo cache: 9.4 MB CSV -> ~2-3 MB Parquet
- **Type preservation.** Datetime columns survive round-trip natively --
  no `parse_dates` needed on load.  Numeric precision is preserved
  without the CSV pitfalls of float-to-string-to-float conversion.
- **Corruption detection.** Checksummed; a corrupt file fails loudly
  rather than silently returning wrong data.
- **Broad tool support.** Readable by Python/pandas, DuckDB, R, Spark,
  PostgreSQL (via `COPY FROM`), and CLI tools (`parquet-tools`).

### Feather/Arrow (considered, not chosen)

- Faster raw load (~0.2s vs ~0.5-1s) but irrelevant for a once-at-startup
  load of a long-running app.
- Younger, still-evolving format spec (Arrow IPC) -- less confidence
  in decade-scale backwards compatibility.
- Narrower tool support outside Python/R.
- Uncompressed Feather is larger than Parquet; compressed Feather
  loses its speed advantage.

### CSV (what we're replacing)

- Human-readable (can `head`/`less` the file), but this is largely
  replaced by `python -c "print(pd.read_parquet('f').head())"` or
  DuckDB's CLI.
- No type preservation (everything is strings on disk).
- No compression.
- Silent corruption (truncated writes, encoding issues).

## Changes Made

### `requirements.txt`

Added `pyarrow>=15.0`.

### `app/discovery_stats.py`

**`_load_cached_query()`** (used by `LOAD_SQL` and `BOXSCORE_SQL`):
- Writes `.parquet` instead of `.csv` on refresh
- Reads with `pd.read_parquet()` on startup
- Falls back to legacy `.csv` if the Parquet file doesn't exist yet
  and the CSV cache is still fresh (smooth transition)

**`load_apparition_data()`** (separate cache logic for `APPARITION_SQL`):
- Same Parquet write/read with CSV fallback
- The `parse_dates` parameter is only used on the CSV fallback path;
  Parquet preserves datetime types natively

### Not changed

- **Small catalog caches** (`.nea_h_cache.csv`, `.pha_cache.csv`,
  `.sbdb_moid_cache.csv`): under 1 MB total, read into plain dicts
  not DataFrames.  Not worth the complexity.
- **MPEC text cache** (`.mpec_cache/`): scraped HTML, not tabular data.

## Deployment Sequence

1. `pip install pyarrow` in the venv (done)
2. Code changes applied (done)
3. Run `--refresh` to generate new Parquet caches from the database
4. Restart the app (a few seconds of Cloudflare 502)

Old CSV files remain on disk but are never read once Parquet versions
exist.  They can be cleaned up at any time.

## Observed Results (2026-03-28)

First Parquet refresh completed in ~14 minutes total:

| Query | Time (meta) | Duration | CSV size | Parquet size | Reduction |
|---|---|---|---|---|---|
| LOAD_SQL | 12:19 UTC | ~1 min | 9.4 MB | 3.9 MB | 59% |
| APPARITION_SQL | 12:20 UTC | ~1 min | 47 MB | 13 MB | 72% |
| BOXSCORE_SQL | 12:20 UTC | ~13 min | 176 MB | 85 MB | 52% |
| **Total (big 3)** | | **~14 min** | **232 MB** | **102 MB** | **56%** |

`BOXSCORE_SQL` is the slowest query despite being a simple SELECT +
LEFT JOIN, because it scans all ~1.5M rows in `mpc_orbits` (all object
classes, not just the ~43K NEOs).  The `APPARITION_SQL` query, which
hits `obs_sbn` (526M rows), is fast because its `CROSS JOIN LATERAL`
uses indexed lookups scoped to the ~43K NEO discovery set.

## Venv Fix (incidental)

The venv's `pip` script had a stale shebang pointing to
`/Users/seaman/Desktop/Claude/code/CSS_SBN_derived/venv/bin/python3.14`
(a different project's venv).  The Python symlink chain was correct,
only pip's wrapper was wrong.  Fixed by running
`python -m pip install --upgrade pip`, which regenerated the wrapper
with the correct shebang.
