# NEO Consensus Schema and Pipeline

**Status:** v1 in production on Gizmo as of 2026-04-26.
**Schema:** `css_neo_consensus` in the local `mpc_sbn` database.
**Predecessor:** [`neo_list_reconciliation.md`](neo_list_reconciliation.md)
documented the original need; this doc covers what was built.

## Purpose

A per-object membership ledger that records which authoritative NEO
catalogs recognize each object as a Near-Earth Object. v1 stores
membership facts only — designation × source × timestamps — without
per-source metadata (H, MOID, orbit class, etc.); those join from
`mpc_sbn` or future per-source tables on demand.

The principle (per [`memory/neo_list_design.md`](../) — read by Claude
sessions): **per-object provenance, never aggregate counts.** Each NEO
carries side-by-side flags showing which sources include it.

## Sources

Six sources, each with its own orbit-fitting paradigm:

| Source identifier | Provider | URL / source | Filter | Rows |
|---|---|---|---|---:|
| `mpc` | Minor Planet Center | `https://minorplanetcenter.net/iau/MPCORB/NEA.txt` | curated NEA list (asteroid-by-syntax) | 41,587 |
| `mpc_orbits` | MPC | local query against `public.mpc_orbits` | q ≤ 1.3 ∧ e < 1, asteroid + A/ only | 41,667 |
| `cneos` | JPL | `ssd-api.jpl.nasa.gov/sbdb_query.api?sb-class=IEO,ATE,APO,AMO` | NEO orbit classes | 41,577 |
| `neocc` | ESA | `neo.ssa.esa.int/PSDB-portlet/download?file=allneo.lst` | full asteroid catalog | 41,595 |
| `neofixer` | U. Arizona | `neofixerapi.arizona.edu/targets/?site=500&q-max=1.3` | post-filtered: drop NEOCP candidates and rows where find_orb q > 1.3 | 41,638 |
| `lowell` | Lowell Observatory | `ftp.lowell.edu/pub/elgb/astorb.dat.gz` | computed q ≤ 1.3 ∧ e < 1 | 41,596 |

(Counts as of 2026-04-26 snapshot.)

### Source quirks worth knowing about

**`cneos`** strips the `A/` prefix from the `pdes` field for
asteroid-on-cometary-orbit objects (e.g. CNEOS reports `2019 Q2` for
`A/2019 Q2`). The ingestor falls back to extracting the parenthesized
form from `full_name` when `pdes` doesn't canonicalize — see
`lib/neo_consensus_cneos.py::_extract_from_full_name`.

**`neocc`** writes provisional designations without the IAU-standard
space (`"2026HZ1"` instead of `"2026 HZ1"`, `"6344P-L"` instead of
`"6344 P-L"`). A single regex `^(\d+)([A-Z].*)$` inserts the space
before `mpc-designation` parses.

**`neofixer`** mixes formally-designated NEOs with NEOCP candidates
and lets Mars-Crossers leak past its `q-max=1.3` URL parameter
(advisory, not strict). Both filters are enforced client-side using
the per-row `neocp` boolean and `q` field. NEOfixer is also the only
source carrying near-Earth comets (164 NECs in the snapshot).

**`lowell`** has no explicit q column. We compute `q = a(1 − e)`. The
catalog's web docs quote a FORTRAN format string that doesn't match
actual byte positions (likely a 2018 revision the docs missed); use
the empirically-verified column slices in
`lib/neo_consensus_lowell.py` (e at 159–168, a at 170–181). Verified
against Eros, Apollo, Apophis, Ceres before deploying.

## Schema

Two tables, three views. SQL DDL: [`sql/consensus/install.sql`](../sql/consensus/install.sql).

