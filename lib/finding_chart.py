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
    """Centered longitude in (-180, +180].

    The final negation flips the longitude axis so that increasing RA
    (eastward on the sky) maps to *decreasing* x — the astronomical
    convention NEOlyzer uses, with east on the LEFT of the plot.
    Wrap-break logic compares `|Δlon|` so it's invariant under this
    sign flip, and projection_boundary() returns a symmetric ellipse,
    so no other code needs to change.
    """
    lon = ((np.asarray(ra_deg, dtype=float) - center_ra_deg + 540.0)
           % 360.0) - 180.0
    return -lon


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

# ICRS ↔ galactic rotation, J2000 (transposed from the standard ICRS-to-
# galactic matrix; here we go galactic → ICRS for the galactic-plane
# reference curve).  Numerical values match astropy 5.x for the
# fk5/icrs alignment within ~milliarcsec, which is way beyond what a
# finding-chart overlay needs.
_GAL_TO_ICRS = np.array([
    [-0.054875539, +0.494109454, -0.867666136],
    [-0.873437105, -0.444829594, -0.198076390],
    [-0.483834992, +0.746982249, +0.455983776],
])
_ECLIPTIC_OBLIQUITY_DEG = 23.43929111  # J2000


def _ra_hms_str(ra_deg: float) -> str:
    """Format RA in degrees as `HHh MMm SS.Ss` sexagesimal."""
    h_total = (float(ra_deg) % 360.0) / 15.0
    h = int(h_total)
    m_total = (h_total - h) * 60.0
    m = int(m_total)
    s = (m_total - m) * 60.0
    if s >= 59.95:
        s = 0.0
        m += 1
        if m >= 60:
            m = 0
            h = (h + 1) % 24
    return f"{h:02d}h {m:02d}m {s:04.1f}s"


def _dec_dms_str(dec_deg: float) -> str:
    """Format Dec in degrees as `±DD° MM' SS.S\"` sexagesimal."""
    d_abs = abs(float(dec_deg))
    sign = "-" if dec_deg < 0 else "+"
    d = int(d_abs)
    m_total = (d_abs - d) * 60.0
    m = int(m_total)
    s = (m_total - m) * 60.0
    if s >= 59.95:
        s = 0.0
        m += 1
        if m >= 60:
            m = 0
            d += 1
    return f"{sign}{d:02d}° {m:02d}' {s:04.1f}\""

# Fixed celestial reference points (J2000, ICRS).  Cardinal-direction
# badges and the four pole markers depend on these.
_NGP_RA_DEG = 192.85948
_NGP_DEC_DEG = +27.12825
_SGP_RA_DEG = (192.85948 + 180.0) % 360.0
_SGP_DEC_DEG = -27.12825
_NEP_RA_DEG = 270.0
_NEP_DEC_DEG = +90.0 - _ECLIPTIC_OBLIQUITY_DEG
_SEP_RA_DEG = 90.0
_SEP_DEC_DEG = -(90.0 - _ECLIPTIC_OBLIQUITY_DEG)

# Plot colors for the ecliptic / galactic groups — keep consistent
# between the plane line, the pole markers, and any future overlays.
_ECLIPTIC_COLOR = "rgba(255,200,90,0.95)"
_GALACTIC_COLOR = "rgba(190,140,255,0.95)"


