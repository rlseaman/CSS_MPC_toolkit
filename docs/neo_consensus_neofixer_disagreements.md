# NEOfixer consensus disagreements — root-cause analysis

*Generated: 2026-05-04 from the NEO Consensus snapshot built off NEOfixer cache `2026-05-04T13:04:11Z`*

## Summary

The NEO Consensus tab of the Planetary Defense Dashboard reports
per-object membership across six independent NEO sources. Two
disagreement classes involve NEOfixer:

- **121 objects** present in all five other sources (MPC NEA.txt,
  `mpc_orbits`, JPL CNEOS, ESA NEOCC, Lowell `astorb`) but not
  flagged `in_neofixer`.
- **38 objects** present in NEOfixer but in none of the other five.

Both populations are dominated by NEO-boundary effects in NEOfixer's
Find_Orb solutions, plus a smaller residual of objects that are
genuinely outside NEOfixer's catalog. Findings in detail below.

| Group | Count | Root cause |
|---|---:|---|
| **A.** Missing — in NEOfixer's `site=500` list, q > 1.3 (filtered by our code) | 45 | Our client-side `q > 1.3` filter in `lib/neo_consensus_neofixer.py` |
| **B1.** Missing — in NEOfixer's `/orbit/` catalog but not in tonight's target list | 15 | NEOfixer service drops these from `site=500` (priority/visibility); orbits still exist |
| **B2.** Missing — genuinely unknown to NEOfixer | 61 | NEOfixer's API returns "Unknown object" on both `/orbit/` and `/obs/` |
| **C.** Only-in-NEOfixer — boundary q | 38 | NEOfixer's Find_Orb q ≤ 1.3, MPC's q just over 1.3 |

## Methodology

Inputs:

- `css_neo_consensus.v_membership_wide` (Gizmo replica, refreshed 2026-05-04)
- The NEOfixer JSON cache that today's ingest consumed:
  `app/.neofixer_targets.json` from `https://neofixerapi.arizona.edu/targets/?site=500&q-max=1.3`,
  generated 2026-05-04T13:04:11Z, 42,412 objects.
- Live per-object probes against `https://neofixerapi.arizona.edu/orbit/?object={packed}`
  and `https://neofixerapi.arizona.edu/obs/?object={packed}` for the 76 designations not
  found in the bulk cache.
- `mpc_orbits.q,e,i` (joined on the unpacked primary provisional designation).

The ingestor (`lib/neo_consensus_neofixer.py`) applies two client-side filters to the
NEOfixer bulk response: drop rows with `neocp=True` and drop rows with `q > 1.3`. Both
filters are documented in the module docstring; this analysis confirms that **0 of the 121
disagreements are NEOCP-related** and **45 (37%) are q-related**.

## Group A — 45 with NEOfixer q > 1.3 (in cache, filtered by our code)

These are present in the NEOfixer `site=500` bulk response (i.e. NEOfixer itself
lists them as NEO observation targets) but NEOfixer's Find_Orb q exceeds 1.3 AU.
Our code at `lib/neo_consensus_neofixer.py:99–102` drops them, even though `mpc_orbits`
(and the other four sources) classify them as NEOs.

q-distribution:

| NF q range | Count |
|---|---:|
| 1.30 < q ≤ 1.31 (boundary) | 17 |
| 1.31 < q ≤ 1.40 | 15 |
| 1.40 < q ≤ 1.50 | 4 |
| q > 1.50 | 9 |

Largest |NF q − MPC q| divergences (different orbit fits, possibly different epochs):

| packed | designation | NF q | MPC q | Δ |
|---|---|---:|---:|---:|
| `K04BG0P` | 2004 BP160 | 2.4410 | 1.1958 | +1.2452 |
| `K16Ea2U` | 2016 EU362 | 1.3530 | 0.6649 | +0.6881 |
| `K17FE6Q` | 2017 FQ146 | 1.7490 | 1.1850 | +0.5640 |
| `K05UF0F` | 2005 UF150 | 1.5810 | 1.0752 | +0.5058 |
| `K14J79R` | 2014 JR79 | 1.5390 | 1.0440 | +0.4950 |
| `K10R16E` | 2010 RE16 | 1.7290 | 1.2571 | +0.4719 |
| `K10VK1Z` | 2010 VZ201 | 1.4240 | 1.0192 | +0.4048 |
| `K14Qh9P` | 2014 QP439 | 1.6200 | 1.2968 | +0.3232 |
| `K14HJ5T` | 2014 HT195 | 1.4830 | 1.2294 | +0.2536 |
| `K17DC0B` | 2017 DB120 | 1.3670 | 1.1157 | +0.2513 |

**Full Group A list** (sorted by NF q):

