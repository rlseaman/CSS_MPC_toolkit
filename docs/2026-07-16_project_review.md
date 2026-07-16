# Project Review — 2026-07-16

Full-stack review of the CSS MPC Toolkit: code, documentation, operating
infrastructure (both database replicas, launchd jobs, dashboards), and
procedures. Conducted with three parallel review passes (code
architecture, documentation, live infrastructure inspection on Gizmo)
plus a same-morning operational health check.

## Executive summary

The project is **operationally healthy** — replication caught up on both
replicas (byte-identical freshness), all five launchd agents loaded, all
four dashboard surfaces responding, the morning refresh and orbit-watch
both green. The two structural exposures are (1) **no database backup of
any kind** while locally-generated schemas (`css_ades_overlay`,
`css_orbit_watch`) now hold irreplaceable data on a fragile external
NVMe, and (2) **no outage alerting** — the July 10–14 power outage left
prod dark four days with no notification. The top code finding is that
the app's embedded NEO-selection predicate has **diverged in logic** from
the authoritative `sql/discovery_tracklets.sql`, not just in threshold.

## Project status snapshot

- **Prod dashboard**: 12 tabs at hotwireduniverse.org (200 OK), dev at
  dev.hotwireduniverse.org (Cloudflare Access, 302), both on Gizmo.
- **Replication**: both subscriptions at identical LSN, minutes-fresh;
  Gizmo (PG 18.3) and Sibyl (PG 15.15) `max(mpc_orbits.updated_at)`
  byte-identical. mpc_orbits at 1,558,585 rows. DB 297 GB on a 3.6 TB
  volume (91% free).
- **Nightly refresh** (06:00 MST): SUCCESS, 1452 s (~24 min — above the
  documented 16–19 min; watch, no errors). All stages green, all 8
  parquet caches written, 0 orphans swept.
- **Orbit-watch** (07:00 MST): green; 18 daily snapshots, 50,358 orbits
  today, 33 events total. Permanent snapshot gap 07-11→07-14 from the
  outage.
- **Git**: main and station-report in sync with origin on MBP, Gizmo
  checkout, and Gizmo dev worktree; all trees clean; no dangling
  parquet symlinks in the dev worktree.
- **Active workstreams**: ADES overlay (pilot live: ~1.62 M obs, ~414 K
  tracklets; 2003–2019 backlog ~100 M rows pending), Daily Orbit News
  (data side live since 06-26, dashboard tab not built), Station Report
  tab (paused pending ADS integration).

## Unmitigated risks (priority order)

### R1. No database backup; local schemas are irreplaceable
Time Machine has no destination configured; no pg_dump jobs, scripts,
or backup launchd agents exist on Gizmo. The implicit recovery story —
re-seed from SBN logical replication — covers only MPC-origin data. It
does **not** cover:

- `css_ades_overlay` — the reprocessed CSS astrometry MPC won't ingest
  (the entire point of the overlay);
- `css_orbit_watch.orbit_snapshot` — daily history that cannot be
  reconstructed after the fact (the July outage already put a permanent
  4-day hole in it);
- `css_neo_consensus` ingest history.

These sit on the same external Thunderbolt NVMe that dropped once
already (2026-06-27, cable bump). **Mitigation**: nightly `pg_dump` of
the three local schemas (small relative to the 297 GB DB) to the boot
volume and/or off-host; a Time Machine destination for boot-volume
config.

### R2. No outage alerting
The 4-day dark outage was discovered manually. The 2026-07-15
unattended-boot fix reduces recurrence odds but detects nothing.
**Mitigation**: external heartbeat on hotwireduniverse.org (e.g.
UptimeRobot / healthchecks.io) and/or a dead-man's-switch curl at the
end of refresh stage 6. Also: `apireq_summary.sh` alerting is still
commented out "pending a baseline" — the baseline now exists. UPS still
unpurchased.

### R3. NEO-definition divergence (correctness)
`sql/discovery_tracklets.sql:86` selects
`mo.q < 1.32 OR mo.orbit_type_int IN (0,1,2,3,20)`; the app's embedded
LOAD_SQL uses bare `mo.q <= 1.30` with **no orbit-class fallback**, so
the dashboard silently drops objects that are NEOs by orbit class with
q just over 1.30. The predicate is restated four times inside
`app/discovery_stats.py` (~lines 517, 534, 686, 763) plus once in the
SQL file. The two "NEO discovery" datasets from this repo will not
reconcile. **Mitigation**: decide the authoritative predicate once and
generate/import it everywhere (the long-standing CTE-unification goal).

### R4. Bus factor / bare-metal reconstructability
The load-bearing `local.postgresql18` plist, its `pg18-start.sh`
wrapper, and the `com.cloudflare.tunnel` agent exist only on Gizmo —
referenced in docs as prose, never checked in. `deployment.md` and
`server_provisioning.md` target Rocky Linux, not the Mac mini actually
running prod; `mac_mini_setup.md` is a stale bring-up checklist.
**Mitigation**: check the missing plists/wrapper into `scripts/`, add a
one-page Gizmo LaunchAgent inventory + macOS runbook.

