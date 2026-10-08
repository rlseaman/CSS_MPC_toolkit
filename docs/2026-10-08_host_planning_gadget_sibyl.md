# Host Planning — Gadget, Sibyl, Gizmo, and a Linux DB Server

*2026-10-08. Planning note, not a decision record.*

Two goals drive this:

1. **A public web server** for the Planetary Defense Dashboard and
   related services.
2. **A high-performance PostgreSQL host** for the MPC catalog
   (`mpc_sbn`) and likely other databases. The web server needs to
   reach it, and so does the internal CSS network.

The question is how the current hosts (Gizmo, Sibyl) compare, how a
proposed office Mac mini ("**gadget**") would fit, and what a Linux
host or VM would need to outperform all of them.

Companion document: `docs/server_provisioning.md` (2026-06-25), the
Rocky Linux build brief. Where the two disagree, see §6.

---

## 1. Measured baseline (2026-10-08)

| | **Sibyl** | **Gizmo** |
|---|---|---|
| Hardware | x86 server, RHEL 8.6, 251 GB RAM, **HDD** | Apple M4 (10 cores), **16 GB RAM**, external TB NVMe (OWC Express 1M2, 4 TB) |
| PostgreSQL | 15.15 | 18.3 (async I/O, `io_method=worker`) |
| `mpc_sbn` size | **453 GB** (`obs_sbn` 443 GB) | **306 GB** (`obs_sbn` 293 GB) |
| `shared_buffers` / `effective_cache_size` | 80 GB / 240 GB | 5 GB / 15 GB |
| `random_page_cost` / `effective_io_concurrency` | 4 / 1 | 1.1 / 200 |
| Data volume used | — | 322 GB of 3.6 TB (9%) |

Query timings (from `cache_format` / benchmark notes, 2026-04 → 05):

| Query | Shape | Sibyl | Gizmo |
|---|---|---|---|
| `APPARITION_SQL` | many lookups by index (LATERAL) | **~55 s** | ~4:40 |
| `BOXSCORE_SQL` | full `mpc_orbits` join | ~3 s | **~0.7 s** |
| `obs_summary_all` build | full scan + aggregate | did not finish in 10 min | **~2:30** |

**Pattern:** Sibyl wins whenever the data a query touches fits in its
RAM, and Gizmo wins whenever a query has to read from disk. Each
machine falls short on exactly what the other has: Sibyl has memory
but a slow disk, Gizmo has a fast disk but little memory.

### Things to note about Sibyl

- **`obs_sbn` is 50% larger on Sibyl than on Gizmo, with the same
  rows.** That's either table/index bloat or extra indexes. At 443 GB
  the table and its indexes no longer fit in 251 GB of RAM, which
  weakens Sibyl's main advantage. A `pg_repack` or index review on
  Sibyl is worthwhile whatever else is decided.
- **The software is getting old.** RHEL 8.6 is an old point release,
  and PostgreSQL 15 lacks the asynchronous I/O added in 18.

### Growth rate

Rows added to `obs_sbn` per year (by `created_at`):

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (to 10-08) |
|---|---|---|---|---|---|
| 40 M | 62 M | 34 M | 45 M | 46 M | 36 M (~47 M/yr pace) |

At about 530 bytes per row including indexes (Gizmo), that's **about
25 GB/yr**. Rubin hasn't produced a visible jump yet. How much it will
add once it ramps up is the biggest unknown for sizing.

---

## 2. Gadget — proposed office Mac mini

Base quote: M6 Mac mini, 32 GB / 512 GB, 10 GbE, $1,500, plus NVMe.
Gadget would have **its own** logical-replication subscription from
MPC/SBN, not a replica of Gizmo.

### Recommended changes

| Item | Recommendation | Reason |
|---|---|---|
| **RAM** | **Go up: 64 GB (or 48 GB if offered); 32 GB minimum** | It's the one thing you can't change later. Gizmo is limited by its 16 GB (the `APPARITION_SQL` gap above). |
| **Internal SSD** | Keep 512 GB if PGDATA is external | The OS, venvs, caches and local dumps come to about 20 GB. |
| **NVMe** | **4 TB** | See sizing below. |
| **10 GbE** | Keep | Cheap option. Useful on campus (Sibyl, CSS network, fast restores). Doesn't help anything that crosses the 1 Gbps internet link, including replication from MPC and the public site. |

### NVMe sizing

