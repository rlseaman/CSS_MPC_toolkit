"""MPC NEO source ingestor (NEA.txt → css_neo_consensus.source_membership).

NEA.txt at https://minorplanetcenter.net/iau/MPCORB/NEA.txt is MPC's
curated NEA catalog. The MPC has been promising a cleaner direct query
against ``mpc_orbits`` for years; until that lands, NEA.txt is as
authoritative as anything else for "what does MPC consider an NEO?"

Source identifier in ``source_membership.source``: ``'mpc'``.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Tuple

from .nea_catalog import _download_nea_txt, _parse_nea_txt
from .neo_consensus import (
    Canonical,
    begin_run,
    canonicalize,
    finish_run,
    upsert_membership,
)

SOURCE = "mpc"


def ingest_mpc(conn, cache_dir: str) -> Tuple[int, int]:
    """Ingest the MPC NEO list from NEA.txt.

    Args:
        conn: open psycopg2 connection (write-capable) to mpc_sbn.
        cache_dir: directory in which to cache the NEA.txt download.

    Returns:
        ``(n_upserted, n_unresolved)``.

    The function manages its own transactions: the run row is written
    and committed up front; the membership upsert is committed atomically
    after canonicalization completes; the run row is then updated with
    the terminal status and committed. On exception, the membership upsert
    is rolled back and the run row records ``status='fail'``.
    """
    started_at = begin_run(conn, SOURCE)
    try:
        path = _download_nea_txt(cache_dir)
        nea_rows = _parse_nea_txt(path)  # (packed, h, is_numbered, number_str)

        canonicals: list[Canonical] = []
        n_unresolved = 0
        for packed, _h, _is_numbered, _number in nea_rows:
            c = canonicalize(packed, conn)
            if c is None:
                n_unresolved += 1
                continue
            canonicals.append(c)

        now = datetime.now(tz=timezone.utc)
        n_upserted = upsert_membership(conn, SOURCE, canonicals, now=now)
        conn.commit()

        finish_run(
            conn,
            SOURCE,
            started_at,
            status="ok",
            n_rows=n_upserted,
            n_unresolved=n_unresolved,
        )
        conn.commit()
        return n_upserted, n_unresolved
    except Exception as e:
        conn.rollback()
        finish_run(
            conn,
            SOURCE,
            started_at,
            status="fail",
            error=f"{type(e).__name__}: {e}",
        )
        conn.commit()
        raise
