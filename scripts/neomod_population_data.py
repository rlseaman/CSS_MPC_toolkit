"""
NEOMOD NEO Population & Completeness Estimates
================================================

Extracted from three NEOMOD papers plus Harris & Chodas (2021) reference model.
All cumulative values are N(<H) = number of NEOs with absolute magnitude < H.

Diameter conversion: D(km) = 1329 / sqrt(pV) * 10^(-H/5)
    At pV = 0.14:  H=17.75 -> D=1.00 km
                    H=22.00 -> D=141 m
                    H=22.75 -> D=100 m
                    H=25.00 -> D=35.5 m
                    H=28.00 -> D=8.9 m

Sources
-------
[1] NEOMOD (Paper I): Nesvorny et al. 2023, AJ 166, 55
    arXiv: 2306.09521
    "NEOMOD: A New Orbital Distribution Model for Near Earth Objects"
    - Calibrated on CSS (703+G96) detections 2005-2012
    - 12 orbital source regions, cubic spline H-distribution
    - H range: 15-25; 28 free parameters

[2] NEOMOD 2: Nesvorny et al. 2024, Icarus 411, 115922
    arXiv: 2312.09406
    "NEOMOD 2: An Updated Model of Near-Earth Objects from a Decade
     of Catalina Sky Survey Observations"
    - Calibrated on CSS G96 detections 2013-2022 (pre+post upgrade)
    - Extended to H=28; 30 free parameters
    - Adds tidal disruption component for small NEOs

[3] NEOMOD 3: Nesvorny et al. 2024, Icarus 417, 116110
    arXiv: 2404.18805
    "NEOMOD 3: The Debiased Size Distribution of Near Earth Objects"
    - Extends NEOMOD2 with WISE/NEOWISE albedo data
    - Provides diameter-based estimates (not just H)
    - Albedo distribution: sum of two Rayleigh (dark: pV~0.03, bright: pV~0.17)

[HC21] Harris & Chodas 2021, Icarus 365, 114452
    "The population of near-earth asteroids revisited and updated"
    - Re-detection ratio method, half-magnitude bins
    - Discoveries through August 2020

[G18] Granvik et al. 2018, Icarus 312, 181-207
    arXiv: 1804.10265
    "Debiased orbit and absolute-magnitude distributions for near-Earth objects"
    - 802,000 synthetic NEOs, 17<H<25

[D25] Deienno et al. 2025, Icarus 425, 116316
    "The debiased Near-Earth object population from ATLAS telescopes"
    arXiv: 2409.10453
"""

# ============================================================================
# CUMULATIVE POPULATION ESTIMATES: N(<H)
# ============================================================================
# Format: {H_max: N_cumulative} or {H_max: (N, uncertainty)}
# All values are number of NEOs with H < H_max (cumulative)

# --- NEOMOD 2 (Paper II) - Table 3 and text ---
# Primary reference for H=15-28 range
NEOMOD2_CUMULATIVE = {
    # H_max:  (N_estimate, sigma)  # source in paper
    15.00: (50, None),              # fixed constraint (complete sample)
    17.75: (936, 29),               # primary calibration point (D>1km)
    19.75: (4545, 42),              # Table 3 comparison
    # 21.75 not explicitly given but implied ~15000-16000
    24.75: (291_000, 3_000),        # Table 3 comparison
    27.75: (9_120_000, None),       # 0.912e7; text comparison
    28.00: (12_000_000, 400_000),   # (1.20 +/- 0.04) x 10^7
}

# --- NEOMOD 3 (Paper III) - Table 3 ---
# Diameter-based, converted to H using NEOMOD3's own reference albedos
# pV_ref varies: 0.15 (H<18), 0.16 (18<H<22), 0.18 (H>22)
# N1=simple, N2=fixed albedo extrapolated, N3=variable albedo
NEOMOD3_BY_DIAMETER = {
    # D_threshold_m: (N_simple, N_fixed_albedo, N_variable_albedo)
    1000:  (779,     891,     828),      # D > 1 km
    300:   (7_330,   8_208,   6_620),    # D > 300 m
    140:   (20_000,  22_100,  18_000),   # D > 140 m
    100:   (30_200,  33_500,  27_000),   # D > 100 m
    30:    (368_000, 427_000, 307_000),  # D > 30 m
    10:    (6_500_000, 6_500_000, None), # D > 10 m
}

