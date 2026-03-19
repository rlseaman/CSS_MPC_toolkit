# NEO Discovery Circumstances: Twilight, Lunar Phase, and Eclipse Analysis

**Date:** 2026-03-19
**Authors:** Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
**Dataset:** 44,217 NEO discovery tracklets from the MPC/SBN database

## 1. Introduction

This report examines the observing circumstances at the moment of
discovery for all known Near-Earth Objects in the MPC database.  We
classify each discovery by solar altitude (twilight state), compute
the angular separation from the Moon, and identify the rare cases
where a NEO was discovered during a lunar eclipse.

The analysis uses approximate solar and lunar ephemerides (~1 degree
accuracy) evaluated at the UTC time and geographic coordinates of
each discovery observation.  Observatory positions are taken from
the MPC `obscodes` table; lunar eclipse contact times are from
Fred Espenak's Six Millennium Catalog (EclipseWise.com).

## 2. Twilight Classification

Each discovery is classified by the Sun's altitude at the observer's
location at the time of the first discovery observation:

| Category | Sun altitude | Count | % |
|---|---|---|---|
| Nighttime | < -18 deg | 42,929 | 97.09 |
| Astronomical twilight | -18 deg to -12 deg | 617 | 1.40 |
| Space-based | N/A (satellite) | 662 | 1.50 |
| Unknown site | geocentric/roving | 4 | 0.01 |
| Nautical twilight | -12 deg to -6 deg | 3 | 0.01 |
| Daytime | > 0 deg | 2 | 0.005 |
| Civil twilight | -6 deg to 0 deg | 0 | 0 |

The overwhelming majority of NEO discoveries (97%) occur during full
astronomical darkness.  The 617 astronomical twilight discoveries
(1.4%) reflect the practice of beginning observations before the end
of evening twilight or continuing into morning twilight, particularly
at sites conducting dedicated NEO surveys.  No NEO has been discovered
during civil twilight from a ground-based site.

The 3 nautical twilight discoveries are:
- **1997 TD** (Haleakala-NEAT, sun alt -10.4 deg)
- **C/2021 D1** (Piszkesteto, Hungary, sun alt -11.9 deg)
- **2026 AC** (Mt. Lemmon, sun alt -11.2 deg)

The 2 "daytime" discoveries are both from station 500 (Geocentric),
a virtual reference point, not a physical observatory.

### Space-based discovery sites

| Code | Name | Discoveries |
|---|---|---|
| C51 | WISE/NEOWISE | 658 |
| 249 | SOHO | 2 |
| C55 | Kepler | 1 |
| C57 | TESS | 1 |

WISE/NEOWISE accounts for 99.4% of space-based NEO discoveries.
The SOHO, Kepler, and TESS detections are serendipitous.

## 3. Lunar Phase and NEO Discovery Rate

We computed the lunar phase at each discovery time using the mean
synodic month (29.5306 days) referenced to the full moon of
2000-01-21 04:40 UTC.

**Key findings:**
- Within +/-24h of full moon: **133 discoveries (0.30%)** --
  expected 6.8% if uniform.  This represents a **23x suppression**.
- Within +/-24h of new moon: **4,443 discoveries (10.0%)** --
  a 48% enhancement over the uniform expectation of 6.8%.
- Peak discovery rate: days +8 to +11 after full moon (2,400-2,500
  per bin), corresponding to waning gibbous through last quarter.

The lunar phase histogram shows a striking avoidance curve:

