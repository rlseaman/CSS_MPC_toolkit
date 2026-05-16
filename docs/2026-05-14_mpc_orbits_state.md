# mpc_orbits — State of the table, 2026-05-14

**Author:** Rob Seaman (with Claude)
**Replicas surveyed:** Sibyl (PG 15.15) and Gizmo (PG 18.3).  Row counts and
per-month completeness agree to within a few rows; everything below is
quoted from Sibyl unless noted.

## Question

Has MPC delivered the `mpc_orbits` improvements reported at last week's MUG
meeting?  Are top-level columns more completely populated than the
"scattershot" state recorded in
`memory/mpc_orbits_is_scattershot.md`?

**Answer in one line:** Yes for new and recently-refreshed rows
(near-saturation populations), no for the historical bulk
(~700 K rows, 45 % of the table, last touched 2025-08-29 and still
in the legacy state).

## Headline numbers (Sibyl, 2026-05-14 22:30 UTC)

| Metric                                     | Sibyl  | Gizmo  |
|--------------------------------------------|--------|--------|
| Total rows                                 | 1,548,398 | 1,548,437 |
| Min `updated_at`                           | 2025-08-29 15:43 UTC | same |
| Max `updated_at`                           | 2026-05-14 22:33 UTC | 2026-05-15 01:16 UTC |

Growth since the prior "1.51 M rows" baseline: roughly **+37 K rows**
across the whole period 2025-08 → 2026-05.

## Top-level column population (% of all rows)

```
total rows  1,548,398
mpc_orb_jsonb               99.83 %
h, g                        99.83 %
q, e, i, node, argperi,
peri_time, *_unc            99.83 %     ← cometary elements + uncertainties
fitting_datetime            99.83 %
normalized_rms              99.52 %
orbit_type_int              69.31 %     ← prior baseline 65 %
nopp, nobs_total, u_param   99.83 %
a, mean_anomaly             50.51 %     ← prior baseline 43 %
period, mean_motion          ~49 %
arc_length_total/sel        ~50.5 %     ← same scattershot shape
earth_moid                  37.03 %     ← prior baseline 30 %
not_normalized_rms           7.91 %     ← rarely written
yarkovsky                      186 rows (0.012 %)
srp / a1 / a2 / a3 / dt        0–15 rows
```

`mpc_orb_jsonb IS NULL` for **2,615 rows** — these have nothing beyond
the designation and (sometimes) a few derived metadata fields.

## JSONB is canonical; top-level columns mirror it

Top-level columns are derived from `mpc_orb_jsonb` at ingest.  Two
cross-checks confirm this:

* `orbit_type_int`: 1,073,224 rows have the value in both top-level
  and `jsonb->'categorization'->>'orbit_type_int'`, 468,414 rows have
  NULL in both, and only **4,158 rows** have a JSONB value that the
  top-level column failed to mirror.  No reverse mismatches.
* `earth_moid`: 568,446 rows in agreement, 962,762 NULL in both,
  9,742 JSONB-only, 4,847 top-level-only.  Same story — JSONB is the
  authority, top-level is a (slightly leaky) projection.

So **the "scattershot" coverage is not a propagation bug**.  When the
top-level columns are NULL, it is overwhelmingly because the JSONB
itself has no value for that field — MPC's pipeline did not compute it.

The JSONB representation always includes cometary (`COM`) and
Cartesian (`CAR`) blocks.  A Keplerian (`KEP`) block is present for
only **129,235 rows (8.4 %)**, so the top-level Keplerian columns
that *are* populated for ~50 % of rows are derived (presumably
`a = q/(1-e)` and friends).  That code path is internal to MPC; the
DERIVED_COLUMNS handling in `lib/orbits.py` remains necessary for the
other half.

## The temporal signal — improvement is real, but not retroactive

| `updated_at` month | Rows  | %`orbit_type_int` | %`a` | %`earth_moid` | %`h` |
|--------------------|------:|------------------:|-----:|--------------:|-----:|
| 2025-08            | 700,547 |  33.1 |   2.5 |  47.2 | 100.0 |
| 2025-09            |  54,554 | 100.0 |  61.4 |  40.9 | 100.0 |
| 2025-10            |  54,430 | 100.0 |  70.3 |  31.6 | 100.0 |
| 2025-11            |  75,944 | 100.0 |  89.8 |   9.8 | 100.0 |
| 2025-12            | 109,890 | 100.0 |  83.8 |  12.5 | 100.0 |
| 2026-01            |  89,471 | 100.0 |  90.2 |  10.0 | 100.0 |
| 2026-02            | 170,714 | 100.0 |  98.2 |  10.7 | 100.0 |
| 2026-03            |  65,284 | 100.0 |  91.3 |   8.2 | 100.0 |
| 2026-04            | 111,245 |  95.4 |  97.1 |  38.2 |  97.6 |
| 2026-05            | 116,334 |  98.6 | 100.0 |  91.9 | 100.0 |

Read this table top-down:

1. **2025-08-29 is the legacy snapshot.**  699,013 rows carry that
   exact `updated_at` — a one-shot ingest event.  Their `orbit_type_int`
   is populated for only 33 %, `a` for 2.5 %, `earth_moid` for 47 %.
   This bucket is the source of the "scattershot" reputation; it
   accounts for 45 % of the table and has not been re-touched since.
   Inside this bucket, `fitting_datetime` spans 2022 → 2025, so these
   are legitimate (if old) orbit fits — the rows just have not flowed
   through MPC's newer enrichment pipeline.
