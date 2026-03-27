# Hosting Architecture Notes

## Overview

Notes on hosting the Planetary Defense Dashboard (`app/discovery_stats.py`)
and supporting infrastructure, comparing campus Linux hosting (plan A) with
a supplemental home Mac Mini behind Cloudflare.

## Current Setup

- **Database host (sibyl):** RHEL 8.6, 251 GB RAM, HDD, PostgreSQL 15.2
  with logical replication from MPC
- **Key tables:** `obs_sbn` (526M+ rows, 239 GB), `mpc_orbits` (1.51M rows)
- **Database role:** `claude_ro` (read-only)
- **App:** Dash/Plotly at http://127.0.0.1:8050/, served over Cloudflare Tunnel
- **Cloudflare:** Free account, nameservers switched 2026-03-26

## Database Query Lifecycle

### Cached at `--refresh` time (daily cron, CSV with 24-hour TTL)

| Query | Tables | Rows | Time | Cache file |
|-------|--------|------|------|------------|
| `LOAD_SQL` | mpc_orbits, numbered_identifications, obs_sbn, obscodes | ~45K NEOs | ~30s | `.neo_cache_*.csv` |
| `APPARITION_SQL` | mpc_orbits, numbered_identifications, obs_sbn | ~362K station rows | 1–2 min | `.apparition_cache_*.csv` |
| `BOXSCORE_SQL` | mpc_orbits, numbered_identifications | ~1.5M objects | ~30s | `.boxscore_cache_*.csv` |
| NEA.txt H-mag resolution | numbered_identifications | ~35K | seconds | `.nea_h_cache.csv` |
| PHA.txt set | numbered_identifications | ~2.5K | seconds | `.pha_cache.csv` |
| SBDB Earth MOID | numbered_identifications | ~35K | seconds | `.sbdb_moid_cache.csv` |

After `--refresh`, the app serves entirely from in-memory DataFrames.
All 30+ Dash callbacks for Tabs 1–7 operate on cached data with no
database access.

### Live queries (on user interaction)

Only one path: `resolve_designation()` in `lib/identifications.py`,
called from the **MPEC Browser** (Tab 0) when a user clicks on an MPEC
entry.  Queries `current_identifications`, `numbered_identifications`,
and `mpc_orbits` for single-row indexed lookups (~milliseconds).
Results are cached at the module level so repeated lookups for the same
object do not re-query.

### Scripts (run manually, not part of the app)

- `scripts/compute_circumstances.py` — queries `obscodes` and discovery
  observations at startup
- `lib/ades_export.py` (when run as `__main__`) — direct psycopg2
  connection for ADES generation

## Platform Comparison

### Linux on Campus (Plan A)

**Advantages:**
- PostgreSQL's native platform; full access to huge pages, io_uring
  (PG 16+), kernel AIO, proper fsync
- Can spec 128–256 GB RAM to keep hot indexes and working sets cached
- ECC RAM available on server/workstation boards
- systemd service management, mature monitoring ecosystem
- Logical replication is rock-solid and runs as MPC intends
- Direct low-latency access to the database

**Considerations:**
- The single biggest improvement is moving from HDD to NVMe — this alone
  would likely cut APPARITION_SQL from 1–2 min to under 10 seconds
- A used/refurbished workstation (Xeon/EPYC, 256 GB ECC) is
  cost-effective and would handle this workload for years

### Mac Mini at Home (Supplemental)

**Advantages:**
- Apple Silicon has excellent single-thread performance (PostgreSQL
  benefits: single query = single core)
- NVMe SSD standard — transformative vs current HDD host
- Silent, tiny footprint, low power (~20–60W under load)
- Already serving dashboard over Cloudflare Tunnel
- Can host other services: historical web pages migrated from
  third-party commercial hosting

**Limitations:**
- PostgreSQL on macOS is second-class: no huge pages, no io_uring, fsync
  semantics differ — ~10–20% I/O overhead vs Linux on equivalent hardware
- M4 Pro maxes at 64 GB RAM; M4 Max at 128 GB — well under the current
  host's 251 GB, though most of the working set would still fit
- No ECC RAM
- macOS not designed as a headless server OS; power management and sleep
  can interfere with long-running services
- ARM PostgreSQL extensions may lag

### VMs (Cloud or Institutional)

- Adds latency and shared-tenancy noise
- Easier to provision and maintain remotely
- Not recommended if direct NVMe access and predictable memory are
  important for the 239 GB table

## Split Hosting Model

The app's cache-based architecture makes split hosting straightforward:

**Option A — Refresh over tunnel:**
Run the daily `--refresh` cron on the Mac Mini through an SSH tunnel to
campus PostgreSQL.  The three big queries take a few minutes total.
Then the app serves from local CSV cache with zero ongoing DB dependency.

**Option B — Cache transfer:**
Run `--refresh` on campus, rsync the CSV caches to the Mac Mini.
The app never needs DB access at all.

**The MPEC Browser wrinkle:** `resolve_designation()` needs real-time DB
access for single-row lookups.  Options:
1. Accept tunneled latency (indexed lookups, even 50ms RTT is fine)
2. Pre-cache identification tables locally (they're small)
3. Local SQLite mirror of identification tables only

## Security: Home-to-Campus Database Access

### SSH Tunnel (simplest, strongest)

```
ssh -L 5432:sibyl:5432 campus-gateway
```

- PostgreSQL sees a local connection; SSH key is the only credential
  exposed to the network
- Persistent with `autossh` or a launchd plist
- Campus firewall only needs to allow SSH to the gateway
- PostgreSQL is never directly exposed

### WireGuard VPN (better for always-on)

- Point-to-point encrypted tunnel, ~3ms overhead on top of base RTT
- Handles reconnection gracefully
- `pg_hba.conf` restricts to WireGuard subnet
- Lower overhead than SSH for sustained connections

### Cloudflare Tunnel (already in place)

- Can tunnel TCP (not just HTTP), so PostgreSQL could be exposed
  through it
- Adds Cloudflare as middleman for database traffic — trust/compliance
  question for university data
- Better suited for the HTTP dashboard than raw database access

### PostgreSQL-Level Hardening (either paradigm)

- `claude_ro` is already read-only
- `pg_hba.conf`: restrict to specific source IPs or subnets
- Require SSL: `sslmode=verify-full` in connection strings
- `log_connections = on` for audit trail
- Consider a dedicated role for the live lookup path with access limited
  to `current_identifications`, `numbered_identifications`, and
  `mpc_orbits` only (no `obs_sbn` access)

### Recommendation

SSH tunnel for the daily `--refresh` job and occasional
`resolve_designation()` lookups.  Zero-config on the PostgreSQL side,
works through any campus firewall allowing SSH, and `claude_ro` already
limits blast radius.  WireGuard is worth adding if more services need
campus access.
