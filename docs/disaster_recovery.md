# Dashboard disaster recovery

Context for what to do if the public dashboard at
[hotwireduniverse.org](https://hotwireduniverse.org) stops serving
fresh data.

## Normal architecture (as of 2026-04-26)

Two Dash processes on Gizmo, both under launchd:

- **Prod** — `com.rlseaman.dashboard` → port 8050 → `hotwireduniverse.org`.
  Public, no auth.
- **R&D** — `com.rlseaman.dashboard-rnd` → port 8051 →
  `dev.hotwireduniverse.org`. Behind Cloudflare Access (email
  allow-list, configured in the Cloudflare Zero Trust dashboard).
  Runs the same `app/discovery_stats.py` with `--rnd` to enable
  R&D-only surfaces (currently the **NEO Consensus** tab).

Both processes share the cache directory and the `mpc_sbn` database;
they're independent instances of the same code, distinguished only
by the flag.

All three data paths are native to **Gizmo**:

- **DB source:** Gizmo's local `mpc_sbn` replica (PostgreSQL 18.3, NVMe,
  logical replication from SBN RDS).
- **Daily refresh:** launchd agent `org.seaman.gizmo-refresh` at 06:00
  MST runs `scripts/refresh_matview_gizmo.sh`, which (as of
  2026-04-27):
  1. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo` (~3.6 min)
  2. Refreshes all six `css_neo_consensus` source-membership tables
     (mpc, cneos, neocc, neofixer, mpc_orbits, lowell — best-effort,
     ~25 s total). Per-source success/failure logged in
     `css_neo_consensus.source_runs` and surfaced in the status JSON.
  3. `REFRESH MATERIALIZED VIEW CONCURRENTLY
     css_neo_consensus.obs_summary` (~5 min, best-effort). Pre-
     aggregates `obs_sbn` into per-NEO `first_obs / last_obs / arc /
     nobs` so the NEO Consensus tab joins instead of LATERAL-probing
     41K times. Failure is logged but doesn't fail the wrapper; the
     obs columns just lag a day.
  4. Rebuilds all four parquet caches (neo_cache, apparition_cache,
     boxscore_cache, consensus_membership) via
     `python app/discovery_stats.py --refresh-only` (~5 min). Runs
     after stages 2 + 3 so the consensus_membership cache captures
     today's fresh source ingest — without this ordering the
     banner-level NEO source filter would lag a day.
  5. Restarts the Dash process so it loads the freshly-written
     caches into memory (~5 s gap of 502s during rebind).
- **Dashboard:** `start-dashboard.sh` loads the parquets at startup.

The stage-3 restart is a deliberate bridge: Dash holds caches in memory
once loaded, so without it the on-disk refresh has no effect on what
hotwireduniverse.org serves. This was discovered 2026-04-26 when the
"Caches refreshed" UI label was found to be 3 days stale despite the
daily refresh succeeding.

**Critical detail in the plist:** `AbandonProcessGroup=true` is
required. Without it, launchd reaps the freshly-started Dash the
moment the refresh script exits — first-pass commissioning hit this
and left the site at 502 until manual recovery. See
`memory/feedback_launchd_abandonprocessgroup.md`.

Long-term fix per `memory/dashboard_hardening_backlog.md` #1: put
Dash under its own launchd agent so stage 3 becomes
`launchctl kickstart -k`. Even longer-term per #3: in-process cache
reload via SIGHUP or interval polling, eliminating the restart gap
entirely.

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

Expected: `"status": "OK"`, fresh `ts`, `elapsed_s` around 800–900 s,
broken down (in the post-2026-04-27 ordering) as `stage1_s` ≈
170–230 (obs_sbn_neo REFRESH CONCURRENTLY), `stage2_s` ≈ 20–30 (NEO
consensus, all 6 sources), `stage3_s` ≈ 280–320 (obs_summary REFRESH
CONCURRENTLY), `stage4_s` ≈ 280–320 (`--refresh-only`: LOAD_SQL +
NEA.txt resolve + APPARITION_SQL + BOXSCORE + SBDB MOID API + PHA.txt
+ consensus_membership), `stage5_s` ≈ 6–15 (Dash kill + restart).
The status JSON also carries a `consensus` map of
`{source: "ok"|"fail"}` after stage 2, an `obs_summary` field of
`"ok"|"fail"` after stage 3, and `new_dash_pid` when stage 5
succeeds.

Per-source consensus failures (e.g. NEOCC outage) don't fail the
overall job — stage 4 is best-effort. Inspect
`css_neo_consensus.source_runs` for details when a source's status is
`fail`, and watch `v_source_health.time_since_last_ok` for staleness.

Spot-check the dashboard's actual freshness by visiting
hotwireduniverse.org and reading the "Caches refreshed" label in the
upper left — it should match the stage-2 cache mtime, i.e. last
fired window. If it's older, stage 3 likely warned and the launch
failed silently; check `launchd.err` and the dashboard log under
`~/Claude/mpc_sbn/logs/dashboard_*.log`.

An OK status with `elapsed_s` well outside that range (say >900 s) is a
soft warning — probably a cache-cold stage 1 or a replication-catchup
spike, worth investigating.