2. **Every monthly batch from September onward populates
   `orbit_type_int` essentially to completion** (95–100 %).  Whatever
   classification logic was missing for the August cohort is wired in
   for fresh fits.
3. **Top-level `a` climbs from 61 % (Sep 2025) to 100 % (Feb 2026
   onwards).**  By February the Keplerian derivation runs on every
   fresh fit.
4. **`earth_moid` is messier.**  It drops from 47 % (Aug) into the
   single digits over the autumn, then jumps back to ~98 % only in
   May 2026.  This looks like MPC turned a MOID solver back on this
   month.  Sample week of daily numbers (2026-05-09 → 2026-05-14):
   `earth_moid` populated for 97–99 % every day, `a` 100 %,
   `orbit_type_int` 99 %+.

The picture is consistent with MPC having rewritten or re-enabled
several enrichment stages over the past nine months — classifier,
Keplerian derivation, MOID solver — but applying them only to rows
that get re-fit.  The August cohort represents the "in flight at the
time" set, frozen at the previous fitter's output.

## NEO subset is disproportionately stale

Among the 42,063 NEOs in `mpc_orbits` (q ≤ 1.3, e < 1):

| Cohort            | Rows   | %`orbit_type_int` | %`a` | %`earth_moid` |
|-------------------|-------:|------------------:|-----:|--------------:|
| Aug 2025 legacy   | 34,228 |   6.8 |  0.3 | 35.6 |
| Sep 2025 +        |  7,835 |  99.0 | 66.5 | 48.8 |

**81 % of NEOs are still in the legacy state**, and within that
cohort the population is markedly worse than the table-wide Aug 2025
average — `orbit_type_int` only 6.8 %, `a` only 0.3 %.  Plausible
explanation: the classifier needs Keplerian `a`, and the legacy import
did not produce it for NEOs.  Whatever the cause, this is the
practical reason "mpc_orbits is scattershot" is still the right
working assumption for any NEO-only consumer that doesn't override
with NEA.txt and the consensus catalogs.

## What this means for the toolkit

* **Keep the workarounds.**  `lib/orbits.py` `DERIVED_COLUMNS`
  (cometary → Keplerian), `lib/orbit_classes.py`
  `classify_from_elements()` (cometary → orbit_type_int), and the
  NEA.txt H-magnitude override are all still load-bearing.  None of
  them can be retired until MPC re-fits the August 2025 cohort.
* **Particularly important for the NEO Consensus tab and any
  size/orbit-class plot keyed off `mpc_orbits` alone.**  The CSS NEO
  consensus catalog cross-checks against MPC NEA.txt, SBDB,
  NEOCC, NEOfixer, and Lowell precisely because `mpc_orbits` is not
  sufficient on its own.  Nothing in the present audit changes that.
* **A "Most rows have NULL `a`" claim in CLAUDE.md should be softened
  but not removed.**  The headline 50 % top-level coverage is real
  for the whole table; for fresh rows it is 100 %; for the legacy
  cohort it is 2.5 %.  Saying "scattershot" without qualifier remains
  accurate.
* **Watch the next two months.**  If MPC re-fits the August cohort,
  table-wide `a` should jump toward 100 %, `orbit_type_int` toward
  99 %, and `earth_moid` toward ~98 %.  When it happens we can drop
  the cometary→Keplerian derivation, re-measure, and credit the MUG
  report properly.  A simple re-run of the queries in this document
  will tell.

## Reproducing this audit

All numbers above come from `psql` against Sibyl over a single
session 2026-05-14 21:30–22:30 UTC, using `PGHOST=sibyl
PGCONNECT_TIMEOUT=10 psql -U claude_ro mpc_sbn`.  The exact queries:

```sql
-- Headline counts
SELECT COUNT(*), MIN(updated_at), MAX(updated_at) FROM mpc_orbits;

-- Column population
SELECT COUNT(*) AS total,
       COUNT(orbit_type_int) AS otype,
       COUNT(a) AS a, COUNT(period) AS period,
       COUNT(earth_moid) AS emoid, COUNT(h) AS h
FROM mpc_orbits;

-- JSONB vs top-level orbit_type_int agreement
SELECT (orbit_type_int IS NULL) AS top_null,
       ((mpc_orb_jsonb->'categorization'->>'orbit_type_int')::int
          IS NULL) AS jsonb_null,
       COUNT(*)
FROM mpc_orbits WHERE mpc_orb_jsonb IS NOT NULL
GROUP BY 1, 2;

-- Temporal completeness
SELECT date_trunc('month', updated_at) AS month,
       COUNT(*) AS rows,
       ROUND(100.0 * COUNT(orbit_type_int) / COUNT(*), 1) AS pct_otype,
       ROUND(100.0 * COUNT(a)              / COUNT(*), 1) AS pct_a,
       ROUND(100.0 * COUNT(earth_moid)     / COUNT(*), 1) AS pct_emoid
FROM mpc_orbits
WHERE updated_at IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

Gizmo numbers were sampled over SSH with `psql -h /tmp -U claude_ro
mpc_sbn` (TCP listen is localhost-only); row counts agreed to within
~40 rows because Gizmo's logical replication was a few minutes ahead
of Sibyl.

## See also

* `docs/source_tables.md`
* `memory/mpc_orbits_is_scattershot.md` (the prior baseline this
  report updates)
* `memory/neo_consensus_schema.md` (why we cross-source NEOs)
* `lib/orbits.py` — `DERIVED_COLUMNS` keeps the missing Keplerian
  values usable
* `lib/orbit_classes.py` — `classify_from_elements()` recovers
  `orbit_type_int` from cometary elements when MPC's column is NULL
