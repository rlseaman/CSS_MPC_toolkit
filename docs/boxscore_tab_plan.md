# Boxscore Tab — Design Plan

## Purpose

A new tab for the Planetary Defense Dashboard that provides flexible,
interactive tallies of asteroid and comet **detections, tracklets, and
discoveries** broken down by object class, time period, and survey.
Modeled after MPC pages like YearlyBreakdown.html and mpc/summary, but
going well beyond them in several ways:

1. **Detections, not just discoveries** — count observations and
   tracklets, not only first-discovery credit
2. **Granular time axes** — year, month, lunation (CLN), UT date
3. **Rich object taxonomy** — 21 classes including MB subdivisions,
   Amor near/distant, Hungarias, retrograde flag
4. **Statistics beyond COUNT** — median H, element distributions,
   detection/discovery ratios, unique object counts
5. **Cross-tabulation** — any combination of class x time x station

This tab also serves as a test harness for query patterns that will
inform the design of a refined mpc_sbn schema on dedicated hardware.

---

## Object Classification Scheme

Extend the current 17-type MPC scheme with finer subdivisions.
The `orbit_classes.py` classify function returns one of these codes;
the Boxscore tab maps them to display groups.

### Current MPC types (orbit_type_int)

| Code | Name              | Count     |
|------|-------------------|-----------|
| 0    | Atira (IEO)       | 20        |
| 1    | Aten              | 767       |
| 2    | Apollo            | 4,698     |
| 3    | Amor              | 3,270     |
| 9    | Inner Other       | 0         |
| 10   | Mars Crosser      | 12,465    |
| 11   | Main Belt         | 949,751   |
| 12   | Jupiter Trojan    | 12,845    |
| 19   | Middle Other      | 7,971     |
| 20   | Jupiter Coupled   | 2,455     |
| 21   | Neptune Trojan    | 18        |
| 22   | Centaur           | 264       |
| 23   | TNO               | 1,841     |
| 30   | Hyperbolic        | 37        |
| 31   | Parabolic         | 0 in DB   |
| 99   | Other (Unusual)   | 0 in DB   |
| NULL | Unclassified      | 520,512   |

### New subdivisions for Boxscore

These are **display-level** groupings derived from the base type plus
element ranges.  They do not change orbit_type_int; they add a
`boxscore_class` column in the app layer.

**Amor split** (type 3, q boundary at 1.15 AU):
- Near Amor (q <= 1.15 AU): 1,850 objects — more PD-relevant
- Distant Amor (1.15 < q <= 1.3 AU): 1,420 objects

**Main Belt split** (type 11, using Kirkwood gap boundaries):
- Hungaria zone (1.78 < a < 2.06 AU): ~21,300 objects (high-i)
- Inner MB (2.06 <= a < 2.50 AU): ~254,000 objects
- Middle MB (2.50 <= a < 2.82 AU): ~347,000 objects
- Outer MB (2.82 <= a < 3.28 AU): ~328,000 objects
- Note: ~24 objects with a < 1.78 folded into Hungaria or flagged

**Retrograde flag** (i >= 90 deg): 83 objects across classes
- Not a separate class; shown as a filter toggle or annotation

**PHA flag**: MOID <= 0.05 AU and H <= 22.0
- Cross-cuts NEO subtypes; shown as filter toggle

### Display grouping levels

Users can toggle between:
- **Fine** (21 classes): all subdivisions shown
- **Standard** (17 classes): MPC types as-is
- **Coarse** (7 groups): NEO, Mars Crosser, Main Belt, Jupiter
  region, Outer SS, Hyperbolic/Parabolic, Unclassified

---

## Counting Dimensions

What to count (user-selectable):
- **Observations**: individual astrometric reports (obs_sbn rows)
- **Tracklets**: same-night observation groups (distinct trkid)
- **Distinct objects**: unique provid/permid per time bin
- **Discoveries**: only disc='*' observations

These are distinct and non-overlapping metrics.  Default: distinct
objects (most analogous to MPC pages, most useful for science).

---

## Time Axes

