"""
Authoritative NEO list builder — per-object reconciliation from MPC and JPL.

Two independent sources maintain curated lists of Near-Earth Objects:
  - MPC NEA.txt: https://minorplanetcenter.net/iau/MPCORB/NEA.txt
  - JPL SBDB:    https://ssd-api.jpl.nasa.gov/sbdb_query.api

This module downloads both, parses every object with its properties,
cross-matches on designation, and produces a unified DataFrame where
each row is one NEO with source-specific columns side by side.

The resulting list is the foundation for all downstream analysis:
discovery statistics, completeness, follow-up timing, etc.

Usage:
    from lib.neo_list import build_neo_list, load_neo_list

    # Build from scratch (downloads both sources, ~30s)
    df = build_neo_list(cache_dir="app")

    # Load from cache (instant)
    df = load_neo_list(cache_dir="app")

    # Filter by provenance
    mpc_only = df[df["in_mpc"] & ~df["in_jpl"]]
    jpl_only = df[~df["in_mpc"] & df["in_jpl"]]
    both     = df[df["in_mpc"] & df["in_jpl"]]
"""

import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from mpc_designation import unpack

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEA_URL = "https://minorplanetcenter.net/iau/MPCORB/NEA.txt"
SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
SBDB_CLASSES = "IEO,ATE,APO,AMO"

_CACHE_MAX_AGE_SEC = 86400  # 1 day

# ---------------------------------------------------------------------------
# MPC NEA.txt parser
# ---------------------------------------------------------------------------

# MPCORB fixed-width column definitions (0-indexed)
# Reference: https://minorplanetcenter.net/iau/info/MPOrbitFormat.html
_MPCORB_COLS = {
    "packed_desig":   (0, 7),
    "h":              (8, 13),
    "g":              (14, 19),
    "epoch":          (20, 25),
    "mean_anom":      (26, 35),
    "arg_peri":       (37, 46),
    "long_node":      (48, 57),
    "incl":           (59, 68),
    "ecc":            (70, 79),
    "mean_daily_mot": (80, 91),
    "semi_major_a":   (92, 103),
    "orbit_type":     (161, 163),
    "readable_desig": (166, 194),
}


def _download_file(url, path):
    """Download a URL to a local path."""
    print(f"Downloading {url}...")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CSS_MPC_toolkit/1.0")
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(path, "wb") as f:
            f.write(resp.read())
    size_mb = os.path.getsize(path) / 1e6
    print(f"Saved {size_mb:.1f} MB to {path}")
    return path


def _parse_nea_txt(path):
    """Parse every object from NEA.txt into a list of dicts.

    Each dict has: packed_desig, unpacked_desig, is_numbered, number,
    h, g, a, e, i, q, mean_anom, arg_peri, long_node, readable_desig.
    """
    rows = []
    with open(path) as f:
        for line in f:
            if len(line) < 103 or not line[0].strip():
                continue

            packed = line[0:7].rstrip()

            # Parse numeric fields
            def _fld(start, end):
                s = line[start:end].strip()
                if not s:
                    return None
                try:
                    return float(s)
                except ValueError:
                    return None

            h = _fld(8, 13)
            g = _fld(14, 19)
            a = _fld(92, 103)
            e = _fld(70, 79)
            i = _fld(59, 68)
            mean_anom = _fld(26, 35)
            arg_peri = _fld(37, 46)
            long_node = _fld(48, 57)

            # Sentinel H values
            if h is not None and (h > 90 or h <= 0):
                h = None

            # Derive q from a and e
            q = None
            if a is not None and e is not None and e < 1:
                q = a * (1.0 - e)

            # Aphelion Q
            cap_q = None
            if a is not None and e is not None and e < 1:
                cap_q = a * (1.0 + e)

            # Readable designation (trailing part of the line)
            readable = line[166:194].strip() if len(line) > 166 else ""

            # Determine if numbered
            is_numbered = (packed.isdigit()
                           or (len(packed) >= 2 and packed[0].isalpha()
                               and packed[1:].isdigit())
                           or packed.startswith("~"))
            number = None
            unpacked = None
            if is_numbered:
                try:
                    number = unpack(packed)
                except Exception:
                    pass
                # For numbered objects, unpacked_desig will be resolved
                # later via numbered_identifications or from readable_desig
            else:
                try:
                    unpacked = unpack(packed)
                except Exception:
                    unpacked = packed

            rows.append({
                "packed_desig": packed,
                "unpacked_desig": unpacked,
                "is_numbered": is_numbered,
                "number": number,
                "readable_desig": readable,
                "h_mpc": h,
                "g_mpc": g,
                "a_mpc": a,
                "e_mpc": e,
                "i_mpc": i,
                "q_mpc": q,
                "cap_q_mpc": cap_q,
                "mean_anom_mpc": mean_anom,
                "arg_peri_mpc": arg_peri,
                "long_node_mpc": long_node,
            })
    return rows


