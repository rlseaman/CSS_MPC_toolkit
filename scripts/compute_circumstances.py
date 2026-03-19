#!/usr/bin/env python
"""Compute discovery circumstances for NEO discovery tracklets.

Reads the base discovery tracklets CSV (from run_pipeline.sh) and
enriches it with observing circumstance columns:

  sun_alt_deg       - Solar altitude at discovery (degrees)
  twilight_class    - Space-based / Nighttime / Astronomical twilight /
                      Nautical twilight / Civil twilight / Daytime /
                      Unknown site
  lunar_elong_deg   - Angular separation from Moon (degrees)
  eclipse_class     - "" / Penumbral eclipse / Partial eclipse /
                      Total eclipse
  eclipse_date      - ISO date of the eclipse (if applicable)

Output: NEO_discovery_tracklets_extra_DDMonYY.csv alongside the input,
with a symlink NEO_discovery_tracklets_extra.csv -> latest dated file.

Usage:
    python scripts/compute_circumstances.py                    # latest symlinked CSV
    python scripts/compute_circumstances.py path/to/input.csv  # specific file
"""

import os
import sys
import argparse
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.db import connect, timed_query
from lib.solar import (sun_altitude, classify_twilight,
                       _observer_latitude, TWILIGHT_ORDER)
from lib.lunar import lunar_elongation, classify_eclipse


def load_station_info():
    """Query obscodes table for observatory coordinates and type."""
    sql = """
    SELECT obscode,
           longitude::double precision,
           rhocosphi::double precision,
           rhosinphi::double precision,
           observations_type
    FROM obscodes
    """
    with connect() as conn:
        return timed_query(conn, sql)


def load_discovery_times(designations):
    """Query obs_sbn for discovery observation UTC timestamps.

    The base CSV has avg_mjd (mean of tracklet) but we need the actual
    first observation time for accurate solar/lunar altitude.
    """
    # Build a temp-table-free approach: pass designations as values
    # For ~44K designations, use a CTE with the packed designation
    sql = """
    WITH neo_list AS (
        SELECT
            mo.unpacked_primary_provisional_designation AS unpacked_desig,
            ni.permid IS NOT NULL AS is_numbered,
            ni.permid AS asteroid_number,
            CASE WHEN ni.permid IS NULL
                 THEN mo.unpacked_primary_provisional_designation
            END AS provisional_desig,
            ni.unpacked_primary_provisional_designation AS num_provid
        FROM mpc_orbits mo
        LEFT JOIN numbered_identifications ni
            ON ni.packed_primary_provisional_designation
             = mo.packed_primary_provisional_designation
        WHERE mo.q < 1.32 OR mo.orbit_type_int IN (0, 1, 2, 3, 20)
    ),
    discovery_obs_all AS (
        SELECT neo.unpacked_desig, neo.is_numbered, neo.asteroid_number,
               obs.stn, obs.obstime
        FROM neo_list neo
        INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
        WHERE neo.is_numbered AND obs.disc = '*'
        UNION ALL
        SELECT neo.unpacked_desig, neo.is_numbered, neo.asteroid_number,
               obs.stn, obs.obstime
        FROM neo_list neo
        INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
        WHERE NOT neo.is_numbered AND obs.disc = '*'
        UNION ALL
        SELECT neo.unpacked_desig, neo.is_numbered, neo.asteroid_number,
               obs.stn, obs.obstime
        FROM neo_list neo
        INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
        WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
    ),
    discovery_info AS (
        SELECT DISTINCT ON (unpacked_desig)
            unpacked_desig, is_numbered, asteroid_number,
            stn AS station_code, obstime AS disc_obstime
        FROM discovery_obs_all
        ORDER BY unpacked_desig, obstime
    )
    SELECT
        CASE WHEN is_numbered THEN asteroid_number
             ELSE unpacked_desig
        END AS primary_designation,
        station_code,
        disc_obstime
    FROM discovery_info
    """
    with connect() as conn:
        return timed_query(conn, sql)


