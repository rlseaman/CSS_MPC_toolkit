# SBN PostgreSQL 18 rebuild: subscriber resync runbook (2026-10-26)

> **Outcome (2026-10-27): not needed this time; kept as the contingency
> for a future from-scratch resync.** SBN synced its new Aurora PG18
> cluster through a backup chain and paused the MPC stream at a
> checkpoint (2026-10-26 ~13:29 UTC). Subscribers keeping their major
> version ("Group 2") resumed with no re-copy:
>
> 1. Confirm the checkpoint values in UTC: `current_identifications`
>    max `updated_at` 2026-10-26 13:26:56.66856, `mpc_orbits`
>    13:29:45.99212, `obs_sbn` 13:29:15.766536+00.
> 2. Drop both subscriptions.
> 3. Create them again **under the same names** with
>    `copy_data = false` against
>    `aurora_pg_cluster_{obs_table,other_tables}_pub` on
>    `sbn-am-aurora-pg-cluster.cluster-c1t4y1fwdvea.us-east-2.rds.amazonaws.com`.
>
> When each replica switched:
> - **Sibyl** (15.15): 10-26, `binary = true, streaming = true`.
> - **Gizmo** (18.3): 10-27 14:25 UTC, `binary = true,
>   streaming = parallel, synchronous_commit = off`.
>
> Both matched the checkpoint exactly. No agents were paused and no
> tables were moved.
>
> **Lesson:** during the pause, `db_up_check.sh` stayed green for about
> 25 h. The workers were alive and keep-alives kept arriving, but no
> data came in. It needs a data-freshness test.

On 2026-10-26 (Full Moon), SBN rebuilds its EC2 publisher and Aurora
cluster from scratch on PostgreSQL 18, replacing v16. SBN's estimates:
a 10–12 h outage on their side, and 15–18 h or more for subscribers.
Subscribers are asked to rebuild as well.

**What this means for us.** The publisher is rebuilt, so the replication
slots behind our subscriptions disappear. Every subscriber has to drop
its subscription and copy the data again from the start. This applies
to Gizmo even though Gizmo already runs 18.3. Sibyl (15.15) also gets
a major-version upgrade, but later (§9).

**Strategy, in order of priority:**

1. **Protect the irreplaceable local state.** `css_orbit_watch`,
   `css_neo_consensus` and `css_ades_overlay` live in the same
   database. We never rebuild the database. Only the 18 replicated
   tables are replaced.
2. **Keep yesterday's data until the new copy checks out.** We don't
   TRUNCATE. We move the old tables into a holding schema
   (`sbn_pre_resync`) and subscribe fresh, empty tables in `public`.
   The matviews and views move along with the old tables, so the
   dashboard keeps working on the old data. Rollback is a schema move
   (§8).
3. **Stop automation from running on partial data.** The orbit-watch
   diff against a half-loaded `mpc_orbits` would write thousands of
   false NEO_EXIT/PHA_EXIT rows into the append-only `orbit_event`
   log. The nightly refresh would rebuild the public caches from
   partial tables.
4. **Stagger the replicas.** Gizmo resyncs first. Sibyl keeps its
   frozen 2026-10-26 copy as the fallback for the MBP-seeded cache path
   (`scripts/deploy_to_mini.sh`, DR doc §B) until Gizmo is verified.

All commands in §2–§8 run **on Gizmo** as `robertseaman` (superuser),
unless marked otherwise:

```bash
ssh robertseaman@192.168.0.157
export PGHOST=/tmp PGDATABASE=mpc_sbn
W=~/Claude/mpc_sbn/resync_2026-10-26     # working dir; holds conninfo → mode 700
mkdir -p $W && chmod 700 $W
```

Gizmo runs on MST (UTC−7, no DST). Ask SBN to give times in UTC.

---

## 0. Facts as of 2026-10-13 (re-check on the day)

| | Gizmo | Sibyl |
|---|---|---|
| Version | 18.3 (Homebrew) | 15.15 (RHEL 8.6) |
| Subscriptions | `sbn_css_gizmo_obs_table_sub` → `sbn146_obs_table_pub` (binary, streaming=parallel)<br>`sbn_css_gizmo_other_tables_sub` → `sbn146_other_tables_pub` (streaming=parallel) | `sbn146_css_obs_table_sibyl_sub`<br>`sbn146_css_other_tables_sibyl_sub` |
| DB size | 307 GB (`obs_sbn` 294 GB: 224 GB heap + 70 GB indexes) | 454 GB |
| Free disk | 3.3 TB on `/Volumes/data1` | **unknown, check** |
| Local schemas | `css_ades_overlay`, `css_neo_consensus`, `css_orbit_watch`, `css_utilities` | `css_utilities` |

