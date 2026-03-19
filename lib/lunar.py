"""Lunar position, elongation, and eclipse circumstance classification.

Provides:
- Approximate Moon RA/Dec (~1 degree accuracy, Meeus Ch. 47 truncated)
- Lunar elongation from any sky position
- Lunar eclipse catalog (1990-2027) with penumbral/umbral contact times
- Classification of observations as occurring during a lunar eclipse

The Moon position uses the 10 largest longitude terms and 8 largest
latitude terms from Meeus, "Astronomical Algorithms" (2nd ed.).
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Moon position (simplified Meeus Ch. 47)
# ---------------------------------------------------------------------------

# Longitude terms: (D, M, M', F, coefficient_degrees)
_LONG_TERMS = [
    (0,  0,  1,  0,  +6.288774),
    (2,  0, -1,  0,  +1.274027),
    (2,  0,  0,  0,  +0.658314),
    (0,  0,  2,  0,  +0.213618),
    (0,  1,  0,  0,  -0.185116),
    (0,  0,  0,  2,  -0.114332),
    (2,  0, -2,  0,  +0.058793),
    (2, -1, -1,  0,  +0.057066),
    (2,  0,  1,  0,  +0.053322),
    (2, -1,  0,  0,  +0.045758),
]

# Latitude terms: (D, M, M', F, coefficient_degrees)
_LAT_TERMS = [
    (0,  0,  0,  1,  +5.128122),
    (0,  0,  1,  1,  +0.280602),
    (0,  0,  1, -1,  +0.277693),
    (2,  0,  0, -1,  +0.173237),
    (2,  0, -1,  1,  +0.055413),
    (2,  0, -1, -1,  +0.046271),
    (2,  0,  0,  1,  +0.032573),
    (0,  0,  2,  1,  +0.017198),
]


def moon_ra_dec(obstime_utc):
    """Approximate Moon RA/Dec (J2000, degrees) for an array of UTC times.

    Accuracy ~1 degree, sufficient for elongation and eclipse proximity.

    Parameters
    ----------
    obstime_utc : array-like of datetime64 or pandas Timestamps

    Returns
    -------
    moon_ra, moon_dec : ndarray (degrees)
    """
    t = pd.DatetimeIndex(pd.to_datetime(obstime_utc))
    jd_offset = (t - pd.Timestamp("2000-01-01 12:00:00")
                 ).total_seconds().to_numpy() / 86400.0
    T = jd_offset / 36525.0

    # Fundamental arguments (degrees)
    Lp = (218.3164477 + 481267.88123421 * T
          - 0.0015786 * T**2) % 360
    D = (297.8501921 + 445267.1114034 * T
         - 0.0018819 * T**2) % 360
    M = (357.5291092 + 35999.0502909 * T
         - 0.0001536 * T**2) % 360
    Mp = (134.9633964 + 477198.8675055 * T
          + 0.0087414 * T**2) % 360
    F = (93.2720950 + 483202.0175233 * T
         - 0.0036539 * T**2) % 360

    # Convert to radians for trig
    Dr, Mr, Mpr, Fr = (np.radians(x) for x in (D, M, Mp, F))

    # Sum longitude perturbations
    sigma_l = np.zeros_like(T)
    for d, m, mp, f, coeff in _LONG_TERMS:
        arg = d * Dr + m * Mr + mp * Mpr + f * Fr
        sigma_l += coeff * np.sin(arg)

    # Sum latitude perturbations
    sigma_b = np.zeros_like(T)
    for d, m, mp, f, coeff in _LAT_TERMS:
        arg = d * Dr + m * Mr + mp * Mpr + f * Fr
        sigma_b += coeff * np.sin(arg)

    # Ecliptic coordinates
    ecl_lon = np.radians((Lp + sigma_l) % 360)
    ecl_lat = np.radians(sigma_b)

    # Mean obliquity
    obliquity = np.radians(23.439291 - 0.0130042 * T)

    # Ecliptic to equatorial
    ra = np.degrees(np.arctan2(
        np.sin(ecl_lon) * np.cos(obliquity)
        - np.tan(ecl_lat) * np.sin(obliquity),
        np.cos(ecl_lon))) % 360

    dec = np.degrees(np.arcsin(
        np.sin(ecl_lat) * np.cos(obliquity)
        + np.cos(ecl_lat) * np.sin(obliquity) * np.sin(ecl_lon)))

    return ra, dec


def lunar_elongation(obstime_utc, ra_deg, dec_deg):
    """Angular separation between the Moon and a sky position (degrees).

    Parameters
    ----------
    obstime_utc : array-like of datetime64 or pandas Timestamps
    ra_deg, dec_deg : ndarray (degrees), target position

    Returns
    -------
    elongation : ndarray (degrees)
    """
    moon_ra, moon_dec = moon_ra_dec(obstime_utc)

    ra1 = np.radians(np.asarray(ra_deg, dtype=float))
    dec1 = np.radians(np.asarray(dec_deg, dtype=float))
    ra2 = np.radians(moon_ra)
    dec2 = np.radians(moon_dec)

    cos_elong = (np.sin(dec1) * np.sin(dec2)
                 + np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2))
    return np.degrees(np.arccos(np.clip(cos_elong, -1, 1)))


def moon_altitude(obstime_utc, longitude_deg, latitude_deg):
    """Moon altitude (degrees) for arrays of times and observer locations.

    Parameters
    ----------
    obstime_utc : array-like of datetime64 or pandas Timestamps
    longitude_deg : ndarray, east-positive (MPC convention)
    latitude_deg : ndarray, geodetic degrees

    Returns
    -------
    altitude : ndarray (degrees)
    """
    t = pd.DatetimeIndex(pd.to_datetime(obstime_utc))
    moon_ra, moon_dec = moon_ra_dec(t)

    jd_offset = (t - pd.Timestamp("2000-01-01 12:00:00")
                 ).total_seconds().to_numpy() / 86400.0
    T = jd_offset / 36525.0
    gmst_deg = (280.46061837
                + 360.98564736629 * jd_offset
                + 0.000387933 * T**2) % 360

    lon = np.asarray(longitude_deg, dtype=float)
    lat = np.radians(np.asarray(latitude_deg, dtype=float))
    ha = np.radians((gmst_deg + lon - moon_ra) % 360)
    dec_r = np.radians(moon_dec)

    alt = np.degrees(
        np.arcsin(np.sin(lat) * np.sin(dec_r)
                  + np.cos(lat) * np.cos(dec_r) * np.cos(ha)))
    return alt


# ---------------------------------------------------------------------------
# Lunar eclipse catalog 1990-2027
# ---------------------------------------------------------------------------
# Source: Fred Espenak / EclipseWise.com (Six Millennium Catalog)
# All times UTC (UT1 as published; <0.9s difference from UTC)
#
# Fields: (date_str, type, P1, U1, U2, Greatest, U3, U4, P4)
# Type: T=total, P=partial, N=penumbral
# None = contact does not occur for that eclipse type

def _t(s):
    """Parse 'YYYY-MM-DD HH:MM:SS' to pandas Timestamp (UTC)."""
    if s is None:
        return None
    return pd.Timestamp(s, tz="UTC")


# Each tuple: (type, P1, U1, U2, Greatest, U3, U4, P4)
LUNAR_ECLIPSES = [
    ("T", "1990-02-09 16:21", "1990-02-09 17:29", "1990-02-09 18:50", "1990-02-09 19:11", "1990-02-09 19:32", "1990-02-09 20:53", "1990-02-09 22:01"),
    ("P", "1990-08-06 11:31", "1990-08-06 12:45", None, "1990-08-06 14:12", None, "1990-08-06 15:40", "1990-08-06 16:53"),
    ("N", "1991-01-30 04:00", None, None, "1991-01-30 05:59", None, None, "1991-01-30 07:57"),
    ("N", "1991-06-27 01:50", None, None, "1991-06-27 03:15", None, None, "1991-06-27 04:40"),
    ("N", "1991-07-26 16:52", None, None, "1991-07-26 18:08", None, None, "1991-07-26 19:24"),
    ("P", "1991-12-21 08:27", "1991-12-21 10:01", None, "1991-12-21 10:33", None, "1991-12-21 11:05", "1991-12-21 12:39"),
    ("P", "1992-06-15 02:11", "1992-06-15 03:27", None, "1992-06-15 04:57", None, "1992-06-15 06:27", "1992-06-15 07:43"),
    ("T", "1992-12-09 20:57", "1992-12-09 22:00", "1992-12-09 23:07", "1992-12-09 23:44", "1992-12-10 00:21", "1992-12-10 01:29", "1992-12-10 02:31"),
    ("T", "1993-06-04 10:12", "1993-06-04 11:11", "1993-06-04 12:13", "1993-06-04 13:00", "1993-06-04 13:48", "1993-06-04 14:49", "1993-06-04 15:49"),
    ("T", "1993-11-29 03:29", "1993-11-29 04:41", "1993-11-29 06:03", "1993-11-29 06:26", "1993-11-29 06:49", "1993-11-29 08:12", "1993-11-29 09:23"),
    ("P", "1994-05-25 01:20", "1994-05-25 02:38", None, "1994-05-25 03:30", None, "1994-05-25 04:23", "1994-05-25 05:41"),
    ("N", "1994-11-18 04:28", None, None, "1994-11-18 06:44", None, None, "1994-11-18 09:00"),
    ("P", "1995-04-15 10:10", "1995-04-15 11:42", None, "1995-04-15 12:18", None, "1995-04-15 12:55", "1995-04-15 14:26"),
    ("N", "1995-10-08 14:00", None, None, "1995-10-08 16:04", None, None, "1995-10-08 18:08"),
    ("T", "1996-04-04 21:17", "1996-04-04 22:21", "1996-04-04 23:27", "1996-04-05 00:10", "1996-04-05 00:53", "1996-04-05 01:58", "1996-04-05 03:02"),
    ("T", "1996-09-27 00:14", "1996-09-27 01:13", "1996-09-27 02:20", "1996-09-27 02:54", "1996-09-27 03:29", "1996-09-27 04:36", "1996-09-27 05:35"),
    ("P", "1997-03-24 01:42", "1997-03-24 02:58", None, "1997-03-24 04:39", None, "1997-03-24 06:21", "1997-03-24 07:36"),
    ("T", "1997-09-16 16:12", "1997-09-16 17:08", "1997-09-16 18:16", "1997-09-16 18:47", "1997-09-16 19:17", "1997-09-16 20:25", "1997-09-16 21:21"),
    ("N", "1998-03-13 02:17", None, None, "1998-03-13 04:20", None, None, "1998-03-13 06:23"),
    ("N", "1998-08-08 01:37", None, None, "1998-08-08 02:25", None, None, "1998-08-08 03:13"),
    ("N", "1998-09-06 09:16", None, None, "1998-09-06 11:10", None, None, "1998-09-06 13:04"),
    ("N", "1999-01-31 14:07", None, None, "1999-01-31 16:18", None, None, "1999-01-31 18:28"),
    ("P", "1999-07-28 08:58", "1999-07-28 10:23", None, "1999-07-28 11:34", None, "1999-07-28 12:45", "1999-07-28 14:09"),
    ("T", "2000-01-21 02:04", "2000-01-21 03:02", "2000-01-21 04:05", "2000-01-21 04:44", "2000-01-21 05:22", "2000-01-21 06:25", "2000-01-21 07:23"),
    ("T", "2000-07-16 10:48", "2000-07-16 11:58", "2000-07-16 13:02", "2000-07-16 13:56", "2000-07-16 14:49", "2000-07-16 15:54", "2000-07-16 17:03"),
    ("T", "2001-01-09 17:45", "2001-01-09 18:42", "2001-01-09 19:50", "2001-01-09 20:21", "2001-01-09 20:51", "2001-01-09 21:59", "2001-01-09 22:57"),
    ("P", "2001-07-05 12:12", "2001-07-05 13:35", None, "2001-07-05 14:55", None, "2001-07-05 16:15", "2001-07-05 17:38"),
    ("N", "2001-12-30 08:27", None, None, "2001-12-30 10:29", None, None, "2001-12-30 12:31"),
    ("N", "2002-05-26 10:15", None, None, "2002-05-26 12:03", None, None, "2002-05-26 13:52"),
    ("N", "2002-06-24 20:22", None, None, "2002-06-24 21:27", None, None, "2002-06-24 22:32"),
    ("N", "2002-11-20 23:34", None, None, "2002-11-21 01:47", None, None, "2002-11-21 03:59"),
    ("T", "2003-05-16 01:07", "2003-05-16 02:03", "2003-05-16 03:14", "2003-05-16 03:40", "2003-05-16 04:06", "2003-05-16 05:18", "2003-05-16 06:14"),
    ("T", "2003-11-09 22:17", "2003-11-09 23:33", "2003-11-10 01:07", "2003-11-10 01:19", "2003-11-10 01:30", "2003-11-10 03:05", "2003-11-10 04:21"),
    ("T", "2004-05-04 17:52", "2004-05-04 18:48", "2004-05-04 19:52", "2004-05-04 20:30", "2004-05-04 21:08", "2004-05-04 22:12", "2004-05-04 23:08"),
    ("T", "2004-10-28 00:07", "2004-10-28 01:14", "2004-10-28 02:23", "2004-10-28 03:04", "2004-10-28 03:44", "2004-10-28 04:54", "2004-10-28 06:01"),
    ("N", "2005-04-24 07:52", None, None, "2005-04-24 09:55", None, None, "2005-04-24 11:58"),
    ("P", "2005-10-17 09:53", "2005-10-17 11:35", None, "2005-10-17 12:03", None, "2005-10-17 12:31", "2005-10-17 14:13"),
    ("N", "2006-03-14 21:24", None, None, "2006-03-14 23:48", None, None, "2006-03-15 02:12"),
    ("P", "2006-09-07 16:44", "2006-09-07 18:06", None, "2006-09-07 18:51", None, "2006-09-07 19:37", "2006-09-07 20:59"),
    ("T", "2007-03-03 20:18", "2007-03-03 21:30", "2007-03-03 22:44", "2007-03-03 23:21", "2007-03-03 23:58", "2007-03-04 01:12", "2007-03-04 02:24"),
    ("T", "2007-08-28 07:53", "2007-08-28 08:51", "2007-08-28 09:52", "2007-08-28 10:37", "2007-08-28 11:23", "2007-08-28 12:24", "2007-08-28 13:21"),
    ("T", "2008-02-21 00:36", "2008-02-21 01:43", "2008-02-21 03:01", "2008-02-21 03:26", "2008-02-21 03:51", "2008-02-21 05:09", "2008-02-21 06:16"),
    ("P", "2008-08-16 18:24", "2008-08-16 19:36", None, "2008-08-16 21:10", None, "2008-08-16 22:44", "2008-08-16 23:56"),
    ("N", "2009-02-09 12:38", None, None, "2009-02-09 14:38", None, None, "2009-02-09 16:38"),
    ("N", "2009-07-07 08:38", None, None, "2009-07-07 09:39", None, None, "2009-07-07 10:40"),
    ("N", "2009-08-06 23:04", None, None, "2009-08-07 00:39", None, None, "2009-08-07 02:14"),
    ("P", "2009-12-31 17:17", "2009-12-31 18:52", None, "2009-12-31 19:23", None, "2009-12-31 19:53", "2009-12-31 21:29"),
    ("P", "2010-06-26 08:57", "2010-06-26 10:17", None, "2010-06-26 11:38", None, "2010-06-26 13:00", "2010-06-26 14:20"),
    ("T", "2010-12-21 05:29", "2010-12-21 06:32", "2010-12-21 07:41", "2010-12-21 08:17", "2010-12-21 08:54", "2010-12-21 10:02", "2010-12-21 11:05"),
    ("T", "2011-06-15 17:24", "2011-06-15 18:23", "2011-06-15 19:22", "2011-06-15 20:13", "2011-06-15 21:03", "2011-06-15 22:03", "2011-06-15 23:01"),
    ("T", "2011-12-10 11:33", "2011-12-10 12:45", "2011-12-10 14:06", "2011-12-10 14:32", "2011-12-10 14:58", "2011-12-10 16:18", "2011-12-10 17:30"),
    ("P", "2012-06-04 08:48", "2012-06-04 10:00", None, "2012-06-04 11:03", None, "2012-06-04 12:07", "2012-06-04 13:19"),
    ("N", "2012-11-28 12:15", None, None, "2012-11-28 14:33", None, None, "2012-11-28 16:51"),
    ("P", "2013-04-25 18:03", "2013-04-25 19:53", None, "2013-04-25 20:08", None, "2013-04-25 20:22", "2013-04-25 22:12"),
    ("N", "2013-05-25 03:53", None, None, "2013-05-25 04:10", None, None, "2013-05-25 04:28"),
    ("N", "2013-10-18 21:50", None, None, "2013-10-18 23:50", None, None, "2013-10-19 01:50"),
    ("T", "2014-04-15 04:53", "2014-04-15 05:58", "2014-04-15 07:06", "2014-04-15 07:46", "2014-04-15 08:25", "2014-04-15 09:33", "2014-04-15 10:38"),
    ("T", "2014-10-08 08:15", "2014-10-08 09:14", "2014-10-08 10:25", "2014-10-08 10:55", "2014-10-08 11:24", "2014-10-08 12:35", "2014-10-08 13:34"),
    ("T", "2015-04-04 09:01", "2015-04-04 10:16", "2015-04-04 11:57", "2015-04-04 12:00", "2015-04-04 12:04", "2015-04-04 13:45", "2015-04-04 15:00"),
    ("T", "2015-09-28 00:11", "2015-09-28 01:07", "2015-09-28 02:11", "2015-09-28 02:47", "2015-09-28 03:24", "2015-09-28 04:27", "2015-09-28 05:23"),
    ("N", "2016-03-23 09:39", None, None, "2016-03-23 11:47", None, None, "2016-03-23 13:55"),
    ("N", "2016-09-16 16:55", None, None, "2016-09-16 18:54", None, None, "2016-09-16 20:54"),
    ("N", "2017-02-11 22:34", None, None, "2017-02-12 00:44", None, None, "2017-02-12 02:54"),
    ("P", "2017-08-07 15:50", "2017-08-07 17:23", None, "2017-08-07 18:20", None, "2017-08-07 19:18", "2017-08-07 20:51"),
    ("T", "2018-01-31 10:51", "2018-01-31 11:48", "2018-01-31 12:51", "2018-01-31 13:30", "2018-01-31 14:08", "2018-01-31 15:12", "2018-01-31 16:09"),
    ("T", "2018-07-27 17:14", "2018-07-27 18:24", "2018-07-27 19:30", "2018-07-27 20:22", "2018-07-27 21:14", "2018-07-27 22:19", "2018-07-27 23:29"),
    ("T", "2019-01-21 02:36", "2019-01-21 03:34", "2019-01-21 04:41", "2019-01-21 05:12", "2019-01-21 05:44", "2019-01-21 06:51", "2019-01-21 07:48"),
    ("P", "2019-07-16 18:43", "2019-07-16 20:01", None, "2019-07-16 21:31", None, "2019-07-16 23:00", "2019-07-17 00:18"),
    ("N", "2020-01-10 17:07", None, None, "2020-01-10 19:10", None, None, "2020-01-10 21:13"),
    ("N", "2020-06-05 17:46", None, None, "2020-06-05 19:25", None, None, "2020-06-05 21:05"),
    ("N", "2020-07-05 03:07", None, None, "2020-07-05 04:30", None, None, "2020-07-05 05:53"),
    ("N", "2020-11-30 07:32", None, None, "2020-11-30 09:43", None, None, "2020-11-30 11:54"),
    ("T", "2021-05-26 08:47", "2021-05-26 09:45", "2021-05-26 11:11", "2021-05-26 11:19", "2021-05-26 11:27", "2021-05-26 12:53", "2021-05-26 13:50"),
    ("P", "2021-11-19 06:02", "2021-11-19 07:18", None, "2021-11-19 09:03", None, "2021-11-19 10:48", "2021-11-19 12:04"),
    ("T", "2022-05-16 01:32", "2022-05-16 02:28", "2022-05-16 03:29", "2022-05-16 04:12", "2022-05-16 04:54", "2022-05-16 05:55", "2022-05-16 06:51"),
    ("T", "2022-11-08 08:02", "2022-11-08 09:09", "2022-11-08 10:16", "2022-11-08 10:59", "2022-11-08 11:42", "2022-11-08 12:49", "2022-11-08 13:57"),
    ("N", "2023-05-05 15:14", None, None, "2023-05-05 17:23", None, None, "2023-05-05 19:32"),
    ("P", "2023-10-28 18:01", "2023-10-28 19:35", None, "2023-10-28 20:14", None, "2023-10-28 20:53", "2023-10-28 22:27"),
    ("N", "2024-03-25 04:53", None, None, "2024-03-25 07:13", None, None, "2024-03-25 09:33"),
    ("P", "2024-09-18 00:41", "2024-09-18 02:13", None, "2024-09-18 02:44", None, "2024-09-18 03:16", "2024-09-18 04:48"),
    ("T", "2025-03-14 03:57", "2025-03-14 05:09", "2025-03-14 06:26", "2025-03-14 06:59", "2025-03-14 07:32", "2025-03-14 08:48", "2025-03-14 10:01"),
    ("T", "2025-09-07 15:28", "2025-09-07 16:27", "2025-09-07 17:31", "2025-09-07 18:12", "2025-09-07 18:53", "2025-09-07 19:57", "2025-09-07 20:55"),
    ("T", "2026-03-03 08:44", "2026-03-03 09:50", "2026-03-03 11:04", "2026-03-03 11:34", "2026-03-03 12:03", "2026-03-03 13:17", "2026-03-03 14:23"),
    ("P", "2026-08-28 01:23", "2026-08-28 02:33", None, "2026-08-28 04:13", None, "2026-08-28 05:52", "2026-08-28 07:02"),
    ("N", "2027-02-20 21:12", None, None, "2027-02-20 23:13", None, None, "2027-02-21 01:13"),
    ("N", "2027-07-18 15:54", None, None, "2027-07-18 16:03", None, None, "2027-07-18 16:12"),
    ("N", "2027-08-17 05:24", None, None, "2027-08-17 07:14", None, None, "2027-08-17 09:03"),
]


def _parse_eclipse_catalog():
    """Build structured eclipse data from the catalog.

    Returns list of dicts with Timestamp contacts (UTC-aware).
    """
    eclipses = []
    for row in LUNAR_ECLIPSES:
        etype, p1, u1, u2, greatest, u3, u4, p4 = row
        eclipses.append({
            "type": etype,
            "P1": _t(p1), "U1": _t(u1), "U2": _t(u2),
            "greatest": _t(greatest),
            "U3": _t(u3), "U4": _t(u4), "P4": _t(p4),
        })
    return eclipses


_ECLIPSE_CACHE = None


def _get_eclipses():
    global _ECLIPSE_CACHE
    if _ECLIPSE_CACHE is None:
        _ECLIPSE_CACHE = _parse_eclipse_catalog()
    return _ECLIPSE_CACHE


def classify_eclipse(obstime_utc, longitude_deg, latitude_deg, is_satellite):
    """Classify whether each observation occurred during a lunar eclipse.

    For ground-based sites, the Moon must also be above the horizon.

    Parameters
    ----------
    obstime_utc : array-like of datetime64 or pandas Timestamps
    longitude_deg : ndarray, east-positive (MPC convention)
    latitude_deg : ndarray, geodetic degrees
    is_satellite : ndarray of bool

    Returns
    -------
    eclipse_class : ndarray of str
        "", "Penumbral eclipse", "Partial eclipse", "Total eclipse"
        (the deepest phase occurring at observation time)
    eclipse_date : ndarray of str
        ISO date of the eclipse (e.g., "2004-10-28"), or ""
    """
    eclipses = _get_eclipses()
    t = pd.DatetimeIndex(pd.to_datetime(obstime_utc)).tz_localize("UTC")
    n = len(t)

    eclipse_class = np.full(n, "", dtype=object)
    eclipse_date = np.full(n, "", dtype=object)

    # Compute moon altitude for ground-based sites (vectorized)
    moon_alt = moon_altitude(obstime_utc, longitude_deg, latitude_deg)

    for ecl in eclipses:
        p1 = ecl["P1"]
        p4 = ecl["P4"]
        if p1 is None or p4 is None:
            continue

        # Quick filter: observations within penumbral window
        in_penumbral = (t >= p1) & (t <= p4)
        if not in_penumbral.any():
            continue

        # For ground-based: Moon must be above horizon
        visible = is_satellite | (moon_alt > 0)
        candidates = in_penumbral & visible

        if not candidates.any():
            continue

        # Determine deepest phase at observation time
        date_str = ecl["greatest"].strftime("%Y-%m-%d")
        etype = ecl["type"]

        for idx in np.where(candidates)[0]:
            obs_t = t[idx]

            # Determine phase at this instant
            if (etype == "T" and ecl["U2"] is not None
                    and ecl["U3"] is not None
                    and ecl["U2"] <= obs_t <= ecl["U3"]):
                phase = "Total eclipse"
            elif (etype in ("T", "P") and ecl["U1"] is not None
                    and ecl["U4"] is not None
                    and ecl["U1"] <= obs_t <= ecl["U4"]):
                phase = "Partial eclipse"
            else:
                phase = "Penumbral eclipse"

            # Keep the deepest classification if multiple eclipses overlap
            # (shouldn't happen, but be safe)
            _DEPTH = {"": 0, "Penumbral eclipse": 1,
                      "Partial eclipse": 2, "Total eclipse": 3}
            if _DEPTH.get(phase, 0) > _DEPTH.get(eclipse_class[idx], 0):
                eclipse_class[idx] = phase
                eclipse_date[idx] = date_str

    return eclipse_class, eclipse_date
