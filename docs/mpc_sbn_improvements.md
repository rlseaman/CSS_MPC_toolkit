# Improving the utility of mpc_sbn — a slate for the MUG meeting

## Framing

`mpc_sbn` is a logical-replication copy of the MPC PostgreSQL
catalog, maintained at the Catalina Sky Survey on two replicas
(Sibyl and Gizmo). The mission of `CSS_MPC_toolkit` is to *improve
the utility of mpc_sbn (and broader community) assets* — for our own
analysis, for MPC-adjacent users, and for the wider planetary-defense
and small-body community.

The Planetary Defense Dashboard is one demonstration surface for
that mission, not the mission itself. It exists in part to show
what's possible once mpc_sbn is well-indexed, well-summarized, and
well-instrumented; the more interesting deliverables for a working
audience like MUG are at the database, library, and data-distribution
layers.

## βeta release readiness

The dashboard βeta is **independently shippable today**. None of the
items below are prerequisites. The case for *announcing it alongside*
some of these — rather than letting the dashboard stand alone — is
narrative, not technical: MUG is exactly the kind of audience that
wants to see what's *behind* a viewer, not just the viewer.

The Station Report tab on `dev.hotwireduniverse.org` is a working
demonstration of how mpc_sbn enables tools beyond outreach. It can
either ship with the βeta (with sharp edges acknowledged) or stay
gated until ADS reconciliation matures.

## A. Database-level improvements (Gizmo first; Sibyl after operational experience)

Three of the originally-proposed items below were **measured against
Gizmo on 2026-04-29** and the picture changed:

- BRIN on `obs_sbn.obstime` (A1) is *not viable* on the current
  layout — correlation between physical row order and `obstime` is
  effectively zero.
- The `(stn, obstime)` composite (A2) *already exists* as
  `idx_obs_stn_time`.
- `pg_stat_statements` (A3) is *already enabled and recording*; ~17 h
  of accumulated query time was already on hand. Its top-consumer
  output surfaced a much higher-impact target: A0.

A0 is the new top priority. A1–A3 are retained as-was so the
reasoning behind the original proposal — and what measurement
revealed — stays in the historical record.

### A0. Materialize `css_neo_consensus.v_membership_wide` (highest impact)

`pg_stat_statements` on Gizmo (claude_ro user, ~17 h of recorded
query time) shows a single dominant hot spot:

| total time      | calls | mean   | shape                                              |
| --------------: | ----: | -----: | -------------------------------------------------- |
| 13,515 s (~3.7 h) | 27 | 500 s | `css_neo_consensus.v_membership_wide` filtered     |
|        3,998 s  |   4 | 1000 s | `LOAD_SQL`-shaped CTE (cache rebuild)              |
|        3,684 s  |   4 |  921 s | `LOAD_SQL`-shaped CTE                              |

**~40 % of total DB time** goes to `v_membership_wide`. It is
currently a regular view (not a matview), and re-aggregates
`source_membership` (48 MB, six per-source rollup tables) into one
row per primary designation on every call. Mean execution time is
500–750 s for queries that return ~41 K rows.

Converting to a materialized view, refreshed in stage 2 of the
nightly pipeline (right after `source_membership` is updated),
collapses each call to a simple scan of a pre-aggregated result.
Expected impact:

- 500 s mean → a few seconds (sub-second for simple shapes).
- ~40 % of total DB time recovered.
- Refresh cost added to stage 2: small — `source_membership` is
  48 MB and the aggregation is one `GROUP BY`.

This is the single MUG-friendly slide the audit produced: *"by
materializing the cross-source join, consensus-tab response went
from ~8 minutes to a few seconds."* Implementation is roughly
half a day: `CREATE MATERIALIZED VIEW` with the existing view body,
either point dependent code at the new name or use `ALTER VIEW ...
RENAME` so the matview can take the original name, then append a
`REFRESH MATERIALIZED VIEW CONCURRENTLY` line to
`scripts/refresh_matview_gizmo.sh` stage 2.

### A1. BRIN on `obs_sbn.obstime` — investigated, NOT viable here

Retained for context: this *was* the marquee proposal until
measurement ruled it out. The reasoning is still useful for future
decisions on related tables.

A Block Range Index stores a `(min, max)` summary per range of
physical heap pages (default 128 pages, ~1 MB of table) instead
of one entry per row. For 526 M rows, the existing btree on
`obstime` is ~4.2 GB; a BRIN with `pages_per_range = 32` would
have been on the order of 20 MB — ~200× smaller. The catch is
that BRIN is *only* useful when physical row order correlates
with the indexed value; otherwise per-range `(min, max)` summaries
are too wide to skip pages.

**Measurement (2026-04-29).** `pg_stats` on Gizmo:

```
attname     correlation
obstime     -0.009
created_at   0.082
updated_at  -0.000032
stn          0.080
```

