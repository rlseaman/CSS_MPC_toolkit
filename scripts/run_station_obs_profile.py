#!/usr/bin/env python3
"""
Run the station observation profile query (Query B) and save results.

This is a full scan of obs_sbn (~526M rows) and takes 20-40 minutes.
Progress is indicated by periodic status messages from timed_query.

Usage:
    python scripts/run_station_obs_profile.py
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.db import connect, timed_query

SQL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "sql", "station_obs_profile.sql")
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "app", ".station_obs_profile.csv")


def main():
    sql = open(SQL_FILE).read()

    print(f"Starting station observation profile query...")
    print(f"This scans all ~526M rows of obs_sbn. Expect 20-40 minutes.")
    print(f"Started at: {time.strftime('%H:%M:%S')}")
    print()

    t0 = time.time()
    with connect() as conn:
        # Set a long statement timeout (90 min)
        conn.cursor().execute("SET statement_timeout = '5400s'")
        df = timed_query(conn, sql, label="station_obs_profile")

    elapsed = time.time() - t0
    print(f"\nQuery completed in {elapsed/60:.1f} minutes")
    print(f"Got {len(df):,} stations")
    print()

    # Save
    df.to_csv(OUTPUT, index=False)
    print(f"Saved to {OUTPUT}")

    # Print top 20
    print(f"\nTop 20 stations by observation count:")
    print(df.head(20).to_string(index=False))

    # Summary
    print(f"\nTotal observations: {df['n_obs'].sum():,}")
    print(f"Total stations:    {len(df):,}")


if __name__ == "__main__":
    main()
