# Claude Code Project Guide

## Project Overview

CSS MPC Toolkit — SQL scripts, Python libraries, and interactive
applications for deriving value-added datasets from the MPC (Minor Planet
Center) PostgreSQL database, maintained by the Catalina Sky Survey at the
University of Arizona.

## Database Access

- **Host:** `$PGHOST` (set in environment; RHEL 8.6, 251 GB RAM, HDD)
- **Database:** `mpc_sbn` — PostgreSQL 15.2, logical replication from MPC
- **Connect:** `psql -h $PGHOST -U claude_ro mpc_sbn`
- **Python:** `from lib.db import connect, timed_query`
- **Credentials:** `~/.pgpass` (readonly role `claude_ro`)

### Critical Performance Rules

- **obs_sbn has 526M+ rows (239 GB)** — NEVER run unfiltered COUNT,
  COUNT(DISTINCT), or full-table scans. Always use indexed lookups.
- **Indexed columns on obs_sbn:** obsid, permid, provid, stn, trkid,
  trksub, trkmpc, obstime, created_at, updated_at, submission_block_id
- **No foreign keys** anywhere in the schema — all joins use text field
  matching; referential integrity is unenforced

### Key Data Quirks

- **mpc_orbits** (1.51M rows): cometary elements (q,e,i) for ALL rows,
  but Keplerian (a, period) for only 43%. Always derive
  `a = q/(1-e)` when e<1. See `lib/orbits.py` DERIVED_COLUMNS.
- **orbit_type_int is NULL for 35%** — use `classify_from_elements()`
  in `lib/orbit_classes.py` to recover 99.2%
- **earth_moid NULL for 70%** of mpc_orbits
- **CAST(jsonb_text AS numeric)** returns Python Decimal — use
  `::double precision` in SQL for pandas compatibility
- **`orbit_quality` in JSONB is text** ("good", etc.) — don't CAST to
  numeric

## Project Structure

```
app/                          # Interactive Dash web application
  discovery_stats.py          #   NEO discovery explorer (13 tabs, ~15,500 lines)
  assets/                     #   CSS, theme, custom JS (finding_chart.js,
                              #     slider_linked.js, keyboard.js)
  .horizons_cache/            #   Per-object Horizons ephemeris parquet
                              #     (gitignored; 1-week TTL)
lib/                          # Python library layer
  db.py                       #   DB connections, timed queries, QueryLog
  orbits.py                   #   Parameterized query builders for mpc_orbits
  orbit_classes.py            #   Classification constants, Tisserand, colors
  mpc_convert.py              #   80-col format converters, designation pack/unpack
  observation_history.py      #   V-vs-time figure for the obshist tab
  finding_chart.py            #   Projection math, graticule, NSEW, predictions
  horizons.py                 #   JPL Horizons web-API client + parquet cache
  api_clients.py              #   JPL SBDB/Sentry, NEOfixer, NEOCC, MPC archive
                              #     (shared throttle, failure cooldown, APIREQ log)
  mpec_parser.py              #   MPC.net MPEC list + body fetch / parse (5 req/s)
  ades_export.py              #   ADES XML/PSV generation from NEOCP data
  ades_validate.py            #   XSD validation
sql/                          # SQL scripts
  discovery_tracklets.sql     #   Main NEO discovery statistics (43,629 tracklets)
  css_utilities_functions.sql #   PostgreSQL equivalents of Python converters
  obs_summary_all.sql         #   Full-catalog obs aggregate matview (1.6M rows)
  ades_export.sql             #   ADES-ready columns from NEOCP
  viz/                        #   Reference queries for visualization
data/                         # Vendored static reference data
  finding_chart/              #   Hipparcos V<6 + IAU constellation boundaries
scripts/                      # Operational tools
  run_pipeline.sh             #   Execute SQL, validate, upload discovery tracklets
  db_health_check.sh          #   Diagnostic: replication, dead tuples, indexes
notebooks/                    # Jupyter Lab exploration (strip outputs before commit)
  01_query_profiling.ipynb
  02_orbital_elements.ipynb
  03_data_quality.ipynb
schema/                       # ADES format XSD schemas
  general.xsd, submit.xsd
docs/                         # Source tables, band corrections
sandbox/                      # Analysis notes, exploratory outputs
```

## Interactive App (`app/discovery_stats.py`)

