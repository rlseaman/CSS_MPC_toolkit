# CSS MPC Toolkit -- Project Planning

**Date:** 2026-02-08 (updated)
**Author:** Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
**Repository:** https://github.com/rlseaman/CSS_MPC_toolkit

## Context

The [Catalina Sky Survey](https://catalina.lpl.arizona.edu) (CSS) at the
University of Arizona's Lunar and Planetary Laboratory maintains a local
PostgreSQL replica of the [Minor Planet Center's](https://www.minorplanetcenter.net)
(MPC) observation and orbit catalogs distributed through the
[PDS Small Bodies Node](https://sbnmpc.astro.umd.edu) (SBN).

- Schema: https://www.minorplanetcenter.net/mpcops/documentation/replicated-tables-schema/
- General info: https://www.minorplanetcenter.net/mpcops/documentation/replicated-tables-info-general/

The database resides on host `sibyl` (RHEL 8.6, 251 GB RAM, HDD), running
PostgreSQL 15.2 with logical replication from MPC. The database is 446 GB
with 18 tables in the public schema, dominated by `obs_sbn` (526M+ rows,
239 GB).

This project develops "value-added" data products: SQL scripts, Python
libraries, and derived datasets useful to the NEO community.

## MPC/SBN Database Schema

The replicated database contains 18 tables. Full analysis in
`sandbox/schema_review.md`.

### Currently used

| Table | Rows | Used for |
|-------|------|----------|
| `obs_sbn` | 526M | All published observations (239 GB) |
| `mpc_orbits` | 1.51M | NEO selection by orbital elements |
| `numbered_identifications` | 876K | Number-to-designation mapping |
| `obscodes` | 2.4K | Observatory name enrichment |
| `neocp_obs_archive` | 777K | NEOCP archived observations (ADES export) |
| `neocp_prev_des` | 71K | NEOCP designation resolution |
| `neocp_events` | 310K | NEOCP operational audit log |

### Key schema insights

1. **No foreign keys** exist anywhere in the schema. Referential integrity
   is unenforced -- all joins rely on matching text fields.

2. **`orbit_type_int` is NULL for 35%** of `mpc_orbits`. These are objects
   with computed orbits but no MPC classification.

3. **`primary_objects.object_type = 0`** is generic "minor planet" (1.5M
   objects). It cannot distinguish NEOs from the general population.

4. **NEOCP tables** carry ADES-native uncertainty fields (`rmsra`, `rmsdec`,
   `rmscorr`, `rmstime`) not present in `obs_sbn`.

5. **Logical replication** means local DDL (schemas, functions, indexes) is
   safe. MPC enforces a 5% XMIN lag threshold and 14 days/year maximum
   downtime.

## Completed Work

### Discovery Tracklets Pipeline

1. **Initial SQL** -- `sql/discovery_tracklets.sql` computing discovery
   tracklet statistics for all NEOs
2. **Pipeline scripts** -- `run_pipeline.sh`, `validate_output.sh`,
   `upload_release.sh` for automated execution
3. **UNION-based refactor** -- Replaced OR-based joins with 3x UNION
   branches targeting single indexes (permid, provid, num_provid)
4. **Refactored to use numbered_identifications** -- Replaced `mpc_orbits`
   for designation lookup (more reliable, fully populated)
5. **NEO list from mpc_orbits** -- Replaced NEA.txt download with orbital
   criteria (`q < 1.32 OR orbit_type_int IN (0,1,2,3,20)`)
6. **Tracklet metrics** -- Added nobs, span_hours, rate_deg_per_day,
   position_angle_deg, discovery_site_name (12 columns total)
7. **Output:** 43,629 NEO discovery tracklets

### Conversion Library

8. **`lib/mpc_convert.py`** -- Python functions: date conversion (fractional
   day to ISO 8601), RA/Dec sexagesimal to decimal degrees, catalog/mode/band
   code mappings, packed designation encode/decode, full obs80 parser
9. **`sql/css_utilities_functions.sql`** -- PostgreSQL equivalents as
   IMMUTABLE STRICT PARALLEL SAFE functions in `css_utilities` schema

### ADES Export

10. **`lib/ades_export.py`** -- ADES XML and PSV generator conforming to
    `general.xsd` (version 2022). Produces standalone `<optical>` elements
    with all 7 required fields satisfied from NEOCP data.
11. **`sql/ades_export.sql`** -- SQL query producing ADES-ready columns from
    `neocp_obs_archive` with designation resolution via `neocp_prev_des`

### Database Operations

12. **Health check toolkit** -- `scripts/db_health_check.sh` with 9
    diagnostic sections
13. **Tuning applied** -- `shared_buffers` 128 MB -> 64 GB, `work_mem`
    4 MB -> 128 MB, autovacuum thresholds lowered. obs_sbn dead rows:
    82M -> 2,308.
14. **Index cleanup** -- Identified and removed duplicate indexes created
    by previous sessions. Retained only `idx_obs_sbn_disc` (partial index
    on `disc = '*'`).
15. **Schema review** -- Comprehensive analysis in `sandbox/schema_review.md`
16. **NEOCP analysis** -- Table inventory, join paths, latency analysis,
    ADES feasibility in `sandbox/neocp_ades_analysis.md`

## Remaining Work

### Near-term

- **Install `css_utilities` schema** on sibyl (needs privileged user)
- **Install `postgresql15-contrib`** on sibyl for `pg_buffercache` and
  `pg_stat_statements` extensions
- **Enable huge pages** at next maintenance reboot (instructions in
  `scripts/enable_huge_pages.md`)
- **Contact MPC/SBN about unused indexes** -- `obs_sbn_submission_block_id_key`
  (12 GB) and `obs_sbn_trkmpc_idx` (10 GB) are never used
- **Run production pipeline** with finalized SQL and publish release

### Medium-term

- **Set up cron** on a CSS server for daily/weekly pipeline execution
- **Materialized views** for discovery tracklets (refreshable, queryable)
- **ADES validation** against `general.xsd` using the IAU's Python tools
- **Extend ADES export to obs_sbn** for non-NEOCP observations (limited
  to fields available in obs80)

### Value-added derived products (from schema review)

- **Observatory performance dashboard** -- per-station discovery rates,
  follow-up contribution, astrometric quality trends
- **Completeness analysis** -- sky coverage gaps, magnitude-dependent
  completeness, temporal patterns
- **JSONB materialization** -- Extract key fields from `mpc_orb_jsonb`
  into flat columns (covariance, MOIDs, Tisserand parameter)
- **Cross-match with external catalogs** -- JPL SBDB physical properties,
  NEOWISE diameters/albedos, NEODyS impact probabilities

## Distribution Strategy

### Flat files via GitHub Releases

- Publish CSV outputs as GitHub Release assets
- Daily/weekly updates via CSS cron using `gh release upload --clobber`
- Gate uploads on validation (row counts, format checks)

### Database enrichment

- SQL scripts written to be idempotent (`CREATE IF NOT EXISTS`, etc.)
- Local `css_utilities` schema for functions and derived tables
- Materialized views for refreshable computed datasets

### Downstream replication

- Provide SQL scripts for users with their own MPC replicas
- Provide `pg_dump` extracts of derived tables as release assets
- Document schema dependencies clearly

## Open Questions (Resolved)

1. ~~**object_type codes**~~ -- `primary_objects.object_type = 0` is generic
   minor planet; cannot distinguish NEOs. NEO selection uses orbital criteria
   from `mpc_orbits` instead.
2. ~~**mpc_orbits population**~~ -- 1.51M rows, 35% missing `orbit_type_int`.
   Orbital elements (q, e, i, etc.) are well-populated. `earth_moid` is
   available but not used for NEO selection.
3. ~~**Update cadence**~~ -- Pipeline is self-contained; cadence is
   operationally determined by cron scheduling.

## Open Questions (Active)

1. **Stakeholder communication** -- How will downstream users know when
   new data products are available?
2. **Schema change handling** -- MPC schema is "beta release". How do we
   handle upstream changes?
3. **ADES validation scope** -- Should we validate against `submit.xsd`
   (more restrictive) or only `general.xsd` for distribution?
