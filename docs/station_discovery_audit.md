# Station Discovery Profile Audit

**Date:** 2026-03-29
**Status:** Initial findings

## Method

Query A (`sql/station_discovery_profile.sql`) computes per-station
discovery counts from the mpc_sbn database:
- All-class discoveries (any object with disc='*')
- NEO discoveries using `q <= 1.30` definition
- NEO discoveries using `orbit_type_int IN (0,1,2,3)`
- First and last NEO discovery year

Results are cross-matched against the MPC YearlyBreakdown page
(scraped via `scripts/yearly_breakdown.py`).

Query ran in 66 seconds using the `disc='*'` partial index.

## Summary

| Metric | DB (q<=1.3) | YB page | Diff |
|---|---|---|---|
| Total NEO discoveries | 41,516 | 40,986 | +530 |
| Stations with NEO disc | 192 | 185 | +7 |
| Stations in both | 182 | — | — |
| Exact matches | 119 | — | 65% of shared |
| In YB only | — | 3 | all with 1 NEO |
| In DB only | 10 | — | all with 1–2 NEOs |

## orbit_type_int is unsuitable for NEO selection

The `orbit_type_int IN (0,1,2,3)` definition finds only 9,362
discoveries — 77% of NEOs lack the correct class code due to the
35% NULL rate in this column.  The `q <= 1.30` filter is the
correct approach.

## Largest discrepancies (DB vs YB)

| Station | DB | YB | Diff | % over | Notes |
|---|---|---|---|---|---|
| C51 (NEOWISE) | 481 | 348 | +133 | +38% | Largest outlier |
| G96 (Mt. Lemmon) | 13,153 | 13,092 | +61 | +0.5% | |
| G45 (SST) | 193 | 140 | +53 | +38% | |
| F51 (Pan-STARRS 1) | 9,050 | 9,002 | +48 | +0.5% | |
| W84 (DECam) | 371 | 330 | +41 | +12% | |
| X05 (Rubin) | 39 | 9 | +30 | +333% | Commissioning objects? |
| 704 (LINEAR) | 2,477 | 2,501 | **-24** | -1.0% | DB undercounts |
| 703 (Catalina) | 3,886 | 3,896 | **-10** | -0.3% | DB undercounts |

**Pattern:** The DB almost always overcounts.  The few undercounts
(704, 703, E12, J75, 608, U68) are small and may reflect objects
whose discovery station changed via identification/linking.

**C51 and G45** both show +38% excess.  C51 likely includes objects
later attributed to ground-based precovery, or objects whose orbits
refined past q=1.3.  G45 (Space Surveillance Telescope) may have
similar issues with how discoveries are credited.

**X05 (Rubin)** at 39 vs 9 is the largest relative discrepancy.
The DB may include commissioning/test observations that the MPC
page doesn't credit as survey discoveries.

## Stations in YB but not in DB as NEO discoverers

3 stations, each with 1 NEO on the YB page:

| Station | YB NEOs | DB all-class disc | Notes |
|---|---|---|---|
| 071 (NAO Rozhen) | 1 | 289 | Active discoverer, NEO orbit likely refined past q=1.3 |
| C41 (MASTER-II Kislovodsk) | 1 | 13 | |
| 391 (Sendai) | 1 | 45 | |

These are likely objects that were NEOs when the YB page was updated
but whose orbits have since refined to q > 1.30 in mpc_orbits.

## Stations in DB but not in YB

10 stations with 1–2 NEO discoveries in the DB:

| Station | DB NEOs | DB all disc | First | Last | Notes |
|---|---|---|---|---|---|
| 872 | 2 | 21 | 2018 | 2020 | |
| 249 | 2 | 4 | 2023 | 2025 | |
| I47 | 1 | 4 | 2024 | 2024 | Recent |
| 711 | 1 | 551 | 1951 | 1951 | Historical (McDonald) |
| Z17 | 1 | 1 | 2025 | 2025 | Recent |
| 323 | 1 | 126 | 1970 | 1970 | Historical |
| 897 | 1 | 74 | 1989 | 1989 | |
| 468 | 1 | 22 | 1998 | 1998 | |
| 754 | 1 | 149 | 1934 | 1934 | Historical (Heidelberg) |
| L32 | 1 | 1 | 2018 | 2018 | |

Likely explanations: boundary objects with q near 1.3 that the MPC
curated list excludes, historical discoveries credited differently,
or objects whose classification changed.

## Exact matches (119 stations)

65% of shared stations have identical NEO discovery counts between
the DB and the YB page.  Includes major surveys:

- 644 (NEAT): 298
- 699 (LONEOS): 289 — confirmed exact in later run
- 950 (La Palma): 12
- T14 (CFHT): 5
- Many single-discovery stations

## Historical note

Station 675 (Palomar Mountain) shows first_neo_year = 1949 in the
DB, while the YB page shows "<1971".  The database captures the
full historical record predating the YB page's 1971 cutoff.

## Query B: Observation Profile (2026-03-29)

Query B (`sql/station_obs_profile.sql`) performs a full sequential
scan of obs_sbn (~533M rows) to compute per-station observation
counts.  Only the minimal aggregation (COUNT, MIN, MAX) succeeded
within the 90-minute statement timeout; COUNT(DISTINCT ...) for
tracklets and objects was too expensive for a single pass.

Results saved to `app/.station_obs_profile.csv`.
Completed in 10 minutes.  2,633 stations.

### Key findings from the combined profile

| Station | Obs | All Disc | NEO Disc | Disc/Obs | Notes |
|---|---|---|---|---|---|
| G96 | 83.1M | 324K | 13,153 | 0.39% | |
| F51 | 83.5M | 506K | 9,050 | 0.61% | Most all-class disc |
| 691 | 14.6M | 285K | 861 | 1.96% | High disc rate (main belt) |
| U68 | 11.5K | 333 | 331 | 2.9% | 99.4% of disc are NEOs |
| T08 | 32.5M | 737 | 570 | 0.00% | ATLAS: survey obs, few credited disc |
| T05 | 34.1M | 674 | 470 | 0.00% | ATLAS: same pattern |
| P07 | 10.1M | 68 | 68 | 0.00% | SST: 100% of disc are NEOs |
| L51 | 4.0K | 211 | 153 | 5.3% | Very efficient |
| 381 | 9.0K | 1,783 | 57 | 19.8% | Most targeted |
| 675 | 205K | 14,304 | 148 | 7.0% | Historical Palomar |

**Discovery efficiency patterns:**
- ATLAS (T05, T08, W68, M22): tens of millions of observations but
  fewer than 1,000 credited discoveries each.  ATLAS functions as
  a wide-field survey; most observations track known objects.
- U68 (SynTrack): extremely NEO-focused — 99.4% of discoveries are
  NEOs, from only 11K total observations.
- 381 (Tokyo-Kiso): highest discovery rate at 19.8%, reflecting a
  highly targeted search program.

### Statement timeout issues

The full scan with COUNT(DISTINCT trkid) and COUNT(DISTINCT permid/
provid) exceeded the 90-minute statement timeout on the 526M-row
table.  The minimal version (COUNT, MIN, MAX only) completed in
10 minutes.  For distinct counts, future approaches:
- Run per-station queries for just the ~192 NEO-discovering stations
- Use the stn index to limit scan scope
- Run during low-load periods on the database server

## Next steps

- Investigate C51 excess at object level: which 133 objects are in
  the DB but not credited to C51 on the YB page?
- Investigate X05 excess: are these commissioning objects?
- Run targeted distinct-count queries for NEO-discovering stations
- Cross-match DB NEO list against NEA.txt object-by-object to
  identify boundary cases
