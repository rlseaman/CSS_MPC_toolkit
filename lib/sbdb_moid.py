"""
SBDB Earth MOID loader — authoritative MOID values from JPL.

The MPC's mpc_orbits table has earth_moid for only ~37% of NEOs.
JPL's Small-Body Database (SBDB) provides Earth MOID for essentially
all NEOs (~41K objects, only ~130 null) via a single bulk API call.

The resolution cache (.sbdb_moid_cache.csv) maps:
    unpacked_provisional_designation -> earth_moid

This file is rebuilt when --refresh is passed or the cache expires.
At normal startup, only the CSV is read — no DB or API call needed.

Usage:
    from lib.sbdb_moid import load_sbdb_moid_lookup

    # Returns dict[designation -> moid_value]
    moid_lookup = load_sbdb_moid_lookup(cache_dir, force_refresh=False)
"""

import json
import os
import time
import urllib.request

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
# NEO orbital classes: Interior Earth Objects, Atens, Apollos, Amors
SBDB_CLASSES = "IEO,ATE,APO,AMO"
_CACHE_MAX_AGE_SEC = 86400  # 1 day

# ---------------------------------------------------------------------------
# SBDB API query
# ---------------------------------------------------------------------------


def _fetch_sbdb_moid():
    """Fetch Earth MOID for all NEOs from JPL SBDB in a single bulk query.

    Returns list of (pdes, moid_value) tuples.  pdes is the primary
    designation: the number as a string for numbered objects (e.g. "433"),
    or the provisional designation for unnumbered (e.g. "2024 AA").
    """
    params = urllib.parse.urlencode({
        "fields": "pdes,moid",
        "sb-class": SBDB_CLASSES,
    })
    url = f"{SBDB_URL}?{params}"
    print(f"Fetching Earth MOID from SBDB ({SBDB_CLASSES})...")

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CSS_MPC_toolkit/1.0")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())

    fields = data["fields"]
    pdes_idx = fields.index("pdes")
    moid_idx = fields.index("moid")

    rows = []
    for row in data["data"]:
        pdes = row[pdes_idx]
        moid_str = row[moid_idx]
        if pdes and moid_str is not None:
            rows.append((pdes, float(moid_str)))

    print(f"Received {data['count']:,} NEOs from SBDB, "
          f"{len(rows):,} with MOID values")
    return rows


# ---------------------------------------------------------------------------
# Resolution cache: designation -> moid
# ---------------------------------------------------------------------------


def _build_moid_cache(cache_dir):
    """Build the resolution cache: unpacked_prov_desig -> earth_moid.

    For unnumbered objects: pdes is already the unpacked provisional.
    For numbered objects: resolve via numbered_identifications to get
    the unpacked provisional designation used throughout the dashboard.

    Requires a DB connection (only called during --refresh).
    """
    from lib.db import connect, timed_query

    rows = _fetch_sbdb_moid()

    # Separate numbered (pdes is all digits) from unnumbered (provisional)
    numbered = []
    unnumbered = []
    for pdes, moid in rows:
        if pdes.isdigit():
            numbered.append((pdes, moid))
        else:
            unnumbered.append((pdes, moid))

    # Unnumbered: pdes is the unpacked provisional designation
    moid_map = {pdes: moid for pdes, moid in unnumbered}

    # Numbered: resolve via numbered_identifications
    print(f"Resolving {len(numbered):,} numbered NEOs via "
          f"numbered_identifications...")

    with connect() as conn:
        ni = timed_query(conn, """
            SELECT permid,
                   unpacked_primary_provisional_designation AS unpacked_prov
            FROM numbered_identifications
        """, label="numbered_identifications")

    ni_lookup = dict(zip(ni["permid"], ni["unpacked_prov"]))

    matched = 0
    for pdes, moid in numbered:
        unpacked_prov = ni_lookup.get(pdes)
        if unpacked_prov:
            moid_map[unpacked_prov] = moid
            matched += 1

    print(f"Resolved {matched:,}/{len(numbered):,} numbered NEOs")

    # Write cache CSV
    cache_file = os.path.join(cache_dir, ".sbdb_moid_cache.csv")
    df = pd.DataFrame(
        sorted(moid_map.items()),
        columns=["designation", "earth_moid"],
    )
    df.to_csv(cache_file, index=False)
    print(f"Cached {len(df):,} SBDB MOID values to {cache_file}")

    return moid_map


def load_sbdb_moid_lookup(cache_dir, force_refresh=False):
    """Load Earth MOID values keyed by unpacked provisional designation.

    Returns dict[designation -> moid_value].

    The resolution cache is rebuilt when force_refresh=True or when
    the cache file is older than 1 day.
    """
    cache_file = os.path.join(cache_dir, ".sbdb_moid_cache.csv")

    if not force_refresh and os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < _CACHE_MAX_AGE_SEC:
            df = pd.read_csv(cache_file)
            moid_map = dict(zip(df["designation"], df["earth_moid"]))
            print(f"Loaded {len(moid_map):,} cached SBDB MOID values "
                  f"(age: {age/3600:.1f} h)")
            return moid_map

    return _build_moid_cache(cache_dir)
