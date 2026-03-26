# Streaming Integration Plan

## Context

The [event_streaming](https://github.com/rlseaman/event_streaming)
repository defines a 30-field Avro schema (`css.neo.DiscoveryCircumstances`,
version 01.01) for streaming NEO discovery records via Apache Kafka, with a
parallel path for NASA GCN integration.  That repo's pipeline currently
consumes the 12-column CSV produced by this project's
`sql/discovery_tracklets.sql`, enriches it with astropy-computed
discovery circumstances, serializes to Avro, and publishes to Kafka.

This document describes how to expand the standalone CTE chain in
`discovery_tracklets.sql` so it can serve as the single authoritative
source for both the archival CSV product and the streaming pipeline,
and how to evolve the full-rebuild query into an incremental one suitable
for near-real-time streaming.


## Current Column Inventory

| # | Standalone SQL (12 cols) | App LOAD_SQL (~21 cols) | Avro Schema (30 fields) |
|---|--------------------------|-------------------------|-------------------------|
| 1 | primary_designation | designation | primary_designation |
| 2 | packed_primary_provisional_designation | disc_year | packed_designation |
| 3 | avg_mjd_discovery_tracklet | disc_month | permanent_number |
| 4 | avg_ra_deg | disc_date | name |
| 5 | avg_dec_deg | disc_obstime | discovery_mjd |
| 6 | median_v_magnitude | station_code | ra_deg |
| 7 | nobs | h | dec_deg |
| 8 | span_hours | orbit_type_int | n_obs |
| 9 | rate_deg_per_day | q, e, i | span_hours |
| 10 | position_angle_deg | stn_longitude | v_mag |
| 11 | discovery_site_code | stn_rhocosphi | rate_deg_per_day |
| 12 | discovery_site_name | stn_rhosinphi | position_angle_deg |
| | | stn_type | site_code |
| | | avg_ra_deg | site_name |
| | | avg_dec_deg | sun_alt_deg |
| | | median_v_mag | twilight_class |
| | | tracklet_nobs | lunar_elong_deg |
| | | rate_deg_per_day | eclipse_class |
| | | position_angle_deg | sun_elong_deg |
| | | | moon_phase |
| | | | moon_age_days |
| | | | gal_lat_deg |
| | | | ecl_lat_deg |
| | | | orbit_class |
| | | | H |
| | | | V_ephem |
| | | | earth_moid |
| | | | pha |
| | | | source |
| | | | record_mjd |

The standalone SQL and app LOAD_SQL share the same core CTE chain
(`neo_list` -> `discovery_obs_all` -> `discovery_info` ->
`tracklet_obs_all` -> `discovery_tracklet_stats`) but diverge in NEO
selection criteria, output columns, and column naming.  See the
[CTE chain divergence](#cte-chain-divergence) section below.


## Proposed Expansion: Two Tiers

### Tier 1: SQL-side additions (expand standalone to ~19 columns)

These require only joining tables already used by the app LOAD_SQL
and add negligible query cost (the expensive work is the 3-branch
UNION ALL against 526M obs_sbn rows; `mpc_orbits` is 1.5M rows on
indexed columns):

| New Column | Source | Notes |
|------------|--------|-------|
| `permanent_number` | Existing permid resolution logic | Integer; NULL for unnumbered |
| `name` | `mpc_designation.name` | Only ~100 NEOs have IAU names |
| `H` | `mpc_orbits.h` (with NEA.txt override) | App already implements NEA.txt override via `lib/nea_catalog.py` |
| `orbit_class` | `classify_from_elements()` or `mpc_orbits.orbit_type_int` | String label (Atira/Aten/Apollo/Amor/etc.) |
| `earth_moid` | `mpc_orbits.earth_moid` | NULL for ~70% of orbits |
| `pha` | Derived: H <= 22 AND earth_moid <= 0.05 | Boolean; requires both H and earth_moid |
| `stn_longitude`, `stn_rhocosphi`, `stn_rhosinphi`, `stn_type` | `obscodes` table | Needed downstream by astropy for circumstance computation |

This makes the standalone SQL self-sufficient as the Avro pipeline's
input, eliminating the need for a separate orbit join in the streaming
pipeline.

### Tier 2: Post-SQL Python enrichment (already built)

These columns cannot be computed in SQL -- they require astropy or are
stamped at generation time:

| Column | Source | Notes |
|--------|--------|-------|
| `sun_alt_deg` | astropy AltAz transform | Solar altitude at observatory |
| `twilight_class` | Derived from sun_alt_deg | Nighttime/Astronomical/Nautical/Civil/Daytime/Space-based |
| `lunar_elong_deg` | astropy | Target-Moon angular separation |
| `eclipse_class` | astropy shadow geometry | Penumbral/Partial/Total/NULL |
| `sun_elong_deg` | astropy | Target-Sun angular separation |
| `moon_phase` | astropy | Lunar illumination fraction [0-1] |
| `moon_age_days` | astropy | Signed days from nearest new moon |
| `gal_lat_deg` | Coordinate transform | Galactic latitude |
| `ecl_lat_deg` | Coordinate transform | Ecliptic latitude |
| `V_ephem` | astropy ephemeris + H | Retroactive magnitude estimate |
| `source` | Stamped at generation | e.g., "CSS_MPC_toolkit" |
| `record_mjd` | Stamped at generation | MJD timestamp of record creation |

The `discovery_circumstances.py` module in `event_streaming` already
computes the first 9 of these using vectorized astropy (~40 seconds for
~44K records, with 43 tests covering edge cases).


## Resulting Pipeline

```
discovery_tracklets.sql (~19 cols, ~30s)
  -> CSV
  -> discovery_circumstances.py --compute-circumstances (~40s, adds 9 cols)
  -> csv_to_avro.py (+ stamp source, record_mjd, compute V_ephem)
  -> Avro file
  -> Kafka producer -> neo.discovery.circumstances topic
```


## CTE Chain Divergence

Two copies of the core CTE chain exist:

1. **`sql/discovery_tracklets.sql`** -- standalone, produces archival CSV
2. **`app/discovery_stats.py` LOAD_SQL** -- feeds the Dash app tabs

### Key differences

| Aspect | Standalone | App |
|--------|-----------|-----|
| NEO boundary | `q < 1.32 OR orbit_type_int IN (0,1,2,3,20)` | `q <= 1.30` |
| Output columns | 12 (astrometry/photometry only) | ~21 (adds orbit elements, observatory coords) |
| Column names | `primary_designation`, `discovery_site_code`, `nobs` | `designation`, `station_code`, `tracklet_nobs` |
| Sort order | Numbered-first, then by designation | Chronological by obstime |
| H override | None | NEA.txt via `lib/nea_catalog.py` |

### Plan

Preserve the standalone SQL as the authoritative data-product chain.
The app LOAD_SQL remains separate because it has UI-specific columns
(`disc_year`, `disc_month`, `disc_date`) and a different NEO boundary
suited to IAU convention.  Long-term, both could derive from a shared
parameterized base query, but that unification is not required for
streaming integration.


## Incremental Query Strategy

The current CTE chain runs a full rebuild (~44K rows, ~30 seconds).
For streaming, we need to detect new discoveries efficiently.  Three
options, in order of increasing ambition:

### Option A: Differential on `created_at` (simplest, works now)

`obs_sbn.created_at` is indexed.  Add a WHERE filter:

```sql
WHERE created_at > :last_run_timestamp
```

This narrows the scan from 526M rows to recent inserts (typically
hundreds per day).  Catches NEOs whose discovery observation was
recently ingested.

**Limitation:** A new discovery observation may arrive for an object
whose other observations already existed, so the full tracklet must
be re-resolved for any touched object.  Also, bulk re-ingestion by
MPC would flood `created_at` with false positives; a secondary check
against the previous run's designation set handles this.

### Option B: Maintain a known-discoveries table (recommended)

Keep a persistent table or CSV of all designations already processed.
Each run:

1. Query `mpc_orbits` for NEOs (fast -- 1.5M rows, indexed on q/e)
2. Anti-join against `known_discoveries` to find new designations
3. Run the full CTE chain only for new designations (parameterized:
   `WHERE permid = ANY(:new_permids)`)
4. Append results to the master file and update `known_discoveries`

**Advantages:**
- Clean separation: does not depend on `created_at` semantics
- Reduces daily incremental query from ~30s to <1s (typically 0-5
  new NEOs per day)
- The full rebuild becomes a periodic validation run (weekly/monthly)
- Naturally produces the incremental records the Kafka producer needs

**Trade-off:** Requires managing a small state file (~44K designations).

### Option C: PostgreSQL logical replication / Debezium CDC (future)

The `event_streaming` repo's Phase 4 roadmap names this explicitly.
Since `mpc_sbn` already uses logical replication from MPC, we could
tap that replication stream to detect inserts to `obs_sbn` where
`disc = '*'`.  This gives true real-time (<1 min latency) but
requires infrastructure work and DBA coordination.

### Recommendation

**Option B is the practical sweet spot.**  The workflow becomes:

1. **Daily cron** (or more frequent): incremental query -> new Avro
   records -> Kafka
2. **Weekly/monthly**: full rebuild for validation and correction
3. **Future**: replace polling with CDC (Option C) when
   infrastructure supports it


## Relationship to event_streaming Repository

The `event_streaming` repo is an R&D prototype (originating at the
RAPID Response workshop, Caltech, March 2026).  Production code is
intended to migrate into `CSS_MPC_toolkit` and `astro_map_plot`.
The integration points are:

- **Schema:** The Avro schema (`neo_discovery.avsc`) defines the
  contract.  The Tier 1 SQL expansion aligns the standalone CSV
  output with the schema's required fields.
- **Enrichment:** `discovery_circumstances.py` (Tier 2 computation)
  is a self-contained module with its own test suite; it can be
  adopted into `CSS_MPC_toolkit` as-is.
- **Transport:** The Kafka producer/consumer pair and GCN JSON Schema
  are transport-layer concerns that remain in `event_streaming` until
  the streaming infrastructure is production-ready.
- **Two-topic model:** Discovery circumstances (append-only topic)
  and orbital elements (compacted topic) are separate Kafka topics,
  reflecting the immutable-facts vs. evolving-properties distinction.
