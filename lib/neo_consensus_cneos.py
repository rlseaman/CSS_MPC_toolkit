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
from typing import List, Optional, Tuple
import json
import os
import re
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

    # full_name is needed because SBDB strips the "A/" prefix from `pdes`
    # for asteroid-on-cometary-orbit objects (e.g. A/2019 Q2). Without
    # full_name we can't recover the prefix and they fail to canonicalize.
    params = urllib.parse.urlencode({
        "fields": "pdes,full_name",
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


_FULL_NAME_PARENS_RE = re.compile(r"\(([^)]+)\)")


def _extract_from_full_name(full_name: str) -> Optional[str]:
    """Pull the parenthesized designation out of an SBDB ``full_name``.

    SBDB ``full_name`` has shapes like ``"       (A/2019 Q2)"`` or
    ``"      433 Eros (1898 DQ)"``; the parenthesized fragment is the
    primary provisional in MPC syntax (with the ``A/`` prefix preserved
    when it applies).
    """
    if not full_name:
        return None
    m = _FULL_NAME_PARENS_RE.search(full_name)
    return m.group(1).strip() if m else None


def _parse_cneos_list(path: str) -> List[Tuple[str, str]]:
    """Return ``(pdes, full_name)`` tuples from the cached SBDB JSON.

    ``full_name`` may be empty for some rows; ``pdes`` is always present.
    """
    with open(path) as f:
        data = json.load(f)
    pdes_idx = data["fields"].index("pdes")
    fn_idx = data["fields"].index("full_name")
    return [(row[pdes_idx], row[fn_idx] or "")
            for row in data["data"] if row[pdes_idx]]


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
        rows = _parse_cneos_list(path)
        print(f"Parsed {len(rows):,} CNEOS designations")

        canonicals: List[Canonical] = []
        n_unresolved = 0
        n_recovered_via_full_name = 0
        for pdes, full_name in rows:
            c = canonicalize(pdes, conn)
            if c is None:
                # Fallback: SBDB sometimes strips the A/ prefix from pdes
                # for asteroid-on-cometary-orbit objects. The parenthesized
                # part of full_name preserves the prefix.
                alt = _extract_from_full_name(full_name)
                if alt and alt != pdes:
                    c = canonicalize(alt, conn)
                    if c is not None:
                        n_recovered_via_full_name += 1
            if c is None:
                n_unresolved += 1
                continue
            canonicals.append(c)
        if n_recovered_via_full_name:
            print(f"Recovered {n_recovered_via_full_name} via full_name fallback")

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
