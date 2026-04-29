-- station_report.sql — per-site rollup of obs / tracklets / discoveries.
-- Splits NEOs vs. non-NEOs using *current* mpc_orbits q/e (q ≤ 1.3 AU,
-- e < 1.0).  Orbit class label is derived live via
-- css_utilities.classify_orbit_label(q, e, i) — we deliberately do
-- NOT trust mpc_orbits.orbit_type_int, which is NULL for ~35 pct of
-- rows. (The bare percent sign would otherwise confuse psycopg2's
-- parameter binder, which doesn't strip SQL comments before reading.)
--
-- Parameters:
--   :site          — IAU obs code ('V00', 'F51', '703', …)
--   :date_start    — inclusive lower bound on obstime (or NULL for all)
--   :date_end      — inclusive upper bound on obstime (or NULL for all)
--
-- One result row per (year × is_neo × orbit_class) bucket.  The ORDER
-- and stage of each CTE matters for performance — see comments.
--
-- Resolution path: obs_sbn.provid is joined directly to
-- mpc_orbits.unpacked_primary_provisional_designation (uniquely
-- indexed).  Objects whose provid is a SECONDARY (alias) — typically
-- renamed/merged identifications — fall into 'Unclassified'.  These
-- are minority cases; if they show up materially in a result we'll
-- add a current_identifications fallback path here.

WITH site_obs AS (
    -- Indexed scan on obs_sbn.stn.  V00 → ~4.5 M rows; F51 → ~50 M.
    -- Performance is dominated by this slice; everything downstream
    -- works on the result.
    SELECT
        permid, provid, trkid, disc, obstime,
        EXTRACT(YEAR FROM obstime)::int AS obs_year
    FROM obs_sbn
    WHERE stn = %(site)s
      AND (%(date_start)s::date IS NULL OR obstime::date >= %(date_start)s::date)
      AND (%(date_end)s::date   IS NULL OR obstime::date <= %(date_end)s::date)
),
-- Distinct objects observed at this site.  Typically O(10⁵) for an
-- active survey — small enough to hash-aggregate in seconds.
site_objects AS (
    SELECT DISTINCT provid
    FROM site_obs
    WHERE provid IS NOT NULL
),
-- Single equi-join on the unique index
-- (mpc_orbits.unpacked_primary_provisional_designation).  Index lookup
-- per object — fast.
classified AS (
    SELECT
        obj.provid,
        m.q, m.e, m.i, m.h,
        css_utilities.classify_orbit_label(m.q, m.e, m.i) AS orbit_class,
        (m.q IS NOT NULL AND m.e IS NOT NULL
         AND m.q <= 1.3 AND m.e < 1.0)                    AS is_neo
    FROM site_objects obj
    LEFT JOIN mpc_orbits m
        ON m.unpacked_primary_provisional_designation = obj.provid
)
SELECT
    o.obs_year,
    COALESCE(c.is_neo, false)                            AS is_neo,
    COALESCE(c.orbit_class, 'Unclassified')              AS orbit_class,
    COUNT(*)                                             AS obs_count,
    COUNT(DISTINCT o.trkid)                              AS tracklet_count,
    COUNT(DISTINCT o.provid)                             AS object_count,
    COUNT(*) FILTER (WHERE o.disc = '*')                 AS discovery_obs,
    COUNT(DISTINCT o.provid) FILTER (WHERE o.disc = '*') AS discovery_objects
FROM site_obs o
LEFT JOIN classified c ON c.provid = o.provid
GROUP BY o.obs_year, COALESCE(c.is_neo, false),
         COALESCE(c.orbit_class, 'Unclassified')
ORDER BY o.obs_year, is_neo DESC, orbit_class;