# Final quoted NEOMOD3 values (best estimates spanning model range)
NEOMOD3_FINAL = {
    # D_threshold_m: (N_best, uncertainty)
    1000: (830, 60),        # "830 +/- 60 NEOs with D > 1 km"
    140:  (20_000, 2_000),  # "20,000 +/- 2,000 NEOs with D > 140 m"
    100:  (30_000, 3_000),  # "~30,000 +/- 3,000"
    10:   (6_500_000, None), # "~6.5 x 10^6"
}

# --- Harris & Chodas 2021 ---
# Half-magnitude bins, re-detection method
HARRIS_CHODAS_2021 = {
    # H_max: (N_estimate, sigma)
    17.75: (940, 10),               # "940 +/- 10" (or 950 in some references)
    19.75: (4_580, 160),            # alternate: 4625 cited in NEOMOD1
    21.75: (16_020, 550),           # alternate: 15880 cited in NEOMOD1
    24.75: (289_000, 15_000),       # (2.89 +/- 0.15) x 10^5
    # Values below extrapolated by H&C assumed completion model
    27.75: (24_400_000, None),      # 2.44 x 10^7 (NEOMOD2 says 3x too high)
}

# Note: NEOMOD1 cites slightly different H&C values: N(<19.75)=4625,
# N(<21.75)=15880, N(<24.75)=3.13e5. These may be from a different
# H&C publication year or rounding.

# --- Granvik et al. 2018 ---
GRANVIK_2018 = {
    # H_max: (N_estimate, sigma_plus, sigma_minus)
    17.75: (962, 52, 56),           # D > 1 km
    25.00: (802_000, 48_000, 42_000),  # 802+48/-42 x 10^3
}


# ============================================================================
# COMPLETENESS ESTIMATES
# ============================================================================
# Fraction of total population already discovered

# NEOMOD2 completeness (MPC catalog as of Oct 2022)
NEOMOD2_COMPLETENESS = {
    # H_max: (completeness_fraction, uncertainty)
    17.75: (0.91, 0.04),    # "91 +/- 4%"  (854 known / 936 est.)
    22.75: (0.26, None),    # "~26%"
    # 27.75: ~0.003          # ~27000 known / 9.12M est.
}

# NEOMOD3 completeness (referenced in text)
NEOMOD3_COMPLETENESS = {
    # H_max: completeness_fraction
    22.0: 0.35,     # "current completeness for H<22 ... is only ~35%"
    24.0: 0.10,     # "and H<24 is only ... ~10%"
}

# Deienno et al. 2025 (ATLAS-based)
ATLAS_COMPLETENESS = {
    # H_max: (completeness_fraction, sigma_plus, sigma_minus)
    17.75: (0.88, 0.03, 0.02),   # "88% +3/-2%"
    22.25: (0.36, 0.01, 0.01),   # "36% +1/-1%"
}


# ============================================================================
# NEOMOD2 SOURCE CONTRIBUTIONS (Table 2)
# ============================================================================
# Fraction of NEO population from each source region
# at bright (H=15) and faint (H=28) ends

NEOMOD2_SOURCES = {
    # source: (alpha_H15, alpha_H28)
    'nu6':       (0.06, 0.60),   # secular resonance - dominates faint end
    '3:1':       (0.28, 0.31),   # mean motion resonance
    '5:2':       (0.30, 0.05),   # dominates bright end
    '8:3':       (0.15, 0.01),
    '11:5':      (0.08, 0.00),
    '2:1':       (0.12, 0.01),
    'Hungarias':  (0.01, 0.025),
    '7:3':       (0.00, 0.00),   # negligible
    '9:4':       (0.00, 0.00),   # negligible
    'Phocaeas':  (0.00, 0.00),   # negligible
    'JFC':       (0.00, 0.00),   # negligible
}


# ============================================================================
# SIZE-FREQUENCY DISTRIBUTION SLOPES
# ============================================================================

# NEOMOD2: cumulative power-law index for H=25-28
# N(<H) ~ 10^(alpha * H), where alpha = cumulative index / 5
# cumulative index ~2.6 for H=25-28  (differential gamma ~ 0.51)
# Harris & Chodas: cumulative index ~3.75 for H>26

SFD_SLOPES = {
    'NEOMOD2_H25_28': {'cumulative_index': 2.6, 'differential_gamma': 0.51},
    'Harris_Chodas_H26plus': {'cumulative_index': 3.75},
}