```
css_neo_consensus.source_membership
    source            TEXT     -- 'mpc' | 'cneos' | 'neocc' | 'neofixer' | 'mpc_orbits' | 'lowell'
    primary_desig     TEXT     -- canonical: unpacked primary provisional ('1932 HA')
    packed_desig      TEXT     -- packed primary provisional ('J32H00A')
    permid            TEXT     -- nullable; for numbered NEOs ('433', '99942', '780896')
    raw_string        TEXT     -- whatever the source emitted, pre-canonicalization
    desig_parsed      BOOL     -- TRUE if mpc-designation accepted the source string
    orbit_in_mpc      BOOL     -- TRUE if mpc_orbits has a row for primary_desig
    is_comet          BOOL     -- detected from designation form (C/, P/, D/)
    first_seen        TIMESTAMPTZ
    last_seen         TIMESTAMPTZ
    last_refreshed    TIMESTAMPTZ
    PRIMARY KEY (source, primary_desig)

css_neo_consensus.source_runs
    source         TEXT
    started_at     TIMESTAMPTZ
    finished_at    TIMESTAMPTZ
    status         TEXT  -- 'running' | 'ok' | 'fail' | 'partial'
    n_rows         INT
    n_unresolved   INT
    error_text     TEXT
    PRIMARY KEY (source, started_at)
```

Views:

- **`v_membership_wide`** — pivot to one row per asteroid with
  per-source booleans (`in_mpc`, `in_cneos`, …). Comets filtered out
  by default. Drives boolean cross-source predicates.
- **`v_member_designations`** — every alias for objects in
  `source_membership`: primary, secondaries via
  `current_identifications`, permid via `numbered_identifications`.
  One row per (primary, alias, kind) tuple.
- **`v_source_health`** — per-source recency summary. Watch
  `time_since_last_ok` for staleness alerts.

## Two design choices to keep in mind

1. **Canonical key = unpacked primary provisional** (e.g. "1932 HA"
   for Apollo, NOT the permid 1862). `permid` is auxiliary. Numbering
   an object does NOT migrate its row — its `primary_desig` was
   already its provisional, and it remains so.

2. **`desig_parsed` and `orbit_in_mpc` are SEPARATE booleans.** A
   designation can parse cleanly via `mpc-designation` without yet
   appearing in `mpc_orbits` — e.g. NEOCC virtual-impactor candidates,
   or recent NEOs MPC has fit but Gizmo's logical replication hasn't
   propagated. Don't conflate.

## Ingestion

Each source has an ingestor at `lib/neo_consensus_<source>.py`
implementing a single function `ingest_<source>(conn, cache_dir) ->
(n_upserted, n_unresolved)`. The shared canonicalization helpers and
upsert primitives live in [`lib/neo_consensus.py`](../lib/neo_consensus.py).

Per-source ingest pattern:

```
fetch raw            HTTP/local file
parse                source-specific extractor → list of raw designation strings
canonicalize         mpc-designation + numbered_identifications lookup
                     → Canonical(primary_desig, packed_desig, permid, …)
upsert               INSERT … ON CONFLICT (source, primary_desig) DO UPDATE
                     → updates last_seen and last_refreshed
log run              source_runs gets the terminal status row
```

CLI: [`scripts/ingest_neo_consensus.py`](../scripts/ingest_neo_consensus.py)
dispatches by source name.

```
ssh robertseaman@192.168.0.157 \
    'cd ~/CSS_MPC_toolkit && \
     ./venv/bin/python scripts/ingest_neo_consensus.py <source>'
```

Available sources: `mpc`, `cneos`, `neocc`, `neofixer`, `mpc_orbits`,
`lowell`.

## Daily refresh

All six sources refresh as **stage 4 of `refresh_matview_gizmo.sh`**,
inside the existing `org.seaman.gizmo-refresh` launchd agent at 06:00
MST. Bundled, sequential, best-effort: a single source's failure
(NEOCC outage, NEOfixer API blip) doesn't fail the wrapper. Per-source
status surfaces in:

- The daily run's status JSON: `"consensus": {source: "ok"|"fail"}`
  and `"stage4_s": <seconds>`.
- `css_neo_consensus.source_runs` rows.
- `v_source_health` for time-since-last-ok diagnostics.

