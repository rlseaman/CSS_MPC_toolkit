"""Lowell Observatory astorb source ingestor (→ css_neo_consensus).

Lowell publishes a daily-updated, fixed-column ASCII asteroid catalog
of ~1.5 M orbits at:

    https://ftp.lowell.edu/pub/elgb/astorb.dat.gz   (~106 MB)

The catalog has no explicit perihelion-distance column, so we filter
NEOs by computing q = a(1 − e) and selecting q ≤ 1.3 ∧ e < 1.
Lowell's own orbit-fitting pipeline is independent of MPC/JPL/ESA —
this source's value is providing a sixth orbit-fitting paradigm for
cross-source comparison.

Empirically-verified column positions (1-indexed inclusive). The
web-docs FORTRAN format string doesn't match actual byte positions
on the live file (revised 2018+ but the doc wasn't updated), so we
rely on empirical verification against known objects (Eros, Apollo,
Apophis, Ceres):

    1–6     asteroid number (or blank if unnumbered)
    8–25    name / preliminary designation
    43–47   absolute magnitude H
    107–114 epoch (yyyymmdd)
    148–157 inclination i
    159–168 eccentricity e
    170–181 semi-major axis a

Numbered NEOs come through as the bare integer permid (e.g. ``"433"``);
unnumbered as the unpacked provisional with the IAU-standard space
(e.g. ``"1991 GO"``). Both shapes are already handled by
:func:`lib.neo_consensus.canonicalize`.

Source identifier in ``source_membership.source``: ``'lowell'``.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Tuple
import gzip
import os
import time
import urllib.request

from .neo_consensus import (
    Canonical,
    begin_run,
    canonicalize,
    finish_run,
    upsert_membership,
)

SOURCE = "lowell"
ASTORB_URL = "https://ftp.lowell.edu/pub/elgb/astorb.dat.gz"
USER_AGENT = "CSS_MPC_toolkit/1.0 (consensus ingest)"

_CACHE_FILE = ".astorb.dat.gz"
_CACHE_MAX_AGE_SEC = 21600  # 6 h


def _download_astorb(cache_dir: str) -> str:
    """Fetch astorb.dat.gz, caching to disk with a 6 h TTL.

    The file is ~106 MB compressed. We keep it gzipped on disk to save
    space and stream-decompress at parse time.
    """
    path = os.path.join(cache_dir, _CACHE_FILE)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SEC:
            return path
    print(f"Fetching Lowell astorb.dat.gz from {ASTORB_URL}")
    req = urllib.request.Request(ASTORB_URL)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    print(f"Saved astorb.dat.gz ({len(data) / 1024 / 1024:.1f} MB)")
    return path


def _parse_neos(path: str) -> Tuple[List[str], int]:
    """Stream-parse astorb.dat.gz and return ``(raw_designations, n_skipped)``.

    Filter: q = a(1 − e) ≤ 1.3 AND e < 1. ``n_skipped`` is the number of
    rows whose e/a fields couldn't parse (effectively zero in practice
    on this clean format, but tracked for diagnostics).
    """
    raws: List[str] = []
    n_skipped = 0
    with gzip.open(path, "rt") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                e = float(line[158:168])  # cols 159-168, F10.8
                a = float(line[169:181])  # cols 170-181, F12.8
            except ValueError:
                n_skipped += 1
                continue
            if e >= 1:
                continue
            if a * (1 - e) > 1.3:
                continue
            num = line[0:6].strip()
            if num:
                raws.append(num)
            else:
                desig = line[7:25].strip()
                if desig:
                    raws.append(desig)
    return raws, n_skipped


def ingest_lowell(conn, cache_dir: str) -> Tuple[int, int]:
    """Ingest the Lowell astorb NEO list (q ≤ 1.3 ∧ e < 1).

    Returns ``(n_upserted, n_unresolved)``.
    """
    started_at = begin_run(conn, SOURCE)
    try:
        path = _download_astorb(cache_dir)
        raws, n_parse_skipped = _parse_neos(path)
        if n_parse_skipped:
            print(f"Skipped {n_parse_skipped} unparseable rows during scan")
        print(f"Parsed {len(raws):,} astorb NEOs (q ≤ 1.3 ∧ e < 1)")

        canonicals: List[Canonical] = []
        n_unresolved = 0
        for raw in raws:
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
