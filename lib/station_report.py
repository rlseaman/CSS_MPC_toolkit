"""
Per-site rollups of obs / tracklets / discoveries from obs_sbn.

Loads `sql/station_report.sql`, parameterizes it on (site, date_start,
date_end), and returns a DataFrame ready for the Station Report tab.
Splits NEO vs. non-NEO at the *object* level using
classify_orbit_label(q, e, i) on current mpc_orbits — deliberately
not on orbit_type_int, which is NULL for ~35% of rows.

Performance note: the underlying SQL takes ~2-3 minutes per active
site (V00 ≈ 2:30; F51, G96 will be longer because they have ~10×
more rows in obs_sbn).  We cache results to disk (parquet) keyed on
(site, date_start, date_end) so repeated dashboard requests are
instant.  Cache is force-rebuildable via refresh=True.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pandas as pd

from lib.db import connect, timed_query


_SQL_PATH = Path(__file__).parent.parent / "sql" / "station_report.sql"
_CACHE_DIR = Path(__file__).parent.parent / "app" / ".station_cache"
_CACHE_TTL_SECONDS = 24 * 3600  # rebuild if older than a day


def _load_sql() -> str:
    return _SQL_PATH.read_text()


def _cache_path(site: str, date_start: Optional[str],
                date_end: Optional[str]) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{site}_{date_start or 'any'}_{date_end or 'any'}"
    return _CACHE_DIR / f"station_{key}.parquet"


def fetch_station_report(
    site: str,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Pull per-(year × is_neo × orbit_class) rollup for `site`.

    Returns a DataFrame with columns:
        obs_year, is_neo, orbit_class,
        obs_count, tracklet_count, object_count,
        discovery_obs, discovery_objects.

    Caches to a parquet file under app/.station_cache/.  The cache
    is reused if younger than 24 h; pass refresh=True to force a
    re-query.  Date filters narrow obstime; pass None to span all.
    """
    site = site.strip().upper()
    cache = _cache_path(site, date_start, date_end)

    if not refresh and cache.exists():
        age = time.time() - cache.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return pd.read_parquet(cache)

    sql = _load_sql()
    params = {
        "site": site,
        "date_start": date_start,
        "date_end": date_end,
    }
    with connect() as conn:
        df = timed_query(conn, sql, params,
                         label=f"station_report[{site}]")

    df.to_parquet(cache, index=False)
    return df


def split_neo_non_neo(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the rollup into a NEO table and a non-NEO + Unclassified
    table.  Unclassified objects (no orbit in mpc_orbits — typically
    NEOCP candidates) ride in the non-NEO table for now."""
    neo = df[df["is_neo"]].copy()
    non_neo = df[~df["is_neo"]].copy()
    return neo, non_neo


def summarize(df: pd.DataFrame) -> dict:
    """Compute headline totals for a rollup DataFrame.

    Note: tracklet_count and object_count are DISTINCT *per bucket* in
    the SQL output, so summing them here over-counts an object that
    appears in multiple year/class buckets.  Use these as
    order-of-magnitude indicators only; the obs_count and
    discovery_obs sums are exact.
    """
    if df.empty:
        return {"obs_count": 0, "tracklet_count_approx": 0,
                "object_count_approx": 0, "discovery_obs": 0,
                "discovery_objects_approx": 0,
                "year_min": None, "year_max": None}
    return {
        "obs_count":                int(df["obs_count"].sum()),
        "tracklet_count_approx":    int(df["tracklet_count"].sum()),
        "object_count_approx":      int(df["object_count"].sum()),
        "discovery_obs":            int(df["discovery_obs"].sum()),
        "discovery_objects_approx": int(df["discovery_objects"].sum()),
        "year_min":                 int(df["obs_year"].min()),
        "year_max":                 int(df["obs_year"].max()),
    }
