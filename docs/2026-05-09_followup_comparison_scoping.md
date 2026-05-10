# Follow-up Comparison Tab — Scoping Assessment

**Status:** Scoping + Phase 1 implementation, 2026-05-09.
**Motivation:** Cross-site comparison of follow-up activity. The
existing **Multi-survey Comparison** tab compares survey *groups*
(CSS, Pan-STARRS, ATLAS, …) within ±200 days of discovery; the
existing **Follow-up Timing** tab measures cross-survey response
latency. Neither resolves to the per-site level, and neither covers
multi-apparition recovery work — the bread-and-butter of dedicated
follow-up sites like H01, H21, J95, V06.
**Related:**
[`source_tables.md`](source_tables.md) §`obscodes` and §`obs_sbn.prog`;
[`station_discovery_audit.md`](station_discovery_audit.md);
in-flight `station-report` branch (per-site Station Report tab,
currently paused at Phase 1).

## Use case

Make per-site follow-up activity inspectable and comparable:

- "Which sites contributed the most NEO follow-up tracklets in 2025?"
- "Where on Earth are our follow-up assets — and what's the
  geographic gap?"
- "How does H01's target list differ from J95's?"
- "Show all follow-up tracklets from Australian sites."

These are site-axis questions. They span apparitions (a follow-up
at a future apparition still counts) and they spill beyond optical
astrometry (occultation, satellite, radar are all follow-up).

## Database investigation

### Q5 — program codes (`obs_sbn.prog`)

Column exists. Sampling **April 2026** at the sites of operational
interest:

| stn | rows  | with prog | distinct prog | values seen |
|-----|-------|-----------|---------------|-------------|
| G96 | 593K  | 100%      | 2             | (two flavors) |
| I52 |  4.0K | 100%      | 1             | `01` |
| V06 |   983 | 100%      | 1             | `01` |
| 291 |   189 | 100%      | 1             | `00` |
| 695 |    48 | 100%      | 1             | `0j` |
| J95 |   313 | 100%      | 1             | `00` |
| H01 |   409 | **0%**    | 0             | — |
| H21 |   785 | **0%**    | 0             | — |

**Decision: hold.** `prog` is populated for major surveys but with
near-zero diversity, and not populated at all for several
follow-up sites that need disambiguation least. For the
multi-observer case at 695/807 (Q6) `prog` would be exactly the
right tool — but coverage today does not support it. Not worth
building anything load-bearing on it. Revisit if the MPC
backfills or if program-code reporting becomes a community norm.

### Q6 — multi-telescope sites

Confirmed from `obscodes`. Co-located codes within centimeters of
each other on the same mountain:

- **Kitt Peak:** 291 (LPL/Spacewatch II, `0.84947 / 0.52647`),
  695 (Kitt Peak generic, `0.84950 / 0.52643`), and several
  others. 695 is the catch-all for any Kitt Peak instrument
  without its own assigned code.
- **Cerro Tololo:** 807 plays the same role.

Without `prog` we cannot resolve which telescope at 695 produced
a given observation. **For Phase 1 we surface co-location on the
map** (cluster pins or jittered dots) but do not attempt
telescope-level resolution. Geographic grouping ("all 695-class
multi-tenant sites") is the practical handle.

### Q1 — world map data

`public.obscodes` has **2,697 rows**, **2,675 with longitude +
rhocosphi/rhosinphi**, all with `observations_type`:

| observations_type | count |
|-------------------|-------|
| optical           | 2,656 |
| satellite         |    22 |
| radar             |    15 |
| occultation       |     2 |
| roving            |     2 |

Latitude is recoverable from rhosinphi (geocentric latitude ≈
`asin(rhosinphi / sqrt(rhocosphi² + rhosinphi²))`) — accurate
enough for marker placement on a world map.

`obscodes.observations_type` directly answers the "follow-up is
broader than astrometry" point — we can color or facet by type.

### Q7 — site forensics — folded into Station Report

Per-site magnitude completeness, astrometric residuals,
star-catalog usage (`astcat`), tracklet length, time-of-night
cadence, target-list bias (NEO/MBA/comet) all belong inside a
single-site context — the Station Report tab on `station-report`.
**Decision:** when Station Report resumes, it absorbs Q7 as
context for the literature-search and per-site-stats sections
already planned for Phase 2 of that work. Follow-up Comparison
links *out* to Station Report on click; it does not duplicate the
forensic depth.

## Naming and scope decisions

- **Tab name: "Follow-up Comparison"** (not "Follow-up Sites").
  The verb "compare" signals the contrast with Follow-up Timing
  (latency) and Multi-survey Comparison (group-level Venn).
- **Position:** between Multi-survey Comparison (tab 4) and
  Follow-up Timing (tab 5).
- **Future feature — follow-up groups.** Some operational
  follow-up is a *network*, not a site:
  - **LCO** (Las Cumbres Observatory) — many co-located and
    distributed telescopes under one mission.
  - **ARO** (Astronomical Research Observatory) and its
    affiliates — H21, H45, others, sometimes co-located,
    sometimes not.
  Phase 1 keeps the axis as raw site code. Phase 2+ adds a
  user-defined-or-curated "follow-up group" overlay — a
  many-to-one site→group mapping that lets a user say "treat
  these eight sites as one entity for the bar chart and Venn."
  Deferred — not in the Phase 1 surface.

## Phase 1 — what lands today

1. **Stub tab** between Multi-survey and Follow-up Timing,
   `value="tab-followup-compare"`.
2. **World map** (Plotly Scattergeo, equirectangular default)
   of all `obscodes` sites with valid lat/lon, color-coded by
   `observations_type`. Hover: site code + name + recent obs
   count. Filters on the map: site type, minimum follow-up
   tracklet count in window.
3. **Bar chart** of follow-up tracklets per site over a
   year-range slider. Multi-select on site code (default: top
   20 by follow-up volume). "Follow-up tracklet" in Phase 1 =
   any tracklet at site X for an object whose discovery
   tracklet is at a different site, **within the discovery
   apparition** (reuses the existing `tracklet_obs_all` data —
   no new heavy queries against raw `obs_sbn`).
4. **astro_map_plot reference.** The library
   (https://github.com/rlseaman/astro_map_plot, MIT) uses
   Cartopy/Matplotlib for static publication maps and is not
   directly importable into a Dash interactive context. We
   borrow its conceptual approach to MPC obscode parsing
   (`observatories.py`) — the geocentric-rho → lat/lon math and
   the convention of treating obscodes as a first-class catalog.
   No code copied; we have the obscodes table directly.

## Phase 2+ — backlog

- Pairwise overlap / Venn at site level, with **configurable**
  time window (default "all post-discovery", to cover
  multi-apparition recovery — the part Multi-survey Comparison
  intentionally doesn't).
- Per-continent zoom / popup. Likely cleaner as map-projection
  presets ("Europe", "Australasia", …) than literal popups.
- Follow-up group overlay (LCO, ARO, …).
- Heavier per-site forensic stats — lives in Station Report,
  not here.

## Out of scope for this assessment

- Anything touching `prog` beyond surfacing it where it has
  diversity (G96).
- Reworking the `tracklet_obs_all` CTE to span multiple
  apparitions. That's a Phase 2 query-layer concern.
- Mobile reflow (see [mobile backlog memory](https://...) — map
  + bar combos do not survive 360-px viewports).
