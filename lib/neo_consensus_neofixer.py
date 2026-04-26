"""NEOfixer NEO source ingestor (NEOfixer /targets/ → css_neo_consensus).

NEOfixer (https://neofixer.arizona.edu/, U. of Arizona) is an
observational-priority service. Its target list for site code 500
(geocenter / "all NEOs") is the bulk endpoint we want:

    https://neofixerapi.arizona.edu/targets/?site=500&q-max=1.3

NEOfixer is paradigmatically distinct from the other three sources:
its underlying orbit-fitting pipeline (find_orb) is independent of
MPC, JPL, and ESA. Two important content-filtering steps are needed
to make the NEOfixer list comparable to MPC/CNEOS/NEOCC:

  1. NEOfixer mixes formally-designated NEOs with NEOCP candidates
     (per https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html).
     NEOCP candidates carry survey-internal temporary designations
     (e.g. "P22mVBC") that mpc-designation cannot parse and that
     don't yet correspond to a formal MPC designation. Each row
     carries a `neocp` boolean; we drop rows where `neocp=True`.

  2. The `q-max=1.3` URL parameter is *advisory*, not strictly
     enforced — empirically ~760 / ~42,400 rows leak through with
     `q > 1.3` (Mars Crossers, plausibly because NEOfixer's find_orb
     q for them is ≤ 1.3 in some recent fit but the response carries
     a different epoch's value). We therefore enforce `q ≤ 1.3`
     client-side using the per-row `q` field that find_orb populates.

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


def _parse_neofixer_list(path: str) -> Tuple[List[str], int, int]:
    """Return ``(packed_designations, n_dropped_neocp, n_dropped_q)``.

    Walks the cached JSON-RPC response, applying the two filters:
    drop NEOCP candidates (``neocp=True``); drop rows where
    NEOfixer's own find_orb q exceeds 1.3 AU. Returns the packed
    designations of survivors plus per-filter drop counts for the
    run log.
    """
    with open(path) as f:
        data = json.load(f)
    result = data.get("result", {})
    objects = result.get("objects", {})
    survivors: List[str] = []
    n_dropped_neocp = 0
    n_dropped_q = 0
    for packed, obj in objects.items():
        if obj.get("neocp"):
            n_dropped_neocp += 1
            continue
        q = obj.get("q")
        if q is None or q > 1.3:
            n_dropped_q += 1
            continue
        survivors.append(packed)
    return survivors, n_dropped_neocp, n_dropped_q


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
        ids, n_dropped_neocp, n_dropped_q = _parse_neofixer_list(path)
        print(f"NEOfixer: {len(ids):,} after filters "
              f"(dropped {n_dropped_neocp} NEOCP candidates, "
              f"{n_dropped_q} with q > 1.3 AU)")

        canonicals: List[Canonical] = []
        n_unresolved = 0
        for raw in ids:
            c = canonicalize(raw, conn)
            if c is None:
                # After dropping NEOCP candidates, any remaining
                # parse failure is genuinely anomalous — log and skip.
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