Physical heap layout is effectively random with respect to all
time columns — even `created_at`, which one would expect to track
insertion order. The likely culprits are past `pg_repack` runs
and parallel replication workers writing rows from independent
transactions to wherever the next free page is.

**Verdict: do not build.** With near-zero correlation, BRIN
page-skip would deliver effectively zero selectivity gain over a
sequential scan or the existing btree. The 20 MB index would
cost ~minutes of build time for no measurable speedup.

A periodic `pg_repack --order-by obstime` (or full `CLUSTER`,
which takes an exclusive lock) would restore correlation and make
BRIN viable, but on a 526 M-row replicating table that's a heavy
maintenance event for limited gain over the btree we already have.

If we ever build new analytical tables that *are* monotonically
appended (no repack, no shuffle), BRIN will be on the table again
— so the design pattern is preserved here, just not applied to
`obs_sbn` as it stands today.

### A2. Multi-column index `(stn, obstime)` — already exists

Confirmed 2026-04-29: `idx_obs_stn_time` (4.5 GB) already covers
`(stn, obstime)`. Per-station date-range queries (Station Report,
follow-up timing) get index seeks for the right station + date
range, in order, regardless of physical heap layout — which is why
this index works for those queries while BRIN wouldn't have. The
provisioner of the original index inventory deserves credit; no
new work needed here. Section retained so future readers know this
ground was already covered.

### A3. `pg_stat_statements` audit — already running, with findings

Confirmed 2026-04-29: `pg_stat_statements` is enabled on Gizmo
(extension version 1.12) and has been accumulating since the
replica came up — ~17 h of recorded query time across 1,168
distinct query shapes was already on hand when checked. Top
consumers are listed under A0 above; the headline finding is that
~40 % of recorded DB time goes to `v_membership_wide`, motivating
the A0 matview conversion.

To compare against Sibyl (year+ of workload):

```sql
SHOW shared_preload_libraries;
SELECT * FROM pg_available_extensions WHERE name = 'pg_stat_statements';
SELECT * FROM pg_extension          WHERE extname = 'pg_stat_statements';
SELECT count(*) AS recorded_queries,
       round(sum(total_exec_time)/1000) AS total_seconds
  FROM pg_stat_statements;
```

If Sibyl has it on, comparing the top-N between hosts will tell us
whether the consensus-view dominance is a Gizmo phenomenon (driven
by the dashboard) or a workload-shape that exists across both
replicas. If Sibyl doesn't have it on, enabling there is the same
recipe (postgresql.conf + restart + `CREATE EXTENSION`) — schedule
the restart for a quiet maintenance window.

### A4. More targeted matviews

Modeled on `obs_sbn_neo` and `obs_summary`:

- `obs_sbn_pha` — PHAs only, even smaller subset (< 10 K rows of
  obs per typical month).
- `obs_sbn_numbered` — obs of numbered objects only, where the
  long-arc science lives.
- `obs_sbn_recent` — last 90 days, refreshed hourly. Supports a
  "what's new this week" view without touching the 526 M-row parent.

### A5. More functions in the `css_utilities` schema

SQL parity with `lib/`, so psql users get CSS-level analysis
without leaving the database:

- `is_neo(q, e)`, `is_pha(q, e, h)` — formal classification
- `tisserand(a, e, i)` — already conceptually present, just expose
- `pack_designation(text)` / `unpack_designation(text)` — currently
  Python-only in `lib/mpc_convert.py`

### A6. Autovacuum + bloat baseline

Confirm with `pgstattuple` (or `pg_stat_user_tables`) that
`obs_sbn`'s dead-tuple percentage is below ~10 %. High-append-low-
update tables typically don't bloat, but "we measured and it's
fine" is a stronger MUG sentence than "we never looked."  If
needed, schedule a one-time `pg_repack` and tune autovacuum
thresholds for the high-traffic tables.

## B. Library / toolkit improvements

### B1. `mpc-query` CLI

A thin wrapper exposing `lib/orbits.py` + `lib/identifications.py`
query-builders from the command line. Astronomers who don't want to
write Python or psql get something usable.

### B2. Notebook tutorials

Extend `notebooks/` with end-to-end examples:

- Querying the NEO consensus catalog
- Deriving an orbit class from current elements
- Generating an ADES file from local data
- Per-station rollups (mirrors the Station Report tab in code)

Pedagogy is high-value for a working-DB audience.

### B3. Consolidated `resolve_designation()`

Designation alias resolution currently lives in three places: a
Python function in `lib/identifications.py`, a SQL pattern through
`current_identifications` + `numbered_identifications`, and the
`obs_sbn_neo` matview's CTE. Yesterday's NEO-undercount bug came
from this divergence. One blessed function with a documented
contract reduces surprises and gives MUG users one path to follow.

## C. Alternatives to PostgreSQL — extend mpc_sbn's reach

