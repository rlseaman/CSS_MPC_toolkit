# CSS Discovery Statistics — All Time

Generated: 2026-04-08

Source: MPC `obs_sbn` discovery flags (`disc='*'`) for the seven CSS
stations, classified using JPL Small-Body Database (SBDB) orbit classes.
Comet categories are excluded due to known MPC publication lag and
incomplete SBDB coverage.

```
Category                           G96     703    E12  V06  I52    V00  CSS Total
---------------------------------------------------------------------------------
— NEOs —
  Atira                              8       3      0    0    0      2         13
  Aten                           1,130     403     55    0    2     98      1,688
  Apollo                         8,008   2,699    233    1   10    690     11,641
  Amor                           4,033     808    176    0    7    477      5,501
NEO subtotal                    13,179   3,913    464    1   19  1,267     18,843
— NEO subsets (overlapping) —
  PHAs                             455     297     85    0    0     23        860
  1 km+ (H < 17.75)                 41      90     35    0    0      0        166
  140 m+ (H ≤ 22)                2,245   1,162    326    0    3    125      3,861
— Non-NEOs —
  Mars-crosser                   5,355   1,363    317    0    6    320      7,361
  Inner Main Belt                7,288   1,896    207    1    4    275      9,671
  Main Belt                    273,476  43,670  4,300    8  126  7,292    328,872
  Outer Main Belt                9,378   1,250    121    0    1    272     11,022
  Jupiter Trojan                 3,131     166     17    0    2    119      3,435
  Centaur                          112      17      9    0    0     20        158
  TNO                               33       6      3    0    0      6         48
Non-NEO subtotal               298,773  48,368  4,974    9  139  8,304    360,567
TOTAL                          311,952  52,281  5,438   10  158  9,571    379,410
```

## Stations

| Code | Name |
|---|---|
| G96 | Mt. Lemmon Survey |
| 703 | Catalina Sky Survey (Mt. Bigelow) |
| E12 | Siding Spring Survey |
| V06 | CSS-Kuiper |
| I52 | Mt. Lemmon-Steward |
| V00 | Bok NEO Survey* |

*V00 is the Bok NEO Survey, a partnership with Spacewatch and
the University of Minnesota.

## Notes

- "NEO subsets" rows are subsets of the NEO total (overlapping with
  the Atira/Aten/Apollo/Amor classes above), not separate categories.
- PHAs (Potentially Hazardous Asteroids) are NEOs with H ≤ 22 and
  Earth MOID ≤ 0.05 AU, as flagged by SBDB.
- Comet categories (near-Earth comets, Jupiter-family comets,
  Halley-type, etc.) are excluded from this report. MPC's comet
  publication is known to lag, and SBDB's comet coverage is
  incomplete enough that the numbers cannot be relied upon.
- Discoveries are credited to whichever station carried the
  `disc='*'` flag in the MPC observation database.
