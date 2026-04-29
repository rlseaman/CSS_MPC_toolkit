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

Quick wins, 1–3 days each:

### A1. BRIN on `obs_sbn.obstime`

`obs_sbn` is monotonically appended via logical replication, so
physical row order is highly correlated with `obstime`. That's the
sweet spot for a Block Range Index — orders of magnitude smaller
than a btree (a few MB instead of ~10 GB) and faster for date-range
scans, which dominate analytic queries. Same case applies to
`created_at` and `updated_at` if you want to support
"what was submitted/changed in the last N days" queries.

### A2. Multi-column index `(stn, obstime)`

The Station Report query took ~2:30 on V00 (4.5 M rows from the
indexed `stn` filter, then row-by-row aggregation). A composite
index on `(stn, obstime)` reduces this to seconds — index seeks
return only the obs in the right station and date range, in order.
Same shape benefits follow-up-timing queries and per-station
rollups generally.

### A3. `pg_stat_statements` audit

If `pg_stat_statements` is enabled, you have months of real
workload data already; it just needs reading. A "top 20 by total
elapsed time" report tells us where to add indexes guided by actual
queries rather than guesses. If it isn't enabled, enabling it is a
postgresql.conf line + a one-time PG restart, after which it
accumulates silently.

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

If we have ~5–7 days of focus before the meeting, the highest-yield
bundle is a coherent story rather than any one piece:

1. **Dashboard βeta** — already shippable, announce it.
2. **`mpc_sbn_neo.parquet` snapshot + DuckDB recipe** — the single
   highest-impact "you can use this today" artifact.
3. **BRIN on `obstime` + composite `(stn, obstime)` index** —
   measurable performance wins, easy to demo.
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
