"""mpc_orbits NEO source ingestor (local DB → css_neo_consensus).

This is the broader-than-NEA.txt MPC view — every ``mpc_orbits`` row
with q ≤ 1.3 AU and e < 1, *including* A/-prefix objects (asteroids on
cometary orbits) that NEA.txt's asteroid-by-syntax curation drops.

Unlike the other four sources, this one doesn't fetch from an external
HTTP API — it's a single SQL query against the local replica. So the
``cache_dir`` argument is ignored.

What we include:
  * Plain asteroids (no syntax prefix), q ≤ 1.3, e < 1
  * A/-prefix asteroids (cometary-orbit asteroids), q ≤ 1.3, e < 1

What we exclude:
  * C/, P/, D/-prefix comets (the dashboard tracks asteroids; comets
    can be a separate source layer if/when we want them)
  * Hyperbolic / parabolic objects (e ≥ 1)

Source identifier in ``source_membership.source``: ``'mpc_orbits'``.

Scope: this is intentionally an alternate "what does MPC's orbit catalog
say is an NEO?" view, distinct from ``'mpc'`` (NEA.txt). When MPC
completes their long-promised mpc_orbits cleanup, the two should
converge — but until then, comparing them surfaces the delta in MPC's
own internal disagreement between NEA.txt curation and orbit-catalog
membership.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Tuple

from .neo_consensus import (
    Canonical,
    begin_run,
    finish_run,
    upsert_membership,
)

SOURCE = "mpc_orbits"


def ingest_mpc_orbits(conn, cache_dir: str = "") -> Tuple[int, int]:
    """Ingest the mpc_orbits NEO view.

    Args:
        conn: psycopg2 write-capable connection to mpc_sbn.
        cache_dir: ignored (no external fetch); kept for the
            CLI dispatch's uniform signature.

    Returns:
        ``(n_upserted, n_unresolved)``. n_unresolved is always 0 — the
        SQL filter guarantees every selected row has packed + unpacked
        designations and an orbit fit.
    """
    started_at = begin_run(conn, SOURCE)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mo.unpacked_primary_provisional_designation,
                       mo.packed_primary_provisional_designation,
                       ni.permid
                  FROM public.mpc_orbits mo
                  LEFT JOIN public.numbered_identifications ni
                    ON ni.packed_primary_provisional_designation
                     = mo.packed_primary_provisional_designation
                 WHERE mo.q <= 1.3
                   AND mo.e < 1
                   AND mo.unpacked_primary_provisional_designation NOT LIKE 'C/%%'
                   AND mo.unpacked_primary_provisional_designation NOT LIKE 'P/%%'
                   AND mo.unpacked_primary_provisional_designation NOT LIKE 'D/%%'
                """
            )
            rows = cur.fetchall()

        canonicals = [
            Canonical(
                primary_desig=unpacked,
                packed_desig=packed,
                permid=permid,
                raw_string=unpacked,
                desig_parsed=True,
                # By construction — we read from mpc_orbits.
                orbit_in_mpc=True,
                # A/-prefix is asteroid-on-cometary-orbit; we already
                # exclude C/P/D above, so anything reaching here is
                # asteroid (plain or A/). Per project convention:
                # A/ is asteroid-by-physics → is_comet=False.
                is_comet=False,
            )
            for (unpacked, packed, permid) in rows
        ]
        print(f"mpc_orbits: {len(canonicals):,} rows match q ≤ 1.3, e < 1, "
              f"asteroid + A/ only")

        now = datetime.now(tz=timezone.utc)
        n_upserted = upsert_membership(conn, SOURCE, canonicals, now=now)
        conn.commit()

        finish_run(
            conn, SOURCE, started_at, status="ok",
            n_rows=n_upserted, n_unresolved=0,
        )
        conn.commit()
        return n_upserted, 0
    except Exception as e:
        conn.rollback()
        finish_run(
            conn, SOURCE, started_at, status="fail",
            error=f"{type(e).__name__}: {e}",
        )
        conn.commit()
        raise
