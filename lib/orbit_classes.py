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

Reference boundaries (JPL/CNEOS, confirmed against mpc_orbits data):
    Atira (IEO): a < 1.0 AU, Q < 0.983 AU  (aphelion inside Earth perihelion)
    Aten:        a < 1.0 AU, Q >= 0.983 AU  (Earth-crossing, a < 1)
    Apollo:      a >= 1.0 AU, q <= 1.017 AU (Earth-crossing, a >= 1)
    Amor:        a >= 1.0 AU, 1.017 < q <= 1.3 AU
    Mars-crossing: 1.3 <= q < 1.666 AU (approximate)
    Main Belt: 2.0 < a < 3.3 AU (approximate)

MPC orbit_type_int mapping (verified Feb 2026):
    0=Atira/IEO, 1=Aten, 2=Apollo, 3=Amor, 10=Mars-X, 11=MB,
    12=Hungaria, 19=JT, 20=Dual, 21=Centaur, 22=TNO, 23=SDO, 30=Comet
"""

import math

# Jupiter's semi-major axis (AU) for Tisserand parameter
A_JUPITER = 5.2026


# ---------------------------------------------------------------------------
# orbit_type_int -> (short_name, long_name, hex_color)
# ---------------------------------------------------------------------------

ORBIT_TYPES = {
    0:    ("Atira",   "Atira",                    "#e6194b"),
    1:    ("Aten",    "Aten",                     "#d62728"),
    2:    ("Apollo",  "Apollo",                   "#f58231"),
    3:    ("Amor",    "Amor",                     "#ffe119"),
    10:   ("Mars-X",  "Mars-crossing",            "#3cb44b"),
    11:   ("MB",      "Main Belt",                "#4363d8"),
    12:   ("Hungaria","Hungaria",                 "#42d4f4"),
    13:   ("Phocaea", "Phocaea",                  "#469990"),
    14:   ("Hilda",   "Hilda",                    "#aaffc3"),
    19:   ("JT",      "Jupiter Trojan",           "#9A6324"),
    20:   ("Dual",    "Dual-status (NEO/comet)",  "#800000"),
    21:   ("Centaur", "Centaur",                  "#808000"),
    22:   ("TNO",     "Trans-Neptunian Object",   "#000075"),
    23:   ("SDO",     "Scattered Disk Object",    "#a9a9a9"),
    30:   ("Comet",   "Comet-like",               "#f032e6"),
    None: ("Unclass", "Unclassified",             "#bfbfbf"),
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
    order = [0, 1, 2, 3, 10, 11, 12, 13, 14, 19, 20, 21, 22, 23, 30, None]
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
    Recover orbit classification from orbital elements.

    Uses standard dynamical boundaries to assign an orbit_type_int for
    objects where the database value is NULL.  Returns the orbit_type_int
    that would be assigned, or None if classification is ambiguous.

    Parameters
    ----------
    a : float
        Semi-major axis in AU.
    e : float
        Eccentricity.
    i_deg : float
        Inclination in degrees.
    q : float
        Perihelion distance in AU.

    Returns
    -------
    int or None
        The inferred orbit_type_int.
    """
    if a is None or e is None or q is None:
        return None

    # Aphelion
    Q = a * (1.0 + e)

    # NEO subtypes (q < 1.3 AU or Q < 0.983)
    if a < 1.0 and Q < 0.983:
        return 0   # Atira (IEO)
    if a < 1.0 and Q >= 0.983:
        return 1   # Aten
    if a >= 1.0 and q <= 1.017:
        return 2   # Apollo
    if 1.017 < q < 1.3:
        return 3   # Amor

    # Mars-crossing (approximate)
    if 1.3 <= q < 1.666:
        return 10  # Mars-crossing

    # Compute Tisserand for comet discrimination
    if i_deg is not None:
        tj = tisserand_jupiter(a, e, i_deg)
    else:
        tj = None

    # Main Belt and neighbors
    if 1.78 <= a <= 2.0 and e < 0.18 and (i_deg is not None and 16 <= i_deg <= 34):
        return 12  # Hungaria
    if 2.0 < a < 3.3 and e < 0.4:
        return 11  # Main Belt
    if 3.7 < a < 4.1 and e < 0.3:
        return 14  # Hilda

    # Jupiter Trojans (near 5.2 AU, moderate e)
    if 4.6 < a < 5.5 and e < 0.3:
        return 19  # Jupiter Trojan

    # Distant objects
    if a > 30:
        if e > 0.2:
            return 23  # SDO
        return 22  # TNO
    if 5.5 < a <= 30:
        return 21  # Centaur

    # Comet-like (high eccentricity, low Tisserand)
    if tj is not None and tj < 2.0 and e > 0.9:
        return 30  # Comet-like

    return None
