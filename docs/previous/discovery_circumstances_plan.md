# Discovery Circumstances Tab — Implementation Plan

## Context

The Dash app has 4 tabs exploring NEO discoveries (by year, size distribution, multi-survey overlap, follow-up timing). Tab 5 answers: *where, how bright, and how fast are NEOs when discovered?* This reveals survey detection biases, sky coverage, and the relationship between NEO properties and observability.

The data already exists — `sql/discovery_tracklets.sql` computes RA, Dec, apparent magnitude, rate of motion, and position angle for all ~44K NEO discovery tracklets. We just need to bring those columns into the app's `LOAD_SQL` query.

## File to Modify

- `app/discovery_stats.py` — all changes in this single file

## 1. Extend LOAD_SQL

The existing `LOAD_SQL` shares the same CTE structure as `discovery_tracklets.sql` (`neo_list` → `discovery_obs_all` → `discovery_info`). Add two CTEs copied from `discovery_tracklets.sql`:

**A. Expand `discovery_obs_all`** — add `obs.obsid, obs.trkid` to all three UNION ALL branches (currently only selects `unpacked_desig, stn, obstime`).

**B. Expand `discovery_info`** — add `obsid, NULLIF(trkid, '') AS trkid` to the DISTINCT ON select.

**C. New CTE: `tracklet_obs_all`** (from `discovery_tracklets.sql` lines 180–209) — fetches all observations in the discovery tracklet via `trkid` with ±12h safety cap; falls back to single obs when `trkid IS NULL`. Selects `ra, dec, mag, band, obstime`.

**D. New CTE: `discovery_tracklet_stats`** (from lines 211–275) — GROUP BY to compute `avg_ra_deg`, `avg_dec_deg`, `median_v_mag` (with band corrections), `nobs`, `span_hours`, `span_days`, plus first/last coordinates for rate/PA.

**E. Expand final SELECT** — join with `discovery_tracklet_stats` and add 6 new output columns:

| Column | Type | Source |
|--------|------|--------|
| `avg_ra_deg` | float | Mean RA of discovery tracklet (degrees) |
| `avg_dec_deg` | float | Mean Dec of discovery tracklet (degrees) |
| `median_v_mag` | float | Median V-band magnitude (band-corrected) |
| `tracklet_nobs` | int | Number of observations in tracklet |
| `rate_deg_per_day` | float | Great-circle rate (Haversine); NULL if nobs=1 |
| `position_angle_deg` | float | Bearing 0=N, 90=E; NULL if nobs=1 |

The SQL hash changes → old cache auto-invalidated → fresh query on next startup (~30s). Row count stays ~44K.

## 2. Module-Level Constants

Add ecliptic and galactic plane coordinate arrays (precomputed at import time, ~10 lines each) for the sky map overlay:

- **Ecliptic**: obliquity ε=23.44°, parametric `(RA, Dec)` from ecliptic longitude 0→360°
- **Galactic plane**: galactic pole at (RA=192.86°, Dec=27.13°), parametric `(RA, Dec)` from galactic longitude 0→360° at b=0

Both verified: ecliptic Dec range ±23.4°, galactic Dec range ±62.9°.

## 3. Tab Layout

New tab "Discovery Circumstances" (`value="tab-circumstances"`) after Tab 4.

**Controls:**
- **Discovery years** — RangeSlider (id: `circ-year-range`), default [2004, year_max]
- **Size class** — Dropdown (id: `circ-size-filter`), All sizes + H_BINS options
- **Color by** — RadioItems (id: `circ-color-by`): Survey / Size class / Year

**Visualizations (2×2 grid):**

| Top left | Top right |
|----------|-----------|
| **Sky map** (id: `sky-map`) — RA/Dec scatter of discovery positions | **Apparent magnitude** (id: `mag-distribution`) — histogram of V mag at discovery |

| Bottom left | Bottom right |
|-------------|--------------|
| **Rate of motion** (id: `rate-plot`) — rate vs H magnitude scatter | **Position angle** (id: `pa-rose`) — polar histogram of motion direction |

## 4. Visualizations

### Sky Map (`_make_sky_map`)
- `go.Scattergl` (WebGL) for ~40K points, marker size 3, opacity 0.3
- RA axis reversed (360→0, astronomical convention)
- Ecliptic plane overlay: dashed yellow `go.Scatter` line
- Galactic plane overlay: dashed gray line
- Lines split at RA wraparound (insert NaN where ΔRA > 30°)
- Color by survey (PROJECT_COLORS), size class (SIZE_COLORS), or year (Viridis continuous)
- Title: "Discovery sky positions"

### Apparent Magnitude (`_make_mag_distribution`)
- `go.Histogram` with 0.5-mag bins
- Stacked by survey or size class when `color_by` matches; single color for year mode
- x-axis: "Apparent V magnitude at discovery"
- Drop rows where `median_v_mag` is NULL

### Rate of Motion (`_make_rate_plot`)
- `go.Scattergl` — x: absolute H, y: rate (deg/day), log y-scale
- Reveals size–distance–motion correlation
- Drop NULL rates (single-obs tracklets); annotate excluded count
- Color follows `color_by` setting

### Position Angle Rose (`_make_pa_rose`)
- `go.Barpolar` with 15° bins (24 sectors)
- 0=North, 90=East (standard PA convention)
- Single color (theme-appropriate)
- Drop NULL PAs (single-obs tracklets)

## 5. Callback

```python
@app.callback(
    Output("sky-map", "figure"),
    Output("mag-distribution", "figure"),
    Output("rate-plot", "figure"),
    Output("pa-rose", "figure"),
    Input("circ-year-range", "value"),
    Input("circ-size-filter", "value"),
    Input("circ-color-by", "value"),
    Input("group-by", "value"),
    Input("theme-toggle", "value"),
    Input("plot-height", "value"),
    Input("tabs", "value"),
)
def update_circumstances(...):
    if active_tab != "tab-circumstances" or df is None:
        raise PreventUpdate
    # filter by year/size, call 4 helper functions
```

## 6. Reset Infrastructure

- `_get_defaults()`: add `circ-year-range`, `circ-size-filter`, `circ-color-by`
- `_TAB_KEYS`: add `"tab-circumstances"` entry
- `_RESET_ORDER`: append 3 control IDs before shared keys

## 7. Implementation Steps

1. Extend `LOAD_SQL` with `tracklet_obs_all` and `discovery_tracklet_stats` CTEs
2. Add ecliptic/galactic plane constants
3. Add 4 helper functions (`_make_sky_map`, `_make_mag_distribution`, `_make_rate_plot`, `_make_pa_rose`)
4. Add Tab 5 layout
5. Add `update_circumstances` callback
6. Update `_get_defaults()`, `_TAB_KEYS`, `_RESET_ORDER`
7. Update CLAUDE.md with Tab 5 description

## 8. Verification

- Run app; click "Discovery Circumstances" tab
- Sky map: NEOs should cluster near the ecliptic; galactic plane should show avoidance zone
- Magnitude histogram: peak around V=20–21 (typical survey limit)
- Rate plot: positive correlation between H (faint=small) and rate (fast=close)
- Rose diagram: dominant E–W motion direction (ecliptic plane opposition motion)
- Toggle Color by: survey colors should match other tabs
- Toggle themes, plot height, year range, size filter
- Verify Reset Tab/All works for new controls