def fetch_mpc_neos(cache_dir, force=False):
    """Download and parse NEA.txt into a DataFrame.

    Returns DataFrame with one row per NEA.txt object.
    Numbered objects have unpacked_desig = None (needs DB resolution).
    """
    raw_path = os.path.join(cache_dir, ".nea_raw.txt")

    if not force and os.path.exists(raw_path):
        age = time.time() - os.path.getmtime(raw_path)
        if age < _CACHE_MAX_AGE_SEC:
            print(f"Using cached NEA.txt (age: {age/3600:.1f} h)")
        else:
            _download_file(NEA_URL, raw_path)
    else:
        _download_file(NEA_URL, raw_path)

    rows = _parse_nea_txt(raw_path)
    df = pd.DataFrame(rows)
    print(f"Parsed {len(df):,} objects from NEA.txt "
          f"({df['is_numbered'].sum():,} numbered, "
          f"{(~df['is_numbered']).sum():,} unnumbered)")
    return df


# ---------------------------------------------------------------------------
# JPL SBDB bulk query
# ---------------------------------------------------------------------------

def fetch_jpl_neos():
    """Fetch all NEOs from JPL SBDB with orbital elements and properties.

    Returns DataFrame with one row per NEO.  The 'pdes' column is the
    primary designation: number as string for numbered objects, or
    provisional designation for unnumbered.
    """
    fields = ",".join([
        "pdes",         # primary designation
        "name",         # name (if any)
        "class",        # orbit class (APO, AMO, ATE, IEO)
        "H",            # absolute magnitude
        "e",            # eccentricity
        "a",            # semi-major axis (AU)
        "q",            # perihelion distance (AU)
        "i",            # inclination (deg)
        "om",           # longitude of ascending node (deg)
        "w",            # argument of perihelion (deg)
        "moid",         # Earth MOID (AU)
        "pha",          # PHA flag (Y/N)
        "condition_code",
    ])
    params = urllib.parse.urlencode({
        "fields": fields,
        "sb-class": SBDB_CLASSES,
        "full-prec": "0",
    })
    url = f"{SBDB_URL}?{params}"
    print(f"Fetching all NEOs from SBDB ({SBDB_CLASSES})...")

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CSS_MPC_toolkit/1.0")
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode())

    field_names = data["fields"]
    rows = data["data"]
    df = pd.DataFrame(rows, columns=field_names)
    print(f"Received {len(df):,} NEOs from SBDB")

    # Convert numeric columns
    for col in ["H", "e", "a", "q", "i", "om", "w", "moid"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derive aphelion Q
    df["Q"] = df["a"] * (1.0 + df["e"])

    # Flag numbered vs unnumbered
    df["is_numbered"] = df["pdes"].str.match(r"^\d+$")

    # Rename to avoid collisions when merging
    df = df.rename(columns={
        "H": "h_jpl",
        "e": "e_jpl",
        "a": "a_jpl",
        "q": "q_jpl",
        "i": "i_jpl",
        "om": "long_node_jpl",
        "w": "arg_peri_jpl",
        "Q": "cap_q_jpl",
        "moid": "earth_moid_jpl",
        "pha": "pha_jpl",
        "class": "orbit_class_jpl",
        "condition_code": "condition_code_jpl",
    })

    return df


# ---------------------------------------------------------------------------
# Designation resolution helpers
# ---------------------------------------------------------------------------

def _resolve_numbered_designations(mpc_df, jpl_df):
    """Resolve numbered objects to unpacked provisional designations.

    For MPC: numbered objects have unpacked_desig = None; resolve via
    the readable_desig field (which often contains the provisional) or
    by matching against JPL's pdes.

    For JPL: numbered objects have pdes = number string.

    Both need to be resolved to a common key for cross-matching.
    We use the MPC number as the join key for numbered objects,
    and the unpacked provisional designation for unnumbered.
    """
    # For unnumbered MPC objects, unpacked_desig is already set
    # For unnumbered JPL objects, pdes is the provisional designation

    # Build a lookup: number -> unpacked provisional from MPC readable_desig
    # readable_desig looks like "(433) Eros" or "(887) Alinda" or
    # "2024 AA" for unnumbered
    pass  # Resolution happens in build_neo_list


# ---------------------------------------------------------------------------
# Cross-match and merge
# ---------------------------------------------------------------------------

def _classify_orbit(a, e, q, cap_q):
    """Classify an orbit as Atira/Aten/Apollo/Amor from elements."""
    if a is None or e is None or e >= 1:
        return "Unclassified"
    if q is None:
        q = a * (1.0 - e)
    if cap_q is None:
        cap_q = a * (1.0 + e)
    if a < 1.0 and cap_q < 0.983:
        return "Atira"
    if a < 1.0:
        return "Aten"
    if q < 1.017:
        return "Apollo"
    if q < 1.3:
        return "Amor"
    return "Other"


def build_neo_list(cache_dir, force=False):
    """Build the unified per-object NEO list from MPC and JPL.

    Returns a DataFrame with one row per unique NEO, columns:
        designation     - common key (unpacked provisional or number)
        packed_desig    - MPC packed designation
        number          - MPC permanent number (if numbered)
        in_mpc          - present in NEA.txt
        in_jpl          - present in SBDB
        source          - "both", "mpc", or "jpl"
        h_mpc, h_jpl    - H magnitude from each source
        a_mpc, a_jpl    - semi-major axis
        e_mpc, e_jpl    - eccentricity
        i_mpc, i_jpl    - inclination
        q_mpc, q_jpl    - perihelion distance
        cap_q_mpc, cap_q_jpl - aphelion distance
        earth_moid_jpl  - Earth MOID from SBDB
        pha_jpl         - PHA flag from SBDB
        orbit_class     - computed from best available elements
        orbit_class_jpl - JPL's classification
    """
    from datetime import datetime, timezone

    # Fetch both sources
    mpc = fetch_mpc_neos(cache_dir, force=force)
    jpl = fetch_jpl_neos()

    # --- Resolve designations to a common key ---
    # Strategy: use unpacked provisional designation as primary key.
    # For unnumbered objects this is straightforward.
    # For numbered objects, we need to find the provisional designation.

    # JPL numbered objects: pdes is the number string.
    # JPL also has a "name" field but it's the name, not the provisional.
    # We need to match numbered objects between MPC and JPL by number,
    # then use MPC's readable_desig to extract the provisional.

    # Step 1: Build number-keyed lookups
    mpc_numbered = mpc[mpc["is_numbered"]].copy()
    mpc_unnumbered = mpc[~mpc["is_numbered"]].copy()
    jpl_numbered = jpl[jpl["is_numbered"]].copy()
    jpl_unnumbered = jpl[~jpl["is_numbered"]].copy()

    # MPC: extract provisional from readable_desig for numbered objects
    # readable_desig looks like "(433) Eros" — but the provisional
    # is actually NOT in this field for numbered objects. We need the
    # packed designation unpacked.  For numbered objects the packed
    # designation IS the number, and the provisional lives elsewhere.
    # We'll use the number as the join key.

    # Step 2: Merge numbered objects by number
    mpc_numbered["_key"] = mpc_numbered["number"].astype(str)
    jpl_numbered["_key"] = jpl_numbered["pdes"].astype(str)

    numbered_merged = pd.merge(
        mpc_numbered, jpl_numbered,
        on="_key", how="outer", suffixes=("_m", "_j"),
        indicator=True,
    )
    numbered_merged["in_mpc"] = numbered_merged["_merge"].isin(
        ["both", "left_only"])
    numbered_merged["in_jpl"] = numbered_merged["_merge"].isin(
        ["both", "right_only"])

    # Use the number as the designation for numbered objects
    numbered_merged["designation"] = numbered_merged["_key"]
    numbered_merged["number"] = numbered_merged["_key"]
    numbered_merged["packed_desig"] = numbered_merged.get(
        "packed_desig", numbered_merged.get("packed_desig_m"))

    # Step 3: Merge unnumbered objects by designation
    # MPC unpacked_desig should match JPL pdes for unnumbered
    mpc_unnumbered["_key"] = mpc_unnumbered["unpacked_desig"]
    jpl_unnumbered["_key"] = jpl_unnumbered["pdes"]

    unnumbered_merged = pd.merge(
        mpc_unnumbered, jpl_unnumbered,
        on="_key", how="outer", suffixes=("_m", "_j"),
        indicator=True,
    )
    unnumbered_merged["in_mpc"] = unnumbered_merged["_merge"].isin(
        ["both", "left_only"])
    unnumbered_merged["in_jpl"] = unnumbered_merged["_merge"].isin(
        ["both", "right_only"])
    unnumbered_merged["designation"] = unnumbered_merged["_key"]
    unnumbered_merged["number"] = None

    # Step 4: Combine numbered and unnumbered
    # Select and rename columns to a common schema
    def _extract(merged, is_numb):
        out = pd.DataFrame()
        out["designation"] = merged["designation"]
        out["number"] = merged["number"] if is_numb else None
        out["packed_desig"] = merged.get(
            "packed_desig_m", merged.get("packed_desig"))
        out["in_mpc"] = merged["in_mpc"]
        out["in_jpl"] = merged["in_jpl"]

        # MPC columns (may have _m suffix from merge)
        for col in ["h_mpc", "g_mpc", "a_mpc", "e_mpc", "i_mpc",
                     "q_mpc", "cap_q_mpc"]:
            src = f"{col}_m" if f"{col}_m" in merged.columns else col
            out[col] = merged[src] if src in merged.columns else None

        # JPL columns (may have _j suffix)
        for col in ["h_jpl", "a_jpl", "e_jpl", "i_jpl", "q_jpl",
                     "cap_q_jpl", "earth_moid_jpl", "pha_jpl",
                     "orbit_class_jpl", "condition_code_jpl"]:
            src = f"{col}_j" if f"{col}_j" in merged.columns else col
            out[col] = merged[src] if src in merged.columns else None

        return out

    df_num = _extract(numbered_merged, True)
    df_unnum = _extract(unnumbered_merged, False)
    df = pd.concat([df_num, df_unnum], ignore_index=True)

    # Step 5: Compute derived columns
    df["source"] = "both"
    df.loc[df["in_mpc"] & ~df["in_jpl"], "source"] = "mpc"
    df.loc[~df["in_mpc"] & df["in_jpl"], "source"] = "jpl"

    # Best H: prefer MPC (NEA.txt is curated), fall back to JPL
    df["h_best"] = df["h_mpc"].fillna(df["h_jpl"])

    # Best elements for classification: prefer JPL (more complete),
    # fall back to MPC
    a_best = df["a_jpl"].fillna(df["a_mpc"])
    e_best = df["e_jpl"].fillna(df["e_mpc"])
    q_best = df["q_jpl"].fillna(df["q_mpc"])
    cap_q_best = df["cap_q_jpl"].fillna(df["cap_q_mpc"])

    df["orbit_class"] = [
        _classify_orbit(a, e, q, cq)
        for a, e, q, cq in zip(a_best, e_best, q_best, cap_q_best)
    ]

    # Step 6: Flag discrepancies
    df["h_diff"] = (df["h_mpc"] - df["h_jpl"]).abs()
    df["q_diff"] = (df["q_mpc"] - df["q_jpl"]).abs()

    # Metadata
    df["list_date"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")

    # Summary
    n_both = (df["source"] == "both").sum()
    n_mpc = (df["source"] == "mpc").sum()
    n_jpl = (df["source"] == "jpl").sum()
    print(f"\nUnified NEO list: {len(df):,} objects")
    print(f"  In both:    {n_both:,}")
    print(f"  MPC only:   {n_mpc:,}")
    print(f"  JPL only:   {n_jpl:,}")

    # H discrepancy summary (where both sources have H)
    has_both_h = df["h_mpc"].notna() & df["h_jpl"].notna()
    if has_both_h.any():
        big_h_diff = (df.loc[has_both_h, "h_diff"] > 0.5).sum()
        print(f"  H differs by >0.5 mag: {big_h_diff:,}"
              f" of {has_both_h.sum():,} with both H values")

    return df


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def save_neo_list(df, cache_dir):
    """Save the unified NEO list to Parquet."""
    path = os.path.join(cache_dir, ".neo_list.parquet")
    df.to_parquet(path, index=False)
    print(f"Saved {len(df):,} NEOs to {path}")
    return path


def load_neo_list(cache_dir, max_age_sec=_CACHE_MAX_AGE_SEC):
    """Load the unified NEO list from cache, or return None if stale."""
    path = os.path.join(cache_dir, ".neo_list.parquet")
    if not os.path.exists(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > max_age_sec:
        return None
    df = pd.read_parquet(path)
    print(f"Loaded {len(df):,} NEOs from cache (age: {age/3600:.1f} h)")
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """Build the NEO list and print a summary."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build unified NEO list from MPC and JPL sources.")
    parser.add_argument("--cache-dir", default="app",
                        help="Directory for cache files (default: app)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download even if cache is fresh")
    parser.add_argument("--mpc-only", action="store_true",
                        help="Show objects in MPC but not JPL")
    parser.add_argument("--jpl-only", action="store_true",
                        help="Show objects in JPL but not MPC")
    parser.add_argument("--h-diff", type=float, default=None,
                        help="Show objects where H differs by more than "
                             "this many magnitudes")
    args = parser.parse_args()

    df = build_neo_list(args.cache_dir, force=args.force)
    save_neo_list(df, args.cache_dir)

    if args.mpc_only:
        subset = df[df["source"] == "mpc"].sort_values(
            "h_mpc", na_position="last")
        print(f"\n{len(subset):,} objects in MPC only:")
        cols = ["designation", "h_mpc", "q_mpc", "e_mpc", "orbit_class"]
        print(subset[cols].head(50).to_string(index=False))

    if args.jpl_only:
        subset = df[df["source"] == "jpl"].sort_values(
            "h_jpl", na_position="last")
        print(f"\n{len(subset):,} objects in JPL only:")
        cols = ["designation", "h_jpl", "q_jpl", "e_jpl",
                "orbit_class_jpl"]
        print(subset[cols].head(50).to_string(index=False))

    if args.h_diff is not None:
        has_both = df["h_mpc"].notna() & df["h_jpl"].notna()
        big = df[has_both & (df["h_diff"] > args.h_diff)].sort_values(
            "h_diff", ascending=False)
        print(f"\n{len(big):,} objects with H diff > {args.h_diff}:")
        cols = ["designation", "h_mpc", "h_jpl", "h_diff", "orbit_class"]
        print(big[cols].head(50).to_string(index=False))


if __name__ == "__main__":
    main()
