"""
PHA.txt catalog loader — authoritative PHA list from the MPC.

The MPC's PHA.txt flat file lists all objects classified as Potentially
Hazardous Asteroids (H <= 22.0 and Earth MOID <= 0.05 AU).  Since the
earth_moid column in mpc_orbits is NULL for ~70% of rows, using the
database column alone undercounts PHAs (~1,176 vs ~2,500).  This module
provides the authoritative set by downloading PHA.txt directly.

The resolution cache (.pha_cache.csv) maps:
    unpacked_provisional_designation -> True

This file is rebuilt when --refresh is passed or the cache expires.
At normal startup, only the CSV is read — no DB connection needed.

Requires: mpc_designation (pip install from rlseaman/MPC_designations)

Usage:
    from lib.pha_catalog import load_pha_set

    # Returns set of unpacked provisional designations
    pha_set = load_pha_set(cache_dir, force_refresh=False)
"""

import os
import time

import pandas as pd
from mpc_designation import unpack

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHA_URL = "https://minorplanetcenter.net/iau/MPCORB/PHA.txt"
_CACHE_MAX_AGE_SEC = 86400  # 1 day

# ---------------------------------------------------------------------------
# PHA.txt download and parse
# ---------------------------------------------------------------------------


def _download_pha_txt(cache_dir):
    """Download PHA.txt to cache_dir/.pha_raw.txt if stale or missing."""
    import urllib.request

    path = os.path.join(cache_dir, ".pha_raw.txt")
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SEC:
            return path
    print(f"Downloading {PHA_URL}...")
    urllib.request.urlretrieve(PHA_URL, path)
    print(f"Saved PHA.txt ({os.path.getsize(path) / 1e6:.1f} MB)")
    return path


def _parse_pha_txt(path):
    """Parse PHA.txt MPCORB fixed-width format.

    Returns list of (packed_desig, is_numbered, number_str).
    """
    rows = []
    with open(path) as f:
        for line in f:
            if len(line) < 7 or not line[0].strip():
                continue
            packed = line[0:7].rstrip()

            is_numbered = (packed.isdigit()
                           or (len(packed) == 5 and packed[0].isalpha()
                               and packed[1:].isdigit())
                           or packed.startswith("~"))
            number = None
            if is_numbered:
                try:
                    number = unpack(packed)
                except Exception:
                    pass

            rows.append((packed, is_numbered, number))
    return rows


# ---------------------------------------------------------------------------
# Resolution cache: set of unpacked provisional designations
# ---------------------------------------------------------------------------


def _build_pha_cache(cache_dir, pha_path):
    """Build the resolution cache: set of unpacked provisional designations.

    For unnumbered objects: unpack the packed designation directly.
    For numbered objects: look up in numbered_identifications to get
    the unpacked provisional designation.

    Requires a DB connection (only called during --refresh).
    """
    from lib.db import connect, timed_query

    parsed = _parse_pha_txt(pha_path)

    numbered = [(packed, num) for packed, is_num, num in parsed
                if is_num and num]
    unnumbered = [(packed,) for packed, is_num, _ in parsed
                  if not is_num]

    # Resolve unnumbered
    pha_desigs = set()
    for (packed,) in unnumbered:
        try:
            desig = unpack(packed)
        except Exception:
            continue
        pha_desigs.add(desig)

    # Resolve numbered via numbered_identifications
    numbers = [num for _, num in numbered]
    print(f"Resolving {len(numbers):,} numbered PHAs via "
          f"numbered_identifications...")

    with connect() as conn:
        ni = timed_query(conn, """
            SELECT permid,
                   unpacked_primary_provisional_designation AS unpacked_prov
            FROM numbered_identifications
        """, label="numbered_identifications")

    ni_lookup = dict(zip(ni["permid"], ni["unpacked_prov"]))

    matched = 0
    for packed, num in numbered:
        unpacked_prov = ni_lookup.get(num)
        if unpacked_prov:
            pha_desigs.add(unpacked_prov)
            matched += 1

    print(f"Resolved {matched:,}/{len(numbered):,} numbered PHAs")

    # Write cache CSV
    cache_file = os.path.join(cache_dir, ".pha_cache.csv")
    df = pd.DataFrame(sorted(pha_desigs), columns=["designation"])
    df.to_csv(cache_file, index=False)
    print(f"Cached {len(df):,} PHA designations to {cache_file}")

    return pha_desigs


def load_pha_set(cache_dir, force_refresh=False):
    """Load PHA designations as a set of unpacked provisional designations.

    Returns set[str].  Designations in the set are in PHA.txt.

    The resolution cache is rebuilt when force_refresh=True or when
    the cache file is older than 1 day.
    """
    cache_file = os.path.join(cache_dir, ".pha_cache.csv")

    if not force_refresh and os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < _CACHE_MAX_AGE_SEC:
            df = pd.read_csv(cache_file)
            pha_set = set(df["designation"])
            print(f"Loaded {len(pha_set):,} cached PHA designations "
                  f"(age: {age/3600:.1f} h)")
            return pha_set

    # Need to rebuild
    pha_path = _download_pha_txt(cache_dir)
    return _build_pha_cache(cache_dir, pha_path)