```
Days from full moon | Count
 -15 to -14        |  1652  ################################
 -14 to -13        |  2214  ############################################
 -13 to -12        |  2191  ###########################################
 -12 to -11        |  2126  ##########################################
 -11 to -10        |  2049  ########################################
 -10 to  -9        |  1893  #####################################
  -9 to  -8        |  1917  ######################################
  -8 to  -7        |  1673  #################################
  -7 to  -6        |  1481  #############################
  -6 to  -5        |  1247  ########################
  -5 to  -4        |   852  ################
  -4 to  -3        |   495  #########
  -3 to  -2        |   250  ####
  -2 to  -1        |   126  ##
  -1 to  +0        |    62  #
  +0 to  +1        |    71  #  <-- FULL MOON
  +1 to  +2        |    92  #
  +2 to  +3        |   187  ###
  +3 to  +4        |   535  ##########
  +4 to  +5        |  1098  #####################
  +5 to  +6        |  1684  #################################
  +6 to  +7        |  1990  #######################################
  +7 to  +8        |  2196  ###########################################
  +8 to  +9        |  2508  ##################################################
  +9 to +10        |  2466  #################################################
 +10 to +11        |  2489  #################################################
 +11 to +12        |  2410  ################################################
 +12 to +13        |  2316  ##############################################
 +13 to +14        |  2239  ############################################
 +14 to +15        |  1735  ##################################
```

The distribution is strongly asymmetric around full moon.  The
post-full recovery is markedly faster than the pre-full decline:
by day +5, discovery rates have already returned to 75% of peak,
while at day -5 they are only at 37%.  This reflects the Moon's
rising time: after full moon the Moon rises progressively later
each night, opening dark hours before moonrise; before full moon,
the Moon is already high during the early evening hours when most
survey operations begin.

### Lunar elongation

The angular separation between the Moon and the discovered NEO
ranges from 9.9 deg to 179.9 deg, with a median of 116.4 deg.

## 4. NEO Discoveries During Lunar Eclipses

