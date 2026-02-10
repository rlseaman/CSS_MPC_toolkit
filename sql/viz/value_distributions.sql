-- ==============================================================================
-- SERVER-SIDE HISTOGRAMMING via width_bucket()
-- ==============================================================================
-- Computes histograms on the database server to avoid transferring raw data.
-- Change :col, :nbins, :lo, :hi as needed.  For automatic min/max, use the
-- CTE variant below.
--
-- NOTE: Uses derived a = q/(1-e) for semi-major axis when the flat column
-- is NULL (~57% of rows).  Adjust the column expression for other columns.
--
-- Usage (with psql variables):
--   psql -h sibyl -d mpc_sbn -v col=a -v nbins=100 -v lo=0 -v hi=100 \
--        -f sql/viz/value_distributions.sql
-- ==============================================================================

-- --- Variant 1: Explicit bounds ---

-- SELECT
--     bucket,
--     :lo + (bucket - 1) * (:hi - :lo) / :nbins::double precision AS bin_lo,
--     :lo + bucket * (:hi - :lo) / :nbins::double precision AS bin_hi,
--     COUNT(*) AS count
-- FROM (
--     SELECT width_bucket(
--         COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END),
--         :lo, :hi, :nbins) AS bucket
--     FROM mpc_orbits
--     WHERE COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END) IS NOT NULL
-- ) t
-- WHERE bucket BETWEEN 1 AND :nbins
-- GROUP BY bucket
-- ORDER BY bucket;


-- --- Variant 2: Auto-detect bounds ---
-- Semi-major axis distribution (derived a)

WITH derived AS (
    SELECT COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END) AS a_derived
    FROM mpc_orbits
),
bounds AS (
    SELECT MIN(a_derived) AS lo, MAX(a_derived) AS hi
    FROM derived
    WHERE a_derived IS NOT NULL AND a_derived < 100  -- exclude extreme outliers
),
binned AS (
    SELECT width_bucket(d.a_derived, b.lo, b.hi + 1e-10, 100) AS bucket
    FROM derived d, bounds b
    WHERE d.a_derived IS NOT NULL AND d.a_derived < 100
)
SELECT
    bucket,
    (SELECT lo FROM bounds) + (bucket - 1) * ((SELECT hi - lo FROM bounds)) / 100.0 AS bin_lo,
    (SELECT lo FROM bounds) + bucket * ((SELECT hi - lo FROM bounds)) / 100.0 AS bin_hi,
    COUNT(*) AS count
FROM binned
WHERE bucket BETWEEN 1 AND 100
GROUP BY bucket
ORDER BY bucket;
