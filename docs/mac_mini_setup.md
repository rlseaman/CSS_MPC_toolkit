# Mac Mini Setup Guide

Setup notes for the M4 Mac Mini as a dashboard host, discussed 2026-03-27.

## Current Status

### Completed
- Homebrew installed
- Python 3.12 installed (`brew install python@3.12`)
- PostgreSQL client libraries installed (`brew install libpq`)
- Git installed
- Repo cloned, venv created, `pip install -r requirements.txt` done
- All core imports verified (dash, plotly, pandas, numpy, psycopg2, lxml)
- Project library imports verified (orbit_classes, mpc_convert, orbits)
- 102 unit tests passing
- App syntax compiles cleanly

### TODO: Network & Access
- [ ] Enable Remote Login (SSH) in System Settings > General > Sharing
- [ ] Assign static IP on local network (either in Mac Mini network
      settings or via router DHCP reservation — need router admin access)
- [ ] Add SSH config entry on laptop (`Host mini` with HostName/User)
- [ ] Set up SSH key-based auth between laptop and Mini

### TODO: Database (Local Partial Replica)
- [ ] Install PostgreSQL on the Mini (`brew install postgresql@15`)
- [ ] Create local `mpc_sbn` database with read-only role
- [ ] Set up logical replication for 3 small tables only:
  - `current_identifications` (~2M rows)
  - `numbered_identifications` (~876K rows)
  - `mpc_orbits` (~1.5M rows)
- [ ] Configure `~/.pgpass` for local PostgreSQL
- [ ] Verify `resolve_designation()` works against local DB
- [ ] **Do NOT replicate `obs_sbn`** (526M rows, 239 GB) — not needed
      on the Mini

### TODO: Daily Cache Transfer
- [ ] Set up SSH tunnel or key-based access from Mini to campus machine
      (sibyl) — no VPN
- [ ] Daily cron on campus machine runs:
      `python app/discovery_stats.py --refresh`
      producing CSV caches (~30s + 3-8 min for the big queries)
- [ ] Daily rsync/scp from campus to Mini pulls the cache files:
  - `.neo_cache_*.csv` (LOAD_SQL output, ~45K NEOs)
  - `.apparition_cache_*.csv` (APPARITION_SQL output, ~362K rows)
  - `.boxscore_cache_*.csv` (BOXSCORE_SQL output, ~1.5M objects)
  - `.nea_h_cache.csv` (NEA.txt H-magnitude overrides)
  - `.pha_cache.csv` (PHA list)
  - `.sbdb_moid_cache.csv` (JPL SBDB Earth MOID data)
- [ ] App on Mini starts with `--no-refresh` (or just without
      `--refresh`) and loads from pre-existing CSVs instantly

### TODO: Cloudflare Tunnel
- [ ] Transfer Cloudflare tunnel config from laptop to Mini
      (`~/.cloudflared/` directory and credentials)
- [ ] Install cloudflared on Mini (`brew install cloudflared`)
- [ ] Update tunnel config to point to localhost:8050
- [ ] Set up as launchd service for auto-start

### TODO: Process Management
- [ ] launchd plist for the Dash app (auto-start on boot)
- [ ] launchd plist for cloudflared tunnel
- [ ] Disable sleep (System Settings > Energy or `sudo pmset -a sleep 0
      disablesleep 1`)
- [ ] Consider cron or launchd job to pull updated CSVs daily

## Architecture Summary

```
┌─────────────────────────────────┐
│  Campus Machine (sibyl)         │
│  PostgreSQL 15.2, full replica  │
│  - obs_sbn (526M rows)          │
│  - mpc_orbits, identifications  │
│  Daily: python --refresh        │
│         produces CSV caches     │
└──────────┬──────────────────────┘
           │ rsync/scp (SSH tunnel, daily cron)
           ▼
┌─────────────────────────────────┐
│  Mac Mini (M4, home network)    │
│  Local PostgreSQL (small):      │
│  - current_identifications (2M) │
│  - numbered_identifications     │
│  - mpc_orbits (1.5M)            │
│                                 │
│  CSV caches from campus:        │
│  - .neo_cache_*.csv             │
│  - .apparition_cache_*.csv      │
│  - .boxscore_cache_*.csv        │
│  - .nea_h_cache.csv + others    │
│                                 │
│  Dash app (localhost:8050)      │
│  - Tabs 1-7: cached DataFrames  │
│  - MPEC Browser: live lookups   │
│    from local partial DB        │
│                                 │
│  Cloudflare Tunnel → public URL │
└─────────────────────────────────┘
```

## Key Design Decisions

1. **obs_sbn stays on campus only.** At 239 GB it's impractical to
   replicate to the Mini and unnecessary — all queries touching it are
   pre-cached to CSV daily.

2. **Three small tables replicated locally** to support real-time
   `resolve_designation()` lookups from the MPEC Browser tab.  Total
   size ~1-2 GB.  Logical replication keeps them current without
   manual intervention.

3. **CSV cache transfer replaces direct DB queries** for all dashboard
   tabs (1-7).  The app's existing cache architecture already supports
   this — it checks for valid CSV files before attempting any DB query.

4. **No campus VPN required.** SSH tunnel provides encrypted access for
   both the rsync transfers and (optionally) the logical replication
   subscription.  Only SSH needs to reach the campus gateway.

## Notes

- Router admin access needed to assign a static local IP (DHCP
  reservation by MAC address is preferred over static IP config on
  the Mini itself)
- The Cloudflare tunnel was previously set up on the laptop — config
  and credentials need to be migrated, not recreated
- macOS power management must be disabled for reliable server operation
  (`pmset` settings)
- Consider whether logical replication for the 3 small tables is worth
  the complexity vs. a simpler daily pg_dump/restore — the tables
  change infrequently (mpc_orbits updates daily, identifications less
  often)
