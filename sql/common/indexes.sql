-- ==============================================================================
-- SHARED INDEX DEFINITIONS
-- ==============================================================================
-- Project: CSS_MPC_toolkit
--
-- Performance indexes on MPC/SBN tables used by multiple scripts in this
-- project.  Safe to run repeatedly (CREATE IF NOT EXISTS).
--
-- These indexes are created on the existing MPC/SBN tables (obs_sbn,
-- mpc_orbits) and do not modify any data.
-- ==============================================================================

-- obs_sbn indexes for discovery matching
CREATE INDEX IF NOT EXISTS idx_obs_sbn_disc ON obs_sbn(disc) WHERE disc = '*';
CREATE INDEX IF NOT EXISTS idx_obs_sbn_provid ON obs_sbn(provid);
CREATE INDEX IF NOT EXISTS idx_obs_sbn_permid ON obs_sbn(permid);
CREATE INDEX IF NOT EXISTS idx_obs_sbn_trksub ON obs_sbn(trksub);
