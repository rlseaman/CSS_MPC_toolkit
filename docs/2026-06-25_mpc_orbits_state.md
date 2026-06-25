# mpc_orbits — State of the table, 2026-06-25

**Author:** Rob Seaman (with Claude)
**Replica surveyed:** Gizmo (PG 18.3). Measured 2026-06-24/25 UT.
**Updates:** [`docs/2026-05-14_mpc_orbits_state.md`](./2026-05-14_mpc_orbits_state.md)

## Question

The 2026-05-14 audit ended with a prediction: *if MPC re-fits the frozen
August-2025 cohort, table-wide `a` should jump toward 100%, `orbit_type_int`
toward 99%, `earth_moid` toward ~98%. A simple re-run of the queries will tell.*
Six weeks on — did it?

**Answer in one line:** No. The bulk re-fit has **not** happened. The legacy
cohort is draining only slowly (~10 K rows/week), so the table-wide populations
have crept up a few points rather than jumped, and the NEO subset is essentially
unchanged.

## Headline (Gizmo, 2026-06-24/25 UT)

| Metric | 2026-05-14 | 2026-06-25 |
|---|--:|--:|
| Total rows | 1,548,437 | 1,558,527 |
| Min `updated_at` | 2025-08-29 15:43 | **2025-08-29 15:43** (unchanged) |
| Max `updated_at` | 2026-05-15 01:16 | 2026-06-24 21:48 |
| Rows still stamped 2025-08-29 | 699,013 | **640,420** |

The frozen August snapshot lost ~58.6 K rows in 41 days (~1,430/day ≈ 10 K/week).
At that attrition rate, clearing the remaining 640 K (**41% of the table**) takes
**~15 months** — i.e. this is incremental re-fitting of objects that happen to
get new astrometry, not a deliberate bulk reprocessing.

## Top-level column population (% of all rows)

| Column | 2026-05-14 | 2026-06-25 | Δ |
|---|--:|--:|--:|
| `mpc_orb_jsonb`, `h`, `q`, `e` | 99.83 | 99.83 | — |
| `orbit_type_int` | 69.31 | **70.34** | +1.0 |
| `a` | 50.51 | **54.73** | +4.2 |
| `period` | ~49 | **53.06** | +4 |
| `mean_anomaly` | — | 54.73 | — |
| `earth_moid` | 37.03 | **43.82** | +6.8 |
| `u_param` | 99.83 | 99.68 | — |

## Temporal completeness by `updated_at` month

```
month       rows     %otype  %a     %emoid  %h
2025-08   641,892    29.7    2.4    50.1    100.0   <- legacy snapshot, untouched
2025-09    51,554   100.0   61.0    41.5    100.0
2025-10    47,248   100.0   67.2    35.3    100.0
2025-11    65,205   100.0   88.4    11.2    100.0
2025-12   100,142   100.0   84.6    13.5    100.0
2026-01    82,523   100.0   89.7    10.6    100.0
2026-02   154,316   100.0   98.1    11.7    100.0
2026-03    59,020   100.0   90.7     8.8    100.0
2026-04    85,593    94.2   96.4    35.5     96.9
2026-05   102,196    97.9  100.0    82.3    100.0
2026-06   167,536    97.8  100.0    92.7    100.0
```

Fresh fits stay excellent: from May 2026 on, `a` is 100% and `earth_moid`
82–93%. The whole drag on the table-wide averages is the single 2025-08 row.

## NEO subset is still disproportionately stale (q ≤ 1.3, e < 1)

| Cohort | 2026-05-14 rows | 2026-06-25 rows | %otype | %a | %emoid |
|---|--:|--:|--:|--:|--:|
| Aug 2025 legacy | 34,228 | 33,124 | 6.7 | 0.3 | 36.1 |
| Sep 2025 + | 7,835 | 9,169 | 98.5 | 72.1 | 60.2 |

**78% of NEOs are still legacy** (was 81%), and within that cohort `a` is
present for just 0.3% of rows. NEOs remain the worst-off slice of the table.

## JSONB still canonical; projection slightly leakier

| top-level | jsonb | rows |
|---|---|--:|
| populated | populated | 1,095,375 |
| NULL | populated | **8,136** (was 4,158) |
| NULL | NULL | 451,088 |

No reverse mismatches (no row where the top-level column is set but JSONB is
NULL) — JSONB remains the authority, top-level a derived projection. The
JSONB-only count doubling to 8,136 means the projection is a touch leakier than
in May; `mpc_orb_jsonb->'categorization'->>'orbit_type_int'` remains the more
complete source.

## Wider schema snapshot (Gizmo, same session)

- `obs_sbn`: **~540 M rows / 286 GB** (was quoted 526 M / 239 GB — `CLAUDE.md`
  updated this session).
- Matviews all populated: `obs_sbn_neo` 5.06 M / 1.15 GB, `obs_summary_all`
  1.63 M / 193 MB, `obs_summary` 42 K / 5 MB.
- Replication **live**: latest `obs_sbn` row created within the hour of
  measurement; `obstime` current to the same day.
- Nightly NEO-consensus pipeline ran clean (6/6 sources `ok`, 0 unresolved,
  ~41.9–42.0 K rows each).

## What this means for the toolkit

Unchanged from the May audit — **keep every workaround**: `lib/orbits.py`
`DERIVED_COLUMNS`, `lib/orbit_classes.py` `classify_from_elements()`, and the
NEA.txt H override. None can be retired until MPC re-fits the August cohort, and
at 10 K/week that is not imminent. "Scattershot" stays the correct working
assumption, especially for any NEO-only consumer not backstopped by NEA.txt +
the consensus catalogs.

## Reproducing

Same queries as the 2026-05-14 doc, run on Gizmo via
`/opt/homebrew/bin/psql -h /tmp -U claude_ro mpc_sbn`.

## See also

- `docs/2026-05-14_mpc_orbits_state.md` (the prior audit this updates)
- `memory/mpc_orbits_is_scattershot.md` (refreshed with this measurement)
- `docs/2026-06-25_daily_orbit_news_design.md` (a use for `updated_at` churn:
  the Daily Orbit News diff)