def compute_circumstances(df_base):
    """Enrich a discovery tracklets DataFrame with circumstance columns.

    Parameters
    ----------
    df_base : DataFrame
        Must contain at least: primary_designation, avg_ra_deg, avg_dec_deg,
        discovery_site_code

    Returns
    -------
    DataFrame with added circumstance columns
    """
    print("Querying observatory coordinates...")
    stations = load_station_info()
    stn_map = stations.set_index("obscode")

    print("Querying discovery timestamps...")
    disc_times = load_discovery_times(df_base["primary_designation"].values)

    # Merge discovery times onto base data
    # Both use primary_designation: number for numbered, provid for unnumbered
    df = df_base.copy()
    df["_merge_key"] = df["primary_designation"].astype(str)
    disc_times["_merge_key"] = disc_times["primary_designation"].astype(str)
    df = df.merge(
        disc_times[["_merge_key", "disc_obstime", "station_code"]],
        on="_merge_key", how="left", suffixes=("", "_obs"))
    df.drop(columns=["_merge_key"], inplace=True)

    # Merge station coordinates
    site_col = "discovery_site_code"
    df = df.merge(
        stn_map[["longitude", "rhocosphi", "rhosinphi", "observations_type"]],
        left_on=site_col, right_index=True, how="left")

    # Compute observer latitude from parallax constants
    is_sat = (df["observations_type"] == "satellite").values
    lon = df["longitude"].values.astype(float)
    lat = _observer_latitude(
        df["rhocosphi"].values.astype(float),
        df["rhosinphi"].values.astype(float))

    # Solar altitude and twilight class
    print("Computing solar altitude and twilight class...")
    has_time = df["disc_obstime"].notna()
    sun_alt = np.full(len(df), np.nan)
    twi_class = np.full(len(df), "", dtype=object)

    if has_time.any():
        idx = has_time.values
        alt = sun_altitude(df.loc[idx, "disc_obstime"], lon[idx], lat[idx])
        sun_alt[idx] = np.round(alt, 2)
        twi_class[idx] = classify_twilight(alt, is_sat[idx])

    df["sun_alt_deg"] = sun_alt
    df["twilight_class"] = twi_class

    # Lunar elongation
    print("Computing lunar elongation...")
    has_pos = has_time & df["avg_ra_deg"].notna()
    moon_elong = np.full(len(df), np.nan)
    if has_pos.any():
        idx = has_pos.values
        elong = lunar_elongation(
            df.loc[idx, "disc_obstime"],
            df.loc[idx, "avg_ra_deg"].values,
            df.loc[idx, "avg_dec_deg"].values)
        moon_elong[idx] = np.round(elong, 1)
    df["lunar_elong_deg"] = moon_elong

    # Eclipse classification
    print("Checking lunar eclipse circumstances...")
    ecl_class = np.full(len(df), "", dtype=object)
    ecl_date = np.full(len(df), "", dtype=object)
    if has_time.any():
        idx = has_time.values
        ec, ed = classify_eclipse(
            df.loc[idx, "disc_obstime"], lon[idx], lat[idx], is_sat[idx])
        ecl_class[idx] = ec
        ecl_date[idx] = ed
    df["eclipse_class"] = ecl_class
    df["eclipse_date"] = ecl_date

    # Drop working columns, keep only the enrichment
    drop_cols = ["station_code_obs", "disc_obstime",
                 "longitude", "rhocosphi", "rhosinphi", "observations_type"]
    df.drop(columns=[c for c in drop_cols if c in df.columns],
            inplace=True, errors="ignore")

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Compute discovery circumstances for NEO tracklets")
    parser.add_argument("input_csv", nargs="?", default=None,
                        help="Input CSV (default: NEO_discovery_tracklets.csv symlink)")
    args = parser.parse_args()

    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.input_csv:
        input_path = args.input_csv
    else:
        input_path = os.path.join(repo_dir, "NEO_discovery_tracklets.csv")

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {input_path}...")
    df_base = pd.read_csv(input_path)
    print(f"  {len(df_base)} rows, {len(df_base.columns)} columns")

    df_out = compute_circumstances(df_base)

    # Output path: replace base name with _extra_ variant
    date_stamp = datetime.now().strftime("%d%b%y")
    out_name = f"NEO_discovery_tracklets_extra_{date_stamp}.csv"
    out_path = os.path.join(repo_dir, out_name)
    link_name = os.path.join(repo_dir, "NEO_discovery_tracklets_extra.csv")

    # Select output columns: all original + new circumstance columns
    extra_cols = ["sun_alt_deg", "twilight_class",
                  "lunar_elong_deg", "eclipse_class", "eclipse_date"]
    out_cols = list(df_base.columns) + extra_cols
    out_cols = [c for c in out_cols if c in df_out.columns]

    df_out[out_cols].to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")
    print(f"  {len(df_out)} rows, {len(out_cols)} columns")

    # Update symlink
    if os.path.islink(link_name):
        os.remove(link_name)
    elif os.path.exists(link_name):
        os.remove(link_name)
    os.symlink(os.path.basename(out_path), link_name)
    print(f"  Symlink {os.path.basename(link_name)} -> {os.path.basename(out_path)}")

    # Summary
    print(f"\n--- Twilight classification ---")
    for cat in TWILIGHT_ORDER:
        n = (df_out["twilight_class"] == cat).sum()
        if n > 0:
            print(f"  {cat:25s} {n:6d}  ({100*n/len(df_out):.2f}%)")

    ecl = df_out[df_out["eclipse_class"] != ""]
    if len(ecl) > 0:
        print(f"\n--- Lunar eclipse discoveries ({len(ecl)}) ---")
        for _, row in ecl.iterrows():
            desig = row["primary_designation"]
            site = row["discovery_site_code"]
            ecls = row["eclipse_class"]
            edate = row["eclipse_date"]
            melong = row["lunar_elong_deg"]
            print(f"  {desig:15s}  {site}  {ecls:20s}  "
                  f"eclipse={edate}  lunar_elong={melong:.0f} deg")

    print(f"\n--- Lunar elongation ---")
    valid = df_out["lunar_elong_deg"].dropna()
    print(f"  min={valid.min():.1f}  median={valid.median():.1f}  "
          f"max={valid.max():.1f} deg")


if __name__ == "__main__":
    main()
