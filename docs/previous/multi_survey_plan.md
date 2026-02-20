# Multi-survey Comparison Tab — Implementation Plan

## Context

NEOs are often detected by multiple surveys during their discovery apparition (~200 days). The user wants a new "Multi-survey Comparison" tab showing which surveys co-detected NEOs, visualized as Venn/Euler diagrams. This requires a new SQL query and cache layer for apparition-window observations, plus new Plotly visualizations. The cache design must support future follow-up analysis.

## File to Modify

- `app/discovery_stats.py` — all changes in this single file (following existing pattern)

## 1. SQL Query (APPARITION_SQL)

Reuses the existing `neo_list` and `discovery_obs_all` CTEs from LOAD_SQL, then adds an `apparition_obs` CTE that fetches **all observations** within ±200 days of each NEO's discovery:

```
neo_list → discovery_info (DISTINCT ON earliest disc='*')
         → apparition_obs (3-branch UNION ALL, joining on permid/provid with obstime BETWEEN disc-200d AND disc+200d)
```

**Output columns**: `designation`, `obsid`, `stn`, `obstime`, `disc_obstime`

The ±200 day window (400 days total) captures both precoveries and post-discovery detections. The precovery toggle filters client-side — no re-query needed.

**Deduplication**: Include `obsid` to deduplicate across the 3 UNION branches (numbered objects can match via both permid and num_provid).

**Estimated performance**: ~60-120s first run (3 obs_sbn scans via permid/provid indexes with obstime filter). Returns ~1-2M raw observation rows, aggregated to ~100-200K tracklets in Python before caching.

## 2. Cache Design — Tracklet-Level Persistence

After SQL returns raw observations, Python aggregates to tracklets:
- **trkid not NULL**: GROUP BY (designation, trkid)
- **trkid is NULL**: GROUP BY (designation, stn, date) as fallback

**Cached columns** (one row per tracklet per NEO):

| Column | Type | Purpose |
|--------|------|---------|
| designation | str | NEO identifier (joins to main df) |
| trkid | str/null | MPC tracklet ID |
| station_code | str | Observatory code |
| project | str | Survey name (mapped from stn) |
| first_obs | datetime | Earliest obs in tracklet |
| last_obs | datetime | Latest obs in tracklet |
| nobs | int | Observation count |
| disc_obstime | datetime | Discovery timestamp |
| days_from_disc | float | (first_obs - disc_obstime) in days |

This granularity supports both the current multi-survey comparison and future targeted follow-up analysis (tracklet timing, sequence, cadence).

**Cache files**: `.apparition_cache_{hash}.csv` + `.meta` (same pattern as existing cache, same 24h TTL).

## 3. Loading Strategy — Lazy Load

- Do **not** block app startup with the apparition query
- `df_apparition = None` at module level
- On first access to tab-comparison, check for fresh cache → load CSV (~1-2s) or query DB (~60-120s)
- `dcc.Loading` wrapper provides spinner during first load
- `--refresh` flag forces both caches to refresh

**Refactor**: Extract current `load_data()` logic into a generic `load_cached_query(sql, prefix, label, force)` helper. Both the existing discovery cache and the new apparition cache use this.

## 4. Tab Layout

New tab "Multi-survey Comparison" (`value="tab-comparison"`) after the existing two tabs.

**Controls row:**
- **Discovery years** — RangeSlider (id: `comp-year-range`), default [2004, year_max] (modern multi-survey era)
- **Size class** — Dropdown (id: `comp-size-filter`), same options as Tab 1 minus "Split sizes"
- **Surveys for Venn** — Dropdown multi-select (id: `comp-survey-select`), options from PROJECT_ORDER, default ["Catalina", "Pan-STARRS", "ATLAS"], max 3
- **Precovery** — RadioItems (id: `comp-precovery`), "Post-discovery only" (default) / "Include precoveries"

Shared banner controls (Group by, Plot height, Theme) apply as usual.

