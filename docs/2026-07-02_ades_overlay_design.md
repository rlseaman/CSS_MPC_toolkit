# ADES reprocessing overlay — design

**Author:** Rob Seaman (with Claude)
**Date:** 2026-07-02
**Status:** Pilot / proposal. Schema `sql/ades_overlay/schema.sql`; a live pilot
(2 tracklets) runs on Gizmo as `css_ades_overlay`.
**Companion:** [`2026-07-02_ades_resubmission_findings.md`](./2026-07-02_ades_resubmission_findings.md)
(why this is needed).

## Motivation

CSS is reprocessing its historical astrometry (Gaia recalibration + full ADES
quality fields) and resubmitting it to the MPC. But MPC does **not** ingest
resubmissions as updates to already-published observations — verified
archive-wide: of ~1.6 M 2020 CSS observations resubmitted in ADES, only 0.06%
show any ADES field in `obs_sbn`; the rest remain obs80-precision, untouched.

So the reprocessed data — precise positions, `rmsRA/rmsDec`, `logSNR`, `nStars`,
full-precision time — has nowhere to live in the queryable database. This is the
same shape as the project's other MPC-shortfall workarounds (`css_neo_consensus`,
the `mpc_orbits` derivations): build a **local value-added layer** that queries
can opt into.

**Concept of operations.** A CSS-authoritative *overlay* on top of `obs_sbn`:
where CSS has reprocessed a tracklet, the overlay is treated as more authoritative
and transparently substituted; elsewhere `obs_sbn` shows through unchanged.
"Effective observations" = overlay where present, else `obs_sbn`.

## Scope

- **Now:** the Nov-2024 resubmission (~1.62 M obs, 5 telescopes, 2020).
- **Eventual:** the 2003–2019 backlog, **~100 M rows** — a months-long
  reprocessing campaign, ingested as **deltas** as batches complete.
- **Boundary:** overlay only the obs80-origin backlog; native-ADES-era `obs_sbn`
  rows (post ~2019) already carry their fields and are left alone.

## The model: tracklet supersession

The unit is the **tracklet**, not the observation: per CSS, if *any* observation
in a tracklet is reprocessed, the **entire original tracklet is invalidated** and
replaced wholesale. This makes the model three operations plus versioning:

| op | meaning |
|----|---------|
| `supersede` | invalidate the original tracklet (a set of `obs_sbn.obsid`s) and substitute the reprocessed tracklet's observations |
| `add` | reprocessed tracklet with no `obs_sbn` counterpart (previously unsubmitted) — `original_obsids` empty |
| `suppress` | invalidate an original tracklet with no replacement — no overlay observations |

The requested variations map cleanly:

| variation | model |
|---|---|
| (a) previously unsubmitted | `add` |
| (b) head-to-head swap | `supersede`, replacement = original count |
| (c) more new obs / tracklet | `supersede`, replacement > original |
| (d) fewer new obs / tracklet | `supersede`, replacement < original |
| (e) mixed new/old/matching | `supersede` — wholesale swap sidesteps per-obs bookkeeping |
| (f) MPC later updates underneath | versioning: `basis_max_updated` drift detection (below) |
| (g) shadow rescinded | versioning: `status='rescinded'` → originals reappear |

This mirrors ADES's own `replacesObsID` / `deprecated` semantics — we are locally
reimplementing what MPC would do if it ingested the resubmissions.

## Data model

`css_ades_overlay.tracklet` — one supersession record per reprocessed tracklet:
`overlay_trk_id`, `source_batch`, `stn`, `new_trksub`, `op`, `original_obsids`
(the whole invalidated tracklet, resolved to `obs_sbn.obsid`s), `status`
(active | rescinded), `basis_max_updated` (the `max(obs_sbn.updated_at)` of the
originals at reconciliation time — for (f) drift detection), `created_at`.

`css_ades_overlay.obs` — the reprocessed observations (the `add`/`supersede`
payloads): identity + `obstime` (full precision) + `ra/dec` + `mag/band` +
`astCat/photCat` + the ADES quality fields (`rmsRA/rmsDec/rmsCorr/rmsTime/rmsMag/
logSNR/rmsFit/nStars`).