Dash web application at http://127.0.0.1:8050/ (prod) and
http://127.0.0.1:8051/ (dev/`--rnd --dev-tabs`) with thirteen
tabbed pages on dev, twelve on prod. Tab indices below are the
layout order on the `station-report` dev branch; on prod (`main`)
the Station Report tab is hidden by the `--dev-tabs` flag and
About shifts from Tab 12 to Tab 11. All other tabs — including
Observation history — are live on prod.

### Tab 0: MPEC Browser
- Searchable list of recent Minor Planet Electronic Circulars
  (designation- or MPEC-ID-based search) plus a viewer panel showing
  the full text of the selected MPEC.
- Per-MPEC enrichment cards pull live metadata: JPL SBDB orbit, JPL
  Sentry impact risk, NEOfixer orbit + ephemeris + ADES, ESA NEOCC
  risk list. These fire on a 60 s `dcc.Interval` poll (up to 10×).
  Enrichment calls (`lib/api_clients.py`) are per-host rate-limited
  (JPL 4 req/s, others 5 req/s), cache failures with an escalating
  cooldown, and emit one `APIREQ` log line per outbound call; MPC
  fetches keep the separate 5 req/s `lib/mpec_parser.py::_mpc_throttle`.
  See `docs/dashboard_security.md` → "Outbound politeness".
- MPEC list itself is fetched live from MPC each time the tab opens;
  individual MPEC bodies are memoized to disk under
  `app/.mpec_cache/` (one `.txt` + `.nav` per MPEC, populated on
  first access). The on-disk cache is NOT touched by the daily
  refresh — it grows monotonically as users browse.
- Data: live; not part of the parquet-cache pipeline.

### Tab 1: NEO Consensus
- Cross-source membership view of the `css_neo_consensus` schema:
  per-NEO booleans across MPC NEA.txt, `mpc_orbits` (q ≤ 1.3), JPL
  CNEOS, ESA NEOCC, CSS NEOfixer, Lowell `astorb`. Highlights
  agreements / disagreements among the six sources.
- **Filter panel** (five columns):
  - Per-source 3-state radios (Inc / Exc / Any) + a `hide_all_six`
    checklist (the "show only disagreements" toggle).
  - Class radios (Atira / Aten / Apollo / Amor / Mars-x) with
    auto-Only/Exc switching.
  - Numbered / Named bool rows.
  - "Filter by range" column: q / e / i / H / U / Nopp min-max
    inputs; first_obs / last_obs date ranges.
  - **"Misc. filters" column** (added 2026-05-29):
    Alias (Any / Is alias / Has alias — scoped to the table's own
    pairing, NOT MPC's full `current_identifications` catalogue);
    `Disc by` free-text obscode filter (whitelist-validated against
    MPC obscode shape); 7-bin Arc dropdown with sub-day bins
    (`< 3 h`, `3–6 h`, `6–12 h`, `12 h – 1 d`, `1–30 d`, `30 d – 1 yr`,
    `≥ 1 yr`); precise `Arc (hr)` min/max numeric range; Sites
    3-state (Any / Single-site ≤ 2 / Multi ≥ 3) backed by the new
    `obs_summary.n_stns` column.
- **Above-the-table controls**: `Find:` navigation search box
  (matches primary_desig / permid / iau_name, case-insensitive +
  space-tolerant via `REGEXP_REPLACE`; whitelist guard against SQL
  injection); `Open external links in:` dropdown (JPL SBDB /
  Sentry / MPC Explorer / MPC DB / NEOfixer / ESA NEOCC -- NEOCC
  routes through permid for numbered NEOs so it lands on their
  records).
- **Per-row `↗` column** is a markdown link to whichever target the
  Open-in dropdown picked. All links open in a new tab
  (`markdown_options={"link_target": "_blank"}` on the DataTable).
- **Table identity columns**: Designation (= primary_desig =
  unpacked primary provisional, NEVER a number); Permid; Name;
  Alias? + True primary (populated when the row's primary_desig is
  itself a secondary in `current_identifications` -- nine rows
  today, the Rubin-tracklet-was-actually-a-comet pair plus seven
  asteroidal case-B aliases).
- **Plot #1**: horizontal disagreement-breakdown bar (one segment
  per "Missing from X" / "Only in X" pattern + a single gray
  "Mixed (2-4 sources)" catch-all).
