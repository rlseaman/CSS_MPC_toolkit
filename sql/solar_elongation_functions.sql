-- ==============================================================================
-- SOLAR ELONGATION HISTOGRAM - FUNCTION VERSION (OPTIMIZED)
-- ==============================================================================
-- Creates a reusable function for generating solar elongation histograms
-- OPTIMIZATION: Pre-computes Sun position once per day instead of per-observation
--
-- SIGNED ELONGATION: +ve = East of Sun (evening), -ve = West (morning)
-- ==============================================================================

-- Drop existing functions if they exist
DROP FUNCTION IF EXISTS solar_elongation_histogram(text, date, date, numeric);
DROP FUNCTION IF EXISTS solar_elongation_stats(text, date, date);

-- Create the histogram function
CREATE OR REPLACE FUNCTION solar_elongation_histogram(
    p_station text DEFAULT 'G96',
    p_start_date date DEFAULT '2020-01-01',
    p_end_date date DEFAULT '2025-12-31',
    p_bin_width numeric DEFAULT 5
)
RETURNS TABLE (
    bin_label text,
    "N_obs" bigint,
    "bin %" numeric,
    "cumm. %" numeric
)
LANGUAGE SQL
STABLE
AS $$
WITH 
-- Pre-compute Sun RA/Dec once per day
sun_positions AS (
    SELECT
        d::date as obs_date,
        ((DEGREES(ATAN2(
            COS(RADIANS(23.439 - 0.013 * T)) * SIN(RADIANS(L)),
            COS(RADIANS(L))
        ))::numeric % 360) + 360)::numeric % 360 as sun_ra,
        DEGREES(ASIN(SIN(RADIANS(23.439 - 0.013 * T)) * SIN(RADIANS(L)))) as sun_dec
    FROM (
        SELECT 
            d::date as d,
            (d::date - DATE '2000-01-01')::double precision / 36525.0 as T,
            ((280.466 + 36000.77 * (d::date - DATE '2000-01-01')::double precision / 36525.0
              + 1.915 * SIN(RADIANS((357.529 + 35999.05 * (d::date - DATE '2000-01-01')::double precision / 36525.0)::numeric % 360))
             )::numeric % 360 + 360)::numeric % 360 as L
        FROM generate_series(p_start_date, p_end_date, '1 day'::interval) d
    ) sc
),

-- Calculate signed elongation and aggregate in single pass  
histogram AS (
    SELECT 
        FLOOR(
            CASE 
                WHEN ((obs.ra - sp.sun_ra + 360)::numeric % 360) <= 180 THEN 1
                ELSE -1
            END *
            DEGREES(ACOS(
                GREATEST(-1::double precision, LEAST(1::double precision,
                    SIN(RADIANS(obs.dec)) * SIN(RADIANS(sp.sun_dec))
                    + COS(RADIANS(obs.dec)) * COS(RADIANS(sp.sun_dec))
                      * COS(RADIANS(obs.ra - sp.sun_ra))
                ))
            )) / p_bin_width
        )::integer as bin_num,
        COUNT(*) as n_obs
    FROM obs_sbn obs
    INNER JOIN sun_positions sp ON sp.obs_date = obs.obstime::date
    WHERE obs.stn = p_station
      AND obs.obstime >= p_start_date
      AND obs.obstime < p_end_date + INTERVAL '1 day'
      AND obs.ra IS NOT NULL
      AND obs.dec IS NOT NULL
    GROUP BY 1
),

with_pct AS (
    SELECT
        bin_num,
        n_obs,
        ROUND(100.0 * n_obs / SUM(n_obs) OVER (), 2) as bin_pct
    FROM histogram
)

SELECT
    CASE 
        WHEN w.bin_num >= 0 THEN
            LPAD((w.bin_num * p_bin_width)::integer::text, 4, ' ') || '° to ' ||
            LPAD(((w.bin_num + 1) * p_bin_width)::integer::text, 4, ' ') || '° E'
        ELSE
            LPAD(((w.bin_num + 1) * p_bin_width * -1)::integer::text, 4, ' ') || '° to ' ||
            LPAD((w.bin_num * p_bin_width * -1)::integer::text, 4, ' ') || '° W'
    END as bin_label,
    w.n_obs as "N_obs",
    w.bin_pct as "bin %",
    ROUND(SUM(w.bin_pct) OVER (ORDER BY w.bin_num), 2) as "cumm. %"
FROM with_pct w
ORDER BY w.bin_num;
$$;

-- ==============================================================================
-- USAGE EXAMPLES
-- ==============================================================================

-- Example 1: Default parameters (G96, 2020-2025, 5° bins)
-- SELECT * FROM solar_elongation_histogram();

-- Example 2: Pan-STARRS 1, 2021 only, 10° bins  
-- SELECT * FROM solar_elongation_histogram('F51', '2021-01-01', '2021-12-31', 10);