# ============================================================================
# PERIHELION DISRUPTION MODEL (NEOMOD2)
# ============================================================================
# Critical perihelion distance below which NEOs are disrupted
# q*(H) = 0.135 + 0.032 * (H - 20)  [au]
# Examples from NEOMOD1:
#   H=17-19: q* ~ 0.06 au
#   H=20-22: q* ~ 0.12 au
#   H=23-25: q* ~ 0.18 au

def perihelion_disruption_distance(H):
    """Critical perihelion distance (au) for NEO disruption, NEOMOD2 model."""
    return 0.135 + 0.032 * (H - 20.0)


# ============================================================================
# IMPACT FLUX (NEOMOD3, Table 5)
# ============================================================================

NEOMOD3_IMPACT_FLUX = {
    # D_threshold_m: (impacts_per_Myr_low, impacts_per_Myr_high)
    1000: (1.51, 1.74),      # D > 1 km; interval 570-660 kyr
    140:  (42, 52),           # D > 140 m; interval 19-24 kyr
}
# D > 10 m: mean interval ~40 years
# D > 5 km: ~30 impacts/Gyr


# ============================================================================
# ALBEDO DISTRIBUTION (NEOMOD3)
# ============================================================================

NEOMOD3_ALBEDO = {
    'pV_dark_scale':  0.029,   # +/- 0.003
    'pV_bright_scale': 0.170,  # +/- 0.006
    'dark_fraction':   0.233,  # +/- 0.030
}

# Reference albedo for H-to-D conversion varies with H:
NEOMOD3_REFERENCE_ALBEDO = {
    # H_range: pV_ref
    'H<18':      0.15,
    '18<H<22':   0.16,
    'H>22':      0.18,
}


# ============================================================================
# INTERPOLATED CUMULATIVE DISTRIBUTION FOR PLOTTING
# ============================================================================
# Best-effort compilation of N(<H) from all sources.
# Where models agree (H<25), values are very similar.
# For H>25, NEOMOD2 gives significantly fewer NEOs than Harris & Chodas.

import math

def H_to_diameter_km(H, pV=0.14):
    """Convert absolute magnitude H to diameter in km, given geometric albedo."""
    return 1329.0 / math.sqrt(pV) * 10**(-H / 5.0)

def H_to_diameter_m(H, pV=0.14):
    """Convert absolute magnitude H to diameter in meters."""
    return H_to_diameter_km(H, pV) * 1000.0


# Compiled best-estimate cumulative N(<H) combining NEOMOD2+3 and H&C21.
# For H<=25, models agree well; for H>25, we use NEOMOD2 (preferred, survey-based).
# Anchor points come from published values; interpolated values (marked ~) use
# log-linear interpolation between anchors, adjusted where NEOMOD3 diameter-
# based estimates provide additional constraints.
#
# Key anchor points with multiple-model agreement:
#   H=15:    N=50       (all models, complete sample)
#   H=17.75: N~940      (NEOMOD2: 936+/-29, H&C21: 940+/-10, G18: 962+/-54)
#   H=19.75: N~4550     (NEOMOD2: 4545+/-42, H&C21: 4580+/-160)
#   H=21.75: N~16000    (H&C21: 16020+/-550)
#   H=24.75: N~290000   (NEOMOD2: 291K+/-3K, H&C21: 289K+/-15K)
#
# NEOMOD3 provides diameter-based anchors (at pV=0.14):
#   D>1km  (H~17.75): 830+/-60   (consistent with H-based estimates)
#   D>300m (H~20.4):  7330       (simple model)
#   D>140m (H~22.0):  20000+/-2K
#   D>100m (H~22.75): 30000+/-3K
#   D>30m  (H~25.4):  368000
#   D>10m  (H~27.75): 6.5M