Total stage-4 wall clock: ~25 s for all six sources.

**Stage 5** then runs `REFRESH MATERIALIZED VIEW CONCURRENTLY
css_neo_consensus.obs_summary` (~5 min on Gizmo, best-effort). This
matview pre-aggregates `obs_sbn` into per-NEO `first_obs / last_obs
/ arc_days / nobs`, keyed on `primary_desig`. The dashboard's NEO
Consensus tab joins it directly, replacing a per-target LATERAL
that was prohibitively expensive at full population scale (~3 min
for the all-six-agree set; see "Dashboard surface" below). Status
JSON carries `"obs_summary": "ok"|"fail"` and `"stage5_s"`.

## Use cases

```sql
-- "What's MPC's NEO list?"
SELECT primary_desig FROM css_neo_consensus.source_membership
 WHERE source='mpc';

-- "Is <designation> in MPC's list?"
SELECT EXISTS (SELECT 1 FROM css_neo_consensus.source_membership
               WHERE source='mpc' AND primary_desig = $1);

-- "Update NEOCC."
$ python scripts/ingest_neo_consensus.py neocc

-- "Common to all six sources."
SELECT primary_desig FROM css_neo_consensus.v_membership_wide
 WHERE in_mpc AND in_mpc_orbits AND in_cneos AND in_neocc
   AND in_neofixer AND in_lowell;

-- "<designation> in any source?"
SELECT EXISTS (SELECT 1 FROM css_neo_consensus.source_membership
               WHERE primary_desig = $1);

-- "MPC ∩ CNEOS expanded to all known designations
--  (primary + secondaries + permids)."
WITH common AS (
    SELECT primary_desig, packed_desig
      FROM css_neo_consensus.v_membership_wide
     WHERE in_mpc AND in_cneos AND packed_desig IS NOT NULL
)
SELECT DISTINCT v.designation, v.kind
  FROM css_neo_consensus.v_member_designations v
  JOIN common c USING (primary_desig);
```

## Known disagreement signals (snapshot 2026-04-26)

- **All six agree:** 41,376 asteroids — the "definitely an NEO"
  consensus answer.
- **NEOfixer 164 NECs:** the only source carrying near-Earth comets;
  filtered out of `v_membership_wide` by default.
- **A/-prefix asteroids:** A/2019 Q2 and A/2024 G8 appear in CNEOS,
  NEOCC, NEOfixer, mpc_orbits, and Lowell — but **not** in MPC's
  NEA.txt (asteroid-by-syntax curation). Both have full `mpc_orbits`
  rows and obs_sbn observations. The `mpc_orbits` source closes the
  NEA.txt gap.
- **`mpc` vs `mpc_orbits` delta:** 96 in mpc_orbits not in NEA.txt
  (mostly recent designations); 16 in NEA.txt not in mpc_orbits at
  q ≤ 1.3 (likely replication lag, recent orbit refits, or e-drift).
- **NEOfixer 138 ✗:** 138 objects all five other sources include but
  NEOfixer doesn't. NEOfixer applies its own find_orb fits and
  disagrees with the consensus on a small but non-trivial population.

## Dashboard surface (R&D, 2026-04-27)

The consensus data is exposed in the dashboard as a **NEO Consensus**
tab on the R&D instance only — visible at `dev.hotwireduniverse.org`,
behind Cloudflare Access (email allow-list), gated by the `--rnd` flag
to `app/discovery_stats.py`. Prod (`hotwireduniverse.org`) doesn't
show the tab; both Dash processes run under launchd
(`com.rlseaman.dashboard` and `com.rlseaman.dashboard-rnd`).

### Layout

A description blurb and a one-line **Snapshot** of any-six vs
all-six totals (queried once at module load), then a four-column
filter grid, then count + download buttons + the result table.

**Filter grid** (left to right):