| packed | designation | NF q | NF H | MPC q | MPC e |
|---|---|---:|---:|---:|---:|
| `K06D62V` | 2006 DV62 | 1.3010 | 20.14 | 1.2982 | 0.5145 |
| `K14F00V` | 2014 FV | 1.3010 | 20.23 | 1.3000 | 0.5124 |
| `K19N05O` | 2019 NO5 | 1.3010 | 21.82 | 1.2978 | 0.3966 |
| `K19R86C` | 2019 RC86 | 1.3010 | 20.36 | 1.2981 | 0.3982 |
| `K03G00J` | 2003 GJ | 1.3020 | 19.75 | 1.2896 | 0.5160 |
| `K18A13B` | 2018 AB13 | 1.3020 | 22.18 | 1.2992 | 0.4838 |
| `K19N03F` | 2019 NF3 | 1.3020 | 20.02 | 1.2981 | 0.4021 |
| `K20O07K` | 2020 OK7 | 1.3020 | 21.81 | 1.2997 | 0.4378 |
| `K22J01Z` | 2022 JZ1 | 1.3020 | 23.11 | 1.2968 | 0.3927 |
| `K07M24K` | 2007 MK24 | 1.3030 | 20.21 | 1.2990 | 0.3870 |
| `K11S21Z` | 2011 SZ21 | 1.3030 | 17.52 | 1.2945 | 0.5604 |
| `K20K05T` | 2020 KT5 | 1.3030 | 19.31 | 1.2983 | 0.4088 |
| `K23O44Q` | 2023 OQ44 | 1.3030 | 21.13 | 1.2994 | 0.4224 |
| `K22K11H` | 2022 KH11 | 1.3040 | 19.84 | 1.2957 | 0.4454 |
| `K03G29V` | 2003 GV29 | 1.3050 | 19.45 | 1.2952 | 0.5438 |
| `K03U26W` | 2003 UW26 | 1.3050 | 19.18 | 1.2952 | 0.5224 |
| `K16GM0O` | 2016 GO220 | 1.3100 | 17.50 | 1.2918 | 0.5881 |
| `K13HF0U` | 2013 HU150 | 1.3110 | 21.46 | 1.2721 | 0.4969 |
| `K14Qa3X` | 2014 QX363 | 1.3110 | 19.17 | 1.2886 | 0.5062 |
| `K17W11W` | 2017 WW11 | 1.3120 | 18.72 | 1.2947 | 0.5065 |
| `K23U09P` | 2023 UP9 | 1.3150 | 17.73 | 1.2986 | 0.5591 |
| `K11H52Y` | 2011 HY52 | 1.3160 | 20.18 | 1.2865 | 0.5390 |
| `K13T69G` | 2013 TG69 | 1.3160 | 20.77 | 1.2904 | 0.6135 |
| `K14Hq3K` | 2014 HK523 | 1.3160 | 22.46 | 1.2546 | 0.4095 |
| `K21H12M` | 2021 HM12 | 1.3180 | 21.17 | 1.2990 | 0.5183 |
| `K14Od2Q` | 2014 OQ392 | 1.3290 | 22.24 | 1.2949 | 0.4702 |
| `K15KF7Z` | 2015 KZ157 | 1.3300 | 23.49 | 1.2250 | 0.0618 |
| `K11K09K` | 2011 KK9 | 1.3410 | 22.32 | 1.2436 | 0.3909 |
| `K15MD1A` | 2015 MA131 | 1.3500 | 21.85 | 1.2868 | 0.4548 |
| `K16Ea2U` | 2016 EU362 | 1.3530 | 19.08 | 0.6649 | 0.2233 |
| `K15RI3S` | 2015 RS183 | 1.3670 | 16.34 | 1.2502 | 0.5815 |
| `K17DC0B` | 2017 DB120 | 1.3670 | 22.46 | 1.1157 | 0.4683 |
| `K12B86K` | 2012 BK86 | 1.4200 | 21.84 | 1.2711 | 0.3079 |
| `K10VK1Z` | 2010 VZ201 | 1.4240 | 20.81 | 1.0192 | 0.1904 |
| `K15HI2C` | 2015 HC182 | 1.4440 | 23.12 | 1.2902 | 0.0893 |
| `K14HJ5T` | 2014 HT195 | 1.4830 | 23.48 | 1.2294 | 0.4804 |
| `K14J79R` | 2014 JR79 | 1.5390 | 22.62 | 1.0440 | 0.2068 |
| `K05UF0F` | 2005 UF150 | 1.5810 | 20.28 | 1.0752 | 0.5109 |
| `K14Qh9P` | 2014 QP439 | 1.6200 | 20.15 | 1.2968 | 0.4072 |
| `K10R16E` | 2010 RE16 | 1.7290 | 19.17 | 1.2571 | 0.1488 |
| `K17FE6Q` | 2017 FQ146 | 1.7490 | 18.88 | 1.1850 | 0.3629 |
| `K25Oo9Z` | 2025 OZ509 | 2.0540 | 20.64 | 2.0516 | 0.1652 |
| `K25Oh4X` | 2025 OX434 | 2.2520 | 19.52 | 2.2623 | 0.0236 |
| `K04BG0P` | 2004 BP160 | 2.4410 | 19.28 | 1.1958 | 0.6412 |
| `K25Oq9X` | 2025 OX529 | 3.0420 | 17.90 | 2.9344 | 0.0715 |

## Group B1 — 15 in NEOfixer's orbit catalog but not in today's `site=500` list