**The 18 replicated tables** (all owned by `postgres`, replica identity
default = PK, no triggers, no sequences):
`obs_sbn` (557.8M rows) in the obs publication; `comet_names`,
`current_identifications`, `minor_planet_names`, `mpc_orbits`,
`neocp_els`, `neocp_events`, `neocp_obs`, `neocp_obs_archive`,
`neocp_prev_des`, `neocp_var`, `numbered_identifications`,
`obs_alterations_corrections`, `obs_alterations_deletions`,
`obs_alterations_redesignations`, `obs_alterations_unassociations`,
`obscodes`, `primary_objects` in the other.

**Local objects that depend on them.** These move with the tables when
they are parked, and are rebuilt in §7:

| Object | Kind | Reads |
|---|---|---|
| `public.obs_sbn_neo` | matview | obs_sbn, mpc_orbits, numbered_/current_identifications |
| `public.obs_summary_all` | matview | obs_sbn |
| `css_neo_consensus.obs_summary` | matview | obs_sbn |
| `css_neo_consensus.v_member_designations` | view | numbered_/current_identifications |
| `css_ades_overlay.v_effective` | view | obs_sbn |
| `css_orbit_watch.v_epoch_migration` | view | mpc_orbits |

Nothing depends on these six objects in turn (checked 2026-10-13).

**Our 12 secondary indexes on `obs_sbn`** (58 GB), deliberately
different from upstream; see memory `gizmo_mpc_sbn_replica.md`:
`idx_obs_sbn_disc` (partial), `idx_obs_sbn_permid`, `idx_obs_sbn_provid`,
`idx_obs_sbn_trkid`, `idx_obs_stn_time`, `obs_sbn_count_simple_idx`,
`obs_sbn_created_at_idx`, `obs_sbn_obstime_idx`, `obs_sbn_obstime_text_idx`,
`obs_sbn_stn_idx`, `obs_sbn_trksub_idx`, `obs_sbn_updated_at_idx`.
Also: `STATISTICS 500` on provid/permid/trkid/trksub/obstime, and the
autovacuum scale factors 0.01 / 0.005.

**Live obs_sbn readers in the app.** Only `lib/observation_history.py`
(the Tab 8 V-vs-time plot and finding chart). It reads `public.obs_sbn`
by name, so it will show partial data while the copy runs. Everything
else reads the parquet caches or the matviews.

---

## 1. Questions for SBN (send this week)

1. Are the publication names unchanged (`sbn146_obs_table_pub`,
   `sbn146_other_tables_pub`), with the same 18 tables in each?
2. Are the publisher host, IP, port and credentials unchanged? (Today:
   `18.189.159.179:5432`.)
3. Does the IP whitelist carry over? Gizmo is `98.161.181.28`
   ("CSS_gizmo"); also Sibyl's address.
4. **Are there any DDL changes to the 18 tables in the v18 build?**
   Please send `pg_dump -s` for them. A column missing on our side stops
   the apply worker.
5. When does the work start, in UTC? How will you announce "subscribers
   may resubscribe now"?
6. Should subscribers drop their slots before the teardown, or will you
   handle it?
7. Is it OK if Sibyl resyncs a few days after Gizmo instead of the
   same day?

---

## 2. Prep week (by Fri 2026-10-23)

### 2.1 Pin PostgreSQL

```bash
brew pin postgresql@18     # unpin after the event (§10)
```

A new binary path silently loses the Full Disk Access grant, and then
PG won't start under launchd (DR doc §D). Don't change the binary
right before the event.

### 2.2 Save the connection strings (contains secrets, keep out of git)

```bash
psql -Atc "SELECT subname, subconninfo FROM pg_subscription" > $W/conninfo.txt
chmod 600 $W/conninfo.txt
```

Update it with whatever SBN answers to Q2.

### 2.3 Capture DDL

