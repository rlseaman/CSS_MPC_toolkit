# Server Provisioning — Externally-Accessible Web Host + Replica

Provisioning brief for standing up the **Planetary Defense Dashboard**
(`app/discovery_stats.py`) and a supporting **`mpc_sbn` PostgreSQL replica**
on a new, externally-accessible server. Target OS: **Rocky Linux** (9 or 10).

This document assumes the new deployment differs from the current
Gizmo/Cloudflare production host in two deliberate ways:

1. **The replica lives on (or beside) the public web server**, outside the
   campus network firewall. A highly-performant, externally-reachable
   replica is a project goal in its own right — not just a backing store
   for the dashboard.
2. **No Cloudflare.** Public exposure is via a conventional reverse proxy +
   TLS + host firewall, which the project must now provide for itself
   (Cloudflare previously supplied TLS termination, the tunnel, bot
   mitigation, and edge rate-limiting).

All figures below are grounded in the live Gizmo deployment as of
2026-06. Numbers grow over time — treat them as floors.

---

## 0. Architecture at a glance

```
   MPC publisher (campus)                  Internet
          │                                    │
          │ logical replication                │ HTTPS :443
          │ (outbound from replica,            │
          │  or MPC-side IP allow-list)        ▼
          ▼                            ┌──────────────────┐
   ┌─────────────┐   localhost :5432   │  reverse proxy   │  nginx / Apache
   │  PostgreSQL │◀────────────────────│  (TLS, rate-     │  + certbot
   │  mpc_sbn    │                     │   limit, auth)   │
   │  replica    │                     └────────┬─────────┘
   │  (PG 18)    │                              │ localhost :8050 / :8051
   └─────────────┘                     ┌────────▼─────────┐
          ▲   localhost :5432          │  waitress + Dash │  systemd services
          └────────────────────────────│  (prod + dev)    │
                                        └──────────────────┘
                            ▲ daily systemd timer: refresh matviews + caches
```

The DB and the app **can** share one box, but see §2.2 on sizing — the DB
is the heavy component. The app tier is light (~1 GB RAM, a few GB disk).

---

## 1. PostgreSQL replica — the heavy requirement

> The dashboard needs more than "a copy of the MPC DB." It reads
> **value-added objects** layered on top of the raw replica:
> materialized views, the `css_neo_consensus` schema, and the
> `css_utilities` function suite (§1.5). A bare replica will not serve the
> app until these are installed and kept fresh.

### 1.1 Version & replication topology

| Item | Requirement |
|---|---|
| **PostgreSQL** | **18.x** (current replica version on Gizmo). Logical replication is cross-version tolerant; the MPC publisher runs 15.x. Do **not** go below the publisher major version. |
| **Replication type** | **Logical** replication (subscription-based) from the MPC publisher — *not* physical streaming. The app's "replica" is a subscriber with its own indexes, matviews, and roles, which physical replication could not carry. |
| **Subscriptions** | Two, mirroring the current deployment: one for the large `obs_sbn` table, one for the other tables (e.g. `sbn_css_gizmo_obs_table_sub`, `sbn_css_gizmo_other_tables_sub`). Both must show running workers and near-zero lag (`pg_stat_subscription`). |

**Connectivity / firewall (critical for an off-campus replica):**
Logical replication requires the subscriber to reach the MPC publisher's
Postgres port. With the new server **outside** the campus firewall, this
must be arranged with MPC:
- The publisher (or a campus-side replication endpoint) must be reachable
  from the new server's public IP, **or**
- MPC adds the new server's IP to its `pg_hba.conf` / replication
  allow-list and any campus firewall ACL.

Confirm this path **before** provisioning — it is the single most likely
blocker and is outside our control. Until replication is flowing, the
replica is empty and nothing downstream works.

### 1.2 Storage