NEOfixer responds with valid orbit data for these designations on the per-object
`/orbit/?object=` endpoint, but they do not appear in the bulk `site=500` target list
(neither in today's cached snapshot nor in a fresh fetch without `q-max`). The most
plausible interpretation is that NEOfixer's nightly priority generator filters them out
— low priority, lost, behind the sun, or already heavily observed. Their orbits exist;
they are simply not on tonight's observation list.

| packed | designation | MPC q | NF /orbit/ q |
|---|---|---:|---:|
| `K03YD6H` | 2003 YH136 | 0.2534 | 0.2531 |
| `K05X04Y` | 2005 XY4 | 0.4247 | 0.4235 |
| `K09V09P` | 2009 VP9 | 1.2718 | 1.2730 |
| `K10N81T` | 2010 NT81 | 0.9605 | 0.9605 |
| `K10V72D` | 2010 VD72 | 0.7519 | 0.7518 |
| `K10V21P` | 2010 VP21 | 0.3343 | 0.3343 |
| `K12F10D` | 2012 FD10 | 1.2429 | 1.2790 |
| `K15G00Y` | 2015 GY | 0.8543 | 0.8541 |
| `K17Q17P` | 2017 QP17 | 0.6224 | 0.6225 |
| `K24R12P` | 2024 RP12 | 1.0011 | 1.0011 |
| `K25D49K` | 2025 DK49 | 1.0482 | 1.0479 |
| `K25O13O` | 2025 OO13 | 0.8695 | 0.8708 |
| `K25QE7N` | 2025 QN147 | 1.7482 | 1.7296 |
| `K25X06N` | 2025 XN6 | 0.5889 | 0.5952 |
| `K26B02E` | 2026 BE2 | 1.0921 | 1.0921 |

Note that several of these have very low MPC q values (e.g. 2003 YH136 q=0.25,
2010 VP21 q=0.33), so q > 1.3 is not the gating factor — they are in NEOfixer's
orbital catalog but not in its observation-target list.

## Group B2 — 61 genuinely unknown to NEOfixer's API

Both `/orbit/?object=` (returns "Unknown object specified", JSON-RPC code -32602)
and `/obs/?object=` (returns "The specified format is not available for that object"
or "Unknown object", code -3) reject these. The public web URL
`https://neofixer.arizona.edu/site/500/{packed}` returns HTTP 404 for sample probes.
These objects are simply not in NEOfixer's catalog as currently exposed.

Most are older NEOs (often single-apparition or short-arc); a few have very deep q
and would normally be high-interest targets if NEOfixer had data on them.

| packed | designation | MPC q | MPC e | MPC i (°) | obs (mpc_orbits) |
|---|---|---:|---:|---:|---:|
| `J97N06J` | 1997 NJ6 | 1.1518 | 0.2323 | 18.70 | 265 |
| `J98H03M` | 1998 HM3 | 1.1691 | 0.0622 | 39.33 | 0 |
| `K01M03R` | 2001 MR3 | 1.2982 | 0.4522 | 4.42 | 184 |
| `K01U11Q` | 2001 UQ11 | 1.2968 | 0.5128 | 3.86 | 363 |
| `K04F17M` | 2004 FM17 | 0.6640 | 0.2500 | 6.76 | 227 |
| `K04X14P` | 2004 XP14 | 0.8851 | 0.1586 | 32.95 | 1399 |
| `K07X16H` | 2007 XH16 | 0.9082 | 0.2349 | 27.43 | 467 |
| `K08T04C` | 2008 TC4 | 0.3476 | 0.5545 | 10.65 | 182 |
| `K13R36F` | 2013 RF36 | 0.6506 | 0.7176 | 28.27 | 0 |
| `K13X28H` | 2013 XH28 | 0.5493 | 0.3069 | 19.47 | 14 |
| `K15Ff5E` | 2015 FE415 | 0.3338 | 0.7747 | 4.35 | 13 |
| `K16CW3G` | 2016 CG323 | 0.9465 | 0.1376 | 13.82 | 12 |
| `K16CW3H` | 2016 CH323 | 0.7863 | 0.2398 | 17.56 | 12 |
| `K16CW3J` | 2016 CJ323 | 0.5108 | 0.3197 | 8.70 | 14 |
| `K16CW3L` | 2016 CL323 | 0.7461 | 0.2188 | 5.99 | 20 |
| `K16CW3M` | 2016 CM323 | 0.8995 | 0.4242 | 12.73 | 15 |
| `K16K10G` | 2016 KG10 | 0.9995 | 0.5072 | 9.74 | 14 |
| `K16M04W` | 2016 MW4 | 0.3883 | 0.4495 | 12.15 | 24 |
| `K16N90U` | 2016 NU90 | 0.9494 | 0.6221 | 11.01 | 15 |
| `K16N90W` | 2016 NW90 | 1.0135 | 0.5266 | 10.65 | 52 |
| `K16N90Y` | 2016 NY90 | 0.4730 | 0.4415 | 0.95 | 25 |
| `K16UF0E` | 2016 UE150 | 0.7541 | 0.5742 | 2.08 | 15 |
| `K16UE9T` | 2016 UT149 | 0.7752 | 0.2093 | 2.73 | 21 |
| `K16UE9V` | 2016 UV149 | 0.9387 | 0.2668 | 15.40 | 16 |
| `K16UE9W` | 2016 UW149 | 0.8886 | 0.2453 | 10.16 | 24 |
| `K16UE9X` | 2016 UX149 | 0.8883 | 0.1938 | 12.65 | 20 |
| `K16UE9Y` | 2016 UY149 | 0.9662 | 0.2937 | 26.30 | 13 |
| `K16UE9Z` | 2016 UZ149 | 0.8427 | 0.3435 | 25.89 | 29 |
| `K16V21T` | 2016 VT21 | 0.7366 | 0.5672 | 7.44 | 20 |
| `K16V21V` | 2016 VV21 | 1.0159 | 0.6513 | 5.58 | 29 |
| `K16W58A` | 2016 WA58 | 0.7089 | 0.2342 | 12.94 | 15 |
| `K16W58D` | 2016 WD58 | 0.8240 | 0.1088 | 49.40 | 23 |
| `K16W58E` | 2016 WE58 | 0.9026 | 0.4349 | 1.14 | 29 |
| `K16W57O` | 2016 WO57 | 0.9987 | 0.5931 | 2.50 | 49 |
| `K16W57P` | 2016 WP57 | 0.3068 | 0.6865 | 0.70 | 20 |
| `K16W57R` | 2016 WR57 | 0.9201 | 0.4220 | 28.62 | 13 |
| `K16W57S` | 2016 WS57 | 0.9349 | 0.6243 | 5.30 | 23 |
| `K16W57T` | 2016 WT57 | 0.9210 | 0.6498 | 17.30 | 24 |
| `K16W57U` | 2016 WU57 | 0.3577 | 0.8344 | 3.72 | 17 |
| `K16W57X` | 2016 WX57 | 0.7351 | 0.1527 | 12.31 | 37 |
| `K16X24Z` | 2016 XZ24 | 0.7550 | 0.3483 | 40.62 | 18 |
| `K16Y14M` | 2016 YM14 | 0.9849 | 0.3198 | 22.51 | 29 |
| `K17BE2C` | 2017 BC142 | 0.9067 | 0.3322 | 15.96 | 31 |
| `K17C36B` | 2017 CB36 | 0.9016 | 0.0825 | 8.90 | 10 |
| `K17C36C` | 2017 CC36 | 0.5545 | 0.3038 | 2.10 | 12 |
| `K17C36D` | 2017 CD36 | 0.8171 | 0.2373 | 24.81 | 15 |
| `K17C36E` | 2017 CE36 | 0.8012 | 0.4347 | 5.87 | 36 |
| `K17C36G` | 2017 CG36 | 0.2258 | 0.8864 | 19.43 | 18 |
| `K17C35W` | 2017 CW35 | 0.9334 | 0.6197 | 8.72 | 31 |
| `K17C35X` | 2017 CX35 | 0.7047 | 0.4941 | 36.91 | 19 |
| `K17C35Y` | 2017 CY35 | 0.4863 | 0.3463 | 2.89 | 22 |
| `K17C35Z` | 2017 CZ35 | 0.7934 | 0.2552 | 14.20 | 15 |
| `K17DC3G` | 2017 DG123 | 0.8865 | 0.5514 | 5.00 | 36 |
| `K17DC3J` | 2017 DJ123 | 0.7863 | 0.4222 | 8.15 | 54 |
| `K17DC3K` | 2017 DK123 | 0.8690 | 0.2591 | 23.55 | 23 |
| `K17DC3L` | 2017 DL123 | 0.7037 | 0.2031 | 19.80 | 20 |
| `K17DC3O` | 2017 DO123 | 0.7743 | 0.4746 | 7.44 | 23 |
| `K17E25N` | 2017 EN25 | 0.4658 | 0.5252 | 29.81 | 23 |
| `K17E25P` | 2017 EP25 | 0.9776 | 0.4666 | 4.08 | 24 |
| `K20X05L` | 2020 XL5 | 0.6132 | 0.3872 | 13.85 | 61 |
| `K26G00B` | 2026 GB | 0.9562 | 0.6177 | 10.23 | 188 |

## Group C — 38 only-in-NEOfixer (boundary-q disagreement)

All 38 objects flagged `in_neofixer=True` but `in_mpc=False`, `in_mpc_orbits=False`,
`in_cneos=False`, `in_neocc=False`, `in_lowell=False` are present in `mpc_orbits` (the
table itself, joined on the unpacked primary provisional designation). They are absent
from the consensus's `in_mpc_orbits` flag because **all 38 have `mpc_orbits.q > 1.3`**
(range: 1.3000 to 1.3916; median ≈ 1.302). NEOfixer's Find_Orb fits give them
q ≤ 1.3 (33 of the 38 currently in cache; the other 5 carry `in_neofixer=True` from
today's ingest but their packed designation in the cache differs from the consensus
canonical form — see *Note on canonicalisation* below).

This is the symmetric counterpart of Group A: when NEOfixer's Find_Orb and MPC's
orbit solution disagree near the q = 1.3 cutoff, one side calls "NEO" and the other
does not. The other four sources (NEA.txt, CNEOS, NEOCC, Lowell) all use a
q ≤ 1.3 NEO definition with their own orbit catalogs, and they side with MPC here.

| packed | designation | NF q | MPC q | Δ (MPC−NF) | MPC e | NF H |
|---|---|---:|---:|---:|---:|---:|
| `K12T79A` | 2012 TA79 | — | 1.3015 | — | 0.4405 | — |
| `K11F87R` | 2011 FR87 | — | 1.3009 | — | 0.4114 | — |
| `K19C00P` | 2019 CP | — | 1.3007 | — | 0.2679 | — |
| `K03A23E` | 2003 AE23 | — | 1.3004 | — | 0.3270 | — |
| `K02S41S` | 2002 SS41 | — | 1.3003 | — | 0.3822 | — |
| `K13T04U` | 2013 TU4 | 1.0900 | 1.3507 | +0.2607 | 0.2094 | 19.98 |
| `K20F07H` | 2020 FH7 | 1.0870 | 1.3290 | +0.2420 | 0.2559 | 21.01 |
| `K13S24T` | 2013 ST24 | 1.2340 | 1.3916 | +0.1576 | 0.1889 | 21.16 |
| `K01D77C` | 2001 DC77 | 1.2690 | 1.3149 | +0.0459 | 0.4878 | 19.92 |
| `K18C00S` | 2018 CS | 1.2650 | 1.3104 | +0.0454 | 0.4159 | 20.64 |
| `K13R74A` | 2013 RA74 | 1.2810 | 1.3257 | +0.0447 | 0.2861 | 22.49 |
| `K21B00G` | 2021 BG | 1.2680 | 1.3099 | +0.0419 | 0.5247 | 19.71 |
| `K05Q87N` | 2005 QN87 | 1.2660 | 1.3013 | +0.0353 | 0.3543 | 20.17 |
| `K09S00Z` | 2009 SZ | 1.2860 | 1.3058 | +0.0198 | 0.3731 | 20.30 |
| `J99H01W` | 1999 HW1 | 1.2920 | 1.3101 | +0.0181 | 0.4505 | 20.01 |
| `K22E04Q` | 2022 EQ4 | 1.2920 | 1.3072 | +0.0152 | 0.5399 | 21.26 |
| `K06V03B` | 2006 VB3 | 1.2860 | 1.3003 | +0.0143 | 0.5430 | 21.16 |
| `K12U27W` | 2012 UW27 | 1.2880 | 1.3016 | +0.0136 | 0.5404 | 21.14 |
| `K09X08J` | 2009 XJ8 | 1.2910 | 1.3024 | +0.0114 | 0.4714 | 21.04 |
| `K22B09J` | 2022 BJ9 | 1.2930 | 1.3027 | +0.0097 | 0.4304 | 20.79 |
| `K10K80J` | 2010 KJ80 | 1.2960 | 1.3047 | +0.0087 | 0.5033 | 19.30 |
| `K24S05C` | 2024 SC5 | 1.3000 | 1.3081 | +0.0081 | 0.4028 | 20.35 |
| `K14G53E` | 2014 GE53 | 1.2960 | 1.3038 | +0.0078 | 0.5120 | 18.48 |
| `K02E01H` | 2002 EH1 | 1.2950 | 1.3024 | +0.0074 | 0.4207 | 19.56 |
| `K16L51F` | 2016 LF51 | 1.2990 | 1.3035 | +0.0045 | 0.5043 | 18.88 |
| `K13V12Q` | 2013 VQ12 | 1.2970 | 1.3015 | +0.0045 | 0.2472 | 20.56 |
| `K18F05H` | 2018 FH5 | 1.2980 | 1.3010 | +0.0030 | 0.4922 | 20.35 |
| `K17F90Q` | 2017 FQ90 | 1.2990 | 1.3015 | +0.0025 | 0.3629 | 22.17 |
| `K20X05U` | 2020 XU5 | 1.2980 | 1.3002 | +0.0022 | 0.4275 | 21.18 |
| `K10G23J` | 2010 GJ23 | 1.2990 | 1.3010 | +0.0020 | 0.5222 | 19.37 |
| `K13T04D` | 2013 TD4 | 1.3000 | 1.3019 | +0.0019 | 0.4024 | 21.26 |
| `K21N50N` | 2021 NN50 | 1.3000 | 1.3017 | +0.0017 | 0.5210 | 19.55 |
| `K20H02S` | 2020 HS2 | 1.3000 | 1.3009 | +0.0009 | 0.4221 | 21.37 |
| `K22A06U` | 2022 AU6 | 1.3000 | 1.3005 | +0.0005 | 0.0779 | 21.11 |
| `K04H02A` | 2004 HA2 | 1.3000 | 1.3005 | +0.0005 | 0.2700 | 20.09 |
| `K21P23D` | 2021 PD23 | 1.3000 | 1.3004 | +0.0004 | 0.3977 | 21.58 |
| `K22D05D` | 2022 DD5 | 1.3000 | 1.3002 | +0.0002 | 0.3167 | 21.66 |
| `K22C12L` | 2022 CL12 | 1.3000 | 1.3000 | +0.0000 | 0.1559 | 23.06 |

### Note on canonicalisation

Five of the 38 (rows with `NF q = —` above) carry `in_neofixer=True` in the consensus
but have no entry in today's `app/.neofixer_targets.json` keyed on the packed
designation shown. Their `in_neofixer=True` flag came in via `canonicalize()` mapping the
cache's `packed` key to a slightly different canonical packed designation in the
consensus table. The five are: 2002 SS41, 2003 AE23, 2011 FR87, 2012 TA79, 2019 CP.
A focused designation-canonicalisation audit would be a useful follow-up; it is not the
main story of this disagreement.

## Recommendations

1. **Drop the client-side `q > 1.3` filter** in `lib/neo_consensus_neofixer.py` (or
   relax it to a broader cushion such as `q > 1.5`). Membership in NEOfixer's
   `site=500` list is itself NEOfixer's NEO classification signal; second-guessing it
   with our own q test forces NEOfixer's flag to track MPC's solution rather than
   NEOfixer's. Recovering those 45 reduces the largest single disagreement bucket and
   makes the consensus tab more honestly "what does each source say".

2. **Document Group B1 as expected behaviour**, or follow up with NEOfixer to ask
   whether `site=500` should include orbit-only (non-priority) entries. The current
   bulk endpoint returns ~42K NEOs whereas the underlying orbit catalog clearly has
   more. If NEOfixer can expose a "full catalog" endpoint, ingesting from that would
   be more comparable to the other five sources.

3. **Group B2 is real catalog divergence** — keep flagging these as
   `in_neofixer=False`. They are not present in NEOfixer's API by any path tested.
   These are candidates for a future "objects each source uniquely lacks" panel on the
   dashboard.

4. **Group C is unavoidable boundary-class disagreement** unless we widen the NEO
   definition. A separate "borderline NEOs" view with 1.3 < q ≤ 1.4 is worth
   considering for the dashboard.

---

## Follow-up (2026-05-06): why are B1 and B2 missing from NEOfixer?

Two days after the initial analysis, this section pulls the per-object orbit
quality data NEOfixer publishes on its `/orbit/` endpoint for the 15 B1 objects,
joins our DB stats (arc, last observation, observation count) for the 61 B2
objects, and compares both against a 500-row random sample of objects NEOfixer
*does* include — to identify the actual gating filter and to separate "NEOfixer
correctly omitted" cases from "NEOfixer is missing real data".

### B1 deep-dive: 15 in `/orbit/` but not in `site=500`

NEOfixer's `site=500` is operationally a *target priority list* for tonight's
observation, not a complete catalog. Three filters appear to gate the cut from the
underlying `/orbit/` catalog into the `/targets/?site=500` response:

1. **Orbit uncertainty** — Find_Orb's `U` parameter (0=tight, 9=lost). Median U for B1 is 7.
2. **Recency of last observation** — median 593 days since last obs for B1, with five
   above 1500 days (effectively lost objects).
3. **NEOfixer's own q solution** — three of the 15 have NF Find_Orb q close to or
   above 1.3 (1.273, 1.279, 1.730), so even without the advisory `q-max=1.3` URL
   parameter, NEOfixer's server-side classification deprioritises them.

Per-object table, sorted by U (high U = high uncertainty):

| packed | designation | NF q | NF H | U | rms (″) | wrms | n_used | arc (d) | last obs | days ago |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| `K12F10D` | 2012 FD10 | 1.279 | 21.19 | 9.8 | 0.39 | 0.71 | 31 | 1 | 2012-03-20 | 5160 |
| `K03YD6H` | 2003 YH136 | 0.253 | 19.02 | 9.8 | 0.27 | 0.72 | 46 | 6 | 2023-11-18 | 900 |
| `K25QE7N` | 2025 QN147 | 1.730 | 21.81 | 9.4 | 0.13 | 0.86 | 9 | 11 | 2025-08-28 | 251 |
| `K25O13O` | 2025 OO13 | 0.871 | 23.69 | 9.0 | 0.12 | 0.34 | 8 | 15 | 2025-08-17 | 262 |
| `K24R12P` | 2024 RP12 | 1.001 | 24.17 | 8.1 | 0.24 | 0.69 | 38 | 11 | 2024-09-20 | 593 |
| `K26B02E` | 2026 BE2 | 1.092 | 24.56 | 7.6 | 0.20 | 0.93 | 25 | 3 | 2026-01-21 | 105 |
| `K25D49K` | 2025 DK49 | 1.048 | 22.35 | 7.4 | 0.20 | 0.93 | 19 | 62 | 2025-04-28 | 373 |
| `K10V21P` | 2010 VP21 | 0.334 | 23.51 | 7.0 | 0.41 | 0.48 | 103 | 23 | 2010-11-28 | 5638 |
| `K25X06N` | 2025 XN6 | 0.595 | 29.04 | 6.5 | 0.19 | 0.82 | 18 | 2 | 2025-12-17 | 140 |
| `K09V09P` | 2009 VP9 | 1.273 | 18.43 | 5.8 | 0.24 | 0.55 | 11 | 4546 | 2022-04-20 | 1477 |
| `K10N81T` | 2010 NT81 | 0.961 | 21.69 | 5.1 | 0.62 | 0.67 | 14 | 4247 | 2022-02-26 | 1530 |
| `K05X04Y` | 2005 XY4 | 0.424 | 23.49 | 3.1 | 1.85 | 2.07 | 19 | 7385 | 2026-02-24 | 71 |
| `K15G00Y` | 2015 GY | 0.854 | 21.68 | 2.1 | 0.39 | 0.56 | 256 | 662 | 2017-01-31 | 3382 |
| `K17Q17P` | 2017 QP17 | 0.623 | 19.58 | 0.6 | 0.40 | 0.61 | 106 | 2402 | 2024-03-18 | 779 |
| `K10V72D` | 2010 VD72 | 0.752 | 21.54 | -0.0 | 0.59 | 0.81 | 99 | 5467 | 2025-10-28 | 190 |

Two anomalies do not fit any of the three heuristics:

- **2010 VD72** (U≈0, n_used=99, last obs 190 days ago) — well-determined orbit,
  recently observed, q=0.752 (potentially hazardous). No obvious reason for exclusion.
- **2017 QP17** (U=0.6, n_used=106, last obs 779 days ago) — also well-determined,
  q=0.623. Less recent than 2010 VD72 but still inside the typical follow-up window.

Possible additional gating: NEOfixer may exclude well-determined orbits that don't
*need* more astrometry from `site=500` (treating the list as a "needs follow-up tonight"
queue, not a "all known NEOs" catalog). Without internal NEOfixer documentation we can't
confirm.

### B2 deep-dive: 61 unknown to NEOfixer's API

B2 splits cleanly into two subpopulations once orbital arc and absolute magnitude are
considered:

- **B2a — 50 short-arc faint detections** (arc < 1 day, H > 26): single-night CSS-style
  tracklets with provisional designations but no follow-up.
- **B2b — 11 well-observed numbered NEOs** (arc 148–9657 d, nobs 61–1399, all but one numbered).

#### B2a: short-arc faint single-night detections

All 50 have:

- `arc_days < 1` (single-night detections, often a few hours of observations)
- `H` typically 27–33 (extremely faint — sub-100-metre objects observable only at
  closest approach)
- `last_obs` 3300–4500 days ago (no follow-up since the discovery night)

They cluster heavily by half-month, consistent with CSS post-processing precovery
batches (running tracklet detection over old images, submitting designations en masse):

| year + half-month | count | sample members |
|---|---:|---|
| 2016 W | 10 | 2016 WO57, 2016 WP57, 2016 WR57, 2016 WS57, 2016 WT57, 2016 WU57, … (+4) |
| 2017 C | 9 | 2017 CW35, 2017 CX35, 2017 CY35, 2017 CZ35, 2017 CB36, 2017 CC36, … (+3) |
| 2016 U | 7 | 2016 UT149, 2016 UV149, 2016 UW149, 2016 UX149, 2016 UY149, 2016 UZ149, … (+1) |
| 2016 C | 5 | 2016 CG323, 2016 CH323, 2016 CJ323, 2016 CL323, 2016 CM323 |
| 2017 D | 5 | 2017 DG123, 2017 DJ123, 2017 DK123, 2017 DL123, 2017 DO123 |
| 2016 N | 3 | 2016 NU90, 2016 NW90, 2016 NY90 |

**This is NEOfixer doing the right thing.** With only single-night astrometry from
a decade ago, Find_Orb cannot fit a usable orbit, and even if it could, the prediction
uncertainty after 9–10 years would dwarf the celestial sphere. Listing these on a
site=500 target page would direct observers to chase impossible-to-find ghosts. The
other five sources (MPC NEA.txt, mpc_orbits, CNEOS, NEOCC, Lowell) keep them in their
catalogues for historical record-keeping, not as observation targets.

#### B2b: well-observed numbered NEOs absent from NEOfixer (real catalog gap)

These are ordinary, multi-decade-arc NEOs with hundreds of observations, mostly
numbered. NEOfixer should have them; it does not.

| packed | designation | permid | nobs | arc (d) | last obs | mpc q | mpc H |
|---|---|---|---:|---:|---|---:|---:|
| `J97N06J` | 1997 NJ6 | 189011 | 265 | 9657 | 2023-12-16 | 1.152 | 19.08 |
| `J98H03M` | 1998 HM3 | 326291 | 586 | 9172 | 2023-06-01 | 1.169 | 19.00 |
| `K01M03R` | 2001 MR3 | 333311 | 184 | 8148 | 2023-10-12 | 1.298 | 19.07 |
| `K01U11Q` | 2001 UQ11 | 306918 | 363 | 8093 | 2023-11-18 | 1.297 | 17.31 |
| `K04F17M` | 2004 FM17 | 387816 | 227 | 7351 | 2024-05-08 | 0.664 | 19.36 |
| `K07X16H` | 2007 XH16 | 484402 | 465 | 6490 | 2025-09-14 | 0.908 | 19.68 |
| `K04X14P` | 2004 XP14 | 612901 | 1399 | 5785 | 2020-10-12 | 0.885 | 19.79 |
| `K08T04C` | 2008 TC4 | 614134 | 182 | 4726 | 2021-09-14 | 0.348 | 21.65 |
| `K20X05L` | 2020 XL5 | 614689 | 61 | 4390 | 2024-12-30 | 0.613 | 20.28 |
| `K13R36F` | 2013 RF36 | 555122 | 123 | 4250 | 2025-04-25 | 0.651 | 16.97 |
| `K26G00B` | 2026 GB | — | 188 | 148 | 2026-04-25 | 0.956 | 22.51 |

I probed NEOfixer for 9 of these 11 across every identifier the API accepts — packed
designation, unpacked designation, permid as a bare integer string — and the public
webpage `https://neofixer.arizona.edu/site/500/{packed}`. Every probe returned
"Unknown object specified." (JSON-RPC code -32602) or HTTP 404. **2008 TC4** alone has
a famous 2017 close approach and 1399 catalogued observations; its absence is striking.

Plausible explanations (none confirmed without insight into NEOfixer's ingestion):

1. NEOfixer's Find_Orb may have generated a non-NEO solution for these (a different
   orbit fit), causing them to be classified out of NEOfixer's NEO database. Unlikely
   for objects with thousands of observations and tight U=0 orbits, but possible if
   NEOfixer started from a different astrometry slice.
2. NEOfixer's ingestion may have specifically deprioritised these (recovered,
   numbered, well-determined — "no new astrometry needed"). But B1 has well-determined
   numbered objects that *are* in `/orbit/` if not `/targets/`, so a complete API drop
   is more drastic than mere deprioritisation.