-- Example 3: Catalina Sky Survey, 2020-2023, 2° bins
-- SELECT * FROM solar_elongation_histogram('703', '2020-01-01', '2023-12-31', 2);

-- Example 4: Get stats with east/west counts
-- SELECT * FROM solar_elongation_stats('G96', '2020-01-01', '2025-12-31');

-- ==============================================================================
-- DOCUMENTATION  
-- ==============================================================================

/*
SIGNED ELONGATION CONVENTION:
  Positive (+) / "E": Object is EAST of the Sun (evening sky)
  Negative (-) / "W": Object is WEST of the Sun (morning sky)

  0° = Conjunction (object near the Sun)
  ±180° = Opposition (object opposite the Sun)

The stats function returns east_count and west_count for quick asymmetry check.
*/

-- ==============================================================================
-- ADDITIONAL UTILITY FUNCTION: Summary Statistics
-- ==============================================================================

CREATE OR REPLACE FUNCTION solar_elongation_stats(
    p_station text DEFAULT 'G96',
    p_start_date date DEFAULT '2020-01-01',
    p_end_date date DEFAULT '2025-12-31'
)
RETURNS TABLE (
    station_code text,
    start_date date,
    end_date date,
    total_observations bigint,
    min_signed_elong numeric,
    max_signed_elong numeric,
    mean_signed_elong numeric,
    median_signed_elong numeric,
    east_count bigint,
    west_count bigint
)
LANGUAGE SQL
STABLE
AS $$
WITH 
date_series AS (
    SELECT generate_series(p_start_date, p_end_date, '1 day'::interval)::date as obs_date
),
sun_daily AS (
    SELECT 
        d.obs_date,
        (d.obs_date - DATE '2000-01-01')::double precision / 36525.0 as T
    FROM date_series d
),
sun_coords AS (
    SELECT 
        sd.obs_date,
        (280.46646 + 36000.76983 * sd.T)::numeric % 360 as L0,
        (357.52911 + 35999.05029 * sd.T)::numeric % 360 as M,
        23.439291 - 0.0130042 * sd.T as obliquity,
        sd.T
    FROM sun_daily sd
),
sun_radec AS (
    SELECT
        sc.obs_date,
        sc.obliquity,
        sc.L0,
        (1.914602 - 0.004817 * sc.T) * SIN(RADIANS(sc.M))
        + 0.019993 * SIN(RADIANS(2 * sc.M)) as eqn_center
    FROM sun_coords sc
),
sun_positions AS (
    SELECT
        sr.obs_date,
        ((DEGREES(ATAN2(
            COS(RADIANS(sr.obliquity)) * SIN(RADIANS((sr.L0 + sr.eqn_center)::numeric % 360 + 360)),
            COS(RADIANS((sr.L0 + sr.eqn_center)::numeric % 360 + 360))
        ))::numeric % 360) + 360)::numeric % 360 as sun_ra,
        DEGREES(ASIN(
            SIN(RADIANS(sr.obliquity)) * SIN(RADIANS((sr.L0 + sr.eqn_center)::numeric % 360 + 360))
        )) as sun_dec
    FROM sun_radec sr
),
elongation_calc AS (
    SELECT
        CASE 
            WHEN ((obs.ra - sp.sun_ra + 360)::numeric % 360) <= 180 THEN 1 
            ELSE -1
        END *
        DEGREES(ACOS(
            GREATEST(-1::double precision, LEAST(1::double precision,
                SIN(RADIANS(obs.dec)) * SIN(RADIANS(sp.sun_dec))
                + COS(RADIANS(obs.dec)) * COS(RADIANS(sp.sun_dec))
                  * COS(RADIANS(obs.ra - sp.sun_ra))
            ))
        )) as signed_elongation
    FROM obs_sbn obs
    INNER JOIN sun_positions sp ON sp.obs_date = obs.obstime::date
    WHERE obs.stn = p_station
      AND obs.obstime >= p_start_date
      AND obs.obstime < p_end_date + INTERVAL '1 day'
      AND obs.ra IS NOT NULL
      AND obs.dec IS NOT NULL
)
SELECT
    p_station as station_code,
    p_start_date as start_date,
    p_end_date as end_date,
    COUNT(*) as total_observations,
    ROUND(MIN(signed_elongation)::numeric, 2) as min_signed_elong,
    ROUND(MAX(signed_elongation)::numeric, 2) as max_signed_elong,
    ROUND(AVG(signed_elongation)::numeric, 2) as mean_signed_elong,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY signed_elongation)::numeric, 2) as median_signed_elong,
    COUNT(*) FILTER (WHERE signed_elongation > 0) as east_count,
    COUNT(*) FILTER (WHERE signed_elongation < 0) as west_count
FROM elongation_calc;
$$;

-- ==============================================================================
-- RUN DEFAULT QUERY
-- ==============================================================================

-- Histogram with defaults
SELECT * FROM solar_elongation_histogram();

-- To also get summary statistics, uncomment below (runs query twice):
-- SELECT * FROM solar_elongation_stats();
