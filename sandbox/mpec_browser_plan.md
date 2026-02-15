# MPEC Browser — Implementation Plan

Saved: 2026-02-15

## Completed (Phase 0 + Phase 1)

### Phase 0: Auto-select & auto-update
- `mpec-auto-mode` Store tracks "follow latest" vs "pinned" state
- `refresh_mpec_list` auto-selects first discovery MPEC on load/refresh
- Manual click sets pinned mode; "Follow latest" button re-enables
- Green "Following latest" / grey "Pinned" indicator above list

### Phase 1: Enrichment & Data Center Status
- **`lib/api_clients.py`** — API wrappers with 5-min TTL cache:
  - JPL SBDB (orbit class, elements, close approaches)
  - JPL Sentry (impact risk: Torino, Palermo, IP)
  - NEOfixer orbit (Find_Orb elements, MOIDs, H, U, RMS)
  - NEOfixer targets & ephemeris (for Phase 2)
  - ESA NEOCC risk & physical properties
- **Enrichment polling** — 60-second interval, max 10 polls
  - Fetches all APIs on MPEC selection
  - Re-checks sources that returned None (data center lag)
  - Stops when all respond or 10 min elapsed
- **Data Center Status card** in detail panel:
  - Orbit summary (class, a, e, i, H) from best source
  - MOID, condition code, arc length, obs count
  - Source status indicators (checkmark/hourglass/dash)
  - Close approaches (top 5)
  - Sentry impact risk assessment
  - NEOCC risk status
  - External links: MPECWatch, CNEOS, NEOCC, Horizons

### Additional improvements
- Banner renamed: "Planetary Defense Dashboard"
- Browser tab title updated
- MPECWatch link corrected to sbnmpc.astro.umd.edu
- Observations: first-line indent fixed (strip newlines only)
- Observations: tracklet color-coding with alternating backgrounds
- Observations: discovery obs bolded
- Orbital Elements labeled with source (MPC)
- MPEC list items: orbit class, H, MOID, PHA annotation
- Background pre-fetch of all list MPECs for annotations

### Phase 2: Observability Panel (complete)
- **"Short term observability"** accordion section with NEOfixer ephem
- Altitude curve (5-day window) with fill, V magnitude on secondary axis
- Night shading (twilight bands, dark time) for Mt. Lemmon latitude
- "Now" time marker, min-altitude line (20°), peak stats summary
- Site selector buttons: I52, G96, 703, V06 — dedicated callback
- Hover text with alt, V mag, exposure time, motion rate

### Additional improvements (Phase 2)
- Discovery tracklet highlighted with green box-shadow (not border)
- Discovery station highlighted in Observer Credits
- PHA displayed as red cartouche badge (like Discovery green badge)
- Orbit info line (class, H, MOID, PHA) in MPEC detail header
- `--maintenance` CLI flag with yellow advisory banner

## Phase 3: MPEC Classification & DOU Integration (planning)

### MPECWatch Taxonomy

The current parser (`classify_mpec` in `lib/mpec_parser.py`) uses three
types: `discovery`, `recovery`, and `editorial`.  MPECWatch defines a
richer taxonomy that better represents MPC publication practice:

| MPECWatch Type | Current Mapping | Description |
|----------------|----------------|-------------|
| **Discovery** | `discovery` | New object with provisional designation |
| **OrbitUpdate (P/R/FU)** | `recovery` | Orbit updates from precovery/recovery/follow-up obs |
| **DOU** | `editorial` (filtered) | Daily Orbit Update — bulk orbit updates |
| **Editorial** | `editorial` (filtered) | Announcements and notices |
| **ListUpdate** | (not handled) | Updates to lists of interesting objects (mostly retired since 2012) |
| **Retraction** | (not handled) | Retracted MPECs |
| **Other** | (not handled) | Uncategorized MPECs |

### What's in the DOU

The Daily Orbit Update (DOU) is a single MPEC issued each day
containing bulk orbit updates for many objects.  It includes:

- **Newly identified objects** — objects linked to previous
  apparitions (numbered or multi-apparition)
- **Orbit improvements** — updated elements from new observations
- **One-opposition orbit updates** — refined orbits from same-lunation
  additional observations

The DOU is currently filtered out entirely (`editorial` type).  This
discards useful information:

1. **CSS objects in the DOU** — which CSS discoveries got orbit updates
   today?  Did any get linked to previously known objects?
