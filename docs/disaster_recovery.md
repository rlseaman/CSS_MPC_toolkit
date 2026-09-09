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
- **Nightly backup (added 2026-09-09):** launchd agent
  `org.seaman.pg-backup` at 07:30 MST runs `scripts/pg_backup_gizmo.sh`,
  a `pg_dump -Fc` (zstd) of every `css_*` schema plus the cluster
  globals, written to the **boot volume** under
  `~/Claude/mpc_sbn/backups/dumps/` — deliberately not the external
  NVMe that holds PGDATA. ~265 MB and ~22 s per run. Retention: every
  dump from the last 14 days plus the first dump of each month for a
  year (~7 GB steady state). Each run verifies the archive with
  `pg_restore -l`, records a sha256, and updates `latest.dump`. The
  replicated MPC tables are not dumped — path A/B re-seeds them from
  SBN. Restore procedure in §F. No off-host copy yet; the plan is an
  external drive (Time Machine for the boot volume, which will sweep
  the dumps along with it).
- **Heartbeats (added 2026-09-09):** three dead-man's-switch checks on
  healthchecks.io — `gizmo-refresh`, `pg-backup`, `site-up` — each
  with period 1 day, grace 2 h. The refresh and backup scripts ping
  `/start` on entry, the bare URL on success, and `/fail` (with a
  reason in the body) on any failure exit, via `scripts/heartbeat.sh`.
  Refresh stage 7 fetches `https://hotwireduniverse.org/` from Gizmo —
  which goes out to the Cloudflare edge and back through the tunnel —
  and pings `site-up` only on a 200. A missed ping or a `/fail` emails
  the maintainer. Ping URLs live in `~/Claude/mpc_sbn/heartbeat.env`
  (mode 600, not in git); if that file is missing the scripts log a
  line and carry on. Gizmo dark → all three checks go "down" within
  ~2 h of their windows, which is the alert the July outage lacked.

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

### D) PostgreSQL down from external NVMe disconnect (Thunderbolt)

**Symptom:** `psql` fails "Connection refused" on the `/tmp` socket; no
`postgres` processes; PG log shows `could not write to log file:
Input/output error`. The DB lives on an external Thunderbolt NVMe (OWC
Express 1M2) at `/Volumes/data1`; the drive momentarily dropped — kernel
logs a Thunderbolt HPD unplug (`plug = 0`) → APFS `cluster_push() failed
with 6` (errno 6 = ENXIO) → PG writes fail and the postmaster dies.

**First seen 2026-06-27:** plugging *and* unplugging a USB-C device in
the **rear port adjacent** to the NVMe's Thunderbolt port dropped the
drive (caught live in the kernel log). A properly seated cable should not
do this — treat a recurrence as a loose/marginal Thunderbolt cable or a
bumped enclosure, and keep other devices off the adjacent ports.

**Recovery (≈1 min; ran cleanly 2026-06-27):**
1. Confirm the drive is back and writable *before* starting PG:
   ```bash
   diskutil info /Volumes/data1 | grep -E 'SMART|Mounted|Read-Only'
   touch /Volumes/data1/.wtest && rm /Volumes/data1/.wtest   # must succeed
   ```
   If unmounted: reseat the Thunderbolt cable at both ends (re-enumerates
   in seconds).
2. Start PostgreSQL — crash recovery replays the little WAL since the last
   checkpoint (~2 s). Postgres is managed by the **`local.postgresql18`**
   LaunchAgent (custom `pg18-start.sh` wrapper + the `PathState` drive-mount
   guard) — **not** `brew services`; see §E on why the stock
   `homebrew.mxcl.postgresql@18` agent is disabled:
   ```bash
   launchctl kickstart -k gui/$(id -u)/local.postgresql18
   pg_isready -h /tmp        # wait for "accepting connections"
   ```
3. Verify replication resumed + data intact:
   ```bash
   psql -h /tmp -d mpc_sbn -c "SELECT subname, last_msg_receipt_time FROM pg_stat_subscription;"
   psql -h /tmp -d mpc_sbn -c "SELECT matviewname, ispopulated FROM pg_matviews;"
   ```
