-- ==============================================================================
-- STATION NEO FOLLOW-UP PARTITION  (V-magnitude augmented)
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Authors: Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
-- Created: 2026-06-24
--
-- Second version of station_neo_followup.sql. Same per-station discovery /
-- follow-up / precovery partition and the same unique-object / observation /
-- tracklet counts, PLUS four V-magnitude statistics per (station, category):
--   v_min       minimum (brightest) corrected V
--   v_median    median corrected V
--   v_med_mad   median + 1.4826 * MAD   (robust "typical faint" depth proxy)
--   v_p95       95th-percentile corrected V (faint-end depth proxy)
--
-- V CONVERSION: MPC-standard band-to-V offsets from
--   https://minorplanetcenter.net/iau/info/BandConversion.txt
--   (the same CASE used in discovery_tracklets.sql): V_corr = mag + offset(band).
--   Observations with a NULL mag are dropped from the V statistics only (they
--   still count in the unique/obs/tracklet tallies).
--
-- V SAMPLE PER CATEGORY:
--   discoveries -> the discovery-tracklet observations (role='disc_tracklet')
--                  of objects this station discovered in the window
--   follow-up   -> the station's in-window follow-up observations
--   precovery   -> the station's in-window precovery observations
--
-- Everything else (NEA.txt NEO set, permid+provid matching, disc='*' pivot,
-- self-discoveries included, half-open obstime window) is identical to
-- station_neo_followup.sql -- see that file's header for the full rationale.
--
-- RUNTIME: ~10-12 min against the 5.09M-row obs_sbn_neo matview on Gizmo NVMe.
--
-- USAGE:
--   psql -h /tmp -U claude_ro mpc_sbn -f sql/station_neo_followup_vmag.sql
-- ==============================================================================

\timing on

\set t0 '2025-08-01'
\set t1 '2026-06-18'

