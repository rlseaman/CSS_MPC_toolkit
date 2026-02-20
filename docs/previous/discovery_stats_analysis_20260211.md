# Discovery Stats App — Analysis Notes (2026-02-11)

## H-Magnitude ↔ Diameter Mapping

The relationship between absolute magnitude H and diameter D (in km) is:

    D = 1329 / sqrt(p_v) * 10^(-H/5)

or equivalently:

    H = 5 * log10(1329 / (D_km * sqrt(p_v)))

### Standard Mapping (p_v = 0.14, Harris & Chodas 2021)

Effective diameter constant: 1329/sqrt(0.14) = 3551.8 km

| Diameter | H magnitude | Derivation |
|----------|-------------|------------|
| 2 km     | 16.25       | 5*log10(3551.8/2) |
| 1 km     | 17.75       | 5*log10(3551.8/1) |
| 500 m    | 19.25       | 5*log10(3551.8/0.5) |
| 250 m    | 20.75       | 5*log10(3551.8/0.25) |
| 140 m    | 22.0        | 5*log10(3551.8/0.14) |
| 100 m    | 22.75       | 5*log10(3551.8/0.1) |
| 50 m     | 24.25       | 5*log10(3551.8/0.05) |
| 20 m     | 26.25       | 5*log10(3551.8/0.02) |
| 10 m     | 27.75       | 5*log10(3551.8/0.01) |

### NEOMOD3 Mapping (Nesvorny et al. 2024, arXiv:2404.18805)

NEOMOD3 uses size-dependent debiased geometric albedos:
- p_v,ref ~ 0.15 for H < 18 (large NEOs)
- p_v,ref ~ 0.16 for 18 < H < 22 (medium NEOs)
- p_v,ref ~ 0.18 for H > 22 (small NEOs)

Effective diameter constants:
- 1329/sqrt(0.15) = 3431.6 km (H < 18)
- 1329/sqrt(0.16) = 3322.5 km (18 < H < 22)
- 1329/sqrt(0.18) = 3132.0 km (H > 22)

| Diameter | H magnitude | Albedo used | Derivation |
|----------|-------------|-------------|------------|
| 2 km     | 16.2        | 0.15        | 5*log10(3431.6/2) |
| 1 km     | 17.7        | 0.15        | 5*log10(3431.6/1) |
| 500 m    | 19.1        | 0.16        | 5*log10(3322.5/0.5) |
| 250 m    | 20.6        | 0.16        | 5*log10(3322.5/0.25) |
| 140 m    | 21.9        | 0.16        | 5*log10(3322.5/0.14) |
| 100 m    | 22.5        | 0.18        | 5*log10(3132.0/0.1) |
| 50 m     | 24.0        | 0.18        | 5*log10(3132.0/0.05) |
| 20 m     | 26.0        | 0.18        | 5*log10(3132.0/0.02) |
| 10 m     | 27.5        | 0.18        | 5*log10(3132.0/0.01) |

Note: the 500 m boundary (H ~ 19) falls in the p_v = 0.16 regime. The albedo
step at H = 18 means the 1 km → 500 m transition crosses an albedo boundary,
producing a slightly different H spacing (~1.4 mag) than the standard mapping
(~1.5 mag, which is the constant-albedo value of 5*log10(2) = 1.505).


## Completeness Point Placement: Bin Center vs Right Edge

### The Issue

NEOMOD2 Table 3 provides half-magnitude bins with columns:
- `dN`: number of NEOs in the bin [H1, H2)
- `N_cumul` = N(H < H2): cumulative count up to the **right edge** of the bin
- `N_min`, `N_max`: 1-sigma bounds on the cumulative count

The completeness curve was originally plotted at bin centers (e.g., H = 22.0
for the 21.75–22.25 bin). But both the model and discovered counts used in
the ratio are evaluated at the right bin edge.

### Analysis

**Cumulative mode:**
- Model denominator: `N_cumul` = N(H < H2) — evaluated at H2
- Discovered numerator: `(h_vals < row["h2"]).sum()` — also evaluated at H2
- The completeness ratio `disc(H < H2) / model(H < H2)` is defined at H2
- **Points belong at H2 (the right bin edge)**

