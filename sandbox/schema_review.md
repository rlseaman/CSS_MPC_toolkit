# MPC/SBN Database Schema Review and Value-Added Opportunities

**Project:** CSS_MPC_toolkit
**Authors:** Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
**Date:** 2026-02-08
**Database:** PostgreSQL 15.2, database `mpc_sbn` (local replica)
**Schema:** 18 tables, ~526M observations, ~1.51M orbits

---

## Table Inventory

| Table | Est. Rows | Purpose |
|-------|-----------|---------|
| obs_sbn | 526M | Core observation table (91 columns) |
| current_identifications | 2.0M | Links primary/secondary designations |
| mpc_orbits | 1.51M | Orbital elements + JSONB blob (52 columns) |
| primary_objects | 1.50M | Master object registry (20 columns) |
| obs_alterations_deletions | 1.38M | Deleted observation records |
| numbered_identifications | 853K | Permanent number assignments |
| neocp_obs_archive | 732K | Archived NEOCP observations |
| obs_alterations_unassociations | 488K | Unassociated observations |
| neocp_events | 288K | NEOCP audit log |
| neocp_var | 102K | NEOCP variant orbits |
| neocp_prev_des | 64K | NEOCP objects that received designations |
| minor_planet_names | 26K | Named minor planets |
| comet_names | 4.3K | Named comets |
| obs_alterations_redesignations | 4.3K | Redesignated observations |
| obscodes | 2.6K | Observatory codes and metadata |
| neocp_obs | ~950 | Current NEOCP observations |
| neocp_els | ~57 | Current NEOCP candidates |
| obs_alterations_corrections | ~0 | Corrected observations (rare) |

---

## Schema Normalization Issues

### 1. No Foreign Keys

Referential integrity is completely unenforced across the entire schema.
Key relationships that exist logically but lack FK constraints:

- `obs_sbn.stn` → `obscodes.obscode`
- `obs_sbn.provid` → `primary_objects.unpacked_primary_provisional_designation`
- `obs_sbn.permid` → `numbered_identifications.permid`
- `mpc_orbits.packed_primary_provisional_designation` → `primary_objects.packed_primary_provisional_designation`

Understandable for a high-volume ingest pipeline (FK checks on 526M rows would
be costly), but orphaned references can accumulate silently.

### 2. Duplicate Indexes

**obs_sbn** has three pairs of redundant btree indexes:

| Original | Duplicate |
|----------|-----------|
| `obs_sbn_permid_idx` | `idx_obs_sbn_permid` |
| `obs_sbn_provid_idx` | `idx_obs_sbn_provid` |
| `obs_sbn_trksub_idx` | `idx_obs_sbn_trksub` |

**primary_objects** has two identical unique indexes on
`packed_primary_provisional_designation`:

| Index 1 | Index 2 |
|---------|---------|
| `primary_objects_packed_primary_provisional_designation_idx` | `primary_objects_packed_primary_provisional_designation_key` |

These waste disk space and slow every INSERT/UPDATE.

### 3. mpc_orbits: Intentional Denormalization

The 46 flat columns (q, e, i, uncertainties, etc.) are extracted copies of
values that also live inside the `mpc_orb_jsonb` JSONB blob.  Pragmatic for
query performance, but creates a consistency risk if the JSONB is updated
without updating flat columns (or vice versa).

### 4. Redundant Discovery Flags in obs_sbn

Both `disc` (character, `'*'`) and `designation_asterisk` (boolean) appear to
encode the same information.  Consistency between them has not been verified.

### 5. No Reference Tables for Integer Codes

`orbit_type_int` in mpc_orbits and `object_type` in primary_objects are bare
integers with no lookup table.  Known mappings (from external documentation):

**mpc_orbits.orbit_type_int:**