4. Restart the dashboards so they drop stale DB connections:
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.rlseaman.dashboard
   launchctl kickstart -k gui/$(id -u)/com.rlseaman.dashboard-rnd
   ```

**Prevention / durable fix:** the off-host replica in
`docs/server_provisioning.md` — a production DB should not hang off a
bus-attached external drive this sensitive to a desk bump.

### E) Power outage — Gizmo dark, does not come back on its own

**Symptom:** hotwireduniverse.org down after a building power outage; on
return you find the mini powered off, or sitting at a login window with
nothing started. This is what happened **2026-07-10 → 2026-07-14**: a
power loss took Gizmo down and it stayed dark for four days (owner out of
town) because a cold boot required a manual FileVault unlock **and** an
interactive login before any launchd agent would run.

**Durable fix applied 2026-07-15 — the unattended-boot chain.** Each link
was configured so a cold boot recovers with no keyboard/monitor/human:

| Link | Setting / mechanism |
|---|---|
| Power returns → machine boots | `pmset -g \| grep autorestart` → `autorestart 1` |
| No pre-boot password wall | **FileVault OFF** (`fdesetup status` → Off) |
| Session starts with no login | **Auto-login ON** for `robertseaman` (`sysadminctl -autologin status`; `/etc/kcpassword` present) |
| DB drive mounts | `/Volumes/data1` auto-mounts (no `/etc/fstab` override) |
| Postgres starts, waits for drive | `local.postgresql18` LaunchAgent with `KeepAlive → PathState → /Volumes/data1/postgresql@18/PG_VERSION` |
| Dashboards + tunnel + refresh | GUI (Aqua) LaunchAgents, `RunAtLoad`, reached via auto-login |

FileVault is safe to disable here: PGDATA is on the external `data1` NVMe
which was never FileVault-encrypted (FileVault only ever covered the
internal *Macintosh HD*), and it's a public-data replica. It also gives
**no** disk-speed change — the DB disk was already unencrypted and the
internal SSD is hardware-AES regardless.

**GOTCHA:** `sudo sysadminctl -autologin set -userName robertseaman
-password -` fails with `SACSetAutoLoginPassword error:22` when run over
**SSH**. It must be run from a **console/GUI session** — a Terminal under
**Screen Sharing** works. FileVault must already be off first.

**One-agent rule for Postgres (learned 2026-07-15).** Two LaunchAgents can
start Postgres: the intended `local.postgresql18` (with the drive-mount
guard) and the stock `homebrew.mxcl.postgresql@18`. If both are enabled they
**race on boot** for the data directory — the reboot test found homebrew had
won (pid 781) while `local.postgresql18` sat in a 10 s `FATAL: lock file
"postmaster.pid" already exists` loop, meaning the running Postgres had **no
drive-mount guard**. Fix applied: `homebrew.mxcl.postgresql@18` is booted out
and **disabled** (`launchctl disable gui/$(id -u)/homebrew.mxcl.postgresql@18`
— persists across reboots), leaving `local.postgresql18` as sole owner. If the
homebrew agent ever reappears in `launchctl list | grep postgres` alongside a
running `local.postgresql18`, disable it again.

**Verify the chain (any time, or after a real outage):**
```bash
ssh robertseaman@192.168.0.157
pmset -g | grep autorestart              # want: autorestart 1
fdesetup status                          # want: FileVault is Off.
sysadminctl -autologin status            # want: Automatic login user: robertseaman
who | grep console                       # a console session with no manual login = auto-login worked
```
Then the standard health checks (replication, `curl :8050`, public 200).

**What this does NOT cover** — verified by a `sudo reboot` on 2026-07-15
(full stack self-recovered), but a soft reboot never removes power, so
two things remain untested and unprotected:
1. **Hardware auto-power-on** (`autorestart`) only fires on a real power
   cut, not a soft reboot. The setting is correct but unproven on this host.
2. **Dirty-shutdown recovery** — an abrupt cut leaves Postgres to WAL-replay
   (crash-safe, ~2 s) and puts the abrupt-cut hit on the fragile NVMe (see D).

**The one thing that closes both:** a **UPS with USB signaling** — rides
through brief outages, and on a long one does a *clean* shutdown before the
battery dies so macOS auto-restarts on power return. Its "simulate power
failure" is also the only safe way to test the full power-loss path
(don't yank the plug — see D for why abrupt drops on this drive are risky).
Not yet purchased as of 2026-07-15.

### F) Local schemas lost or corrupted — restore from the nightly pg_dump

Applies when `css_neo_consensus`, `css_orbit_watch`, `css_ades_overlay`
or `css_utilities` are gone or damaged but the cluster itself is
running (e.g. after an NVMe drop that took the data directory, or a
re-seeded replica that only carries the MPC tables). These schemas are
the only data in the cluster that cannot be rebuilt from upstream.

**1. Pick a dump.** Newest is `latest.dump`; the directory also holds
14 daily and up to 12 monthly-first archives:

```bash
ls -la ~/Claude/mpc_sbn/backups/dumps/
cat ~/Claude/mpc_sbn/backups/last_backup_status.json     # last run OK?
shasum -a 256 -c ~/Claude/mpc_sbn/backups/dumps/<name>.dump.sha256
```

**2. Roles first** if the cluster was rebuilt from scratch (skip if
`claude_ro` and `robertseaman` already exist):

```bash
psql -h /tmp -d postgres -f ~/Claude/mpc_sbn/backups/dumps/globals_<stamp>.sql
```

**3. Restore into `mpc_sbn`.** The archive is custom format, so you can
restore everything or one schema. Drop the damaged schema first if it
half-exists, otherwise `pg_restore` errors on every existing object:

```bash
psql -h /tmp -d mpc_sbn -c 'DROP SCHEMA IF EXISTS css_orbit_watch CASCADE'
pg_restore -h /tmp -d mpc_sbn -j 4 -n css_orbit_watch \
    ~/Claude/mpc_sbn/backups/dumps/latest.dump
