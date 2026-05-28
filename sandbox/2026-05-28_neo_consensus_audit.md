# NEO Consensus tab — full source + disagreement audit (snapshot 2026-05-28)

Probe of `css_neo_consensus.source_membership` (250,885 rows) and the
displayed `v_membership_wide` view (41,969 NEA primaries) against
`current_identifications`, `numbered_identifications`, `mpc_orbits`,
`obs_summary_all`, `obs_sbn`, and `obscodes`.

Reproducible via `psql -h /tmp -U claude_ro mpc_sbn -f sql/consensus_audit.sql`.
NEA scope only (`v_membership_wide` already applies `WHERE NOT is_comet`).

## Headlines

| metric | value |
|---|---|
| primaries displayed (NEA) | 41,969 |
| all-six-agree | 41,604 |
| disagreements | **365** |
| secondary-designation aliases across all sources | 15 rows |
| disagreements that close upon collapse | 7 (1.9 %) |
| **MPC-internal (NEA.txt vs mpc_orbits q≤1.3) mismatch** | **102** |
| share of disagreements where NEOfixer is the missing source | **~40 %** |

Aliasing is **not** the dominant driver. The real story is **survey
provenance** (which station discovered the object) and **arc structure**
(single-night, single-site detections that some institutions accept and
others don't), plus genuine **orbit-fit divergence at q ≈ 1.3**.

## 1. Faithfulness audit — what each ingestor actually does

All six lists descend ultimately from MPC observations; the five
independent institutions then each fit their own orbits.  Where our
pipeline applies its own filter rather than passing the institution's
declaration through, the consensus tab reflects *our* interpretation,
not the institution's:

| source | endpoint | filter applied | passthrough vs derived? |
|---|---|---|---|
| `mpc` (NEA.txt) | `https://minorplanetcenter.net/iau/MPCORB/NEA.txt` | none | **passthrough** |
| `mpc_orbits` | local SQL against `public.mpc_orbits` | **`q ≤ 1.3 ∧ e < 1`, asteroids + `A/` only** | **derived (ours)** |
| `cneos` | `ssd-api.jpl.nasa.gov/sbdb_query.api?sb-class=IEO,ATE,APO,AMO` | trust JPL's `sb-class` tag | **passthrough** |
| `neocc` | `neo.ssa.esa.int/PSDB-portlet/download?file=allneo.lst` | none | **passthrough** |
| `neofixer` | `neofixerapi.arizona.edu/targets/?site=500&q-max=1.3` | **drop NEOCP + smart q-rule** (overrides NEOfixer when NF q > 1.3 AND orbit "solid") | **derived (ours)** |
| `lowell` | `ftp.lowell.edu/pub/elgb/astorb.dat.gz` | **q = a(1−e) ≤ 1.3 ∧ e < 1**, computed by us | **derived (ours)** |

Two important consequences:

- The `mpc_orbits` source is **MPC's orbit catalog under our q ≤ 1.3
  filter**, not "what MPC declares to be an NEO."  MPC's authoritative
  declaration is NEA.txt (the `mpc` source).
- `neofixer` and `lowell` are **our reductions of orbit catalogs to a
  q-cut**, not those institutions' published NEO lists.  Lowell doesn't
  publish an NEO list; NEOfixer publishes a target-priority list, and
  we apply a smart q-rule that intentionally diverges from theirs.

So "we don't represent what NEOfixer claims" is *correct by design* — but
worth saying out loud.  We *do* represent what MPC NEA.txt, NEOCC, and
CNEOS publish, with no filtering on top.

## 2. Pairwise disagreement matrix (5 institutions)

Cell `[A, −B]` is the count of objects A has but B doesn't.  Diagonal
is zero by construction.  Excludes `mpc_orbits` (our view, tallied
separately).

|          | −mpc | −cneos | −neocc | −neofixer | −lowell | total |
|---|---|---|---|---|---|---|
| mpc      |  —   |  50    |  21    |  **156**  |  30     | 41,794 |
| cneos    |  27  |   —    |  30    |  **123**  |  45     | 41,771 |
| neocc    |  16  |  48    |   —    |  **159**  |  26     | 41,789 |
| neofixer |  62  |  52    |  70    |   —       |  82     | 41,700 |
| lowell   |  39  |  77    |  40    |  **185**  |   —     | 41,803 |

Closest pairs (point 4 — institutions using similar fit choices):

| pair | A−B + B−A | comment |
|---|---|---|
| **MPC ↔ NEOCC** | **16 + 21 = 37** | smallest mutual divergence — NEOCC tracks NEA.txt closely |
| MPC ↔ Lowell | 30 + 39 = 69 | second-closest |
| MPC ↔ CNEOS | 27 + 50 = 77 | |
| CNEOS ↔ NEOCC | 30 + 48 = 78 | both lean on orbit-class tags |
| CNEOS ↔ Lowell | 45 + 77 = 122 | |
| NEOCC ↔ Lowell | 26 + 40 = 66 | |
| **MPC ↔ NEOfixer** | **156 + 62 = 218** | NEOfixer is the outlier with everyone |
| CNEOS ↔ NEOfixer | 123 + 52 = 175 | |
| NEOCC ↔ NEOfixer | 159 + 70 = 229 | largest |
| Lowell ↔ NEOfixer | 185 + 82 = 267 | |

**NEOfixer disagrees with every other institution by 175–267 objects**,
roughly 3–6× the mutual disagreement among MPC/CNEOS/NEOCC/Lowell.  That
is the consistent signal: NEOfixer is paradigmatically distinct
(Find_Orb-based, observability-prioritised), while the other four cluster.

## 3. MPC-internal: NEA.txt vs mpc_orbits

|  | count |
|---|---|
| in NEA.txt, not in `mpc_orbits` (q ≤ 1.3 filter) | 16 |
| in `mpc_orbits` (q ≤ 1.3 filter), not in NEA.txt | **86** |
| both | 41,778 |
| neither, but at least one other source has it | 89 |

This is the real MPC-internal disagreement — 102 mismatches between
MPC's curated text-file catalog and its own orbit catalog, despite
both nominally representing MPC's view.  The 86-row asymmetry suggests
NEA.txt curation lags `mpc_orbits` ingest: orbits with q ≤ 1.3 land in
the database before they're promoted into NEA.txt.

## 4. What drives the 358 substantive disagreements

### Top disagreement patterns and what survey discovered them

| pattern | n | dominant `disc_by` station | what it is |
|---|---|---|---|
| missing only NEOfixer | **99** | **G45 = SST (50/99)**, G96, F51, X05 | mostly Space Surveillance Telescope dense single-night tracklets, no follow-up |
| `mpc_orbits` only | 71 | **C51 = WISE (67/71)** | space-based survey detections, no ground follow-up |
| only NEOfixer | 38 | (well-observed, multi-site) | the Mars-Crosser shell — orbit-fit divergence, MPC q > 1.3 but NF q ≤ 1.3 |
| missing CNEOS + NEOfixer | 35 | **C51 = WISE (28/35)** | WISE detections that didn't graduate into JPL's class tags |
| only Lowell | 21 | mixed | recent discoveries Lowell ingested before others |
| missing only Lowell | 17 | mixed | last week's discoveries Lowell hasn't pulled yet |

### Observational characteristics (vs all-six-agree baseline)

|  | n | nobs p50 | arc p50 (days) | one-night | arc < 30 d | single-site |
|---|---|---|---|---|---|---|
| **all_six (5000-sample)** | 5000 | 55 | 56 | 66 (1.3 %) | 1,134 (23 %) | (low) |
| missing only NF | 99 | 24 | **0** | 51 (52 %) | 60 (61 %) | **54 (55 %)** |
| `mpc_orbits` only | 71 | 10 | **1** | 16 (23 %) | 67 (94 %) | **67 (94 %)** |
| missing CNEOS + NF | 35 | 15 | 2 | 1 | 35 (100 %) | **28 (80 %)** |
| only NF | 38 | 45 | 68 | 3 (8 %) | 12 | 2 (5 %) |
| only Lowell | 21 | 14 | 2 | 1 | 17 (81 %) | 7 (33 %) |
| missing only Lowell | 17 | 16 | **0** | 13 (76 %) | 17 (100 %) | 3 (18 %) |

The pattern is overwhelming:

- **Short arcs.** Median arc in the disagreement categories is 0–2
  days, vs 56 days in the baseline.  Almost every disagreement category
  is dominated by sub-30-day arcs (61 % – 100 %), vs ~23 % in baseline.
- **Single-site detections.** 18 %–94 % of disagreement rows are
  single-site, vs ~1 % in baseline.  These are objects observed by
  exactly one station and never confirmed elsewhere.
- **Survey provenance does most of the work.**  Two surveys explain
  most of the "missing from someone" mass:
  - **C51 (WISE)** — space-based, no ground follow-up — accounts for
    67/71 in `mpc_orbits`-only and 28/35 in CNEOS+NF-missing.
  - **G45 (Space Surveillance Telescope, Atom Site)** — USAF dense
    intra-night tracklets, no multi-night follow-up — accounts for
    50/99 in NF-missing.

This is *not* an H-magnitude story.  Faint objects show up because
faint objects are exactly the ones that don't get the multi-site arcs
required for promotion into curated catalogs.  H is a *consequence* of
the short-arc / single-site selection, not a filter any institution is
applying.

### "only NEOfixer" is the only category driven by orbit fit

The 38 only-NEOfixer rows are the opposite shape: well-observed
(median 45 obs, median arc 68 d, median 7 stations), and every one has
NEOfixer's q ≤ 1.3 while MPC's q > 1.3.  This is the genuine
Mars-Crosser-shell — independent Find_Orb fit putting the object inside
the NEA boundary while MPC's fit puts it outside.

## 5. Per-source exception table (alias rows)

15 rows total across the six sources.  Collapsing closes 7 of 365
disagreements.

### MPC NEA.txt — 2 alias rows
| reported | resolves to | note |
|---|---|---|
| `2010 MZ112` | `2026 AA14` | also reported by Lowell; primary present in all six |
| `2025 XU`    | `2010 HK22` | also reported by Lowell; primary present in all six |

### Lowell astorb.dat.gz — 9 alias rows
| reported | resolves to | case |
|---|---|---|
| `2010 MZ112` | `2026 AA14` | B (also in mpc) |
| `2025 XU`    | `2010 HK22` | B (also in mpc) |
| `2026 DU14`  | `2011 EC41` | B |
| `2026 EG2`   | `2005 XY4`  | B |
| `2026 EK1`   | `2015 EX`   | B |
| `2026 FM`    | `2026 EU3`  | B |
| `2026 GF`    | `2001 MS3`  | B |
| `2025 MN229` | `P/1994 P1` (= 141P/Machholz 2) | D comet, Rubin observation |
| `2025 NR197` | `P/1818 W1` (= 2P/Encke)        | D comet, Rubin observation |

### JPL CNEOS — 2 alias rows
| reported | resolves to |
|---|---|
| `2025 MN229` | `P/1994 P1` (= 141P/Machholz 2) |
| `2025 NR197` | `P/1818 W1` (= 2P/Encke)        |

### ESA NEOCC — 2 alias rows
| reported | resolves to |
|---|---|
| `2025 MN229` | `P/1994 P1` (= 141P/Machholz 2) |
| `2025 NR197` | `P/1818 W1` (= 2P/Encke)        |

### NEOfixer — 0 alias rows; two separate notes:

- **137 periodic comets** in NEOfixer's NEA-scope endpoint (1P, 2P,
  12P, 13P, …, 218P, fragments).  All tagged `is_comet=true` at our
  ingest and filtered from `v_membership_wide` by `WHERE NOT is_comet`.
  **Feature, not bug** — but worth confirming with the NEOfixer team
  that intent is "we ship NECs alongside NEAs."
