"""
Orbit classification constants, color palettes, and derived parameters.

Provides the canonical mapping from orbit_type_int (as stored in mpc_orbits)
to human-readable names and Plotly-compatible colors.  Also implements
dynamical classification from orbital elements, Tisserand parameter
computation, and conversion between cometary and Keplerian element sets.

Element set notes:
    mpc_orbits stores cometary elements (q, e, i, node, argperi, peri_time)
    for ALL objects.  Keplerian elements (a, mean_anomaly, period, mean_motion)
    are populated for only ~43% of objects.  Use q_e_to_a() or the DERIVED_COLUMNS
    in lib/orbits.py to compute Keplerian elements when needed.

MPC orbit_type_int mapping
(source: https://www.minorplanetcenter.net/mpcops/documentation/orbit-types/
 verified against mpc_orbits element distributions, Feb 2026):

    Code  Name              Criteria
    ----  ----------------  --------------------------------------------------
    0     Atira (IEO)       a < 1.0, Q < 0.983
    1     Aten              a < 1.0, Q >= 0.983
    2     Apollo            a >= 1.0, q < 1.017
    3     Amor              a >= 1.0, 1.017 <= q < 1.3
    9     Inner Other       catch-all inner region (none currently in DB)
    10    Mars Crosser      1 <= a < 3.2, 1.3 < q < 1.666
    11    Main Belt         1 <= a < 3.27831, i < 75
    12    Jupiter Trojan    4.8 < a < 5.4, e < 0.3
    19    Middle Other      a < a_Jupiter, not fitting other middle types
    20    Jupiter Coupled   a >= 1, 2 < T_J < 3
    21    Neptune Trojan    29.8 < a < 30.4
    22    Centaur           a_Jupiter <= a < a_Neptune
    23    TNO               a >= a_Neptune
    30    Hyperbolic        e > 1
    31    Parabolic         e = 1
    99    Other (Unusual)   classification failure
"""

import math

# Planetary semi-major axes (AU)
A_JUPITER = 5.2026
A_NEPTUNE = 30.0690

# Main Belt outer boundary: 2:1 mean-motion resonance with Jupiter
A_MB_OUTER = 3.27831


# ---------------------------------------------------------------------------
# orbit_type_int -> (short_name, long_name, hex_color)
# ---------------------------------------------------------------------------

ORBIT_TYPES = {
    0:    ("Atira",    "Atira",                    "#e6194b"),
    1:    ("Aten",     "Aten",                     "#d62728"),
    2:    ("Apollo",   "Apollo",                   "#f58231"),
    3:    ("Amor",     "Amor",                     "#ffe119"),
    9:    ("InOther",  "Inner Other",              "#bcbd22"),
    10:   ("Mars-X",   "Mars Crosser",             "#3cb44b"),
    11:   ("MB",       "Main Belt",                "#4363d8"),
    12:   ("JT",       "Jupiter Trojan",           "#9A6324"),
    19:   ("MidOther", "Middle Other",             "#469990"),
    20:   ("JupCoup",  "Jupiter Coupled",          "#800000"),
    21:   ("NepTr",    "Neptune Trojan",           "#17becf"),
    22:   ("Centaur",  "Centaur",                  "#808000"),
    23:   ("TNO",      "TNO",                      "#000075"),
    30:   ("Hyper",    "Hyperbolic",               "#f032e6"),
    31:   ("Para",     "Parabolic",                "#e377c2"),
    99:   ("Other",    "Other (Unusual)",          "#a9a9a9"),
    None: ("Unclass",  "Unclassified",             "#bfbfbf"),
}


def short_name(orbit_type_int):
    """Return short label for an orbit_type_int value."""
    entry = ORBIT_TYPES.get(orbit_type_int, ORBIT_TYPES[None])
    return entry[0]


def long_name(orbit_type_int):
    """Return long label for an orbit_type_int value."""
    entry = ORBIT_TYPES.get(orbit_type_int, ORBIT_TYPES[None])
    return entry[1]


def color(orbit_type_int):
    """Return hex color for an orbit_type_int value."""
    entry = ORBIT_TYPES.get(orbit_type_int, ORBIT_TYPES[None])
    return entry[2]


def color_map():
    """Return dict mapping long_name -> hex_color for Plotly color_discrete_map."""
    return {v[1]: v[2] for v in ORBIT_TYPES.values()}


def category_order():
    """Return list of long_name values in canonical display order."""
    order = [0, 1, 2, 3, 9, 10, 11, 12, 19, 20, 21, 22, 23, 30, 31, 99, None]
    return [ORBIT_TYPES[k][1] for k in order if k in ORBIT_TYPES]


# ---------------------------------------------------------------------------
# Element conversions (cometary <-> Keplerian)
# ---------------------------------------------------------------------------

def q_e_to_a(q, e):
    """Semi-major axis from perihelion distance and eccentricity.

    Returns None/NaN for parabolic (e=1) or hyperbolic (e>=1) orbits.
    Works with scalars or numpy arrays.
    """
    try:
        import numpy as np
        result = np.where(e < 1.0, q / (1.0 - e), np.nan)
        return result
    except (ImportError, TypeError):
        if e is None or e >= 1.0:
            return None
        return q / (1.0 - e)


def q_e_to_aphelion(q, e):
    """Aphelion distance Q = a(1+e) from perihelion and eccentricity.

    Returns None/NaN for non-elliptical orbits.
    """
    try:
        import numpy as np
        a = np.where(e < 1.0, q / (1.0 - e), np.nan)
        return a * (1.0 + e)
    except (ImportError, TypeError):
        if e is None or e >= 1.0:
            return None
        return q * (1.0 + e) / (1.0 - e)