| 5-year scenario | Database size |
|---|---|
| Current pace | about 450 GB |
| Rubin multiplies volume by 3–5× | roughly 0.8–1.2 TB |

On top of that you need space for:

- the ADES overlay backfill (about 100M rows, very roughly 50–60 GB),
- `pg_upgrade` or dump/restore and `REINDEX`/`VACUUM FULL`, which
  temporarily need 1.5–2× the database size,
- WAL and matviews.

2 TB works on paper but leaves little room. 8 TB is only worth it if
you expect Rubin to be much larger than these scenarios.

### Expected performance

- **Compared with Gizmo:** clearly better. With 4× the RAM, many more
  index lookups would stay in memory, and per-core speed is the same
  or better. I'd expect `APPARITION_SQL` to drop from about 4:40 to
  roughly 1–2 minutes. That's an estimate, not a measurement.
- **Compared with Sibyl:** better at full scans and anything that
  reads from disk. Probably still slower on large random-access
  workloads, since 64 GB can't cache what Sibyl's RAM can.

### Concerns

1. **The external drive is Gizmo's biggest operational weakness.** The
   Thunderbolt NVMe dropped out on 2026-06-27 and again on 2026-09-10,
   the second time for 8 hours unnoticed. For gadget, either:
   - pay for a larger internal SSD and put PGDATA on it (2 TB internal
     would last several years), or
   - use a quality enclosure on a dedicated rear port with the cable
     strain-relieved, and nothing that gets plugged and unplugged
     nearby.

   Internal is the stronger option if the price is acceptable.
2. **A second subscription from MPC/SBN.** Check with MPC first. The
   initial copy of `obs_sbn` will take days over 1 Gbps. Run
   PostgreSQL 18 to match Gizmo, so scripts and dumps move between the
   two unchanged.
3. **Campus IT policy.**
   - Gizmo runs with FileVault off, auto-login on and `pmset
     autorestart 1` so it restarts on its own after a power loss.
     University device management may require FileVault, and that
     conflicts with unattended reboot.
   - Check whether outbound connections to MPC's replication endpoint
     are allowed, and how vulnerability scanning would affect the
     machine.
   - The Cloudflare tunnel avoids inbound firewall changes, but get IT
     to sign off on it.
4. **Split state.** If both hosts run the nightly refresh, Orbit News
   and the consensus ingest, their `css_*` schemas will gradually
   diverge. Decide up front which host is authoritative for each
   schema. Running Orbit News on both does give a second copy of
   history that can't be recreated, which matters because that job
   has no heartbeat.
5. **Mac mini limits as a database server.** No ECC memory, no
   out-of-band management (IPMI or similar) for remote power cycling
   or console access, no RAID, a single power supply, and no io_uring
   or huge pages. These matter more for a database that serves as a
   record than for a dashboard host.

### Ways gizmo and gadget can help each other

- **Public site failover.** One Cloudflare named tunnel can have
  connectors on both hosts, and Cloudflare routes around a host that's
  down. If both serve the same dashboard version, an outage like
  2026-09-10 would be invisible to users. This is the most valuable
  reason to add the second machine.
- **Cross-backups.** Each host stores the other's nightly `css_*` dump
  (about 265 MB). That gives an off-site copy, which Time Machine on a
  USB drive next to Gizmo doesn't.
- **Spreading the work.** Gadget, with more RAM, could take the heavy
  work: `APPARITION_SQL`, lifetime follow-up, and the ADES overlay
  backfill. Gizmo would keep serving.
- **How they connect.** Gizmo is on a 192.168.0.x LAN and gadget would
  be on campus, so they'd talk over the internet. Use
  Tailscale/WireGuard or SSH through the Cloudflare tunnel, and don't
  open ports. For service requests in either direction, a small
  authenticated HTTP endpoint over that private link is simpler and
  safer than opening PostgreSQL to the other host.
- **Repo setup.** Bring gadget up from git, not by copying Gizmo.
  That's a good test of whether `main` can rebuild everything, and
  today it can't: the Orbit News SQL (`sql/orbit_watch/`) exists only
  on `station-report`. Promote it to `main` first.

---

## 3. A Linux host that beats all three across the board

The goal is **enough RAM to hold the hot part of the database, on fast
NVMe, so any query that misses memory is still fast.**

