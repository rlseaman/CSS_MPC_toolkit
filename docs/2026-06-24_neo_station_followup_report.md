# NEO station follow-up report — progress-report double-check

**Generated:** 2026-06-24
**Reporting period:** 2025-08-01 → 2026-06-17 (inclusive)
**Replica:** Gizmo (PostgreSQL 18.3 logical replica of `mpc_sbn`, row-exact with Sibyl)
**Query:** [`sql/station_neo_followup.sql`](../sql/station_neo_followup.sql)
**Purpose:** Independent cross-check of the figures hand-built with MAQI for the
next CSS progress report.

---

## 1. NEO discoveries — survey telescopes

| Station | NEO discoveries |
|---|--:|
| **G96** Mt. Lemmon | **614** |
| **V00** Bok        | **366** |
| **703** Catalina   | **207** |

## 2. NEO incidental follow-up — survey telescopes

| Station | Unique NEOs | Total obs | Tracklets |
|---|--:|--:|--:|
| **G96** | 1,861 | 16,545 | 4,248 |
| **V00** |   716 |  3,470 |   882 |
| **703** |   841 | 16,107 | 4,201 |

## 3. Precovery observations — survey telescopes

| Station | Unique NEOs | Total obs | Tracklets |
|---|--:|--:|--:|
| **G96** | 172 | 494 | 196 |
| **V00** |  38 |  88 |  39 |
| **703** |  61 | 151 |  63 |

## 4. Follow-up — dedicated follow-up telescopes

| Station | Unique NEOs | Total obs | Tracklets |
|---|--:|--:|--:|
| **I52** | 2,286 | 20,717 | 5,693 |
| **V06** |   692 |  3,817 |  1,089 |

I52 also had 1 object / 3 obs classed as precovery; V06 had none. Neither
follow-up telescope discovered an NEA in the window.

---

## Methodology

- **NEO set = MPC NEA.txt.** The 41,955 objects flagged `in_mpc` in
  `css_neo_consensus.v_membership_wide`, ingested nightly from
  `minorplanetcenter.net/iau/MPCORB/NEA.txt`. 41,917 matched ≥1 observation;
  the 38 unmatched are brand-new NEA.txt entries (0.09%, negligible).
- **Object → observation match** on both `permid` and `provid` (plus secondary
  provisional aliases via `css_neo_consensus.v_member_designations`). Both keys
  are required: numbered objects such as Apophis carry ~90% of their
  observations under `permid` with an empty `provid`.
- **Discovery** = the earliest `disc='*'` observation of the object; that
  observation's `stn` is the discoverer. The "NEO discoveries" figure counts
  **distinct NEAs** whose discovery observation fell inside the window.
- **Temporal partition (relative to each object's discovery):**
  - *precovery* = the station's observations of the object **before** discovery,
  - *follow-up* = the station's observations **after** the discovery tracklet
    (the discovery tracklet itself is excluded from both).
  - **Self-discoveries are included** in follow-up (a station's later
    re-observations of objects it discovered count as follow-up).
- **Counting units:** "Total" = individual observations (obs80 lines); "unique"
  = distinct NEAs; "tracklets" = distinct `trkid` (observations with a null
  `trkid` count as singleton tracklets).
- **Window applied to observation date** (`obstime`), half-open
  `[2025-08-01, 2026-06-18)` so all of 2026-06-17 is included.

### Definitional notes / things to confirm against MAQI's numbers

- **Precovery convention.** Here *precovery* means precovery observations the
  station **took during the reporting period** (i.e. `obstime` in window, before
  that object's discovery). An alternative convention — precoveries *of objects
  discovered during the period*, regardless of when the precovery frame was
  taken — would give different (generally similar) numbers. One-line change in
  the query if MAQI used the latter.
- **Unclassifiable leakage.** A few in-window observations belong to NEAs with
  no `disc='*'` flag anywhere in the archive and cannot be assigned to
  discovery / follow-up / precovery: 703 → 93 obs (2 objects), G96 → 39 obs
  (3 objects), V00 → 8 obs (2 objects). These are excluded from the tables above.

### Run cost

Main partition query ~8m24s; the diagnostic pass ~2m16s (Gizmo NVMe, against
the 5.09M-row `obs_sbn_neo` matview). No scan of the raw 526M-row `obs_sbn`.