1. **Hide all-six-agree** checkbox (default ON — surfaces only
   disagreements), then two big buttons:
   - **All-six consensus** — every source radio → Inc, hide-all → off.
   - **Reset to defaults** — all radios → Any, all ranges cleared,
     hide-all → on.
   Plus stacked **first_obs** and **last_obs** date ranges
   (`YYYY-MM-DD` text inputs, regex-validated).
2. **Filter by source** — six three-way Inc / Exc / Any radios, one
   per source (MPC NEA.txt, mpc_orbits q ≤ 1.3, JPL CNEOS, ESA
   NEOCC, CSS NEOfixer, Lowell astorb). AND-combined.
3. **Filter by class** — five three-way **Only** / Exc / Any radios,
   one per class (Atira, Aten, Apollo, Amor, MarsX). Selecting Only
   on one auto-flips the other four to Exc via a clientside
   callback. Picking multiple Onlys gives `class IN (...)` (OR
   among Onlys); picking Excs gives `class NOT IN (...)`. Plus two
   boolean Inc / Exc / Any radios:
   - **Numbered** — `permid IS NOT NULL`.
   - **Named** — IAU name present (joined from
     `minor_planet_names`; ~183 of 41K NEOs).
4. **Filter by range** — six numeric min/max pairs for q (AU), e, i
   (°), H, U (uncertainty 0–9), Nopp (oppositions). Empty = no
   constraint.

All filters AND-combined.

**Live count** below the grid. Reads "N matching NEOs" or "N matching
NEOs (showing first 5,000; …)" if the result was capped (50K cap is
above the ~42K population, so this caption rarely fires). Adds "(only
showing objects that do not appear in all lists)" when hide-all is on.

**Download buttons** below the count, both operating on the
currently-displayed table:

- **Download designations** — plain text, one primary designation
  per line.
- **Download NEA.txt subset** — original MPCORB-format lines from
  NEA.txt for those displayed rows that appear in NEA.txt; others
  are skipped with a header-comment count. Lookup is keyed by
  `unpack()` of each NEA.txt line's packed designation, with
  permid fallback for numbered NEOs.

### Detail table columns

- **Identity**: Designation, Permid, Name (IAU name from
  `minor_planet_names` when present).
- **Per-source membership booleans** (✓ / blank).
- **Class**: always `css_utilities.classify_orbit(q, e, i)` — single
  source of truth, no COALESCE with `mpc_orbits.orbit_type_int`
  (which is NULL for ~77% of NEOs).
- **Orbital elements**: q, e, i, H from `mpc_orbits`.
- **Quality flags**: `U` (orbit uncertainty 0–9), `Nopp`
  (oppositions). Capitalized in the column header — they were
  lowercase in the v1 table.
- **Observation summary**: `first_obs`, `last_obs`, `arc` (days),
  `nobs` — joined from `css_neo_consensus.obs_summary`, the daily-
  refreshed matview pre-aggregating `obs_sbn` by `primary_desig`.
  A handful of designations have no obs match (~2 in current
  snapshot) and show blank cells.

### Implementation notes

The buttons drive radios + filter via a **clientside callback**
(7 → 30 outputs). The earlier server-side approach with the radios
as both Input AND Output produced a multi-fire feedback storm —
Dash's self-loop guard didn't dedupe across multiple Output→Input
loops, and the callback fired 12 times for one button click with
partially-updated state. The clientside path is the standard fix:
the browser settles all props in one tick, the server-side
`update_consensus` callback fires once on the new Inputs.

The Only-flips-others class behavior is a second clientside callback
keyed on `triggered.value === 'include'` — only acts when the user
clicks Only, not when our own previous Output write set a class to
Exc. `allow_duplicate=True` is needed because the buttons callback
also writes to the five class radio Outputs.

Three operational lessons came out of the session and are recorded
in memory:

