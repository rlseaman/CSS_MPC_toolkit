#!/usr/bin/env python3
"""
ades_overlay_loader.py — reconcile an ADES reprocessing batch against obs_sbn and
emit tracklet-supersession assertions for css_ades_overlay.

Pipeline (see docs/2026-07-02_ades_overlay_design.md):
  parse batch -> group into reprocessed tracklets -> proximity-match each obs to
  obs_sbn on (stn, obstime window, nearest ra/dec) with a 2x confidence gate ->
  classify each tracklet (supersede | add; auto | review) -> emit SQL assertions.

Read-only against obs_sbn via lib.db (claude_ro); the archive is opened read-only.
WRITES are emitted as SQL (--out) to apply separately as the schema owner, so the
'review' tail can be inspected first. original_obsids and basis_max_updated are
resolved by subquery on the write host (which performs the whole-original-tracklet
expansion and avoids cross-replica obsid concerns).

Usage:
    setenv PGHOST <host>
    ./venv/bin/python scripts/ades_overlay_loader.py <batch.tar.gz> \
        --source-batch CSS_2024Nov29 --out /tmp/overlay_batch.sql
    ...  --max-files 50            # quick subset
"""
import argparse, collections, datetime as dt, os, re, sys, tarfile, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.db import connect  # noqa: E402

UTC = dt.timezone.utc
FIELDS = ('trkSub','obsTime','ra','dec','mode','astCat','photCat','mag','rmsMag',
          'band','rmsRA','rmsDec','rmsCorr','rmsTime','logSNR','rmsFit','nStars')
TAG = re.compile(r'<('+'|'.join(FIELDS)+r'|stn)>([^<]*)</')
# obs table column  <-  ADES field
COLMAP = [('stn','stn'),('trksub','trkSub'),('obstime','obsTime'),('ra','ra'),
          ('dec','dec'),('mode','mode'),('astcat','astCat'),('photcat','photCat'),
          ('mag','mag'),('rmsmag','rmsMag'),('band','band'),('rmsra','rmsRA'),
          ('rmsdec','rmsDec'),('rmscorr','rmsCorr'),('rmstime','rmsTime'),
          ('logsnr','logSNR'),('rmsfit','rmsFit'),('nstars','nStars')]
NUMERIC = {'ra','dec','mag','rmsmag','rmsra','rmsdec','rmscorr','rmstime','logsnr','rmsfit','nstars'}


def _tsv(v):
    if v is None or v == '':
        return r'\N'
    return str(v).replace('\\', '\\\\').replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')


def _arr(obsids):
    return '{' + ','.join(obsids) + '}'   # obsids are alphanumeric; no quoting needed


def parse_batch(path, max_files):
    """Group the batch's optical records into reprocessed tracklets keyed by
    (stn, trkSub). Returns {key: [obs_dict, ...]}. Read-only."""
    tf = tarfile.open(path, 'r:gz')
    tracklets = collections.defaultdict(list)
    nf = nobs = nskip = 0
    for m in tf:
        if not m.isfile():
            continue
        if max_files is not None and nf >= max_files:
            break
        nf += 1
        data = tf.extractfile(m).read().decode('utf-8', 'replace')
        for blk in data.split('<optical>')[1:]:
            d = dict(TAG.findall(blk.split('</optical>')[0]))
            if 'ra' not in d or 'stn' not in d or 'trkSub' not in d or 'obsTime' not in d:
                continue
            try:   # skip sentinel/garbage obsTime (e.g. JD-0 '-4712-01-01...')
                d['_t'] = dt.datetime.strptime(d['obsTime'][:23], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)
            except ValueError:
                nskip += 1
                continue
            tracklets[(d['stn'], d['trkSub'])].append(d)
            nobs += 1
    return tracklets, nf, nobs, nskip


def sep_arcsec(ra, dec, ra2, dec2):
    return np.sqrt(((ra - ra2) * np.cos(np.radians(dec)))**2 + (dec - dec2)**2) * 3600.0


def load_station_night(cur, stn, day, cache):
    """Pull obs_sbn for a station's night (UTC-straddle padded), cached."""
    key = (stn, day)
    if key in cache:
        return cache[key]
    lo = dt.datetime.combine(day, dt.time(), UTC) - dt.timedelta(hours=12)
    hi = lo + dt.timedelta(hours=48)
    cur.execute("""SELECT obsid, COALESCE(NULLIF(trksub,''), trkid) AS otrk, obstime,
                          ra::float8, dec::float8, updated_at
                   FROM obs_sbn WHERE stn=%s AND obstime>=%s AND obstime<%s""",
                (stn, lo.replace(tzinfo=None), hi.replace(tzinfo=None)))
    rows = cur.fetchall()
    d = {'obsid': np.array([r[0] for r in rows]),
         'otrk':  np.array([r[1] for r in rows]),
         'ts':    np.array([r[2].replace(tzinfo=UTC).timestamp() for r in rows]),
         'ra':    np.array([r[3] for r in rows]),
         'dec':   np.array([r[4] for r in rows]),
         'upd':   [r[5] for r in rows]}
    cache[key] = d
    return d


def match_obs(o, sn, window, max_radius, ratio):
    """Proximity-match one reprocessed obs to obs_sbn. Returns
    (original_trk | None, status) where status in matched|ambiguous|new."""
    if len(sn['obsid']) == 0:
        return None, 'new'
    ts = o['_t'].timestamp()
    m = np.abs(sn['ts'] - ts) <= window
    if not m.any():
        return None, 'new'
    seps = np.where(m, sep_arcsec(float(o['ra']), float(o['dec']), sn['ra'], sn['dec']), np.inf)
    order = np.argsort(seps)
    n0 = order[0]; s0 = seps[n0]; s1 = seps[order[1]] if len(order) > 1 else np.inf
    if s0 > max_radius:
        return None, 'new'
    if s1 < ratio * max(s0, 1e-6):
        return sn['otrk'][n0], 'ambiguous'
    return sn['otrk'][n0], 'matched'