| Resource | Need |
|---|---|
| **Database size** | **~300 GB today, growing.** `obs_sbn` alone is ~240 GB / 526M+ rows; full DB measured at **296 GB** on 2026-06. Provision **≥ 500 GB** to leave headroom for growth, WAL, bloat, and index rebuilds. |
| **Disk type** | **NVMe SSD, mandatory** for "highly performant." The original Sibyl replica is on HDD and several query shapes are I/O-bound there; Gizmo's NVMe is what makes sub-second loads possible. Do not put this DB on spinning disk or network storage. |
| **WAL / temp** | Logical-replication apply plus daily matview refreshes generate WAL and large sorts. Keep `pg_wal` and `temp` on the same fast NVMe; size `max_wal_size` generously (see §1.4). |

### 1.3 Memory — sizing for performance

RAM is the lever that decides whether this replica is "highly performant"
or not. The governing rule from operational experience:

> **Speed tracks working-set fit.** A box wins when the hot working set
> fits in RAM (shared_buffers + OS page cache). The 251 GB Sibyl host beats
> the 16 GB Gizmo host on the RAM-hungry `APPARITION_SQL` shape precisely
> because Gizmo can't cache the LATERAL probe set. Do **not** under-provision
> RAM and expect NVMe to compensate.

| Tier | RAM | Suitability |
|---|---|---|
| Minimum | **32 GB** | App serves from caches fine; heavy refresh queries (`APPARITION_SQL`, `obs_summary_all`) will spill to disk and run slow. |
| Recommended | **128 GB** | Comfortable working-set fit for the nightly refresh and any ad-hoc analytics against `obs_sbn`. |
| Match-Sibyl | **256 GB** | Full headroom for the worst query shapes and future growth. Choose this if the replica is also meant to serve interactive analytical queries, not just back the dashboard. |

### 1.4 Tuning (`postgresql.conf`)

Postgres ships with `shared_buffers = 128 MB` regardless of DB size — for a
300 GB database that means nearly every query hits disk. **This is the
single most impactful setting.** Reference: `scripts/db_tune_recommendations.sql`
(written for the 251 GB host; scale to the chosen RAM).

For a **128 GB** box:

```conf
shared_buffers       = 32GB      # ~25% of RAM
effective_cache_size = 96GB      # ~75% of RAM (planner hint, not an allocation)
work_mem             = 128MB     # per sort/hash; watch max_connections × this
maintenance_work_mem = 4GB       # speeds matview refresh, VACUUM, index builds
wal_buffers          = 64MB
max_wal_size         = 16GB      # absorb replication apply + refresh bursts
huge_pages           = on        # see scripts/enable_huge_pages.md (OS-side sysctl first)
max_connections      = 100
```

Scale `shared_buffers`/`effective_cache_size`/`maintenance_work_mem`
linearly for 32 GB or 256 GB. Apply the per-table autovacuum settings and
one-time `VACUUM` from `db_tune_recommendations.sql` as well — the raw
replica arrives untuned. **Restart** Postgres after `postgresql.conf`
changes. For huge pages, configure the OS first
(`vm.nr_hugepages`, `vm.hugetlb_shm_group`) — see
`scripts/enable_huge_pages.md`.

### 1.5 Required value-added DB artifacts

These are built by this toolkit's SQL and must exist on the replica before
the app will serve. They are refreshed by the nightly timer (§6):

| Artifact | Kind | Purpose |
|---|---|---|
| `obs_sbn_neo` | matview | NEO-scoped slice of `obs_sbn`; backs LOAD_SQL / APPARITION_SQL. ~3.5 min refresh. |
| `obs_summary` | matview | per-NEO first/last obs, arc, nobs, disc_by, n_stns — NEO Consensus tab. ~5 min. |
| `obs_summary_all` | matview | full-catalog sibling — Observation history tab. ~2.5 min. |
| `css_neo_consensus` | schema | six-source NEO membership (MPC / mpc_orbits / CNEOS / NEOCC / NEOfixer / Lowell) + `v_membership_wide`. |
| `css_utilities` | functions + types | orbit classification, designation pack/unpack, ADES helpers (server-side mirror of `lib/`). Install via `sql/install_classify_orbit.sql` and `sql/css_utilities_functions.sql` / `css_utilities_extensions.sql`. |

