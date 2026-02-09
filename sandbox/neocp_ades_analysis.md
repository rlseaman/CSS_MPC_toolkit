# NEOCP Tables & ADES Export Feasibility Analysis

Generated: 2026-02-08

## 1. NEOCP Table Inventory

Six tables form a complete lifecycle model for objects transiting the NEO
Confirmation Page:

| Table | Rows | Role |
|-------|------|------|
| `neocp_els` | 58 | Current orbital elements (live NEOCP only) |
| `neocp_obs` | 1,081 | Current observations (live NEOCP only) |
| `neocp_var` | 102K | Orbit variant clones / MCMC samples (live only) |
| `neocp_obs_archive` | 777K | Archived observations after NEOCP removal |
| `neocp_events` | 310K | Audit log of every action (back to 2019-03) |
| `neocp_prev_des` | 71K | Final designation mapping after removal |

The "live" tables (`neocp_els`, `neocp_obs`, `neocp_var`) are a snapshot of
what's currently on the NEOCP -- objects cycle through in days.  The archive
and events tables are the permanent historical record.

### Schema Details

**neocp_els** -- Current orbital elements for objects on the NEOCP

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | integer | NO | PK |
| desig | varchar(16) | NO | UNIQUE, temporary NEOCP designation |
| els | varchar(255) | NO | Packed orbital elements string |
| dsc_obs | varchar(255) | NO | Discovery observation in 80-col format |
| digest2 | numeric | YES | Digest2 NEO score (0-100) |
| flag | char(1) | YES | NULL or 'S' |
| prep | char(1) | YES | Always NULL in current data |
| comet | char(1) | YES | NULL or 'T' (comet flag) |
| created_at | timestamp | YES | UTC |
| updated_at | timestamp | YES | UTC |

**neocp_obs / neocp_obs_archive** -- Observations (identical schema)

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | integer | NO | PK |
| desig | varchar(16) | NO | Temporary NEOCP designation |
| trkid | text | NO | Tracklet ID (links to obs_sbn) |
| obs80 | varchar(255) | NO | Full 80-column MPC format line |
| rmstime | numeric | YES | Time uncertainty (seconds) |
| rmsra | numeric | YES | RA*cos(Dec) uncertainty (arcsec) |
| rmsdec | numeric | YES | Dec uncertainty (arcsec) |
| rmscorr | numeric | YES | RA-Dec correlation (-1 to +1) |
| force_code | text | YES | |
| created_at | timestamp | YES | Record creation time |
| updated_at | timestamp | YES | Record update time |

**neocp_events** -- Audit log

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | integer | NO | PK |
| desig | text | YES | Temporary NEOCP designation |
| event_type | text | YES | ADDOBJ, UPDOBJ, REDOOBJ, REMOBJ, FLAG, COMBINEOBJ, REMOBS |
| event_text | text | YES | Free-text description |
| event_user | text | YES | 17 distinct users (human + automated) |
| created_at | timestamp | YES | UTC |
| updated_at | timestamp | YES | UTC |

**neocp_prev_des** -- Final designation after NEOCP removal

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | integer | NO | PK |
| desig | text | NO | Temporary NEOCP designation |
| status | text | YES | 'lost', 'dne', 'na', 'ns', etc. or another NEOCP desig |
| iau_desig | text | YES | Final IAU designation (e.g. '2024 YR4') |
| pkd_desig | text | YES | Packed MPC designation |
| ref | text | YES | |
| digest2 | numeric | YES | Digest2 score at removal time |
| created_at | timestamp | YES | UTC |
| updated_at | timestamp | YES | UTC |

**neocp_var** -- Orbit variant clones

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | integer | NO | PK |
| desig | varchar(16) | NO | Temporary NEOCP designation |
| els | varchar(255) | NO | Variant orbital elements |
| created_at | timestamp | YES | UTC |
| updated_at | timestamp | YES | UTC |

### Data Ranges

