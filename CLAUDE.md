# Claude Code Project Guide

## Project Overview

CSS SBN Derived Data Products — SQL scripts, Python libraries, and
interactive applications for deriving value-added datasets from the MPC
(Minor Planet Center) PostgreSQL database, maintained by the Catalina Sky
Survey at the University of Arizona.

## Database Access

- **Host:** `sibyl` (RHEL 8.6, 251 GB RAM, HDD)
- **Database:** `mpc_sbn` — PostgreSQL 15.2, logical replication from MPC
- **Connect:** `psql -h sibyl -U claude_ro mpc_sbn`
- **Python:** `from lib.db import connect, timed_query`
- **Credentials:** `~/.pgpass` (readonly role `claude_ro`)

### Critical Performance Rules

- **obs_sbn has 526M+ rows (239 GB)** — NEVER run unfiltered COUNT,
  COUNT(DISTINCT), or full-table scans. Always use indexed lookups.
- **Indexed columns on obs_sbn:** obsid, permid, provid, stn, trkid,
  trksub, trkmpc, obstime, created_at, updated_at, submission_block_id
- **No foreign keys** anywhere in the schema — all joins use text field
  matching; referential integrity is unenforced

### Key Data Quirks

- **mpc_orbits** (1.51M rows): cometary elements (q,e,i) for ALL rows,
  but Keplerian (a, period) for only 43%. Always derive
  `a = q/(1-e)` when e<1. See `lib/orbits.py` DERIVED_COLUMNS.
- **orbit_type_int is NULL for 35%** — use `classify_from_elements()`
  in `lib/orbit_classes.py` to recover 99.2%
- **earth_moid NULL for 70%** of mpc_orbits
- **CAST(jsonb_text AS numeric)** returns Python Decimal — use
  `::double precision` in SQL for pandas compatibility
- **`orbit_quality` in JSONB is text** ("good", etc.) — don't CAST to
  numeric

## Project Structure

```
app/                          # Interactive Dash web application
  discovery_stats.py          #   NEO discovery explorer (main app)
  assets/                     #   CSS, logo, static files
lib/                          # Python library layer
  db.py                       #   DB connections, timed queries, QueryLog
  orbits.py                   #   Parameterized query builders for mpc_orbits
  orbit_classes.py            #   Classification constants, Tisserand, colors
  mpc_convert.py              #   80-col format converters, designation pack/unpack
  ades_export.py              #   ADES XML/PSV generation from NEOCP data
  ades_validate.py            #   XSD validation
sql/                          # SQL scripts
  discovery_tracklets.sql     #   Main NEO discovery statistics (43,629 tracklets)
  css_utilities_functions.sql #   PostgreSQL equivalents of Python converters
  ades_export.sql             #   ADES-ready columns from NEOCP
  viz/                        #   Reference queries for visualization
scripts/                      # Operational tools
  run_pipeline.sh             #   Execute SQL, validate, upload discovery tracklets
  db_health_check.sh          #   Diagnostic: replication, dead tuples, indexes
notebooks/                    # Jupyter Lab exploration (strip outputs before commit)
  01_query_profiling.ipynb
  02_orbital_elements.ipynb
  03_data_quality.ipynb
schema/                       # ADES format XSD schemas
  general.xsd, submit.xsd
docs/                         # Source tables, band corrections
sandbox/                      # Analysis notes, exploratory outputs
```

## Interactive App (`app/discovery_stats.py`)

Dash web application at http://127.0.0.1:8050/ with two tabbed pages:

### Tab 1: Discovery by Year
- Stacked bar chart of NEO discoveries by year/survey
- Grouping: Combined, by Project (CNEOS definitions), or by Station
- Size class filtering with "Split sizes" mode (viridis-colored
  stacking by H magnitude bin)
- Annual or cumulative views
- Secondary row: size distribution histogram + top-15 stations table

### Tab 2: Size Distribution vs. NEOMOD3
- Half-magnitude bin chart comparing MPC discoveries to NEOMOD3
  population model (Nesvorny et al. 2024, Icarus 411)
- Undiscovered remainder bars, completeness curve with 1-sigma errors
- Differential or cumulative modes
- NEOMOD3 reference table with per-bin completeness

### Shared Banner Controls
- CSS logo (linked to catalina.lpl.arizona.edu) at upper left
- Group by, Plot height, and Theme toggle in the banner
- CSS custom properties for dark/light theme switching

### Architecture
- Data: PostgreSQL query cached to CSV (1-day auto-invalidation)
- Theming via CSS custom properties set on `#page-container`
- `SIZE_COLORS` (viridis) for size-class stacking
- `PROJECT_COLORS` match CNEOS site_all.json exactly

### Running
```bash
source venv/bin/activate
python app/discovery_stats.py        # default: http://127.0.0.1:8050/
python app/discovery_stats.py --refresh  # force re-query from DB
```

## Development Conventions

- **Python env:** `venv/`, pinned in `requirements.txt`
- **Strip notebook outputs before committing** — use
  `jupyter nbconvert --clear-output` or `nbstripout` before `git add`
- **Never use `SELECT *`** — explicit column lists always
- **Readonly database access** — all queries go through `lib/db.py`
  context manager
- **COALESCE expressions** derive missing Keplerian elements from
  cometary (q,e,i) — see `lib/orbits.py`

## Key Terminology

- **NEO:** Near-Earth Object (q <= 1.3 AU)
- **H magnitude:** absolute magnitude (proxy for size; lower = bigger)
- **NEOMOD3:** Debiased population model (Nesvorny et al. 2024)
- **ADES:** Astrometric Data Exchange Standard (IAU observation format)
- **obs80:** Legacy MPC 80-column observation format
- **permid:** Permanent MPC number; **provid:** Provisional designation
- **trkid:** Tracklet identifier grouping same-night observations
- **disc = '*':** Discovery observation flag in obs_sbn
