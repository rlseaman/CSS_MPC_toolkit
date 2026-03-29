# NEO List Reconciliation

**Started:** 2026-03-28
**Status:** Active investigation

## Motivation

The project computes NEO discovery statistics from the MPC PostgreSQL
database (mpc_sbn).  Comparing our database-derived counts against two
independent references — the MPC YearlyBreakdown page and the CNEOS
discovery statistics — reveals systematic discrepancies of 2–5% in total
counts and larger deviations for specific stations and projects.

Rather than tuning SQL WHERE clauses to minimize residuals, we need to
work from first principles: establish authoritative NEO lists, then
layer discovery attribution, orbital properties, and derived statistics
on top.

## Authoritative NEO Lists

Two independent sources maintain curated lists of Near-Earth Objects:

### MPC: NEA.txt

- URL: https://www.minorplanetcenter.net/iau/MPCORB/NEA.txt
- Maintained by the Minor Planet Center (IAU)
- Fixed-width format with packed designation, H, orbital elements
- Updated approximately daily
- Includes numbered and unnumbered NEAs
- Sentinel H = 99.99 means "unreliable / unknown"
- **This is the MPC's own definition of what is and isn't a NEA**
- Existing loader: `lib/nea_catalog.py` (currently used only for H
  magnitude overrides)

### JPL: Small-Body Database (SBDB)

- API: https://ssd-api.jpl.nasa.gov/sbdb_query.api
- Maintained by JPL/CNEOS
- RESTful JSON API with flexible query parameters
- Can query by orbital class (Aten, Apollo, Amor, Atira) or by
  element ranges
- Includes Earth MOID, PHA flag, and other derived quantities
- May differ from MPC on boundary objects and on orbit solutions
- Existing client: `lib/api_clients.py` (`fetch_sbdb`)

### Why two sources?

MPC and JPL maintain independent orbit solutions.  An object's
perihelion distance q may differ between the two at the milli-AU level,
which matters at the q = 1.3 AU boundary.  JPL also computes Earth
MOID independently, which affects PHA classification.  For most objects
(>99%) the two lists agree.  The disagreements are scientifically
informative.

## Architecture

### NEO list as a foundation layer

All downstream analysis — discovery statistics, completeness estimates,
size distributions, follow-up timing — depends on the NEO list.  The
list should be:

1. **Explicit** — a concrete set of designations, not an implicit
   database query
2. **Sourced** — each record tracks whether it came from NEA.txt,
   SBDB, or both
3. **Augmentable** — new discoveries (from MPECs or NEOCP) between
   the latest list snapshot and the current time can be added at
   runtime
4. **Selectable** — downstream tools can choose MPC-only, JPL-only,
   intersection, or union, depending on the analysis

### Proposed record schema

Each entry in the unified NEO list carries:

| Field | Description |
|---|---|
| `designation` | Unpacked provisional designation (primary key) |
| `packed_desig` | Packed MPC designation |
| `permid` | Permanent MPC number (if numbered) |
| `in_mpc` | Boolean: present in NEA.txt |
| `in_jpl` | Boolean: present in SBDB NEO query |
| `h_mpc` | H magnitude from NEA.txt |
| `h_jpl` | H magnitude from SBDB |
| `h_best` | Resolved H (preference TBD) |
| `q`, `e`, `i`, `a` | Orbital elements (source TBD) |
| `earth_moid_jpl` | Earth MOID from SBDB |
| `pha_mpc` | In PHA.txt |
| `pha_jpl` | PHA flag from SBDB |
| `orbit_class` | Atira/Aten/Apollo/Amor (computed from elements) |
| `source` | Provenance: "mpc", "jpl", "both", "mpec" |
| `list_date` | Timestamp of the source list snapshot |

### Runtime augmentation

Between daily list updates, new NEOs are announced via MPECs.  The
MPEC browser (Tab 0) already parses discovery MPECs and extracts
designations.  A future enhancement could:

1. Check each new MPEC designation against the current NEO list
2. If absent, fetch a preliminary orbit from NEOfixer or MPC
3. Add to the list with `source = "mpec"` and a provisional flag
4. On the next daily refresh, the entry is either confirmed (appears
   in NEA.txt/SBDB) or dropped

## Investigation Plan

### Step 1: Establish the NEO list baseline

- Download NEA.txt and count objects
- Query SBDB for all NEOs and count objects
- Compare counts to:
  - Our database query (`mpc_orbits WHERE q <= 1.30`): ~41,500
  - MPC YearlyBreakdown total: ~40,970
  - CNEOS discovery statistics total: ~41,040
- Identify the object-level deltas (in one list but not the other)

### Step 2: Cross-match NEA.txt against mpc_orbits

- Which NEA.txt objects have `q > 1.30` in mpc_orbits?
  (boundary objects, stale orbits, comets)
- Which `q <= 1.30` objects in mpc_orbits are absent from NEA.txt?
  (non-NEA objects with low q, e.g. comets, misclassifications)
- Are there NEA.txt objects with no row in mpc_orbits at all?

### Step 3: Check discovery matching completeness

- Starting from the NEA.txt list, how many can we match to a
  `disc = '*'` observation in obs_sbn?
- Known gaps: 2009 US19 and 2024 TZ7 have no disc='*' (reported
  to MPC as of 2026-02-07)
