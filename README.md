# CSS SBN Derived Data Products

Value-added data products derived from the MPC/SBN PostgreSQL database,
developed by the Catalina Sky Survey at the University of Arizona.

## Overview

The Minor Planet Center (MPC) publishes asteroid observations and orbital
elements through the Planetary Data System (PDS) Small Bodies Node (SBN) as
a PostgreSQL database. Catalina Sky Survey maintains a local replica of this
database. This project provides SQL scripts that compute derived data
products useful to the NEO community.

## Available Data Products

### NEA Discovery Tracklets

**Script:** [`sql/discovery_tracklets.sql`](sql/discovery_tracklets.sql)

Computes discovery circumstances for all Near-Earth Asteroids listed in the
MPC's [NEA.txt](https://minorplanetcenter.net/iau/MPCORB/NEA.txt) catalog.

**Output columns:**

| Column | Description |
|--------|-------------|
| `primary_designation` | Asteroid number (if numbered) or provisional designation |
| `packed_primary_provisional_designation` | MPC packed format designation |
| `avg_mjd_discovery_tracklet` | Mean MJD epoch of the discovery tracklet |
| `avg_ra_deg` | Mean Right Ascension (decimal degrees) |
| `avg_dec_deg` | Mean Declination (decimal degrees) |
| `median_v_magnitude` | Median V-band magnitude (with band corrections) |
| `discovery_site_code` | MPC observatory code of the discovery site |

**Completeness:** 40,805 / 40,807 NEAs (99.995% as of 2026-02-07)

The output CSV is consumed by [NEOlyzer](https://github.com/rlseaman/neolyzer)
and is available as a release asset for download.

## Project Structure

```
CSS_SBN_derived/
├── README.md                     # This file
├── PLANNING.md                   # Project roadmap and design decisions
├── sql/
│   ├── discovery_tracklets.sql   # NEA discovery tracklet statistics
│   ├── common/
│   │   └── indexes.sql           # Shared index definitions
│   └── debug/
│       └── discovery_tracklets_diag.sql  # Diagnostic queries
├── scripts/
│   ├── run_pipeline.sh           # Download NEA.txt, run SQL, validate, upload
│   ├── validate_output.sh        # Output validation checks
│   └── upload_release.sh         # Upload CSV to GitHub Releases
├── schema/
│   └── discovery_tracklets.md    # Output schema documentation
└── docs/
    ├── source_tables.md          # Required MPC/SBN tables and columns
    └── band_corrections.md       # Photometric band-to-V corrections
```

## Quick Start

### Prerequisites

- PostgreSQL client (`psql`)
- Access to an MPC/SBN database replica
- `curl` for downloading NEA.txt
- `gh` CLI for uploading release assets (optional)

### Manual Run

```bash
# Download the current NEA catalog
curl -o /tmp/NEA.txt https://minorplanetcenter.net/iau/MPCORB/NEA.txt

# Run the query (adjust host/database as needed)
psql -h localhost -d mpc_sbn -f sql/discovery_tracklets.sql --csv -o NEA_discovery_tracklets.csv
```

### Automated Pipeline

```bash
# Run the full pipeline: download, query, validate, upload
./scripts/run_pipeline.sh
```

See [scripts/run_pipeline.sh](scripts/run_pipeline.sh) for configuration
options (database host, credentials, output paths).

## Distribution

Data products are distributed in two ways:

1. **CSV files** via [GitHub Releases](https://github.com/rlseaman/CSS_SBN_derived/releases) —
   download the latest release asset for flat-file access
2. **SQL scripts** in this repository — run directly against your own
   MPC/SBN database replica to generate the data locally

## Database Requirements

These scripts are designed to run against a PostgreSQL replica of the MPC/SBN
database. See [docs/source_tables.md](docs/source_tables.md) for the required
tables and columns.

## License

MIT License — Copyright (c) 2026 University of Arizona, Catalina Sky Survey

## Contact

**Rob Seaman**
Catalina Sky Survey, Lunar and Planetary Laboratory, University of Arizona
rseaman@arizona.edu
