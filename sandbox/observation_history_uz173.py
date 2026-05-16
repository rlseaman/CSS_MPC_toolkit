#!/usr/bin/env python
"""Prototype: observation history plot for 2019 UZ173.

Sister of `observation_history_eris.py`, retargeted at a sparse 3-apparition TNO
that would benefit from further astrometry.  Pulls all astrometry for
provid '2019 UZ173' directly from mpc_sbn and emits a two-panel interactive
HTML figure: band-corrected V vs obstime on top, site-code lifeline on the
bottom.

Why this object: 39 obs across exactly three apparitions (Jul–Aug 2016 at
Subaru/T09, Oct–Dec 2019 at Subaru/T09, Oct 2024 at LDT/G37) over an
8.2-yr arc — H ≈ 6.8, q ≈ 35 AU, e ≈ 0.27, i ≈ 19°.  Numbered status is
on the bubble; the 2024 recovery got only 3 nights at one site, so the
trail is thin going forward.

Run from repo root with PGHOST set:
    PGHOST=sibyl ./venv/bin/python sandbox/observation_history_uz173.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sandbox._observation_history_helpers import (  # noqa: E402
    fetch_obs, build_history_figure, write_html,
)

PROVID = "2019 UZ173"
NAME = "2019 UZ173"
SLUG = "uz173"
OUTPUT_HTML = REPO_ROOT / "sandbox" / f"observation_history_{SLUG}.html"

# UZ173 sits at V≈24; presets shifted faint relative to Eris.
V_PRESETS = [
    ("auto",         dict(autorange="reversed")),
    ("22 – 26",      dict(autorange=False, range=[26, 22])),
    ("23 – 25",      dict(autorange=False, range=[25, 23])),
    ("23.5 – 24.5",  dict(autorange=False, range=[24.5, 23.5])),
]


def main() -> int:
    df = fetch_obs(provid=PROVID)
    if df.empty:
        print(f"No obs found for provid={PROVID}", file=sys.stderr)
        return 1

    print(f"{NAME}: {len(df):,} obs "
          f"({df['obstime'].min()} → {df['obstime'].max()})")
    print(f"  stations: {df['stn'].nunique()}  "
          f"({', '.join(sorted(df['stn'].unique()))})")
    print(f"  bands present: " + ", ".join(
        f"{b}={n}" for b, n in
        df['band_norm'].value_counts().head(6).items()))
    print(f"  elongation range: "
          f"{df['elong'].min():.1f}° to {df['elong'].max():.1f}°")
    v = df['v_mag'].dropna()
    if not v.empty:
        print(f"  V_approx range:   {v.min():.2f} to {v.max():.2f}")

    fig = build_history_figure(
        df, name=NAME,
        title_extra="3-apparition TNO needing further astrometry",
        # Pad the grid by half a year past the last obs so the rangeslider
        # has somewhere to "see" the upcoming season.
        grid_end_pad_days=180,
        v_presets=V_PRESETS,
    )
    write_html(fig, OUTPUT_HTML)
    print(f"\nWrote interactive plot: "
          f"{OUTPUT_HTML.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
