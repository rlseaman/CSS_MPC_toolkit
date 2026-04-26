"""CNEOS NEO source ingestor (JPL SBDB → css_neo_consensus.source_membership).

CNEOS (the JPL Center for Near Earth Object Studies) treats the JPL
Small-Body Database (SBDB) as its authoritative registry. Its NEO list
is therefore the SBDB bulk query filtered to NEO orbit classes:

  IEO  Atira (Inner Earth Object)
  ATE  Aten
  APO  Apollo
  AMO  Amor

This source covers asteroids only — CNEOS's near-Earth comet list is
separate and not included here (NEC support is deferred for v1).

Source identifier in `source_membership.source`: ``'cneos'``.

The bulk query returns each object's primary designation (``pdes``):
the integer permid as a string for numbered objects, or the unpacked
primary provisional for unnumbered objects. Both forms are handled by
:func:`lib.neo_consensus.canonicalize`.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Tuple
import json
import os
import time
import urllib.parse
import urllib.request

from .neo_consensus import (
    Canonical,
    begin_run,
    canonicalize,
    finish_run,
    upsert_membership,
)

SOURCE = "cneos"
SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
SBDB_NEO_CLASSES = "IEO,ATE,APO,AMO"
USER_AGENT = "CSS_MPC_toolkit/1.0 (consensus ingest)"

_CACHE_FILE = ".cneos_neo_list.json"
_CACHE_MAX_AGE_SEC = 21600  # 6 h — SBDB updates often, but not by the minute


def _download_cneos_list(cache_dir: str) -> str:
    """Fetch the SBDB NEO list and cache the JSON to disk.

    Returns the path to the cached file. Re-uses an existing cache if it
    is younger than ``_CACHE_MAX_AGE_SEC``.
    """
    path = os.path.join(cache_dir, _CACHE_FILE)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SEC:
            return path

    params = urllib.parse.urlencode({
        "fields": "pdes",
        "sb-class": SBDB_NEO_CLASSES,
    })
    url = f"{SBDB_URL}?{params}"
    print(f"Fetching CNEOS NEO list from SBDB ({SBDB_NEO_CLASSES})...")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    print(f"Saved CNEOS list ({len(data) / 1024:.1f} KB)")
    return path


def _parse_cneos_list(path: str) -> List[str]:
    """Return the list of pdes strings from the cached SBDB JSON."""
    with open(path) as f:
        data = json.load(f)
    pdes_idx = data["fields"].index("pdes")
    return [row[pdes_idx] for row in data["data"] if row[pdes_idx]]


def ingest_cneos(conn, cache_dir: str) -> Tuple[int, int]:
    """Ingest the CNEOS NEO list via JPL SBDB bulk query.

    Args:
        conn: psycopg2 write-capable connection to mpc_sbn.
        cache_dir: directory in which to cache the SBDB JSON download.

    Returns:
        ``(n_upserted, n_unresolved)``.

    Same transactional shape as :func:`lib.neo_consensus_mpc.ingest_mpc`:
    run row written and committed up front; membership upsert committed
    atomically; run row terminal status committed last; rollback on any
    exception.
    """
    started_at = begin_run(conn, SOURCE)
    try:
        path = _download_cneos_list(cache_dir)
        raw_designations = _parse_cneos_list(path)
        print(f"Parsed {len(raw_designations):,} CNEOS designations")

        canonicals: List[Canonical] = []
        n_unresolved = 0
        for raw in raw_designations:
            c = canonicalize(raw, conn)
            if c is None:
                n_unresolved += 1
                continue
            canonicals.append(c)

        now = datetime.now(tz=timezone.utc)
        n_upserted = upsert_membership(conn, SOURCE, canonicals, now=now)
        conn.commit()

        finish_run(
            conn, SOURCE, started_at, status="ok",
            n_rows=n_upserted, n_unresolved=n_unresolved,
        )
        conn.commit()
        return n_upserted, n_unresolved
    except Exception as e:
        conn.rollback()
        finish_run(
            conn, SOURCE, started_at, status="fail",
            error=f"{type(e).__name__}: {e}",
        )
        conn.commit()
        raise
