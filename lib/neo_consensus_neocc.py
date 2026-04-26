"""NEOCC NEO source ingestor (ESA allneo.lst → css_neo_consensus).

NEOCC (the European Space Agency's Near Earth Object Coordination
Centre) publishes a plain-text bulk catalog at:

    https://neo.ssa.esa.int/PSDB-portlet/download?file=allneo.lst

Format is fixed-column / whitespace-delimited:
  Numbered:    "433       Eros                "  -- cols 0-9 = permid,
                                                      cols 10-29 = IAU name
  Unnumbered:  "          2026HZ1             "  -- cols 0-9 blank,
                                                      cols 10-29 = compact
                                                      designation (no space)
  Survey:      "          6344P-L             "  -- Palomar-Leiden survey
                                                      style (also no space)
  Mixed:       "145656    4788P-L            "  -- numbered with historical
                                                      survey-style provisional

The compact form ("2026HZ1", "6344P-L") needs a space inserted before
``mpc-designation`` will parse it; a single regex handles both kinds of
prefix. NEOCC's catalog is asteroid-by-syntax — no ``A/`` objects, so
no full-name fallback needed (unlike CNEOS).

Source identifier in ``source_membership.source``: ``'neocc'``.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Tuple
import os
import re
import time
import urllib.request

from .neo_consensus import (
    Canonical,
    begin_run,
    canonicalize,
    finish_run,
    upsert_membership,
)

SOURCE = "neocc"
NEOCC_URL = "https://neo.ssa.esa.int/PSDB-portlet/download?file=allneo.lst"
USER_AGENT = "CSS_MPC_toolkit/1.0 (consensus ingest)"

_CACHE_FILE = ".neocc_allneo.lst"
_CACHE_MAX_AGE_SEC = 21600  # 6 h

# "leading digits + first letter onward" splitter:
#   "2026HZ1"  -> ("2026", "HZ1")
#   "6344P-L"  -> ("6344", "P-L")
_COMPACT_RE = re.compile(r"^(\d+)([A-Z].*)$")


def _download_neocc_list(cache_dir: str) -> str:
    """Fetch allneo.lst, caching to disk with a 6 h TTL."""
    path = os.path.join(cache_dir, _CACHE_FILE)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SEC:
            return path
    print(f"Fetching NEOCC NEO list from {NEOCC_URL}")
    req = urllib.request.Request(NEOCC_URL)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    print(f"Saved NEOCC list ({len(data) / 1024:.1f} KB)")
    return path


def _normalize_unnumbered(s: str) -> str:
    """Insert a space between leading-digits and the letter portion.

    NEOCC writes ``"2026HZ1"`` and ``"6344P-L"``; ``mpc-designation``
    expects ``"2026 HZ1"`` and ``"6344 P-L"``.
    """
    m = _COMPACT_RE.match(s)
    return f"{m.group(1)} {m.group(2)}" if m else s


def _parse_neocc_list(path: str) -> List[str]:
    """Return a list of raw designation strings from allneo.lst.

    Numbered → the bare integer permid (e.g. ``"433"``).
    Unnumbered → space-normalized compact form (e.g. ``"2026 HZ1"``).
    Empty / non-conforming lines are skipped.
    """
    designations: List[str] = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            first = parts[0]
            if first.isdigit():
                designations.append(first)
            else:
                designations.append(_normalize_unnumbered(first))
    return designations


def ingest_neocc(conn, cache_dir: str) -> Tuple[int, int]:
    """Ingest the NEOCC NEO list (ESA allneo.lst).

    Returns ``(n_upserted, n_unresolved)``. Same transactional shape as
    the MPC and CNEOS ingestors.
    """
    started_at = begin_run(conn, SOURCE)
    try:
        path = _download_neocc_list(cache_dir)
        raw_designations = _parse_neocc_list(path)
        print(f"Parsed {len(raw_designations):,} NEOCC designations")

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
