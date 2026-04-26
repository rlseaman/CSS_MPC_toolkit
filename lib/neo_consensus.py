"""
NEO consensus tables (`css_neo_consensus` schema): canonicalization
helpers and source-run/membership upsert primitives.

Per-source ingestors (e.g. `lib/neo_consensus_mpc.py`) build on these
primitives. The canonical key for an NEO is its **unpacked primary
provisional designation** (e.g. ``"2024 YR4"``, or for numbered objects
the unpacked provisional like ``"2004 MN4"`` — NOT the permid, which is
auxiliary).

Designs and rationale: see ``sql/consensus/install.sql`` and the
project memory ``neo_list_design.md``.
"""

from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

import psycopg2
import psycopg2.extras
from mpc_designation import (
    MPCDesignationError,
    detect_format,
    is_valid_designation,
    pack,
    sanitize,
    unpack,
)


@dataclass
class Canonical:
    """Canonical form of one source-emitted NEO designation.

    `desig_parsed` and `orbit_in_mpc` come apart deliberately: the
    string can parse cleanly via ``mpc-designation`` without yet being
    in ``public.mpc_orbits`` (e.g. NEOCC virtual-impactor candidate
    that MPC hasn't ingested).
    """
    primary_desig: str            # unpacked primary provisional (canonical key)
    packed_desig: Optional[str]   # packed primary provisional; None iff desig_parsed=False
    permid: Optional[str]         # for numbered NEOs only ("433", "99942", ...)
    raw_string: str               # exactly what the source emitted
    desig_parsed: bool
    orbit_in_mpc: bool
    is_comet: bool


@contextmanager
def connect_consensus(host: str = "/tmp",
                      dbname: str = "mpc_sbn") -> Iterator:
    """Context-managed write-capable connection to the consensus schema.

    Defaults to peer auth on Gizmo (``PGHOST=/tmp``). The connecting
    OS user must have INSERT/UPDATE on ``css_neo_consensus`` tables.
    Commits on clean exit; rolls back on exception.
    """
    conn = psycopg2.connect(host=host, dbname=dbname)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def canonicalize(raw: str, conn) -> Optional[Canonical]:
    """Canonicalize one source-emitted designation.

    Returns ``None`` when the input is rejected by ``mpc-designation``
    or — for numbered objects — when ``numbered_identifications``
    has no row for the permid (in which case we can't recover the
    primary provisional and refuse to invent one).

    Otherwise returns a fully-populated :class:`Canonical`.
    """
    s = sanitize(raw)
    if not s or not is_valid_designation(s):
        return None

    try:
        fmt = detect_format(s)
    except MPCDesignationError:
        return None
    # A/ and I/ designations carry comet-style syntax but are physically
    # asteroids (objects on cometary orbits without a coma; or interstellar
    # objects). mpc-designation flags them with type='comet_full' but the
    # subtype contains 'asteroid'. Don't conflate with real comets (C/, P/,
    # D/), which v_membership_wide deliberately filters out for v1.
    is_comet = (fmt["type"].startswith("comet")
                and "asteroid" not in fmt.get("subtype", ""))

    if fmt["type"] == "permanent":
        # Numbered object: DB lookup to recover the provisional.
        try:
            permid = unpack(s) if fmt["format"] == "packed" else s
        except MPCDesignationError:
            return None
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT packed_primary_provisional_designation,
                       unpacked_primary_provisional_designation
                  FROM public.numbered_identifications
                 WHERE permid = %s
                """,
                (permid,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        packed, unpacked = row
        c = Canonical(
            primary_desig=unpacked,
            packed_desig=packed,
            permid=permid,
            raw_string=raw,
            desig_parsed=True,
            orbit_in_mpc=False,
            is_comet=is_comet,
        )
    else:
        # Provisional (asteroid or comet).
        try:
            packed = pack(s) if fmt["format"] == "unpacked" else s
            unpacked = unpack(s) if fmt["format"] == "packed" else s
        except MPCDesignationError:
            return None
        c = Canonical(
            primary_desig=unpacked,
            packed_desig=packed,
            permid=None,
            raw_string=raw,
            desig_parsed=True,
            orbit_in_mpc=False,
            is_comet=is_comet,
        )

    # orbit_in_mpc probe — independent signal of whether mpc_orbits has
    # caught up with this object.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
              FROM public.mpc_orbits
             WHERE packed_primary_provisional_designation = %s
             LIMIT 1
            """,
            (c.packed_desig,),
        )
        c.orbit_in_mpc = cur.fetchone() is not None

    return c


def begin_run(conn, source: str) -> datetime:
    """Insert a 'running' source_runs row and commit immediately so the
    run is visible even if the ingest crashes mid-flight. Returns the
    started_at timestamp (used as part of the row's primary key)."""
    started_at = datetime.now(tz=timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO css_neo_consensus.source_runs
                (source, started_at, status)
            VALUES (%s, %s, 'running')
            """,
            (source, started_at),
        )
    conn.commit()
    return started_at


def finish_run(
    conn,
    source: str,
    started_at: datetime,
    status: str,
    n_rows: int = 0,
    n_unresolved: int = 0,
    error: Optional[str] = None,
) -> None:
    """Update the run row with terminal status. Caller commits."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE css_neo_consensus.source_runs
               SET finished_at  = %s,
                   status       = %s,
                   n_rows       = %s,
                   n_unresolved = %s,
                   error_text   = %s
             WHERE source = %s AND started_at = %s
            """,
            (
                datetime.now(tz=timezone.utc),
                status,
                n_rows,
                n_unresolved,
                error,
                source,
                started_at,
            ),
        )


def upsert_membership(
    conn,
    source: str,
    canonicals: Iterable[Canonical],
    now: datetime,
) -> int:
    """Bulk-upsert canonicals into source_membership for one source.

    Updates ``last_seen`` and ``last_refreshed`` on matching rows,
    inserts new rows. Does NOT delete rows whose ``primary_desig``
    isn't in ``canonicals`` — that is a separate retention policy.
    """
    rows = [
        (
            source,
            c.primary_desig,
            c.packed_desig,
            c.permid,
            c.raw_string,
            c.desig_parsed,
            c.orbit_in_mpc,
            c.is_comet,
            now,
            now,
            now,
        )
        for c in canonicals
    ]
    if not rows:
        return 0
    sql = """
        INSERT INTO css_neo_consensus.source_membership (
            source, primary_desig, packed_desig, permid,
            raw_string, desig_parsed, orbit_in_mpc, is_comet,
            first_seen, last_seen, last_refreshed
        ) VALUES %s
        ON CONFLICT (source, primary_desig) DO UPDATE SET
            packed_desig    = EXCLUDED.packed_desig,
            permid          = EXCLUDED.permid,
            raw_string      = EXCLUDED.raw_string,
            desig_parsed    = EXCLUDED.desig_parsed,
            orbit_in_mpc    = EXCLUDED.orbit_in_mpc,
            is_comet        = EXCLUDED.is_comet,
            last_seen       = EXCLUDED.last_seen,
            last_refreshed  = EXCLUDED.last_refreshed
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=1000)
    return len(rows)