- `neocp_obs_archive` and `neocp_events`: back to 2019-03-14 (system inception)
- `neocp_prev_des.created_at`: back to 2013-01-01 (historical backfill)
- `neocp_var`: only last ~5 days (purged when objects leave NEOCP)
- Live tables (`neocp_els`, `neocp_obs`): oldest object ~2025-07-26

## 2. Join Paths

### Within NEOCP tables

All join on `desig` (temporary NEOCP designation):

```sql
-- Full lifecycle of an NEOCP object
SELECT pd.desig, pd.iau_desig, pd.status,
       oa.obs80, oa.rmsra, oa.rmsdec,
       ev.event_type, ev.event_text, ev.event_user
FROM neocp_prev_des pd
JOIN neocp_obs_archive oa ON oa.desig = pd.desig
JOIN neocp_events ev ON ev.desig = pd.desig
WHERE pd.iau_desig = '2024 YR4';
```

### To main catalog

`neocp_prev_des` bridges temporary to permanent designations:

```sql
-- Link NEOCP archive to mpc_orbits via final packed designation
SELECT pd.desig AS neocp_desig, pd.iau_desig,
       mo.q, mo.e, mo.i, mo.orbit_type_int
FROM neocp_prev_des pd
JOIN mpc_orbits mo
    ON mo.unpacked_primary_provisional_designation = pd.iau_desig
WHERE pd.iau_desig IS NOT NULL AND pd.iau_desig != '';
```

### To obs_sbn

`trkid` links NEOCP observations to permanent observation records:

```sql
-- Match NEOCP observations to their final obs_sbn records
SELECT oa.desig, oa.obs80 AS neocp_obs80, o.obs80 AS sbn_obs80,
       oa.created_at AS neocp_time, o.created_at AS sbn_time
FROM neocp_obs_archive oa
JOIN obs_sbn o ON o.trkid = oa.trkid
WHERE oa.desig = 'P22lq3P'
LIMIT 10;
```

## 3. Event Type Distribution

| Event | Count | Meaning |
|-------|-------|---------|
| UPDOBJ | 172,312 | Observations added (automated by `process_neocp`) |
| REDOOBJ | 50,019 | Orbit recomputed and pushed |
| ADDOBJ | 43,189 | New object posted (automated by `process_newneo`) |
| REMOBJ | 42,308 | Object removed from NEOCP |
| FLAG | 1,716 | Flags set (comet, etc.) |
| COMBINEOBJ | 763 | Two designations merged |
| REMOBS | 20 | Observations removed |

Operators: 17 distinct users.  `process_neocp` (172K), `pveres` (70K),
`process_newneo` (43K) account for >90% of events.

## 4. Observation-to-Ingestion Latency

The `obs80` field embeds the observation timestamp at positions 16-32 (MPC
80-column format), while `created_at` records database ingestion time.

| Metric | Value |
|--------|-------|
| Minimum | ~3 minutes |
| **Median** | **~45 minutes** |
| 90th percentile | ~11.5 hours |
| 95th percentile | ~42 hours |
| Maximum | weeks (precovery) |

The ~45 min median represents the real pipeline: telescope -> image processing
-> source extraction -> submission -> MPC receipt -> NEOCP posting.  The long
tail comes from precovery observations linked after the fact (e.g., object
posted Feb 7 with obs from Jan 21 = 424 hrs, which is archival linkage rather
than pipeline delay).

Representative examples:
```
P22lq3P: obs 2026-02-07 21:16 -> created 2026-02-07 21:25  =   9.5 min
P22bZYt: obs 2025-07-27 04:29 -> created 2025-07-27 04:42  =  13.0 min
P22liAW: obs 2026-02-02 07:49 -> created 2026-02-02 09:49  =   2.0 hrs
ZTF10Ax: obs 2026-01-28 06:00 -> created 2026-01-28 20:55  =  14.9 hrs
CE5W292: obs 2026-01-21 05:00 -> created 2026-02-07 21:09  = 424.1 hrs (precovery)
```

## 5. ADES Export Feasibility

### Field Mapping: NEOCP -> ADES