- Are there others?  This is the "lost discoveries" count.

### Step 4: Validate station credit

- Objects with `disc = '*'` at multiple stations on the same night
  — who gets credit?
- Objects where our three-branch UNION matches a different station
  than the MPC page credits
- Objects recently numbered where `numbered_identifications` may lag

### Step 5: Reconcile H magnitudes

- Compare mpc_orbits.h vs NEA.txt H vs SBDB H
- Quantify sentinel values (0, -9.99, 99.99)
- Impact on 1km (H < 17.75) and H < 22 counts
- Currently using NEA.txt override in the app; validate this choice

### Step 6: Reconcile PHA status

- PHA.txt (MPC) vs SBDB PHA flag vs database-derived
  (H <= 22 AND earth_moid <= 0.05)
- mpc_orbits.earth_moid is NULL for ~70% — PHA.txt is essential
- SBDB provides earth_moid for ~99.7% of NEOs

### Step 7: Database normalization audit

- Referential integrity: numbered_identifications completeness,
  current_identifications coverage
- Duplicate designations in mpc_orbits
- Orphaned observations (disc='*' with no matching orbit)
- Orphaned orbits (mpc_orbits row with no observations)
- Text-field join consistency (packed vs unpacked, trailing spaces)

## Current Findings (2026-03-28)

### Step 1 results: per-object NEO list reconciliation

Built `lib/neo_list.py` to download both MPC NEA.txt and JPL SBDB,
parse every object, and cross-match by designation.

| Source | Count |
|---|---|
| MPC NEA.txt | 41,372 |
| JPL SBDB (IEO+ATE+APO+AMO) | 41,350 |
| **Unified (union)** | **41,397** |
| In both sources | 41,325 (99.8%) |
| MPC only | 47 |
| JPL only | 25 |
| H differs by >0.5 mag | 22 of 41,323 with both H |

The two authoritative sources agree on >99.8% of objects.

**47 MPC-only objects:**  Mostly 2010-era objects, many Atens with
q near 0.8–0.9.  Likely objects JPL has reclassified after orbit
refinement, or with stale orbits that JPL has removed.

**25 JPL-only objects:**  Mostly Amors with q very close to 1.3 AU
(boundary objects where milli-AU orbit differences determine NEO
status), plus 3 very recent 2026 discoveries not yet in NEA.txt.

**H magnitude discrepancies:**  Only 22 objects differ by >0.5 mag,
mostly faint (H > 23) objects where H is poorly determined.  The
largest discrepancy is 2017 SC33 (MPC: 20.0, JPL: 22.14, diff 2.14).

### Three-way discovery count comparison

Using `sql/yearly_breakdown.sql` (WHERE q <= 1.30, no orbit_type_int
filter) against the MPC YearlyBreakdown page and CNEOS CSV:

| Source | Total NEOs | Notes |
|---|---|---|
| DB query (q <= 1.30) | ~41,509 | Named projects sum to 39,374 |
| MPC YearlyBreakdown | ~40,970 | Human-curated web page |
| CNEOS Discovery Stats | ~41,040 | JPL-curated, 1995–2026 |

### Project-level comparison (DB vs MPC YearlyBreakdown)

| Project | DB | MPC | Diff | |
|---|---|---|---|---|
| Catalina Survey | 17,515 | 17,468 | +47 | close |
| Pan-STARRS | 13,185 | 13,116 | +69 | close |
| LINEAR | 2,714 | 2,685 | +29 | close |
| ATLAS | 1,371 | 1,350 | +21 | close |
| Spacewatch | 950 | 928 | +22 | close |
| NEAT | 442 | 442 | 0 | exact |
| LONEOS | 289 | 289 | 0 | exact |
| **NEOWISE** | **481** | **348** | **+133** | outlier |

NEOWISE (C51) is the largest single-project discrepancy.  The CNEOS
page also shows 394 for NEOWISE (+46 over MPC), suggesting MPC's
YearlyBreakdown may under-count C51 relative to both JPL and the
raw database.

### Evolution of the DB query

Initially used `WHERE q <= 1.30 OR orbit_type_int IN (0,1,2,3,20)`.
The orbit_type_int clause pulled in ~2,300 extra objects (mostly
type 20 Jupiter-coupled), inflating totals to 43,801.  Removing it
brought the total to 41,509, much closer to the authoritative lists.

### Known database issues affecting counts

- `orbit_type_int` NULL for ~35% of mpc_orbits — recovered by
  `classify_from_elements()` in the app, not available in raw SQL
  without installing the classification function
- `earth_moid` NULL for ~70% — PHA counts from database are unreliable
- `mpc_orbits.h` contains sentinel values (0, -9.99) — inflate
  1km counts if not filtered
- No foreign keys anywhere in the schema — join mismatches are silent
- `disc = '*'` flag missing for at least 2 known NEOs

### Tools built

- `lib/neo_list.py` — unified NEO list builder (MPC + JPL), cached
  as `.neo_list.parquet`.  CLI with `--mpc-only`, `--jpl-only`,
  `--h-diff` filters.
- `scripts/yearly_breakdown.py` — parses MPC YearlyBreakdown HTML,
  station/project summaries with dynamic Independent Survey
  classification.
- `sql/yearly_breakdown.sql` — DB query for per-station/year NEO
  discovery counts with orbit class and size breakdowns.