mpc_sbn-on-PostgreSQL needs an authenticated connection from inside
the network. That's a real barrier for most users we'd like to
reach. The biggest "improving the utility" wins might be at the
distribution layer.

### C1. Parquet snapshots, published nightly

Small, redistributable, no auth needed. Publishable on GitHub
Releases or a Cloudflare R2 bucket; refreshed by an extra stage of
the daily pipeline.

- `mpc_sbn_neo.parquet` (~5 MB) — the consensus NEO catalog, flat
  schema, all six source-membership columns + canonical orbit
  elements + arc / nobs from `obs_summary`. **Highest impact.**
- `mpc_orbits.parquet` (~200 MB) — the full orbit catalog without
  JSON, with derived columns (`a` from `q/e`, `period` from `a`,
  classification label).
- `numbered_identifications.parquet`, `current_identifications.parquet`
  — designation maps, very small.

### C2. DuckDB recipe

Three lines of Python, zero infra:

```python
import duckdb
con = duckdb.connect()
con.execute("SELECT * FROM 'mpc_sbn_neo.parquet' WHERE q < 1.0").df()
```

DuckDB reads parquet directly as a SQL table, so anyone with `pip
install duckdb` has effectively local mpc_sbn access for the subsets
we publish. A one-page recipe in `docs/` is a high-leverage,
low-effort artifact.

### C3. VOTable export

A wrapper around `astropy.io.votable` over the parquet snapshots
bridges to TOPCAT, Aladin, and the broader VO ecosystem. MUG
members will recognize this as "we did the integration work for
you." Probably half a day of code.

### C4. Read-only HTTP/JSON API (deferred)

Would let web tools query mpc_sbn without psql. Real engineering
project; not in the MUG window. Worth flagging as where this
direction can go.

## D. Recommended MUG slate (next-week scope)

Revised 2026-04-29 after the BRIN / pg_stat_statements measurement:
the index-side "speedup story" is replaced by the matview
conversion, which has a much stronger before-and-after story
backed by real workload data.

1. **Dashboard βeta** — already shippable, announce it.
2. **`mpc_sbn_neo.parquet` snapshot + DuckDB recipe** — the single
   highest-impact "you can use this today" artifact.
3. **`v_membership_wide` matview conversion** (A0) — measurable,
   demonstrable speedup backed by `pg_stat_statements` before /
   after. ~40 % of DB time recovered for cross-source queries.
4. **2–3 `css_utilities` function additions** (`pack_designation`,
   `unpack_designation`, `is_neo`) — concrete value for psql users.
5. **One notebook tutorial** that ties them all together: query
   `mpc_sbn_neo` locally with DuckDB, classify orbits via
   `css_utilities`, plot.

Pitch: a tool you can browse + a snapshot you can use + measurable
speedups under the hood, all in one announcement.

## E. Beyond MUG (deferred)

- ADS reconciliation for MPEC publications. Naïve `bibstem:MPEC
  fulltext:V00` returns zero — ADS doesn't fulltext-index MPEC
  bodies — so this needs starting from MPC's MPEC index and
  cross-referencing against ADS. Likely weeks, not days.
- `obs_sbn` time-range partitioning. Big win for very-long-range
  scans, but a substantial schema change.
- HTTP/JSON read API for mpc_sbn.
- Mobile-friendly dashboard variant for select tabs (Tools,
  MPEC Browser, About).
- In-process cache reload to eliminate the ~5 s daily 502 window
  during dashboard restart.

## F. Calibrating against real workload

`pg_stat_statements` on Gizmo (already running, A3) gives us
automatic workload signal — top-N by total time, mean time, calls.
That covers the dashboard's own usage and anything else routed
through the Gizmo replica.

What it doesn't capture is *Sibyl*'s year+ of workload from
notebooks, ad-hoc psql sessions, and scripts that never ran on
Gizmo. To complement the automatic capture:

- **Check Sibyl** for `pg_stat_statements` (recipe in A3). If on,
  pull the top-N and compare to Gizmo's profile. Significant
  divergence tells us where Gizmo's index inventory may be
  optimized for the dashboard at the expense of other shapes.
- **Drop representative `.sql` files into `sql/examples/`** — one
  query per file, top-of-file comment about purpose and any known
  pain. The shapes that help most:
  - **Recurrent queries** that script-driven workloads run often.
  - **Known slow queries** — anywhere you've thought "this should
    be faster than it is."
  - **Aspirational queries** — things you've wanted to ask of
    mpc_sbn but skipped because they were too slow or awkward to
    write.

Five to ten representative queries — combined with the automatic
top-N from `pg_stat_statements` — are enough to:

- Decide which (additional) composite indexes are worth the
  maintenance cost vs. over-indexing the table.
- Identify what should land in `css_utilities` as a helper
  function vs. stay client-side.
- Spot what should become a matview vs. an on-demand query (A0
  is the obvious first such finding).