**Indexes on `obs_sbn`:** the raw replicated table is not adequately
indexed for this workload. The current deployment carries **~13 tuned
indexes** on `obs_sbn` covering: `obsid, permid, provid, stn, trkid,
trksub, trkmpc, obstime, created_at, updated_at, submission_block_id`.
Replicate this index set (see the replica build notes) — without it the
NEVER-do-a-full-scan rule on a 526M-row table cannot be honored.

### 1.6 DB roles

| Role | Privilege | Used by |
|---|---|---|
| `claude_ro` | **read-only** (SELECT) | the dashboard serving path; credentials in `~/.pgpass` (mode 600). |
| refresh role | `REFRESH MATERIALIZED VIEW` (owner or granted) | the nightly timer (§6). Distinct from `claude_ro`. |
| replication role | `REPLICATION` / subscription owner | the logical-replication subscriptions. |

---

## 2. Where to put the DB relative to the app

### 2.1 Same box (acceptable)
Simplest, and the model used on Gizmo. Requires the box to satisfy **both**
the DB sizing (§1.2–1.3) **and** the app footprint (§4). The app reaches
the DB over the local Unix socket / `localhost:5432`.

### 2.2 Separate boxes (recommended if hosting "other apps" too)
The DB is the heavy, RAM-sensitive, 300-GB-and-growing component; the app
tier is light. Splitting them lets the web tier stay small and be reused
for the other apps without the DB dominating it. The app already supports a
remote DB via `$PGHOST` + `.pgpass`. If split, open 5432 **only** between
the two hosts (private subnet / firewall rule), never to the internet.

---

## 3. Python runtime & OS packages

| Item | Requirement |
|---|---|
| **Python** | **3.12** (proven production version). Rocky 9 ships 3.9 — too old; install `python3.12` from AppStream. Rocky 10 carries 3.12 natively. |
| **Virtualenv** | One dedicated `venv/` per app — no shared environments. |

**`dnf install` at build/deploy time:**
- `python3.12`, `python3.12-pip`, `python3.12-devel`
- `git` — one pip dependency installs from GitHub
- `gcc`, `make` — build backstop for source installs
- PostgreSQL **client** matching the server major version (`psql` — for the
  refresh script). The `postgresql18` client RPM from the PGDG repo.
- `nginx` (or `httpd`) — reverse proxy (§5)
- `certbot` + `python3-certbot-nginx` — TLS (§5), if using Let's Encrypt

---

## 4. Python dependencies & app footprint

### 4.1 `requirements.txt`

```
psycopg2-binary>=2.9     # DB driver (binary wheel — no libpq-dev needed)
pandas>=2.1, numpy>=1.26 # dataframes
pyarrow>=15.0            # Parquet cache I/O
dash>=2.14, plotly>=5.18 # web UI + charts
waitress>=3.0            # production WSGI server
kaleido>=0.2             # static Plotly image export (bundles headless Chromium)
lxml>=6.1.0              # ADES XML (pinned >=6.1 for CVE-2026-41066 / XXE)
jupyterlab>=4.0          # notebooks (dev only — not needed to serve)
mpc-designation          # pip-installs from github.com/rlseaman/MPC_designations
```

Notes:
- **`kaleido`** on Linux needs a few system libs for its bundled Chromium
  (`libX11`, `libexpat`, `nss`, `fontconfig`-class). Install if static
  PNG/SVG export errors; not needed for interactive use.
- **`jupyterlab`** can be omitted from a pure-serving install.
- **`mpc-designation`** needs `git` + network at install time.

### 4.2 App memory & cache storage

| Resource | Need |
|---|---|
| **App RAM** | ~**0.7 GB resident per Dash instance** (measured 711 MB). Budget ~1 GB each. Currently three instances run on the tunnel (prod :8050, dev :8051, a third app :8060) — size for the set you intend to host. |
| **Cache storage** | ~**300 MB, slowly growing**: ~180 MB Parquet caches + ~103 MB MPEC text cache (`app/.mpec_cache/`, grows monotonically) + ~5 MB Horizons ephemeris cache. Budget a few GB. |
| **Code + venv** | A few hundred MB (pandas/plotly/kaleido). |

