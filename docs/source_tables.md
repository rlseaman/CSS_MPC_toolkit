# Source Tables: MPC/SBN Database

## Overview

The SQL scripts in this project query the MPC/SBN PostgreSQL database, a
replica of the [Minor Planet Center's](https://www.minorplanetcenter.net)
observation and orbit catalogs distributed through the
[PDS Small Bodies Node](https://sbnmpc.astro.umd.edu) (SBN).

- Schema docs: https://www.minorplanetcenter.net/mpcops/documentation/replicated-tables-schema/
- General info: https://www.minorplanetcenter.net/mpcops/documentation/replicated-tables-info-general/

**Database name:** `mpc_sbn`

## Tables Used by This Project

### mpc_orbits

Orbital elements for minor planets. One row per object. Used to identify
NEOs by orbital criteria rather than requiring an external NEA list download.

**Columns used:**

| Column | Type | Description |
|--------|------|-------------|
| `packed_primary_provisional_designation` | text | Primary designation (packed, unique key) |
| `unpacked_primary_provisional_designation` | text | Primary designation (human-readable) |
| `q` | double precision | Perihelion distance (au) |
| `orbit_type_int` | integer | MPC orbital classification (nullable; NULL for 35%) |

**NEO selection criteria:** `q < 1.32 OR orbit_type_int IN (0, 1, 2, 3, 20)`

**Caveats:** `orbit_type_int` is NULL for ~530K of 1.51M objects. These are
objects with computed orbits but no MPC classification. The perihelion
criterion (`q < 1.32`) catches NEOs regardless of classification status.

### obs_sbn

The primary observation table. Each row is a single astrometric observation
of a solar system object. This is the largest table in the database.

**Columns used:**

| Column | Type | Description |
|--------|------|-------------|
| `permid` | text | Permanent (numbered) designation, e.g., `"433"` |
| `provid` | text | Provisional designation, e.g., `"2024 AA1"` |
| `trksub` | text | Observer-assigned tracklet identifier (nullable; ~7% of discovery obs are NULL) |
| `stn` | text | MPC observatory code, e.g., `"703"` (Catalina) |
| `obstime` | timestamp(6) | Observation timestamp (UTC, no timezone) |
| `ra` | numeric | Right Ascension in decimal degrees (J2000) |
| `dec` | numeric | Declination in decimal degrees (J2000) |
| `mag` | numeric | Reported apparent magnitude (nullable) |
| `band` | text | Photometric band code (e.g., `'V'`, `'G'`, `'o'`) |
| `disc` | char(1) | Discovery flag: `'*'` marks the discovery observation |

**Key behaviors:**
- An object's observations may be stored under `permid` (if numbered),
  `provid` (provisional designation), or both
- The `disc = '*'` flag marks the observation designated as the discovery
  observation by the MPC
- `trksub` groups observations into tracklets; when NULL, tracklet
  membership cannot be determined from this field alone

### numbered_identifications

Cross-reference between permanent numbers and provisional designations.
One row per numbered object. This is the authoritative source for mapping
a numbered asteroid to its principal provisional designation.

**Columns used:**

| Column | Type | Description |
|--------|------|-------------|
| `permid` | text | The permanent number as a string, e.g., `"433"` |
| `packed_primary_provisional_designation` | text | Packed form, e.g., `"A898P00A"` |
| `unpacked_primary_provisional_designation` | text | Unpacked form, e.g., `"1898 PA"` |

**Key behaviors:**
- Continuously updated as new objects receive numbered designations
- Links to `current_identifications` via the provisional designation fields
- Used in preference to `mpc_orbits` for designation lookup because
  `numbered_identifications` is fully populated while `mpc_orbits` is
  partially populated and undergoing consistency work

### obscodes

Observatory metadata. One row per MPC observatory code. Used to enrich
discovery tracklet output with human-readable observatory names.

**Columns used:**

| Column | Type | Description |
|--------|------|-------------|
| `obscode` | varchar(4) | MPC station code, e.g., `"703"` (unique) |
| `name` | varchar | Observatory name |

### NEOCP Tables (for ADES Export)

Six tables track the NEO Confirmation Page lifecycle. Used by
`lib/ades_export.py` and `sql/ades_export.sql`.

**neocp_obs_archive** -- Archived observations (777K rows)

| Column | Type | Description |
|--------|------|-------------|
| `desig` | varchar(16) | Temporary NEOCP designation |
| `trkid` | text | Tracklet ID (links to obs_sbn) |
| `obs80` | varchar(255) | Full 80-column MPC format observation line |
| `rmsra` | numeric | RA*cos(Dec) uncertainty in arcsec (ADES-native) |
| `rmsdec` | numeric | Dec uncertainty in arcsec (ADES-native) |
| `rmscorr` | numeric | RA-Dec correlation (ADES-native) |
| `rmstime` | numeric | Time uncertainty in seconds (ADES-native) |
| `created_at` | timestamp | Database ingestion time |

**neocp_prev_des** -- Designation resolution after NEOCP removal (71K rows)

| Column | Type | Description |
|--------|------|-------------|
| `desig` | text | Temporary NEOCP designation |
| `iau_desig` | text | Final IAU designation (e.g., '2024 YR4') |
| `pkd_desig` | text | Packed MPC designation |
| `status` | text | Outcome: empty (designated), 'lost', 'dne', etc. |

**neocp_events** -- Audit log (310K rows)

| Column | Type | Description |
|--------|------|-------------|
| `desig` | text | NEOCP designation |
| `event_type` | text | ADDOBJ, UPDOBJ, REDOOBJ, REMOBJ, FLAG, COMBINEOBJ, REMOBS |
| `event_user` | text | Operator or automated process name |

All NEOCP tables join on `desig`. See `sandbox/neocp_ades_analysis.md` for
full schema details, join paths, and latency analysis.

## Tables Available for Future Use

### current_identifications

Links primary provisional designations to all secondary (linked) designations.
Each object may appear multiple times — once per secondary designation.

| Column | Type | Description |
|--------|------|-------------|
| `packed_primary_provisional_designation` | text | Primary designation (packed) |
| `unpacked_primary_provisional_designation` | text | Primary designation (unpacked) |
| `packed_secondary_provisional_designation` | text | Secondary designation (packed) |
| `unpacked_secondary_provisional_designation` | text | Secondary designation (unpacked) |
| `numbered` | boolean | Whether the primary designation is also numbered |
| `object_type` | integer | Object classification |

**Potential use:** Fallback matching for observations stored under a secondary
designation that doesn't match the primary designation in NEA.txt.

### primary_objects

One row per designated object. Contains orbit status flags and object type.

| Column | Type | Description |
|--------|------|-------------|
| `packed_primary_provisional_designation` | text | Primary designation (packed) |
| `object_type` | integer | Object classification code |
| `no_orbit` | boolean | True if no orbit could be computed |
| `orbit_published` | integer | Publication status (0=unpublished, 1=MPEC, etc.) |

**Potential use:** Filter NEAs by `object_type` instead of downloading NEA.txt.

### obscodes (additional columns)

Now used by discovery_tracklets for `obscode` and `name` (see above).
Additional columns available for future use:

| Column | Type | Description |
|--------|------|-------------|
| `longitude` | numeric | Degrees east of Greenwich |
| `rhocosphi` | numeric | Geocentric parallax constant |
| `rhosinphi` | numeric | Geocentric parallax constant |
| `observations_type` | varchar(255) | Type: optical, radar, satellite, occultation |

**Potential use:** Enrich with observatory location or filter by type.

### mpc_orbits (additional columns)

Now used for NEO selection (see above). Additional columns available:

| Column | Type | Description |
|--------|------|-------------|
| `a`, `e`, `i`, `node`, `argperi` | double precision | Keplerian orbital elements |
| `h`, `g` | double precision | Absolute magnitude and slope parameter |
| `earth_moid` | double precision | Minimum orbit intersection distance (au) |
| `mpc_orb_jsonb` | jsonb | Complete MPC JSON orbit data (11 top-level keys) |

**Potential use:** Earth MOID-based risk ranking, Tisserand parameter
computation, covariance extraction from JSONB. See `sandbox/schema_review.md`
for JSONB structure analysis.

## Recommended Indexes

See [`sql/common/indexes.sql`](../sql/common/indexes.sql) for index
definitions that improve query performance. These are safe to create on a
read-only replica. Note the MPC's warning: excessive indexing can cause
replication lag.

## Data Sources

- **Minor Planet Center:** https://www.minorplanetcenter.net
- **PDS Small Bodies Node (SBN-MPC):** https://sbnmpc.astro.umd.edu
- **Catalina Sky Survey:** https://catalina.lpl.arizona.edu
- **NEA.txt catalog:** https://minorplanetcenter.net/iau/MPCORB/NEA.txt
