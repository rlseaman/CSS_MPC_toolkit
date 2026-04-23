-- bench_1m.sql
--
-- Synthetic 1M-row PostgreSQL engine benchmark, reproducing the suite in
-- ~/Claude/mpc_sbn/baseline_2026-04-18.md on the Mac mini. Designed to be
-- run identically against any PG instance for apples-to-apples hardware +
-- config comparison (not a workload benchmark — see sql/benchmarks/bench_20m.sql
-- for the heavier suite once this one is trusted).
--
-- Usage:
--   psql -h <host> -U <user> -d <db> -f sql/benchmarks/bench_1m.sql \
--        2>&1 | tee logs/bench_1m_<host>_<date>.log
--
-- Requires CREATE SCHEMA privilege on target DB (benchmark builds its own
-- schema `bench_1m`, drops it at the end — no interference with real data).

\timing on
\pset border 2

\echo
\echo '#############################################'
\echo '# 1M-row benchmark — setup'
\echo '#############################################'

DROP SCHEMA IF EXISTS bench_1m CASCADE;
CREATE SCHEMA bench_1m;

SET search_path = bench_1m;

CREATE TABLE t (
  id        SERIAL PRIMARY KEY,
  int_val   INTEGER,
  float_val DOUBLE PRECISION,
  text_val  TEXT,
  ts        TIMESTAMP
);

\echo '--- Load 1M rows ---'
INSERT INTO t (int_val, float_val, text_val, ts)
SELECT (random() * 10000)::int,
       random() * 1000.0,
       md5(random()::text),
       '2024-01-01'::timestamp + (random() * 365 * 86400)::int * interval '1 second'
FROM generate_series(1, 1000000);

\echo '--- VACUUM ANALYZE (baseline state) ---'
VACUUM ANALYZE t;

\echo '--- Table size ---'
SELECT pg_size_pretty(pg_relation_size('t')) AS heap,
       pg_size_pretty(pg_total_relation_size('t')) AS total;

\echo
\echo '#############################################'
\echo '# A. Read benchmarks (no secondary indexes)'
\echo '#############################################'

\echo '--- A1: Full table aggregate (count, avg, stddev) ---'
SELECT count(*), avg(int_val), stddev(float_val) FROM t;

\echo '--- A2: Filtered sequential scan (10% selectivity, ~100K rows) ---'
SELECT count(*) FROM t WHERE int_val < 1000;

\echo '--- A3: Sort + LIMIT 100 (ORDER BY float_val DESC, seq scan) ---'
SELECT id, float_val FROM t ORDER BY float_val DESC LIMIT 100;

\echo '--- A4: GROUP BY month aggregation ---'
SELECT date_trunc('month', ts) AS mo, count(*), avg(float_val)
FROM t GROUP BY mo ORDER BY mo;

\echo '--- A5: Hash self-join (10K x 1M on int_val) ---'
SELECT count(*) FROM t a JOIN t b USING (int_val) WHERE a.id < 10000;

\echo
\echo '#############################################'
\echo '# B. Index creation benchmarks'
\echo '#############################################'

\echo '--- B1: B-tree on int_val (INTEGER) ---'
CREATE INDEX t_int_val_idx ON t (int_val);

\echo '--- B2: B-tree on ts (TIMESTAMP) ---'
CREATE INDEX t_ts_idx ON t (ts);

\echo '--- B3: B-tree on text_val (TEXT, md5) ---'
CREATE INDEX t_text_val_idx ON t (text_val);

ANALYZE t;

\echo
\echo '#############################################'
\echo '# C. Indexed read benchmarks'
\echo '#############################################'

\echo '--- C1: Index point lookup (int_val = 5000) ---'
SELECT count(*) FROM t WHERE int_val = 5000;

\echo '--- C2: Narrow index range (int_val BETWEEN 5000 AND 5010) ---'
SELECT count(*) FROM t WHERE int_val BETWEEN 5000 AND 5010;

\echo '--- C3: Timestamp range scan (2024 Q1, ~25% of rows) ---'
SELECT count(*) FROM t WHERE ts >= '2024-01-01' AND ts < '2024-04-01';

\echo '--- C4: Text equality lookup (md5 hash) ---'
SELECT count(*) FROM t WHERE text_val = (SELECT text_val FROM t LIMIT 1);

\echo
\echo '#############################################'
\echo '# D. Write benchmarks (destructive — run last)'
\echo '#############################################'

\echo '--- D1: Bulk INSERT 100K rows ---'
INSERT INTO t (int_val, float_val, text_val, ts)
SELECT (random() * 10000)::int,
       random() * 1000.0,
       md5(random()::text),
       '2024-01-01'::timestamp + (random() * 365 * 86400)::int * interval '1 second'
FROM generate_series(1, 100000);

\echo '--- D2: UPDATE 100K rows (indexed col int_val) ---'
UPDATE t SET int_val = int_val + 1 WHERE id <= 100000;

\echo '--- D3: DELETE 100K rows ---'
DELETE FROM t WHERE id <= 100000;

\echo '--- D4: VACUUM ANALYZE (post-churn) ---'
VACUUM ANALYZE t;

\echo
\echo '#############################################'
\echo '# Teardown'
\echo '#############################################'

DROP SCHEMA bench_1m CASCADE;

\echo
\echo '=== bench_1m complete ==='