```bash
cd $W
T=""
for t in obs_sbn comet_names current_identifications minor_planet_names \
         mpc_orbits neocp_els neocp_events neocp_obs neocp_obs_archive \
         neocp_prev_des neocp_var numbered_identifications \
         obs_alterations_corrections obs_alterations_deletions \
         obs_alterations_redesignations obs_alterations_unassociations \
         obscodes primary_objects; do T="$T -t public.$t"; done

# tables, defaults, reloptions, per-column STATISTICS, ownership
pg_dump -s --section=pre-data  $T > 10_tables.sql
# PKs + every index
pg_dump -s --section=post-data $T > post_all.sql
# split: the 12 obs_sbn secondary indexes are built AFTER the copy
grep -E  '^CREATE (UNIQUE )?INDEX .* ON public\.obs_sbn USING' post_all.sql > 40_obs_sbn_indexes.sql
grep -vE '^CREATE (UNIQUE )?INDEX .* ON public\.obs_sbn USING' post_all.sql > 20_keys_and_small_indexes.sql
wc -l 40_obs_sbn_indexes.sql            # expect 12
grep -c 'obs_sbn_pkey' 20_keys_and_small_indexes.sql   # expect ≥1: PK stays

# the six dependents, as built (WITH NO DATA + their indexes + grants)
pg_dump -s -t public.obs_sbn_neo -t public.obs_summary_all \
           -t css_neo_consensus.obs_summary \
           -t css_neo_consensus.v_member_designations \
           -t css_ades_overlay.v_effective \
           -t css_orbit_watch.v_epoch_migration > 30_dependents.sql
```

Keep the `obs_sbn` **primary key** in place during the copy. The table
sync worker applies UPDATEs and DELETEs that arrive during the copy,
and without the PK each one would be a sequential scan over 557M rows.
Build only the secondary indexes afterwards.

If SBN sends new DDL (Q4), diff it against `10_tables.sql` and edit the
file. **Extra columns on our side are fine. Missing columns are not.**

### 2.4 Rehearse the DDL on a scratch database (~10 min)

This mirrors the day-of order: replicated tables first, then local
schemas, then the dependents rebuilt from `30_dependents.sql`.

```bash
R="psql -d resync_rehearsal -v ON_ERROR_STOP=1"
createdb resync_rehearsal
$R -f 10_tables.sql -f 20_keys_and_small_indexes.sql
pg_restore -d resync_rehearsal ~/Claude/mpc_sbn/backups/dumps/latest.dump   # css_* schemas
# the css dump already holds 4 of the 6 dependents; drop them so 30 rebuilds them
$R -c "DROP VIEW css_orbit_watch.v_epoch_migration, css_ades_overlay.v_effective,
              css_neo_consensus.v_member_designations;
       DROP MATERIALIZED VIEW css_neo_consensus.obs_summary;"
$R -f 30_dependents.sql -f 40_obs_sbn_indexes.sql
$R -c "REFRESH MATERIALIZED VIEW public.obs_sbn_neo;
       REFRESH MATERIALIZED VIEW public.obs_summary_all;
       REFRESH MATERIALIZED VIEW css_neo_consensus.obs_summary;"
dropdb resync_rehearsal
```

Everything must apply cleanly under `ON_ERROR_STOP`. If a step fails
on a missing role, schema or object, fix the captured files now, not
on the day. `dumps/latest.dump` points at the newest nightly dump
(`ls -t ~/Claude/mpc_sbn/backups/dumps/` to confirm).

### 2.5 Record a baseline

```bash
psql -f ~/CSS_MPC_toolkit/sql/benchmarks/compare_hosts.sql > $W/compare_before.txt
psql -Atc "SELECT relname, reltuples::bigint FROM pg_class
           WHERE relnamespace='public'::regnamespace AND relkind='r' ORDER BY 1" > $W/reltuples_before.txt
```

---

## 3. T-1: Sun 2026-10-25, evening

1. **Fresh backup of the local schemas:**
   `~/CSS_MPC_toolkit/scripts/pg_backup_gizmo.sh`, then check that
   `pg_restore -l` lists all four `css_*` schemas.
2. **Pause on healthchecks.io** (web UI → Pause): `gizmo-refresh`,
   `site-up`, `db-up`. A paused check resumes by itself on its next
   ping, so no unpause step is needed. Leave `pg-backup` and
   `tm-backup` running. **Don't send test `/fail` pings.**
