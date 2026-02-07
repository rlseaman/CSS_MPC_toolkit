# CSS SBN Derived — Project Planning

**Date:** 2026-02-08
**Author:** Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
**Repository:** https://github.com/rlseaman/CSS_SBN_derived

## Context

The [Catalina Sky Survey](https://catalina.lpl.arizona.edu) (CSS) at the
University of Arizona's Lunar and Planetary Laboratory maintains a local
PostgreSQL replica of the [Minor Planet Center](https://www.minorplanetcenter.net)
(MPC) observation and orbit database. This replica is distributed through the
[PDS Small Bodies Node](https://sbnmpc.astro.umd.edu) (SBN) at the University
of Maryland. General information about the replicated database is at:

- Schema: https://www.minorplanetcenter.net/mpcops/documentation/replicated-tables-schema/
- General info: https://www.minorplanetcenter.net/mpcops/documentation/replicated-tables-info-general/

This project develops "value-added" SQL scripts that augment the replicated
database with derived data products useful to the NEO community.

The first such script is `sql/discovery_tracklets.sql`, which computes
discovery tracklet statistics (position, magnitude, epoch) for all NEAs
listed in the MPC's NEA.txt catalog. Current completeness: 40,805 / 40,807
(99.995%), with the 2 missing objects (2009 US19, 2024 TZ7) reported to MPC
as having no discovery observation in the database.

## MPC/SBN Database Schema Analysis

The replicated database contains 16 tables (as of 2026-02). Key tables
relevant to this project:

### Currently used

| Table | Status | Used for |
|-------|--------|----------|
| `obs_sbn` | Ready | All published observations including ITF data |
| `numbered_identifications` | Ready | Number-to-provisional-designation mapping |
| `obscodes` | Ready | Observatory name enrichment |

### Identified for future use

| Table | Status | Potential use |
|-------|--------|---------------|
| `current_identifications` | Ready | Cross-matching secondary designations to primaries |
| `primary_objects` | Ready | Object type classification, orbit status flags |
| `obscodes` | **Now used** | Observatory metadata (name used; location available) |
| `mpc_orbits` | Partial | Orbital elements, Earth MOID, orbit type (when fully populated) |
| `neocp_els` | Ready | Current NEOCP tracklet elements (Digest2 scores) |
| `neocp_prev_des` | Ready | NEOCP removal reasons |

### Schema insights

1. **`numbered_identifications`** is the authoritative cross-reference for
   numbered asteroids. It maps `permid` (the number) to
   `packed/unpacked_primary_provisional_designation`. This is more reliable
   than `mpc_orbits` for designation lookup since `mpc_orbits` is partially
   populated and undergoing orbit consistency work. (Refactored in
   discovery_tracklets.sql as of 2026-02-08.)

2. **`current_identifications`** tracks all secondary designations linked to
   a primary. Each object may appear multiple times — once per secondary
   designation. This could recover observations stored under a secondary
   provisional designation that doesn't match the primary.

3. **`primary_objects.object_type`** classifies objects (NEA, MBA, comet, etc.).
   If the type codes are documented, this could eliminate the dependency on
   downloading NEA.txt to determine which objects are NEAs. The query could
   instead filter directly from the database.

4. **`obscodes`** has longitude, parallax constants (`rhocosphi`, `rhosinphi`),
   observatory name, and observation type. Joining this to discovery tracklet
   output would add observatory name and approximate location at negligible
   query cost.

5. **`mpc_orbits`** — partially populated, with comet and natural satellite
   orbits not yet stored. Fields not fully populated. The `mpc_orb_jsonb`
   column contains the complete MPC JSON orbit format which may have fields
   not yet broken out into individual columns. `earth_moid` and
   `orbit_type_int` are available but population completeness is unclear.

## Vision

This project will grow to include multiple SQL scripts, each producing
value-added data products. Distribution needs fall into three categories:

1. **Flat files (CSV)** — For tools like [NEOlyzer](https://github.com/rlseaman/neolyzer) and general community use
2. **Database enrichment** — New tables and indices in the CSS local postgres
3. **Downstream replication** — Enabling community stakeholders to replicate
   derived tables and indices into their own postgres instances

## Distribution Strategy

### Flat files via GitHub Releases

For CSV outputs consumed by downstream tools (e.g., NEOlyzer):

- Ship a baseline snapshot in the consuming project's repo (updated with
  version tags every few months)
- Publish daily/weekly updates as GitHub Release assets from a CSS cron job
  using `gh release upload --clobber`
- Gate uploads on validation (row counts, file size, format checks)
- Consumers fetch the latest release asset on demand

This avoids git history bloat, makes failures harmless (a failed upload
simply leaves the previous version in place), and keeps data updates
decoupled from code changes.

### Database enrichment (ELT pattern)

SQL scripts should be written to be **idempotent** so they can be re-run
safely:

- `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
- `INSERT ... ON CONFLICT` or truncate-and-reload patterns
- Materialized views where appropriate (refreshable without downtime)

For incorporating external data sources (JPL SBDB, NEOWISE, ESA NEODyS),
this project adopts an **ELT** (Extract-Load-Transform) pattern rather than
traditional ETL:

- **Extract**: Pull external data via API or bulk download
- **Load**: Insert into staging tables in the same postgres database
- **Transform**: SQL views and materialized views join external data with
  MPC tables

The advantage: all transforms happen in SQL, inside the database where
the MPC data already lives. No intermediate files, no Python glue code to
maintain. The database optimizer handles join planning. This is a natural
extension of what `discovery_tracklets.sql` already does — SQL-based
in-database transformation.

Candidate external data sources for fusion:

| Source | Data | Method |
|--------|------|--------|
| [JPL SBDB](https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html) | Physical properties, MOID, Tisserand | API fetch → staging table |
| [NEOWISE](https://wise2.ipac.caltech.edu/docs/release/neowise/) | Thermal diameters, albedos | Bulk CSV → staging table |
| [ESA NEODyS](https://newton.spacedys.com/neodys/) | Impact probabilities | Bulk download → staging table |
| MPC NEA.txt | Authoritative NEA list | Download → temp table (current approach) |

### Downstream replication

For community stakeholders who want derived tables in their own postgres:

- Provide the SQL scripts themselves (they can run against their own replica)
- Additionally provide `pg_dump` extracts of specific tables as release
  assets alongside the CSVs
- Document schema, dependencies, and required source tables clearly

## Completed Steps

### Step 1: Create the GitHub repository

- Repository created at https://github.com/rlseaman/CSS_SBN_derived
- Initialized with directory structure, README, and documentation

### Step 2: Move and rename the SQL script

- `all_neas_from_nea_txt_v4.sql` renamed to `sql/discovery_tracklets.sql`
- Version suffix dropped — git history tracks versions
- Debug/diagnostic queries separated into `sql/debug/discovery_tracklets_diag.sql`

### Step 3: Build the automation pipeline

- `scripts/run_pipeline.sh`: Downloads NEA.txt, runs SQL, validates, uploads
- `scripts/validate_output.sh`: Row count, column count, completeness checks
- `scripts/upload_release.sh`: GitHub Release asset upload via `gh` CLI

### Step 4: Refactor to use numbered_identifications (2026-02-08)

- Replaced `mpc_orbits` join with `numbered_identifications` for
  number-to-designation mapping in all SQL files
- `numbered_identifications` is the authoritative, fully-populated
  cross-reference table; `mpc_orbits` is partially populated and
  undergoing consistency work
- Updated documentation to reflect the new dependency

### Step 5: UNION refactor and tracklet metrics (2026-02-08)

- Replaced OR-based joins in `discovery_info` and `discovery_tracklet_stats`
  with 3× UNION branches, each targeting a single index (permid, provid,
  num_provid) for efficient execution
- `discovery_obs_all` uses UNION ALL (deduplicated by DISTINCT ON)
- `tracklet_obs_all` uses UNION (deduplicates observations matching via
  both permid and provid for numbered asteroids)
- Added 5 new output columns: `nobs`, `span_hours`, `rate_deg_per_day`,
  `position_angle_deg`, `discovery_site_name` — total now 12 columns
- Rate uses Haversine formula; PA uses spherical bearing (both handle
  RA wraparound correctly)
- Updated schema docs, README, and validate_output.sh (EXPECTED_COLS=12)
- **Needs validation** against database on CSS server

## Remaining Steps

### Step A: Validate refactored query on CSS server

- Row count must remain 40,805
- Original 7 columns must match previous output exactly
- `nobs >= 1`, `span_hours >= 0` for all rows
- `rate_deg_per_day IS NULL` iff `nobs = 1`; same for `position_angle_deg`
- `position_angle_deg` in [0, 360) when not NULL
- Spot-check known NEA (e.g., Apophis) against independent data

### Step B: Set up cron on a CSS server

- Daily cron job calling `scripts/run_pipeline.sh`
- Log output for diagnostics
- Alert on failure (email or similar)
- Example crontab entry:
  ```
  0 12 * * * /path/to/CSS_SBN_derived/scripts/run_pipeline.sh --upload >> /var/log/css_sbn_derived.log 2>&1
  ```

### Step 6: Enrich with obscodes data ✅ (2026-02-08)

- Joined `obscodes` to add `discovery_site_name` to output
- LEFT JOIN on `obscode = discovery_stn` (NULL if code not in obscodes)

### Step 7: Add current_identifications fallback matching

- Use `current_identifications` to match observations stored under
  secondary designations
- May recover additional NEAs currently unmatched

### Step 8: Investigate primary_objects.object_type

- Determine if `object_type` codes can replace NEA.txt as the source of
  "which objects are NEAs"
- Would simplify the pipeline by removing the external download dependency

### Step 9: Document for downstream users

- Announce availability to stakeholders
- Provide instructions for running scripts against their own postgres replica
- Establish communication channel for schema changes

## Suggestions and Improvements

### 1. Materialized views instead of (or alongside) flat files

For database enrichment, consider creating the discovery tracklet output
as a **materialized view** rather than a standalone query:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS nea_discovery_tracklets AS
  ( ... the main query ... );

CREATE UNIQUE INDEX ON nea_discovery_tracklets (primary_designation);
```

Benefits: refreshable with `REFRESH MATERIALIZED VIEW CONCURRENTLY` (no
downtime), queryable by other SQL scripts, exportable to CSV with `\copy`.
This also means the flat file and the database table are always derived
from the same source, avoiding drift.

### 2. Provenance metadata

Include a metadata sidecar file with each output:
- Timestamp of generation
- NEA.txt download timestamp and row count
- Database snapshot date
- Script version (git commit hash)
- Match statistics (total, matched, unmatched)

### 3. pg_dump for table distribution

For downstream stakeholders who want postgres tables:

```bash
pg_dump -t nea_discovery_tracklets --no-owner --no-privileges \
    mpc_sbn > release/nea_discovery_tracklets.sql
```

This produces a self-contained SQL file that creates and populates the
table, which can be distributed as a release asset alongside the CSV.

### 4. Future script candidates

Natural extensions of this project might include:
- **NEA orbital element enrichment** — derived parameters not in MPCORB
- **Observatory statistics** — per-station discovery/follow-up counts
- **Linkage tables** — cross-references between MPC designations and
  other catalogs (JPL SBDB, ESA NEODyS, etc.)
- **MOID-based risk tables** — objects sorted by Earth MOID
- **Follow-up priority lists** — objects needing additional observations
- **NEOCP history** — statistics on confirmation page lifecycle

### 5. CI/CD with GitHub Actions

Even though the main pipeline runs on CSS servers, GitHub Actions can:
- Validate SQL syntax on push (using `pgsanity` or similar)
- Check that schema documentation matches the SQL
- Verify that release assets exist and are recent (staleness check)

## Open Questions

1. **Update cadence** — Daily? Weekly? Should different products have
   different cadences?
2. **Stakeholder communication** — How will downstream users know when
   new data products are available?
3. **Database version coupling** — How tightly are the SQL scripts
   coupled to specific versions of the MPC/SBN schema? How do we
   handle schema changes upstream?
4. **object_type codes** — What values in `primary_objects.object_type`
   and `mpc_orbits.orbit_type_int` correspond to NEAs? Can these replace
   the NEA.txt download?
5. **mpc_orbits population** — Which fields in `mpc_orbits` are currently
   populated for NEAs? Is `earth_moid` reliable enough to use?
