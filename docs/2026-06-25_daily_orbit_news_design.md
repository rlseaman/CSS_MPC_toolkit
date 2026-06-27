# Daily Orbit News — design sketch

**Author:** Rob Seaman (with Claude)
**Date:** 2026-06-25
**Status:** Sketch / proposal. SQL skeletons under `sql/orbit_watch/`. Nothing
deployed; DDL needs a superuser, the diff runs as `claude_ro`.

## Idea

Each day MPC re-fits orbits for objects that got new astrometry. The live
replica reflects this in `mpc_orbits.updated_at`, but **keeps only the latest
orbit** — there is no element-history table anywhere in `mpc_sbn`. So two
distinct products fall out of the same mechanism:

1. **Daily diff ("today's orbit news"):** which objects changed *meaningfully*
   since their previous fit — especially those that crossed a
   planetary-defense boundary. Answerable from the replica alone, today.
2. **Longitudinal history:** how each object's orbit evolved over time. The
   replica can't answer this (it discards history); a snapshot we keep
   ourselves, or the DOU MPEC archive backfilled, can.

This doc specifies #1 and leaves a hook for #2.

## Why it's feasible — the volumes are tiny

Measured on Gizmo 2026-06-25 (`sql/orbit_watch/` sizing, also in the
mpc_orbits state doc):

| Population | Count |
|---|--:|
| All `mpc_orbits` | 1,558,527 |
| NEOs (q ≤ 1.3, e < 1) | 42,300 |
| **Watch set (q ≤ 1.5, e < 1)** | **50,269** |
| Near-NEO band (q ∈ [1.25, 1.35]) | 3,307 |
| `earth_moid` ≤ 0.05 | 9,237 |
| Near-PHA band (moid ∈ [0.04, 0.06]) | 1,605 |

Daily re-fit volume over the last week: **1 K–26 K rows/day total**, but only
**~25–135/day fall in the watch set** (NEO-only ~17–112/day). The whole
planetary-defense-relevant orbit-change stream is *a few dozen rows a day* —
small enough to diff in milliseconds and present in full.

## Watch set

`q ≤ 1.5 AND e < 1`, plus any NEA.txt member (`css_neo_consensus … in_mpc`) as
a safety net. The 0.2-AU margin above the q = 1.3 NEO line is there so an
object can be under observation *before* it crosses in — single-fit jumps in q
of more than ~0.2 AU are rare except for very short arcs. `q` is reliable in
`mpc_orbits` (99.8% populated); classification is derived from elements (see
below), never from the scattershot `orbit_type_int`.

## Event taxonomy

A diff between an object's two most recent snapshots emits zero or more events:

| Event | Trigger | Why it matters |
|---|---|---|
| `NEO_ENTER` / `NEO_EXIT` | q crosses 1.3 | object entered/left the NEO population — the exact churn the Consensus tab reconciles |
| `PHA_ENTER` / `PHA_EXIT` | (earth_moid ≤ 0.05 AND H ≤ 22) flips | PHA status change — highest planetary-defense salience |
| `NEO_FIRST_DETERMINED` / `PHA_FIRST_DETERMINED` | classification became *evaluable* (prior snapshot lacked q / MOID / H) | a fresh discovery getting its first full orbit characterization — **not** dynamical motion; kept distinct from a real crossing so the feed isn't misleading (added 2026-06-27 after the live feed surfaced 2026 LZ2 with a NULL→0.0338 MOID) |
| `SUBCLASS_CHANGE` | Atira/Aten/Apollo/Amor label changes | dynamical reclassification |
| `H_REVISION` | \|ΔH\| ≥ 0.3 mag | size estimate moved — feeds the size-distribution / completeness tabs |
| `ORBIT_SHIFT` | \|Δq\| ≥ 0.02 AU or \|Δa\| ≥ 0.05 AU or \|Δe\| ≥ 0.02 | refinement or instability; repeated daily shifts ⇒ poorly-constrained orbit needing follow-up |
| `NEWLY_NUMBERED` | object gained a permid since last snapshot | recovery / identification milestone (joins `numbered_identifications`) |

Thresholds are parameters, tuned once on real output.

## Data model (`sql/orbit_watch/`)

