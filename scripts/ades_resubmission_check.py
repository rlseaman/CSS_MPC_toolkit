#!/usr/bin/env python3
"""
ades_resubmission_check.py — does an ADES resubmission archive's astrometry
carry ADES-only quality fields in obs_sbn, or only obs80-level data?

Parses a gzip-tar of ADES 2017 XML files (read-only — never extracts or modifies
the archive), extracts the (stn, trkSub) key of every observation, and joins the
distinct tracklets against obs_sbn to report ADES-field population by observation
year. A repeatable version of the one-off analysis in
docs/2026-07-02_ades_resubmission_findings.md.

The 2024 CSS resubmission (see that doc) produced ZERO change in obs_sbn: the
2020 survey observations remain obs80-only. Re-run this after any future MPC
reprocessing to see whether that has changed.

Usage:
    setenv PGHOST <host>            # or export PGHOST=<host> (bash)
    ./venv/bin/python scripts/ades_resubmission_check.py <archive.tar.gz>
    ./venv/bin/python scripts/ades_resubmission_check.py <archive.tar.gz> --max-files 200

Notes:
    * Read-only against obs_sbn via lib.db.connect (claude_ro). The join is
      forced onto the obs_sbn.trksub index (enable_seqscan/hashjoin/mergejoin off)
      so it never sequentially scans the 500M+ row table.
    * Runs wherever PGHOST points (a replica with the full ADES obs_sbn schema).
    * Runtime ~2 min on Gizmo NVMe for the full ~1.6M-obs archive; slower on HDD.
"""
import argparse
import collections
import os
import re
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.db import connect  # noqa: E402

TAG = re.compile(r'<(trkSub|provID|permID|stn|obsTime|rmsRA)>([^<]*)</')
ADES_FIELDS = ("rmsra", "nstars", "rmsmag", "logsnr")  # ADES-only quality fields


def parse_archive(path, max_files=None):
    """Stream every optical record; return (pairs set, stats dict). Read-only."""
    tf = tarfile.open(path, "r:gz")
    n_files = n_obs = with_rms = 0
    by_stn = collections.Counter()
    by_year = collections.Counter()
    pairs = set()
    for m in tf:
        if not m.isfile():
            continue
        if max_files is not None and n_files >= max_files:
            break
        n_files += 1
        data = tf.extractfile(m).read().decode("utf-8", "replace")
        for block in data.split("<optical>")[1:]:
            block = block.split("</optical>")[0]
            d = dict(TAG.findall(block))
            stn = d.get("stn", "")
            trk = d.get("trkSub", "")
            year = d.get("obsTime", "")[:4]
            n_obs += 1
            by_stn[stn] += 1
            if year.isdigit():
                by_year[year] += 1
            if "rmsRA" in d:
                with_rms += 1
            if stn and trk:
                pairs.add((stn, trk))
    tf.close()
    return pairs, dict(n_files=n_files, n_obs=n_obs, with_rms=with_rms,
                       by_stn=dict(by_stn), by_year=dict(sorted(by_year.items())))


def join_obs_sbn(pairs, host=None, chunk=8000):
    """Join distinct (stn,trkSub) tracklets to obs_sbn; aggregate field
    population by observation year. Read-only; index-forced."""
    agg = collections.defaultdict(lambda: collections.Counter())
    pairs = list(pairs)
    with connect(host=host) as conn:
        cur = conn.cursor()
        for guc in ("enable_seqscan", "enable_hashjoin", "enable_mergejoin"):
            cur.execute(f"SET {guc}=off")  # force trksub-index nested loop
        cols = ", ".join(f"count(o.{f}) {f}" for f in ADES_FIELDS)
        for i in range(0, len(pairs), chunk):
            batch = pairs[i:i + chunk]
            values = b",".join(cur.mogrify("(%s,%s)", p) for p in batch).decode()
            cur.execute(f"""
                SELECT extract(year FROM o.obstime)::int AS yr,
                       count(*) AS sbn_rows, {cols}, count(o.obs80) AS obs80
                FROM (VALUES {values}) AS k(stn, trksub)
                JOIN obs_sbn o ON o.stn = k.stn AND o.trksub = k.trksub
                GROUP BY 1
            """)
            for row in cur.fetchall():
                yr = row[0]
                agg[yr]["sbn_rows"] += row[1]
                for j, f in enumerate(ADES_FIELDS):
                    agg[yr][f] += row[2 + j]
                agg[yr]["obs80"] += row[2 + len(ADES_FIELDS)]
            print(f"  ...joined {min(i + chunk, len(pairs)):>7}/{len(pairs)} tracklets",
                  end="\r", file=sys.stderr)
    print(file=sys.stderr)
    return agg


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive", help="path to the ADES resubmission .tar.gz")
    ap.add_argument("--host", default=None, help="DB host (default: $PGHOST)")
    ap.add_argument("--max-files", type=int, default=None,
                    help="parse only the first N files (for a quick test)")
    ap.add_argument("--chunk", type=int, default=8000, help="tracklets per join query")
    args = ap.parse_args()

    t0 = time.time()
    print(f"Parsing {args.archive} (read-only) ...")
    pairs, st = parse_archive(args.archive, args.max_files)
    print(f"  files={st['n_files']}  observations={st['n_obs']:,}  "
          f"parsed in {time.time()-t0:.0f}s")
    print(f"  by station: {st['by_stn']}")
    print(f"  by year (ADES files): {st['by_year']}")
    pct = 100 * st['with_rms'] / st['n_obs'] if st['n_obs'] else 0
    print(f"  carry rmsRA in the files: {st['with_rms']:,} ({pct:.1f}%)")
    print(f"  distinct (stn,trkSub) tracklets: {len(pairs):,}")

    print("\nJoining to obs_sbn (index-forced) ...")
    agg = join_obs_sbn(pairs, host=args.host, chunk=args.chunk)

    print("\nobs_sbn field population for the resubmitted tracklets, by year:")
    hdr = f"{'year':>5} {'sbn_rows':>10} " + " ".join(f"{f:>8}" for f in ADES_FIELDS) + f"{'obs80':>10}"
    print(hdr)
    tot = collections.Counter()
    for yr in sorted(agg):
        r = agg[yr]
        print(f"{yr:>5} {r['sbn_rows']:>10,} " +
              " ".join(f"{r[f]:>8,}" for f in ADES_FIELDS) + f"{r['obs80']:>10,}")
        for k, v in r.items():
            tot[k] += v
    any_ades = max(tot[f] for f in ADES_FIELDS) if tot else 0
    n = tot['sbn_rows'] or 1
    print(f"\nHEADLINE: {tot['sbn_rows']:,} obs_sbn rows matched; "
          f"{any_ades:,} ({100*any_ades/n:.2f}%) carry any ADES quality field.")
    print(f"Total elapsed {time.time()-t0:.0f}s.")


if __name__ == "__main__":
    main()
