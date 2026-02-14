"""
Match NEA.txt against mpc_orbits to understand designation alignment.

Downloads NEA.txt (if not cached), parses the MPCORB fixed-width format,
and cross-references against the mpc_orbits table via
numbered_identifications for numbered objects.

Usage:
    venv/bin/python3 sandbox/match_nea_txt.py
"""

import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from mpc_designation import pack, unpack
from lib.db import connect, timed_query

# ---------------------------------------------------------------------------
# NEA.txt parsing
# ---------------------------------------------------------------------------

NEA_URL = "https://minorplanetcenter.net/iau/MPCORB/NEA.txt"
NEA_CACHE = "/tmp/NEA.txt"


def download_nea_txt(path=NEA_CACHE):
    """Download NEA.txt if not already cached."""
    if os.path.exists(path):
        print(f"Using cached {path}")
        return path
    print(f"Downloading {NEA_URL}...")
    urllib.request.urlretrieve(NEA_URL, path)
    print(f"Saved to {path}")
    return path


def parse_nea_txt(path=NEA_CACHE):
    """Parse NEA.txt MPCORB fixed-width format.

    Returns DataFrame with columns:
        packed_desig: 7-char packed designation (as in file)
        unpacked_desig: human-readable designation
        h_nea: absolute magnitude (NaN for 99.99 sentinel)
        is_numbered: bool
        number: asteroid number as string (or None)
    """
    rows = []
    with open(path) as f:
        for line in f:
            if len(line) < 7 or not line[0].strip():
                continue  # skip blank/header lines
            packed = line[0:7]
            h_str = line[8:13].strip()
            try:
                h = float(h_str)
            except (ValueError, IndexError):
                h = float("nan")
            # Treat 99.99 as missing
            if h > 90:
                h = float("nan")

            try:
                unpacked = unpack(packed)
            except Exception:
                unpacked = packed.strip()

            # Determine if numbered: pure digits, letter-prefixed digits,
            # or tilde-prefixed (>= 620000)
            stripped = packed.strip()
            is_numbered = (stripped.isdigit()
                           or (len(stripped) == 5 and stripped[0].isalpha()
                               and stripped[1:].isdigit())
                           or stripped.startswith("~"))

            number = unpacked if is_numbered else None

            rows.append({
                "packed_desig_nea": packed.rstrip(),
                "unpacked_desig_nea": unpacked,
                "h_nea": h,
                "is_numbered_nea": is_numbered,
                "number_nea": number,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def load_mpc_orbits_neos(conn):
    """Load NEO rows from mpc_orbits with numbering info."""
    sql = """
    SELECT
        mo.packed_primary_provisional_designation AS packed_desig_mpc,
        mo.unpacked_primary_provisional_designation AS unpacked_desig_mpc,
        mo.h AS h_mpc,
        mo.q, mo.e,
        ni.permid AS number_mpc
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
        ON ni.packed_primary_provisional_designation
         = mo.packed_primary_provisional_designation
    WHERE mo.q < 1.32 OR mo.orbit_type_int IN (0, 1, 2, 3, 20)
    """
    return timed_query(conn, sql, label="mpc_orbits NEOs")


def load_numbered_identifications(conn):
    """Load the full numbering table for bridging designations."""
    sql = """
    SELECT
        permid,
        packed_primary_provisional_designation AS packed_prov
    FROM numbered_identifications
    """
    return timed_query(conn, sql, label="numbered_identifications")


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match(nea_df, mpc_df, ni_df):
    """Match NEA.txt rows against mpc_orbits rows.

    Strategy:
    1. Numbered NEA.txt objects: use number -> numbered_identifications
       -> packed_prov -> mpc_orbits
    2. Unnumbered NEA.txt objects: match packed_desig directly

    Returns:
        merged: DataFrame with all NEA.txt rows + matched mpc_orbits info
        unmatched_nea: NEA.txt rows not found in mpc_orbits
        unmatched_mpc: mpc_orbits rows not found in NEA.txt
    """
    # Build number -> packed_prov lookup from numbered_identifications
    ni_lookup = ni_df.set_index("permid")["packed_prov"].to_dict()

    # For numbered NEA.txt objects, resolve to provisional packed desig
    def resolve_packed_prov(row):
        if row["is_numbered_nea"] and row["number_nea"]:
            return ni_lookup.get(row["number_nea"])
        return row["packed_desig_nea"]

    nea_df = nea_df.copy()
    nea_df["match_key"] = nea_df.apply(resolve_packed_prov, axis=1)

    # Build mpc lookup by packed_desig_mpc
    mpc_lookup = mpc_df.set_index("packed_desig_mpc")

    # Match
    matched_rows = []
    unmatched_nea_rows = []
    mpc_matched_keys = set()

    for _, nea_row in nea_df.iterrows():
        key = nea_row["match_key"]
        if key and key in mpc_lookup.index:
            mpc_row = mpc_lookup.loc[key]
            if isinstance(mpc_row, pd.DataFrame):
                mpc_row = mpc_row.iloc[0]  # take first if duplicates
            combined = {**nea_row.to_dict(), **mpc_row.to_dict()}
            matched_rows.append(combined)
            mpc_matched_keys.add(key)
        else:
            unmatched_nea_rows.append(nea_row.to_dict())

    merged = pd.DataFrame(matched_rows)
    unmatched_nea = pd.DataFrame(unmatched_nea_rows)

    # mpc_orbits rows not matched by any NEA.txt row
    unmatched_mpc = mpc_df[~mpc_df["packed_desig_mpc"].isin(mpc_matched_keys)]

    return merged, unmatched_nea, unmatched_mpc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    download_nea_txt()

    print("\n=== Parsing NEA.txt ===")
    nea_df = parse_nea_txt()
    n_numbered = nea_df["is_numbered_nea"].sum()
    n_unnumbered = (~nea_df["is_numbered_nea"]).sum()
    print(f"NEA.txt: {len(nea_df):,} objects "
          f"({n_numbered:,} numbered, {n_unnumbered:,} unnumbered)")
    print(f"  H=NaN (99.99 or missing): "
          f"{nea_df['h_nea'].isna().sum():,}")

    print("\n=== Loading mpc_orbits NEOs ===")
    with connect() as conn:
        mpc_df = load_mpc_orbits_neos(conn)
        ni_df = load_numbered_identifications(conn)
    n_mpc_numbered = mpc_df["number_mpc"].notna().sum()
    print(f"mpc_orbits: {len(mpc_df):,} NEOs "
          f"({n_mpc_numbered:,} numbered, "
          f"{len(mpc_df) - n_mpc_numbered:,} unnumbered)")
    print(f"numbered_identifications: {len(ni_df):,} rows")

    print("\n=== Matching ===")
    merged, unmatched_nea, unmatched_mpc = match(nea_df, mpc_df, ni_df)

    print(f"\nResults:")
    print(f"  Matched:           {len(merged):,}")
    print(f"  In NEA.txt only:   {len(unmatched_nea):,}")
    print(f"  In mpc_orbits only:{len(unmatched_mpc):,}")

    # Analyze unmatched NEA.txt
    if len(unmatched_nea) > 0:
        print(f"\n--- NEA.txt objects not found in mpc_orbits ---")
        print(f"  Numbered: {unmatched_nea['is_numbered_nea'].sum()}")
        print(f"  Unnumbered: {(~unmatched_nea['is_numbered_nea']).sum()}")
        # Show some examples
        print(f"\n  First 20:")
        for _, row in unmatched_nea.head(20).iterrows():
            print(f"    {row['unpacked_desig_nea']:20s} "
                  f"(packed: {row['packed_desig_nea']}) "
                  f"H={row['h_nea']:.2f}" if pd.notna(row['h_nea'])
                  else f"    {row['unpacked_desig_nea']:20s} "
                       f"(packed: {row['packed_desig_nea']}) H=?")

    # Analyze H magnitude differences for matched objects
    if len(merged) > 0:
        both_valid = merged[
            merged["h_nea"].notna() & merged["h_mpc"].notna()
            & (merged["h_mpc"] > 0)
        ]
        if len(both_valid) > 0:
            diff = (both_valid["h_mpc"] - both_valid["h_nea"]).abs()
            print(f"\n--- H magnitude comparison (matched, both valid) ---")
            print(f"  N with both valid H:  {len(both_valid):,}")
            print(f"  Exact match (|dH|=0): {(diff == 0).sum():,}")
            print(f"  Close (|dH| < 0.1):   {(diff < 0.1).sum():,}")
            print(f"  Differ (|dH| >= 0.1): {(diff >= 0.1).sum():,}")
            print(f"  Median |dH|:          {diff.median():.3f}")
            print(f"  Max |dH|:             {diff.max():.2f}")

            # Show largest discrepancies
            big_diff = both_valid[diff >= 1.0].copy()
            big_diff["h_diff"] = diff[diff >= 1.0]
            if len(big_diff) > 0:
                print(f"\n  Objects with |dH| >= 1.0: {len(big_diff)}")
                big_diff = big_diff.sort_values("h_diff", ascending=False)
                for _, row in big_diff.head(15).iterrows():
                    print(f"    {row['unpacked_desig_nea']:20s} "
                          f"NEA.txt H={row['h_nea']:5.2f}  "
                          f"mpc_orbits H={row['h_mpc']:6.2f}  "
                          f"dH={row['h_diff']:+.2f}")

        # H in mpc_orbits but sentinel in NEA.txt
        mpc_has_nea_missing = merged[
            merged["h_nea"].isna() & merged["h_mpc"].notna()
            & (merged["h_mpc"] > 0)
        ]
        if len(mpc_has_nea_missing) > 0:
            print(f"\n--- mpc_orbits has H but NEA.txt says 99.99 ---")
            print(f"  Count: {len(mpc_has_nea_missing)}")
            print(f"  mpc_orbits H range: "
                  f"{mpc_has_nea_missing['h_mpc'].min():.2f} to "
                  f"{mpc_has_nea_missing['h_mpc'].max():.2f}")

        # Sentinel H in mpc_orbits
        mpc_sentinel = merged[
            (merged["h_mpc"] <= 0) | merged["h_mpc"].isna()
        ]
        if len(mpc_sentinel) > 0:
            print(f"\n--- mpc_orbits H <= 0 or NULL ---")
            print(f"  Count: {len(mpc_sentinel)}")

    # Summary of unmatched mpc_orbits
    if len(unmatched_mpc) > 0:
        print(f"\n--- mpc_orbits objects not in NEA.txt ---")
        n_num = unmatched_mpc["number_mpc"].notna().sum()
        print(f"  Numbered: {n_num}")
        print(f"  Unnumbered: {len(unmatched_mpc) - n_num}")
        # Check q distribution — are they borderline NEOs?
        print(f"\n  q distribution:")
        print(f"    q <= 1.30: {(unmatched_mpc['q'] <= 1.30).sum()}")
        print(f"    1.30 < q <= 1.32: "
              f"{((unmatched_mpc['q'] > 1.30) & (unmatched_mpc['q'] <= 1.32)).sum()}")
        print(f"    q > 1.32 (orbit_type only): "
              f"{(unmatched_mpc['q'] > 1.32).sum()}")
        print(f"\n  First 20 unnumbered with q <= 1.30:")
        subset = unmatched_mpc[
            (unmatched_mpc["number_mpc"].isna())
            & (unmatched_mpc["q"] <= 1.30)
        ].head(20)
        for _, row in subset.iterrows():
            print(f"    {row['unpacked_desig_mpc']:20s} "
                  f"(packed: {row['packed_desig_mpc']}) "
                  f"q={row['q']:.3f} H={row['h_mpc']}")


if __name__ == "__main__":
    main()
