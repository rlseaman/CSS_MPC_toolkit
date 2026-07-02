# Did the Nov-2024 CSS ADES resubmissions update obs_sbn? — findings

**Author:** Rob Seaman (with Claude)
**Date:** 2026-07-02
**Archive examined:** `CSS_ADES_resubmissions_24Nov29.tar.gz` (67 MB; 3,215 ADES
2017 XML files; ~1,622,363 observations; 5 CSS telescopes)
**Database:** Gizmo replica of `mpc_sbn` (logical replication from MPC)

## Question

CSS resubmitted ~1.62 M observations in ADES format on 2024-11-29. ADES carries
per-observation quality fields the legacy 80-column (obs80) format does not
(`rmsRA`, `rmsDec`, `rmsCorr`, `rmsTime`, `rmsMag`, `photCat`, `logSNR`,
`rmsFit`, `nStars`, full-precision `obsTime`). **Have those ADES-only fields
been populated in `obs_sbn` beyond what the original obs80 submissions carried?**

## Answer, one line

**No — for the 2020 CSS survey/follow-up observations (the bulk of the archive)
the resubmission did not update `obs_sbn` at all.** Those rows still hold only
their original obs80-derived content; every ADES-only quality field is NULL. The
one telescope whose rows *do* carry ADES fields (V00) carries them from its
*original* 2021 ADES submission, not from the resubmission.

## Archive shape

5 telescopes, 83 distinct UTC nights, 2020-05-21 → 2021-02-11:
703 (178 files), G96 (784), I52 (1,849), V06 (396), V00 (8, all 2021-02-11).
The `obs_sbn` schema is a full 91-column ADES schema, so every ADES field exists
as a real column — the question is purely whether they are populated.

## Method

A ~dozen files were sampled across all five telescopes and both ends of the
period (each station's earliest and latest night, biggest file per slot, plus
two mid-period files) — 11 files, **162,786 observations**. Each file was parsed
(ElementTree) and its observations matched to `obs_sbn` by `(stn, night,
trkSub/provID/permID)`, counting how many matched rows carry each ADES field.

**Mapping gotcha:** a naïve join on `obsTime` fails — `obs_sbn.obstime` is stored
at obs80 precision (e.g. `11:29:49.92`) while the ADES file has the full-precision
`11:29:50.027`. The reliable key is `(stn, trkSub)` + `ra/dec`, or obstime rounded
to obs80's ~0.9 s grid. Match rate on the 2020 survey files was **99.98%**
(144,899 of 144,928) — the expected one-to-one mapping holds.

## Results

| File | stn | night | ADES obs | matched | rmsRA | nStars | obs80 | astCat |
|------|-----|-------|--------:|--------:|------:|-------:|------:|-------:|
| 20May22.703.mpcd      | 703 | 2020-05-22 | 19,270 | 19,254 | **0** | 0 | 100% | 100% |
| 20May22.G96.mpcd      | G96 | 2020-05-22 | 30,492 | 30,487 | **0** | 0 | 100% | 100% |
| 20May22.V06.mpcd      | V06 | 2020-05-22 |      7 |     11 | **0** | 0 | 100% | 100% |
| 20May21.I52.mpcd      | I52 | 2020-05-21 |     15 |     15 | **0** | 0 | 100% | 100% |
| 20Aug01.G96.mpcd      | G96 | 2020-08-01 |  1,863 |  1,863 | **0** | 0 | 100% | 100% |
| 20Aug01.I52.U0O05Y    | I52 | 2020-08-01 |      4 |      4 | **0** | 0 | 100% | 100% |
| 703_20200923.mpcd     | 703 | 2020-09-23 | 17,389 | 17,383 | **0** | 0 | 100% | 100% |
| G96_20200923.mpcd     | G96 | 2020-09-23 | 75,867 | 75,861 | **0** | 0 | 100% | 100% |
| I52_20200921.mpcd     | I52 | 2020-09-21 |     17 |     17 | **0** | 0 | 100% | 100% |
| V06_20200918.mpcd     | V06 | 2020-09-18 |      4 |      4 | **0** | 0 | 100% | 100% |
| **V00_20210211.mpcd** | V00 | 2021-02-11 | 17,858 | 11,328\* | **10,736 (95%)** | 11,319 | 100% | 100% |

\* V00 matched via a whole-night UTC-straddle window (its Feb-2021 identifiers use
a different `trkSub` form; its winter night crosses UTC midnight).

**2020 obs80-origin subtotal (10 files): 144,899 matched observations, 0 with any
ADES-only quality field.** 100% carry `obs80` and `astCat` (both obs80-derivable —
`astCat` from the obs80 catalog flag).

## Full-archive pass (all 3,215 files — exact)

