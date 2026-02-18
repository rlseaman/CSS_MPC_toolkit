-- ==============================================================================
-- NULL RATE SURVEY across mpc_orbits flat columns
-- ==============================================================================
-- Single-pass query using COUNT(*) - COUNT(col) for each column.
-- Returns column_name, total rows, null count, and null percentage.
--
-- Usage:
--   psql -h $PGHOST -d mpc_sbn -f sql/viz/column_nulls.sql
-- ==============================================================================

SELECT 'q' AS column_name, COUNT(*) AS total, COUNT(*) - COUNT(q) AS null_count, ROUND(100.0 * (COUNT(*) - COUNT(q)) / COUNT(*), 2) AS null_pct FROM mpc_orbits
UNION ALL
SELECT 'e', COUNT(*), COUNT(*) - COUNT(e), ROUND(100.0 * (COUNT(*) - COUNT(e)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'i', COUNT(*), COUNT(*) - COUNT(i), ROUND(100.0 * (COUNT(*) - COUNT(i)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'a', COUNT(*), COUNT(*) - COUNT(a), ROUND(100.0 * (COUNT(*) - COUNT(a)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'node', COUNT(*), COUNT(*) - COUNT(node), ROUND(100.0 * (COUNT(*) - COUNT(node)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'argperi', COUNT(*), COUNT(*) - COUNT(argperi), ROUND(100.0 * (COUNT(*) - COUNT(argperi)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'h', COUNT(*), COUNT(*) - COUNT(h), ROUND(100.0 * (COUNT(*) - COUNT(h)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'g', COUNT(*), COUNT(*) - COUNT(g), ROUND(100.0 * (COUNT(*) - COUNT(g)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'epoch_mjd', COUNT(*), COUNT(*) - COUNT(epoch_mjd), ROUND(100.0 * (COUNT(*) - COUNT(epoch_mjd)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'earth_moid', COUNT(*), COUNT(*) - COUNT(earth_moid), ROUND(100.0 * (COUNT(*) - COUNT(earth_moid)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'orbit_type_int', COUNT(*), COUNT(*) - COUNT(orbit_type_int), ROUND(100.0 * (COUNT(*) - COUNT(orbit_type_int)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'u_param', COUNT(*), COUNT(*) - COUNT(u_param), ROUND(100.0 * (COUNT(*) - COUNT(u_param)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'nopp', COUNT(*), COUNT(*) - COUNT(nopp), ROUND(100.0 * (COUNT(*) - COUNT(nopp)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'nobs_total', COUNT(*), COUNT(*) - COUNT(nobs_total), ROUND(100.0 * (COUNT(*) - COUNT(nobs_total)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'q_unc', COUNT(*), COUNT(*) - COUNT(q_unc), ROUND(100.0 * (COUNT(*) - COUNT(q_unc)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'e_unc', COUNT(*), COUNT(*) - COUNT(e_unc), ROUND(100.0 * (COUNT(*) - COUNT(e_unc)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'i_unc', COUNT(*), COUNT(*) - COUNT(i_unc), ROUND(100.0 * (COUNT(*) - COUNT(i_unc)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'yarkovsky', COUNT(*), COUNT(*) - COUNT(yarkovsky), ROUND(100.0 * (COUNT(*) - COUNT(yarkovsky)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'srp', COUNT(*), COUNT(*) - COUNT(srp), ROUND(100.0 * (COUNT(*) - COUNT(srp)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'fitting_datetime', COUNT(*), COUNT(*) - COUNT(fitting_datetime), ROUND(100.0 * (COUNT(*) - COUNT(fitting_datetime)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'normalized_rms', COUNT(*), COUNT(*) - COUNT(normalized_rms), ROUND(100.0 * (COUNT(*) - COUNT(normalized_rms)) / COUNT(*), 2) FROM mpc_orbits
UNION ALL
SELECT 'arc_length', COUNT(*), COUNT(*) - COUNT(arc_length), ROUND(100.0 * (COUNT(*) - COUNT(arc_length)) / COUNT(*), 2) FROM mpc_orbits
ORDER BY null_pct DESC;