| Component | Recommendation | Why |
|---|---|---|
| **RAM** | **256 GB minimum, 512 GB preferred**, ECC | 256 GB holds the hot data (indexes, matviews, recent `obs_sbn`). 512 GB holds the whole current database plus several years of growth. |
| **Storage** | 2–4 enterprise NVMe drives (U.2/E.3, PCIe Gen4/5) in **RAID 1 or RAID 10**, about 8 TB usable | Fixes Sibyl's disk bottleneck and Gizmo's single fragile drive. Enterprise drives also protect writes during power loss. |
| **CPU** | Current AMD EPYC or Xeon, **16–32 cores**, favoring clock speed over core count | Each PostgreSQL query mostly runs on one core. Extra cores help parallel scans, concurrent users, and the nightly refresh running alongside the dashboard. |
| **Network** | 10/25 GbE | Feeds the internal CSS network. |
| **Platform** | Rocky/RHEL 9 or 10, **PostgreSQL 18 with `io_method=io_uring`**, huge pages, dedicated BMC/IPMI, redundant power supplies | Linux gets the PostgreSQL I/O optimizations macOS doesn't, and remote management means nobody has to walk over to it. |

**Rough cost guess**, since memory prices have been volatile: a 1U/2U
EPYC server with 512 GB and 2×7.68 TB of NVMe is in the low-to-mid
five figures. A 256 GB configuration costs substantially less and
would already outperform Sibyl, Gizmo and gadget on nearly every
query here.

### If it's a VM

A VM only performs well under these conditions:

- **Storage:** local NVMe (passthrough or local storage on the VM
  host), not a shared SAN or network datastore. On shared or network
  storage it will behave like Sibyl's HDD, or worse.
- **RAM:** reserved for the VM, not overcommitted.
- **CPUs:** pinned or at least not heavily shared with other VMs.

Ask campus IT exactly what storage the VM would sit on. That single
answer decides whether a VM is viable.

---

## 4. Suggested layout for the two goals

These are separate jobs, and should run on separate machines:

1. **Database server (the §3 Linux host), on the campus network.** It
   serves the CSS internal network directly over 10 GbE. It is never
   exposed to the internet and gets no inbound ports from outside.
2. **Web server.** This can be a small machine: gadget, a modest VM,
   or Gizmo. It runs Dash/waitress, publishes through a Cloudflare
   tunnel as today, and reads from the database server. The dashboard
   already does most of its work from parquet caches, so it needs very
   little database performance at request time (single-row lookups,
   the NEO Consensus join).

This puts the expensive, carefully managed hardware behind the
firewall and leaves the internet-facing machine cheap and replaceable.
On that layout, a Mac mini like gadget makes a good **web host and
failover database replica**, and the campus Linux server becomes the
**main high-performance database**.

---

## 5. Sibyl's future

Sibyl's role is what's left open. The options:

- **Upgrade it:** move to RHEL 8.10 or 9, PostgreSQL 18, add NVMe for
  PGDATA, and remove the `obs_sbn` bloat. With 251 GB RAM and NVMe it
  would come close to the §3 target for the cost of drives and an
  upgrade window. This is the cheapest route to a fast database on
  campus, if the chassis and its warranty or support life allow it.
- **Set it up as a standby** for the new database server.
- **Retire it** once the new server is running.

---

## 6. Where this differs from `server_provisioning.md`

The 2026-06-25 brief assumed **the replica lives on or beside the
public web server, outside the campus firewall, with no Cloudflare**.
This note recommends the reverse:

- the database stays inside the campus network,
- a separate, inexpensive web tier sits in front of it,
- Cloudflare stays (the tunnel provides failover, TLS, bot mitigation
  and edge rate limiting at no cost).

The brief's RAM tiers (32 / 128 / 256 GB) were sized to *back the
dashboard*. This note's tiers (256 / 512 GB) are sized to *outperform
Sibyl on every query shape*, which matters if the host also serves
analysis on the CSS network. The brief's §3–§7 (packages, systemd
units, secrets, refresh ported to systemd) still apply as written to
whichever Linux host is built.

---

## 7. Open questions

- What volume will MPC actually ingest from Rubin per year once it's
  fully running? This drives the 4 TB vs. 8 TB decision for every
  host.
- Will MPC/SBN approve a third subscription (gadget) or a fourth (a
  new Linux server)?
- Campus IT: VM storage backing, FileVault mandate, outbound
  replication port, approval for a Cloudflare tunnel.
- Is Sibyl's hardware worth putting NVMe into (§5)?
