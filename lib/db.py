"""
Database connection manager and query performance instrumentation.

Provides a context-managed connection to the MPC/SBN PostgreSQL database,
timed query execution returning pandas DataFrames, and EXPLAIN ANALYZE
wrappers for profiling.  Uses ~/.pgpass for credentials.

Usage:
    from lib.db import connect, timed_query

    with connect() as conn:
        df = timed_query(conn, "SELECT q, e, i FROM mpc_orbits WHERE orbit_type_int = %s", [2])
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import pandas as pd
import psycopg2
import psycopg2.extras


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@contextmanager
def connect(host="sibyl", dbname="mpc_sbn", user="claude_ro"):
    """
    Context manager for a read-only database connection.

    Uses ~/.pgpass for password lookup.  Sets the connection to readonly
    mode to prevent accidental writes.

    Parameters
    ----------
    host : str
        Database server hostname.
    dbname : str
        Database name.
    user : str
        Database role (should be read-only).

    Yields
    ------
    psycopg2.connection
    """
    conn = psycopg2.connect(host=host, dbname=dbname, user=user)
    conn.set_session(readonly=True, autocommit=False)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Query log
# ---------------------------------------------------------------------------

@dataclass
class QueryRecord:
    label: str
    sql: str
    elapsed_sec: float
    row_count: int
    params: tuple = None


class QueryLog:
    """Accumulates query timing records for analysis."""

    def __init__(self):
        self.records: list[QueryRecord] = []

    def add(self, record: QueryRecord):
        self.records.append(record)

    def to_dataframe(self):
        """Return query log as a DataFrame."""
        return pd.DataFrame([
            {"label": r.label, "elapsed_sec": r.elapsed_sec,
             "row_count": r.row_count, "sql_preview": r.sql[:80]}
            for r in self.records
        ])

    def summary(self):
        """Print a summary table of all logged queries."""
        df = self.to_dataframe()
        if df.empty:
            print("No queries logged.")
            return df
        print(f"{'Label':<40} {'Rows':>10} {'Time (s)':>10}")
        print("-" * 62)
        for _, row in df.iterrows():
            print(f"{row['label']:<40} {row['row_count']:>10,} {row['elapsed_sec']:>10.3f}")
        return df

    def clear(self):
        self.records.clear()


# Module-level log instance — shared across all queries in a session
query_log = QueryLog()


# ---------------------------------------------------------------------------
# Timed query execution
# ---------------------------------------------------------------------------

def timed_query(conn, sql, params=None, label="query"):
    """
    Execute a SQL query and return results as a pandas DataFrame.

    Logs elapsed time and row count to the module-level query_log.

    Parameters
    ----------
    conn : psycopg2.connection
        Database connection (from connect()).
    sql : str
        SQL query string with %s placeholders.
    params : list or tuple, optional
        Query parameters.
    label : str
        Human-readable label for the query log.

    Returns
    -------
    pd.DataFrame
        Query results.
    """
    t0 = time.perf_counter()
    cur = conn.cursor()
    cur.execute(sql, params)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    elapsed = time.perf_counter() - t0

    df = pd.DataFrame(rows, columns=columns)
    query_log.add(QueryRecord(
        label=label, sql=sql, elapsed_sec=elapsed,
        row_count=len(df), params=params,
    ))
    return df


def timed_explain(conn, sql, params=None, label="explain"):
    """
    Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) on a query.

    Executes within a rolled-back transaction so no side effects occur
    (important even on a read-only connection for transactional hygiene).

    Parameters
    ----------
    conn : psycopg2.connection
    sql : str
    params : list or tuple, optional
    label : str

    Returns
    -------
    dict
        The JSON execution plan from PostgreSQL.
    """
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"
    t0 = time.perf_counter()
    cur = conn.cursor()
    try:
        cur.execute(explain_sql, params)
        plan = cur.fetchone()[0]  # JSON array with one element
    finally:
        conn.rollback()
        cur.close()
    elapsed = time.perf_counter() - t0

    query_log.add(QueryRecord(
        label=label, sql=sql, elapsed_sec=elapsed,
        row_count=0, params=params,
    ))
    return plan[0] if isinstance(plan, list) else plan