We cross-referenced all 44,217 NEO discovery times against 87 lunar
eclipses from 1990 to 2027 (Fred Espenak, EclipseWise.com).  A
discovery is classified as occurring "during" an eclipse if the
observation time falls between the first and last penumbral contacts
(P1-P4) and the Moon is above the observer's horizon.  The "Eclipse
phase" column further specifies the deepest phase at the instant of
observation: "Penumbral" (between P1-P4 but outside U1-U4), "Partial"
(between first and last umbral contacts U1-U4), or "Total" (between
U2-U3, while the Moon is fully within Earth's umbral shadow).

**Five NEOs were discovered during a lunar eclipse:**

| Designation | Date | Local time | Eclipse phase | Moon sep | V mag | H | MOID (AU) | Site |
|---|---|---|---|---|---|---|---|---|
| 2015 GF | 2015-04-04 | 02:08 | Partial | 77 deg | 20.9 | 20.5 | 0.197 | F51 Pan-STARRS |
| 2021 KK3 | 2021-05-26 | 00:32 | Partial | 37 deg | 22.0 | 22.3 | 0.027 | F51 Pan-STARRS |
| 2021 KM2 | 2021-05-26 | 00:31 | Partial | 38 deg | 21.7 | 22.0 | 0.254 | F51 Pan-STARRS |
| 2022 VW3 | 2022-11-08 | 01:42 | Penumbral | 50 deg | 19.4 | 24.1 | 0.047 | G96 Mt. Lemmon |
| 2026 EY3 | 2026-03-03 | 04:04 | Total | 23 deg | 21.6 | 19.7 | 0.061 | G96 Mt. Lemmon |

Notes:
- **V mag** is the median band-corrected apparent V magnitude of the
  discovery tracklet (from NEO_discovery_tracklets.csv).
- **H** and **MOID** are from JPL's Small-Body Database (SBDB API).
- **Moon sep** is the angular separation between the NEO and the Moon
  at discovery.
- **Local time** is the approximate local time at the observatory
  (UTC + longitude/15).

### Discussion

**2021 KK3 and 2021 KM2** were discovered one minute apart during the
same partial eclipse, at only 37-38 deg from the eclipsed Moon.
These small (H ~ 22) objects were faint (V ~ 22) and close to the
survey's limiting magnitude.

**2022 VW3** is notable for its bright apparent magnitude (V = 19.4)
despite being intrinsically very faint (H = 24.1, roughly 30-60
meters).  It was detected during the penumbral phase, when the sky
background reduction from the eclipse would have been minimal.

**2026 EY3** is the most remarkable: discovered during **totality** on
2026-03-03 at Mt. Lemmon, only 23 deg from the eclipsed Moon.  At
H = 19.7 (roughly 300-500 meters), it is the largest of the five
and has a relatively close Earth MOID of 0.061 AU.  This discovery
occurred just 16 days before this analysis.

### Eclipse nights in context

To verify that "during" means during the actual eclipse and not
merely on the same night, we checked all NEO discoveries within
+/-12 hours of each eclipse's greatest phase.  Ten eclipse nights
had at least one NEO discovery nearby in time:

| Eclipse date | Type | P1-P4 (UTC) | During | Same night, outside |
|---|---|---|---|---|
| 2010-06-26 | P | 08:57-14:20 | 0 | 2 (WISE) |
| 2010-12-21 | T | 05:29-11:05 | 0 | 1 (WISE) |
| 2015-04-04 | T | 09:01-15:00 | 1 | 0 |
| 2017-08-07 | P | 15:50-20:51 | 0 | 2 (Pan-STARRS) |
| 2021-05-26 | T | 08:47-13:50 | 2 | 0 |
| 2022-11-08 | T | 08:02-13:57 | 1 | 0 |
| 2025-03-14 | T | 03:57-10:01 | 0 | 1 (ATLAS) |
| 2025-09-07 | T | 15:28-20:55 | 0 | 2 (ZTF) |
| 2026-03-03 | T | 08:44-14:23 | 1 | 0 |

All five eclipse discoveries fall strictly within the P1-P4 contact
window.  The eight "same night, outside" discoveries were observed
hours before or after the eclipse and are simply ordinary (rare)
full-moon-night detections.

One near-miss: **2025 EL4** (ATLAS-Sutherland, W68) was discovered
at 03:44 UTC on 2025-03-14, just 13 minutes before first penumbral
contact (P1 = 03:57).

The reduced sky brightness during a lunar eclipse -- particularly
during totality and the partial phases -- may improve the detection
of faint objects in the Moon's vicinity.  However, the small sample
(5 out of 44,217) makes it impossible to draw statistical conclusions
about whether eclipses enhance discovery rates.  What is clear is
that modern survey telescopes continue productive operations during
eclipses rather than treating them as lost time.

## 5. Data Products

This analysis produced the following artifacts:

- **`lib/solar.py`** -- Solar position and twilight classification
  (vectorized numpy, VSOP87 approximation)
- **`lib/lunar.py`** -- Lunar ephemeris (~1 deg Meeus truncated),
  elongation, and eclipse catalog (87 eclipses, 1990-2027)
- **`scripts/compute_circumstances.py`** -- Enrichment script
  producing `NEO_discovery_tracklets_extra_DDMonYY.csv`
- **`NEO_discovery_tracklets_extra_19Mar26.csv`** -- 44,217 rows,
  17 columns (12 original + 5 circumstance columns)

New columns in the extra CSV:
- `sun_alt_deg` -- solar altitude at discovery (degrees)
- `twilight_class` -- Space-based / Nighttime / Astronomical
  twilight / Nautical twilight / Civil twilight / Daytime /
  Unknown site
- `lunar_elong_deg` -- angular separation from Moon (degrees)
- `eclipse_class` -- Penumbral / Partial / Total eclipse (blank
  if none)
- `eclipse_date` -- ISO date of the eclipse

## 6. Bug Fix: JPL SBDB MOID Retrieval

During this analysis, a bug was identified in `lib/api_clients.py`:
`fetch_sbdb()` looked for Earth MOID in the orbital elements array,
but the SBDB API returns it at the top level of the orbit object
(`orbit.moid`).  This caused MOID to be None for all SBDB queries.
The fix reads from `orbit.moid` (falling back to elements for
backward compatibility).  This affects the MPEC Browser's object
detail panel when displaying SBDB-sourced data.

## References

- Espenak, F. "Six Millennium Catalog of Lunar Eclipses."
  EclipseWise.com.
- Meeus, J. "Astronomical Algorithms," 2nd ed. Willmann-Bell, 1998.
  Chapter 47 (lunar position).
- Nesvorny, D. et al. "NEOMOD3: Debiased Near-Earth Object Model."
  Icarus 411, 2024.