**Effective view** (`v_effective`): `obs_sbn` rows whose `obsid` is not in any
active tracklet's `original_obsids`, `UNION ALL` the observations of active
`supersede`/`add` tracklets, each row tagged `src` (`obs_sbn` | `overlay`).

## Reconciliation — proximity matching (the hard part, now de-risked)

For 2003–2019 the reprocessed `trkSub`s are freshly minted and do **not** match
`obs_sbn`, so linking a reprocessed observation to the `obs_sbn.obsid` it
supersedes must be **proximity matching** on `(stn, obsTime, ra/dec)`. Two
experiments on the 2020 G96 data (where `trkSub` gives ground truth to score
against):

1. **Accuracy.** Discarding `trkSub` and matching purely by nearest neighbour in
   `(stn, obstime ±2 s, ra/dec)` recovered the correct `obsid` for **1,863 /
   1,863 (100%)** observations — 0 wrong, 0 ambiguous. Reprocessed positions sat
   0.05″ (median) from `obs_sbn`, times within 0.24 s.
2. **Shift tolerance / failure mode.** Perturbing every position by a fixed
   magnitude (random direction) and re-matching:

   | shift | clean-correct | ambiguous (→review) | silent-wrong |
   |---:|---:|---:|---:|
   | 0–10″ | 100.0% | 0.0% | 0.0% |
   | 30″ | 99.7% | 0.3% | 0.0% |
   | 60″ | 99.3% | 0.6% | 0.1% |

   Error-free to a **10″** shift (≫ any real recalibration), and it **fails
   safe**: ambiguity (caught → review) rises before silent-wrong. The driver is
   the inter-source spacing within a survey exposure — median **~24′**,
   minimum 38.6″ — which dwarfs any astrometric shift.

**Reconciler policy:** auto-accept a match only when the nearest source is
**≥ 2× closer than the runner-up**; route the rest to a **review queue**. Carry a
**match-confidence** on each supersession record.

3. **Coarse timing / density.** CSS objects move ~3.4″ between exposures spaced
   ~7.5 min apart. Degrading the usable `obs_sbn` time precision (forcing a wider
   match window, which also grows the candidate set) at a 1″ shift:

   | obs_sbn time known to | clean | ambiguous→review | silent-wrong |
   |---|---:|---:|---:|
   | ≤ 30 s | 100.0% | 0.0% | 0.0% |
   | ~2 min | 99.6% | 0.3% | 0.1% |
   | ≥ 10 min | ~81% | ~19% | ~0.4% |

   The threshold is the **exposure cadence**: while time is known to ≤ ~2 min
   (obs80 encodes it to ≪ 1 min, so real data is here), matching is ~perfect.
   Past the cadence it **fails safe** — ~19% become ambiguous (→review) but
   silent-wrong stays ≤ 0.4%. The coarse-timing failure mode is **self-confusion**
   (matching a slow mover to its adjacent exposure), caught by the confidence gate.
   **Review-queue tail: < 1% realistic, ~19% worst-case; silent-wrong ≤ 0.4%.**

**Residual risk:** genuine dense fields (galactic plane / near-ecliptic, smaller
inter-*object* spacing) and the follow-up scopes (I52/V06, a target on a field
asteroid). The 2020 survey archive is too sparse to exercise this (`diff-obj`
confusion stayed ~0.2% even with a whole night as candidates); it needs a real
low-latitude 2003–2019 batch to test — all bounded and absorbed by the review
queue regardless.

## Precedence when MPC updates underneath (f)

**Hybrid, not blanket "shadow wins."** The overlay is authoritative for the
**measurement fields it improves** (astrometry, uncertainties, precise time), but
MPC stays authoritative for **identity/status** (designation linkage,
`deprecated`, re-designations). A periodic reconciler compares each tracklet's
`basis_max_updated` to the live `obs_sbn.updated_at`; if MPC has since deprecated
or re-linked a superseded `obsid`, that is a **flagged conflict**, not a silent
override — we never resurrect astrometry MPC has since rejected.

## Efficiency and scale

- ~100 M overlay rows ≈ 10–25 GB — smaller than `obs_sbn` (540 M), fits the
  `css_*` local-schema pattern, never touches `obs_sbn` or replication.
- **Filtered queries** (by object/station/time — the real pattern) are efficient:
  `obs_sbn`'s indexes filter first, then a cheap `obsid`-indexed anti-join /
  probe into the overlay.