- **Plot #2 (UpSet)**: top bars per source-membership pattern,
  dot matrix below. Controls just above the plot:
  - **Color overlay** radio: Pattern (default consensus gradient)
    / Discovery site / H mag (size, with 19.25 and 24.25 thresholds
    for ≈ 500 m and ≈ 50 m) / Discovery decade / Arc length / q
    distance from 1.3. Non-Pattern options stack each column by
    overlay category, horizontal legend at the top.
  - **Show Mixed (2-4) bin** checkbox: appends a single aggregated
    column on the right for the 2-3-4-source disagreement set.
  - **Show Rare (rank > 15) bin** checkbox: appends another column
    aggregating patterns beyond the top-15 cutoff. Distinct from
    Mixed -- Rare is by *rank*, Mixed is by source-pattern *type*.
  - **Height** S / M / L radio (280 / 400 / 560 px). Default M.
- **Click-to-filter** on plot #2: clicking a pattern bar snaps the
  source radios to that pattern; clicking an overlay segment ALSO
  writes a `{category, color_by}` filter to a Store; clicking the
  Mixed or Rare aggregate bars writes `mixed_only` or `rare_only`.
  A chip below plot #2 surfaces the active overlay/aggregate filter
  with a Clear button. Auto-cleared on color-overlay change.
- **Histogram strip below the table**: five small bar charts
  (Discovery site / H / Decade / Arc / q distance) reflecting the
  current filtered df with the same palettes as the upset overlay.
- **Heatmap below the histograms**: discovery station × source-
  membership pattern grid (rows: top-10 stations + Other +
  (unknown); cols: top-12 patterns labelled P1..P12 with full
  hover). Cell color = count of NEOs at that intersection. Pairs
  with the upset above and the histograms in between: where the
  upset slices each pattern column by overlay-as-color and the
  histograms slice by overlay-as-x, this heatmap slices by
  station-as-y.
