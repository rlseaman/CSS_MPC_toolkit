# MPEC Browser & Planetary Defense Dashboard — UX Analysis

**Date:** 2026-02-16
**Context:** Review of MPEC Browser (Tab 0) and broader dashboard UX,
informed by NASA PDCO and IAWN priorities.

---

## 1. Arrow Key Navigation

The MPEC list is currently mouse-only. Arrow key stepping is the single
highest-value UX addition. Implementation approach:

- Add a **clientside callback** (Dash's `clientside_callback`) that
  listens for `keydown` events on the list panel
- Up/Down arrows move `mpec-selected-path` to the previous/next item
- The list panel auto-scrolls to keep the selected item visible
  (`scrollIntoView`)
- This must be clientside JavaScript to avoid the ~200ms server
  round-trip per keystroke

## 2. Other Keyboard Shortcuts Worth Adding

| Key | Action | Rationale |
|-----|--------|-----------|
| `↑` / `↓` | Step through MPEC list | Core navigation |
| `Home` / `End` | Jump to newest / oldest in list | Quick repositioning |
| `F` | Toggle "Follow latest" mode | Muscle memory from chat/log tools |
| `1`-`5` | Expand/collapse detail sections | Orbital elements, credits, obs, residuals, ephemeris |
| `O` | Cycle observatory site | Step through I52 → J95 → T14 → H21 → 474 |
| `?` | Show keyboard shortcut overlay | Discoverability |

Keep the set small and avoid conflicting with browser defaults (no
Ctrl/Cmd combos). A small `?`-triggered overlay is the standard pattern
for web apps with shortcuts.

## 3. UI Conveniences

**Within the MPEC Browser tab:**

- **Search/filter box** at top of list panel — filter by designation,
  MPEC ID, or orbit class. With 20-30 items not critical, but essential
  if "load more" is added.
- **PHA-only toggle** — checkbox to show only Potentially Hazardous
  Asteroid MPECs.
- **Visual risk indicator in the list** — small red/amber dot on list
  items so users can scan for high-interest objects without clicking each.
- **Sticky header row** in detail panel showing designation + MPEC ID,
  visible while scrolling through observations/residuals.
- **Copy designation button** — clipboard icon next to the designation.
  Observers frequently paste designations into other tools (MPC
  ephemeris service, JPL Horizons, Find_Orb).
- **Deep-linkable URLs** — use `dcc.Location` to put the MPEC path in
  the browser URL bar (`?mpec=K26/K26CB9`), so users can share/bookmark.

**Across all tabs:**

- **Cross-tab object linking** — clicking a designation in the MPEC
  Browser could pre-filter Tabs 1-5 to that object's survey/year/size
  class, and vice versa.

## 4. Output Options

Currently each tab has "Download CSV." Additional options:

- **Copy table to clipboard** (plain text or TSV) — faster than
  downloading a file when pasting into Slack or email
- **Export current MPEC detail as plain text** — the raw MPC 80-column
  format is already parsed; a "Copy MPEC text" button for forwarding
- **ADES PSV export** for observations shown in the MPEC — `lib/
  ades_export.py` already exists; wiring it to parsed observations is
  natural
- **Ephemeris export** — observability chart data as downloadable CSV
  (site, UTC, alt, azmth, V mag, rate)
- **Print-friendly view** — `@media print` CSS block that hides
  controls, expands all sections, renders detail panel full-width

## 5. Performance Improvements

- **Clientside callbacks for highlighting/styling** — the
  `highlight_selected_mpec` callback currently round-trips to the server
  just to swap CSS classes. Move clientside to eliminate perceived lag.
- **Prefetch adjacent MPECs** — when user selects item N, prefetch N-1
  and N+1 details in background. Arrow-key browsing then feels instant.
- **Lazy-load enrichment sections** — collapsible sections (residuals,
  ephemeris) could defer API calls until opened.

## 6. Under-Explored Opportunities

Gaps the dashboard is well-positioned to fill that existing tools
(CNEOS, Scout, JPL SBDB, MPC) do not cover:

### a) Discovery-to-characterization timeline view
No public tool shows the **lifecycle of a single NEO from discovery
through follow-up to orbit determination to risk assessment** as a
unified timeline. The dashboard already has the pieces (MPEC discovery,
follow-up timing tab, Sentry/NEOCC risk data, SBDB orbit class).

### b) Survey coverage gap analysis
Tab 3 (Multi-survey Comparison) already shows co-detection. The natural
extension: **what regions of sky/time were NOT covered?** Cross-
referencing discovery circumstances (Tab 5 sky map) with survey pointing
data would show where the gaps are — directly relevant to IAWN's
coordination mission.

### c) Discovery efficiency metrics
Discoveries per telescope-hour by survey, discovery rate vs. lunar
phase, H-magnitude reach by survey (faintest discovery per month).
These metrics matter for evaluating whether the NEO survey goal (140m+
completeness) is on track.

### d) Real-time MOID watchlist
Allow users to set a **MOID threshold alert** — "highlight any new MPEC
where Earth MOID < 0.02 AU." Trivially implementable with cached
summary data; transforms the browser from a reading tool into a
monitoring tool.

### e) Observatory follow-up prioritization
Sort the MPEC list by "uncertainty parameter × observability score" to
help observers at the telescope decide what to point at. NEOfixer
provides U values; combine with altitude/magnitude data already fetched.

## What NOT To Do

- Don't replicate CNEOS's close approach tables or Scout
- Don't build an orbit visualizer (JPL's is excellent)
- Don't try to become a general MPC database browser — stay focused on
  the discovery/follow-up workflow
- Don't add complex user accounts or saved preferences — URL-based state
  (`dcc.Location`) covers sharing without infrastructure
