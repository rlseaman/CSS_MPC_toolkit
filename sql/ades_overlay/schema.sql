-- ==============================================================================
-- ADES REPROCESSING OVERLAY — schema (PILOT / PROPOSAL)
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-07-02
-- Design:  docs/2026-07-02_ades_overlay_design.md
--
-- A local, CSS-authoritative overlay on top of obs_sbn for reprocessed
-- astrometry that MPC does not ingest as updates (see
-- docs/2026-07-02_ades_resubmission_findings.md). Tracklet-supersession model:
-- reprocessing a tracklet invalidates the ENTIRE original tracklet and
-- substitutes the reprocessed observations wholesale. Queries opt in by
-- selecting v_effective instead of obs_sbn.
--
-- Requires a superuser to install (CREATE SCHEMA/TABLE); SELECT is granted to
-- claude_ro. Never touches obs_sbn or replication. A live pilot (2 tracklets)
-- runs on Gizmo as css_ades_overlay.
--
-- NOTE: pilot schema — column set and the review-queue / bitemporal decisions
-- (see the design doc's "Open decisions") are expected to evolve.
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS css_ades_overlay;

-- ------------------------------------------------------------------------------
-- tracklet: one supersession record per reprocessed tracklet
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_ades_overlay.tracklet (
    overlay_trk_id     text PRIMARY KEY,          -- e.g. '<batch>:<stn>:<new_trksub>'
    source_batch       text NOT NULL,             -- which reprocessing submission
    stn                text NOT NULL,
    new_trksub         text,                      -- reprocessed tracklet id
    op                 text NOT NULL CHECK (op IN ('supersede','add','suppress')),
    original_obsids    text[],                    -- whole invalidated tracklet (obs_sbn.obsid); empty for 'add'
    match_confidence   text,                      -- auto | review | manual (reconciler provenance)
    status             text NOT NULL DEFAULT 'active' CHECK (status IN ('active','rescinded')),
    basis_max_updated  timestamptz,               -- max(obs_sbn.updated_at) of originals at reconcile (drift detection, f)
    created_at         timestamptz NOT NULL DEFAULT now(),
    rescinded_at       timestamptz
);
CREATE INDEX IF NOT EXISTS tracklet_active_idx
    ON css_ades_overlay.tracklet (status) WHERE status = 'active';

-- ------------------------------------------------------------------------------
-- obs: the reprocessed observations (payload for 'supersede' / 'add')
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_ades_overlay.obs (
    overlay_obs_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    overlay_trk_id  text NOT NULL REFERENCES css_ades_overlay.tracklet (overlay_trk_id),
    stn      text, trksub text,
    obstime  timestamp(6),                        -- full ADES precision
    ra       numeric, dec numeric,
    mode     text, astcat text, photcat text,
    mag      numeric, rmsmag numeric, band text,
    rmsra    numeric, rmsdec numeric, rmscorr numeric, rmstime numeric,
    logsnr   numeric, rmsfit numeric, nstars integer
);
CREATE INDEX IF NOT EXISTS obs_trk_idx ON css_ades_overlay.obs (overlay_trk_id);

-- ------------------------------------------------------------------------------
-- v_effective: obs_sbn with active overlays substituted.
--   obs_sbn rows not superseded/suppressed  UNION  active supersede/add payloads.
--   FILTERED access only — never scan unfiltered (540M-row anti-join). src marks
--   provenance; ades_overlaid flags overlay rows.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW css_ades_overlay.v_effective AS
SELECT o.obsid, o.stn, o.trksub, o.provid, o.permid, o.obstime, o.mode,
       o.ra, o.dec, o.rmsra, o.rmsdec, o.rmscorr, o.rmstime, o.astcat,
       o.mag, o.rmsmag, o.band, o.photcat, o.logsnr, o.rmsfit, o.nstars,
       o.disc, 'obs_sbn'::text AS src, false AS ades_overlaid
  FROM obs_sbn o
 WHERE NOT EXISTS (
        SELECT 1 FROM css_ades_overlay.tracklet t
         WHERE t.status = 'active' AND o.obsid = ANY (t.original_obsids))
UNION ALL
SELECT NULL::text AS obsid, ob.stn, ob.trksub, NULL, NULL, ob.obstime, ob.mode,
       ob.ra, ob.dec, ob.rmsra, ob.rmsdec, ob.rmscorr, ob.rmstime, ob.astcat,
       ob.mag, ob.rmsmag, ob.band, ob.photcat, ob.logsnr, ob.rmsfit, ob.nstars,
       NULL, 'overlay'::text AS src, true AS ades_overlaid
  FROM css_ades_overlay.obs ob
  JOIN css_ades_overlay.tracklet t USING (overlay_trk_id)
 WHERE t.status = 'active' AND t.op IN ('supersede','add');

-- Read-only access for the dashboard role.
GRANT USAGE ON SCHEMA css_ades_overlay TO claude_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA css_ades_overlay TO claude_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA css_ades_overlay GRANT SELECT ON TABLES TO claude_ro;
