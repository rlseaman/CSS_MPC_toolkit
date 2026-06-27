-- ==============================================================================
-- DAILY ORBIT NEWS — nightly snapshot capture (SKETCH / PROPOSAL)
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-25
-- Design:  docs/2026-06-25_daily_orbit_news_design.md
--
-- Inserts today's watch-set element state into css_orbit_watch.orbit_snapshot.
-- Idempotent for a given date (ON CONFLICT refresh). Run nightly AFTER the
-- mpc_orbits replication has caught up (i.e. in refresh_matview_gizmo.sh after
-- the consensus stage). Runs as the schema owner, not claude_ro (INSERT).
--
-- Watch set: q <= 1.5 AND e < 1, UNION any NEA.txt member (in_mpc) as a safety
-- net. Classification is derived from elements; orbit_type_int is NOT trusted.
-- disc_by is pulled from obs_summary (NEO-scoped) -- objects outside that
-- matview get NULL disc_by, acceptable for v1.
--
-- :snap_date defaults to CURRENT_DATE; override for backfill from kept history.
-- ==============================================================================

\set snap_date CURRENT_DATE

INSERT INTO css_orbit_watch.orbit_snapshot AS s (
    snapshot_date, primary_desig, permid, disc_by,
    q, e, i, a, earth_moid, h, u_param, nobs_total,
    is_neo, is_pha, neo_subclass, src_updated_at
)
WITH watch AS (
    SELECT
        mo.unpacked_primary_provisional_designation AS primary_desig,
        ni.permid                                   AS permid,
        mo.q, mo.e, mo.i,
        COALESCE(mo.a, CASE WHEN mo.e < 1 THEN mo.q / (1 - mo.e) END) AS a,
        mo.earth_moid, mo.h, mo.u_param, mo.nobs_total,
        mo.updated_at                               AS src_updated_at
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
      ON ni.packed_primary_provisional_designation = mo.packed_primary_provisional_designation
    WHERE (mo.q <= 1.5 AND mo.e < 1)
       OR mo.packed_primary_provisional_designation IN (
            SELECT packed_desig FROM css_neo_consensus.v_membership_wide WHERE in_mpc
          )
)
SELECT
    :snap_date::date,
    w.primary_desig, w.permid,
    os.disc_by,
    w.q, w.e, w.i, w.a, w.earth_moid, w.h, w.u_param, w.nobs_total,
    (w.q IS NOT NULL AND w.q <= 1.3)                   AS is_neo,
    (w.earth_moid IS NOT NULL AND w.earth_moid <= 0.05
       AND w.h IS NOT NULL AND w.h <= 22.0)            AS is_pha,
    -- element-derived NEO subclass (boundaries per memory/NEO classes);
    -- Q = aphelion = a*(1+e). NULL outside the NEO region.
    CASE
      WHEN w.q > 1.3 OR w.e >= 1 THEN NULL
      WHEN w.a < 1.0 AND w.a*(1+w.e) < 0.983 THEN 'Atira'
      WHEN w.a < 1.0                          THEN 'Aten'
      WHEN w.q < 1.017                        THEN 'Apollo'
      ELSE 'Amor'
    END                                                AS neo_subclass,
    w.src_updated_at
FROM watch w
LEFT JOIN css_neo_consensus.obs_summary os
       ON os.primary_desig = w.primary_desig
ON CONFLICT (snapshot_date, primary_desig) DO UPDATE SET
    permid = EXCLUDED.permid, disc_by = EXCLUDED.disc_by,
    q = EXCLUDED.q, e = EXCLUDED.e, i = EXCLUDED.i, a = EXCLUDED.a,
    earth_moid = EXCLUDED.earth_moid, h = EXCLUDED.h,
    u_param = EXCLUDED.u_param, nobs_total = EXCLUDED.nobs_total,
    is_neo = EXCLUDED.is_neo, is_pha = EXCLUDED.is_pha,
    neo_subclass = EXCLUDED.neo_subclass,
    src_updated_at = EXCLUDED.src_updated_at;