| Code | Type | Count |
|------|------|-------|
| 0 | Unclassified/Atira | 20 |
| 1 | Atira | 743 |
| 2 | Apollo | 4,578 |
| 3 | Aten | 3,191 |
| 10 | Mars-crossing | 12,287 |
| 11 | Main Belt | 935,419 |
| 12 | Hungaria (?) | 12,793 |
| 19 | Hilda (?) | 7,822 |
| 20 | Jupiter Trojan (?) | 2,427 |
| 21-23 | Distant objects (?) | 1,869 |
| 30 | Comet-like (?) | 38 |
| NULL | **No classification** | **529,661 (35%)** |

**primary_objects.object_type:**

| Code | Count |
|------|-------|
| 0 | 1,548,833 |
| 1 | 473 |
| 6 | 11 |
| 10 | 4,495 |
| 11 | 235 |
| 20 | 17 |
| 30 | 416 |
| 50 | 3 |
| NULL | 32 |

### 6. Inconsistent Naming Conventions

The neocp tables use `desig` (varchar) while catalog tables use
`packed_primary_provisional_designation` (text).  The neocp tables also lack
the unpacked form entirely.

---

## Data Gaps

### 7. orbit_type_int NULL for 35% of mpc_orbits

529,661 of 1.51M objects have computed orbits but no dynamical classification.
Many are probably classifiable from their existing orbital elements (a, e, i, q).

### 8. earth_moid Sparsely Populated

Only ~454K of 1.51M objects (~30%) have `earth_moid` in the flat columns.
Other planetary MOIDs (Mars, Venus, Jupiter) exist only in the JSONB
`moid_data` key and are not directly queryable.

### 9. Non-Gravitational Parameters Empty

| Column | Non-NULL count | Total |
|--------|---------------|-------|
| yarkovsky | 133 | 1.51M |
| srp | 0 | 1.51M |
| a1 | 0 | 1.51M |
| a2 | 0 | 1.51M |
| a3 | 0 | 1.51M |
| dt | 0 | 1.51M |

These may exist in the JSONB but haven't been extracted to flat columns.

### 10. No Precomputed Derived Physical Quantities

H magnitude exists, but there is no:
- Diameter or albedo
- Taxonomic class
- Tisserand parameter
- Synodic period or next-opposition date

### 11. No "Last Observed" Readily Available

Finding when an object was last observed requires `MAX(obstime)` across
obs_sbn — an expensive full scan on 526M rows.  No materialized summary exists.

### 12. Dirty Source Data in obscodes

- Trailing whitespace in `name` column
- Backslash-escaped apostrophes (`\'` instead of `'`)
- Already worked around in discovery_tracklets.sql via TRIM/REPLACE

---

## The mpc_orb_jsonb Structure

The JSONB blob contains 11 top-level keys with rich structure largely
inaccessible to SQL without extraction:

| Key | Contents |
|-----|----------|
| `CAR` | Full Cartesian state vectors (x,y,z,vx,vy,vz) + 6x6 covariance matrix + eigenvalues |
| `COM` | Cometary elements (q,e,i,node,argperi,peri_time) + 6x6 covariance matrix + eigenvalues |
| `epoch_data` | Epoch (MJD), timeform, timesystem |
| `system_data` | Ephemeris (DE431), reference system, reference frame |
| `software_data` | Fitting software version, fitting datetime, mpcorb version |
| `categorization` | orbit_type_int/str, object_type_int/str, orbit_subtype |
| `magnitude_data` | H, G, G1, G2, G12, photometric_model |
| `designation_data` | permid, iau_name, orbfit_name, packed/unpacked, secondary designations |
| `moid_data` | Mars, Earth, Venus, Jupiter MOIDs |
| `non_grav_booleans` | Flags: yarkovski, srp, marsden, yabushita, A1/A2/A3/DT |
| `orbit_fit_statistics` | nopp, U_param, nobs_total/sel, normalized_RMS, arc_length, orbit_quality, SNR |

The covariance matrices in `CAR` and `COM` are particularly valuable — they
encode the full uncertainty ellipsoid, not just 1D uncertainties.  This enables
proper ephemeris uncertainty propagation.