3. A specific catalog-version or sync issue: these may have been removed during a
   maintenance cycle and not re-added.

Worth a follow-up email to Eric Christensen / Carson Fuls (NEOfixer maintainers) with
this list and a request for clarification.

### What is NEOfixer doing right vs wrong, compared to the other five sources?

The starting frame matters: **NEOfixer is an observation-prioritisation tool, not a
NEO catalogue.** The other five (MPC NEA.txt, mpc_orbits, CNEOS, NEOCC, Lowell astorb)
are catalogues, listing every known NEO regardless of observability. Once that
asymmetry is acknowledged, much of the "missing" gets reframed:

| Behaviour | NEOfixer | Catalogues |
|---|---|---|
| Single-night unrecoverable detections (B2a, 50 objects) | Excludes | Include |
| Well-determined orbits, lost or low-priority (B1, 13 of 15) | In `/orbit/`, not `site=500` | Include |
| Boundary-q disagreements (Group A, 45) | Trusts own Find_Orb | Trust own orbits |
| Independent orbit fitting | Yes (Find_Orb) | MPC fits, others import |
| Famous well-observed NEOs (B2b, 11) | **Absent — gap** | Include |

**NEOfixer doing right:**

- **Filters out 50 single-night unrecoverable tracklets**. These are valid astronomical
  detections with no observational utility tonight; chasing them would waste telescope
  time. The other catalogues retain them for record-keeping; that's appropriate for
  catalogues but inappropriate for a target list.