Row dimension (user-selectable):
- **Year** (default) — most direct comparison to MPC YearlyBreakdown
- **Month** (YYYY-MM)
- **Lunation** (CLN number) — 28-day periods, operationally meaningful
  for CSS; requires CLN lookup or derivation from UT date
- **UT Date** (YYYY-MM-DD) — highest granularity, large result sets

The time axis applies to `obstime` from obs_sbn (detection time).
For discovery-only counts, it's the discovery date.

---

## Station/Survey Filters

- **All stations** (default)
- **By project group**: CSS, Pan-STARRS, ATLAS, etc. (reuse
  STATION_TO_PROJECT mapping from existing tabs)
- **By individual MPC code**: dropdown/multi-select
- **Discoverer only**: limit to station that made the discovery
  (disc='*' obs)

---

## Statistics Beyond COUNT

For each cell in the cross-tabulation, optionally show:
- **Median H magnitude** — size proxy
- **Mean/median orbital elements** (a, e, i)
- **Detection-to-discovery ratio** — how many objects detected by
  a station were discovered by *someone else* (precovery measure)
- **Unique objects / total observations** — follow-up intensity
- **Objects with H < 22** — size-limited subset (CNEOS threshold)
- **Objects with H < 17.75** — ~1 km threshold

Default view: just counts.  Advanced toggle reveals extra columns.

---

## Data Architecture (Short-term: sibyl)

### Why obs_sbn joins are expensive

The `obs_sbn` table (529M rows, 239 GB on HDD) has no orbit class
column.  Classifying detections requires joining to `mpc_orbits`
(1.5M rows) on a text designation field.

Performance varies dramatically by class size:
- NEOs (~8,750 objects): 2 seconds — planner uses nested loop with
  index lookups into obs_sbn; small fan-out
- Main Belt (~950K objects): 60+ seconds per station-year, 20+
  minutes unfiltered — planner switches to hash join requiring
  full sequential scan of obs_sbn on HDD

### Approach: Python-side CSV cache (matches existing architecture)

The Boxscore tab will use the same cache pattern as existing tabs:
1. Run SQL query once, cache results to CSV
2. App loads CSV at startup (sub-second)
3. 1-day cache invalidation; `--refresh` forces re-query
4. All interactive filtering happens in pandas on cached data

### Query strategy

**For object-level tallies** (how many NEOs exist by class, H
distribution, element stats):
- Query `mpc_orbits` directly — 1.5 seconds, no obs_sbn needed
- Classify with `classify_from_elements()` in Python post-load
- This covers the MPC summary-page equivalent

**For discovery tallies** (who discovered what, when):
- The existing `LOAD_SQL` query already returns ~43K NEO discovery
  tracklets with station, date, H magnitude, orbital elements
- Extend to include non-NEO discoveries (Mars Crossers, etc.)
  by removing the NEO filter — still bounded by discovery count
- Estimated ~100K-200K total asteroid discoveries across all classes
  (each object discovered once) — manageable query

**For detection tallies** (all observations by class):
- This is the expensive case.  Strategy:
  a. Query one class at a time from the `mpc_orbits` side
     (nested-loop approach that works for classes up to ~50K objects)
  b. For Main Belt (950K objects): aggregate in mpc_orbits-driven
     batches, or accept a longer cache-build time (~5-10 min)
  c. Cache the full result; never re-query during interactive use
- Output schema: (provid, stn, year, n_obs, n_tracklets, disc_flag,
  orbit_class, h_mag)

### Estimated cache sizes

| Cache file             | Rows      | Size est. |
|------------------------|-----------|-----------|
| object_catalog.csv     | ~1.5M     | ~80 MB    |
| discovery_summary.csv  | ~200K     | ~10 MB    |
| detection_summary.csv  | ~50-100M? | Too large |

The detection summary at full granularity (all objects x all stations
x all years) may be impractical as a single CSV.  Alternatives:
- **Subset by class**: NEO detections only (~8,750 objects) — fast
  and fits the planetary defense focus
- **Pre-aggregate by year**: (class, stn, year) with counts — ~100K
  rows, tiny
