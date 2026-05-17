"""Finding-chart sky plot for the Observation history tab.

Projects an object's (RA, Dec) observation trail onto a Plotly cartesian
scatter, with optional Hipparcos bright-star and IAU constellation-line
overlays.  Phase 1 is static (no animation); time-order is conveyed by
a viridis color ramp over `obstime`.  Trail is point-to-point linear
within an arc, breaking where the gap between successive observations
exceeds `gap_days` (default 60 d).  An optional Catmull-Rom-equivalent
cubic spline per arc can be toggled on for a smooth overlay.

Inheritance from NEOlyzer's SkyMapCanvas:
- Four projections: rectangular, hammer (default), aitoff, mollweide.
- Wrap-break: |Δλ| > π in centered coordinates → new segment.
- Star catalog: Hipparcos V<6 (vendored from NEOlyzer/data).
- IAU constellation boundaries (J2000, vendored from NEOlyzer/data).

Convention follows NEOlyzer's matplotlib default: east is right
(longitude increases right).  Center longitude is the wrap meridian;
default 180° puts RA=0/24h at the edges of a full-sky view.
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "finding_chart"))


# ---------------------------------------------------------------------------
# Reference-catalog loaders.  Both files are static (vendored from NEOlyzer);
# load once per process via lru_cache.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_stars() -> pd.DataFrame:
    """Hipparcos V<6 bright-star catalog.  Columns: hip, vmag, ra, dec."""
    path = os.path.join(_DATA_DIR, "bright_stars.csv")
    return pd.read_csv(path, comment="#",
                       names=["hip", "vmag", "ra", "dec"])


@lru_cache(maxsize=1)
def load_constellations() -> pd.DataFrame:
    """IAU constellation boundaries (J2000, line segments).
    Columns: ra1, dec1, ra2, dec2, abbrev, name."""
    path = os.path.join(_DATA_DIR, "iau_boundaries_j2000.csv")
    return pd.read_csv(
        path, comment="#",
        names=["ra1", "dec1", "ra2", "dec2", "abbrev", "name"])


# ---------------------------------------------------------------------------
# Projection math.  All inputs in degrees; outputs in projection-native
# units (degrees for rectangular, dimensionless for the equal-area set).
# Center the longitude on `center_ra_deg` before projection so the wrap
# meridian is user-chosen.
# ---------------------------------------------------------------------------

PROJECTIONS = ("rectangular", "hammer", "aitoff", "mollweide")


def _center_lon(ra_deg: np.ndarray, center_ra_deg: float) -> np.ndarray:
    """Return longitude in (-180, +180] centered on `center_ra_deg`."""
    return ((np.asarray(ra_deg, dtype=float) - center_ra_deg + 540.0)
            % 360.0) - 180.0


def project(ra_deg, dec_deg, kind: str,
            center_ra_deg: float = 180.0
            ) -> tuple[np.ndarray, np.ndarray]:
    """Project (RA, Dec) in degrees to plot coordinates."""
    lon = _center_lon(ra_deg, center_ra_deg)
    lat = np.asarray(dec_deg, dtype=float)

    if kind == "rectangular":
        return lon, lat

    lam = np.deg2rad(lon)
    phi = np.deg2rad(lat)

    if kind == "hammer":
        denom = np.sqrt(1.0 + np.cos(phi) * np.cos(lam / 2.0))
        x = 2.0 * np.sqrt(2.0) * np.cos(phi) * np.sin(lam / 2.0) / denom
        y = np.sqrt(2.0) * np.sin(phi) / denom
        return x, y

    if kind == "aitoff":
        alpha = np.arccos(np.clip(np.cos(phi) * np.cos(lam / 2.0),
                                  -1.0, 1.0))
        # sinc(0) = 1; np.sinc(x/pi) avoids the divide-by-zero
        sinc = np.sinc(alpha / np.pi)
        x = 2.0 * np.cos(phi) * np.sin(lam / 2.0) / sinc
        y = np.sin(phi) / sinc
        return x, y

    if kind == "mollweide":
        # Solve 2θ + sin(2θ) = π sin(φ) by Newton iteration.
        theta = np.array(phi, dtype=float, copy=True)
        for _ in range(8):
            num = 2.0 * theta + np.sin(2.0 * theta) - np.pi * np.sin(phi)
            den = 2.0 + 2.0 * np.cos(2.0 * theta)
            den = np.where(np.abs(den) < 1e-12, 1e-12, den)
            theta = theta - num / den
        x = (2.0 * np.sqrt(2.0) / np.pi) * lam * np.cos(theta)
        y = np.sqrt(2.0) * np.sin(theta)
        return x, y

    raise ValueError(f"Unknown projection: {kind!r}")


# ---------------------------------------------------------------------------
# Trail segmentation.  Two cuts produce a NaN-separated polyline:
#   1. Time gaps > `gap_days` between consecutive observations.
#   2. Wrap jumps |Δλ| > 180° in centered coordinates (large RA jumps
#      across the projection's meridian).
# Returning a single (x, y) pair with NaN breakpoints lets Plotly draw
# the whole trail as one Scatter trace with `mode="lines+markers"`.
# ---------------------------------------------------------------------------

def trail_with_breaks(df: pd.DataFrame, kind: str,
                      center_ra_deg: float = 180.0,
                      gap_days: float = 60.0
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the time-ordered (x, y, t) arrays with NaN breakpoints.

    Returns:
        x, y: projected coordinates, NaN inserted between breaks.
        t:    matching obstime values (NaT at breakpoints) for hover.
    """
    if df.empty:
        return (np.array([]),) * 3
    d = df.sort_values("obstime").reset_index(drop=True)
    ra = d["ra"].to_numpy(dtype=float)
    dec = d["dec"].to_numpy(dtype=float)
    t = d["obstime"].to_numpy()
    x, y = project(ra, dec, kind, center_ra_deg=center_ra_deg)

    # Gap-break flags
    dt_days = np.diff(t).astype("timedelta64[s]").astype(float) / 86400.0
    gap_break = dt_days > gap_days

    # Wrap-break flags: large jump in centered longitude
    lon_centered = _center_lon(ra, center_ra_deg)
    wrap_break = np.abs(np.diff(lon_centered)) > 180.0

    breaks = np.where(gap_break | wrap_break)[0]
    if len(breaks) == 0:
        return x, y, t

    # Insert NaN at each break (right after index `b`).
    out_x = []
    out_y = []
    out_t = []
    last = 0
    for b in breaks:
        out_x.extend(x[last:b + 1].tolist() + [np.nan])
        out_y.extend(y[last:b + 1].tolist() + [np.nan])
        out_t.extend(t[last:b + 1].tolist() + [np.datetime64("NaT")])
        last = b + 1
    out_x.extend(x[last:].tolist())
    out_y.extend(y[last:].tolist())
    out_t.extend(t[last:].tolist())
    return np.array(out_x), np.array(out_y), np.array(out_t)


