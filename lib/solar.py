"""Solar position and twilight classification for observatory sites.

Provides vectorised (numpy) computation of the Sun's altitude at a given
UTC time and geographic location, and classifies each observation into a
twilight category.

The Sun position uses the same low-order VSOP87-style approximation
already used for solar elongation in the app (good to ~1° over the
timespan of NEO discovery data, ample for twilight binning at 6° steps).
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Twilight altitude thresholds (degrees)
# ---------------------------------------------------------------------------
TWILIGHT_BINS = [
    ("Nighttime",              None,  -18.0),
    ("Astronomical twilight",  -18.0, -12.0),
    ("Nautical twilight",      -12.0,  -6.0),
    ("Civil twilight",          -6.0,   0.0),
    ("Daytime",                  0.0,  None),
]

# Canonical ordering for display (darkest first)
TWILIGHT_ORDER = [label for label, _, _ in TWILIGHT_BINS]
# Prepend space-based as a separate category
TWILIGHT_ORDER = ["Space-based"] + TWILIGHT_ORDER + ["Unknown site"]


def _observer_latitude(rhocosphi, rhosinphi):
    """Geodetic latitude (degrees) from MPC parallax constants.

    The MPC obscodes table stores geocentric rho*cos(phi') and
    rho*sin(phi') where phi' is the geocentric latitude.  For our
    purposes (solar altitude to ~1°) geocentric latitude is fine.
    """
    return np.degrees(np.arctan2(rhosinphi, rhocosphi))


def sun_ra_dec(obstime_utc):
    """Approximate Sun RA/Dec (J2000, degrees) for an array of UTC datetimes.

    Parameters
    ----------
    obstime_utc : array-like of datetime64 or pandas Timestamps

    Returns
    -------
    sun_ra, sun_dec : ndarray (degrees)
    """
    t = pd.DatetimeIndex(pd.to_datetime(obstime_utc))
    # Days since J2000.0 (2000-01-01 12:00 UTC)
    jd_offset = (t - pd.Timestamp("2000-01-01 12:00:00")
                 ).total_seconds().to_numpy() / 86400.0
    T = jd_offset / 36525.0

    L0 = (280.466 + 36000.77 * T) % 360
    M = np.radians((357.529 + 35999.05 * T) % 360)
    C = 1.915 * np.sin(M) + 0.020 * np.sin(2 * M)
    sun_lon = np.radians((L0 + C) % 360)
    obliquity = np.radians(23.439 - 0.013 * T)

    ra = np.degrees(np.arctan2(
        np.cos(obliquity) * np.sin(sun_lon),
        np.cos(sun_lon))) % 360
    dec = np.degrees(np.arcsin(
        np.sin(obliquity) * np.sin(sun_lon)))
    return ra, dec


def sun_altitude(obstime_utc, longitude_deg, latitude_deg):
    """Sun altitude (degrees) for arrays of times and observer locations.

    Parameters
    ----------
    obstime_utc : array-like of datetime64 or pandas Timestamps
    longitude_deg : ndarray, east-positive (MPC convention)
    latitude_deg : ndarray, geodetic degrees

    Returns
    -------
    altitude : ndarray (degrees), NaN where inputs are missing
    """
    t = pd.DatetimeIndex(pd.to_datetime(obstime_utc))
    sun_ra, sun_dec = sun_ra_dec(t)

    # Greenwich Mean Sidereal Time (degrees)
    # Julian centuries since J2000.0
    jd_offset = (t - pd.Timestamp("2000-01-01 12:00:00")
                 ).total_seconds().to_numpy() / 86400.0
    # GMST at 0h UT + Earth rotation for fractional day
    # Meeus, Astronomical Algorithms, eq. 12.4
    T = jd_offset / 36525.0
    gmst_deg = (280.46061837
                + 360.98564736629 * jd_offset
                + 0.000387933 * T**2) % 360

    # Local hour angle of the Sun
    lon = np.asarray(longitude_deg, dtype=float)
    lat = np.radians(np.asarray(latitude_deg, dtype=float))
    ha = np.radians((gmst_deg + lon - sun_ra) % 360)

    dec_r = np.radians(sun_dec)
    alt = np.degrees(
        np.arcsin(np.sin(lat) * np.sin(dec_r)
                  + np.cos(lat) * np.cos(dec_r) * np.cos(ha)))
    return alt


def classify_twilight(sun_alt, is_satellite):
    """Assign a twilight category to each observation.

    Parameters
    ----------
    sun_alt : ndarray of float (degrees), may contain NaN
    is_satellite : ndarray of bool

    Returns
    -------
    categories : ndarray of str
    """
    cats = np.full(len(sun_alt), "", dtype=object)
    cats[is_satellite] = "Space-based"

    ground = ~is_satellite
    alt = np.asarray(sun_alt, dtype=float)

    for label, lo, hi in TWILIGHT_BINS:
        if lo is None and hi is not None:
            mask = ground & (alt < hi)
        elif hi is None and lo is not None:
            mask = ground & (alt >= lo)
        else:
            mask = ground & (alt >= lo) & (alt < hi)
        cats[mask] = label

    # NaN altitude on ground stations (geocentric, roving) → unknown site
    cats[ground & np.isnan(alt)] = "Unknown site"
    return cats