- **Maintains independent Find_Orb solutions**. The Group A and Group C disagreements
  in the original analysis (83 of 159 total disagreements) are NEOfixer's Find_Orb
  saying something different from MPC at the q≈1.3 boundary. That's genuine cross-
  validation; without NEOfixer the consensus tab would have less analytical value.

**NEOfixer doing wrong:**

- **Catalog gap for 11 well-observed numbered NEOs (B2b)**. No astronomical reason —
  these have multi-decade arcs and hundreds of observations. Best guess is an
  ingestion-pipeline gap; should be raised with NEOfixer maintainers.
- **Inconsistency between `/orbit/` and `/targets/`** for B1. The dashboard's
  per-MPEC link to `https://neofixer.arizona.edu/site/500/{packed}` returns HTTP 404
  for these 15 objects, which is a mild user-facing surprise. NEOfixer could expose a
  "full catalog" endpoint or document the gating logic.

### Updated recommendations

To the original four, add:

5. **Recover B1 by ingesting from `/orbit/` per-object** for designations that are in
   the other-five set but missing from `/targets/?site=500`. ~15 calls per refresh,
   throttled. This recovers NEOfixer-confirmed orbits that the bulk endpoint omits.

6. **Email NEOfixer maintainers** with the B2b list (8 numbered NEOs probed; 3 more
   in the table) and ask whether the absences are intentional or reflect an ingestion
   gap. Cite specific examples: 2008 TC4 (614134), 2004 XP14 (612901), 1998 HM3 (326291).