### R5. Dependency hygiene
`requirements.txt` is floor-pinned only; `mpc-designation` installs
from a git branch tip (reproducibility + supply-chain risk — pin to a
SHA). The next scheduled pip-audit (~July 2026) is due now.

## Duplicated / overlapping functionality

1. **NEO predicate** — see R3; five statements of the same rule.
2. **Band→V correction table** (~25 constants) duplicated between
   `sql/discovery_tracklets.sql` and `app/discovery_stats.py:578-604`.
3. **Python↔SQL converter pair** — eight functions in
   `lib/mpc_convert.py` deliberately mirrored in
   `sql/css_utilities_functions.sql`; intentional dual-runtime port,
   but nothing asserts parity, so drift is silent.
4. **Three hand-rolled rate limiters** (`lib/api_clients.py` per-host;
   `lib/horizons.py`; `lib/mpec_parser.py`). The per-host one
   generalizes the other two — consolidate.
5. **Four parquet-cache load/TTL implementations**
   (`_load_cached_query`; inline apparition-cache variant;
   `lib/station_report.py`; `lib/horizons.py`) — and **no on-disk cache
   evicts files** (TTL governs freshness only): `.mpec_cache`,
   `.horizons_cache`, `.station_cache` grow monotonically; hash-bumped
   parquet orphans are cleaned only by the nightly sweep on the primary
   checkout. One shared cache module with age/size eviction fixes all.
6. **Monolith**: `app/discovery_stats.py` is 17,667 lines with 77
   callbacks in one module. lib/ decomposition is healthy; the app has
   none. Per-tab module split is the obvious refactor before the next
   big tab.

## Gaps

- **Testing**: 663 test lines (2 files, untouched since 2026-02-19)
  against ~26 K first-party lines; no pytest config; no CI. Highest
  value and DB-free: pack/unpack round-trips (`lib/mpc_convert.py`),
  orbit-class boundary cases, Python↔SQL converter parity. A GitHub
  Actions workflow could run these per-push at zero infra cost.
- **`lib/db.py`**: no `connect_timeout` on `psycopg2.connect` — the one
  hang risk in an app where every HTTP call has a timeout. (Also a
  detached docstring in `connect()`.)
- **Doc rot** (fixed in the commit accompanying this review):
  `dashboard_security.md` backlog listed launchd/waitress as open
  (shipped April); `deploy_to_mini.sh`/`refresh_cron.sh` headers still
  claimed active-pipeline status (DR-only since 2026-04-24); README
  said "PostgreSQL 15.2"; CLAUDE.md said ~15,500 lines and described
  only Sibyl under Database Access.
- **Loose ends**: remote branch `feature/neo-consensus-export`
  (`scripts/export_neo_consensus.py`) pushed but never merged — merge
  or delete. Sandbox promotion candidates: `sandbox/schema_review.md`,
  `sandbox/2026-05-28_neo_consensus_audit.md`,
  `sandbox/data_quality_findings_20260210.md`; shipped-feature plans in
  sandbox/ could archive to `docs/previous/`.
- **Cloudflare doc** (`cloudflare_tunnel_setup.md`) still self-labels
  the (now de-facto permanent) architecture "interim."
- Follow-up Comparison scoping doc never back-filled with what actually
  shipped (Phases 2A/2B/3A live only in CLAUDE.md).

## Unexploited opportunities

- **Orbit News dashboard tab** — three weeks of events accumulating
  with no surface; natural next dev tab.
- **ADES overlay scale-up** — pilot validated error-free; 3.3 TB of
  headroom. Schedule deliberately, and land backup (R1) first since the
  overlay is exactly the irreplaceable data.
- **Enable APIREQ alerting** — baseline is mature.
- **SBDB designation handling** — the only API anomaly on 07-15 was 36
  JPL 400s on the dual-designation comet `P/2006 HR30 = P/2026 M4`;
  the enrichment path should split on `=` before querying SBDB.

## Minor watch items

- `mpc_orbits` dead tuples: 272 K (~17%), last autovacuum 07-14 — fine,
  keep an eye on it.
- Refresh wall-clock creeping up (~24 min vs documented 16–19).

## Questions worth asking

1. If the NVMe dies right now, what do we actually lose? (Today:
   overlay + orbit-watch history + days of rebuild. Drives R1.)
2. How do we find out prod is down? (Today: we don't. Drives R2.)
3. Which NEO definition is authoritative? (Drives R3.)
4. Is the Rocky Linux off-host replica (`server_provisioning.md`,
   edited 07-15) still the plan? Changes the calculus on backup, UPS,
   and Gizmo-specific runbook investment.
5. Should Station Report unpause without ADS? The Q7 forensic stats
   don't depend on the literature search.
6. Could anyone else run this? (Drives R4.)

## Agreed next steps ("quick wins", to be scheduled)

1. Nightly pg_dump of the three local schemas + check missing plists
   into the repo.
2. Dead-man's-switch heartbeat on the refresh job / external uptime
   monitor.
3. NEO-predicate unification (single authoritative chain).
4. `connect_timeout` in `lib/db.py`; pin `mpc-designation` to a SHA;
   run the due pip-audit.
5. Doc-rot corrections (done with this review's commit).
