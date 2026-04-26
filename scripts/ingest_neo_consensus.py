#!/usr/bin/env python3
"""Ingest one NEO consensus source into css_neo_consensus.source_membership.

Usage:
    python scripts/ingest_neo_consensus.py mpc [--cache-dir DIR]

Defaults to peer auth on the local Postgres via ``PGHOST=/tmp`` —
intended to run on Gizmo. The cache dir defaults to ``app/`` (where
NEA.txt etc. already live alongside the dashboard caches).

Sources currently supported: ``mpc`` (NEA.txt). Add new sources by
implementing an ``ingest_<source>(conn, cache_dir) -> (n, n_unresolved)``
in ``lib/neo_consensus_<source>.py`` and listing it in INGESTORS below.
"""
from __future__ import annotations
import argparse
import os
import sys

# Project root on sys.path so 'lib.*' imports work when invoked as a script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.neo_consensus import connect_consensus
from lib.neo_consensus_mpc import ingest_mpc
from lib.neo_consensus_cneos import ingest_cneos
from lib.neo_consensus_neocc import ingest_neocc
from lib.neo_consensus_neofixer import ingest_neofixer
from lib.neo_consensus_mpc_orbits import ingest_mpc_orbits


INGESTORS = {
    "mpc": ingest_mpc,
    "cneos": ingest_cneos,
    "neocc": ingest_neocc,
    "neofixer": ingest_neofixer,
    "mpc_orbits": ingest_mpc_orbits,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("source", choices=sorted(INGESTORS),
                    help="which source to ingest")
    ap.add_argument("--cache-dir", default=os.path.join(_ROOT, "app"),
                    help="where to cache downloaded files (default: app/)")
    args = ap.parse_args()

    with connect_consensus() as conn:
        n_rows, n_unresolved = INGESTORS[args.source](conn, args.cache_dir)

    print(f"{args.source}: {n_rows} upserted, {n_unresolved} unresolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
