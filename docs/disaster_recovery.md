# Dashboard disaster recovery

Context for what to do if the public dashboard at
[hotwireduniverse.org](https://hotwireduniverse.org) stops serving
fresh data.

## Normal architecture (as of 2026-04-24)

All three data paths are native to **Gizmo**:

- **DB source:** Gizmo's local `mpc_sbn` replica (PostgreSQL 18.3, NVMe,
  logical replication from SBN RDS).
- **Daily refresh:** launchd agent `org.seaman.gizmo-refresh` at 06:00
  MST runs `scripts/refresh_matview_gizmo.sh`, which:
  1. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo` (~3.6 min)
  2. Rebuilds all three parquet caches via
     `python app/discovery_stats.py --refresh-only` (~1 min)
- **Dashboard:** `start-dashboard.sh` loads the parquets at startup.

Gizmo is a single point of failure for the public dashboard in this
configuration. That trade was made consciously because the alternative
(MBP-seeded pipeline) was flaky in ways the Gizmo-native path is not —
see commit history around the 2026-04-24 project relocation for the
TCC / path-bake-in issues that motivated the change.

## Failure modes and recovery

### A) Gizmo DB replication falls behind or breaks

**Symptom:** `obs_sbn_neo` still refreshes on schedule, but the data
underneath is stale. Dashboard shows old counts; new observations from
MPC don't appear.

**Diagnosis on Gizmo:**
```bash
ssh robertseaman@192.168.0.157
PGHOST=/tmp psql -d mpc_sbn -c "\
  SELECT subname, received_lsn, last_msg_receipt_time, latest_end_time \
  FROM pg_stat_subscription;"
```
If `latest_end_time` is more than a few minutes behind wall-clock, the
subscription is lagging. If it's hours/days behind or NULL, the worker
is likely broken.

**Recovery:**
1. First try restarting the subscription worker:
   `ALTER SUBSCRIPTION sbn_css_gizmo_obs_table_sub DISABLE; ENABLE;`
2. If that doesn't catch up in a reasonable time, the upstream publisher
   slot may have been dropped. Contact Andrei @ SBN (2026-04 IP-whitelist
   contact) and reinitialize the subscription from scratch. This takes
   hours (initial sync of 535M-row `obs_sbn`).
3. **While Gizmo replication is out, fall back to MBP-seeded caches**
   (path B below) so the public dashboard stays current-ish.

### B) Gizmo DB unusable, host healthy

**Symptom:** Gizmo's DB is broken, slow, or the matview is corrupt, but
the host itself is up and the Dash process still serves cached data.

**Recovery — reseed caches from MBP-Sibyl pipeline:**
1. On MBP:
   ```bash
   cd ~/Projects/CSS_MPC_toolkit
   ./scripts/deploy_to_mini.sh      # or scripts/refresh_cron.sh for
                                    # lock/retry/sanity wrapping
   ```
   This rebuilds parquet caches from Sibyl and rsyncs them to Gizmo.
   Expect ~20–30 minutes (BOXSCORE_SQL on Sibyl HDD is ~13 min).
2. On Gizmo, restart the dashboard so it picks up the fresh caches:
   ```bash
   ssh robertseaman@192.168.0.157 '~/Claude/mpc_sbn/start-dashboard.sh'
   ```

**Why the MBP path still works when Gizmo DB is broken:** it queries
Sibyl (an independent replica) and only writes cache files to Gizmo's
filesystem, never touching Gizmo's Postgres. The scripts stay in-repo
specifically so this fallback is one command away.

### C) Gizmo host down entirely

**Symptom:** hotwireduniverse.org returns 5xx or Cloudflare origin
unreachable.

**Recovery:**
1. Physical/remote check of the M4 Mac mini — SSH reachable?
2. If host is recoverable, restart dashboard + verify launchd agents
   loaded:
   ```bash
   ssh robertseaman@192.168.0.157
   launchctl list | grep seaman
   ~/Claude/mpc_sbn/start-dashboard.sh
   ```
3. If host is unrecoverable, the dashboard is down until it's restored.
   Sibyl is not set up to serve the public dashboard on its own — it
   hosts the replica, not the Dash app or the Cloudflare tunnel.
   Standing up a replacement dashboard host is a multi-hour project
   (Dash + tunnel + DNS), not a single-command recovery.

## Retained assets

These are kept in-repo and on-disk even though they're no longer
scheduled, because they are the only mechanism for path B and they
cost nothing to retain:

- `scripts/deploy_to_mini.sh` — rebuilds caches on MBP from Sibyl and
  rsyncs to Gizmo.
- `scripts/refresh_cron.sh` — lock/retry/sanity wrapper around
  `deploy_to_mini.sh`. No longer scheduled by launchd.
- `scripts/org.seaman.css-refresh.plist` — the (now-unscheduled) MBP
  LaunchAgent file, kept in-repo for rapid re-bootstrap if the Gizmo
  path goes permanently non-viable.

The MBP agent was `bootout`ed on 2026-04-24. To re-arm if needed:
```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/org.seaman.css-refresh.plist
```
(The installed plist file is still in `~/Library/LaunchAgents/`.)

## Monitoring checklist

After the 06:00 MST refresh, verify:

```bash
ssh robertseaman@192.168.0.157 cat ~/Claude/mpc_sbn/matview/last_refresh_status.json
```

Expected: `"status": "OK"`, fresh `ts`, `elapsed_s` around 450–550 s,
broken down as `stage1_s` ≈ 170–220 (matview REFRESH CONCURRENTLY),
`stage2_s` ≈ 280–320 (`--refresh-only`: LOAD_SQL + NEA.txt resolve +
APPARITION_SQL + BOXSCORE + SBDB MOID API + PHA.txt).

An OK status with `elapsed_s` well outside that range (say >900 s) is a
soft warning — probably a cache-cold stage 1 or a replication-catchup
spike, worth investigating.
