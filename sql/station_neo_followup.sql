-- ==============================================================================
-- STATION NEO FOLLOW-UP PARTITION
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Authors: Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
-- Created: 2026-06-24
--
-- For a set of MPC station codes and a date window, partition each station's
-- NEO observations into:
--   * discoveries  -- distinct NEAs whose disc='*' observation the station made
--   * follow-up    -- the station's observations AFTER an object's discovery
--   * precovery    -- the station's observations BEFORE an object's discovery
-- reporting unique-object, observation, and tracklet counts for each.
--
-- Built to double-check CSS progress-report figures. See
-- docs/2026-06-24_neo_station_followup_report.md for the first run's results
-- and the full methodology writeup. Sister script to
-- station_discovery_profile.sql (which does all-time, all-station discovery
-- counts using the q<=1.30 orbit definition rather than the NEA.txt list).
--
-- NEO DEFINITION: MPC NEA.txt, via css_neo_consensus.v_membership_wide.in_mpc
--   (ingested nightly from minorplanetcenter.net/iau/MPCORB/NEA.txt). Requires
--   the css_neo_consensus schema + obs_sbn_neo matview, which currently live
--   on the Gizmo replica only (not Sibyl). To use the broader q<=1.30 catalog
--   instead, swap the nea_desig CTE for a mpc_orbits-based NEO list.
--
-- MATCHING: observations are matched to NEA objects on BOTH permid AND provid
--   (plus secondary provisional aliases). Both are required -- numbered objects
--   such as Apophis carry most of their obs under permid with an empty provid.
--
-- PARTITION PIVOT: each object's earliest disc='*' observation. The discovery
--   tracklet (same trkid) is excluded from both follow-up and precovery.
--   Self-discoveries ARE counted in follow-up. Objects with no disc='*' flag
--   anywhere in the archive cannot be classified and are reported separately
--   by the diagnostic at the bottom.
--
-- WINDOW: applied to observation date (obstime), half-open [t0, t1).
--
-- RUNTIME: ~8-9 min for the main query against the 5.09M-row obs_sbn_neo
--   matview on Gizmo NVMe; the diagnostic adds ~2 min. No raw obs_sbn scan.
--
-- USAGE:
--   Edit the t0/t1 window and the targets(stn) VALUES list below, then:
--     psql -h /tmp -U claude_ro mpc_sbn -f sql/station_neo_followup.sql
-- ==============================================================================

\timing on

-- Reporting window (half-open: t1 is exclusive, so use the day AFTER the last
-- date you want included).
\set t0 '2025-08-01'
\set t1 '2026-06-18'

