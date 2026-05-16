"""Observation-history plot helpers.

Two-panel observation history figure: band-corrected V vs obstime on top,
site-code lifeline vs obstime on the bottom, sharing an x-axis and a
rangeslider.  Vertical bands shade intervals where solar elongation > 90°
(observable) vs ≤ 90° (near conjunction).

Sourced from the `sandbox/observation_history_*.py` prototypes (commit
b45a597); kept compatible with those scripts so they keep working.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from lib.db import connect, timed_query

# ---- Photometric band → V offsets ----------------------------------------
# Singles from sql/discovery_tracklets.sql + docs/band_corrections.md.
# Two-character codes (ATLAS, PanSTARRS) mapped to the underlying single-band
# offset; codes not in this dict default to 0.0 ("treat as V").
BAND_TO_V = {
    "V": 0.0, "v": 0.0, "B": -0.8, "U": -1.3, "R": 0.4, "I": 0.8,
    "g": -0.35, "r": 0.14, "i": 0.32, "z": 0.26, "y": 0.32, "u": 2.5,
    "w": -0.13, "c": -0.05, "o": 0.33, "G": 0.28,
    "J": 1.2, "H": 1.4, "K": 1.7, "C": 0.4, "W": 0.4, "L": 0.2, "Y": 0.7,
    "": -0.8,
    "Ao": 0.33, "Ac": -0.05, "Pw": -0.13, "Pi": 0.32,
}

PALETTE = (
    "#1f77b4 #ff7f0e #2ca02c #d62728 #9467bd #8c564b #e377c2 #7f7f7f "
    "#bcbd22 #17becf #aec7e8 #ffbb78 #98df8a #ff9896 #c5b0d5 #c49c94 "
    "#f7b6d2 #c7c7c7 #dbdb8d #9edae5 #393b79 #637939 #8c6d31 #843c39"
).split()


# ---- Ephemerides ----------------------------------------------------------

def julian_day(dt: pd.Series) -> np.ndarray:
    """Pandas datetime → Julian Day.  Treats input as UTC.

    Resolution-agnostic: forces seconds-since-epoch before dividing, so the
    same call works whether pandas stores `datetime64[ns]` (pandas <3.0) or
    `datetime64[us]` (pandas 3+).
    """
    epoch_jd = 2440587.5  # 1970-01-01 00:00 UTC
    secs = dt.to_numpy().astype("datetime64[s]").astype("int64")
    return secs / 86400.0 + epoch_jd


def sun_ra_dec(jd: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Low-precision apparent geocentric RA/Dec of the Sun in degrees.

    Meeus, Astronomical Algorithms ch. 25 (low-accuracy form).  Better than
    0.01° in longitude over 1950–2050 — plenty for an elongation threshold.

    Independent of `lib.solar.sun_ra_dec` because the latter takes pandas
    datetime arrays whereas the shading code here works in JD; harmonising
    is a follow-up.
    """
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T**2) % 360.0
    M = np.deg2rad((357.52911 + 35999.05029 * T - 0.0001537 * T**2) % 360.0)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T**2) * np.sin(M)
         + (0.019993 - 0.000101 * T) * np.sin(2 * M)
         + 0.000289 * np.sin(3 * M))
    lon = np.deg2rad((L0 + C) % 360.0)
    eps = np.deg2rad(23.43929111 - 0.0130041667 * T)
    ra = np.rad2deg(np.arctan2(np.cos(eps) * np.sin(lon), np.cos(lon))) % 360.0
    dec = np.rad2deg(np.arcsin(np.sin(eps) * np.sin(lon)))
    return ra, dec


def angular_separation(ra1, dec1, ra2, dec2) -> np.ndarray:
    r1 = np.deg2rad(ra1); d1 = np.deg2rad(dec1)
    r2 = np.deg2rad(ra2); d2 = np.deg2rad(dec2)
    cos_sep = (np.sin(d1) * np.sin(d2)
               + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2))
    return np.rad2deg(np.arccos(np.clip(cos_sep, -1.0, 1.0)))


def to_v(mag: pd.Series, band: pd.Series) -> pd.Series:
    band = band.fillna("").astype(str).str.strip()
    correction = band.map(BAND_TO_V).fillna(0.0)
    return mag + correction


# ---- Data loading ---------------------------------------------------------

