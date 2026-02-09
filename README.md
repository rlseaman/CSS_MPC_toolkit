# CSS SBN Derived Data Products

Value-added data products derived from the MPC/SBN PostgreSQL database,
developed by the Catalina Sky Survey at the University of Arizona.

## Overview

The Minor Planet Center (MPC) publishes asteroid observations and orbital
elements through the Planetary Data System (PDS) Small Bodies Node (SBN) as
a PostgreSQL database. Catalina Sky Survey maintains a local replica of this
database on host `sibyl`. This project provides SQL scripts, Python
libraries, and derived data products useful to the NEO community.

## Available Data Products

### NEO Discovery Tracklets

**Script:** [`sql/discovery_tracklets.sql`](sql/discovery_tracklets.sql)

Computes discovery circumstances for all Near-Earth Objects (NEOs) identified
from the MPC's orbital element database. NEO selection uses orbital criteria
(`q < 1.32 AU` or `orbit_type_int IN (0, 1, 2, 3, 20)`), which includes
near-Earth comets.

**Output columns (12):**

| Column | Description |
|--------|-------------|
| `primary_designation` | Asteroid number (if numbered) or provisional designation |
| `packed_primary_provisional_designation` | MPC packed format designation |
| `avg_mjd_discovery_tracklet` | Mean MJD epoch of the discovery tracklet |
| `avg_ra_deg` | Mean Right Ascension (decimal degrees) |
| `avg_dec_deg` | Mean Declination (decimal degrees) |
| `median_v_magnitude` | Median V-band magnitude (with band corrections) |
| `nobs` | Number of observations in discovery tracklet |
| `span_hours` | Time span of discovery tracklet (hours) |
| `rate_deg_per_day` | Great-circle rate of motion (deg/day) |
| `position_angle_deg` | Position angle of motion (0=N, 90=E) |
| `discovery_site_code` | MPC observatory code of the discovery site |
| `discovery_site_name` | Observatory name |

**Completeness:** 43,629 NEO discovery tracklets (as of 2026-02-08).
Known missing: 2020 GZ1 (no orbit in mpc_orbits), 2009 US19 and 2024 TZ7
(no discovery observation flag in obs_sbn).