-- ------------------------------------------------------------------------------
-- MAIN QUERY: discovery / follow-up / precovery counts per target station
-- ------------------------------------------------------------------------------
WITH
targets(stn) AS (VALUES        -- <-- edit the station list here
  ('703'), ('G96'), ('V00'), ('I52'), ('V06')
),
nea_desig AS (                 -- every designation of every NEA.txt member
  SELECT md.primary_desig, md.designation, md.kind
  FROM css_neo_consensus.v_member_designations md
  JOIN css_neo_consensus.v_membership_wide w USING (primary_desig)
  WHERE w.in_mpc
),
neo_obs_raw AS (               -- NEA observations, tagged by object, via both keys
  SELECT o.obsid, d.primary_desig AS obj, o.stn, o.obstime,
         NULLIF(o.trkid,'') AS trkid, o.disc
  FROM obs_sbn_neo o
  JOIN nea_desig d ON o.provid = d.designation AND d.kind IN ('primary','secondary')
  UNION ALL
  SELECT o.obsid, d.primary_desig, o.stn, o.obstime, NULLIF(o.trkid,''), o.disc
  FROM obs_sbn_neo o
  JOIN nea_desig d ON o.permid = d.designation AND d.kind = 'permid'
),
neo_obs AS (                   -- one row per observation, mapped to its object
  SELECT DISTINCT ON (obsid) obsid, obj, stn, obstime, trkid, disc
  FROM neo_obs_raw ORDER BY obsid, obj
),
disc AS (                      -- discovery (earliest disc='*') per object
  SELECT DISTINCT ON (obj) obj, stn AS disc_stn, obstime AS disc_time, trkid AS disc_trkid
  FROM neo_obs WHERE disc = '*' ORDER BY obj, obstime
),
tagged AS (
  SELECT n.obj, n.stn, n.obstime,
         COALESCE(n.trkid, n.obsid) AS trk,   -- null trkid => singleton tracklet
         d.disc_stn, d.disc_time,
         CASE
           WHEN d.disc_time IS NULL THEN 'unknown_disc'
           WHEN n.trkid IS NOT NULL AND n.trkid = d.disc_trkid THEN 'disc_tracklet'
           WHEN n.obstime < d.disc_time THEN 'precovery'
           WHEN n.obstime > d.disc_time THEN 'followup'
           ELSE 'disc_tracklet'
         END AS role
  FROM neo_obs n LEFT JOIN disc d USING (obj)
),
win AS (
  SELECT * FROM tagged
  WHERE obstime >= :'t0'::timestamp AND obstime < :'t1'::timestamp
)
SELECT stn, category, unique_objects, observations, tracklets FROM (
  -- Discoveries: distinct NEAs the station discovered within the window
  SELECT d.disc_stn AS stn, '1_discoveries' AS category,
         COUNT(DISTINCT d.obj) AS unique_objects,
         NULL::bigint AS observations, NULL::bigint AS tracklets, 1 AS ord
  FROM disc d JOIN targets t ON t.stn = d.disc_stn
  WHERE d.disc_time >= :'t0'::timestamp AND d.disc_time < :'t1'::timestamp
  GROUP BY d.disc_stn
  UNION ALL
  SELECT w.stn, '2_followup', COUNT(DISTINCT w.obj), COUNT(*), COUNT(DISTINCT w.trk), 2
  FROM win w JOIN targets t ON t.stn = w.stn
  WHERE w.role = 'followup' GROUP BY w.stn
  UNION ALL
  SELECT w.stn, '3_precovery', COUNT(DISTINCT w.obj), COUNT(*), COUNT(DISTINCT w.trk), 3
  FROM win w JOIN targets t ON t.stn = w.stn
  WHERE w.role = 'precovery' GROUP BY w.stn
) x
ORDER BY stn, ord;

-- ------------------------------------------------------------------------------
-- DIAGNOSTIC: in-window observations of NEAs with no disc='*' flag in the
-- archive, which therefore cannot be classified. (CTEs are repeated because
-- each psql statement is independent.)
-- ------------------------------------------------------------------------------
\echo === DIAGNOSTIC: unclassifiable in-window obs (NEA has no disc flag) ===
WITH
targets(stn) AS (VALUES ('703'), ('G96'), ('V00'), ('I52'), ('V06')),
nea_desig AS (
  SELECT md.primary_desig, md.designation, md.kind
  FROM css_neo_consensus.v_member_designations md
  JOIN css_neo_consensus.v_membership_wide w USING (primary_desig) WHERE w.in_mpc),
neo_obs_raw AS (
  SELECT o.obsid, d.primary_desig AS obj, o.stn, o.obstime, NULLIF(o.trkid,'') AS trkid, o.disc
  FROM obs_sbn_neo o JOIN nea_desig d ON o.provid = d.designation AND d.kind IN ('primary','secondary')
  UNION ALL
  SELECT o.obsid, d.primary_desig, o.stn, o.obstime, NULLIF(o.trkid,''), o.disc
  FROM obs_sbn_neo o JOIN nea_desig d ON o.permid = d.designation AND d.kind = 'permid'),
neo_obs AS (SELECT DISTINCT ON (obsid) obsid, obj, stn, obstime, trkid, disc FROM neo_obs_raw ORDER BY obsid, obj),
disc AS (SELECT DISTINCT ON (obj) obj, obstime AS disc_time FROM neo_obs WHERE disc = '*' ORDER BY obj, obstime)
SELECT n.stn, COUNT(*) AS obs_no_disc_in_window, COUNT(DISTINCT n.obj) AS objects
FROM neo_obs n
JOIN targets t ON t.stn = n.stn
LEFT JOIN disc d USING (obj)
WHERE d.disc_time IS NULL
  AND n.obstime >= :'t0'::timestamp AND n.obstime < :'t1'::timestamp
GROUP BY n.stn ORDER BY n.stn;
