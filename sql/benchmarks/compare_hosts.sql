-- compare_hosts.sql
--
-- Quiescent-period exact comparison of mpc_sbn replicas. Run identically
-- on two hosts (e.g. Gizmo and Sibyl), diff the output files. All queries
-- are indexed lookups or bounded aggregates — safe on the 536M-row obs_sbn.
--
-- Usage:
--   psql -h <host> -U <user> -d mpc_sbn -f sql/benchmarks/compare_hosts.sql \
--        > compare_<host>_$(date +%Y%m%d_%H%M).txt
--
--   diff compare_gizmo_<date>.txt compare_sibyl_<date>.txt
--
-- Prereqs:
--   - Both subscribers caught up to a common upstream LSN (check
--     pg_stat_subscription.received_lsn = latest_end_lsn and stable).
--   - obs_sbn recently ANALYZEd on both (for accurate planner choices).
--
-- Output format: pipe-delimited, no headers, no footers. Each row begins
-- with a SECTION tag so diffs are easy to scope.

\pset format unaligned
\pset fieldsep '|'
\pset tuples_only on
\pset footer off
\pset pager off

\echo '# compare_hosts.sql — generated' :DBNAME 'on' :HOST 'at'
SELECT 'META', now()::text, current_setting('server_version'), inet_server_addr()::text;

-- ---------------------------------------------------------------
-- Section 1: exact row counts for all 18 replicated tables.
-- count(*) on obs_sbn is ~3–5 min on NVMe, longer on HDD. All other
-- tables are <2M rows — seconds.
-- ---------------------------------------------------------------

SELECT 'COUNT', 'comet_names',                    count(*) FROM public.comet_names                    UNION ALL
SELECT 'COUNT', 'current_identifications',        count(*) FROM public.current_identifications        UNION ALL
SELECT 'COUNT', 'minor_planet_names',             count(*) FROM public.minor_planet_names             UNION ALL
SELECT 'COUNT', 'mpc_orbits',                     count(*) FROM public.mpc_orbits                     UNION ALL
SELECT 'COUNT', 'neocp_els',                      count(*) FROM public.neocp_els                      UNION ALL
SELECT 'COUNT', 'neocp_events',                   count(*) FROM public.neocp_events                   UNION ALL
SELECT 'COUNT', 'neocp_obs',                      count(*) FROM public.neocp_obs                      UNION ALL
SELECT 'COUNT', 'neocp_obs_archive',              count(*) FROM public.neocp_obs_archive              UNION ALL
SELECT 'COUNT', 'neocp_prev_des',                 count(*) FROM public.neocp_prev_des                 UNION ALL
SELECT 'COUNT', 'neocp_var',                      count(*) FROM public.neocp_var                      UNION ALL
SELECT 'COUNT', 'numbered_identifications',       count(*) FROM public.numbered_identifications       UNION ALL
SELECT 'COUNT', 'obs_alterations_corrections',    count(*) FROM public.obs_alterations_corrections    UNION ALL
SELECT 'COUNT', 'obs_alterations_deletions',      count(*) FROM public.obs_alterations_deletions      UNION ALL
SELECT 'COUNT', 'obs_alterations_redesignations', count(*) FROM public.obs_alterations_redesignations UNION ALL
SELECT 'COUNT', 'obs_alterations_unassociations', count(*) FROM public.obs_alterations_unassociations UNION ALL
SELECT 'COUNT', 'obscodes',                       count(*) FROM public.obscodes                       UNION ALL
SELECT 'COUNT', 'primary_objects',                count(*) FROM public.primary_objects                UNION ALL
SELECT 'COUNT', 'obs_sbn',                        count(*) FROM public.obs_sbn;

-- ---------------------------------------------------------------
-- Section 2: column schema for all 18 tables.
-- Catches any type/nullability/default drift between replicas.
-- ---------------------------------------------------------------

SELECT 'COL',
       table_name,
       ordinal_position,
       column_name,
       data_type,
       coalesce(character_maximum_length::text, ''),
       is_nullable,
       coalesce(column_default, '')
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'comet_names', 'current_identifications', 'minor_planet_names',
    'mpc_orbits', 'neocp_els', 'neocp_events', 'neocp_obs',
    'neocp_obs_archive', 'neocp_prev_des', 'neocp_var',
    'numbered_identifications', 'obs_alterations_corrections',
    'obs_alterations_deletions', 'obs_alterations_redesignations',
    'obs_alterations_unassociations', 'obscodes', 'primary_objects',
    'obs_sbn'
  )
ORDER BY table_name, ordinal_position;

-- ---------------------------------------------------------------
-- Section 3: obs_sbn boundary sanity. All indexed lookups — ms.
-- Lets us quickly see how far each replica has advanced and
-- whether the historical range matches.
-- ---------------------------------------------------------------

SELECT 'BOUND', 'obs_sbn.min_obsid',   min(obsid)::text      FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.max_obsid',   max(obsid)::text      FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.min_obstime', min(obstime)::text    FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.max_obstime', max(obstime)::text    FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.min_created', min(created_at)::text FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.max_created', max(created_at)::text FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.min_updated', min(updated_at)::text FROM public.obs_sbn UNION ALL
SELECT 'BOUND', 'obs_sbn.max_updated', max(updated_at)::text FROM public.obs_sbn;

-- ---------------------------------------------------------------
-- Section 4: secondary table boundaries for the big ones —
-- catches lag in the non-obs_sbn subscription as well.
-- ---------------------------------------------------------------

SELECT 'BOUND', 'mpc_orbits.max_updated',
       max(updated_at)::text FROM public.mpc_orbits UNION ALL
SELECT 'BOUND', 'current_identifications.max_updated',
       max(updated_at)::text FROM public.current_identifications UNION ALL
SELECT 'BOUND', 'primary_objects.max_updated',
       max(updated_at)::text FROM public.primary_objects UNION ALL
SELECT 'BOUND', 'numbered_identifications.max_updated',
       max(updated_at)::text FROM public.numbered_identifications;

\echo '# end of compare_hosts.sql'