# all four schemas: omit -n
```

The MPC tables in `public` must already be present:
`css_ades_overlay.v_effective` and the `css_neo_consensus.obs_summary`
matview reference `public.obs_sbn`, so restoring into a database
without them reports two errors and skips those objects. That is the
expected result of the scratch-database restore test, not a corrupt
archive. In a real recovery restore the schemas after replication has
re-seeded `public`, or re-run the dump's `CREATE VIEW` / `REFRESH
MATERIALIZED VIEW` afterwards.

**4. Verify** row counts against the status JSON's era (they only need
to be plausible — the dump is from 07:30 that morning):

```sql
SELECT count(*) FROM css_orbit_watch.orbit_snapshot;
SELECT css_utilities.classify_orbit_label(0.9, 0.2, 5.0);   -- 'Apollo'
```

Then re-enable the daily jobs that write to these schemas
(`org.seaman.gizmo-refresh` stage 2 for consensus,
`org.seaman.orbit-watch` for snapshots) — they are idempotent per day
but the gap between the dump and the failure is lost.

**Restore test record.** 2026-09-09: the first dump was restored into
a scratch database on Gizmo; all six tables matched live counts
exactly (`source_membership` 254,213 · `orbit_snapshot` 3,686,601 ·
`ades_overlay.obs` 1,622,353 …), all 11 functions and 17 of 18 indexes
came back, the two `public`-dependent objects errored as described.

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

After the 07:30 MST backup:

```bash
ssh robertseaman@192.168.0.157 cat ~/Claude/mpc_sbn/backups/last_backup_status.json
```

Expected: `"status": "OK"`, `bytes` in the few-hundred-MB range and
growing slowly (orbit snapshots add a few MB a month; the ADES-overlay
backlog load will step it up), `n_tables` equal to the live count of
`css_*` tables, `retained_dumps` ≤ 27, `free_gb` comfortably above the
5 GB pre-flight floor. A FAIL status names the reason; the per-run log
is under `~/Claude/mpc_sbn/backups/logs/`.

Or, without SSH: the healthchecks.io dashboard shows all three checks
green with the last ping time and the body of the last ping (the
refresh sends its stage timings; the backup sends dump name and size).
Since 2026-09-09 the refresh status JSON also carries `site_check`
(`ok` or `http_<code>`) and `stage7_s` from the public-URL probe.

Heartbeat failure modes: a check that is *down* with no `/fail` event
means the job never ran or never finished (host dark, launchd agent
unloaded, script hung — see §E). A `/fail` event names the stage.
`site-up` down while `gizmo-refresh` is fine means Dash restarted but
the public path (tunnel / DNS / Cloudflare) did not come back — check
`com.cloudflare.tunnel` and `~/.cloudflared/tunnel.log`.