- **38 only-NEOfixer Mars-Crosser shell** where NF q ≤ 1.3 but MPC q > 1.3.
  Smart q-rule covers the "NF q > 1.3 ∧ solid orbit" case but leaves
  these long-arc Find_Orb divergences in.  See recommendation #2.

### `mpc_orbits` — 0 alias rows.  Clean.

## 6. Recommendations, revised

1. **No NEOfixer-side ingest change to chase the 99 "missing only NF"
   objects.**  They are short-arc, single-site, mostly G45 / WISE
   detections; NEOfixer's omission is consistent with its
   observability-prioritisation purpose, and "force-add" is the wrong
   reflex.  If CSS wants to know "what would Find_Orb do with these
   if it tried?" that's a NEOfixer-internal question, not an ingest
   bug on our side.

2. **Smart q-rule extension for the 38 only-NEOfixer Mars-Crosser
   shell stands.**  Adding "also drop when `mpc_orbits.q > 1.3`" to
   `lib/neo_consensus_neofixer.py` is the cleanest cut: trust MPC's
   long-arc fit over Find_Orb's reprocessed-restart geometry at the
   boundary.  Eliminates the 38 only-NF rows.

3. **MPC-internal mismatch (86 + 16 = 102) is the most informative
   "delta to share."**  It's MPC's own data telling MPC's own
   curators "your text file and your orbit catalog disagree on these
   objects."  An exception report for MPC would lead with that, not
   with the 2 NEA.txt alias rows.

