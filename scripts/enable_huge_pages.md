# Enabling Huge Pages for PostgreSQL on sibyl

**Host:** sibyl (RHEL 8.6, 251 GB RAM, HDD)
**Status:** Deferred — memory fragmentation prevented full allocation on 2026-02-08.
Best attempted during a maintenance reboot when contiguous memory is guaranteed.

## Why Huge Pages

With `shared_buffers = 64GB`, PostgreSQL manages 16.7 million 4 KB pages.
Each needs a TLB (Translation Lookaside Buffer) entry.  Huge pages use 2 MB
pages instead, reducing the count to ~32,768 — small enough to fit in the
CPU's TLB cache.  Expected benefit: 5-10% reduction in CPU overhead for
TLB-heavy workloads (index scans, replication apply).

## Prerequisites

### 1. Determine postgres group ID

```bash
id -g postgres
# Note this value — used in step 3 as <postgres_gid>
```

### 2. Calculate huge page count

```bash
# shared_buffers in GB / 2 MB per page + 5% margin
# For 64 GB: 64 * 1024 / 2 * 1.05 = 34,406 → round to 34408
# For 58 GB: 58 * 1024 / 2 * 1.05 = 31,213 → round to 31216
```

### 3. Configure kernel (persistent across reboots)

```bash
cat > /etc/sysctl.d/99-postgresql-hugepages.conf << EOF
vm.nr_hugepages = 34408
vm.hugetlb_shm_group = <postgres_gid>
EOF
```

### 4. Apply sysctl

```bash
sysctl --system
```

### 5. Verify allocation

```bash
grep HugePages_Total /proc/meminfo
```

If `HugePages_Total` matches the requested count, proceed.  If it's lower,
memory is fragmented — see Troubleshooting below.

### 6. Configure PostgreSQL

In `postgresql.conf`:
```
huge_pages = 'on'
```

Use `'on'` (not `'try'`) so misconfiguration fails visibly at startup
rather than silently falling back.

If shared_buffers doesn't fit in the available huge pages, reduce it:
```
shared_buffers = '58GB'    # if only ~30,000 pages available
```

### 7. Restart PostgreSQL

```bash
systemctl restart postgresql-15
```

### 8. Verify huge pages in use

```bash
grep HugePages /proc/meminfo
```

`HugePages_Free` should drop by approximately `shared_buffers / 2MB`.

## Troubleshooting

### Memory fragmentation (HugePages_Total < requested)

The kernel needs contiguous 2 MB blocks.  After running for weeks/months,
memory becomes fragmented and the kernel can't assemble enough contiguous
blocks.

**Option A — Best: enable at boot time**

Add `vm.nr_hugepages=34408` to sysctl.d (already done in step 3).
At next reboot, pages are reserved before anything fragments memory.

**Option B — Drop caches and retry**

```bash
systemctl stop postgresql-15
sync
echo 3 > /proc/sys/vm/drop_caches
sysctl -w vm.nr_hugepages=34408
grep HugePages_Total /proc/meminfo
# If successful, start PostgreSQL:
systemctl start postgresql-15
```

**Option C — Reduce to what's available**

On 2026-02-08, the kernel could allocate 30,205 of 34,408 requested pages
(59 GB).  Set shared_buffers = '58GB' and nr_hugepages = 30205 to match.

### PostgreSQL fails to start with huge_pages = 'on'

```bash
# Check the log
tail -20 /var/lib/pgsql/15/data/log/$(ls -t /var/lib/pgsql/15/data/log/ | head -1)

# Temporarily fall back
# In postgresql.conf: huge_pages = 'try'
systemctl start postgresql-15
```

Common causes:
- `nr_hugepages` too low for `shared_buffers`
- `hugetlb_shm_group` doesn't match postgres GID
- Huge pages reserved but locked by another process

### Stale lockfile after failed start

```bash
# If postmaster.pid exists but postgres isn't running:
rm /var/lib/pgsql/15/data/postmaster.pid
systemctl start postgresql-15
```

## 2026-02-08 Attempt Log

1. Set `nr_hugepages = 34408` — kernel allocated only 30,205 (fragmentation)
2. Set `huge_pages = 'on'`, `shared_buffers = '64GB'` — PostgreSQL failed
3. Changed to `huge_pages = 'try'` — PostgreSQL started but was killed by
   monitoring tool querying missing `pg_buffercache`/`pg_stat_statements`
   extensions, then failed to restart due to huge pages still reserving 59 GB
4. Fixed by: `sysctl -w vm.nr_hugepages=0`, `systemctl reset-failed`,
   then `systemctl start postgresql-15`
5. Deferred huge pages to next maintenance reboot