def sql_lit(v, col):
    if v is None or v == '':
        return 'NULL'
    if col in NUMERIC:
        return str(v)
    if col == 'obstime':
        return "'" + v.replace('T', ' ').replace('Z', '') + "'"
    return "'" + str(v).replace("'", "") + "'"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive")
    ap.add_argument("--source-batch", default="ADES_batch")
    ap.add_argument("--out", default=None, help="SQL output file (default <batch>.sql)")
    ap.add_argument("--host", default=None)
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--time-window", type=float, default=10.0, help="match time window, s")
    ap.add_argument("--max-radius", type=float, default=30.0, help="max match radius, arcsec")
    ap.add_argument("--ratio", type=float, default=2.0, help="confidence gate (2nd/1st)")
    a = ap.parse_args()
    out = a.out or (os.path.splitext(os.path.basename(a.archive))[0] + ".sql")

    t0 = time.time()
    print(f"Parsing {a.archive} (read-only) ...")
    tracklets, nf, nobs, nskip = parse_batch(a.archive, a.max_files)
    t_parse = time.time() - t0
    print(f"  files={nf}  observations={nobs:,}  reprocessed tracklets={len(tracklets):,}"
          + (f"  (skipped {nskip} bad obsTime)" if nskip else "") + f"  ({t_parse:.0f}s)")

    ops = collections.Counter(); conf = collections.Counter(); by_year = collections.Counter()
    n_new = n_ambig = n_matched = 0
    review = []
    trk_rows = []; obs_rows = []
    cache = {}
    tm = time.time()
    with connect(host=a.host) as conn:
        cur = conn.cursor()
        for (stn, trk), obss in tracklets.items():
            day = min(o['_t'] for o in obss).date()
            by_year[day.year] += len(obss)
            sn = load_station_night(cur, stn, day, cache)
            orig_trks = set(); status_any_review = False
            for o in obss:
                ot, st = match_obs(o, sn, a.time_window, a.max_radius, a.ratio)
                if st == 'new': n_new += 1
                elif st == 'ambiguous': n_ambig += 1; status_any_review = True; orig_trks.add(ot)
                else: n_matched += 1; orig_trks.add(ot)
            op = 'add' if not orig_trks else 'supersede'
            mc = 'review' if status_any_review else 'auto'
            ops[op] += 1; conf[mc] += 1
            if mc == 'review':
                review.append((stn, trk, len(obss)))
            oid = f"{a.source_batch}:{stn}:{trk}"
            # whole-original-tracklet expansion, resolved in-memory from the pulled
            # station-night (obsids are MPC-permanent; read & write the same replica).
            if orig_trks:
                mask = np.isin(sn['otrk'], list(orig_trks))
                orig_obsids = [str(x) for x in sn['obsid'][mask]]
                upds = [sn['upd'][i] for i in np.where(mask)[0]]
                basis = max(upds).isoformat() if upds else None
            else:
                orig_obsids = []; basis = None
            trk_rows.append('\t'.join([oid, a.source_batch, stn, _tsv(trk), op,
                                       _arr(orig_obsids), mc, _tsv(basis)]))
            for o in obss:
                vals = [oid]
                for col, af in COLMAP:
                    v = o.get(af)
                    if col == 'obstime' and v:
                        v = v.replace('T', ' ').replace('Z', '')
                    vals.append(_tsv(v))
                obs_rows.append('\t'.join(vals))
    t_match = time.time() - tm

    # Emit as COPY blocks (fast apply at archive scale).
    with open(out, "w") as f:
        f.write(f"-- ades_overlay_loader COPY batch  source_batch={a.source_batch}  "
                f"window={a.time_window}s radius={a.max_radius}\" ratio={a.ratio}\n")
        f.write("COPY css_ades_overlay.tracklet (overlay_trk_id,source_batch,stn,new_trksub,"
                "op,original_obsids,match_confidence,basis_max_updated) FROM stdin;\n")
        f.write('\n'.join(trk_rows) + '\n\\.\n')
        f.write("COPY css_ades_overlay.obs (overlay_trk_id," + ','.join(c for c, _ in COLMAP)
                + ") FROM stdin;\n")
        f.write('\n'.join(obs_rows) + '\n\\.\n')

    print(f"\nReconciliation: parse {t_parse:.0f}s + match {t_match:.0f}s  "
          f"({nobs/max(t_match,1):,.0f} obs/s match)")
    print(f"  obs matched={n_matched:,}  ambiguous={n_ambig:,}  new-detection={n_new:,}")
    print(f"  tracklets: " + "  ".join(f"{k}={v:,}" for k, v in ops.items()))
    print(f"  confidence: " + "  ".join(f"{k}={v:,}" for k, v in conf.items())
          + f"   (review tail = {100*conf['review']/max(len(tracklets),1):.1f}%)")
    print(f"  obs by year: " + "  ".join(f"{y}={n:,}" for y, n in sorted(by_year.items())))
    if review:
        print(f"  review queue ({len(review)}): " + ", ".join(f"{s}/{t}" for s, t, _ in review[:8])
              + (" ..." if len(review) > 8 else ""))
    print(f"\nCOPY assertions written to {out}  (apply as the schema owner)")


if __name__ == "__main__":
    main()