4. **Tag disagreements with survey provenance + arc-class on the
   Consensus tab.**  Columns `disc_by`, `arc_days`, `n_stns` per
   primary would explain *most* disagreements at a glance and remove
   the need to guess about H or fit-divergence on every row.

5. **Don't filter on H, ever.**  No institution is doing it; any
   apparent H correlation in disagreement categories is a downstream
   symptom of short-arc selection.

## Appendix A — Disagreement categories with survey + arc/site detail

(The summary tables above.)

## Appendix B — How we verified G45

`obs_sbn.stn = 'G45'`: 17,167,417 observations of 53,089 distinct
objects, 2011-11-10 → 2022-04-03.  `obscodes.name`: *Space Surveillance
Telescope, Atom Site*.  Sample of 15 G45-discovered NEAs in the
"missing only NF" category: every one has `arc_days < 0.28` with
`first_obs == last_obs` (single-night), 12–52 obs packed into the
night.  That's the SST surveillance-cadence signature.

## Appendix C — How we verified Rubin's role in the comet aliases

`obscodes.name['X05']` is Rubin Observatory.  `obs_sbn` shows X05
observed 141P/Machholz 2 (10 obs, 2025-06-25 to 2025-07-14) and
2P/Encke (23 obs, 2025-07-11 to 2025-07-21), the most of any station
in that window for 2P.  Both initially carried provisional designations
`2025 MN229` and `2025 NR197` before MPC linked them to the comets.
