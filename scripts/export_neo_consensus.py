#!/usr/bin/env python3
"""
Export the all-six NEO consensus as a portable flat CSV snapshot.

Dumps the ``css_neo_consensus`` membership to a CSV so downstream
consumers that cannot reach this database can classify designations as
NEOs offline. The motivating consumer is the CSS reprocessing V&V on
sikhote: there JPL CNEOS and NEOfixer are firewalled and this Postgres
host (Gizmo) is unreachable, so the consensus has to arrive as a
published snapshot rather than a live query.

Two modes:

  --mode aliases  (default) one row per known designation alias
                  (primary / secondary provisional / permid), each row
                  carrying the per-source boolean flags. Maximizes match
                  coverage: an observation reported under *any* alias of
                  an object still resolves to NEO.
  --mode wide     one row per object (primary_desig) — the compact form.

The ``--min-sources N`` filter selects the consensus strength: 1 keeps
every object recognized by at least one source (the union); 6 keeps only
unanimous objects. Default 1 (union), matching the dashboard's default
membership surface.

Read-only. Uses lib.db (PGHOST + ~/.pgpass, ``claude_ro`` role).

Publish + consume (mirrors scripts/upload_release.sh):

    python scripts/export_neo_consensus.py --out neo_consensus.csv
    ./scripts/upload_release.sh neo_consensus.csv     # -> GH release 'latest'

    # consumer side (e.g. a daily cron on the reprocessing host):
    gh release download latest -R rlseaman/CSS_MPC_toolkit \\
        -p 'neo_consensus*.csv' --clobber

Usage:
    python scripts/export_neo_consensus.py [--mode aliases|wide]
                                           [--min-sources N] [--out PATH]
"""
import argparse
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.db import connect, timed_query

# Per-source membership flags in css_neo_consensus.v_membership_wide.
SOURCES = ["in_mpc", "in_cneos", "in_neocc", "in_neofixer",
           "in_mpc_orbits", "in_lowell"]


def _nsrc(prefix=""):
    return " + ".join(f"{prefix}{c}::int" for c in SOURCES)


def _sql(mode):
    if mode == "wide":
        return f"""
            SELECT primary_desig, packed_desig, permid,
                   {", ".join(SOURCES)},
                   ({_nsrc()}) AS n_sources
              FROM css_neo_consensus.v_membership_wide
             WHERE ({_nsrc()}) >= %s
             ORDER BY primary_desig
        """
    # aliases: expand to every known designation form, carrying the flags.
    return f"""
        SELECT d.primary_desig, d.designation, d.kind,
               w.packed_desig, w.permid,
               {", ".join("w." + c for c in SOURCES)},
               ({_nsrc("w.")}) AS n_sources
          FROM css_neo_consensus.v_member_designations d
          JOIN css_neo_consensus.v_membership_wide w USING (primary_desig)
         WHERE ({_nsrc("w.")}) >= %s
         ORDER BY d.primary_desig, d.kind
    """


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("aliases", "wide"), default="aliases")
    ap.add_argument("--min-sources", type=int, default=1,
                    help="keep objects recognized by at least N of the six "
                         "sources (1 = union/any; 6 = unanimous). Default 1.")
    ap.add_argument("--out", default="neo_consensus.csv",
                    help="output CSV path (default: neo_consensus.csv)")
    args = ap.parse_args()

    if not 1 <= args.min_sources <= len(SOURCES):
        ap.error(f"--min-sources must be in 1..{len(SOURCES)}")

    t0 = time.time()
    with connect() as conn:
        df = timed_query(conn, _sql(args.mode), [args.min_sources],
                         label=f"neo_consensus_export[{args.mode}]")
    df.to_csv(args.out, index=False)

    print(f"\nwrote {args.out}: {len(df):,} rows "
          f"({args.mode}, min_sources={args.min_sources}) "
          f"in {time.time() - t0:.1f}s")
    if "primary_desig" in df:
        print(f"  distinct objects: {df['primary_desig'].nunique():,}")
    for c in SOURCES:
        if c in df:
            print(f"    {c}: {int(df[c].sum()):,}")


if __name__ == "__main__":
    main()