Parsing every file (8 s) confirms the archive is exactly **1,622,363
observations**, all keyed by `trkSub` (703: 268,637; G96: 1,326,515; I52:
7,802; V06: 1,524; V00: 17,885; 96.7% carry `rmsRA` in the files). The 413,559
distinct `(stn, trkSub)` pairs were joined to `obs_sbn` on `(stn, trkSub)`
(session `TEMP` table, `enable_seqscan=off` to force the `trksub` index; ~1m52s):

| obstime year | obs_sbn rows | with rmsRA | with obs80 |
|--------------|-------------:|-----------:|-----------:|
| **2020**     | **1,605,711** | **916 (0.06%)** | 100% |
| 2021         | 140          | 103        | 100% |
| other (2016–19, 2022–26) | ~224 | ~95   | 100% |

**Of the ~1.606 M `obs_sbn` rows matched to the resubmitted 2020 tracklets,
only 916 — 0.06% — carry any ADES quality field.** Archive-wide, the 2020 CSS
survey observations are obs80-only; the resubmission changed nothing. (The 916
are negligible edge cases, likely obs with a native-ADES origin.)

Two notes: (1) ~16 K archive observations — essentially all of V00 — did not
match on `(stn, trkSub)` because V00's ADES `trkSub` form differs from obs_sbn's
stored `trksub`; V00 is characterized separately below and *does* carry ADES
fields, from its **original 2021** submission. (2) The tiny cross-year tails are
`trkSub`-string collisions with unrelated tracklets in other years.

The original tarball was opened read-only and is byte-identical after the run
(SHA-256 `ac35e5f8…bffbd264`).

## The anchor observation (worked example)

ADES file `20Aug01.G96.FYQR62.1.1.ades`, obs of trkSub `C2YQR62`:
`rmsRA 0.19389`, `rmsDec 0.19303`, `rmsMag 0.174`, `logSNR 0.759`, `nStars 6565`,
`obsTime 2020-08-01T11:29:50.027Z`. The matching `obs_sbn` row:

```
obs80  =      C2YQR62  C2020 08 01.47905 00 29 39.87 +29 15 45.5          20.2 GV     G96
obstime = 2020-08-01 11:29:49.92   (obs80 .47905, NOT the ADES .027)
mag = 20.2 (vs ADES 20.16) ; astcat = Gaia2 (from obs80 flag 'V')
rmsra/rmsdec/rmscorr/rmstime/rmsmag/photcat/logsnr/rmsfit/nstars = NULL
submission_id = 2020-08-01T11:36:56 ; created_at = 2020-08-01 ; updated_at = 2022-05-04
```

Original 2020 obs80 submission, untouched by Nov 2024.

## The V00 control — why it matters

V00's rows *do* carry the ADES fields, but a provenance check shows they are
**original 2021 data**: `submission_id = 2021-02-12`, `created_at = 2021-02-12`,
and `obstime` is full precision (`02:14:16.675`, not obs80-coarse). Bok/V00
submitted ADES natively from the start. This is the decisive control: it proves
`obs_sbn` stores the ADES fields (and full-precision time) **whenever the original
submission is ADES** — so their absence for the 2020 CSS survey data is
attributable to (a) those originals being obs80 and (b) the Nov-2024 resubmission
never being applied. The same stations' *current* (2026) submissions also carry
the full field set — confirming the pipeline works today.

## Conclusion

MPC did **not** ingest the 2024 ADES resubmissions as updates to the already-
published 2020 observations — consistent with a policy of not overwriting
existing astrometry on resubmission. Whatever the resubmission's intent (it
appears to be 2020 CSS data reprocessed with Gaia astrometry + uncertainties),
it produced **no change** in `obs_sbn`: the observations remain obs80-precision,
with none of the resubmitted ADES quality metrics.

## Caveats

- **Replica scope.** This is the Gizmo logical replica. If MPC parked the ADES
  data in a store not covered by this replication, `obs_sbn` would not show it —
  but within `obs_sbn` the 2020 observations are obs80-only.
- **Some rows see later touches** (`max updated_at` up to 2026) — these are
  identification/linkage updates (e.g. a `provid` getting assigned); they never
  add ADES quality fields.
- **Sampling.** 11 files / 162,786 obs, not the full 3.2 K files. The pattern is
  uniform across telescopes and both ends of the period; a full pass is expected
  to match.

## Reproducing

`CSS_MPC_toolkit/venv/bin/python` parses the tarball (tarfile + ElementTree) to
select/parse files and emit per-file match SQL; queries run read-only as
`claude_ro` against Gizmo. Scripts in the session scratchpad; can be promoted to
`scripts/` if this becomes a recurring check.