- **`css_orbit_watch.orbit_snapshot`** — the watch set's element state, one row
  per (object, day). ~50 K rows/day → ~18 M rows/yr, ~2 GB/yr.
  **Retention rule:** the rolling-window prune (e.g. 60 days) applies *only to
  objects outside the any-of-six NEO cohort* — i.e. watch-set margin objects
  (q ≤ 1.5 but called a NEO by none of the six sources, mostly q ∈ (1.3, 1.5]).
  Any-of-six members (every row in `css_neo_consensus.v_membership_wide`,
  ~42 K objects) keep their **full** snapshot history, so the longitudinal
  orbit-convergence record is preserved for real NEOs. Sketch:
  `DELETE FROM css_orbit_watch.orbit_snapshot s
     WHERE s.snapshot_date < CURRENT_DATE - INTERVAL '60 days'
       AND NOT EXISTS (SELECT 1 FROM css_neo_consensus.v_membership_wide w
                       WHERE w.primary_desig = s.primary_desig);`
  (Membership is evaluated at prune time; an object that was a NEO but has since
  dropped out of all six sources becomes prune-eligible — acceptable, but note
  it if "ever-a-NEO" retention is wanted instead.) The *events* table is the
  durable record regardless.
- **`css_orbit_watch.orbit_event`** — append-only log of detected events
  (event_date, primary_desig, disc_by, event_type, prev/new element columns).
  This is simultaneously the daily news feed **and** the longitudinal record of
  boundary churn.

Nightly: `capture_snapshot.sql` (insert today's watch set) → `daily_diff.sql`
(diff the two latest snapshot dates, insert events). Both are cheap; slot them
into the existing `refresh_matview_gizmo.sh` after the consensus refresh.

## Surfacing it

Start as a **card on the MPEC Browser tab** ("Today's orbit news: N NEO
entries, M PHA changes, …" with an expandable list). But the volumes and the
slicing dimensions argue for **its own tab**:

- **By discovery site / project** — `disc_by` is already on `obs_summary`, so
  every event row can carry the discoverer. "Orbit news for CSS objects" is one
  filter; "for ATLAS / Pan-STARRS / Rubin" is another. Of broad interest, not
  just ours — a public "what moved in NEO space today" feed.
- **By event type** — a PHA-change watchlist is a different audience than an
  H-revision feed.
- **Timeline** — once `orbit_event` accumulates, the same tab plots boundary
  churn over weeks/months (the longitudinal payoff) with no extra plumbing.

The tab gates behind `--dev-tabs` until it has run long enough to trust.

## Phase 2: the DOU is an *MBA-monitoring* play, not a NEO backfill

Reframed 2026-06-27 after parsing a real DOU and mining `epoch_mjd` — see
`docs/2026-06-27_dou_orbit_logistics.md`. Key facts that change the plan:

- **The DOU is ~23,750 *numbered main-belt* objects/day, no NEOs, and no MOID.**
  So it is **not** a source of NEO history (NEOs stay on the forward-snapshot
  track) — but it **is** the natural event-driven stream for the slow-cadence
  numbered population we deliberately don't snapshot.
- **Forward for NEOs, DOU for MBAs.** Ingest each DOU's 1-line element blocks
  into an MBA element-history table; reuse `css_orbit_watch.compute_events`
  (generalized to "object's previous recorded elements") for update-cadence,
  element evolution, and the planetary-defense-relevant case of a **numbered MBA
  whose re-fit drops q toward/below 1.3** (a newly-recognized NEO we'd otherwise
  miss). q is derivable as `a(1−e)`; MOID absence is fine — MBAs aren't PHAs.
- **Heavyweight option:** a parser that **computes MOIDs from the orbits**
  (numerical Earth–orbit minimum distance) would restore PHA-style events for
  the MBA stream and cross-check `mpc_orbits.earth_moid` for NEOs.
- **Standard-epoch / migration monitor:** trivially derivable from `epoch_mjd`
  (% of catalog migrated to the current standard epoch + the 200-day-stepped
  backlog histogram) — a one-query logistics/health panel.
- **Backfill** ~3 weeks of DOUs to seed an MBA-cadence baseline (≈20 fetches,
  ~50 K orbit lines; existing throttle). **Read `docs/mpec_access.md` first** —
  the historical-MPEC-corpus landscape is scoped there.
- For NEOs (forward stream): orbit convergence curves, classification-churn
  stats, orbit-instability early-warning.

## Open questions

1. **Snapshot granularity.** Full watch set daily (simple "today vs yesterday"
   diff, 50 K rows/day) — chosen here for robustness — vs updated-only
   (~100 rows/day, but the diff must find each object's previous fit). Easy to
   switch; full-set is the safe default.
2. **PHA H threshold.** Using H ≤ 22 (≈ 140 m). Could also surface MOID-only
   crossings regardless of size.
3. **Comets.** Watch set is e < 1; near-Earth comets (DOU-relevant) would need
   a separate rule.
4. **Dedup vs the replication lag.** A single object can be re-fit twice in a
   day; snapshot on the day's final state (max `updated_at` per object).