def _arc_indices(df: pd.DataFrame, gap_days: float) -> list[tuple[int, int]]:
    """Return [(start, end_exclusive), ...] index ranges for each arc."""
    if df.empty:
        return []
    t = df["obstime"].to_numpy()
    dt_days = np.diff(t).astype("timedelta64[s]").astype(float) / 86400.0
    breaks = np.where(dt_days > gap_days)[0]
    starts = [0] + (breaks + 1).tolist()
    ends = (breaks + 1).tolist() + [len(df)]
    return list(zip(starts, ends))


def spline_overlay(df: pd.DataFrame, kind: str,
                   center_ra_deg: float = 180.0,
                   gap_days: float = 60.0,
                   samples_per_arc: int = 200,
                   max_degree: int = 5,
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Per-arc Chebyshev fit, evaluated densely.  Degree scales with
    arc length (deg = min(max_degree, npts-1)).  RA-unwrapped so the
    fit doesn't oscillate across 0/360°.  Arcs with < 4 points are
    skipped.  numpy-only (no scipy dependency).  Returns NaN-broken
    (x, y).  "Chebyshev or some such" — see project notes.
    """
    if df.empty:
        return np.array([]), np.array([])
    from numpy.polynomial import Chebyshev

    d = df.sort_values("obstime").reset_index(drop=True)
    arcs = _arc_indices(d, gap_days)
    out_x = []
    out_y = []
    for s, e in arcs:
        if e - s < 4:
            continue
        sub = d.iloc[s:e]
        t = sub["obstime"].astype("int64").to_numpy() / 1e9 / 86400.0
        if t[-1] - t[0] <= 0:
            continue
        deg = min(max_degree, len(sub) - 1)
        ra_uw = np.rad2deg(np.unwrap(np.deg2rad(sub["ra"].to_numpy())))
        dec = sub["dec"].to_numpy(dtype=float)
        try:
            cheb_ra = Chebyshev.fit(t, ra_uw, deg)
            cheb_dec = Chebyshev.fit(t, dec, deg)
        except (np.linalg.LinAlgError, ValueError):
            continue
        ts = np.linspace(t[0], t[-1], samples_per_arc)
        ra_s = cheb_ra(ts) % 360.0
        dec_s = np.clip(cheb_dec(ts), -90.0, 90.0)
        x, y = project(ra_s, dec_s, kind, center_ra_deg=center_ra_deg)
        out_x.extend(x.tolist() + [np.nan])
        out_y.extend(y.tolist() + [np.nan])
    if out_x:
        out_x = out_x[:-1]
        out_y = out_y[:-1]
    return np.array(out_x), np.array(out_y)


# ---------------------------------------------------------------------------
# Constellation-line projection.  Each input row is one line segment; we
# project both endpoints, dropping any segment whose Δlon wraps (would
# draw a long line across the meridian).
# ---------------------------------------------------------------------------

def graticule_segments(kind: str, center_ra_deg: float = 180.0,
                       ra_step_deg: float = 30.0,
                       dec_step_deg: float = 15.0,
                       sample_deg: float = 2.0,
                       ) -> tuple[np.ndarray, np.ndarray]:
    """Build NaN-separated (x, y) for an RA/Dec coordinate graticule.

    Dec parallels are drawn at every `dec_step_deg`, RA meridians at
    every `ra_step_deg`; each line is sampled at `sample_deg` and broken
    where the centered longitude jumps > 180° (the projection meridian).
    """
    xs: list[float] = []
    ys: list[float] = []

    def _emit(ra_arr, dec_arr):
        # Project the polyline and insert NaN where centered-lon wraps.
        x, y = project(ra_arr, dec_arr, kind, center_ra_deg=center_ra_deg)
        lon = _center_lon(ra_arr, center_ra_deg)
        breaks = np.where(np.abs(np.diff(lon)) > 180.0)[0]
        last = 0
        for b in breaks:
            xs.extend(x[last:b + 1].tolist() + [np.nan])
            ys.extend(y[last:b + 1].tolist() + [np.nan])
            last = b + 1
        xs.extend(x[last:].tolist() + [np.nan])
        ys.extend(y[last:].tolist() + [np.nan])

    # Dec parallels (skip the poles, which collapse to a point).
    ra_arr = np.arange(0.0, 360.0 + sample_deg, sample_deg)
    for dec in np.arange(-90.0 + dec_step_deg, 90.0, dec_step_deg):
        _emit(ra_arr, np.full_like(ra_arr, dec))

    # RA meridians.
    dec_arr = np.arange(-90.0, 90.0 + sample_deg, sample_deg)
    for ra in np.arange(0.0, 360.0, ra_step_deg):
        _emit(np.full_like(dec_arr, ra), dec_arr)

    if xs:
        xs = xs[:-1]
        ys = ys[:-1]
    return np.array(xs), np.array(ys)


def _project_constellation_segments(kind: str, center_ra_deg: float
                                    ) -> tuple[np.ndarray, np.ndarray]:
    """Build NaN-separated (x, y) for all IAU constellation boundary segs."""
    cb = load_constellations()
    ra1 = cb["ra1"].to_numpy(dtype=float)
    dec1 = cb["dec1"].to_numpy(dtype=float)
    ra2 = cb["ra2"].to_numpy(dtype=float)
    dec2 = cb["dec2"].to_numpy(dtype=float)

    # Drop segments that cross the centered meridian (Δlon > 180°).
    lon1 = _center_lon(ra1, center_ra_deg)
    lon2 = _center_lon(ra2, center_ra_deg)
    keep = np.abs(lon2 - lon1) <= 180.0

    x1, y1 = project(ra1[keep], dec1[keep], kind,
                     center_ra_deg=center_ra_deg)
    x2, y2 = project(ra2[keep], dec2[keep], kind,
                     center_ra_deg=center_ra_deg)

    # Interleave with NaN separators
    n = len(x1)
    xs = np.empty(3 * n, dtype=float)
    ys = np.empty(3 * n, dtype=float)
    xs[0::3] = x1
    xs[1::3] = x2
    xs[2::3] = np.nan
    ys[0::3] = y1
    ys[1::3] = y2
    ys[2::3] = np.nan
    return xs, ys


# ---------------------------------------------------------------------------
# Figure builder.
# ---------------------------------------------------------------------------

def build_finding_figure(
    df: pd.DataFrame,
    *,
    projection: str = "hammer",
    center_ra_deg: float = 180.0,
    gap_days: float = 60.0,
    show_stars: bool = True,
    show_constellations: bool = True,
    show_grid: bool = False,
    star_mag_limit: float = 6.0,
    theme: dict | None = None,
    label: str = "",
) -> go.Figure:
    """Build the finding-chart Plotly figure.

    Coordinate convention follows NEOlyzer / matplotlib geo projections:
    longitude increases right (east-right).  No axis flip is applied.
    Observed positions are drawn as discrete markers — no connecting
    lines.  The cartesian XY axis grid is suppressed (it doesn't
    correspond to anything on the sky); enable `show_grid` to draw a
    proper RA/Dec graticule instead.
    """
    if projection not in PROJECTIONS:
        raise ValueError(f"projection must be one of {PROJECTIONS}")

    fg = (theme or {}).get("fg", "#e0e0e0")
    bg = (theme or {}).get("plot", "#1e1e1e")

    fig = go.Figure()

    # ── Coordinate graticule (drawn first, behind everything) ─────────
    if show_grid:
        gx, gy = graticule_segments(projection, center_ra_deg)
        fig.add_trace(go.Scatter(
            x=gx, y=gy, mode="lines",
            line=dict(color="rgba(140,140,140,0.30)",
                      width=0.6, dash="dot"),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Constellation lines ───────────────────────────────────────────
    if show_constellations:
        cx, cy = _project_constellation_segments(projection, center_ra_deg)
        fig.add_trace(go.Scatter(
            x=cx, y=cy, mode="lines",
            line=dict(color="rgba(120,140,200,0.35)", width=0.7),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Bright stars (sized by magnitude) ──────────────────────────────
    if show_stars:
        stars = load_stars()
        stars = stars[stars["vmag"] <= star_mag_limit]
        sx, sy = project(stars["ra"].to_numpy(),
                         stars["dec"].to_numpy(),
                         projection, center_ra_deg=center_ra_deg)
        size = np.clip(6.0 - 0.7 * stars["vmag"].to_numpy(), 0.6, 6.0)
        fig.add_trace(go.Scatter(
            x=sx, y=sy, mode="markers",
            marker=dict(color="rgba(220,220,220,0.85)",
                        size=size, line=dict(width=0)),
            hovertemplate=("HIP %{customdata[0]:d} · V %{customdata[1]:.2f}"
                           "<extra></extra>"),
            customdata=np.column_stack([
                stars["hip"].to_numpy(),
                stars["vmag"].to_numpy(),
            ]),
            showlegend=False,
        ))

    # ── Observation markers (no connecting lines) ──────────────────────
    if not df.empty:
        d = df.sort_values("obstime").reset_index(drop=True)
        mx, my = project(d["ra"].to_numpy(), d["dec"].to_numpy(),
                         projection, center_ra_deg=center_ra_deg)
        years = np.array([
            (pd.Timestamp(v).year
             + (pd.Timestamp(v).dayofyear - 1)
             / (366.0 if pd.Timestamp(v).is_leap_year else 365.0))
            for v in d["obstime"]
        ], dtype=float)
        fig.add_trace(go.Scatter(
            x=mx, y=my, mode="markers",
            marker=dict(
                color=years, colorscale="Viridis",
                size=5, line=dict(width=0),
                colorbar=dict(
                    title=dict(text="Year", font=dict(color=fg)),
                    tickformat="d",
                ),
            ),
            customdata=d["obstime"].to_numpy(),
            hovertemplate=("%{customdata|%Y-%m-%d %H:%M}<br>"
                           "x %{x:.3f} · y %{y:.3f}<extra></extra>"),
            showlegend=False,
        ))

    # ── Layout ────────────────────────────────────────────────────────
    title = (f"Finding chart — {label}" if label else "Finding chart") + \
            f"  ({projection.title()})"
    fig.update_layout(
        title=dict(text=title, font=dict(color=fg, size=14), x=0.02),
        autosize=True,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor=bg, plot_bgcolor=bg,
        font=dict(color=fg),
        showlegend=False,
        dragmode="pan",
    )
    # Equal aspect in data space keeps the projection true.  The XY
    # cartesian grid is meaningless for a sky projection, so it's
    # suppressed; use `show_grid=True` for a real RA/Dec graticule.
    fig.update_xaxes(
        scaleanchor="y", scaleratio=1,
        showgrid=False, zeroline=False,
        showticklabels=False,
        title=None,
    )
    fig.update_yaxes(
        showgrid=False, zeroline=False,
        showticklabels=False,
        title=None,
    )
    return fig
