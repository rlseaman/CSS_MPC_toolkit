"""NEOfixer NEO source ingestor (NEOfixer /targets/ → css_neo_consensus).

NEOfixer (https://neofixer.arizona.edu/, U. of Arizona) is an
observational-priority service. Its target list for site code 500
(geocenter / "all NEOs") is the bulk endpoint we want:

    https://neofixerapi.arizona.edu/targets/?site=500&q-max=1.3

NEOfixer is paradigmatically distinct from the other three sources:
its underlying orbit-fitting pipeline (find_orb) is independent of
MPC, JPL, and ESA. Two content-filtering steps are needed to make the
NEOfixer list comparable to MPC/CNEOS/NEOCC:

  1. NEOfixer mixes formally-designated NEOs with NEOCP candidates
     (per https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html).
     NEOCP candidates carry survey-internal temporary designations
     (e.g. "P22mVBC") that mpc-designation cannot parse and that
     don't yet correspond to a formal MPC designation. Each row
     carries a `neocp` boolean; we drop rows where `neocp=True`.

  2. NEOfixer's `q-max=1.3` URL parameter is advisory: ~760 / ~42,400
     rows leak through with NF q > 1.3, mostly because NEOfixer's
     Find_Orb fit gives a slightly different q than MPC's. The bar for
     omitting an object as a non-NEO is BOTH (a) a solid NF orbit AND
     (b) NF q > 1.3. "Solid" here means NF and MPC agree within
     `Q_SOLIDITY_TOLERANCE` AU at the 1.3 boundary. When they disagree
     by more (e.g. NF q=2.44 vs MPC q=1.20 for 2004 BP160 — a long-arc
     numbered NEO), we treat NEOfixer's Find_Orb fit as suspect and
     keep the object. This recovers objects where Find_Orb's solution
     is unstable on long arcs while preserving the clean q ≈ 1.3
     boundary disagreements.

Source identifier in ``source_membership.source``: ``'neofixer'``.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Tuple
import json
import os
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

SOURCE = "neofixer"
NEOFIXER_BASE = "https://neofixerapi.arizona.edu"
SITE = "500"      # geocenter — "all NEOs"
Q_MAX = 1.3       # AU; matches MPC/CNEOS/NEOCC NEO definition
Q_SOLIDITY_TOLERANCE = 0.02
    # AU. If NF q > 1.3 and MPC q > 1.3 too, OR |NF q − MPC q| ≤ this
    # tolerance, NF's Find_Orb solution is "solid" and we honour its
    # not-NEO call. If MPC q ≤ 1.3 and the gap exceeds this tolerance,
    # NF's solution is suspect (typical for long-arc numbered NEOs
    # where Find_Orb's restart geometry diverges from MPC's) and we
    # keep the object. The 0.02 AU choice is the user-set boundary
    # that distinguishes legitimate boundary-q disagreements (e.g.
    # NF 1.31 vs MPC 1.29 — both within 0.01 AU of cutoff, agreement)
    # from Find_Orb instabilities (e.g. NF 2.44 vs MPC 1.20).
USER_AGENT = "CSS_MPC_toolkit/1.0 (consensus ingest)"

_CACHE_FILE = ".neofixer_targets.json"
_CACHE_MAX_AGE_SEC = 21600  # 6 h


def _download_neofixer_list(cache_dir: str) -> str:
    """Fetch /targets/ for site=500 with q-max=1.3, cache JSON to disk."""
    path = os.path.join(cache_dir, _CACHE_FILE)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SEC:
            return path

    params = urllib.parse.urlencode({"site": SITE, "q-max": Q_MAX})
    url = f"{NEOFIXER_BASE}/targets/?{params}"
    print(f"Fetching NEOfixer NEO list (site={SITE}, q-max={Q_MAX})")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    print(f"Saved NEOfixer list ({len(data) / 1024:.1f} KB)")
    return path


def _load_mpc_q_lookup(conn) -> dict:
    """Build a ``{neofixer_cache_key: mpc_q}`` lookup.

    NEOfixer's bulk cache mixes packed-provisional and packed-numbered
    keys (~90% / ~7.5%). We want a single dict that resolves either to
    the MPC orbit's q so the smart-q rule can cross-check.
    """
    from .mpc_convert import pack_designation
    lookup: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mo.packed_primary_provisional_designation,
                   mo.q,
                   ni.permid
              FROM public.mpc_orbits mo
              LEFT JOIN public.numbered_identifications ni
                ON ni.packed_primary_provisional_designation
                 = mo.packed_primary_provisional_designation
             WHERE mo.q IS NOT NULL AND mo.e < 1
            """
        )
        for packed_prov, q, permid in cur.fetchall():
            q = float(q)
            lookup[packed_prov] = q
            if permid:
                try:
                    lookup[pack_designation(permid)] = q
                except Exception:
                    # Malformed permid (shouldn't happen for live data); skip.
                    pass
    return lookup


