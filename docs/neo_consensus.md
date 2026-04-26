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

## Pending design topics

These are noted but not implemented:

- **Manual annotations layer** — a separate
  `css_neo_consensus.manual_annotations` table for human-curated
  notes (aliases, overrides, comments). Deferred until there's a
  concrete first use case.
- **Dashboard surface** — initially as a R&D-instance tab (see
  `dashboard_hardening_backlog.md`). Once stabilized, the
  controlling concept is a banner-level "NEO source" selector that
  filters all NEO-aware tabs (Discoveries by Year, Multi-survey,
  Follow-up, Discovery Circumstances). Implementation requires
  expanding LOAD_SQL/APPARITION_SQL to carry per-source `in_X`
  boolean columns drawn from `v_membership_wide`.
- **Comet support (NECs)** — currently `is_comet=TRUE` rows are
  filtered from `v_membership_wide`. NEOfixer carries 164 NECs;
  enabling them is a view edit. Defer until there's a concrete need.