def _project_polyline(ra_deg: np.ndarray, dec_deg: np.ndarray,
                      kind: str, center_ra_deg: float
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Project a closed/open ra/dec polyline with wrap-break at the
    centered-longitude meridian.  Returns NaN-separated (x, y)."""
    lon = _center_lon(ra_deg, center_ra_deg)
    x, y = project(ra_deg, dec_deg, kind, center_ra_deg=center_ra_deg)
    breaks = np.where(np.abs(np.diff(lon)) > 180.0)[0]
    if len(breaks) == 0:
        return x, y
    xs, ys = [], []
    last = 0
    for b in breaks:
        xs.extend(x[last:b + 1].tolist() + [np.nan])
        ys.extend(y[last:b + 1].tolist() + [np.nan])
        last = b + 1
    xs.extend(x[last:].tolist())
    ys.extend(y[last:].tolist())
    return np.array(xs), np.array(ys)


def galactic_plane_segments(kind: str, center_ra_deg: float = 180.0,
                            n_samples: int = 720
                            ) -> tuple[np.ndarray, np.ndarray]:
    """Project the galactic equator (b=0) into the given projection."""
    l = np.deg2rad(np.linspace(0.0, 360.0, n_samples, endpoint=True))
    cb = np.cos(0.0)
    vec_gal = np.stack([cb * np.cos(l), cb * np.sin(l),
                        np.zeros_like(l)])
    eq = _GAL_TO_ICRS @ vec_gal
    ra = np.rad2deg(np.arctan2(eq[1], eq[0])) % 360.0
    dec = np.rad2deg(np.arcsin(np.clip(eq[2], -1.0, 1.0)))
    return _project_polyline(ra, dec, kind, center_ra_deg)


def ecliptic_plane_segments(kind: str, center_ra_deg: float = 180.0,
                            n_samples: int = 720
                            ) -> tuple[np.ndarray, np.ndarray]:
    """Project the ecliptic (β=0) into the given projection."""
    eps = np.deg2rad(_ECLIPTIC_OBLIQUITY_DEG)
    lam = np.deg2rad(np.linspace(0.0, 360.0, n_samples, endpoint=True))
    ra = np.rad2deg(np.arctan2(np.sin(lam) * np.cos(eps),
                               np.cos(lam))) % 360.0
    dec = np.rad2deg(np.arcsin(np.sin(eps) * np.sin(lam)))
    return _project_polyline(ra, dec, kind, center_ra_deg)


def projection_boundary(kind: str
                        ) -> tuple[np.ndarray, np.ndarray]:
    """Closed outline of the projection's whole-sky region.

    Hammer and Mollweide both project to an ellipse with semi-axes
    (2√2, √2); Aitoff projects to (π, π/2).  Rectangular is the
    [-180, +180]×[-90, +90] rectangle.
    """
    if kind == "rectangular":
        x = np.array([-180.0, 180.0, 180.0, -180.0, -180.0])
        y = np.array([-90.0, -90.0, 90.0, 90.0, -90.0])
        return x, y

    if kind in ("hammer", "mollweide"):
        a, b = 2.0 * np.sqrt(2.0), np.sqrt(2.0)
    elif kind == "aitoff":
        a, b = np.pi, np.pi / 2.0
    else:
        raise ValueError(f"Unknown projection: {kind!r}")
    t = np.linspace(0.0, 2.0 * np.pi, 361)
    return a * np.cos(t), b * np.sin(t)


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
    predictions_df: pd.DataFrame | None = None,
    show_prediction_labels: bool = True,
    prediction_v_limit: float | tuple[float, float] = 23.0,
    prediction_elong_min: float = 90.0,
    show_ecliptic: bool = False,
    show_galactic: bool = False,
    show_ngp: bool = False,
    show_sgp: bool = False,
    show_nep: bool = False,
    show_sep: bool = False,
    colorscale: str = "Viridis",
    hide_gray_predictions: bool = False,
    uirevision: str | None = None,
) -> go.Figure:
    """Build the finding-chart Plotly figure.

    Coordinate convention follows NEOlyzer / matplotlib geo projections:
    longitude increases right (east-right).  No axis flip is applied.
    Observed positions are drawn as discrete markers — no connecting
    lines.  The cartesian XY axis grid is suppressed (it doesn't
    correspond to anything on the sky); enable `show_grid` to draw a
    proper RA/Dec graticule instead.  When `predictions_df` is
    supplied (e.g. from `lib.horizons.fetch_predictions`), the
    predicted track is overlaid as a distinct warm-colored polyline.
    """
    if projection not in PROJECTIONS:
        raise ValueError(f"projection must be one of {PROJECTIONS}")

    fg = (theme or {}).get("fg", "#e0e0e0")
    bg = (theme or {}).get("plot", "#1e1e1e")
    # Theme-aware overlay colors.  Default to dark-mode values; caller
    # supplies light-mode overrides via the `theme` dict.
    grid_color = (theme or {}).get("grid", "rgba(180,180,210,0.45)")
    boundary_color = (theme or {}).get(
        "boundary", "rgba(200,200,220,0.85)")
    constellation_color = (theme or {}).get(
        "constellation", "rgba(120,140,200,0.45)")
    star_color = (theme or {}).get("star", "rgba(230,230,230,0.90)")

    fig = go.Figure()

    # ── Whole-sky projection boundary ────────────────────────────────
    # Drawn first (under) but at moderate weight so the oval / rectangle
    # of the projection frames the chart.
    bx, by = projection_boundary(projection)
    fig.add_trace(go.Scatter(
        x=bx, y=by, mode="lines",
        line=dict(color=boundary_color, width=1.5),
        hoverinfo="skip", showlegend=False,
    ))

    # ── Coordinate graticule (opt-in) ────────────────────────────────
    if show_grid:
        gx, gy = graticule_segments(projection, center_ra_deg)
        fig.add_trace(go.Scatter(
            x=gx, y=gy, mode="lines",
            line=dict(color=grid_color, width=0.8, dash="dot"),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Ecliptic ──────────────────────────────────────────────────────
    if show_ecliptic:
        ex, ey = ecliptic_plane_segments(projection, center_ra_deg)
        fig.add_trace(go.Scatter(
            x=ex, y=ey, mode="lines",
            line=dict(color=_ECLIPTIC_COLOR,
                      width=1.8, dash="dash"),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Galactic plane ────────────────────────────────────────────────
    if show_galactic:
        gx2, gy2 = galactic_plane_segments(projection, center_ra_deg)
        fig.add_trace(go.Scatter(
            x=gx2, y=gy2, mode="lines",
            line=dict(color=_GALACTIC_COLOR,
                      width=1.8, dash="dashdot"),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Galactic / ecliptic poles (opt-in) ────────────────────────────
    # Plus signs in the matching plane color.  Hover text identifies
    # which pole each marker is so the chart explains itself even with
    # no legend.
    pole_specs: list[tuple[float, float, str, str]] = []
    if show_ngp:
        pole_specs.append((_NGP_RA_DEG, _NGP_DEC_DEG, _GALACTIC_COLOR,
                           "N. galactic pole"))
    if show_sgp:
        pole_specs.append((_SGP_RA_DEG, _SGP_DEC_DEG, _GALACTIC_COLOR,
                           "S. galactic pole"))
    if show_nep:
        pole_specs.append((_NEP_RA_DEG, _NEP_DEC_DEG, _ECLIPTIC_COLOR,
                           "N. ecliptic pole"))
    if show_sep:
        pole_specs.append((_SEP_RA_DEG, _SEP_DEC_DEG, _ECLIPTIC_COLOR,
                           "S. ecliptic pole"))
    for ra_p, dec_p, color, label_p in pole_specs:
        xp, yp = project(np.array([ra_p]), np.array([dec_p]),
                         projection, center_ra_deg=center_ra_deg)
        fig.add_trace(go.Scatter(
            x=xp, y=yp, mode="markers",
            marker=dict(symbol="cross", color=color, size=9,
                        line=dict(color=color, width=0.8)),
            hovertext=[label_p], hoverinfo="text",
            showlegend=False,
        ))

    # ── Constellation lines ───────────────────────────────────────────
    if show_constellations:
        cx, cy = _project_constellation_segments(projection, center_ra_deg)
        fig.add_trace(go.Scatter(
            x=cx, y=cy, mode="lines",
            line=dict(color=constellation_color, width=0.7),
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
            marker=dict(color=star_color,
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
        # Pre-format RA/Dec sexagesimal so hover reads naturally.  Pass
        # alongside the timestamp via an object-dtype customdata.
        ra_arr = d["ra"].to_numpy()
        dec_arr = d["dec"].to_numpy()
        custom = np.array(list(zip(
            d["obstime"].astype(str).to_numpy(),
            [_ra_hms_str(r) for r in ra_arr],
            [_dec_dms_str(c) for c in dec_arr],
        )), dtype=object)
        fig.add_trace(go.Scatter(
            x=mx, y=my, mode="markers",
            marker=dict(
                color=years, colorscale=colorscale,
                size=5, line=dict(width=0),
                colorbar=dict(
                    title=dict(text="Year", font=dict(color=fg)),
                    tickformat="d",
                ),
            ),
            customdata=custom,
            hovertemplate=("%{customdata[0]}<br>"
                           "RA %{customdata[1]}<br>"
                           "Dec %{customdata[2]}<extra></extra>"),
            showlegend=False,
        ))

    # ── Predicted positions (Horizons ephemeris) ──────────────────────
    # Year 0 (next 12 months) renders in solid orange.  Years 1+ use a
    # warm-to-cool gradient (Turbo) so each subsequent year is visibly
    # distinct from the near-term track.  Non-observable dates
    # (elong < min OR V outside the slider range) render in gray
    # unless `hide_gray_predictions` is set, in which case they're
    # skipped entirely.  Prediction labels mark the first and last
    # observable date *within each year* — so multi-year forecasts get
    # one pair of labels per year.
    if predictions_df is not None and not predictions_df.empty:
        pd_sorted = predictions_df.sort_values("obstime").reset_index(
            drop=True)
        v_pred = (pd_sorted["v_pred"].to_numpy()
                  if "v_pred" in pd_sorted.columns
                  else np.full(len(pd_sorted), np.nan))
        elong = (pd_sorted["solar_elong"].to_numpy()
                 if "solar_elong" in pd_sorted.columns
                 else np.full(len(pd_sorted), np.nan))
        mxp, myp = project(pd_sorted["ra"].to_numpy(),
                           pd_sorted["dec"].to_numpy(),
                           projection, center_ra_deg=center_ra_deg)

        # Combined observability mask.  NaN values pass through so
        # older cache files without solar_elong / v_pred degrade
        # gracefully.  V-limit accepts either a single float (upper
        # bound only) or a (low, high) tuple.
        if isinstance(prediction_v_limit, (tuple, list)):
            v_lo, v_hi = float(prediction_v_limit[0]), float(
                prediction_v_limit[1])
        else:
            v_lo, v_hi = -np.inf, float(prediction_v_limit)
        elong_ok = np.isnan(elong) | (elong >= prediction_elong_min)
        vmag_ok = (np.isnan(v_pred)
                   | ((v_pred >= v_lo) & (v_pred <= v_hi)))
        observable = elong_ok & vmag_ok
        date_strs = pd_sorted["obstime"].astype(str).to_numpy()

        # Year offset: integer number of 365-day rolls past the
        # window start.  Year 0 covers ~today through today + 365 d.
        t_start = pd.Timestamp(pd_sorted["obstime"].iloc[0])
        delta_days = ((pd_sorted["obstime"] - t_start)
                      .dt.total_seconds().to_numpy() / 86400.0)
        year_offset = (delta_days // 365.25).astype(int)

        # Pre-format RA/Dec for every predicted date so the hover
        # template can pull a sexagesimal string per point.
        ra_pred = pd_sorted["ra"].to_numpy()
        dec_pred = pd_sorted["dec"].to_numpy()
        ra_str_all = np.array([_ra_hms_str(r) for r in ra_pred],
                              dtype=object)
        dec_str_all = np.array([_dec_dms_str(c) for c in dec_pred],
                               dtype=object)

        def _customdata(mask):
            return np.array(list(zip(
                date_strs[mask],
                np.where(np.isnan(v_pred[mask]), -99.0, v_pred[mask]),
                np.where(np.isnan(elong[mask]), -1.0, elong[mask]),
                ra_str_all[mask],
                dec_str_all[mask],
            )), dtype=object)

        # Year-0 observable: orange (the existing scheme).
        y0_obs = (year_offset == 0) & observable
        if y0_obs.any():
            fig.add_trace(go.Scatter(
                x=mxp[y0_obs], y=myp[y0_obs], mode="markers",
                marker=dict(
                    color="rgba(255,165,0,0.95)", size=5,
                    symbol="circle-open",
                    line=dict(color="rgba(255,165,0,0.95)",
                              width=1.2),
                ),
                customdata=_customdata(y0_obs),
                hovertemplate=(
                    "Predicted %{customdata[0]}<br>"
                    "RA %{customdata[3]}<br>"
                    "Dec %{customdata[4]}<br>"
                    "V ≈ %{customdata[1]:.1f} · "
                    "S-O-T %{customdata[2]:.1f}°"
                    "<extra></extra>"),
                showlegend=False,
            ))

        # Years 1+ observable: Turbo gradient by year-offset so each
        # subsequent year reads as a different color.  marker.color
        # carries the year number; the colorbar is suppressed because
        # the meaning is exposed in hover ("Year N").
        yN_obs = (year_offset >= 1) & observable
        if yN_obs.any():
            yvals = year_offset[yN_obs].astype(float)
            max_y = float(year_offset.max())
            fig.add_trace(go.Scatter(
                x=mxp[yN_obs], y=myp[yN_obs], mode="markers",
                marker=dict(
                    color=yvals,
                    cmin=1.0,
                    cmax=max(1.0, max_y),
                    colorscale="Turbo",
                    size=5,
                    symbol="circle-open",
                    line=dict(width=1.2),
                    showscale=False,
                ),
                customdata=np.array(list(zip(
                    date_strs[yN_obs],
                    np.where(np.isnan(v_pred[yN_obs]),
                             -99.0, v_pred[yN_obs]),
                    np.where(np.isnan(elong[yN_obs]),
                             -1.0, elong[yN_obs]),
                    yvals.astype(int),
                    ra_str_all[yN_obs],
                    dec_str_all[yN_obs],
                )), dtype=object),
                hovertemplate=(
                    "Predicted %{customdata[0]} "
                    "(Year %{customdata[3]})<br>"
                    "RA %{customdata[4]}<br>"
                    "Dec %{customdata[5]}<br>"
                    "V ≈ %{customdata[1]:.1f} · "
                    "S-O-T %{customdata[2]:.1f}°"
                    "<extra></extra>"),
                showlegend=False,
            ))

        # Non-observable dates → single gray trace (or skipped when
        # the user has hidden them).  Single trace across all years
        # keeps the chart cleaner; the year info is still in hover.
        low_mask = ~observable
        if low_mask.any() and not hide_gray_predictions:
            fig.add_trace(go.Scatter(
                x=mxp[low_mask], y=myp[low_mask], mode="markers",
                marker=dict(
                    color="rgba(150,150,150,0.55)", size=5,
                    symbol="circle-open",
                    line=dict(color="rgba(150,150,150,0.55)",
                              width=1.0),
                ),
                customdata=np.array(list(zip(
                    date_strs[low_mask],
                    np.where(np.isnan(v_pred[low_mask]),
                             -99.0, v_pred[low_mask]),
                    np.where(np.isnan(elong[low_mask]),
                             -1.0, elong[low_mask]),
                    year_offset[low_mask].astype(int),
                    ra_str_all[low_mask],
                    dec_str_all[low_mask],
                )), dtype=object),
                hovertemplate=(
                    "Predicted %{customdata[0]} "
                    "(Year %{customdata[3]}, below threshold)<br>"
                    "RA %{customdata[4]}<br>"
                    "Dec %{customdata[5]}<br>"
                    "V ≈ %{customdata[1]:.1f} · "
                    "S-O-T %{customdata[2]:.1f}°"
                    "<extra></extra>"),
                showlegend=False,
            ))

        # Per-year endpoint date labels (opt-in).  Each year of the
        # window gets its own first / last observable date, so a
        # multi-year forecast shows label pairs at every apparition.
        if show_prediction_labels:
            for y_val in sorted(set(year_offset[observable].tolist())):
                y_mask = (year_offset == y_val) & observable
                if not y_mask.any():
                    continue
                idx = np.where(y_mask)[0]
                i0, iN = int(idx[0]), int(idx[-1])
                t0_str = pd.Timestamp(pd_sorted["obstime"].iloc[i0]
                                      ).strftime("%Y-%m-%d")
                fig.add_annotation(
                    x=float(mxp[i0]), y=float(myp[i0]),
                    text=t0_str, showarrow=True, arrowhead=2,
                    arrowcolor=fg, arrowwidth=1.0,
                    ax=0, ay=-26,
                    font=dict(color="rgba(255,200,120,1)", size=11),
                    bgcolor="rgba(0,0,0,0)", borderpad=2)
                if iN != i0:
                    tN_str = pd.Timestamp(pd_sorted["obstime"].iloc[iN]
                                          ).strftime("%Y-%m-%d")
                    fig.add_annotation(
                        x=float(mxp[iN]), y=float(myp[iN]),
                        text=tN_str, showarrow=True, arrowhead=2,
                        arrowcolor=fg, arrowwidth=1.0,
                        ax=0, ay=-26,
                        font=dict(color="rgba(255,200,120,1)", size=11),
                        bgcolor="rgba(0,0,0,0)", borderpad=2)

    # ── Layout ────────────────────────────────────────────────────────
    title = (f"Finding chart — {label}" if label else "Finding chart") + \
            f"  ({projection.title()})"
    # ── Cardinal-direction badges (N / S / E / W) ─────────────────────
    # Static labels just inside the projection's whole-sky boundary.
    # East goes on the LEFT because _center_lon negates the longitude
    # for the east-left convention.  Marker size is in pixels so the
    # badges stay readable when the user zooms in.
    if projection == "rectangular":
        ax_x, ax_y = 180.0, 90.0
    elif projection in ("hammer", "mollweide"):
        ax_x, ax_y = 2.0 * np.sqrt(2.0), np.sqrt(2.0)
    elif projection == "aitoff":
        ax_x, ax_y = np.pi, np.pi / 2.0
    else:
        ax_x = ax_y = 1.0
    cardinal_x = [0.0, 0.0, -ax_x * 0.93, ax_x * 0.93]
    cardinal_y = [ax_y * 0.90, -ax_y * 0.90, 0.0, 0.0]
    cardinal_t = ["N", "S", "E", "W"]
    fig.add_trace(go.Scatter(
        x=cardinal_x, y=cardinal_y,
        mode="markers+text",
        text=cardinal_t,
        textfont=dict(color=fg, size=12),
        textposition="middle center",
        marker=dict(size=26,
                    color=bg,
                    line=dict(color=fg, width=1)),
        hoverinfo="skip", showlegend=False,
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(color=fg, size=14), x=0.02),
        autosize=True,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor=bg, plot_bgcolor=bg,
        font=dict(color=fg),
        showlegend=False,
        # Drag draws a zoom rectangle by default; the modebar's Pan
        # button toggles to drag-pan when the user prefers that.
        # Double-click resets to the projection's natural extent.
        dragmode="zoom",
        # `uirevision` preserves the user's zoom/pan state when the
        # figure is rebuilt with the same revision tag.  Caller sets
        # this from (object, projection) so control toggles (overlays,
        # V-mag slider, label visibility) don't snap the viewport
        # back to whole-sky — only switching object or projection
        # does.
        uirevision=uirevision or "default",
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