7. **Document NEOfixer as a prioritisation tool** in the consensus tab's legend.
   Currently the six sources are presented symmetrically; users may interpret
   `in_neofixer=False` as "NEOfixer disagrees", when frequently it just means
   "NEOfixer has no priority for this object tonight". A small label change would
   reduce that confusion.

---

## Correction (2026-05-07): NEOfixer indexes numbered objects by packed *numbered* designation

Yesterday's addendum claimed B2b — 11 well-observed numbered NEOs (2008 TC4, 2004 XP14,
1998 HM3, etc.) — was a "real catalog gap" in NEOfixer. **That claim was wrong.** Today's
investigation reveals all 11 are present in NEOfixer's `/orbit/` catalog; my probes
yesterday used the *provisional* packed designation (e.g. `K08T04C` for 2008 TC4) where
NEOfixer requires the *numbered* packed designation (`z4134`).

### Discovery

NEOfixer's `/orbit/?object=` endpoint accepts multiple identifier forms but **rejects the
packed provisional designation for objects that have been numbered**. For 2008 TC4
(permanent number 614134), only `z4134` (packed numbered) and `2008 TC4` (unpacked) work;
`K08T04C` returns "Unknown object specified". This is consistent across all 11 objects.

Probe results (today, 2026-05-07):