Example: the bin 21.75–22.25 has N_cumul = 24,900 = N(H < 22.25).
We count discovered NEOs with H < 22.25. The resulting completeness
percentage applies at H = 22.25, not at the bin center H = 22.0.

**Differential mode:**
- Model: `dN` covers the full bin [H1, H2)
- Discovered: count of NEOs in that bin
- The bin center is the natural representative x-position
- **Points stay at bin centers**

### Consequence

In cumulative mode, all completeness points shift 0.25 mag to the right.
This has a practical benefit: the points now align more naturally with the
vertical size reference lines (which mark specific H values, not bin centers).

The 140m completeness annotation uses linear interpolation of the NEOMOD2
cumulative model between bin edges, so it is independent of this choice and
remains at the exact H value for 140m.


## 140m Completeness Interpolation

To estimate completeness at an arbitrary H value (e.g., H = 22.0 for 140m
with standard mapping), we linearly interpolate the NEOMOD2 cumulative model:

For H = 22.0, which falls in the bin [21.75, 22.25]:
- N(H < 21.75) = 18,100 (previous bin's N_cumul)
- N(H < 22.25) = 24,900 (this bin's N_cumul)
- frac = (22.0 - 21.75) / (22.25 - 21.75) = 0.5
- N(H < 22.0) ≈ 18,100 + 0.5 * (24,900 - 18,100) = 21,500

For NEOMOD3's H = 21.9:
- frac = (21.9 - 21.75) / (22.25 - 21.75) = 0.3
- N(H < 21.9) ≈ 18,100 + 0.3 * 6,800 = 20,140

The discovered count is exact (count of all NEOs with H < threshold from
the database query), so only the model denominator requires interpolation.

This assumes uniform distribution within the bin, which is a simplification —
the actual H distribution steepens with H — but is reasonable for a 0.5-mag
bin.


## Dash Debug Mode and Double Data Loading

### Problem

With `app.run(debug=True)`, Werkzeug's reloader spawns two processes:
1. **Watcher process** (parent): monitors files for changes, does not serve
2. **Server process** (child): serves HTTP requests, has `WERKZEUG_RUN_MAIN=true`

Both processes import the module and execute `df = load_data()` at module
level. On first run (no cache), the watcher queries the database (~30s),
writes the cache, then spawns the server process which finds the fresh cache.
Result: one DB query + one cache load — two visible "loading" messages.

With `--refresh`, the previous fix (removing the flag from `sys.argv`) may
not fully prevent the reloader from passing it to the child, because Werkzeug
captures `sys.argv` for subprocess spawning. If both processes see `--refresh`,
the database is queried twice.

### Solution

`app.run(debug=True, use_reloader=False)` keeps the Dash debug toolbar but
disables the file-watching subprocess entirely. Only one process runs, so
`load_data()` executes exactly once. The tradeoff is that code changes
require a manual server restart.

Alternative approaches considered:
- Checking `WERKZEUG_RUN_MAIN` env var at import time — fragile, can't
  distinguish "no reloader" from "watcher process" without knowing debug mode
- Lazy loading via `_ensure_loaded()` in each callback — cleaner but requires
  refactoring all callbacks and using placeholder defaults for the layout
- `dcc.Store` with a loading callback — most Dash-idiomatic but a larger refactor


## UI/Layout Fixes

### Timestamp annotation clipping
The "MPC data queried ..." annotation at the bottom of the H-distribution
chart was positioned at `x=0` (paper coordinates), causing it to extend
beyond the left edge of the plot area in some viewport sizes. Shifted to
`x=0.02`.

### Completeness label overlap with error bars
Labels on the red completeness curve were at `textposition="top center"`,
placing them directly above the markers where they overlapped with the
upward error bars. Changed to `"middle right"` to shift labels rightward.

### Secondary y-axis cleanup
The secondary y-axis (completeness %) had its own title, tick labels, and
grid lines, creating a confusing dual-grid overlay and redundant labeling
(since the completeness points can be individually labeled via checkbox).
Removed: `showticklabels=False`, `title_text=""`, `showgrid=False`.

### Annotation preservation
The timestamp annotation was originally set via `update_layout(annotations=[...])`
which **replaces** all existing annotations — including those added by
`add_vline()` and the 140m completeness annotation. Changed to use
`fig.add_annotation()` which appends to the existing list.