WITH
targets(stn) AS (VALUES        -- <-- edit the station list here
  ('703'), ('G96'), ('V00'), ('I52'), ('V06')
),
nea_desig AS (
  SELECT md.primary_desig, md.designation, md.kind
  FROM css_neo_consensus.v_member_designations md
  JOIN css_neo_consensus.v_membership_wide w USING (primary_desig)
  WHERE w.in_mpc
),
neo_obs_raw AS (
  SELECT o.obsid, d.primary_desig AS obj, o.stn, o.obstime,
         NULLIF(o.trkid,'') AS trkid, o.disc, o.mag, o.band
  FROM obs_sbn_neo o
  JOIN nea_desig d ON o.provid = d.designation AND d.kind IN ('primary','secondary')
  UNION ALL
  SELECT o.obsid, d.primary_desig, o.stn, o.obstime, NULLIF(o.trkid,''), o.disc, o.mag, o.band
  FROM obs_sbn_neo o
  JOIN nea_desig d ON o.permid = d.designation AND d.kind = 'permid'
),
neo_obs AS (
  SELECT DISTINCT ON (obsid) obsid, obj, stn, obstime, trkid, disc, mag, band
  FROM neo_obs_raw ORDER BY obsid, obj
),
disc AS (
  SELECT DISTINCT ON (obj) obj, stn AS disc_stn, obstime AS disc_time, trkid AS disc_trkid
  FROM neo_obs WHERE disc = '*' ORDER BY obj, obstime
),
tagged AS (
  SELECT n.obj, n.stn, n.obstime,
         COALESCE(n.trkid, n.obsid) AS trk,
         d.disc_stn, d.disc_time,
         CASE
           WHEN d.disc_time IS NULL THEN 'unknown_disc'
           WHEN n.trkid IS NOT NULL AND n.trkid = d.disc_trkid THEN 'disc_tracklet'
           WHEN n.obstime < d.disc_time THEN 'precovery'
           WHEN n.obstime > d.disc_time THEN 'followup'
           ELSE 'disc_tracklet'
         END AS role,
         -- MPC-standard band-to-V correction (BandConversion.txt)
         CASE WHEN n.mag IS NULL THEN NULL ELSE
           n.mag + CASE n.band
             WHEN 'V' THEN 0.0   WHEN 'v' THEN 0.0
             WHEN 'B' THEN -0.8  WHEN 'U' THEN -1.3
             WHEN 'R' THEN 0.4   WHEN 'I' THEN 0.8
             WHEN 'g' THEN -0.35 WHEN 'r' THEN 0.14
             WHEN 'i' THEN 0.32  WHEN 'z' THEN 0.26
             WHEN 'y' THEN 0.32  WHEN 'u' THEN 2.5
             WHEN 'w' THEN -0.13 WHEN 'c' THEN -0.05
             WHEN 'o' THEN 0.33  WHEN 'G' THEN 0.28
             WHEN 'J' THEN 1.2   WHEN 'H' THEN 1.4
             WHEN 'K' THEN 1.7   WHEN 'C' THEN 0.4
             WHEN 'W' THEN 0.4   WHEN 'L' THEN 0.2
             WHEN 'Y' THEN 0.7   WHEN '' THEN -0.8
             ELSE 0.0
           END
         END AS v_mag
  FROM neo_obs n LEFT JOIN disc d USING (obj)
),
-- --- counts (identical to station_neo_followup.sql) ---------------------------
counts AS (
  SELECT d.disc_stn AS stn, '1_discoveries' AS category,
         COUNT(DISTINCT d.obj) AS unique_objects,
         NULL::bigint AS observations, NULL::bigint AS tracklets, 1 AS ord
  FROM disc d JOIN targets t ON t.stn = d.disc_stn
  WHERE d.disc_time >= :'t0'::timestamp AND d.disc_time < :'t1'::timestamp
  GROUP BY d.disc_stn
  UNION ALL
  SELECT w.stn, '2_followup', COUNT(DISTINCT w.obj), COUNT(*), COUNT(DISTINCT w.trk), 2
  FROM tagged w JOIN targets t ON t.stn = w.stn
  WHERE w.role='followup' AND w.obstime >= :'t0'::timestamp AND w.obstime < :'t1'::timestamp
  GROUP BY w.stn
  UNION ALL
  SELECT w.stn, '3_precovery', COUNT(DISTINCT w.obj), COUNT(*), COUNT(DISTINCT w.trk), 3
  FROM tagged w JOIN targets t ON t.stn = w.stn
  WHERE w.role='precovery' AND w.obstime >= :'t0'::timestamp AND w.obstime < :'t1'::timestamp
  GROUP BY w.stn
),
-- --- V-magnitude sample per (station, category) -------------------------------
bucketed AS (
  SELECT w.stn, '1_discoveries' AS category, w.v_mag
  FROM tagged w JOIN targets t ON t.stn = w.stn
  WHERE w.role='disc_tracklet' AND w.v_mag IS NOT NULL
    AND w.disc_time >= :'t0'::timestamp AND w.disc_time < :'t1'::timestamp
  UNION ALL
  SELECT w.stn, '2_followup', w.v_mag
  FROM tagged w JOIN targets t ON t.stn = w.stn
  WHERE w.role='followup' AND w.v_mag IS NOT NULL
    AND w.obstime >= :'t0'::timestamp AND w.obstime < :'t1'::timestamp
  UNION ALL
  SELECT w.stn, '3_precovery', w.v_mag
  FROM tagged w JOIN targets t ON t.stn = w.stn
  WHERE w.role='precovery' AND w.v_mag IS NOT NULL
    AND w.obstime >= :'t0'::timestamp AND w.obstime < :'t1'::timestamp
),
med AS (   -- group median, needed for the MAD second pass
  SELECT stn, category,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY v_mag) AS med_v
  FROM bucketed GROUP BY stn, category
),
dev AS (   -- absolute deviation from the group median
  SELECT b.stn, b.category, b.v_mag, ABS(b.v_mag - m.med_v) AS ad
  FROM bucketed b JOIN med m USING (stn, category)
),
vstats AS (
  SELECT stn, category,
         COUNT(*) AS n_mag,
         ROUND(MIN(v_mag)::numeric, 2) AS v_min,
         ROUND((percentile_cont(0.5)  WITHIN GROUP (ORDER BY v_mag))::numeric, 2) AS v_median,
         ROUND((percentile_cont(0.5)  WITHIN GROUP (ORDER BY v_mag)
                + 1.4826 * percentile_cont(0.5) WITHIN GROUP (ORDER BY ad))::numeric, 2) AS v_med_mad,
         ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY v_mag))::numeric, 2) AS v_p95
  FROM dev GROUP BY stn, category
)
SELECT c.stn, c.category,
       c.unique_objects, c.observations, c.tracklets,
       v.n_mag, v.v_min, v.v_median, v.v_med_mad, v.v_p95
FROM counts c
LEFT JOIN vstats v USING (stn, category)
ORDER BY c.stn, c.ord;