2. **Impact monitoring triggers** — objects with improved orbits may
   enter or leave Sentry/NEOCC watchlists
3. **Follow-up completeness** — DOU updates often result from follow-up
   observations; tracking these shows the follow-up pipeline working

### Proposed Features

**Phase 3a: DOU awareness (low effort)**

- Parse the DOU to extract object designations mentioned
- Cross-reference against the current MPEC list: if any object from
  a Discovery/OrbitUpdate MPEC appears in today's DOU, annotate it
  (e.g., "Orbit updated in DOU 2026-C123")
- Add a small "DOU status" indicator to the enrichment card
- No need to display the full DOU content (it's very long)

**Phase 3b: Expanded classification (moderate effort)**

- Extend `classify_mpec` to return all MPECWatch types:
  `discovery`, `orbit_update`, `dou`, `editorial`, `list_update`,
  `retraction`, `other`
- Update the MPEC list to show type badges (like Discovery/OrbitUpdate)
- Add a filter dropdown or checkboxes to show/hide types
- OrbitUpdate MPECs are already shown as "recovery" — rename/restyle
- ListUpdate and Retraction are rare; just label them correctly

**Phase 3c: DOU feed (higher effort)**

- Fetch and parse the DOU to extract individual object entries
- Show a "DOU Objects" panel or sub-list: designation, updated
  elements, which stations contributed new observations
- Filter to CSS-observed objects for operational relevance
- This effectively builds a "what changed today" view

### Classification Heuristics

Improving `classify_mpec` to match MPECWatch categories:

```python
def classify_mpec(title, pre_text=""):
    # DOU: title contains "DAILY ORBIT UPDATE"
    if "DAILY ORBIT UPDATE" in title.upper():
        return "dou"
    # Editorial: title contains "EDITORIAL" or other editorial markers
    if "EDITORIAL" in title.upper():
        return "editorial"
    # Retraction: title contains "RETRACTION" or "RETRACTED"
    if "RETRACT" in title.upper():
        return "retraction"
    # ListUpdate: title like "Distant Minor Planets", "Unusual Minor
    #   Planets", "Critical-List Numbered Minor Planets"
    list_markers = ["DISTANT MINOR PLANETS", "UNUSUAL MINOR PLANETS",
                    "CRITICAL-LIST", "POTENTIALLY HAZARDOUS"]
    if any(m in title.upper() for m in list_markers):
        return "list_update"
    # OrbitUpdate: "Revision to MPEC", "Additional Observations"
    if pre_text:
        if "Revision to MPEC" in pre_text or \
           "Additional Observations" in pre_text:
            return "orbit_update"
    # Discovery: new provisional designation
    return "discovery"
```

### Impact on Existing Features

- **MPEC list filtering**: Currently shows discovery + recovery.
  Extending to show orbit_update (= recovery) keeps the same list.
  Adding DOU, list_update, retraction as opt-in filters is additive.
- **Auto-select**: Still follows latest *discovery* MPEC.
- **Enrichment**: Works for any type that has a designation.
- **Discovery stats tabs**: Unaffected (use SQL data, not MPEC parser).

## Phase 4: Multi-orbit Comparison (future)

Cross-reference orbits from NEOfixer, SBDB, MPC, and NEOCC.  Show a
comparison table of elements, highlight discrepancies.  Becomes more
interesting as arc length grows and orbits converge.

## Files modified

| File | Status | Description |
|------|--------|-------------|
| `lib/api_clients.py` | New, complete | All API wrappers (SBDB, Sentry, NEOfixer, NEOCC) |
| `lib/mpec_parser.py` | Modified | strip fix, classification |
| `app/discovery_stats.py` | Modified | Auto-select, enrichment, observability, obs coloring, annotations |
| `app/assets/theme.css` | Modified | Enrichment card, auto-indicator, badge styles |

## Forward-looking Notes

**Responsive / small-screen support:**
- Dash uses CSS/Flexbox; adding `@media` queries for mobile is feasible
- Plotly charts resize via `responsive=True` (default in Dash)
- The two-panel MPEC browser layout would need to stack vertically
- Consider `dash-mantine-components` or `dash-bootstrap-components` for
  responsive grid systems

**Multi-language / i18n:**
- No built-in Dash i18n; text strings would need a translation layer
- A planetary defense glossary (IAU terms, orbit classes, risk scales)
  would be the foundation
- Approach: extract all UI strings to a dict/JSON keyed by language code
- Plotly axis labels and hover text support Unicode natively