3. **Stop the three agents** that touch the replicated tables. A
   bootout alone doesn't stick across a login, so also disable them:

   ```bash
   for j in org.seaman.gizmo-refresh org.seaman.orbit-watch org.seaman.db-up; do
     launchctl bootout gui/$(id -u)/$j
     launchctl disable gui/$(id -u)/$j
   done
   launchctl list | grep -E 'gizmo-refresh|orbit-watch|db-up'   # expect nothing
   ls -d /tmp/gizmo_matview_refresh.lock 2>/dev/null            # expect nothing
   ```

   Leave both dashboards, the tunnel, `pg-backup` and `tm-check`
   running.

---

## 4. When SBN starts the work (old publisher goes away)

Stop the apply workers so they don't spin on reconnect errors. The data
in `public` stays intact and the site keeps working on it.

```sql
ALTER SUBSCRIPTION sbn_css_gizmo_obs_table_sub    DISABLE;
ALTER SUBSCRIPTION sbn_css_gizmo_other_tables_sub DISABLE;
```

Then **wait for SBN's go-ahead** (Q5). Don't park the tables early: the
old copy in `public` is the best data available until the new one
starts arriving.

---

## 5. On SBN's go-ahead: park the old tables, subscribe the new ones

### 5.1 Drop the old subscriptions

The remote slots are gone, so detach them first. Otherwise the DROP
tries to reach the old publisher and fails.

```sql
ALTER SUBSCRIPTION sbn_css_gizmo_obs_table_sub    SET (slot_name = NONE);
ALTER SUBSCRIPTION sbn_css_gizmo_other_tables_sub SET (slot_name = NONE);
DROP SUBSCRIPTION sbn_css_gizmo_obs_table_sub;
DROP SUBSCRIPTION sbn_css_gizmo_other_tables_sub;
```

### 5.2 Park the old tables (one transaction, takes seconds)

```sql
CREATE SCHEMA sbn_pre_resync;
BEGIN;
ALTER TABLE public.obs_sbn                        SET SCHEMA sbn_pre_resync;
ALTER TABLE public.comet_names                    SET SCHEMA sbn_pre_resync;
ALTER TABLE public.current_identifications        SET SCHEMA sbn_pre_resync;
ALTER TABLE public.minor_planet_names             SET SCHEMA sbn_pre_resync;
ALTER TABLE public.mpc_orbits                     SET SCHEMA sbn_pre_resync;
ALTER TABLE public.neocp_els                      SET SCHEMA sbn_pre_resync;
ALTER TABLE public.neocp_events                   SET SCHEMA sbn_pre_resync;
ALTER TABLE public.neocp_obs                      SET SCHEMA sbn_pre_resync;
ALTER TABLE public.neocp_obs_archive              SET SCHEMA sbn_pre_resync;
ALTER TABLE public.neocp_prev_des                 SET SCHEMA sbn_pre_resync;
ALTER TABLE public.neocp_var                      SET SCHEMA sbn_pre_resync;
ALTER TABLE public.numbered_identifications       SET SCHEMA sbn_pre_resync;
ALTER TABLE public.obs_alterations_corrections    SET SCHEMA sbn_pre_resync;
ALTER TABLE public.obs_alterations_deletions      SET SCHEMA sbn_pre_resync;
ALTER TABLE public.obs_alterations_redesignations SET SCHEMA sbn_pre_resync;
ALTER TABLE public.obs_alterations_unassociations SET SCHEMA sbn_pre_resync;
ALTER TABLE public.obscodes                       SET SCHEMA sbn_pre_resync;
ALTER TABLE public.primary_objects                SET SCHEMA sbn_pre_resync;
COMMIT;
GRANT USAGE ON SCHEMA sbn_pre_resync TO claude_ro;
```

The six dependents refer to tables by OID, so they now read the parked
copies and keep serving yesterday's data.

### 5.3 Create the empty tables and tune for bulk load

```bash
psql -v ON_ERROR_STOP=1 -f $W/10_tables.sql -f $W/20_keys_and_small_indexes.sql
psql -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO claude_ro;"
psql -c "ALTER SYSTEM SET max_wal_size = '16GB';" -c "SELECT pg_reload_conf();"
```

From here until §6 finishes, the Tab 8 plot and finding chart show
partial data (§0).

### 5.4 Subscribe

Take `<CONNINFO>` from `$W/conninfo.txt`, updated with SBN's answer to
Q2. Use the same names and options as before.