**Visualizations (2×2 grid):**

| Top left | Top right |
|----------|-----------|
| **Venn diagram** (id: `venn-diagram`) — 2 or 3 selected surveys | **Survey reach** (id: `survey-reach`) — horizontal bar chart of NEOs per survey |

| Bottom left | Bottom right |
|-------------|--------------|
| **Pairwise heatmap** (id: `pairwise-heatmap`) — co-detection % matrix | **Summary stats** (id: `comparison-summary`) — key numbers (total NEOs, multi-survey %, median surveys per NEO) |

## 5. Data Processing — `build_survey_sets()`

```python
def build_survey_sets(df_main, df_apparition, year_range, size_filter, exclude_precovery):
    # 1. Filter main df by year range and size class → eligible NEO set
    # 2. Filter apparition tracklets to eligible NEOs
    # 3. If exclude_precovery: keep only tracklets where days_from_disc >= 0
    # 4. Return dict[project_name → set[designation]]
```

## 6. Visualizations — All Pure Plotly (No New Dependencies)

### Venn Diagram (Plotly shapes + annotations)

- **2-set**: Two overlapping circles, 3 region counts (A only, both, B only)
- **3-set**: Three circles in triangle arrangement, 7 region counts
- Fixed-size circles (not area-proportional) with count labels in each region
- Circle fill colors from PROJECT_COLORS with opacity=0.25
- Set names + totals annotated above each circle
- Title: "NEOs co-detected during discovery apparition"
- Note: "Circle sizes are not proportional — see counts"

### Survey Reach Bar Chart

Horizontal bars showing total unique NEOs detected per survey during apparition windows (within selected filters). Uses PROJECT_COLORS. Provides context for the Venn overlaps.

### Pairwise Co-detection Heatmap

`go.Heatmap` with surveys on both axes. Cell[i,j] = % of survey i's NEOs also detected by survey j. Diagonal = total count. Asymmetric (reading across a row answers "what fraction of this survey's NEOs did other surveys also see?").

### Summary Statistics

`go.Table` or HTML showing:
- Total NEOs in selection
- NEOs detected by exactly 1, 2, 3+ surveys
- Mean/median surveys per NEO
- Discovery survey breakdown

## 7. Callback

Single callback with 4 outputs (venn, reach, heatmap, summary), triggered by:
- `comp-year-range`, `comp-size-filter`, `comp-survey-select`, `comp-precovery` (tab controls)
- `theme-toggle`, `plot-height` (shared)
- `tabs` (for lazy load trigger and tab-switch re-render)

Guard: `if active_tab != "tab-comparison": raise PreventUpdate`

Validate survey selection: require 2-3 for Venn, show message if <2.

## 8. Implementation Steps

1. **Refactor `load_data()`** into generic `load_cached_query()` helper
2. **Add `APPARITION_SQL`** constant (extending the 3-way UNION pattern)
3. **Add tracklet aggregation** function (raw obs → tracklet DataFrame)
4. **Add lazy loader** `load_apparition_data()` with `dcc.Loading` support
5. **Add `build_survey_sets()`** data processing function
6. **Add Venn rendering** functions (`make_venn2`, `make_venn3`)
7. **Add supplementary viz** functions (reach bar, heatmap, summary)
8. **Add tab layout** (third `dcc.Tab` with controls and graph placeholders)
9. **Add callback** wiring all inputs to 4 outputs
10. **Test** — verify with real data, check dark/light themes, edge cases

## 9. Verification

- Run app with `python app/discovery_stats.py`
- First click on "Multi-survey Comparison" tab should show loading spinner, then populate
- Verify Venn counts: A_only + B_only + both = total unique across A and B
- Toggle precovery: counts should increase when including precoveries
- Narrow year range to recent years: Catalina/ATLAS/Pan-STARRS should show substantial overlap
- Switch themes: all charts should follow dark/light correctly
- Check plot height control applies to the new tab's charts
