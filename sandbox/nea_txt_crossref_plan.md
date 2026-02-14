# Plan: NEA.txt as Authoritative H Magnitude Cross-Reference

## Problem

`mpc_orbits.h` contains unreliable values — plausible-looking magnitudes
(e.g. 15.9, 16.7) for objects where the MPC's own curated NEA.txt says
H=99.99 (unknown). There are also ~3,800 objects in mpc_orbits with
q <= 1.3 that aren't in NEA.txt at all. The MPC has confirmed that
NEA.txt is the more reliable source pending further work on the
PostgreSQL tables.

## Investigation Summary (2026-02-14)

NEOWISE 2010 case study: our dashboard showed 20 H<18 discoveries vs
CNEOS's 7. After filtering H<=0 sentinels and adjusting the size-class
boundary to H=17.75 (canonical p_v=0.14), 15 remained. Of those:

- 5 have H=99.99 in NEA.txt (unreliable H in mpc_orbits)
- 5 are absent from NEA.txt entirely (not confirmed NEAs)
- ~7 match CNEOS, with consistent H values in both sources

The broader comparison: 40,349 NEAs in NEA.txt vs 41,062 with q<=1.3 in
mpc_orbits. ~3,100 objects in each direction don't match, largely due to
designation aliasing (packed number vs packed provisional), but also
genuine differences.

## Approach

Add a lightweight NEA.txt ingestion step to the data pipeline, used to
validate and override H magnitudes.

## Implementation

### 1. New library function

In `lib/orbits.py` (or a new `lib/nea_catalog.py`):

- `load_nea_catalog(url_or_path)` — downloads/reads NEA.txt, parses the
  fixed-width MPCORB format, returns a DataFrame with columns:
  `packed_desig`, `h_nea`, `g`, `epoch`, etc.
- Handles both packed-number designations (e.g. `e4108`) and
  packed-provisional (e.g. `K10KF7F`)
- Treats H=99.99 as NaN

### 2. Designation resolution

The key challenge is matching mpc_orbits rows (keyed by provisional
packed designation) to NEA.txt rows (keyed by either packed number or
packed provisional). We already have `numbered_identifications` to
bridge these. The merge would be:

- Join mpc_orbits packed_desig -> numbered_identifications -> packed
  number -> NEA.txt
- Fall back to direct packed_desig match for unnumbered objects

### 3. Integration into load_data()

After loading the cached discovery query:

- Load/cache NEA.txt (download daily or use a local copy; same 1-day
  cache pattern)
- Merge on packed designation (resolved through numbering)
- Replace `h` with `h_nea` where available; set to NaN where NEA.txt
  has 99.99 or object is absent
- Flag objects not in NEA.txt (they may not be confirmed NEAs)

### 4. Cache strategy

NEA.txt is ~6 MB, updates daily. Cache it alongside the existing CSV
caches with the same 1-day invalidation. Download from
`https://minorplanetcenter.net/iau/MPCORB/NEA.txt`.

### 5. Dashboard impact

- The NEOWISE 2010 spike drops to match CNEOS
- A small number of objects gain a "not in NEA catalog" flag — these
  could be shown in tooltips or excluded from size-class filters
- The total NEO count may shift slightly

### 6. Reversibility

When MPC finishes the mpc_orbits work, we can remove the NEA.txt
override and fall back to the database values. The cross-reference
code stays useful for validation.

## What this does NOT change

- NEOMOD3 bins and comparisons (those use their own H bin edges)
- The SQL queries themselves (still query mpc_orbits for orbits,
  obs_sbn for observations)
- The apparition data pipeline

## Estimated scope

~100-150 lines of new code (parser + merge logic), plus minor
modifications to `load_data()`. No new dependencies — just `pandas`
and `urllib` for the download.