- **Downloads**: "Download designations" (one designation per
  line; checkbox toggles packed format for numbered NEOs ->
  packed permanent like `00433` / `~0fr6`, unnumbered -> packed
  provisional from the row); "Download NEA.txt subset" (original
  MPCORB lines for displayed objects on MPC's NEA.txt).
- **Reset button** (in the tab header alongside the all-six
  preset) covers every control on the page -- 44 outputs spanning
  filters, display radios, download toggle, and the click-filter
  Store. Preset preserves display choices via `no_update`.
- Snapshot stats card surfaces total / all-six / disagreements
  counts at a glance.
- Data: live join on `css_neo_consensus.v_membership_wide` against
  `obs_summary` (per-NEO `first_obs` / `last_obs` / `arc_days` /
  `nobs` / `n_stns` / `disc_by`) and `current_identifications` for
  alias resolution. `n_stns` was added to the `obs_summary` matview
  on 2026-05-29 -- the previous schema had to compute it per render.

### Tab 2: Discoveries by Year
- Stacked bar chart of NEO discoveries by year/survey
- Grouping: Combined, by Project (CNEOS definitions), or by Station
- Size class filtering with "Split sizes" mode (viridis-colored
  stacking by H magnitude bin)
- Annual or cumulative views
- Secondary row: size distribution histogram + top-15 stations table

### Tab 3: Size Distribution vs. NEOMOD3
- Half-magnitude bin chart comparing MPC discoveries to NEOMOD3
  population model (Nesvorny et al. 2024, Icarus 411)
- Undiscovered remainder bars, completeness curve with 1-sigma errors
- Differential or cumulative modes
- NEOMOD3 reference table with per-bin completeness

### Tab 4: Multi-survey Comparison
- Venn diagrams (1-3 surveys) showing co-detection during discovery
  apparitions (observations within +/-200 days of discovery)
- Survey reach bar chart, pairwise co-detection heatmap, summary stats
- Precovery toggle, collapsible MPC codes reference
- Data: `APPARITION_SQL` uses `CROSS JOIN LATERAL` with
  `AS MATERIALIZED` CTEs for indexed scans (~1-2 min query)

### Tab 5: Follow-up Comparison
- Per-site (not per-survey) follow-up activity. Sister tab to
  Multi-survey Comparison and Follow-up Timing, but pivoting on
  individual MPC site code rather than survey group.
- World map (Plotly Scattergeo) of all ~2,675 MPC obscodes with
  valid lat/lon, colored by follow-up volume on a Viridis (or
  user-selected) colormap. Selectable map projection (8 options;
  default equirectangular for precise viewport bbox); log/linear
  color scale; site-type filter (default Optical, ~99% of codes);
  NEO-active filter (default On — restricts to ~500 sites that
  have ever observed a NEO in a discovery apparition).
- Map gestures: trackpad pinch / scroll wheel zooms, click-drag
  pans, double-click resets — Scattergeo does not support
  drag-rectangle zoom, so a small caption under the map states
  the working gestures. `scrollZoom: True` is set per-graph (the
  cartesian plots elsewhere keep the global default).
- Stats card responsive to map pan/zoom: tallies of sites in
  viewport, NEOs in window, NEOs with follow-up there, median
  follow-up sites per NEO. Bbox derivation is exact for
  equirectangular/mercator/miller (axis ranges); approximate for
  others (center + scale).
- Bar chart with multi-select (typed or pasted as a list), top-N
  selector (default 10), and colors matched to the map's colormap
  and domain.
- Follow-up window selector: 1 d / 1 wk / 1 lunation / 100 d /
  200 d (capped by the apparition cache's ±200 d window).
  Post-discovery vs include-precoveries radio.
- **Metric radio** (Phase 2A, 2026-05-09): NEOs (default) /
  Tracklets / Observations. Drives the map colorbar, hover, bar
  values, and stats card uniformly. Tracklets and observations
  come from 28 pre-aggregated FILTER columns added to
  APPARITION_SQL — `n_trk_post_W` / `n_trk_any_W` / `n_obs_post_W`
  / `n_obs_any_W` for W in {1, 7, 29, 50, 100, 150, 200} (the
  union of FUC's and Multi-survey's window selectors). Continuous
  windows would require a per-tracklet cache; the pre-agg approach
  was chosen because the discrete dropdowns are stable.
- **Time scope radio** (Phase 2B, 2026-05-10): Discovery
  apparition (default — uses `apparition_cache`) / All time / Recovery
  only. The latter two use a new `lifetime_cache` built from
  LIFETIME_FOLLOWUP_SQL (same CTE chain, no ±200 d bound, ~503 K
  rows, ~11 MB parquet, ~10 min on Gizmo). Recovery-only filters
  to (NEO × station) rows where `last_obs > disc + 200 d`; for
  tracklets/obs it subtracts the apparition's `n_trk_any_200` /
  `n_obs_any_200` so the result is strictly recovery activity.
  Window + Precovery controls disable when scope ≠ apparition.
- **Depth filter** (Phase 3A, 2026-05-10): per-station V-corrected
  mag distribution from obs_sbn_neo (most recent 5 years if site
  has ≥ 1000 NEO obs in that window, else all-time fallback;
  stations with < 50 valid obs excluded). Three statistics
  exposed via dropdown: Median + 1.4826·MAD (default, robust),
  Mean + 1σ, 95th percentile. Double-ended range slider on V
  (14.0–24.0) filters sites whose chosen statistic falls inside.
  Sites without published depth data are kept by default
  ("unknown" ≠ "shallow"). Cache: `site_mag_stats` parquet,
  ~2 K rows, sub-MB.
- Data: live obscodes table + `apparition_cache`. New 1-day
  parquet caches `obscodes_cache`, `site_mag_stats`.
- See `docs/2026-05-09_followup_comparison_scoping.md`.

### Tab 6: Follow-up Timing
- Response curve (CDF): fraction of NEOs observed by 1st/2nd/3rd
  follow-up survey within N days of discovery
- Box plots of follow-up time by survey (excludes discoverer's own
  survey project — only cross-survey follow-up counted)
- Follow-up network heatmap: discoverer -> first follow-up survey
- Median follow-up time trend by discovery year with IQR band

### Tab 7: Discovery Circumstances
- Sky map (RA/Dec scatter) of discovery positions with ecliptic and
  galactic plane overlays; WebGL for ~40K points
- Apparent V magnitude histogram (band-corrected) at discovery
- Rate of motion vs. absolute magnitude H scatter (log y-scale)
- Position angle rose diagram (15° bins, 0=N/90=E convention)
- Controls: year range, size class filter, color by (survey/size/year)
- Data: `tracklet_obs_all` and `discovery_tracklet_stats` CTEs added
  to `LOAD_SQL`; same ~44K rows, 6 new columns

### Tab 8: Observation history
- Default object on first load is **Apophis (99942)**.  Default class
  filter is "All NEOs" — Atira / Aten / Apollo / Near Amor / Distant
  Amor, the canonical NEO group.  The Classes dropdown carries an
  "All NEOs" virtual option at the top that expands to those five
  on selection.
- Three stacked panels:
  1. **Class-filtered catalog** of mpc_orbits objects, paired with a
     per-object **V-vs-time plot** of band-corrected magnitudes over
     the full obs_sbn record.  Site-code lifeline below; vertical
     shading marks solar elongation > 90° (observable) vs. ≤ 90°.
  2. **Finding chart** (sky map) — see next section.
- Designation entry (Enter to submit) resolves permid (`99942`),
  provid (`2019 UZ173`), iau_name (`Pluto`), and packed forms
  (`K24Y04R` → `lib/mpc_convert.unpack_designation`).  On submit,
  switches Classes to the resolved object's orbit class, clears
  other filters, and pins the row to the top of the table.  A
  duplicate Designation + Random-object button sits next to the
  Finding-chart projection picker so the user doesn't have to
  scroll back up to switch object while studying the sky map.
- "Collapse to selected row" checkbox above the table contracts
  the catalog to the displayed object's single row, keeping the
  finding chart visually anchored to its data.
- Plot controls (Reset axes / Show all bands / Toggle elongation
  shading / V-range slider) are html.Buttons + dcc.RangeSlider
  below the dcc.Graph — they pick up the page's theme CSS on
  hover.
- Details panel above the V-vs-time plot: Class / H / q / Q / e /
  i / a / U / Nopp / n_obs / arc / disc-by chips + JPL SBDB · MPC
  Explorer · NEOfixer (NEOs only) link buttons.
- Pin tracks the currently-displayed object across arbitrary
  filter changes — selecting a row, pressing Random, or typing
  another designation moves the pin.  With the 5000-row H-sort
  cap on classes >5K (any MBA fine class), this is how an object
  like Lewseaman (H 17.0, IMB H-rank 77,744) stays in the table
  while it's plotted.
- Data: `boxscore_cache` (same source as Asteroid Classes), joined
  at load time with `obs_summary_all_cache` for the authoritative
  first_obs / last_obs / arc / nobs / disc_by columns.

#### Finding chart (sky-plot section under the obshist table)
- Per-object sky-plot of the observed (RA, Dec) trail, with optional
  Horizons-predicted track overlay.  Lives in `lib/finding_chart.py`
  (~500 lines) plus the Horizons client in `lib/horizons.py`
  (~140 lines).  Drawn as a Plotly cartesian scatter — server-side
  projection math, plain pan/zoom, no scattergeo.
- **Projections:** Hammer (default), Aitoff, Mollweide, Rectangular.
  East-on-left convention (NEOlyzer-style); `_center_lon` negates the
  centered longitude.  Center RA in **hours** (default 0 h, step
  0.25 h = 15 min, range −12 to +12; double-click resets to 0 via
  `assets/finding_chart.js`).  Whole-sky boundary is drawn at moderate
  weight (ellipse for the equal-area three; rectangle for
  Rectangular).
- **Static reference data**: `data/finding_chart/bright_stars.csv`
  (~160 KB Hipparcos V<6, vendored from NEOlyzer/data) and
  `data/finding_chart/iau_boundaries_j2000.csv` (~85 KB IAU
  constellation boundaries).  Loaded once per process.
- **Overlays** (Checklist): Stars · Constellations · Grid
  (RA/Dec graticule) · Ecliptic · Galactic plane · Ecliptic poles ·
  Galactic poles · Predictions · Prediction labels · Hide
  non-observable · Hide historical.  Defaults: Grid, Ecliptic,
  Galactic plane, Prediction labels on.  Ecliptic / galactic plane
  are dashed lines at width 1.8 in the matching pole color.  Pole
  markers are plus signs (Plotly `symbol="cross"`) at the canonical
  J2000 positions.
- **NSEW badges** at the projection's whole-sky extent (0.97 N/S,
  0.98 E/W) — small circles overlaying the map.  E on the left.
- **Colormap dropdown** (Viridis default) — drives the
  viridis-by-year markers for historical observations.
- **Predictions** via the JPL Horizons web API (`lib/horizons.py`,
  endpoint `https://ssd.jpl.nasa.gov/api/horizons.api`).  Forecast
  window dropdown: 1 / 5 / 10 / 20 years.  Horizons step auto-widens
  (1 y/1 d, 5 y/7 d, 10 y/14 d, 20 y/30 d) so responses stay small.
  On-demand fetch when the Predictions toggle is on; disk-cached
  per `(designation, t_start, t_stop, step, observer)` under
  `app/.horizons_cache/<hash>.parquet` with a 1-week TTL.  Cold
  fetch ~400 ms, cache hit ~30 ms.  Outbound is rate-limited to
  2 req/s and a failure (Horizons down, designation not resolved)
  starts a 120 s cooldown so re-renders don't re-hit it; failures
  degrade quietly to the observed-only chart with a status-line note.
- **Predicted-marker treatment**: year 0 (next 12 months) in solid
  orange `circle-open`; years 1+ in a Turbo gradient by year offset
  so each future year reads as a distinct color.  Dates with
  solar elongation < `Min elongation` slider (default 60°) OR
  Horizons V outside the `Horizons V-mag range` slider gray out as
  `rgba(150,150,150,0.55)` open circles.  "Hide non-observable"
  drops every gray marker entirely.  No connecting line through
  the markers (it hid the gray ones).
- **V-mag range** is a `dcc.RangeSlider` whose min/max snap to the
  object's predicted V range (rounded to 0.1 mag) on object change
  or Predictions toggle-on.  Slider geometry tracked via the
  `fc-slider-state` Store so projection switches / overlay toggles
  don't reset the user's narrowed range.
- **Prediction labels** annotate the first and last observable date
  *per year* (so a 5-year forecast can show up to 10 date labels).
  Labels shift with the slider — narrowing the V range or raising
  the elongation cut moves them inward.
- **`uirevision`** keyed on `(permid, provid, projection, center_ra)`
  so overlay toggles, slider drags, hide-historical, etc. preserve
  the user's zoom/pan.  Switching object, projection, or center
  resets the viewport.  Axis ranges locked to 1.05× the projection's
  extent so toggling traces never auto-refits the view.
- **Drag-rectangle zoom** is the default `dragmode`; modebar Pan
  swaps to drag-pan; double-click resets.  `scrollZoom` is off so
  trackpad scrolling the page works normally over the chart.
- **`dcc.Loading`** with `delay_show=400` so the spinner only paints
  for genuinely slow callbacks (cold Horizons fetch); slider drags
  no longer blink.

### Tab 9: Asteroid Classes
- Cross-tabulation of the full `mpc_orbits` catalog (~1.5M objects,
  all classes — not just NEOs) by orbit type and selected attributes.
- Class grouping: Fine (21), Standard (17), Coarse (7) MPC orbit
  type bins.
- Filters: NEO-only, PHA-only, retrograde-only, and an H-magnitude
  range slider (5–32).
- Charts: H distribution histogram and a–e (semi-major axis vs.
  eccentricity) scatter, both rendered with the active filter set.
- Per-tab CSV download.
- Data: `boxscore_cache` (`BOXSCORE_SQL` — full mpc_orbits + numbered
  identifications join). Same ~1.5M rows that drive boxscore-class
  callbacks elsewhere.

### Tab 10: Tools
- Standalone calculators and converters for planetary-defense work.
  No data dependencies; all pure Python computation via `lib/`.
- Currently 10 cards:
  - Pack Designation, Unpack Designation, Validate Designation
    (`lib/mpc_convert.py`)
  - H Magnitude ↔ Diameter
  - Tisserand Parameter, Orbit Classification
    (`lib/orbit_classes.py`)
  - Parse obs80 Line (`lib/mpc_convert.py`)
  - Date Converter, CLN ↔ UTC, Airmass ↔ Altitude
- Inputs are debounced; outputs render in the same card. Useful as
  outreach utilities and as a sanity-check surface for the same
  conversion primitives the SQL `css_utilities` schema exposes
  server-side.

### Tab 11: Station Report (dev only)
- Per-site deep-dive — site code + optional date range yields a
  summary line, year × class breakdown for NEOs (Atira / Aten /
  Apollo / Amor) and non-NEOs, and an MPEC-publications stub
  (Phase 2, ADS-backed). Phase 1 lives at `lib/station_report.py`
  + `sql/station_report.sql`. NEO/non-NEO split is taken from the
  `obs_sbn_neo` matview (q ≤ 1.3 with no e bound; resolves
  designations through `current_identifications`/`numbered_
  identifications`).
- Currently paused pending Phase 2 ADS integration. Q7-style
  per-site forensic stats from the Follow-up Comparison scoping
  doc are intended to land here as context for the literature
  search.

### Tab 12: About
- Static project page: short description, GitHub repo link, contact
  email (`contact@hotwireduniverse.org` via Cloudflare Email Routing),
  maintainer line. Release notes card + FAQ (data freshness, NEO
  definition, six-source rationale, orbit-class derivation, map
  projections, mobile, contact). No state, no callbacks.

### Survey Groupings
Stations are mapped to project groups via `STATION_TO_PROJECT`:
- **Catalina Survey** (703, E12, G96) — core CSS telescopes
- **Catalina Follow-up** (I52, V06, G84) — CSS follow-up telescopes
- **Pan-STARRS** (F51, F52)
- **ATLAS** (T05, T07, T08, T03, M22, W68, R17)
- **Bok NEO Survey** (V00)
- **Rubin/LSST** (X05)
- Also: LINEAR, NEAT, Spacewatch, LONEOS, NEOWISE, Other-US, Others

### Shared Banner Controls
- CSS logo (linked to catalina.lpl.arizona.edu) at upper left
- NEO sources (filter by membership in MPC / mpc_orbits / CNEOS /
  NEOCC / NEOfixer / Lowell / all-six / disagreements / any),
  Group by, Plot height, Theme toggle (Light/Dark)
- "NEO sources" hides on tabs whose plots don't slice by membership
  (MPEC, Asteroid Classes, Tools, Consensus, About). "Group by"
  hides when the active context overrides it (e.g. size-filter=split
  on Discoveries, color-by≠survey on Circumstances).
- Reset buttons: "Tab" (resets current tab), "All" (resets all tabs)
- Per-tab "Download CSV" buttons export currently filtered data

### Architecture
- **Finding-chart predictions** add an on-demand per-object
  `app/.horizons_cache/<hash>.parquet` pool — 1-week TTL, keyed on
  designation × window × step × observer.  Hand-rolled requests
  client in `lib/horizons.py`; no astroquery dependency.
- **Seven SQL queries** cached to Parquet (1-day auto-invalidation,
  falls back to legacy CSV if Parquet not yet generated). Scan sources
  and timings differ between hosts; numbers below are DB-only wall
  clocks measured 2026-04-24:
  - `LOAD_SQL` — discovery data + tracklet circumstances (~43K NEOs).
    Scans `obs_sbn_neo` (matview) on Gizmo: **~0.4 s**. Raw `obs_sbn`
    on Sibyl: ~1 min.
  - `APPARITION_SQL` — station-level observations within +/-200 days
    of discovery (~373K station rows). Scans `obs_sbn_neo` on Gizmo:
    **~4:40**. Raw `obs_sbn` on Sibyl: ~55 s. (LATERAL probes don't
    fully fit in Gizmo's 16 GB even after the matview shrink — Sibyl's
    251 GB RAM still wins for this shape.) Phase 2A (2026-05-09)
    extended this with 28 pre-aggregated FILTER columns
    (`n_trk_{post,any}_W`, `n_obs_{post,any}_W` for 7 windows),
    bumping cache parquet from ~19 MB to ~21 MB and the SQL hash
    from `031b17ad` to `811ddeb6`. Query time unchanged — the
    FILTER aggregations run on rows already in the LATERAL.
  - `LIFETIME_FOLLOWUP_SQL` — per (NEO × station × all-time)
    with first/last obstime + tracklet/obs totals (~503 K rows,
    ~11 MB parquet). Phase 2B addition (2026-05-10) for the FUC
    Time scope radio. Same CTE chain as APPARITION_SQL but the
    LATERAL has no ±200 d bound. Gizmo first run ~10 min;
    subsequent loads ~few s from parquet.
  - `SITE_MAG_STATS_SQL` — per-station V-mag depth distribution
    (mean+σ, median+1.4826·MAD, 95th pct) from obs_sbn_neo,
    5-year window with all-time fallback. Phase 3A
    (2026-05-10). ~2 K rows, sub-MB parquet, query <1 min.
  - `BOXSCORE_SQL` — full mpc_orbits + numbered_identifications JOIN
    (~1.5M rows, all object classes). Doesn't touch obs_sbn. Gizmo
    NVMe: **~0.7 s**. Sibyl: **~3 s**. (CLAUDE.md prior to 2026-04-24
    quoted "~13 min" for Sibyl — that was either a cold-cache reading
    or wall-clock for the full Python cache-rebuild including the
    SBDB MOID API call; the DB query itself is seconds.)  At load
    time we LEFT JOIN the boxscore in-memory with the next entry
    (`obs_summary_all_cache`) to surface authoritative obs aggregates.
  - `OBS_SUMMARY_ALL_SQL` — full-catalog sibling to
    `css_neo_consensus.obs_summary`.  `SELECT primary_desig,
    first_obs, last_obs, arc_days, nobs, disc_by FROM
    public.obs_summary_all` (~1.6M rows, ~38 MB parquet, hash
    `065fdeb7`).  The matview itself is built by
    `sql/obs_summary_all.sql` and refreshed nightly by stage 3b
    of `refresh_matview_gizmo.sh` (~2:30 on Gizmo NVMe via parallel
    seq scan + hash aggregate; Sibyl HDD couldn't finish in 10 min
    — see 2026-05-16 benchmark).
- **NEA.txt H magnitude override** (`lib/nea_catalog.py`): downloads
  the MPC's curated NEA catalog, resolves designations via
  `numbered_identifications` and `mpc_designation`, and overrides
  `mpc_orbits.h` where NEA.txt provides a reliable value.  Cached
  as `.nea_h_cache.csv` with same 1-day invalidation.  Removable
  when MPC completes mpc_orbits cleanup.
- Both caches load at startup; `--refresh` forces re-query
- Theming via CSS custom properties set on `#page-container`
- `SIZE_COLORS` (viridis) for size-class stacking
- `PROJECT_COLORS` match CNEOS site_all.json (with additions)
- Max 3 surveys enforced for Venn via server-side callback

### Running
```bash
source venv/bin/activate
python app/discovery_stats.py        # default: http://127.0.0.1:8050/
python app/discovery_stats.py --refresh  # force re-query from DB
```

### Production Deployment
Public surface at `hotwireduniverse.org` is served from a Mac mini
(Gizmo) replica via a Cloudflare named tunnel. Dash itself runs
under launchd (`com.rlseaman.dashboard`, port 8050) behind a
waitress WSGI server. A daily launchd agent
(`org.seaman.gizmo-refresh`, 06:00 MST) runs seven stages:
  1. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo`
  2. NEO consensus refresh (six sources, best-effort)
  3. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_summary`
     (NEO-scoped, drives the NEO Consensus tab).
  3b. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_summary_all`
     (full mpc_orbits catalog, drives the Observation history tab;
     added 2026-05-16).
  4. `python app/discovery_stats.py --refresh-only` to rebuild
     parquet caches against today's matview state
  4a. Sweep orphan parquet/.meta files from prior SQL-hash bumps
     (so `_cache_refresh_label()`'s `min(mtime)` over the cache glob
     doesn't back-date the "Caches refreshed …" subtext).
  5. `launchctl kickstart -k` on the Dash plist so the running
     process picks up the fresh caches (~5 s of 502s while the
     port rebinds; acceptable for a low-traffic outreach window).
  6. `scripts/apireq_summary.sh` — tally yesterday's outbound HTTP
     volume by host / outcome from the just-rotated dashboard log
     into `~/Claude/mpc_sbn/logs/apireq_summary_YYYYMMDD.txt`. Best-
     effort; no alerts in week 1 (alert block commented in the script,
     enable after a baseline). See `docs/dashboard_security.md` →
     "Cloudflare protection refinements" #5.
Total elapsed ~16–19 min in normal operation. See `docs/disaster_recovery.md`
for what to do if a stage fails.

### Dev surface
A second Dash instance runs alongside prod for staging in-flight
work. Served from `dev.hotwireduniverse.org` via the same
Cloudflare tunnel, gated by a Cloudflare Access email allow-list.
launchd label `com.rlseaman.dashboard-rnd`, port 8051, run with
`--rnd --dev-tabs`. `--rnd` is now also on prod (it's how NEO
Consensus shipped); `--dev-tabs` is the new gate (2026-05-10)
for tabs that aren't ready for prod, currently just Station
Report. The
plist's WorkingDirectory points at the git worktree
`~/CSS_MPC_toolkit_dev` (currently on `station-report`); parquet
caches are symlinked from the primary checkout so dev sees the
nightly refresh's output without re-querying. To deploy a
station-report change: push to origin, `git pull` in the
worktree, `launchctl kickstart -k gui/$(id -u)/com.rlseaman.
dashboard-rnd`. Logs at
`~/Claude/mpc_sbn/logs/dashboard-rnd_<timestamp>.log`.

## Development Conventions

- **Python env:** `venv/`, pinned in `requirements.txt`
- **Strip notebook outputs before committing** — use
  `jupyter nbconvert --clear-output` or `nbstripout` before `git add`
- **Never use `SELECT *`** — explicit column lists always
- **Readonly database access** — all queries go through `lib/db.py`
  context manager
- **COALESCE expressions** derive missing Keplerian elements from
  cometary (q,e,i) — see `lib/orbits.py`

## Key Terminology

- **NEO:** Near-Earth Object (q <= 1.3 AU)
- **H magnitude:** absolute magnitude (proxy for size; lower = bigger)
- **NEOMOD3:** Debiased population model (Nesvorny et al. 2024)
- **ADES:** Astrometric Data Exchange Standard (IAU observation format)
- **obs80:** Legacy MPC 80-column observation format
- **permid:** Permanent MPC number; **provid:** Provisional designation
- **trkid:** Tracklet identifier grouping same-night observations
- **disc = '*':** Discovery observation flag in obs_sbn