def fetch_obs(*, permid: str | None = None,
              provid: str | None = None,
              conn=None) -> pd.DataFrame:
    """Pull astrometry from obs_sbn for the given designation.

    Exactly one of `permid` or `provid` must be supplied.  Returns the
    canonical columns with elongation and V_approx already computed.

    If `conn` is None a fresh connection is opened (uses PGHOST env var).
    Callers in a callback context that already hold a connection should
    pass it through to avoid the connect/disconnect overhead.
    """
    if (permid is None) == (provid is None):
        raise ValueError("supply exactly one of permid or provid")

    if permid is not None:
        sql = ("SELECT obstime, ra, dec, mag, band, stn FROM obs_sbn "
               "WHERE permid=%s AND obstime IS NOT NULL "
               "AND ra IS NOT NULL AND dec IS NOT NULL "
               "ORDER BY obstime")
        params = (permid,)
        label = f"obs_sbn[permid={permid}]"
    else:
        sql = ("SELECT obstime, ra, dec, mag, band, stn FROM obs_sbn "
               "WHERE provid=%s AND obstime IS NOT NULL "
               "AND ra IS NOT NULL AND dec IS NOT NULL "
               "ORDER BY obstime")
        params = (provid,)
        label = f"obs_sbn[provid={provid}]"

    if conn is None:
        with connect() as c:
            df = timed_query(c, sql, params=params, label=label)
    else:
        df = timed_query(conn, sql, params=params, label=label)
    if df.empty:
        return df

    df["ra"] = df["ra"].astype(float)
    df["dec"] = df["dec"].astype(float)
    df["mag"] = pd.to_numeric(df["mag"], errors="coerce")
    df["obstime"] = pd.to_datetime(df["obstime"])

    jd = julian_day(df["obstime"])
    sun_ra, sun_dec = sun_ra_dec(jd)
    df["elong"] = angular_separation(
        df["ra"].to_numpy(), df["dec"].to_numpy(), sun_ra, sun_dec)
    df["v_mag"] = to_v(df["mag"], df["band"])
    df["band_norm"] = df["band"].fillna("").astype(str).str.strip()
    return df


# ---- Shading segments -----------------------------------------------------

def compute_elong_segments(df: pd.DataFrame, grid_start: pd.Timestamp,
                           grid_end: pd.Timestamp, step: str = "3D"
                           ) -> list[tuple[pd.Timestamp, pd.Timestamp, bool]]:
    """Walk a dense time grid, interpolating the object's sky position from
    the nearest observation, and emit (x0, x1, is_above_90deg) intervals.
    """
    grid = pd.date_range(grid_start, grid_end, freq=step)
    grid_jd = julian_day(pd.Series(grid))
    g_sun_ra, g_sun_dec = sun_ra_dec(grid_jd)

    obs_jd = julian_day(df["obstime"])
    obs_ra = df["ra"].to_numpy()
    obs_dec = df["dec"].to_numpy()
    nearest = np.searchsorted(obs_jd, grid_jd)
    nearest = np.clip(nearest, 1, len(obs_jd) - 1)
    left = nearest - 1
    pick_left = (np.abs(obs_jd[left] - grid_jd)
                 < np.abs(obs_jd[nearest] - grid_jd))
    idx = np.where(pick_left, left, nearest)
    g_elong = angular_separation(obs_ra[idx], obs_dec[idx],
                                 g_sun_ra, g_sun_dec)

    above = g_elong > 90.0
    boundaries = np.flatnonzero(np.diff(above.astype(int))) + 1
    starts = np.concatenate([[0], boundaries])
    ends = np.concatenate([boundaries, [len(grid)]])
    return [(grid[s], grid[min(e, len(grid) - 1)], bool(above[s]))
            for s, e in zip(starts, ends)]


# ---- Site grouping --------------------------------------------------------

def site_groups(df: pd.DataFrame, top_n: int = 6,
                others_label: str = "Others") -> tuple[pd.Series, list[str]]:
    """Map obs to `top_n` busiest sites + others_label.

    Returns (group_series, ordered_categories_top_first).  The ordered list
    is suitable for `yaxis.categoryarray` with `autorange='reversed'` so the
    busiest site sits at the top of the panel.
    """
    counts = df["stn"].value_counts()
    top = list(counts.head(top_n).index)
    has_others = len(counts) > top_n
    group = df["stn"].where(df["stn"].isin(top), others_label)
    order = top + ([others_label] if has_others else [])
    return group, order


# ---- Figure builder -------------------------------------------------------

_DARK_BAND_ABOVE = "#3d3520"   # muted yellow-ish for elong > 90°
_DARK_BAND_BELOW = "#2a2a2a"   # grey for elong ≤ 90°
_LIGHT_BAND_ABOVE = "#fff2c7"
_LIGHT_BAND_BELOW = "#e6e6e6"


