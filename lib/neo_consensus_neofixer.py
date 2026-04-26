"""NEOfixer NEO source ingestor (NEOfixer /targets/ → css_neo_consensus).

NEOfixer (https://neofixer.arizona.edu/, U. of Arizona) is an
observational-priority service. Its target list for site code 500
(geocenter / "all NEOs") is the bulk endpoint we want:

    https://neofixerapi.arizona.edu/targets/?site=500&q-max=1.3

The ``q-max=1.3`` filter is important. CSS intentionally includes a
thin shell of Mars Crossers in its operational target list (orbits
that may evolve toward q ≤ 1.3 AU as fit precision improves), so
without ``q-max`` we'd ingest those too. The user's stated intent is
"NEOs only" — q ≤ 1.3.

NEOfixer is paradigmatically distinct from the other three sources:
its underlying orbit-fitting pipeline is independent (separate from
MPC, JPL, ESA), and the list also tracks NEOCP candidates that
haven't received a formal MPC designation yet. Those NEOCP
candidates carry NEOfixer-internal packed designations (e.g.
``"P22mVBC"``) which ``mpc-designation`` cannot parse — for those we
record a "weak" membership row (``desig_parsed=FALSE``, ``primary_desig``
set to the raw packed form). They show up as NEOfixer-only entries
in cross-source queries, which is accurate: they ARE genuinely
NEOfixer-only until MPC ingests them.

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


def _parse_neofixer_list(path: str) -> List[str]:
    """Return the list of packed designations from the cached JSON-RPC response."""
    with open(path) as f:
        data = json.load(f)
    result = data.get("result", {})
    return list(result.get("ids", []))


def _weak_canonical(raw: str) -> Canonical:
    """Last-resort Canonical when mpc-designation can't parse the input.

    Used for NEOCP-style packings (e.g. ``"P22mVBC"``) that NEOfixer
    tracks pre-MPC-designation. The row joins MPC/CNEOS/NEOCC only by
    coincidence (different sources would have to use the same packed
    string), which they essentially never do — so these land as
    NEOfixer-only members, accurately.
    """
    return Canonical(
        primary_desig=raw,
        packed_desig=None,
        permid=None,
        raw_string=raw,
        desig_parsed=False,
        orbit_in_mpc=False,
        is_comet=False,
    )


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
        ids = _parse_neofixer_list(path)
        print(f"Parsed {len(ids):,} NEOfixer ids")

        canonicals: List[Canonical] = []
        n_weak = 0
        for raw in ids:
            c = canonicalize(raw, conn)
            if c is None:
                c = _weak_canonical(raw)
                n_weak += 1
            canonicals.append(c)
        if n_weak:
            print(f"Weak (desig_parsed=False) rows: {n_weak} "
                  f"— typically NEOCP candidates not yet in MPC")

        now = datetime.now(tz=timezone.utc)
        n_upserted = upsert_membership(conn, SOURCE, canonicals, now=now)
        conn.commit()

        # The schema's `n_unresolved` slot was designed for parser-rejected
        # rows; for NEOfixer we don't *reject*, we record weakly. Reuse the
        # field to surface the weak count so v_source_health stays useful.
        finish_run(
            conn, SOURCE, started_at, status="ok",
            n_rows=n_upserted, n_unresolved=n_weak,
        )
        conn.commit()
        return n_upserted, n_weak
    except Exception as e:
        conn.rollback()
        finish_run(
            conn, SOURCE, started_at, status="fail",
            error=f"{type(e).__name__}: {e}",
        )
        conn.commit()
        raise