The output CSV is consumed by [NEOlyzer](https://github.com/rlseaman/neolyzer)
and is available as a release asset for download.

### ADES Export (NEOCP Observations)

**Scripts:** [`lib/ades_export.py`](lib/ades_export.py),
[`sql/ades_export.sql`](sql/ades_export.sql)

Exports NEOCP (NEO Confirmation Page) archived observations in
[ADES](https://github.com/IAU-ADES/ADES-Master) format (XML or PSV),
conforming to `general.xsd` (version 2022). The NEOCP tables carry
ADES-native uncertainty fields (`rmsRA`, `rmsDec`, `rmsCorr`, `rmsTime`)
not available in the main `obs_sbn` table.

**Usage:**
```bash
# All current NEOCP observations
python3 -m lib.ades_export --host sibyl --format xml --all -o neocp_live.xml

# Single designation from live NEOCP
python3 -m lib.ades_export --host sibyl --format psv --desig CE5W292 -o output.psv

# Historical lookup from archive
python3 -m lib.ades_export --host sibyl --archive --desig "2024 YR4" -o yr4.xml
```

Requires `psycopg2`: `pip install psycopg2-binary`

## Conversion Library

**Module:** [`lib/mpc_convert.py`](lib/mpc_convert.py)

Reusable conversion functions for MPC 80-column observation format:

| Function | Input | Output |
|----------|-------|--------|
| `mpc_date_to_iso8601()` | `"2024 12 27.238073"` | `"2024-12-27T05:42:49.5Z"` |
| `ra_hms_to_deg()` | `"08 56 40.968"` | `134.1707` |
| `dec_dms_to_deg()` | `"-00 16 11.93"` | `-0.2700` |
| `mpc_cat_to_ades()` | `"V"` | `"Gaia2"` |
| `mpc_mode_to_ades()` | `"C"` | `"CCD"` |
| `unpack_designation()` | `"K24Y04R"` | `"2024 YR4"` |
| `pack_designation()` | `"2024 YR4"` | `"K24Y04R"` |
| `parse_obs80()` | 80-col line | ADES field dict |

PostgreSQL equivalents are in
[`sql/css_utilities_functions.sql`](sql/css_utilities_functions.sql),
designed for a `css_utilities` schema on the local replica.

## Database Operations

### Health Check

**Script:** [`scripts/db_health_check.sh`](scripts/db_health_check.sh)

Diagnostic toolkit covering replication status, table health (dead tuples,
vacuum/analyze staleness), index usage, configuration review, and active
connections.

```bash
bash scripts/db_health_check.sh --host sibyl
bash scripts/db_health_check.sh --host sibyl --output health_$(date +%Y%m%d).txt
```

### Tuning Recommendations

**File:** [`scripts/db_tune_recommendations.sql`](scripts/db_tune_recommendations.sql)

PostgreSQL configuration recommendations for the `sibyl` replica
(251 GB RAM, HDD). Covers `shared_buffers`, `work_mem`,
`maintenance_work_mem`, autovacuum thresholds, and per-table overrides
for `obs_sbn`.

### Huge Pages

**File:** [`scripts/enable_huge_pages.md`](scripts/enable_huge_pages.md)

Step-by-step guide for enabling huge pages on RHEL 8 for PostgreSQL with
64 GB `shared_buffers`. Deferred to next maintenance reboot due to memory
fragmentation.

## Project Structure

```
CSS_SBN_derived/
├── README.md                           # This file
├── PLANNING.md                         # Project roadmap and design decisions
├── lib/
│   ├── mpc_convert.py                  # MPC format conversion functions
│   └── ades_export.py                  # ADES XML/PSV export
├── sql/
│   ├── discovery_tracklets.sql         # NEO discovery tracklet statistics
│   ├── css_utilities_functions.sql       # PostgreSQL conversion functions
│   ├── ades_export.sql                 # ADES-ready columns from NEOCP
│   ├── common/
│   │   └── indexes.sql                 # Shared index definitions
│   └── debug/
│       └── discovery_tracklets_diag.sql
├── scripts/
│   ├── run_pipeline.sh                 # Run SQL, validate, upload
│   ├── validate_output.sh             # Output validation checks
│   ├── upload_release.sh              # Upload CSV to GitHub Releases
│   ├── db_health_check.sh            # Database diagnostic toolkit
│   ├── db_tune_recommendations.sql   # PostgreSQL tuning guide
│   └── enable_huge_pages.md          # Huge pages setup guide (RHEL 8)
├── schema/
│   └── discovery_tracklets.md         # Output schema documentation
├── sandbox/
│   ├── schema_review.md               # Comprehensive schema analysis
│   └── neocp_ades_analysis.md         # NEOCP tables & ADES feasibility
└── docs/
    ├── source_tables.md               # Required MPC/SBN tables and columns
    └── band_corrections.md            # Photometric band-to-V corrections
```

## Quick Start

### Prerequisites

- PostgreSQL client (`psql`)
- Access to an MPC/SBN database replica (host `sibyl` by default)
- Python 3.8+ (for conversion library and ADES export)
- `psycopg2` (for database-connected Python scripts)
- `gh` CLI for uploading release assets (optional)

### Run the Discovery Tracklets Pipeline

```bash
# Run the query directly
psql -h sibyl -d mpc_sbn -f sql/discovery_tracklets.sql \
    --csv -o NEO_discovery_tracklets.csv

# Or use the automated pipeline
./scripts/run_pipeline.sh
```

### Install SQL Functions on the Replica

```bash
# Requires CREATE SCHEMA / CREATE FUNCTION privileges
psql -h sibyl -U <owner> mpc_sbn -f sql/css_utilities_functions.sql
```

### Run the Health Check

```bash
bash scripts/db_health_check.sh --host sibyl
```

## Distribution

Data products are distributed in two ways:

1. **CSV files** via [GitHub Releases](https://github.com/rlseaman/CSS_SBN_derived/releases) --
   download the latest release asset for flat-file access
2. **SQL scripts** in this repository -- run directly against your own
   MPC/SBN database replica to generate the data locally

## Database Requirements

These scripts are designed to run against a PostgreSQL replica of the MPC/SBN
database. See [docs/source_tables.md](docs/source_tables.md) for the required
tables and columns. The database on `sibyl` is PostgreSQL 15.2 receiving
logical replication from MPC.

## License

MIT License -- Copyright (c) 2026 University of Arizona, Catalina Sky Survey

## Contact

**Rob Seaman**
Catalina Sky Survey, Lunar and Planetary Laboratory, University of Arizona
rseaman@arizona.edu