| ADES Field | Source | Available? |
|------------|--------|------------|
| `permID` / `provID` / `trkSub` | `obs80` cols 1-12, or `neocp_prev_des.iau_desig` | Yes |
| `obsTime` | `obs80` cols 16-32, convert to ISO 8601 | Yes |
| `ra` | `obs80` cols 33-44, convert HMS -> decimal degrees | Yes |
| `dec` | `obs80` cols 45-56, convert DMS -> decimal degrees | Yes |
| `mag` | `obs80` cols 66-70 | Yes |
| `band` | `obs80` col 71 (legacy code -> ADES code mapping) | Yes |
| `stn` | `obs80` cols 78-80 | Yes |
| `mode` | `obs80` col 15 (C->CCD, etc.) | Yes |
| `disc` | `obs80` col 13 | Yes |
| `notes` | `obs80` col 14 | Yes |
| `rmsRA` | `rmsra` column (arcsec) | **Yes (ADES-native)** |
| `rmsDec` | `rmsdec` column (arcsec) | **Yes (ADES-native)** |
| `rmsCorr` | `rmscorr` column | **Yes (ADES-native)** |
| `rmsTime` | `rmstime` column (seconds) | **Yes (ADES-native)** |
| `astCat` | obs80 col 72 (single-char code, partial mapping) | Partial |
| `ref` | obs80 cols 72-77 (packed) | Yes (MPC-assigned) |
| Telescope metadata | Not in database | **No** |
| Observer/measurer names | Not in database | **No** |
| Software | Not in database | **No** |

### Assessment

**Valid ADES for distribution (general.xsd): YES.**  All required observation
fields are present.  The rms fields are a genuine value-add over raw 80-column
format.  Header metadata (telescope, observers) is missing but optional.

**Valid ADES for re-submission (submit.xsd): NO.**  Submit schema requires
`astCat` (full catalog name), plus mandatory header blocks for observatory,
submitter, observers, measurers, and telescope.  These are not in the database.

### Key Value Proposition

The NEOCP tables are the **best** source in this database for ADES conversion:
they have `rmsra`, `rmsdec`, `rmscorr`, and `rmstime` columns that the MPC
computes but doesn't encode in 80-column format.  The main `obs_sbn` table has
only `obs80` with no uncertainty columns.  NEOCP-derived ADES carries genuinely
more information than obs_sbn alone.

## 6. Interesting Analytical Queries

### NEOCP outcomes
```sql
-- What fraction of NEOCP postings become real designations?
SELECT
    CASE
        WHEN iau_desig IS NOT NULL AND iau_desig != '' THEN 'designated'
        WHEN status = 'lost' THEN 'lost'
        WHEN status = 'dne' THEN 'does not exist'
        ELSE 'other (' || COALESCE(status, 'null') || ')'
    END AS outcome,
    count(*)
FROM neocp_prev_des
GROUP BY 1
ORDER BY 2 DESC;
```

### Observatory throughput on NEOCP
```sql
SELECT substring(obs80, 78, 3) AS stn, count(*) AS nobs,
       count(DISTINCT desig) AS n_objects
FROM neocp_obs_archive
GROUP BY 1 ORDER BY 2 DESC
LIMIT 20;
```

### Per-object observation count distribution
```sql
SELECT desig, count(*) AS nobs,
       min(created_at) AS first_seen, max(created_at) AS last_seen
FROM neocp_obs_archive
GROUP BY desig
ORDER BY nobs DESC
LIMIT 20;
```

### Time on NEOCP before removal
```sql
SELECT pd.desig, pd.iau_desig,
       min(ev_add.created_at) AS posted,
       min(ev_rem.created_at) AS removed,
       min(ev_rem.created_at) - min(ev_add.created_at) AS duration
FROM neocp_prev_des pd
JOIN neocp_events ev_add ON ev_add.desig = pd.desig AND ev_add.event_type = 'ADDOBJ'
JOIN neocp_events ev_rem ON ev_rem.desig = pd.desig AND ev_rem.event_type = 'REMOBJ'
WHERE pd.iau_desig IS NOT NULL AND pd.iau_desig != ''
GROUP BY pd.desig, pd.iau_desig
ORDER BY duration DESC
LIMIT 20;
```