def a_to_period(a):
    """Orbital period in years from semi-major axis in AU (Kepler's 3rd law)."""
    try:
        import numpy as np
        return np.where(np.isfinite(a) & (a > 0), np.power(a, 1.5), np.nan)
    except (ImportError, TypeError):
        if a is None or a <= 0:
            return None
        return a ** 1.5


# ---------------------------------------------------------------------------
# Tisserand parameter
# ---------------------------------------------------------------------------

def tisserand_jupiter(a, e, i_deg):
    """
    Compute the Tisserand parameter with respect to Jupiter.

    T_J = a_J/a + 2 * cos(i) * sqrt((a/a_J) * (1 - e^2))

    Parameters
    ----------
    a : float or array
        Semi-major axis in AU.
    e : float or array
        Eccentricity.
    i_deg : float or array
        Inclination in degrees.

    Returns
    -------
    float or array
        Tisserand parameter value.  T_J < 3 suggests cometary origin.
    """
    i_rad = math.radians(i_deg) if isinstance(i_deg, (int, float)) else None
    # Support numpy arrays
    try:
        import numpy as np
        i_rad = np.radians(i_deg)
        return A_JUPITER / a + 2.0 * np.cos(i_rad) * np.sqrt((a / A_JUPITER) * (1.0 - e**2))
    except (ImportError, TypeError):
        i_rad = math.radians(i_deg)
        return A_JUPITER / a + 2.0 * math.cos(i_rad) * math.sqrt((a / A_JUPITER) * (1.0 - e**2))


# ---------------------------------------------------------------------------
# Classification from elements
# ---------------------------------------------------------------------------

def classify_from_elements(a, e, i_deg, q):
    """
    Classify an orbit from orbital elements using MPC orbit type definitions.

    Implements the full MPC classification scheme documented at:
    https://www.minorplanetcenter.net/mpcops/documentation/orbit-types/

    Classification priority order (geometric types before Tisserand):
        1. Hyperbolic / Parabolic (e >= 1)
        2. NEO subtypes: Atira, Aten, Apollo, Amor
        3. Mars Crosser
        4. Main Belt (geometric)
        5. Jupiter Trojan (geometric)
        6. Neptune Trojan (geometric)
        7. Jupiter Coupled (Tisserand: 2 < T_J < 3, catch-all)
        8. Centaur
        9. TNO
        10. Middle Other (a < a_Jupiter catch-all)
        11. Inner Other (inner region catch-all)

    Parameters
    ----------
    a : float
        Semi-major axis in AU.
    e : float
        Eccentricity.
    i_deg : float or None
        Inclination in degrees.  Required for Jupiter Coupled (type 20)
        and Main Belt (type 11) classification.
    q : float
        Perihelion distance in AU.

    Returns
    -------
    int or None
        The inferred orbit_type_int, or None if inputs are insufficient.
    """
    if e is None or q is None:
        return None

    # --- Hyperbolic / Parabolic ---
    if e > 1.0:
        return 30  # Hyperbolic
    if e == 1.0:
        return 31  # Parabolic

    # Need a for all remaining classifications
    if a is None:
        if e < 1.0:
            a = q / (1.0 - e)
        else:
            return None

    # Aphelion
    Q = a * (1.0 + e)

    # --- NEO subtypes (q < 1.3 AU or Q < 0.983) ---
    if a < 1.0 and Q < 0.983:
        return 0   # Atira (IEO)
    if a < 1.0 and Q >= 0.983:
        return 1   # Aten
    if a >= 1.0 and q < 1.017:
        return 2   # Apollo
    if a >= 1.0 and 1.017 <= q < 1.3:
        return 3   # Amor

    # --- Mars Crosser: 1 <= a < 3.2, 1.3 < q < 1.666 ---
    if 1.0 <= a < 3.2 and 1.3 < q < 1.666:
        return 10  # Mars Crosser

    # --- Main Belt: 1 <= a < 3.27831, i < 75 ---
    # Checked before Jupiter Coupled: ~5K MBAs have 2 < T_J < 3
    if 1.0 <= a < A_MB_OUTER and (i_deg is not None and i_deg < 75.0):
        return 11  # Main Belt

    # --- Jupiter Trojan: 4.8 < a < 5.4, e < 0.3 ---
    # Checked before Jupiter Coupled: all JTs have 2 < T_J < 3
    if 4.8 < a < 5.4 and e < 0.3:
        return 12  # Jupiter Trojan

    # --- Neptune Trojan: 29.8 < a < 30.4 ---
    # Checked before Centaur/TNO: straddles a_Neptune boundary
    if 29.8 < a < 30.4:
        return 21  # Neptune Trojan

    # --- Jupiter Coupled: a >= 1, 2 < T_J < 3 (requires inclination) ---
    # Checked after geometric types (MB, JT, NepTr all have overlapping T_J)
    if i_deg is not None and a > 0:
        tj = tisserand_jupiter(a, e, i_deg)
        if a >= 1.0 and 2.0 < tj < 3.0:
            return 20  # Jupiter Coupled

    # --- Centaur: a_Jupiter <= a < a_Neptune ---
    if A_JUPITER <= a < A_NEPTUNE:
        return 22  # Centaur

    # --- TNO: a >= a_Neptune ---
    if a >= A_NEPTUNE:
        return 23  # TNO

    # --- Middle Other: a < a_Jupiter, doesn't fit above ---
    if a < A_JUPITER:
        return 19  # Middle Other

    # --- Inner Other: catch-all ---
    return 9   # Inner Other