The app is **stateless apart from these caches**, which it rebuilds from the
DB nightly. After the daily refresh it serves almost entirely from
in-memory DataFrames; the only live per-request DB path is single-row
indexed designation lookups from the MPEC Browser.

---

## 5. Public exposure — reverse proxy + TLS (replacing Cloudflare)

Cloudflare previously supplied TLS, the inbound tunnel, bot mitigation, and
edge rate-limiting. Without it, the host must provide all of this itself.

### 5.1 Reverse proxy
Run **nginx** (or Apache) terminating TLS on **:443** and proxying to the
waitress instances on localhost. waitress binds `127.0.0.1` only — it is
never exposed directly.

```nginx
# /etc/nginx/conf.d/dashboard.conf  (sketch)
server {
    listen 443 ssl http2;
    server_name hotwireduniverse.org www.hotwireduniverse.org;

    ssl_certificate     /etc/letsencrypt/live/hotwireduniverse.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hotwireduniverse.org/privkey.pem;

    # Edge rate-limiting Cloudflare used to do (see http{} limit_req_zone)
    limit_req zone=dash burst=20 nodelay;

    location / {
        proxy_pass http://127.0.0.1:8050;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;   # cold Horizons fetches can be slow
    }
}
# Redirect :80 -> :443, plus an ACME location for certbot.
```

```nginx
# in http{}:
limit_req_zone $binary_remote_addr zone=dash:10m rate=10r/s;
```

### 5.2 TLS certificates
- **Let's Encrypt via certbot** (`certbot --nginx`) with auto-renew
  (`systemd` timer `certbot-renew`), **or**
- an institutional / commercial certificate if campus policy requires it.

Renewal needs inbound :80 reachable (HTTP-01) or DNS-01 access.

### 5.3 Host firewall (`firewalld`)
- **Open:** 443/tcp (HTTPS), 80/tcp (redirect + ACME).
- **Do not open:** 8050/8051/8060 (waitress — localhost only), 5432
  (Postgres — localhost, or private-subnet-only if the DB is on a
  separate host per §2.2).
- SSH: restrict source where possible.

### 5.4 Security posture — what we lose with Cloudflare, and the replacements

The current prod surface is **intentionally unauthenticated** and relied on
Cloudflare's Bot Fight Mode + edge rate-limiting for abuse mitigation
(see `docs/dashboard_security.md`). Off Cloudflare, compensate:

| Lost Cloudflare feature | Replacement on the new host |
|---|---|
| TLS termination | nginx + certbot (§5.2) |
| Edge rate-limiting | nginx `limit_req` (§5.1) |
| Bot Fight Mode / WAF | `fail2ban` on nginx logs; optional ModSecurity WAF; consider a CAPTCHA only if abused |
| DDoS absorption | none at host level — accept the risk, or front with an institutional load balancer / CDN |
| **Access email allow-list (gated the dev surface)** | nginx HTTP Basic auth, or `oauth2-proxy` in front of the dev vhost. **The dev surface must not be left open** — it previously depended entirely on Cloudflare Access. |

The app's **outbound politeness controls remain in-process** (per-host rate
limits, failure cooldowns, `APIREQ` audit log) and are unaffected by the
change of edge.

### 5.5 Outbound egress allow-list
The app + refresh pipeline reach these hosts over HTTPS — allow egress:

| Host | Purpose |
|---|---|
| `ssd.jpl.nasa.gov`, `ssd-api.jpl.nasa.gov`, `cneos.jpl.nasa.gov` | JPL Horizons, SBDB, Sentry |
| `minorplanetcenter.net`, `www.minorplanetcenter.net`, `data.minorplanetcenter.net` | MPC: MPECs, NEA.txt, MPCORB |
| `neo.ssa.esa.int` | ESA NEOCC risk list |
| `neofixer.arizona.edu`, `neofixerapi.arizona.edu` | CSS NEOfixer |
| `ftp.lowell.edu` | Lowell `astorb` |
| `github.com` | pip install of `mpc-designation` (install time only) |

