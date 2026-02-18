# Data Quality Findings: mpc_orbits (2026-02-10)

Observations from `notebooks/03_data_quality.ipynb` run against
`mpc_sbn` on the local replica via `claude_ro`.  These are raw observations,
not recommendations — interpretation depends on project goals.

## Row Count

- mpc_orbits: 1,515,621 rows (as queried; may change with MPC updates)

## NULL Rates (>30% NULL)

| Column | NULL % | NULL Count | Notes |
|--------|-------:|----------:|-------|
| orbit_type_int | 34.93% | 529,347 | No dynamical classification |
| a, period, mean_anomaly, mean_motion | 56.82% | 861,118 | Keplerian elements absent (COM-only orbits) |
| a_unc, period_unc, mean_anomaly_unc, mean_motion_unc | 56.82% | 861,118 | Same objects |
| arc_length_total, arc_length_sel | 56.82% | 861,118 | Same objects |
| earth_moid | 69.89% | 1,059,227 | Only ~30% have Earth MOID |
| not_normalized_rms | 91.32% | ~1.38M | Mostly unpopulated |
| yarkovsky, srp, a1-a3, dt + uncs | ~100% | ~1.51M | Non-grav params effectively empty |

The 56.82% NULL group is consistent: all are Keplerian elements or
derived quantities that are only populated when the orbit is stored
in Keplerian form (~43% of objects).  Cometary elements (q, e, i,
node, argperi, peri_time) are present for 100% of rows.

## orbit_type_int Gap Recovery

- 529,347 objects have NULL orbit_type_int
- All 529,347 have valid derived `a` (all are elliptical, e < 1)
- `classify_from_elements()` recovers 525,275 of 529,347 (99.2%)
- 4,072 remain unclassifiable by our boundary rules

Recovered distribution:
| Class | Count |
|-------|------:|
| Main Belt | 453,715 |
| Apollo | 18,676 |
| Mars-crossing | 17,477 |
| Hungaria | 11,404 |
| Amor | 11,172 |
| Still unclassified | 4,072 |
| Jupiter Trojan | 2,899 |
| Hilda | 2,757 |
| Aten | 2,571 |
| TNO | 2,451 |
| SDO | 1,472 |
| Centaur | 661 |
| Atira | 20 |

## Classification Agreement (DB vs element-based)

- 95.4% agreement on 100K sample (objects that DO have orbit_type_int)
- 4,648 disagreements in the sample
- Disagreements concentrated at class boundaries (expected — our rules
  use approximate boundaries, MPC may use different criteria)

## Cross-Column Consistency

### q vs a*(1-e)
- Mean residual: -3e-6 AU (effectively zero)
- Std: 6.5e-4 AU
- A few outliers up to ~0.08 AU — possibly objects with unusual orbit fits
- Median: exactly 0.0

### Flat H vs JSONB H
- **Perfect agreement**: 0 mismatches in 50,000 sampled rows
- The flat column is a faithful copy of the JSONB value

## Epoch Freshness

- Epoch year range: 1927 — 2026
- Distribution not captured here (see notebook plot)

## JSONB Key Presence (10K sample)

- Results are in the notebook — presence rates for 11 top-level keys
- Exact percentages vary by sample; see the saved plot

## Query Performance (for this notebook)

- NULL rate survey (50 columns): 10.1s
- Load 529K unclassified: 12.1s
- Server-side histograms: 0.7-1.2s each
- Total notebook execution: several minutes