- **The footgun:** never scan `v_effective` unfiltered — that is a 540 M-row
  anti-join. For analytics, build purpose-specific matviews over the slices
  actually studied, not one materialized overlay.
- Ingest is **incremental** — each reprocessing batch appends assertions; no
  rebuild.

**Measured on the full 2020 archive (2026-07-02).** 3,215 files / 1,622,353 obs
→ 413,559 tracklets (408,914 `supersede`, 4,645 `add`, 20,809 new-detection obs,
**0% review**):

| stage | time | note |
|---|---|---|
| parse | 14 s | |
| **match** | **1,782 s** (**910 obs/s**) | the bottleneck — per-obs loop + Sibyl-HDD station-night pulls |
| emit COPY | (in match) | 335 MB file |
| scp + `COPY` apply | 6 s + 27 s | linear |
| storage | 349 MB obs + 145 MB tracklet + idx | ≈ 0.5 GB |
| filtered `v_effective` query | ~5 ms | with the GIN + `(stn,trksub)` indexes |

Per-night ≈ 19.5 K obs → ~21 s match; 2021 (V00, 17.9 K obs) ~20 s.
**Extrapolating to the ~100 M-row 2003–2019 backlog:** `COPY`/storage scale
linearly (~28 min apply, ~30 GB), but **match at 910 obs/s ⇒ ~30 h** — a naive
upper bound. It is trivially **parallelizable** (station-nights are independent)
and **vectorizable** (batch a night's obs into one numpy pass instead of the
per-obs loop), and running against Gizmo NVMe rather than Sibyl HDD removes the
pull cost — together plausibly 10–50×. And the campaign arrives as **deltas**, so
per-batch reconciliation is small regardless.

**One scale caveat for 100 M:** at ~25 M tracklets the GIN-array anti-join will
tire; materialize a normalized `superseded(obsid)` btree table (expand
`original_obsids`) so `v_effective`'s exclusion is an O(log n) probe.

## Pilot (live on Gizmo)

`css_ades_overlay` with 2 real superseded tracklets from G96 2020-08-01.
Demonstrated: before/after through one interface — `obs_sbn` shows the obs80 row
(coarse time, 1-decimal mag, NULL uncertainties); `v_effective` shows the
reprocessed row (full-precision time, 2-decimal mag, `rmsRA 0.084″`,
`nStars 8431`, `src='overlay'`). Rescinding a tracklet (`status='rescinded'`)
makes the `obs_sbn` original transparently reappear. Read access granted to
`claude_ro` (dashboard-ready).

## Open decisions

1. **Auto-accept gate:** hard 2×-confidence tolerance + review queue (proposed),
   vs a softer confidence score carried on every match.
2. **Bitemporal vs current-only:** do we need "effective record as of date X"
   (audit/rollback) or only current effective state? History roughly doubles the
   model but makes (f)/(g) fully auditable.
3. **Rescind granularity (g):** per tracklet (current model), per observation, or
   per submission batch.
4. **Review-queue workflow:** where the ambiguous tail is adjudicated and how
   decisions are recorded.

## Next steps

- ~~Coarse-timing edge-case test~~ **done** (above): review tail < 1% realistic,
  ≤ 0.4% silent-wrong; fails safe. Dense-*field* axis still needs a real
  low-latitude 2003–2019 batch (the 2020 survey data is too sparse).
- ~~Generalize the reconciler into a batch loader~~ **done**:
  `scripts/ades_overlay_loader.py` — parse → proximity-match (2× gate) →
  classify `supersede`/`add`, `auto`/`review` → emit SQL assertions
  (`original_obsids` resolved in-memory with whole-original-tracklet expansion;
  read-only match, writes emitted for owner apply). Validated end-to-end on a
  40-file subset (1,271 tracklets, 0% review) → `v_effective` substitutes
  correctly. Ops note: emit uses per-row `INSERT`; for full-archive-scale
  batches switch to `COPY`. Running the loader against the **same** replica it
  writes to avoids the cross-replica obsid assumption.
- Ingest a real 2003–2019 batch (ideally a low-latitude field) to close the
  dense-field question and exercise `suppress` (needs an explicit removal signal,
  not inferable from the adds alone).
- Wire an ingest of the first real 2003–2019 batch when available.