COMPILED_CUMULATIVE = {
    # H_max:  N(<H)     source/notes
    15.00:    50,        # All models: complete sample
    16.00:    130,       # ~interpolated (log-linear 15->17.75)
    17.00:    430,       # ~interpolated (log-linear 15->17.75)
    17.75:    936,       # NEOMOD2 (936+/-29); H&C21 (940+/-10); G18 (962+/-54)
    18.00:    1_100,     # ~interpolated (17.75->19.75)
    19.00:    2_600,     # ~interpolated (17.75->19.75)
    19.75:    4_550,     # NEOMOD2 (4545+/-42); H&C21 (4580+/-160)
    20.00:    5_500,     # ~interpolated; consistent with NEOMOD3 D>300m=7330
    20.37:    7_300,     # NEOMOD3 D>300m (simple model) at pV=0.14
    21.00:    11_000,    # ~interpolated
    21.75:    16_000,    # H&C21 (16020+/-550); NEOMOD2 implied ~similar
    22.00:    20_000,    # NEOMOD3 D>140m = 20000+/-2000 (at pV=0.14)
    22.25:    24_000,    # ~interpolated (ATLAS completeness ref point)
    22.75:    30_000,    # NEOMOD3 D>100m = 30000+/-3000 (at pV=0.14)
    23.00:    38_000,    # ~interpolated (steepening SFD here)
    24.00:    130_000,   # ~interpolated (H&C21 slope in this range)
    24.75:    290_000,   # NEOMOD2 (291K+/-3K); H&C21 (289K+/-15K)
    25.00:    380_000,   # ~interpolated
    25.37:    500_000,   # ~near NEOMOD3 D>30m=368K (variable albedo shifts H)
    26.00:    1_200_000, # ~interpolated using NEOMOD2 slope (cum.index~2.5)
    27.00:    3_800_000, # ~interpolated using NEOMOD2 slope
    27.75:    9_120_000, # NEOMOD2 explicit (0.912 x 10^7)
    28.00:    12_000_000,# NEOMOD2 (1.20+/-0.04 x 10^7)
}

# NOTE on Granvik 2018: their model file contains 802,000 synthetic NEOs
# with 17<H<25, representing the full debiased population in that range.
# N(<25) = 802,000 is their total, substantially higher than NEOMOD2's
# implied N(<25) ~ 380,000. The difference likely arises from different
# source region models and SFD slopes in the H=22-25 range. NEOMOD2 is
# calibrated on a much longer CSS baseline (2013-2022 vs 2005-2012) and
# is generally considered the more current estimate.
#
# For H>25, Harris & Chodas 2021 predicts ~3x more NEOs than NEOMOD2:
#   H&C21: N(<27.75) = 24.4M vs NEOMOD2: N(<27.75) = 9.12M
# NEOMOD2's shallower faint-end slope (cumulative index ~2.6 vs H&C's ~3.75)
# is based on direct survey calibration, not extrapolation.


# ============================================================================
# NEOMOD2 SPLINE SEGMENT BOUNDARIES
# ============================================================================
# The H-magnitude distribution is modeled as cubic splines over 6 segments:
NEOMOD2_SPLINE_SEGMENTS = [
    (15.0, 16.5),
    (16.5, 17.5),
    (17.5, 20.0),
    (20.0, 24.0),
    (24.0, 25.0),
    (25.0, 28.0),
]
# Knot points at H = 15.0, 16.5, 17.5, 20.0, 24.0, 25.0, 28.0
# N(15) = 50 is fixed; spline slopes gamma_2 through gamma_6 are fitted


if __name__ == '__main__':
    print("NEOMOD Population Estimates - Compiled Data")
    print("=" * 60)
    print()

    print("Cumulative N(<H) - Best Compiled Estimates:")
    print(f"{'H':>6s}  {'D (pV=0.14)':>12s}  {'N(<H)':>12s}")
    print("-" * 36)
    for H, N in sorted(COMPILED_CUMULATIVE.items()):
        D_m = H_to_diameter_m(H)
        if D_m >= 1000:
            d_str = f"{D_m/1000:.2f} km"
        else:
            d_str = f"{D_m:.0f} m"
        print(f"{H:6.2f}  {d_str:>12s}  {N:>12,d}")

    print()
    print("Completeness Estimates:")
    print(f"{'Source':<12s}  {'H<':<6s}  {'Completeness':<15s}")
    print("-" * 40)
    for name, data in [
        ('NEOMOD2', NEOMOD2_COMPLETENESS),
        ('NEOMOD3', NEOMOD3_COMPLETENESS),
        ('ATLAS', ATLAS_COMPLETENESS),
    ]:
        for H, val in sorted(data.items()):
            if isinstance(val, tuple):
                c = val[0]
            else:
                c = val
            print(f"{name:<12s}  {H:<6.2f}  {c*100:.0f}%")
