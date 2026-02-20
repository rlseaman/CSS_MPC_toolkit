# Designation Resolution Analysis

## Problem

MPECs reference objects by their designation at time of publication. Over time,
objects get:
- **Linked**: multiple provisional designations found to be the same object
  (secondary → primary)
- **Numbered**: assigned a permanent MPC number once the orbit is well-determined
- **Named**: given an IAU name (a subset of numbered asteroids)

A 1993 MPEC referencing "1977 QQ5" is actually asteroid (7977). External links
(SBDB, Sentry, NEOfixer) may not resolve the historical designation correctly.

## Database Tables

### `current_identifications` (2,044,537 rows)

Maps every known designation (as a "secondary") to its current primary
provisional designation. Self-referencing rows (primary = secondary) exist for
all primary designations.

| Column | Type | Indexed | Notes |
|--------|------|---------|-------|
| `packed_primary_provisional_designation` | text | btree | 7-char packed form |
| `packed_secondary_provisional_designation` | text | **unique btree** | lookup key |
| `unpacked_primary_provisional_designation` | text | | human-readable |
| `unpacked_secondary_provisional_designation` | text | | human-readable |
| `numbered` | boolean | | whether primary has a permanent number |

**Key stats:**
- 484,278 rows where primary != secondary (actual merges)
- 1,321,540 rows marked as numbered
- Includes comets (C/, P/, D/), asteroids, and cross-type identifications
  (e.g., asteroid designation linked to comet: `2000 OZ21 → P/2022 M1`)

### `numbered_identifications` (875,981 rows)

Maps primary provisional designations to permanent numbers and names.

| Column | Type | Indexed | Notes |
|--------|------|---------|-------|
| `packed_primary_provisional_designation` | text | **unique btree** | join key |
| `unpacked_primary_provisional_designation` | text | **unique btree** | |
| `permid` | text | **unique btree** | permanent number as string |
| `iau_name` | text | **unique btree** | e.g., "Eros" (often NULL) |

## Resolution Chain

Given an MPEC designation (e.g., "1977 QQ5"):

```
Step 1: Pack designation
  "1977 QQ5" → "J77Q05Q" (via mpc_designation.pack())

Step 2: Look up in current_identifications (by secondary)
  packed_secondary = "J77Q05Q"
  → packed_primary = "J77Q05Q", unpacked_primary = "1977 QQ5"
  → numbered = true
  (In this case primary = secondary, so it's already the primary designation)

Step 3: Look up in numbered_identifications (by primary)
  packed_primary = "J77Q05Q"
  → permid = "7977", iau_name = NULL

Result: 1977 QQ5 is (7977), no IAU name
```

For a merged designation:
```
"1981 EG6" → packed "J81E06G"
  → current_identifications: primary = "K13N03B" = "2013 NB3"
  → numbered_identifications: permid exists (numbered = true)

Result: 1981 EG6 → 2013 NB3 → (number)
```

## Edge Cases

| Case | Detection | Handling |
|------|-----------|----------|
| Already primary, unnumbered | primary = secondary, numbered = false | Nothing to display |
| Already primary, numbered | primary = secondary, numbered = true | Show `= (number)` |
| Secondary, unnumbered | primary != secondary, numbered = false | Show `= primary_desig` |
| Secondary, numbered | primary != secondary, numbered = true | Show `= primary = (number)` |
| Permanent number input | `detect_format` returns `permanent` | Query `numbered_identifications` by `permid` |
| Comet designation | `mpc_designation.pack()` handles C/P/D/A/I | Same chain via packed form |
| Not in database | No row returned | Graceful fallback, show nothing |
| Invalid designation | `mpc_designation.pack()` raises error | Catch exception, show nothing |

## Performance

Both tables have unique btree indexes on packed designation columns. Individual
lookups are <1ms. A lazy cache (Python dict) ensures each designation is looked
up at most once per server process lifetime.

## `mpc_designation` Library

Installed from `git+https://github.com/rlseaman/MPC_designations.git`.

Key functions used:
- `pack(designation)` → packed 7-char form (asteroids, comets, satellites)
- `detect_format(designation)` → dict with `format`, `type`, `subtype`
- `is_valid_designation(designation)` → bool (non-throwing validation)

Advantages over `lib/mpc_convert.py`:
- Handles comets (C/, P/, D/, A/, I/ prefixes)
- Handles natural satellites (S/ prefix)
- Handles survey designations (P-L, T-1, T-2, T-3)
- Handles extended format (cycle >= 620)
- Auto-detects designation type

## Existing Codebase Patterns

### `lib/nea_catalog.py`
Already uses `mpc_designation.unpack()` and bulk-loads `numbered_identifications`
(~876K rows in ~1s) to resolve NEA.txt entries. This batch approach is
appropriate for startup; the lazy cache approach is better for on-demand MPEC
browsing.

### `sql/discovery_tracklets.sql`
Uses LEFT JOIN on `numbered_identifications` via
`packed_primary_provisional_designation` for the discovery statistics query.
Three-branch UNION strategy for observation lookups (by permid, by provid, by
numbered provid).

### `lib/mpc_convert.py`
Provides `pack_designation()` and `unpack_designation()` for asteroids only.
Used in `_build_mpec_detail` for external link construction. Will be augmented
(not replaced) by `mpc_designation.pack()` for the identification lookup.

## Proposed Display Format

On summary line 1 (same flex row as designation and badges), pushed to far right:

```
[MPEC desig]  [badges...]          = primary_desig = (number) Name
                                    ↑ only if secondary  ↑ only if named
```

Examples:
  1981 EG6  Discovery  Amor       = 2013 NB3 = (12345)
  1977 QQ5  Recovery               = (7977)
  2024 YR4  Discovery  Apollo PHA  = (number) if numbered
  2026 CE3  Discovery  Apollo      (nothing — too new to be numbered)
