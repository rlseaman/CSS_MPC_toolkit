# What the DOU / orbit-update stream reveals about MPC logistics

**Author:** Rob Seaman (with Claude)
**Date:** 2026-06-27
**Sources:** a live DOU (MPEC 2026-M118) parsed directly, plus `mpc_orbits`
(`epoch_mjd`, `updated_at`) on the Gizmo replica.

Investigation prompted by: can we infer MPC's orbit-processing logistics —
the "standard epoch", the "200-day" quantities, the processing cadence — from
the daily orbit-update stream? Yes, cleanly.

## The DOU itself (MPEC 2026-M118, 2026 June 27)

- **23,750 orbit-element lines** (not ~2,500 — an earlier model summary
  under-counted), in 1-line MPCORB format: `desig H G epoch M peri node incl
  e a opp flag`. Trivially parseable (fixed/whitespace columns; q derivable as
  `a(1−e)`). **No Earth MOID** in the published elements.
- **93% numbered + 7% multi-opposition provisional** — essentially all
  main-belt. NEOs are not in this batch (they flow through other MPECs).
- Plus a small "New identifications" (linkage) section.
- **Every object carries the same epoch `K2669` = MJD 61200 = 2026-06-09.**

## 1. The "standard epoch" is MJD multiples of 200, spaced exactly 200 days

`epoch_mjd` across the 1.56 M-row catalog clusters on exact 200-MJD grid points,
each cluster exactly 200 days from the next:

| epoch_mjd | date       | objects   | % |
|----------:|------------|----------:|----:|
| **61200** | 2026-06-09 | 180,590   | 11.6 |  ← current standard epoch (= the DOU's K2669)
| 61000     | 2025-11-21 | 722,364   | 46.4 |  ← prior epoch (the bulk)
| 60800     | 2025-05-05 | 214,944   | 13.8 |
| 60600     | 2024-10-17 | 128,271   | 8.2 |
| 60400     | 2024-03-31 | 85,053    | 5.5 |
| …200-day steps back to 2020… | | | |

The spacing is dead-on 200 days at every step. So MPC integrates every orbit to
a **common osculation epoch chosen at MJD ≡ 0 (mod 200)**, advancing every
200 days. The current one (61200) took effect ~2026-06-09.

**Note — two different "200 days":** the *standard-epoch spacing* is 200 days;
the observational *apparition window* is also 200 days (cf. `APPARITION_SQL`).
Same number, distinct quantities — a likely source of community conflation.
`epoch_mjd` proves the epoch one.

## 2. Processing cadence: daily, governed by the 200-day epoch cycle

Every fresh fit is stamped with the *current* standard epoch — of the last
7 days' updates, **116,297 → 61200** and only **19 → the old epoch**. So a
re-fit = "re-integrate to the current standard epoch."

Daily `updated_at` volume shows the rhythm: low (hundreds–few thousand/day)
through early June, then a sustained **10–26 K/day** right after the June 9
epoch switch — a **migration campaign** triggered by the epoch advancing. No
clean monthly/bimonthly batch, and no weekend pause (Sat 2026-06-27 was the
busiest at 26,030). The DOU is simply the daily visible increment of this.

| trailing window | distinct objects re-fit |
|---|--:|
| 7 days | 116,316 |
| 30 days | 219,584 |
| 60 days | 291,380 |
| 90 days | 369,366 |
| (catalog) | 1,558,491 |

## 3. The backlog is structural — and it *is* the "scattershot" state

18 days into epoch 61200, only 11.6% of the catalog is migrated; 46% still sits
at the prior epoch, with a 200-day-stepped tail back to 2020. At ~370 K objects
per 90 days, migrating all 1.56 M takes **longer than the 200-day cycle** — so a
fresh backlog is guaranteed every epoch. These stale-epoch objects are the same
ones missing `a` / `orbit_type_int` / `earth_moid` (see
`docs/2026-06-25_mpc_orbits_state.md` and `memory/mpc_orbits_is_scattershot.md`):
the epoch lens and the data-completeness lens show the same un-refit population.

## Implications for the toolkit

- **For the Daily Orbit News MBA stream** (see
  `docs/2026-06-25_daily_orbit_news_design.md`): the DOU is the right
  event-driven source for the slow-cadence numbered population. The orbit lines
  give Keplerian elements + H (q derivable); **MOID is absent**, so PHA logic
  can't come from the DOU directly. A *heavyweight* parser could **compute MOIDs
  from the orbits themselves** (numerically minimize the Earth–asteroid orbit
  distance) — opening PHA-style events for the MBA stream and a cross-check
  against `mpc_orbits.earth_moid` for NEOs.
- **A standard-epoch / migration-progress monitor** is now trivially derivable
  from `epoch_mjd`: "% of catalog migrated to the current standard epoch", and
  the per-epoch backlog histogram, as a one-query health/logistics panel.
- **The parser is proven** — the DOU's 1-line format parses with whitespace
  fields; a real ingester is a small module, no special tooling.
