# Source Tables: MPC/SBN Database

## Overview

The SQL scripts in this project query the MPC/SBN PostgreSQL database, a
replica of the Minor Planet Center's observation and orbit catalogs
distributed through the PDS Small Bodies Node.

**Database name:** `mpc_sbn`

## Required Tables

### obs_sbn

The primary observation table. Each row is a single astrometric observation
of a solar system object.

**Columns used by this project:**

| Column | Type | Description |
|--------|------|-------------|
| `permid` | text | Permanent (numbered) designation, e.g., `"433"` |
| `provid` | text | Provisional designation, e.g., `"2024 AA1"` |
| `trksub` | text | Tracklet submission identifier (nullable; ~7% of discovery obs are NULL) |
| `stn` | text | MPC observatory code, e.g., `"703"` (Catalina) |
| `obstime` | timestamp(6) | Observation timestamp (UTC, no timezone) |
| `ra` | numeric | Right Ascension in decimal degrees |
| `dec` | numeric | Declination in decimal degrees |
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

### mpc_orbits

Orbital elements for all cataloged objects. One row per object.

**Columns used by this project:**

| Column | Type | Description |
|--------|------|-------------|
| `packed_primary_provisional_designation` | text | Packed MPC designation (unique key) |
| `unpacked_primary_provisional_designation` | text | Human-readable designation |

**Key behaviors:**
- This table links packed designations to unpacked (readable) designations
- For numbered asteroids, provides the principal provisional designation
  used to locate discovery observations stored under `provid` in obs_sbn

## Recommended Indexes

See [`sql/common/indexes.sql`](../sql/common/indexes.sql) for index
definitions that improve query performance. These are safe to create on a
read-only replica.

## Data Source

- **MPC Observations:** https://minorplanetcenter.net/
- **PDS Small Bodies Node:** https://pds-smallbodies.astro.umd.edu/
- **NEA.txt catalog:** https://minorplanetcenter.net/iau/MPCORB/NEA.txt