- **On-demand queries**: for MB/JT detection stats, run the query
  when the user selects that class (takes 60s, show spinner)

Recommended initial approach: **pre-aggregated summary** for all
classes + **detail-on-demand** for large classes.

---

## Data Architecture (Long-term: dedicated server)

### Hardware recommendations

A dedicated server for this project changes the calculus significantly:

**SSD storage**: The single biggest win.  The 60-second Main Belt
query on HDD is dominated by random I/O (bitmap heap scan touching
441K scattered pages).  On SSD, the same scan would be 5-10x faster
(~6-12 seconds).  Sequential scans also improve ~3-4x.

**Memory**: The entire `mpc_orbits` table fits in ~1 GB of RAM.
With 32+ GB, PostgreSQL's `shared_buffers` can cache the most
frequently joined portions of obs_sbn index pages, making even
repeated full-table operations faster.

**Cores**: obs_sbn queries already parallelize well (2 workers
observed).  8+ cores would allow `max_parallel_workers_per_gather=4`
or higher, cutting scan times proportionally.

### Schema refinements on dedicated server

Since we control the new server's schema (not just readonly access):

**1. Object classification table** (highest priority):
```sql
CREATE TABLE object_catalog (
    provid text PRIMARY KEY,           -- unpacked designation
    permid integer,                    -- MPC number (nullable)
    orbit_class_int smallint NOT NULL, -- full 17-type scheme
    boxscore_class smallint NOT NULL,  -- 21-type extended scheme
    h double precision,
    a double precision,                -- derived from q/(1-e)
    e double precision,
    i double precision,
    q double precision,
    big_q double precision,            -- aphelion Q = a(1+e)
    tisserand_j double precision,
    earth_moid double precision,
    neo boolean NOT NULL DEFAULT false,
    pha boolean NOT NULL DEFAULT false,
    retrograde boolean NOT NULL DEFAULT false,
    discovery_stn text,
    discovery_date date
);
CREATE INDEX ON object_catalog(orbit_class_int);
CREATE INDEX ON object_catalog(boxscore_class);
CREATE INDEX ON object_catalog(neo) WHERE neo;
CREATE INDEX ON object_catalog(pha) WHERE pha;
```
~1.5M rows, ~150 MB.  Refresh: full rebuild nightly from
mpc_orbits (takes ~10 seconds).

**2. Detection summary materialized view** (medium priority):
```sql
CREATE MATERIALIZED VIEW detection_daily AS
SELECT
    o.provid,
    o.stn,
    o.obstime::date as obs_date,
    count(*) as n_obs,
    count(DISTINCT o.trkid) as n_tracklets,
    bool_or(o.disc = '*') as disc_flag
FROM obs_sbn o
WHERE o.provid IS NOT NULL
GROUP BY o.provid, o.stn, o.obstime::date;
```
Estimated ~200-500M rows (every object-station-night combination).
Initial build: several hours.  Incremental refresh: use
`obs_sbn.created_at > last_refresh` to process only new rows.

This eliminates the need to ever scan obs_sbn for statistical
queries — join detection_daily to object_catalog instead.

**3. Targeted indexes on obs_sbn** (if writable access):
```sql
-- Covering index for class-filtered detection queries
CREATE INDEX idx_obs_provid_stn_time
    ON obs_sbn(provid, stn, obstime);

-- Partial index for discovery observations only
CREATE INDEX idx_obs_disc
    ON obs_sbn(provid, stn, obstime) WHERE disc = '*';
```

**4. Refresh strategy for 24/7 operations**:
- `object_catalog`: full rebuild daily, ~10 seconds, negligible load
- `detection_daily`: incremental append using `created_at` watermark,
  runs every hour or on-demand, processes only new obs rows
- Schedule during Arizona afternoon (UTC ~20:00-00:00) for heaviest
  refresh; incremental updates are light enough for any time
- The server hosts a replica, so writes don't affect telescope
  operations