- **Use `obs_sbn`, not `obs_sbn_neo`, for `permid = $1 OR provid = $2`
  LATERAL aggregates.** Empirical: ~200× faster (1.9 s vs 3:55 on
  the 396-row disagreement set) AND covers Mars-Crossers / objects
  not in `mpc_orbits`. The smaller matview's index set / planner
  choice loses to `obs_sbn`'s broader index ladder on this access
  shape. The matview is still the right scan source for LOAD_SQL /
  APPARITION_SQL where we explicitly want NEO-filtered obs.
- **LATERAL doesn't scale past ~hundreds of targets.** ~5 ms per
  target × 41K = 3+ minutes, and shipping 41K rows × 20 cols of
  JSON is another bottleneck. Solution was to precompute as a
  matview (`obs_summary`) — daily cost paid once, query becomes a
  plain join.
- **`mpc_orbits.arc_length_total` is unreliable for NEOs** (NULL
  ~88%, only 5,091 / 41,763 populated). Compute arc from
  `obs_sbn.obstime` instead.

## Pending design topics

These are noted but not implemented:

- **Manual annotations layer** — a separate
  `css_neo_consensus.manual_annotations` table for human-curated
  notes (aliases, overrides, comments). Deferred until there's a
  concrete first use case.
- **Banner-level "NEO source" selector** — **shipped 2026-04-27**
  (R&D-only via --rnd). A dropdown in the banner with nine options
  (any / all-six / each of the 6 sources / disagreements-only)
  filters the four NEO-aware tabs (Discoveries by Year, Size
  Distribution, Multi-survey Comparison, Follow-up Timing,
  Discovery Circumstances). Membership data comes from a small
  parquet cache (`.consensus_membership_<hash>.parquet`, ~400 KB)
  built from `v_membership_wide` and left-joined into `df` and
  `df_apparition` at app startup. Per-tab callbacks gain one
  Input + a `_apply_source_filter()` slice early in the function
  body. The filter is hidden on tabs that don't slice df by NEO
  source (MPEC Browser, Asteroid Classes, Tools, Consensus).
  Refresh ordering matters: the membership cache build (stage 4
  of `refresh_matview_gizmo.sh`) runs **after** the consensus
  source ingest (stage 2) so today's ingest is visible to the
  banner filter same-day, no 24-hour lag.
- **UpSet plot + pairwise Jaccard heatmap** — single chart showing
  the 14 populated 4-way buckets sorted by count, plus a 6×6 grid
  of pairwise Jaccard coefficients. Would replace or complement the
  current row-by-row table for set-overlap exploration.
- **Object-detail modal** — clicking a table row opens a card with
  per-source `raw_string` / `last_refreshed`, the `v_member_designations`
  alias expansion, and a richer obs-summary view. Currently the user
  has to query the schema manually for this depth.
- **Comet support (NECs)** — currently `is_comet=TRUE` rows are
  filtered from `v_membership_wide`. NEOfixer carries 164 NECs;
  enabling them is a view edit. Defer until there's a concrete need.
- **Alias merging at canonicalization** — 15 designations in non-MPC
  sources resolve to MPC primaries that start with `P/` (i.e., MPC
  classifies the object as a periodic comet but other sources keep the
  asteroid-style provisional). E.g. `2025 NR197` (CNEOS/NEOCC/Lowell)
  ↔ MPC `P/1818 W1` (Pons-Brooks). `lib/neo_consensus.py::canonicalize`
  could follow `current_identifications` and rewrite secondary→primary
  before upsert; would merge these into single rows in
  `v_membership_wide` with `is_comet=TRUE` (and so filtered from the
  default view by design).
- **Fast Earth MOID utility** — for both this dashboard column and the
  toolkit at large. `mpc_orbits.earth_moid` is NULL for ~62% of NEOs.
  JPL SBDB has fuller coverage (overlaid in other dashboard tabs via
  `lib/sbdb_moid.py`). A fast in-process MOID computation from
  orbital elements would close the gap and be a useful
  `css_utilities` function generally — Sitarski (1968) or Gronchi
  (2002) iterative methods are the standard references. Not present
  in the codebase today.