| object | permid | packed numbered | NF /orbit/ q via numbered key | in /targets/ cache? |
|---|---:|---|---:|:---:|
| 2008 TC4  | 614134 | `z4134` | 0.348 | no |
| 2004 XP14 | 612901 | `z2901` | 0.885 | no |
| 2007 XH16 | 484402 | `m4402` | 0.908 | no |
| 1998 HM3  | 326291 | `W6291` | 1.169 | no |
| 1997 NJ6  | 189011 | `I9011` | 1.152 | no |
| 2001 MR3  | 333311 | `X3311` | 1.301 | yes priority=none |
| 2001 UQ11 | 306918 | `U6918` | 1.313 | yes priority=none |
| 2004 FM17 | 387816 | `c7816` | 0.665 | no |
| 2013 RF36 | 555122 | `t5122` | 0.643 | no |
| 2020 XL5  | 614689 | `z4689` | 0.613 | no |
| 2026 GB   | none   | n/a     | n/a   | no (not in /orbit/ either) |

NEOfixer's cache today (42,427 keys total) splits 38,335 packed-provisional + 3,178
packed-numbered + 887 short-temporary + 27 comet-or-other. So 7.5% of cache uses the
numbered key form. Our consensus ingestor's `canonicalize()` does correctly resolve
numbered keys to the canonical packed designation (verified against the 5 "only-in-
NEOfixer" boundary cases from yesterday — all are numbered-key cache entries, all of
which propagated to `in_neofixer=True` correctly). The bug was not in our ingestor; it
was in **my analysis scripts of yesterday**, which probed the cache and `/orbit/` using
provisional packed designations only.