Several fields in the JSONB have no flat-column equivalent:
- `orbit_quality`, `SNR` (from `orbit_fit_statistics`)
- `G1`, `G2`, `G12` (from `magnitude_data`)
- `orbit_type_str`, `orbit_subtype` (from `categorization`)
- Mars/Venus/Jupiter MOIDs (from `moid_data`)
- Full covariance matrices (from `CAR` and `COM`)

---

## Value-Added Opportunities

### For the CSS Replicated Database

#### A. Materialize JSONB into Queryable Views

A materialized view extracting the most useful buried fields would make the
database dramatically more useful:

- All planetary MOIDs (not just Earth)
- Orbit quality score and SNR
- Human-readable orbit_type_str / object_type_str
- G1/G2/G12 photometric parameters
- Covariance matrix eigenvalues (uncertainty ellipsoid characterization)

#### B. Classify the 530K Unclassified Objects

The orbital elements exist — computing orbit_type_int from (a, e, i, q) is
straightforward dynamical classification.  A derived table or materialized
view could fill the gap for the 35% of objects with NULL orbit_type_int.

#### C. Compute and Cache a "Last Observed" Table

A materialized view of `(provid/permid, MAX(obstime), COUNT(*), last_stn)`
per object, refreshed periodically, would eliminate expensive obs_sbn scans
and enable recovery opportunity analysis.

#### D. Build a Tisserand Parameter Column

T_J = a_J/a + 2 * cos(i) * sqrt((a/a_J) * (1 - e^2))

Trivially computable from existing orbital elements.  The single most useful
dynamical discriminant: T_J < 3 implies cometary origin; T_J > 3 implies
asteroidal.  Critical for NEO population studies.

### For GitHub Derived Data Products

#### E. Observatory Performance Dashboard

Per-station metrics derivable from obs_sbn + discovery tracklets:

- Discovery count and rate over time (by month/year)
- Follow-up contribution (non-discovery observations of NEOs)
- Astrometric quality (median rmsra, rmsdec per station)
- Magnitude reach (faintest discoveries over time)
- Sky coverage patterns (using healpix or ra/dec)

Directly relevant to CSS's mission and competitive positioning.

#### F. NEO Population Completeness Analysis

Combining H-magnitude distributions with discovery dates:

- Cumulative discovery curves by H-magnitude bin
- Estimated completeness vs size (comparison to debiased models)
- Discovery rate trends — accelerating or plateauing at each H?

The fundamental question in planetary defense.

#### G. NEOCP Throughput Statistics

The neocp_events + neocp_prev_des tables track the full lifecycle:

- Time from NEOCP posting to designation
- Fraction confirmed as NEOs vs non-NEOs
- Follow-up response time by station
- "Lost" candidates (posted but never designated)

#### H. Recovery and Follow-Up Opportunity Table

Objects needing observations, ranked by urgency:

- Objects approaching opposition with large ephemeris uncertainty
- Short-arc objects (u_param >= 6) nearing the end of their observing window
- Objects with only single-opposition orbits approaching their next apparition

Requires ephemeris propagation (likely external to SQL).

#### I. Identification Network Analysis

The current_identifications and obs_alterations_redesignations tables encode
a rich history:

- How often are objects redesignated?
- Which surveys produce the most identifications?
- Mean time from discovery to identification with a known object

#### J. Observation Quality Metrics

From obs_sbn's rmsra/rmsdec/rmsfit/seeing/exp columns:

- Per-station astrometric performance over time
- Correlation of seeing/exposure with residual quality
- Identification of systematic biases by station or catalog

---

## Priority Assessment

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| High | E. Observatory performance | Direct CSS mission relevance | Medium |
| High | F. Completeness analysis | Fundamental planetary defense question | Medium |
| High | A. Materialize JSONB | Unlocks buried data for all queries | Medium |
| Medium | B. Classify unclassified objects | Fills 35% gap in orbit_type_int | Low |
| Medium | D. Tisserand parameter | Key dynamical discriminant | Low |
| Medium | C. Last-observed cache | Enables recovery analysis | Low |
| Medium | G. NEOCP throughput | Unique operational insight | Medium |
| Lower | H. Recovery opportunities | Requires ephemeris propagation | High |
| Lower | I. Identification network | Research interest | Medium |
| Lower | J. Observation quality | Station-level diagnostics | Medium |