```sql
CREATE SUBSCRIPTION sbn_css_gizmo_other_tables_sub
  CONNECTION '<CONNINFO>'
  PUBLICATION sbn146_other_tables_pub
  WITH (copy_data = true, streaming = parallel, synchronous_commit = off);

CREATE SUBSCRIPTION sbn_css_gizmo_obs_table_sub
  CONNECTION '<CONNINFO>'
  PUBLICATION sbn146_obs_table_pub
  WITH (copy_data = true, binary = true, streaming = parallel, synchronous_commit = off);
```

### 5.5 Monitor

```sql
-- tables not yet ready (i=init, d=copying, f/s=syncing, r=ready)
SELECT s.subname, c.relname, r.srsubstate
  FROM pg_subscription_rel r
  JOIN pg_subscription s ON s.oid = r.srsubid
  JOIN pg_class c ON c.oid = r.srrelid
 WHERE r.srsubstate <> 'r' ORDER BY 1, 2;

-- copy progress: obs_sbn target ≈ 557.8M tuples
SELECT relid::regclass, tuples_processed,
       round(100.0 * tuples_processed / 557.8e6, 1) AS pct_of_obs_sbn,
       pg_size_pretty(bytes_processed) AS bytes
  FROM pg_stat_progress_copy;

SELECT subname, received_lsn, last_msg_receipt_time FROM pg_stat_subscription;
```

Also watch the PG log for `logical replication target relation ... is
missing replicated column`. That error is a DDL change (Q4). Fix it
with `ALTER TABLE public.<t> ADD COLUMN ...`, and the worker retries on
its own.

The other-tables subscription (about 9 GB) should reach `r` within
minutes to an hour. `obs_sbn` is the long one: SBN estimates 5–6 h, and
we have no Gizmo measurement for a copy with the PK in place.

---

## 6. After every table reaches `r`

```bash
# 12 secondary indexes, ~58 GB. Plain CREATE INDEX blocks the apply worker
# while it runs; replication lag builds up and then catches up. That's fine.
psql -v ON_ERROR_STOP=1 \
     -c "SET maintenance_work_mem = '4GB'; SET max_parallel_maintenance_workers = 4;" \
     -f $W/40_obs_sbn_indexes.sql
```

Note: `-c` and `-f` run in the same session, so the `SET`s apply.

```sql
VACUUM (FREEZE, ANALYZE, VERBOSE) public.obs_sbn;  -- avoids a later anti-wraparound surprise
ANALYZE;                                           -- the 17 small tables
ALTER SYSTEM SET max_wal_size = '4GB';
SELECT pg_reload_conf();
```

### 6.1 Verify before switching the dependents over

1. **Schema.** Compare column lists: new `public.*` against
   `sbn_pre_resync.*` (`information_schema.columns`). Any difference
   should be one SBN told us about.
2. **Small tables.** Run `count(*)` on new and parked. New ≥ parked,
   apart from known deletions.
3. **obs_sbn**, using indexed queries only. **No unfiltered COUNT.**
   - `reltuples` after ANALYZE should be about 557.8M or more.
   - Run per-day `count(*) WHERE created_at >= now() - interval '30 days'
     GROUP BY 1` on both, and diff them.
   - For Apophis, `count(*) WHERE permid = '99942'` on both should
     match or be larger.
4. **Did row identity or timestamps change?** For about 20 sample
   `obsid`s, compare `id`, `created_at` and `updated_at` between parked
   and new.
   - Nothing local keys on `obs_sbn.id`; `obs_sbn_neo` is rebuilt.
   - But `css_ades_overlay.tracklet.basis_max_updated` uses
     `updated_at` for drift detection, and `orbit_snapshot.src_updated_at`
     records `mpc_orbits.updated_at`. If SBN reset the timestamps, note
     it here and expect drift flags in the overlay and a one-time jump
     in orbit-watch.
5. Run `compare_hosts.sql` into `$W/compare_after.txt` and diff it
   against `compare_before.txt`. The only differences should be growth
   since 10-25.

If anything here looks wrong, **stop and use §8 (rollback)**. The
dependents still point at the parked data, so the site stays whole.

---

## 7. Point the dependents at the new tables

Use one transaction. Readers of the six objects (the Consensus tab's
`obs_summary` join) **block for about 12 min instead of erroring**.