def _classify_q_filter(q_nf, mpc_q):
    """Apply the user's two-clause omission rule.

    Returns one of:
      'keep'             — NF q ≤ 1.3 (standard NEO).
      'drop_solid'       — NF q > 1.3 and orbit is solid (omit as non-NEO).
      'keep_unsolid'     — NF q > 1.3, MPC says NEO with substantially
                           different q (Find_Orb solution suspect; keep).
      'drop_q_none'      — NF q is null (no information; cannot keep).
    """
    if q_nf is None:
        return "drop_q_none"
    if q_nf <= 1.3:
        return "keep"
    if mpc_q is None or mpc_q > 1.3:
        return "drop_solid"
    # NEOfixer cache reports q to 3 decimals; small float noise (e.g.
    # 1.31 - 1.29 = 0.020000000000000018) shouldn't flip the verdict.
    if abs(q_nf - mpc_q) <= Q_SOLIDITY_TOLERANCE + 1e-9:
        return "drop_solid"
    return "keep_unsolid"


def _parse_neofixer_list(path: str, mpc_q_lookup: dict
                         ) -> Tuple[List[str], dict, dict]:
    """Return ``(survivor_keys, counts, detail)`` from the cached NEOfixer list.

    Walks the cached JSON-RPC response, applying the NEOCP filter and
    the smart q-rule (see :func:`_classify_q_filter` for semantics).
    `counts` carries per-category counts for the run log; `detail` is
    a ``{packed_key: {q, neo, u}}`` map populated for survivors so the
    ingestor can stash NEOfixer's per-object fields on Canonical rows.
    """
    with open(path) as f:
        data = json.load(f)
    objects = data.get("result", {}).get("objects", {})
    survivors: List[str] = []
    detail: dict = {}
    counts = {"neocp": 0, "q_none": 0, "drop_solid": 0, "keep_unsolid": 0,
              "keep_neo": 0}
    for packed, obj in objects.items():
        if obj.get("neocp"):
            counts["neocp"] += 1
            continue
        verdict = _classify_q_filter(obj.get("q"), mpc_q_lookup.get(packed))
        if verdict == "keep":
            counts["keep_neo"] += 1
        elif verdict == "keep_unsolid":
            counts["keep_unsolid"] += 1
        elif verdict == "drop_solid":
            counts["drop_solid"] += 1
            continue
        else:  # 'drop_q_none'
            counts["q_none"] += 1
            continue
        survivors.append(packed)
        detail[packed] = {
            "q":   obj.get("q"),
            "neo": obj.get("neo"),  # 0..100 NEO probability
            "u":   obj.get("u"),    # find_orb uncertainty parameter
        }
    return survivors, counts, detail


def ingest_neofixer(conn, cache_dir: str) -> Tuple[int, int]:
    """Ingest the NEOfixer NEO list (site 500, q ≤ 1.3 AU).

    Returns ``(n_upserted, n_weak)``. ``n_weak`` counts rows stored with
    ``desig_parsed=FALSE`` because the input couldn't be canonicalized
    — typically NEOCP candidates. Same transactional shape as the
    other source ingestors.
    """
    started_at = begin_run(conn, SOURCE)
    try:
        path = _download_neofixer_list(cache_dir)
        mpc_q_lookup = _load_mpc_q_lookup(conn)
        ids, counts, detail = _parse_neofixer_list(path, mpc_q_lookup)
        print(
            f"NEOfixer: {len(ids):,} after filters "
            f"(dropped {counts['neocp']} NEOCP candidates, "
            f"{counts['q_none']} with no q, "
            f"{counts['drop_solid']} with NF q > 1.3 and solid orbit; "
            f"recovered {counts['keep_unsolid']} with NF q > 1.3 but "
            f"|NF q − MPC q| > {Q_SOLIDITY_TOLERANCE} AU)"
        )

        canonicals: List[Canonical] = []
        n_unresolved = 0
        for raw in ids:
            c = canonicalize(raw, conn)
            if c is None:
                # After dropping NEOCP candidates, any remaining
                # parse failure is genuinely anomalous — log and skip.
                n_unresolved += 1
                continue
            d = detail.get(raw, {})
            # Coerce to float (or None) for psycopg2 → REAL columns.
            def _f(x):
                try:
                    return float(x) if x is not None else None
                except (TypeError, ValueError):
                    return None
            c.nf_q = _f(d.get("q"))
            c.nf_neo_prob = _f(d.get("neo"))
            c.nf_u = _f(d.get("u"))
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
