# CSS SBN Derived — Project Planning

**Date:** 2026-02-07
**Author:** Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
**Repository:** https://github.com/rlseaman/CSS_SBN_derived

## Context

Catalina Sky Survey maintains a local PostgreSQL replica of the MPC/SBN
(Minor Planet Center / PDS Small Bodies Node) database (`mpc_sbn`). This
project develops "value-added" SQL scripts that augment that database with
derived data products useful to the NEO community.

The first such script is `sql/discovery_tracklets.sql`, which computes
discovery tracklet statistics (position, magnitude, epoch) for all NEAs
listed in the MPC's NEA.txt catalog. Current completeness: 40,805 / 40,807
(99.995%), with the 2 missing objects (2009 US19, 2024 TZ7) reported to MPC
as having no discovery observation in the database.

## Vision

This project will grow to include multiple SQL scripts, each producing
value-added data products. Distribution needs fall into three categories:

1. **Flat files (CSV)** — For tools like NEOlyzer and general community use
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

### Database enrichment

SQL scripts should be written to be **idempotent** so they can be re-run
safely:

- `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
- `INSERT ... ON CONFLICT` or truncate-and-reload patterns
- Materialized views where appropriate (refreshable without downtime)

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

## Remaining Steps

### Step 4: Set up cron on a CSS server

- Daily cron job calling `scripts/run_pipeline.sh`
- Log output for diagnostics
- Alert on failure (email or similar)
- Example crontab entry:
  ```
  0 12 * * * /path/to/CSS_SBN_derived/scripts/run_pipeline.sh --upload >> /var/log/css_sbn_derived.log 2>&1
  ```

### Step 5: Document for downstream users

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