```bash
psql -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
DROP VIEW css_orbit_watch.v_epoch_migration;
DROP VIEW css_ades_overlay.v_effective;
DROP VIEW css_neo_consensus.v_member_designations;
DROP MATERIALIZED VIEW css_neo_consensus.obs_summary;
DROP MATERIALIZED VIEW public.obs_summary_all;
DROP MATERIALIZED VIEW public.obs_sbn_neo;
\i /Users/robertseaman/Claude/mpc_sbn/resync_2026-10-26/30_dependents.sql
REFRESH MATERIALIZED VIEW public.obs_sbn_neo;              -- ~4 min
REFRESH MATERIALIZED VIEW css_neo_consensus.obs_summary;   -- ~5 min
REFRESH MATERIALIZED VIEW public.obs_summary_all;          -- ~2.5 min
COMMIT;
SQL
```

Then confirm nothing still reads the parked schema. This should return
0 rows:

```sql
SELECT DISTINCT v.oid::regclass
  FROM pg_depend d JOIN pg_rewrite w ON w.oid = d.objid
  JOIN pg_class v ON v.oid = w.ev_class
  JOIN pg_class t ON t.oid = d.refobjid
 WHERE t.relnamespace = 'sbn_pre_resync'::regnamespace AND v.oid <> t.oid;
```

### 7.1 Re-enable automation, one agent at a time

```bash
U=gui/$(id -u); LA=~/Library/LaunchAgents

# 1. db-up first: confirms replication is healthy and un-pauses its check
launchctl enable $U/org.seaman.db-up && launchctl bootstrap $U $LA/org.seaman.db-up.plist
launchctl kickstart $U/org.seaman.db-up;  tail -2 ~/Claude/mpc_sbn/logs/db_up_check.log

# 2. full nightly pipeline (~19 min): consensus ingest, parquet rebuild,
#    Dash restart, public-URL probe. Un-pauses gizmo-refresh + site-up.
launchctl enable $U/org.seaman.gizmo-refresh && launchctl bootstrap $U $LA/org.seaman.gizmo-refresh.plist
launchctl kickstart $U/org.seaman.gizmo-refresh
# watch the newest ~/Claude/mpc_sbn/logs/refresh_*.log to the end
```

Spot-check the public site: Tab 8 with Apophis, the Consensus counts,
and the "Caches refreshed" label. Then the dev worktree:

```bash
find ~/CSS_MPC_toolkit_dev/app -maxdepth 1 -type l \! -exec test -e {} \; -delete
launchctl kickstart -k $U/com.rlseaman.dashboard-rnd
```

### 7.2 Orbit watch (last, and by hand)

`daily_diff.sql` compares the two most recent snapshot dates, so the
first run after the gap compares against 10-25 and folds several days
of churn into one diff. That is correct, as long as **no snapshot was
taken from partial data**. Check first:

```sql
SELECT snapshot_date, count(*) FROM css_orbit_watch.orbit_snapshot
 WHERE snapshot_date >= '2026-10-25' GROUP BY 1 ORDER BY 1;
-- only 10-25 (~50K) should appear. If a partial date slipped in:
--   DELETE FROM css_orbit_watch.orbit_event    WHERE event_date    = '<bad>';
--   DELETE FROM css_orbit_watch.orbit_snapshot WHERE snapshot_date = '<bad>';
```

```bash
launchctl enable $U/org.seaman.orbit-watch && launchctl bootstrap $U $LA/org.seaman.orbit-watch.plist
launchctl kickstart $U/org.seaman.orbit-watch
```

Read the newest `~/orbit_watch_cron/orbitwatch_*.log`. The baseline is
161 events in 87 days, about 2 a day. Expect more after a multi-day
gap, but **hundreds of EXIT events point to a data problem**. In that
case delete that date's events and snapshot (above) and investigate
before the next 07:00 run.

---

## 8. Rollback (any time before §7)

The goal is to return to yesterday's data, stale but consistent, while
the problem is sorted out with SBN.

