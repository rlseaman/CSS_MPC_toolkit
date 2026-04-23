-- bench_20m.sql
--
-- Synthetic 20M-row PostgreSQL engine benchmark, reproducing the suite
-- in ~/Claude/mpc_sbn/baseline_2026-04-18.md on the Mac mini (now Gizmo).
-- Builds 5 indexes (int_val, ts, float_val, text_val, composite ts+float_val),
-- measures sequential scans, indexed reads, writes, index creation, and
-- advanced query shapes (hash join, correlated subquery, window, CTE).
--
-- Expected runtime: ~20-30 min on Gizmo NVMe (baseline's 12:56 for bulk
-- INSERT 1M on empty-DB HDD should be dramatically faster on NVMe).
--
-- Usage (run in background — long):
--   nohup psql -h <host> -U <user> -d postgres \
--        -f sql/benchmarks/bench_20m.sql \
--        > logs/bench_20m_<host>_<date>.log 2>&1 &
--
-- Creates and drops its own schema `bench_20m` — does not touch real data.

\timing on
\pset border 2

\echo
\echo '#############################################'
\echo '# 20M-row benchmark — setup'
\echo '#############################################'

DROP SCHEMA IF EXISTS bench_20m CASCADE;
CREATE SCHEMA bench_20m;

SET search_path = bench_20m;
SET maintenance_work_mem = '2GB';

CREATE TABLE t (
  id        SERIAL PRIMARY KEY,
  int_val   INTEGER,
  float_val DOUBLE PRECISION,
  text_val  TEXT,
  ts        TIMESTAMP
);

\echo '--- Load 20M rows (ts spans 5.5 years, ~66 months) ---'
INSERT INTO t (int_val, float_val, text_val, ts)
SELECT (random() * 10000000)::int,                        -- wide cardinality for COUNT DISTINCT
       random() * 1000.0,
       md5(random()::text),
       '2019-07-01'::timestamp
         + (random() * 5.5 * 365 * 86400)::int * interval '1 second'
FROM generate_series(1, 20000000);

\echo '--- Table size (pre-index) ---'
SELECT pg_size_pretty(pg_relation_size('t')) AS heap,
       pg_size_pretty(pg_total_relation_size('t')) AS total;

\echo '--- VACUUM ANALYZE (baseline state) ---'
VACUUM ANALYZE t;

\echo
\echo '#############################################'
\echo '# A. Sequential scan benchmarks (no secondary indexes)'
\echo '#############################################'

\echo '--- A1: Full table aggregate (count, avg, stddev, min, max) ---'
SELECT count(*), avg(int_val), stddev(float_val), min(ts), max(ts) FROM t;

\echo '--- A2: Filtered seq scan (10% selectivity, ~2M rows) ---'
SELECT count(*) FROM t WHERE int_val < 1000000;

\echo '--- A3: Filtered seq scan (1% selectivity, ~200K rows) ---'
SELECT count(*) FROM t WHERE int_val < 100000;

\echo '--- A4: COUNT DISTINCT (int_val, high cardinality) ---'
SELECT count(DISTINCT int_val) FROM t;

\echo '--- A5: GROUP BY month aggregation (~66 groups) ---'
SELECT date_trunc('month', ts) AS mo, count(*), avg(float_val)
FROM t GROUP BY mo ORDER BY mo;

\echo '--- A6: GROUP BY high cardinality (top 20 by freq) ---'
SELECT int_val, count(*)
FROM t GROUP BY int_val ORDER BY count(*) DESC LIMIT 20;

\echo '--- A7: Sort + LIMIT 100 (ORDER BY float_val DESC) ---'
SELECT id, float_val FROM t ORDER BY float_val DESC LIMIT 100;

\echo '--- A8: Percentiles (25/50/75/95/99) ---'
SELECT percentile_disc(0.25) WITHIN GROUP (ORDER BY float_val),
       percentile_disc(0.50) WITHIN GROUP (ORDER BY float_val),
       percentile_disc(0.75) WITHIN GROUP (ORDER BY float_val),
       percentile_disc(0.95) WITHIN GROUP (ORDER BY float_val),
       percentile_disc(0.99) WITHIN GROUP (ORDER BY float_val)
FROM t;

\echo
\echo '#############################################'
\echo '# B. Index creation benchmarks'
\echo '#############################################'

\echo '--- B1: B-tree on int_val (INTEGER) ---'
CREATE INDEX t_int_val_idx ON t (int_val);

\echo '--- B2: B-tree on ts (TIMESTAMP) ---'
CREATE INDEX t_ts_idx ON t (ts);

\echo '--- B3: B-tree on float_val (DOUBLE PRECISION) ---'
CREATE INDEX t_float_val_idx ON t (float_val);

\echo '--- B4: B-tree on text_val (TEXT, md5) ---'
CREATE INDEX t_text_val_idx ON t (text_val);

\echo '--- B5: B-tree composite (ts, float_val) ---'
CREATE INDEX t_ts_float_idx ON t (ts, float_val);

ANALYZE t;