**5. PostgreSQL tuning for analytical workloads**:
```
shared_buffers = 8GB           # or 25% of RAM
effective_cache_size = 24GB    # or 75% of RAM
work_mem = 256MB               # allow in-memory sorts
max_parallel_workers_per_gather = 4
random_page_cost = 1.1         # SSD (default 4.0 is for HDD)
seq_page_cost = 1.0
enable_partitionwise_join = on
jit = on
```

**6. Optional: table partitioning on obs_sbn**:
- Partition by year on obstime — enables partition pruning for
  time-bounded queries
- Each yearly partition ~26M rows, fits comfortably in memory
- Makes VACUUM and index maintenance manageable

---

## Tab Layout (Boxscore)

This will be Tab 6 in the app (between Discovery Circumstances and
Tools for Planetary Defenders).

### Controls (left sidebar or top bar)

| Control          | Type          | Default         |
|------------------|---------------|-----------------|
| Count metric     | Radio buttons | Distinct objects|
| Time granularity | Dropdown      | Year            |
| Year range       | RangeSlider   | 2004-present    |
| Class grouping   | Radio buttons | Standard (17)   |
| Station filter   | Multi-dropdown| All             |
| PHA only toggle  | Checkbox      | Off             |
| Retrograde only  | Checkbox      | Off             |
| Advanced stats   | Checkbox      | Off             |

### Main display area

**Primary view: Cross-tabulation table**
- Rows: time bins (years, months, etc.)
- Columns: object classes (or grouped)
- Cells: count values with optional color intensity
- Totals row and column
- Sortable columns
- CSV download button

**Secondary view: Summary cards** (top of tab)
- Total objects by broad category (NEO, MB, Outer, etc.)
- Comparable to MPC summary page but live-updated
- Sparkline trends (last 5 years)

**Tertiary view: Charts** (below table)
- Stacked area chart of selected classes over time
- Optional: H magnitude distribution per selected class

### Query/Cache structure

Three cache files, refreshed on `--refresh` or 1-day invalidation:

1. **boxscore_objects.csv** — one row per object from mpc_orbits,
   with all classification columns pre-computed in Python.
   ~1.5M rows.  Query time: ~2 seconds + Python classification.

2. **boxscore_discoveries.csv** — one row per discovery observation,
   all classes.  ~200K rows.  Query time: ~30 seconds.

3. **boxscore_neo_detections.csv** — NEO detections at
   (object, station, night) granularity.  ~2-5M rows for NEOs
   only.  Query time: ~30-60 seconds (small class, nested loop).
   Larger classes added as on-demand queries later.

---

## Implementation Phases

### Phase 1: Object-level boxscore (fast, no obs_sbn)
- Build `boxscore_objects.csv` from mpc_orbits
- Extended classification (MB subdivisions, Amor split, PHA, retro)
- Summary cards + cross-tabulation of object counts by class
- H magnitude distributions
- Compare directly to MPC summary page — immediate value

### Phase 2: Discovery-level boxscore
- Build `boxscore_discoveries.csv` from obs_sbn (disc='*' only)
- Discovery counts by class x year x station
- Direct comparison to MPC YearlyBreakdown — but for ALL classes
- Add CLN (lunation) time axis

### Phase 3: NEO detection-level boxscore
- Build `boxscore_neo_detections.csv` from obs_sbn + mpc_orbits
- Detection and tracklet counts for NEOs by station x time
- Follow-up intensity metrics
- This is the planetary-defense-specific value-add

### Phase 4: Dedicated server deployment
- Stand up object_catalog and detection_daily tables
- Full detection stats for all classes (including MB)
- PostgreSQL tuning for analytical workloads
- Incremental refresh pipeline

---

## Open Questions

1. Should the boxscore tab include comets?  The current mpc_orbits
   table is asteroid-only.  Comets would need a separate data source.

2. CLN (Catalina Lunation Number) derivation: is there a lookup table,
   or do we derive from UT date?  Need the epoch and period.

3. For the dedicated server: full replica of mpc_sbn, or selective
   tables only?  Full replica simplifies maintenance but requires
   more storage.

4. Should the extended classification (21 types) be pushed back into
   `orbit_classes.py` as a new function, or kept as app-layer logic?
   Recommend: new function `classify_extended()` in orbit_classes.py.