```sql
ALTER SUBSCRIPTION sbn_css_gizmo_obs_table_sub    DISABLE;
ALTER SUBSCRIPTION sbn_css_gizmo_other_tables_sub DISABLE;
DROP SUBSCRIPTION sbn_css_gizmo_obs_table_sub;      -- add slot_name = NONE first if the publisher is unreachable
DROP SUBSCRIPTION sbn_css_gizmo_other_tables_sub;
BEGIN;
DROP TABLE public.obs_sbn, public.comet_names, public.current_identifications,
           public.minor_planet_names, public.mpc_orbits, public.neocp_els,
           public.neocp_events, public.neocp_obs, public.neocp_obs_archive,
           public.neocp_prev_des, public.neocp_var, public.numbered_identifications,
           public.obs_alterations_corrections, public.obs_alterations_deletions,
           public.obs_alterations_redesignations, public.obs_alterations_unassociations,
           public.obscodes, public.primary_objects;   -- nothing depends on them before §7
-- then the 18 ALTER TABLE sbn_pre_resync.<t> SET SCHEMA public; from §5.2, reversed
COMMIT;
```

The dependents follow the tables back. The agents can be re-enabled
(§7.1). The refresh will just keep rebuilding from the frozen data.
Leave orbit-watch off until replication is back.

If Gizmo breaks altogether: Sibyl still holds the 10-26 copy. Reseed
the caches from the MBP with `scripts/deploy_to_mini.sh` (DR doc §B).

---

## 9. Sibyl: v15 → v18, a few days after Gizmo is verified

Until then Sibyl's subscriptions are dead, but its data stays as of
10-26. That is our fallback, so leave it alone.

**Prerequisites (this week):**
- Root/admin access on Sibyl.
- PGDG 18 packages for EL8. Check availability. Moving to RHEL 8.10 or 9
  is also an option (host note 2026-10-08).
- **Free disk**: room for a second copy (Gizmo's fresh copy is 307 GB
  incl. indexes). Also a decision on whether Sibyl is worth keeping at
  all; see `docs/2026-10-08_host_planning_gadget_sibyl.md`.

**Procedure** (simpler than Gizmo: Sibyl has only `css_utilities` and
no matviews):

1. Install PG 18 side by side, with a new PGDATA on port 5433. Copy
   Gizmo's settings where the hardware allows (`wal_level=logical`,
   replication workers, `synchronous_commit=off` on the subscriptions).
2. Create roles (`claude_ro`), the 18 tables, and the PKs from Gizmo's
   `10_tables.sql` + `20_keys_and_small_indexes.sql`. Install
   `css_utilities` (`CREATE SCHEMA` first, then
   `sql/css_utilities_functions.sql` + `sql/install_classify_orbit.sql`).
3. Subscribe with Sibyl's own subscription names and IP (Q3/Q7). The
   HDD copy will take **longer than SBN's 5–6 h**. Plan for a day or
   more.
4. Build the secondary indexes (`40_obs_sbn_indexes.sql`), then
   `VACUUM (FREEZE, ANALYZE)`.
5. Run `compare_hosts.sql` on both Sibyl and Gizmo and diff the output.
6. Swap ports (18 → 5432), keep the v15 cluster stopped for a week,
   then remove it.

---

## 10. Cleanup (about a week after §7)

```sql
BEGIN; DROP SCHEMA sbn_pre_resync CASCADE; ROLLBACK;  -- dry run: read the NOTICE list;
                                                      -- expect only the 18 tables + their indexes
DROP SCHEMA sbn_pre_resync CASCADE;                   -- frees ~300 GB
```

```bash
brew unpin postgresql@18
rm -rf ~/Claude/mpc_sbn/resync_2026-10-26     # after copying any notes worth keeping
```

Record the measured timings (COPY, index build, VACUUM FREEZE, §7
transaction) back into this doc. They are the baseline for the next
resync and for gadget's initial copy.

---

## Timeline summary

| When | Step |
|---|---|
| By 10-16 | Send SBN the §1 questions |
| By 10-23 | §2: pin brew, save conninfo, capture DDL, rehearse, baseline. Sibyl prerequisites (§9) |
| 10-25 evening | §3: backup, pause healthchecks, stop 3 agents |
| SBN start | §4: disable subscriptions; site keeps serving the old data |
| SBN go-ahead | §5: drop subscriptions, park tables, create empty ones, subscribe |
| Copy done (+5–6 h, maybe more) | §6: indexes, VACUUM FREEZE, verify |
| Verified | §7: switch dependents, re-enable db-up → refresh → orbit-watch |
| +a few days | §9: Sibyl |
| +1 week | §10: drop the parked schema, unpin |