\echo '--- Size summary (heap, indexes, total) ---'
SELECT pg_size_pretty(pg_relation_size('t'))                                 AS heap,
       pg_size_pretty(pg_indexes_size('t'))                                  AS indexes,
       pg_size_pretty(pg_total_relation_size('t'))                           AS total;

\echo
\echo '#############################################'
\echo '# C. Indexed read benchmarks'
\echo '#############################################'

\echo '--- C1: Point lookup (int_val = 5000000, LIMIT 1) ---'
SELECT * FROM t WHERE int_val = 5000000 LIMIT 1;

\echo '--- C2: Narrow index range (~23 rows expected) ---'
SELECT count(*) FROM t WHERE int_val BETWEEN 5000000 AND 5000010;

\echo '--- C3: Medium index range (~2K rows expected) ---'
SELECT count(*) FROM t WHERE int_val BETWEEN 5000000 AND 5001000;

\echo '--- C4: Wide index range (~200K rows expected) ---'
SELECT count(*) FROM t WHERE int_val BETWEEN 5000000 AND 5100000;

\echo '--- C5: Timestamp range, 1 month (~290K rows) with avg() ---'
SELECT avg(float_val) FROM t WHERE ts >= '2022-06-01' AND ts < '2022-07-01';

\echo '--- C6: Timestamp range, 1 day (~10K rows) ---'
SELECT count(*) FROM t WHERE ts >= '2022-06-15' AND ts < '2022-06-16';

\echo '--- C7: Composite index (year + float filter, ~36K rows) ---'
SELECT count(*) FROM t
WHERE ts >= '2022-01-01' AND ts < '2023-01-01'
  AND float_val > 999;

\echo '--- C8: Index-only scan (float_val > 999.99, ~200 rows) ---'
SELECT count(float_val) FROM t WHERE float_val > 999.99;

\echo '--- C9: Text equality lookup (md5 hash) ---'
SELECT count(*) FROM t WHERE text_val = (SELECT text_val FROM t LIMIT 1);

\echo
\echo '#############################################'
\echo '# D. Advanced query benchmarks'
\echo '#############################################'

\echo '--- D1: Hash self-join (100K x 20M on int_val) ---'
SELECT count(*) FROM t a JOIN t b USING (int_val) WHERE a.id < 100000;

\echo '--- D2: Correlated subquery (100K rows, avg per int_val group) ---'
SELECT avg(sub.g_avg) FROM (
  SELECT (SELECT avg(float_val) FROM t b WHERE b.int_val = a.int_val) AS g_avg
  FROM t a WHERE a.id < 100000
) sub;

\echo '--- D3: Window function (row_number partitioned by month, 1 year) ---'
SELECT count(*) FROM (
  SELECT id, row_number() OVER (PARTITION BY date_trunc('month', ts) ORDER BY float_val DESC) AS rn
  FROM t WHERE ts >= '2022-01-01' AND ts < '2023-01-01'
) w WHERE rn <= 10;

\echo '--- D4: CTE with monthly aggregation + lag() ---'
WITH monthly AS (
  SELECT date_trunc('month', ts) AS mo,
         count(*)        AS n,
         avg(float_val)  AS mean
  FROM t GROUP BY mo
)
SELECT mo, n, mean,
       lag(mean) OVER (ORDER BY mo) AS prev_mean,
       mean - lag(mean) OVER (ORDER BY mo) AS delta
FROM monthly ORDER BY mo;

\echo
\echo '#############################################'
\echo '# E. Write benchmarks (destructive — run last)'
\echo '#############################################'

\echo '--- E1: Bulk INSERT 1M rows ---'
INSERT INTO t (int_val, float_val, text_val, ts)
SELECT (random() * 10000000)::int,
       random() * 1000.0,
       md5(random()::text),
       '2019-07-01'::timestamp
         + (random() * 5.5 * 365 * 86400)::int * interval '1 second'
FROM generate_series(1, 1000000);

\echo '--- E2: UPDATE 1M rows (indexed col int_val) ---'
UPDATE t SET int_val = int_val + 1 WHERE id <= 1000000;

\echo '--- E3: UPDATE 1M rows (non-indexed col — wait, float_val IS indexed) ---'
\echo '--- E3: UPDATE 1M rows (indexed col float_val) ---'
UPDATE t SET float_val = float_val + 0.001 WHERE id > 1000000 AND id <= 2000000;

\echo '--- E4: DELETE 1M rows ---'
DELETE FROM t WHERE id <= 1000000;

\echo '--- E5: VACUUM ANALYZE (post-churn) ---'
VACUUM ANALYZE t;

\echo
\echo '--- Final size summary ---'
SELECT pg_size_pretty(pg_relation_size('t'))        AS heap,
       pg_size_pretty(pg_indexes_size('t'))         AS indexes,
       pg_size_pretty(pg_total_relation_size('t'))  AS total;

\echo
\echo '#############################################'
\echo '# Teardown'
\echo '#############################################'

DROP SCHEMA bench_20m CASCADE;

\echo
\echo '=== bench_20m complete ==='