def build_history_figure(df: pd.DataFrame, *, name: str,
                         title_extra: str = "",
                         grid_start: pd.Timestamp | None = None,
                         grid_end_pad_days: int = 0,
                         v_presets: list[tuple[str, dict]] | None = None,
                         top_n_sites: int = 10,
                         height: int = 820,
                         theme: dict | None = None,
                         with_controls: bool = True) -> go.Figure:
    """Two-panel observation history figure.

    Top panel: V (band-corrected) vs obstime, per-band scatter, with vertical
    elongation-shading bands.
    Bottom panel: site code vs obstime, top_n busiest + 'Others'.

    The two panels share the x-axis and a rangeslider lives below the bottom
    panel for free-form time selection.  Each photometric band is one
    legend entry; toggling it affects both panels.
    """
    if grid_start is None:
        grid_start = df["obstime"].min().normalize()
    grid_end = (df["obstime"].max().normalize()
                + pd.Timedelta(days=grid_end_pad_days))

    segments = compute_elong_segments(df, grid_start, grid_end)
    df = df.copy()
    df["site_row"], site_order = site_groups(df, top_n=top_n_sites)

    is_dark = bool(theme and theme.get("template") == "plotly_dark")
    band_above = _DARK_BAND_ABOVE if is_dark else _LIGHT_BAND_ABOVE
    band_below = _DARK_BAND_BELOW if is_dark else _LIGHT_BAND_BELOW
    plot_template = (theme.get("template") if theme
                     else "plotly_white")
    fg_color = theme.get("text") if theme else "#222"
    subtext_color = theme.get("subtext") if theme else "#666"
    button_bg = theme.get("paper") if theme else "#ffffff"
    button_border = theme.get("hr_color") if theme else "#cccccc"

    # When the object has no usable photometry (all mag NULL — e.g.
    # historical photographic plates), omit the V panel entirely and
    # surface a single-panel site lifeline.  This is the right shape
    # for old comets like C/1913 J1 where positional data exists but
    # there are no calibrated magnitudes.
    has_v = bool(df["v_mag"].notna().any())

    if has_v:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.55, 0.45], vertical_spacing=0.04,
        )
        shading_yrefs = ["y domain", "y2 domain"]
    else:
        fig = make_subplots(rows=1, cols=1)
        shading_yrefs = ["y domain"]

    def _shapes_for(yref: str) -> list[dict]:
        return [
            dict(type="rect", xref="x", yref=yref,
                 x0=x0, x1=x1, y0=0, y1=1,
                 fillcolor=band_above if is_above else band_below,
                 opacity=0.55, line=dict(width=0), layer="below")
            for x0, x1, is_above in segments
        ]
    shapes_visible = sum((_shapes_for(yref) for yref in shading_yrefs), [])
    shapes_hidden = [{**s, "visible": False} for s in shapes_visible]

    site_row = 2 if has_v else 1
    band_counts = df["band_norm"].value_counts()
    for i, band in enumerate(band_counts.index):
        sub = df[df["band_norm"] == band]
        if sub.empty:
            continue
        label = band if band else "(blank)"
        color = PALETTE[i % len(PALETTE)]
        if has_v:
            top_hover = [
                f"{r.obstime:%Y-%m-%d %H:%M}<br>"
                f"stn {r.stn}  band {label}<br>"
                f"m={r.mag:.2f}  V≈{r.v_mag:.2f}<br>"
                f"elong={r.elong:.1f}°"
                for r in sub.itertuples()
            ]
            bot_hover = [
                f"{r.obstime:%Y-%m-%d %H:%M}<br>"
                f"stn {r.stn}  band {label}<br>"
                f"V≈{r.v_mag:.2f}  elong={r.elong:.1f}°"
                for r in sub.itertuples()
            ]
        else:
            bot_hover = [
                f"{r.obstime:%Y-%m-%d %H:%M}<br>"
                f"stn {r.stn}  band {label}<br>"
                f"elong={r.elong:.1f}°"
                for r in sub.itertuples()
            ]
        legendgroup = f"band:{label}"
        if has_v:
            fig.add_trace(go.Scatter(
                x=sub["obstime"], y=sub["v_mag"],
                mode="markers",
                marker=dict(size=5, color=color, line=dict(width=0)),
                text=top_hover, hoverinfo="text",
                name=f"{label}  ({len(sub):,})",
                legendgroup=legendgroup, showlegend=True,
            ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=sub["obstime"], y=sub["site_row"],
            mode="markers",
            marker=dict(size=6, color=color,
                        symbol="line-ns-open",
                        line=dict(width=1.5, color=color)),
            text=bot_hover, hoverinfo="text",
            name=f"{label}  ({len(sub):,})",
            legendgroup=legendgroup, showlegend=not has_v,
        ), row=site_row, col=1)

    title = (f"Observation history — {name}<br>"
             f"<sub>{len(df):,} obs from obs_sbn, "
             f"{df['stn'].nunique()} stations, "
             f"{df['obstime'].min():%Y} – {df['obstime'].max():%Y}"
             f"{('; ' + title_extra) if title_extra else ''}</sub>")

    if v_presets is None:
        v_presets = [
            ("auto", dict(autorange="reversed")),
            ("12 – 25", dict(autorange=False, range=[25, 12])),
        ]

    button_style = dict(
        bgcolor=button_bg,
        bordercolor=button_border,
        borderwidth=1,
        font=dict(color=fg_color, size=12, family="sans-serif"),
    )

    # The Reset-axes args list depends on whether the V panel exists.
    # When it does we restore the reversed V autoscale AND yaxis2; in
    # the lifeline-only case yaxis is the categorical site axis.
    if has_v:
        reset_args = {"xaxis.autorange": True,
                      "yaxis.autorange": "reversed",
                      "yaxis2.autorange": True}
    else:
        reset_args = {"xaxis.autorange": True,
                      "yaxis.autorange": True}

    # In-figure controls are only useful for the sandbox / standalone
    # paths.  The Dash app sets with_controls=False and drives the plot
    # via html.Button + dcc.RangeSlider below the dcc.Graph, which lets
    # them inherit the theme's button CSS instead of fighting Plotly's
    # built-in light hover styling.
    controls_y = -0.32
    updatemenus = []
    if with_controls:
        updatemenus.append(dict(
            type="buttons", direction="right", showactive=False,
            x=0.30, xanchor="left", y=controls_y, yanchor="top",
            pad=dict(t=4, b=4),
            **button_style,
            buttons=[
                dict(label="Reset axes",
                     method="relayout", args=[reset_args]),
                dict(label="Show all bands",
                     method="restyle", args=[{"visible": True}]),
                dict(label="Toggle elongation shading",
                     method="relayout",
                     args=[dict(shapes=shapes_hidden)],
                     args2=[dict(shapes=shapes_visible)]),
            ],
        ))
        if has_v:
            updatemenus.append(dict(
                type="buttons", direction="right", showactive=False,
                x=0.555, xanchor="left", y=controls_y, yanchor="top",
                pad=dict(t=4, b=4),
                **button_style,
                buttons=[
                    dict(label=f"V: {lbl}", method="relayout",
                         args=[{f"yaxis.{k}": v for k, v in spec.items()}])
                    for lbl, spec in v_presets
                ],
            ))

    caption = ("Shading: pale yellow / muted gold = solar elongation "
               "> 90° (observable); grey = ≤ 90° (near conjunction).  "
               "Drag the strip below the lower panel to scrub through "
               "time.")
    annotations = [dict(
        text=caption, xref="paper", yref="paper",
        x=0, y=(-0.44 if with_controls else -0.20),
        xanchor="left", showarrow=False,
        font=dict(size=11, color=subtext_color),
    )]
    if not has_v:
        annotations.append(dict(
            text=("No V-band magnitudes available for this object — "
                  "showing observation timing only."),
            xref="paper", yref="paper",
            x=0.5, y=1.06, xanchor="center", showarrow=False,
            font=dict(size=12, color=subtext_color, family="sans-serif"),
        ))

    fig.update_layout(
        shapes=shapes_visible,
        title=dict(text=title, font=dict(color=fg_color)),
        template=plot_template,
        height=height,
        legend=dict(
            title=dict(text=(
                "Photometric band<br><sub>click to hide · "
                "double-click to isolate</sub>"),
                       font=dict(color=fg_color)),
            font=dict(color=fg_color),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant", traceorder="normal",
        ),
        updatemenus=updatemenus,
        annotations=annotations,
        margin=dict(t=110, b=(220 if with_controls else 110), r=180),
        paper_bgcolor=(theme.get("paper") if theme else None),
        plot_bgcolor=(theme.get("plot") if theme else None),
    )

    if has_v:
        fig.update_yaxes(title_text="V (band-corrected, mag)",
                         autorange="reversed", row=1, col=1)
        fig.update_yaxes(title_text="Site code",
                         categoryorder="array",
                         categoryarray=list(reversed(site_order)),
                         row=2, col=1)
        fig.update_xaxes(title_text="Observation time",
                         rangeslider=dict(visible=True, thickness=0.05),
                         type="date", row=2, col=1)
    else:
        fig.update_yaxes(title_text="Site code",
                         categoryorder="array",
                         categoryarray=list(reversed(site_order)),
                         row=1, col=1)
        fig.update_xaxes(title_text="Observation time",
                         rangeslider=dict(visible=True, thickness=0.05),
                         type="date", row=1, col=1)
    return fig


def write_html(fig: go.Figure, output_path) -> None:
    """Write `fig` to `output_path` as a self-contained HTML page."""
    output_path.write_text(
        pio.to_html(fig, include_plotlyjs="cdn", full_html=True))
