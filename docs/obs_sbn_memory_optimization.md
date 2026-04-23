# Optimizing `obs_sbn` queries under memory constraints (Gizmo)

**Scope:** identify and evaluate approaches to make `obs_sbn`-centric
queries tractable on Gizmo's 16 GB RAM, both for the existing Dashboard
workload and for future live-DB applications on the same replica. This
document is for discussion before any of it is built.

---

## 1. The problem, measured

| Item | Sibyl (HDD, PG 15.15) | Gizmo (NVMe, PG 18.3) |
|---|---:|---:|
| RAM | 251 GB | 16 GB |
| `shared_buffers` | 64 GB | 4 GB |
| `effective_cache_size` | 192 GB | 12 GB |
| `obs_sbn` heap | 239 GB | 213 GB |
| `obs_sbn` indexes (12) | ~200 GB | ~55 GB |
| `obs_sbn` heap cache hit | 28.8% | **11.8%** |
| LOAD_SQL (dashboard) wall time | 65 s | **935 s** (14×) |
| APPARITION_SQL wall time | 60 s | **1007 s** (17×) |
| BOXSCORE_SQL wall time | 31 s | 3.5 s (9× faster) |

The pattern is unambiguous:

- Queries whose working set is small enough to fit in Gizmo's
  `shared_buffers` are **faster** on Gizmo (BOXSCORE_SQL touches only
  `mpc_orbits` at 7.6 GB — fully cached).
- Queries that probe `obs_sbn`'s 55 GB of indexes randomly have poor
  cache hit rates because 55 GB of indexes can't fit in 4 GB of
  `shared_buffers` (or even 16 GB of total RAM). Each miss is a ~100 µs
  NVMe read; tens of thousands of misses per query accumulate.

The synthetic 1M/20M-row benchmarks previously run on Gizmo were
misleading because those datasets fit entirely in cache, which flattered
the hardware and masked this specific weakness.

### Query shape that triggers the problem

LOAD_SQL and APPARITION_SQL both follow a pattern:

```
For each of ~41,000 NEOs:
    probe obs_sbn.permid_idx    -- or provid_idx
    for each matching row:
        probe obs_sbn heap
        sometimes probe obs_sbn.trkid_idx for the tracklet
```

That's ~100K–500K random index + heap probes per query. Sibyl's RAM
absorbs nearly all of them; Gizmo can't.

Non-`obs_sbn` joins (against `mpc_orbits`, `numbered_identifications`,
`obscodes`) are **not** the problem. Those tables are small and cached.

---

## 2. Four candidate approaches

The approaches differ in where they put the memory savings: in a
pre-filtered *table* (A, materialized view), in a pre-filtered *index*
(B, partial indexes), in wider indexes that avoid heap visits (C,
covering indexes), or in fundamentally smaller index structures (D,
BRIN). They are not mutually exclusive.

### A. NEO-only materialized view

**Idea.** Precompute the subset of `obs_sbn` that contains any
observation of any NEO, into a table-like object. Index that smaller
object. Rewrite NEO-focused queries to read the matview.

**Sizing estimate.** ~41K NEOs in `mpc_orbits` (q ≤ 1.30). Well-observed
objects average ~500–1500 observations. Expect **~20–35 M rows, ~8–12 GB
heap, ~2–4 GB of indexes**. Total ~10–16 GB. Most of this fits in
Gizmo's page cache, a meaningful fraction in `shared_buffers`. Requires
measurement — the sizing above is plausible, not verified.

**Example DDL.** See `sql/matviews/obs_sbn_neo.sql` (prototype below).

**Maintenance.** `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo`
once per day, alongside the existing nightly cache refresh. Expected
refresh time on Gizmo: similar to one LOAD_SQL run (~15 min, driven by
the same random-probe cost). The key point: pay 15 min once, then every
NEO-adjacent query runs in seconds.

**Staleness window.** Up to 24 h (matches existing dashboard cache
cadence). Fine for dashboard-style "yesterday's state" views, wrong for
anything that needs "observations posted in the last hour."

