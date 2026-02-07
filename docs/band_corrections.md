# Photometric Band-to-V Corrections

## Overview

Discovery observations are reported in various photometric bands. To produce
a consistent V-band magnitude estimate, corrections are applied based on the
MPC's [Band Conversion table](https://minorplanetcenter.net/iau/info/BandConversion.txt).

The corrected magnitude is: `V_approx = mag_reported + correction`

## Correction Table

| Band Code | Band Name | Correction | Notes |
|-----------|-----------|------------|-------|
| `V` | Johnson V | 0.0 | Reference band |
| `v` | Johnson V (alt) | 0.0 | |
| `B` | Johnson B | -0.8 | Blue |
| `U` | Johnson U | -1.3 | Ultraviolet |
| `R` | Johnson R | +0.4 | Red |
| `I` | Johnson I | +0.8 | Infrared |
| `g` | SDSS g' | -0.35 | Green |
| `r` | SDSS r' | +0.14 | Red |
| `i` | SDSS i' | +0.32 | Infrared |
| `z` | SDSS z' | +0.26 | |
| `y` | SDSS y | +0.32 | |
| `u` | SDSS u' | +2.5 | Ultraviolet |
| `w` | ATLAS w | -0.13 | White/wide |
| `c` | ATLAS c | -0.05 | Cyan |
| `o` | ATLAS o | +0.33 | Orange |
| `G` | Gaia G | +0.28 | |
| `J` | 2MASS J | +1.2 | Near-infrared |
| `H` | 2MASS H | +1.4 | Near-infrared |
| `K` | 2MASS K | +1.7 | Near-infrared |
| `C` | Clear/unfiltered | +0.4 | |
| `W` | Wide | +0.4 | |
| `L` | L-band | +0.2 | |
| `Y` | Y-band | +0.7 | |
| (blank) | No band reported | -0.8 | Assumed B-band |
| (other) | Unknown | 0.0 | Assumed V-band |

## Caveats

These corrections are **approximate**. The actual color terms depend on the
spectral type of the asteroid (S-type vs C-type vs others), which varies
significantly across the NEA population. The corrections assume a roughly
solar-colored object. For precise photometry, per-object spectral type
corrections would be needed.

## Source

MPC Band Conversion: https://minorplanetcenter.net/iau/info/BandConversion.txt