---

## Replication Architecture

**Source:** https://sbnmpc.astro.umd.edu/MPC_database/replication-info.shtml

The CSS replica uses **logical replication** via PostgreSQL's built-in
publication/subscription system.  The MPC master publishes all publicly
distributed tables; the replica subscribes and receives decoded row changes
(INSERTs, UPDATEs, DELETEs) continuously.

### Subscriber Constraints (from MPC)

| Constraint | Threshold |
|------------|-----------|
| Maximum cumulative downtime | 14 days/year |
| Initial sync deadline | 3 days |
| XMIN lag before termination | 5% |
| Copies per institution (without approval) | 4 |
| Hardware | 24/7 capable (no laptops/hibernating) |

### What Logical Replication Allows Locally

Because the replica is a fully independent read-write database that happens to
receive changes from the publisher, the following are all safe:

- **Custom indexes** on replicated tables (explicitly confirmed by MPC docs)
- **Custom tables** in the local database
- **Functions and operators** (zero-cost catalog entries until called)
- **Views** (just catalog definitions; no replication interaction)
- **Materialized views** (refreshed locally, independent of replication)
- **Separate schemas** (e.g., `css_utilities`) for all local work

### Risks

**1. Apply-worker lag from index overhead.**  Every replicated INSERT/UPDATE/
DELETE must update all local indexes during the apply phase.  The apply worker
is single-threaded per table (standard logical replication).  Redundant indexes
directly increase apply time and risk breaching the 5% XMIN lag threshold.
This is why the 4 duplicate indexes (idx_obs_sbn_permid, idx_obs_sbn_provid,
idx_obs_sbn_trksub, primary_objects duplicate) were dropped on 2026-02-08.

**2. Schema is a "β release subject to modification."**  If MPC adds, removes,
or renames columns on replicated tables, any views, materialized views, or
queries referencing those columns will break.  Mitigation:

- Reference columns by name (never `SELECT *` in views or mat views)
- Materialized views fail gracefully (refresh fails, but existing data persists)
- Keep a schema version check or diff against expected column lists

**3. Downtime budget.**  14 days cumulative per year.  Expensive materialized
view refreshes should not be scheduled during catch-up periods after downtime.

**4. Trigger caution.**  `AFTER INSERT` triggers on replicated tables **do fire**
during logical replication apply.  Trigger errors halt replication entirely.
Periodic `REFRESH MATERIALIZED VIEW` is safer than incremental triggers for
derived data maintenance.

### Recommended Architecture for Derived Work

```
MPC/SBN replica (mpc_sbn database)
├── public schema          ← replicated tables (do not modify schema)
│   ├── obs_sbn            ← 526M+ rows, keep indexes minimal
│   ├── mpc_orbits         ← 1.51M rows
│   ├── primary_objects    ← 1.50M rows
│   └── ...                ← other MPC tables
│
└── css_utilities schema     ← local, non-replicated
    ├── MATERIALIZED VIEWS
    │   ├── neo_orbits_extended      (flat + extracted JSONB + Tisserand)
    │   ├── neo_last_observed        (permid/provid, max_obstime, count)
    │   └── observatory_stats        (per-station metrics)
    ├── FUNCTIONS
    │   ├── tisserand_jupiter(a, e, i)
    │   └── orbit_classify(a, e, i, q)
    └── TABLES
        └── orbit_type_lookup        (integer code → name mapping)
```

**Refresh strategy:** Cron-based `REFRESH MATERIALIZED VIEW CONCURRENTLY`
during low-activity periods (daytime Tucson time, when surveys are not
submitting observations).

**Monitoring:** A cron job checking `pg_stat_subscription` for replication
lag (`latest_end_lsn` vs publication LSN) provides early warning if local
work is impacting apply throughput.