**Trade-offs.**
- **+** Reusable across many queries (dashboard refresh, MPEC browser,
  any future live-DB app that cares about NEOs).
- **+** Keeps raw `obs_sbn` untouched — inherited tuning, replication,
  and indexes are unchanged.
- **+** Queries get dramatic speedup (we expect seconds vs minutes),
  without touching replication.
- **−** Storage cost (~10–16 GB) on the NVMe. Trivial in absolute terms
  (3.3 TB free).
- **−** Daily refresh is a moving part. Needs monitoring.
- **−** Stale-during-refresh problem: REFRESH CONCURRENTLY is
  online-friendly (readers don't block), but needs a unique index on the
  matview (trivial on `obsid`) and doubles the disk write during refresh.

### B. Partial indexes on discovery observations

**Idea.** Most NEO dashboard queries start from discovery observations
(`disc = '*'`), of which there are only ~44,000 in the 535 M-row
`obs_sbn`. Indexes with `WHERE disc = '*'` predicate become tiny.

**Example DDL.**

```sql
CREATE INDEX CONCURRENTLY idx_obs_disc_by_permid
    ON obs_sbn (permid) WHERE disc = '*';
CREATE INDEX CONCURRENTLY idx_obs_disc_by_provid
    ON obs_sbn (provid) WHERE disc = '*';
```

Rough size: each ~1 MB. Essentially always in cache.

**Applicability.** Speeds up only the `discovery_obs_all` CTE in
LOAD_SQL and similar "find the discovery observation for this NEO"
patterns. Does *not* help `tracklet_obs_all` (which walks back to the
full tracklet) nor APPARITION_SQL (which spans ±200 days of
observations).

**Sibyl usage check.** The existing plain `idx_obs_sbn_disc` is hit 682
times in Sibyl's lifetime — suggesting that current queries already use
`disc = '*'` as a cross-check but do NOT use it as the primary key
lookup. The planner would need to use the new partial indexes directly
for this to pay off — we'd need to verify that plans actually switch.

**Trade-offs.**
- **+** Tiny, zero-risk, takes seconds to build.
- **+** No maintenance (indexes stay in sync with writes automatically).
- **−** Narrow win. Covers the "first discovery" lookup, nothing more.
- **−** Won't close the Gizmo-vs-Sibyl gap by itself.

### C. Covering indexes for hot query shapes

**Idea.** Use PostgreSQL's `INCLUDE` clause to bundle extra columns into
a B-tree index so that index-only scans can satisfy a query without
visiting the heap. Halves the random I/O for matching queries.

**Example DDL.**

```sql
CREATE INDEX CONCURRENTLY idx_obs_trkid_cover
    ON obs_sbn (trkid)
    INCLUDE (obstime, ra, dec, mag, band);
```

This would let the `tracklet_obs_all` CTE pull everything it needs from
the index alone — no heap visits for the ~300 K tracklet observations
per refresh.

**Trade-offs.**
- **+** Direct hit on the specific I/O pattern (random heap visits per
  row found in the index).
- **+** No application changes — planner picks it automatically.
- **−** Index grows (roughly doubles in this example: 15 GB base +
  additional columns). `trkid` alone is already ~8 GB; with INCLUDE
  maybe ~25 GB. That's *more* index, not less — the win is in fewer
  cache misses per query, but we're adding more to the cache footprint.
- **−** Worth doing only after `pg_stat_statements` on Gizmo shows that
  specific queries are bottlenecked on heap visits. Premature otherwise.
- **−** Writes pay more maintenance cost (every insert touches a bigger
  index).

### D. BRIN on correlated columns

**Idea.** Block Range Indexes summarize page ranges instead of
individual rows. For data whose physical order correlates with a column
value (in our case, `obstime` and `created_at` both grow monotonically
on the replication stream), BRIN is hundreds of times smaller than
B-tree while still enabling effective range scans.

**Example DDL.**

```sql
CREATE INDEX CONCURRENTLY obs_sbn_obstime_brin
    ON obs_sbn USING brin (obstime) WITH (pages_per_range = 32);
CREATE INDEX CONCURRENTLY obs_sbn_created_at_brin
    ON obs_sbn USING brin (created_at) WITH (pages_per_range = 32);
```

Expected size: ~MB, not GB.

**Trade-offs.**
- **+** Trivial cost, always cached.
- **+** Great for time-range scans ("all obs in March 2026",
  incremental "everything new since last run"), which APPARITION_SQL
  partially is.
- **−** Not a replacement for B-tree on `permid`/`provid`/`trkid` —
  BRIN can't do point lookups efficiently. This is an *additional* tool,
  not a substitute.
- **−** BRIN effectiveness depends on physical ordering. `obstime`
  ordering is good but not perfect (late-arriving observations break
  monotonicity); worth verifying `pg_stats` correlation values before
  building.

---

## 3. Summary matrix

| | Latency win (LOAD_SQL) | Latency win (APPARITION) | Latency win (future) | Disk | Refresh/maint | Risk |
|---|---|---|---|---|---|---|
| A. NEO matview | **large** (expected sec vs min) | **large** | **large** for NEO queries | +10–16 GB | 15 min/day | Stale-during-refresh window |
| B. Partial indexes | small (first CTE only) | none | narrow | +few MB | none | none |
| C. Covering indexes | targeted, per-query | targeted, per-query | none unless rebuilt | +10–15 GB per index | none | bigger index to cache |
| D. BRIN | none for key lookups | partial (time filters) | good for time-scan patterns | +few MB | none | none |

## 4. Suggested sequence

A sequencing that starts with no-risk wins and escalates only if the
prior step doesn't close the gap:

1. **Ship B + D immediately.** Partial indexes on `disc = '*'` + BRIN
   on `obstime`/`created_at`. Total cost: minutes of DBA time, ~tens of
   MB of disk. Rerun LOAD_SQL/APPARITION_SQL on Gizmo and remeasure.
2. **If dashboard refresh is still multi-minute,** prototype the NEO
   matview (A) and benchmark the LOAD_SQL rewrite against it. The
   prototype in `sql/matviews/obs_sbn_neo.sql` below is the first
   concrete step.
3. **Only after A is committed and profiled,** identify the remaining
   hot query shapes from `pg_stat_statements` on Gizmo and build
   targeted covering indexes (C) for them. Avoid speculative INCLUDE
   clauses.
4. **Do not re-architect replication** (publisher-side filtering,
   partitioning) without a demonstrated need — both are disproportionate
   to the problem as currently measured.

## 5. Open questions for evaluation

- **Refresh cadence for the matview.** Daily is the natural fit. Is
  hourly ever needed? If so, the matview's refresh cost (~15 min)
  becomes a non-trivial fraction of the hour.
- **Which future live-DB applications are planned?** The matview
  approach amortizes best across many NEO-focused consumers. If the
  dashboard is the only consumer, the MBP→Sibyl nightly pipeline
  already solves the problem without a matview.
- **Is there appetite for a second NEO-adjacent matview** (e.g.
  `mpec_observations_neo` for the MPEC browser)? The architecture
  scales to multiple matviews cheaply if each one is small.
- **What's the tolerance for staleness mid-refresh?** CONCURRENTLY
  maintains read availability but roughly doubles the disk write during
  refresh. With 10–16 GB doubled, that's 20–32 GB of write churn per
  daily refresh — well within the NVMe's endurance budget but worth
  naming.
- **Does the schema drift (`mpc_orbits.updated_at_aws` on Gizmo but not
  Sibyl) affect any of this?** No — the matview definition uses only
  columns present on both sides.

## 6. Prototype

See `sql/matviews/obs_sbn_neo.sql` for the initial prototype: a wide
NEO-scoped materialized view, the indexes to put on it, a rewritten
version of LOAD_SQL that uses it, and a comparison scaffold for timing
it against the current query.
