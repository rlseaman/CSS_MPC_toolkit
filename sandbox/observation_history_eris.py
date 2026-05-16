#!/usr/bin/env python
"""Prototype: observation history plot for Eris.

Pulls all astrometry for permid 136199 (Eris) directly from mpc_sbn and
emits a two-panel interactive HTML figure: band-corrected V vs obstime on
top, site-code lifeline on the bottom, sharing an x-axis and a rangeslider.
Vertical bands shade intervals where solar elongation > 90° (observable)
vs ≤ 90° (near conjunction).

Shading is computed across the full 1954 → 2026 data range; the long gaps
between the 1954 Palomar plate and 1990s precovery points are filled by
nearest-neighbour extrapolation of Eris's sky position.  Eris moves
~0.6°/yr in the sky, so the band edges in those gaps may be ~½ month off
from the truth — fine at this zoom level, but not for precise planning.

Run from repo root with PGHOST set:
    PGHOST=sibyl ./venv/bin/python sandbox/observation_history_eris.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.observation_history import (  # noqa: E402
    fetch_obs, build_history_figure, write_html,
)

PERMID = "136199"
NAME = "Eris"
SLUG = "eris"
OUTPUT_HTML = REPO_ROOT / "sandbox" / f"observation_history_{SLUG}.html"

# Eris sits at V≈18-20; presets bracket the useful zoom.  u-band corrected
# points overshoot to V~24, so the loose "15-25" preset accommodates them.
V_PRESETS = [
    ("auto",    dict(autorange="reversed")),
    ("15 – 25", dict(autorange=False, range=[25, 15])),
    ("17 – 21", dict(autorange=False, range=[21, 17])),
    ("18 – 20", dict(autorange=False, range=[20, 18])),
]


def main() -> int:
    df = fetch_obs(permid=PERMID)
    if df.empty:
        print(f"No obs found for permid={PERMID}", file=sys.stderr)
        return 1

    print(f"{NAME}: {len(df):,} obs "
          f"({df['obstime'].min()} → {df['obstime'].max()})")
    print(f"  stations: {df['stn'].nunique()}")
    print(f"  bands present: " + ", ".join(
        f"{b}={n}" for b, n in
        df['band_norm'].value_counts().head(6).items()))
    print(f"  elongation range: "
          f"{df['elong'].min():.1f}° to {df['elong'].max():.1f}°")
    v = df['v_mag'].dropna()
    if not v.empty:
        print(f"  V_approx range:   {v.min():.2f} to {v.max():.2f}")
    print(f"  top 6 sites: " + ", ".join(
        f"{s}={n}" for s, n in df['stn'].value_counts().head(6).items()))

    fig = build_history_figure(
        df, name=f"{NAME} (permid {PERMID})",
        v_presets=V_PRESETS,
    )
    write_html(fig, OUTPUT_HTML)
    print(f"\nWrote interactive plot: "
          f"{OUTPUT_HTML.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