Plus the Postgres replication path to MPC (§1.1).

---

## 6. Process supervision & nightly refresh (launchd → systemd)

Gizmo uses macOS **launchd**; on Rocky these become **systemd** units.
A `systemd` service with `WantedBy=multi-user.target` also fixes the
"didn't come back after a power cut" failure mode — it restarts cleanly on
reboot with no manual intervention.

**Services (one per process):**
- `dashboard.service` — prod: `venv/bin/python app/discovery_stats.py --waitress --rnd` (:8050)
- `dashboard-dev.service` — dev: `… --rnd --dev-tabs --port 8051`
- `nginx.service`, plus `certbot-renew.timer`
- (no `cloudflared` service — removed for this deployment)

Use `Restart=on-failure`, a dedicated service account, `WorkingDirectory`
at the checkout, and `EnvironmentFile` for `PGHOST` etc.

**Nightly refresh — `systemd` timer** (replaces the launchd
`org.seaman.gizmo-refresh` agent; logic in
`scripts/refresh_matview_gizmo.sh`). Fires ~06:00 local, ~14–19 min,
stages:
1. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo` (~3.5 min)
2. NEO consensus six-source ingest (best-effort, ~15–25 s)
3. `REFRESH … obs_summary` (~5 min) + `3b.` `obs_summary_all` (~2.5 min)
4. `python app/discovery_stats.py --refresh-only` — rebuild Parquet caches (~15 min)
   + `4a.` sweep orphan parquet/.meta files from prior SQL-hash bumps
5. Restart the Dash service(s) to pick up fresh caches
6. `scripts/apireq_summary.sh` — tally yesterday's outbound HTTP volume (best-effort)

Needs `psql` and the write-capable refresh role. Ordering matters: stages
2–3 land before stage 4 so the cache build captures today's source
memberships.

---

## 7. Secrets / config to carry over (never in git)

- `~/.pgpass` (mode 600) — DB credentials for `claude_ro` and the refresh role
- Logical-replication connection string / credentials for the subscriptions
- TLS private key + cert (or certbot's `/etc/letsencrypt/`)
- dev-surface auth secret (Basic-auth file or `oauth2-proxy` client config)
- `EnvironmentFile` with `PGHOST`, ports, flags

---

## 8. Provisioning checklist

- [ ] **Confirm MPC logical-replication reachability** from the new public
      IP (firewall / `pg_hba` allow-list) — do this first; it's the
      likeliest blocker and is MPC-controlled.
- [ ] NVMe storage ≥ 500 GB; RAM per §1.3 (128 GB recommended).
- [ ] Install PostgreSQL 18; create replica DB + two logical subscriptions; verify lag → 0.
- [ ] Apply `postgresql.conf` tuning (§1.4) + autovacuum settings; restart; one-time VACUUM.
- [ ] Build the ~13 `obs_sbn` indexes.
- [ ] Install value-added artifacts: matviews, `css_neo_consensus`, `css_utilities`.
- [ ] Create `claude_ro` + refresh roles; populate `~/.pgpass`.
- [ ] Install Python 3.12, git, build tools, nginx, certbot, psql client.
- [ ] Create venv, `pip install -r requirements.txt`.
- [ ] `python app/discovery_stats.py --refresh` once to build caches; verify it serves on localhost:8050.
- [ ] nginx reverse proxy + TLS + `limit_req`; firewalld opens 80/443 only.
- [ ] Authenticate the dev vhost (Basic auth / oauth2-proxy) — never leave it open.
- [ ] `systemd` services for prod/dev Dash + the refresh timer; enable on boot.
- [ ] fail2ban on nginx; egress allow-list per §5.5.
- [ ] Verify public 200 over HTTPS; verify nightly timer runs end-to-end.

---

*See also: `docs/hosting_architecture_notes.md`, `docs/dashboard_security.md`,
`docs/disaster_recovery.md`, `docs/deployment.md`,
`scripts/db_tune_recommendations.sql`, `scripts/enable_huge_pages.md`,
`scripts/refresh_matview_gizmo.sh`.*
