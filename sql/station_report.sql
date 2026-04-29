-- station_report.sql — per-site rollup of obs / tracklets / discoveries.
--
-- NEO vs. non-NEO split is taken from obs_sbn_neo (a matview with
-- the canonical NEO definition: q <= 1.3 AU, plus alias resolution
-- through current_identifications and numbered_identifications, so
-- secondary provisional designations and numbered primaries are all
-- folded into the same bucket).  Trying to redo this split inline
-- against mpc_orbits.q/e undercounts ~25 pct of NEO obs because of
-- both the missing alias paths and the (unwanted) e<1 exclusion of
-- hyperbolic NEOs.
--
-- Orbit class label (Atira/Aten/Apollo/Amor/Main Belt/...) is then
-- derived live per-object via css_utilities.classify_orbit_label(
-- q, e, i) against current mpc_orbits — we deliberately do NOT use
-- mpc_orbits.orbit_type_int, which is NULL for ~35 pct of rows.
-- Objects without a published orbit in mpc_orbits (mostly NEOCP
-- candidates) bucket as 'Unclassified' — present rather than dropped.
-- An alias path object whose provid doesn't match mpc_orbits primary
-- directly will also land in 'Unclassified', but its is_neo flag is
-- still correct because it came from obs_sbn_neo.
--
-- Parameters:
--   :site          — IAU obs code ('V00', 'F51', '703', ...)
--   :date_start    — inclusive lower bound on obstime (or NULL for all)
--   :date_end      — inclusive upper bound on obstime (or NULL for all)
--
-- One result row per (year x is_neo x orbit_class) bucket.

WITH site_obs AS (
    -- Indexed scan on obs_sbn.stn.  V00 -> ~4.5 M rows; F51 -> ~50 M.
    -- Carries the NEO flag from a LEFT JOIN against obs_sbn_neo on
    -- the shared id column (obs_sbn_neo is a row-subset of obs_sbn).
    SELECT
        o.permid, o.provid, o.trkid, o.disc, o.obstime,
        EXTRACT(YEAR FROM o.obstime)::int AS obs_year,
        (n.id IS NOT NULL) AS is_neo
    FROM obs_sbn o
    LEFT JOIN obs_sbn_neo n
        ON n.id = o.id AND n.stn = %(site)s
    WHERE o.stn = %(site)s
      AND (%(date_start)s::date IS NULL OR o.obstime::date >= %(date_start)s::date)
      AND (%(date_end)s::date   IS NULL OR o.obstime::date <= %(date_end)s::date)
),
-- Distinct objects at this site.  Typically O(10^5) for an active
-- survey — small enough to hash-aggregate in seconds.
site_objects AS (
    SELECT DISTINCT provid
    FROM site_obs
    WHERE provid IS NOT NULL
),
-- Single equi-join to mpc_orbits via the unique index on the primary
-- provisional designation, only to look up the orbit class label.
classified AS (
    SELECT
        obj.provid,
        css_utilities.classify_orbit_label(m.q, m.e, m.i) AS orbit_class
    FROM site_objects obj
    LEFT JOIN mpc_orbits m
        ON m.unpacked_primary_provisional_designation = obj.provid
)
SELECT
    o.obs_year,
    o.is_neo,
    COALESCE(c.orbit_class, 'Unclassified')              AS orbit_class,
    COUNT(*)                                             AS obs_count,
    COUNT(DISTINCT o.trkid)                              AS tracklet_count,
    COUNT(DISTINCT o.provid)                             AS object_count,
    COUNT(*) FILTER (WHERE o.disc = '*')                 AS discovery_obs,
    COUNT(DISTINCT o.provid) FILTER (WHERE o.disc = '*') AS discovery_objects
FROM site_obs o
LEFT JOIN classified c ON c.provid = o.provid
GROUP BY o.obs_year, o.is_neo,
         COALESCE(c.orbit_class, 'Unclassified')
ORDER BY o.obs_year, o.is_neo DESC, orbit_class;
