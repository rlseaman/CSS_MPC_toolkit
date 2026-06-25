-- ==============================================================================
-- DAILY ORBIT NEWS — schema (SKETCH / PROPOSAL)
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-25
-- Design:  docs/2026-06-25_daily_orbit_news_design.md
--
-- Two tables in a new css_orbit_watch schema:
--   orbit_snapshot  per-(object, day) element state of the watch set
--                   (q <= 1.5 watch set; ~50 K rows/day; prune to a rolling
--                   window -- orbit_event is the durable record)
--   orbit_event     append-only log of boundary crossings / revisions; this is
--                   both the daily news feed and the longitudinal churn record
--
-- NOTE: requires a superuser (creates schema + tables). The nightly capture
-- (capture_snapshot.sql) and diff (daily_diff.sql) then run as the owner; the
-- read-only dashboard role only needs SELECT, granted at the bottom.
-- This is a sketch -- column set and thresholds are expected to change once
-- it has run against real output.
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS css_orbit_watch;

-- ------------------------------------------------------------------------------
-- Daily element snapshot of the watch set
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_orbit_watch.orbit_snapshot (
    snapshot_date   date        NOT NULL,
    primary_desig   text        NOT NULL,   -- unpacked primary provisional
    permid          text,                   -- numbered designation, if any
    disc_by         text,                   -- discovery obscode (from obs_summary)
    -- elements (top-level mpc_orbits, q reliable; a derived when KEP absent)
    q               double precision,
    e               double precision,
    i               double precision,
    a               double precision,       -- COALESCE(a, q/(1-e)) at capture
    earth_moid      double precision,
    h               double precision,
    u_param         text,
    nobs_total      integer,
    -- derived classification (element-based, NOT scattershot orbit_type_int)
    is_neo          boolean,                 -- q <= 1.3
    is_pha          boolean,                 -- earth_moid <= 0.05 AND h <= 22
    neo_subclass    text,                    -- Atira/Aten/Apollo/Amor or NULL
    src_updated_at  timestamptz,             -- mpc_orbits.updated_at at capture
    PRIMARY KEY (snapshot_date, primary_desig)
);

CREATE INDEX IF NOT EXISTS orbit_snapshot_desig_idx
    ON css_orbit_watch.orbit_snapshot (primary_desig, snapshot_date);

-- ------------------------------------------------------------------------------
-- Append-only event log (the "news feed" + longitudinal churn record)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_orbit_watch.orbit_event (
    event_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_date      date        NOT NULL,    -- diff date (= newer snapshot_date)
    primary_desig   text        NOT NULL,
    permid          text,
    disc_by         text,
    event_type      text        NOT NULL,    -- NEO_ENTER, PHA_EXIT, H_REVISION, ...
    prev_date       date,                    -- older snapshot_date compared
    -- before/after values (only the relevant ones populated per event_type)
    prev_q          double precision,  new_q          double precision,
    prev_a          double precision,  new_a          double precision,
    prev_e          double precision,  new_e          double precision,
    prev_moid       double precision,  new_moid       double precision,
    prev_h          double precision,  new_h          double precision,
    prev_subclass   text,              new_subclass   text,
    detail          text                     -- free-text summary for display
);

CREATE INDEX IF NOT EXISTS orbit_event_date_idx  ON css_orbit_watch.orbit_event (event_date);
CREATE INDEX IF NOT EXISTS orbit_event_desig_idx ON css_orbit_watch.orbit_event (primary_desig);
CREATE INDEX IF NOT EXISTS orbit_event_type_idx  ON css_orbit_watch.orbit_event (event_type, event_date);

-- Read-only dashboard access
GRANT USAGE ON SCHEMA css_orbit_watch TO claude_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA css_orbit_watch TO claude_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA css_orbit_watch GRANT SELECT ON TABLES TO claude_ro;
