# NEO station follow-up report — V-magnitude augmented

**Generated:** 2026-06-24
**Reporting period:** 2025-08-01 → 2026-06-17 (inclusive)
**Replica:** Gizmo (PostgreSQL 18.3 logical replica of `mpc_sbn`, row-exact with Sibyl)
**Query:** [`sql/station_neo_followup_vmag.sql`](../sql/station_neo_followup_vmag.sql)
**Companion to:** [`2026-06-24_neo_station_followup_report.md`](./2026-06-24_neo_station_followup_report.md)

Same per-station discovery / follow-up / precovery partition as the companion
report, with four corrected-V-magnitude statistics added per category. The
unique-object / observation / tracklet counts are **identical** to the
companion report (verified — same query logic, V columns bolted on).

---

## Results — counts + corrected-V statistics

`n_mag` = observations with a usable magnitude (the V stats are computed over
these); `V_min` = brightest; `V_med` = median; `V_med+MAD` = median +
1.4826·MAD; `V_p95` = 95th percentile (faint-end depth proxy). All V values are
MPC band-corrected (see below).

| Station | Category | Unique NEOs | Obs | Tracklets | n_mag | V_min | V_med | V_med+MAD | V_p95 |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **703** | discoveries | 207 | — | — | 653 | 16.21 | 18.89 | 19.65 | 20.03 |
| **703** | follow-up   | 841 | 16,107 | 4,201 | 15,127 | 10.85 | 18.55 | 19.56 | 20.08 |
| **703** | precovery   | 61 | 151 | 63 | 129 | 16.35 | 19.56 | 20.43 | 20.79 |
| **G96** | discoveries | 614 | — | — | 2,092 | 17.94 | 20.80 | 21.50 | 21.91 |
| **G96** | follow-up   | 1,861 | 16,545 | 4,248 | 15,465 | 11.83 | 20.37 | 21.42 | 21.82 |
| **G96** | precovery   | 172 | 494 | 196 | 425 | 19.02 | 21.43 | 22.10 | 22.49 |
| **V00** | discoveries | 366 | — | — | 1,217 | 19.12 | 22.07 | 22.69 | 23.03 |
| **V00** | follow-up   | 716 | 3,470 | 882 | 3,196 | 15.30 | 21.78 | 22.79 | 23.12 |
| **V00** | precovery   | 38 | 88 | 39 | 62 | 19.20 | 22.58 | 23.58 | 23.96 |
| **I52** | follow-up   | 2,286 | 20,717 | 5,693 | 18,768 | 14.38 | 20.67 | 21.69 | 22.03 |
| **I52** | precovery   | 1 | 3 | 1 | 2 | 20.98 | 20.98 | 20.98 | 20.98 |
| **V06** | follow-up   | 692 | 3,817 | 1,089 | 3,529 | 17.48 | 22.17 | 22.61 | 23.01 |

The depth ordering is the expected one: 703 (Schmidt) brightest, G96
(Mt. Lemmon 1.5 m) fainter, V00 (Bok 90″) faintest; the dedicated follow-up
scopes I52/V06 reach to V ≈ 22–23 at the 95th percentile. I52's precovery row
rests on a single object (2 magnitudes), so its V statistics are not
meaningful.

---

## Methodology (V-magnitude specifics)

Everything about the NEO set, designation matching, the discovery pivot, and
the window is identical to the companion report. The V-magnitude additions:

- **Band → V correction (MPC standard).** `V_corr = mag + offset(band)`, using
  the offsets from
  [`minorplanetcenter.net/iau/info/BandConversion.txt`](https://minorplanetcenter.net/iau/info/BandConversion.txt)
  — the same `CASE` expression already used in `sql/discovery_tracklets.sql`
  (e.g. V/v 0.0, B −0.8, R +0.4, g −0.35, r +0.14, w −0.13, o +0.33, G +0.28,
  blank band treated as B = −0.8, unknown bands assumed V = 0.0).
- **Statistics.** `V_min` = `MIN`; `V_med` = `percentile_cont(0.5)`;
  `V_med+MAD` = `V_med + 1.4826 · median(|V − V_med|)` (the robust-σ
  convention, matching the depth statistic in the dashboard's Follow-up
  Comparison tab); `V_p95` = `percentile_cont(0.95)`.
- **Which observations feed the V stats.**
  - *discoveries* → the discovery-tracklet observations (all obs sharing the
    discovery `trkid`) of objects the station discovered in the window — so
    `n_mag` exceeds the discovery object count (multiple frames per tracklet).
  - *follow-up* / *precovery* → that bucket's in-window observations.
- **NULL magnitudes** are excluded from the V statistics only; they still count
  in the unique / obs / tracklet tallies (hence `n_mag` ≤ obs).

### Run cost

40.8 s on Gizmo (the `obs_sbn_neo` matview was warm in cache from the earlier
companion-report run; a cold run is ~10 min). No scan of the raw 526M-row
`obs_sbn`.
