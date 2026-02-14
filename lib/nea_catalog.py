"""
NEA.txt catalog loader — authoritative H magnitudes from the MPC.

The MPC's NEA.txt flat file (MPCORB format) is currently the most reliable
source of NEA orbital elements and absolute magnitudes, pending further
work on the mpc_orbits PostgreSQL table.  This module downloads, caches,
and parses NEA.txt, resolving designations through numbered_identifications
so that H magnitudes can be matched to the unpacked provisional
designations used throughout the dashboard.

The resolution cache (.nea_h_cache.csv) maps:
    unpacked_provisional_designation -> h_nea

This file is rebuilt when --refresh is passed or the cache expires.
At normal startup, only the CSV is read — no DB connection needed.

Requires: mpc_designation (pip install from rlseaman/MPC_designations)

Usage:
    from lib.nea_catalog import load_nea_h_lookup

    # Returns dict[designation -> h_value]
    h_lookup = load_nea_h_lookup(cache_dir, force_refresh=False)
"""

import os
import time
import urllib.request

import numpy as np
import pandas as pd
from mpc_designation import unpack

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEA_URL = "https://minorplanetcenter.net/iau/MPCORB/NEA.txt"
_CACHE_MAX_AGE_SEC = 86400  # 1 day

# ---------------------------------------------------------------------------
# NEA.txt download and parse
# ---------------------------------------------------------------------------


def _download_nea_txt(cache_dir):
    """Download NEA.txt to cache_dir/.nea_raw.txt if stale or missing."""
    path = os.path.join(cache_dir, ".nea_raw.txt")
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SEC:
            return path
    print(f"Downloading {NEA_URL}...")
    urllib.request.urlretrieve(NEA_URL, path)
    print(f"Saved NEA.txt ({os.path.getsize(path) / 1e6:.1f} MB)")
    return path


def _parse_nea_txt(path):
    """Parse NEA.txt MPCORB fixed-width format.

    Returns list of (packed_desig, h_value, is_numbered, number_str).
    H = 99.99 is treated as NaN.  H <= 0 is treated as NaN.
    """
    rows = []
    with open(path) as f:
        for line in f:
            if len(line) < 13 or not line[0].strip():
                continue
            packed = line[0:7].rstrip()
            h_str = line[8:13].strip()
            try:
                h = float(h_str)
            except ValueError:
                h = float("nan")
            if h > 90 or h <= 0:
                h = float("nan")

            # Determine if this is a numbered designation
            is_numbered = (packed.isdigit()
                           or (len(packed) == 5 and packed[0].isalpha()
                               and packed[1:].isdigit())
                           or packed.startswith("~"))
            number = None
            if is_numbered:
                try:
                    number = unpack(packed)  # e.g. "433", "620000"
                except Exception:
                    pass

            rows.append((packed, h, is_numbered, number))
    return rows


# ---------------------------------------------------------------------------
# Resolution cache: designation -> h_nea
# ---------------------------------------------------------------------------


def _build_h_cache(cache_dir, nea_path):
    """Build the resolution cache: unpacked_prov_desig -> h_nea.

    For unnumbered objects: unpack the packed designation directly.
    For numbered objects: look up in numbered_identifications to get
    the unpacked provisional designation.

    Requires a DB connection (only called during --refresh).
    """
    from lib.db import connect, timed_query

    parsed = _parse_nea_txt(nea_path)

    # Separate numbered and unnumbered
    numbered = [(packed, h, num) for packed, h, is_num, num in parsed
                if is_num and num]
    unnumbered = [(packed, h) for packed, h, is_num, _ in parsed
                  if not is_num]

    # Resolve unnumbered: unpack packed provisional -> unpacked provisional
    h_map = {}
    for packed, h in unnumbered:
        try:
            desig = unpack(packed)
        except Exception:
            continue
        if not np.isnan(h):
            h_map[desig] = h
        else:
            h_map[desig] = None  # known NEA but no reliable H

    # Resolve numbered: query numbered_identifications for batch lookup
    numbers = [num for _, _, num in numbered]
    print(f"Resolving {len(numbers):,} numbered NEAs via "
          f"numbered_identifications...")

    with connect() as conn:
        # Load all numbered_identifications — fast (~1s for 876K rows)
        # and avoids array parameter edge cases
        ni = timed_query(conn, """
            SELECT permid,
                   unpacked_primary_provisional_designation AS unpacked_prov
            FROM numbered_identifications
        """, label="numbered_identifications")

    ni_lookup = dict(zip(ni["permid"], ni["unpacked_prov"]))

    matched_numbered = 0
    for packed, h, num in numbered:
        unpacked_prov = ni_lookup.get(num)
        if unpacked_prov:
            if not np.isnan(h):
                h_map[unpacked_prov] = h
            else:
                h_map[unpacked_prov] = None
            matched_numbered += 1

    print(f"Resolved {matched_numbered:,}/{len(numbered):,} numbered NEAs")

    # Write cache CSV
    cache_file = os.path.join(cache_dir, ".nea_h_cache.csv")
    rows = [(desig, h) for desig, h in h_map.items()]
    df = pd.DataFrame(rows, columns=["designation", "h_nea"])
    df.to_csv(cache_file, index=False)
    print(f"Cached {len(df):,} NEA.txt H values to {cache_file}")

    return h_map


def load_nea_h_lookup(cache_dir, force_refresh=False):
    """Load NEA.txt H magnitudes keyed by unpacked provisional designation.

    Returns dict[designation -> h_value].  Designations with H=99.99 in
    NEA.txt map to None (known NEA, unreliable H).  Designations not in
    the dict are not in the curated NEA catalog.

    The resolution cache is rebuilt when force_refresh=True or when
    the cache file is older than 1 day.
    """
    cache_file = os.path.join(cache_dir, ".nea_h_cache.csv")

    # Check if resolution cache is fresh
    if not force_refresh and os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < _CACHE_MAX_AGE_SEC:
            df = pd.read_csv(cache_file)
            h_map = {}
            for _, row in df.iterrows():
                h_map[row["designation"]] = (row["h_nea"]
                                             if pd.notna(row["h_nea"])
                                             else None)
            print(f"Loaded {len(h_map):,} cached NEA.txt H values "
                  f"(age: {age/3600:.1f} h)")
            return h_map

    # Need to rebuild — download NEA.txt and resolve designations
    nea_path = _download_nea_txt(cache_dir)
    return _build_h_cache(cache_dir, nea_path)