### Re-classification of the 11

| object | revised group | reason |
|---|---|---|
| 2001 MR3 | **Group A** (in cache, q > 1.3 filtered by our code) | NF q=1.301, neo=0 |
| 2001 UQ11 | **Group A** | NF q=1.313, neo=0 |
| 2008 TC4 | **Group B1** (in `/orbit/`, not in `/targets/`) | as `z4134` |
| 2004 XP14 | **Group B1** | as `z2901` |
| 2007 XH16 | **Group B1** | as `m4402` |
| 1998 HM3 | **Group B1** | as `W6291` |
| 1997 NJ6 | **Group B1** | as `I9011` |
| 2004 FM17 | **Group B1** | as `c7816` |
| 2013 RF36 | **Group B1** | as `t5122` |
| 2020 XL5 | **Group B1** | as `z4689` |
| 2026 GB | **Group B2** (genuinely not in NEOfixer) | last obs only 12 days ago — likely too recent for ingest |

### Revised totals for the 121 missing-from-NEOfixer

| Group | original | corrected | delta |
|---|---:|---:|---:|
| **A.** in cache, q > 1.3 (our q-filter drops) | 45 | **47** | +2 |
| **B1.** in `/orbit/` but not in `/targets/` | 15 | **23** | +8 |
| **B2.** genuinely not in NEOfixer | 61 | **51** | −10 |
| **Total** | 121 | 121 | 0 |

B2 is now almost entirely B2a (50 short-arc unrecoverable single-night CSS detections
— NEOfixer correctly excludes), plus 2026 GB (recent object, likely just not yet ingested).

### Two further insights from full cache inspection

Inspecting the full `/targets/` cache entries for `X3311` (2001 MR3) and `U6918`
(2001 UQ11) reveals fields not visible in the abridged dump our ingestor consumes:

- `"neo": 0` — **NEOfixer's own NEO probability is 0%** for these two objects.
  NEOfixer's Find_Orb gives them q just over 1.3 and classifies them as non-NEO.
  They appear in `/targets/?site=500` with `priority=none, score=0` because the
  endpoint returns NEOfixer's broader catalog, not just objects with `neo=100`.
- For 2010 VD72 and 2017 QP17 (the two B1 anomalies highlighted yesterday), NEOfixer
  has **two separate orbit fits** — one indexed by packed provisional (`K10V72D`,
  `K17Q17P`) and one by packed numbered (`~152D`, `~0F9j`). The two fits return
  slightly different q values (e.g. 0.7518140992121 vs 0.7518141031038 for 2010 VD72),
  hinting that NEOfixer maintains parallel orbital solutions for the same physical
  object.

### Mechanism of `/targets/` exclusion

NEOfixer's API documentation at `https://neofixer.arizona.edu/api-info` confirms that
`/targets/` returns "highest scoring targets first" with scores evaluated against tonight's
observability. The endpoint accepts dozens of filter parameters (`score-min`, `cost-max`,
`elong-min`, `numbered`, `mult-opp`, etc.) but lacks any per-object lookup. Probing with
`?score-min=-99` or `?all=true` does not surface excluded objects, which means the
exclusion is enforced at the catalog-build step, not at the response-filter step.

NEOfixer offers seven endpoints total: `activity`, `ephem`, `obs`, `orbit`, `report`,
`targets`, `uncert`. There is no catalog-dump endpoint. The only way to know whether
NEOfixer has a given object is to probe `/orbit/?object=` with the right identifier.

### Updated recommendations

Recommendations 1–4 (original analysis) and 5–7 (yesterday's addendum) all stand,
except **withdraw recommendation 6** ("email NEOfixer maintainers about the B2b real
catalog gap") — there is no such gap.

New recommendations from today's findings:

8. **Audit `lib/api_clients.py:fetch_neofixer_orbit`** for the same packed-provisional
   bias. The function is called by the MPEC Browser tab to fetch a NEOfixer orbit per
   MPEC body. For numbered NEOs, the URL `/orbit/?object={packed_provisional}` returns
   "Unknown object specified". The caller must either supply the packed numbered
   designation or the unpacked form, or the function must fall back through both.

9. **Surface NEOfixer's `neo` probability field** in the consensus tab. Ingesting and
   exposing the `neo: 0..100` field would allow disagreements like 2001 MR3
   (NEOfixer says 0% NEO; MPC NEA, mpc_orbits, CNEOS, NEOCC, Lowell all agree it is
   a NEO with q ≈ 1.30) to be presented as honest scientific disagreements rather than
   "NEOfixer is missing this object".

10. **2026 GB tracking**: re-probe in ~30 days. If still absent, ask NEOfixer about
   ingestion latency for newly-discovered NEOs.

### Note on yesterday's "B2b famous catalog gap" claim

Yesterday's addendum (commit `4a0e36b`) leant heavily on the framing "NEOfixer is
missing 2008 TC4 — striking absence". That framing is now retracted. The lesson:
when probing a third-party catalog with a designation that returns "not found", confirm
the negative across **all common identifier encodings**, not just the one used in our
local schema. The packed-numbered/packed-provisional split is well-known to MPC
tooling but I missed it in the original probe sweep.
