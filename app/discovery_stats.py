"""
NEO Discovery Statistics — Interactive Dash Explorer

Stacked bar chart of NEO discoveries by year and survey, with drill-down
by size class, survey grouping, and cumulative views.  Data sourced from
the MPC/SBN PostgreSQL database (mpc_orbits + obs_sbn).

Usage:
    source venv/bin/activate.csh
    python app/discovery_stats.py

Then open http://127.0.0.1:8050/ in a browser.
"""

import hashlib
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import dash
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.dcc import send_data_frame
from dash.exceptions import PreventUpdate
from plotly.subplots import make_subplots

from lib.db import connect, timed_query
from lib.mpec_parser import (fetch_recent_mpecs, fetch_mpec_detail,
                              mpec_id_to_url, lookup_mpecs_by_designation)
from mpc_designation import pack as pack_designation, unpack as unpack_designation
from lib.nea_catalog import load_nea_h_lookup
from lib.identifications import resolve_designation
from lib.api_clients import (
    fetch_sbdb, fetch_sentry, fetch_neofixer_orbit, fetch_neocc_risk,
    fetch_neofixer_ephem, fetch_neofixer_ades, resolve_mps_url,
    _load_mps_bundles,
)
try:
    from lib.api_clients import check_service_health
except ImportError:
    def check_service_health():
        return {"NEOfixer": False, "MPC": True, "JPL": False,
                "Sentry": False, "NEOCC": False}

# ---------------------------------------------------------------------------
# Data constants
# ---------------------------------------------------------------------------

# Cache file includes a hash of the SQL so it auto-invalidates on query changes
_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Station code -> readable name (top discovery sites only)
STATION_NAMES = {
    "703": "Catalina",
    "G96": "Mt. Lemmon",
    "E12": "Siding Spring",
    "I52": "Mt. Lemmon-Steward",
    "V06": "CSS-Kuiper",
    "G84": "Mt. Lemmon SkyCenter",
    "V00": "Kitt Peak-Bok",
    "X05": "Rubin",
    "F51": "Pan-STARRS 1",
    "F52": "Pan-STARRS 2",
    "T05": "ATLAS-HKO",
    "T08": "ATLAS-MLO",
    "T03": "ATLAS-Sutherland",
    "M22": "ATLAS-El Sauce",
    "W68": "ATLAS-Río Hurtado",
    "R17": "ATLAS-TDO",
    "704": "LINEAR",
    "699": "LONEOS",
    "691": "Spacewatch",
    "291": "Spacewatch II",
    "644": "NEAT-Palomar",
    "608": "NEAT-Haleakala",
    "I41": "ZTF",
    "C51": "WISE/NEOWISE",
    "C57": "WISE/NEOWISE",
    "W84": "DECam",
    "U68": "SynTrack",
    "U74": "SynTrack 2",
}

# Station code -> project (for grouped view)
# Groupings match CNEOS site_all.json definitions
STATION_TO_PROJECT = {
    "704": "LINEAR", "G45": "LINEAR", "P07": "LINEAR",
    "566": "NEAT", "608": "NEAT", "644": "NEAT",
    "691": "Spacewatch", "291": "Spacewatch",
    "699": "LONEOS",
    "703": "Catalina Survey", "E12": "Catalina Survey",
    "G96": "Catalina Survey",
    "I52": "Catalina Follow-up", "V06": "Catalina Follow-up",
    "G84": "Catalina Follow-up",
    "V00": "Bok NEO Survey",
    "F51": "Pan-STARRS", "F52": "Pan-STARRS",
    "C51": "NEOWISE", "C57": "NEOWISE",
    "T05": "ATLAS", "T07": "ATLAS", "T08": "ATLAS",
    "T03": "ATLAS", "M22": "ATLAS", "W68": "ATLAS", "R17": "ATLAS",
    "X05": "Rubin/LSST",
    "I41": "Other-US", "U68": "Other-US", "U74": "Other-US",
    "W84": "Other-US",
}

# Reverse mapping: project -> list of station codes
PROJECT_STATIONS = {}
for _stn, _proj in STATION_TO_PROJECT.items():
    PROJECT_STATIONS.setdefault(_proj, []).append(_stn)

# Stacking order matches CNEOS (bottom to top in the bar chart).
# Plotly stacks traces in list order, so first entry = bottom of stack.
PROJECT_ORDER = [
    "LINEAR",
    "NEAT",
    "Spacewatch",
    "LONEOS",
    "Catalina Survey",
    "Catalina Follow-up",
    "Pan-STARRS",
    "NEOWISE",
    "ATLAS",
    "Bok NEO Survey",
    "Rubin/LSST",
    "Other-US",
    "Others",
]

# Colors match CNEOS site_all.json exactly
PROJECT_COLORS = {
    "LINEAR": "#4363d8",
    "NEAT": "#f58231",
    "Spacewatch": "#e6194B",
    "LONEOS": "#ffe119",
    "Catalina Survey": "#3cb44b",
    "Catalina Follow-up": "#aaffc3",
    "Pan-STARRS": "#f032e6",
    "NEOWISE": "#469990",
    "ATLAS": "#42d4f4",
    "Bok NEO Survey": "#dcbeff",
    "Rubin/LSST": "#800000",
    "Other-US": "#9A6324",
    "Others": "#d4bc9a",
}

# H magnitude size classes (standard p_v = 0.14 boundaries)
H_BINS = [
    ("H < 17.75 (~1 km+)", None, 17.75),
    ("17.75 \u2264 H < 22 (~140 m\u20131 km)", 17.75, 22),
    ("22 \u2264 H < 24.25 (~50\u2013140 m)", 22, 24.25),
    ("24.25 \u2264 H < 27.75 (~10\u201350 m)", 24.25, 27.75),
    ("H \u2265 27.75 (< 10 m)", 27.75, None),
]

# Colors for size-class stacking (viridis palette, matching size histogram)
SIZE_COLORS = ["#440154", "#31688e", "#35b779", "#90d743", "#fde725"]

# ---------------------------------------------------------------------------
# Ecliptic and galactic plane coordinates for sky map overlays
# ---------------------------------------------------------------------------

# Ecliptic plane: parametric (RA, Dec) from ecliptic longitude 0→360°
_ECL_LON = np.linspace(0, 360, 361)
_OBLIQUITY = 23.44  # degrees
_ECL_RA_360 = np.degrees(np.arctan2(
    np.sin(np.radians(_ECL_LON)) * np.cos(np.radians(_OBLIQUITY)),
    np.cos(np.radians(_ECL_LON)),
)) % 360
_ECL_DEC = np.degrees(np.arcsin(
    np.sin(np.radians(_ECL_LON)) * np.sin(np.radians(_OBLIQUITY))
))

# Galactic plane (b=0): standard J2000 rotation matrix (Hipparcos/IAU).
# Columns are galactic x̂, ŷ, ẑ (=NGP) basis vectors in equatorial coords.
# Verified: GC at (266.4°, -28.9°), NGP at (192.86°, 27.13°).
_R_GAL_TO_EQ = np.array([
    [-0.05487554,  0.49410943, -0.86766615],
    [-0.87343711, -0.44482963, -0.19807637],
    [-0.48383502,  0.74698224,  0.45598378],
])
_GAL_L_RAD = np.radians(np.linspace(0, 360, 361))
_gal_xyz = np.vstack([np.cos(_GAL_L_RAD), np.sin(_GAL_L_RAD),
                       np.zeros_like(_GAL_L_RAD)])
_eq_xyz = _R_GAL_TO_EQ @ _gal_xyz
_GAL_DEC = np.degrees(np.arcsin(np.clip(_eq_xyz[2], -1, 1)))
_GAL_RA_360 = np.degrees(np.arctan2(_eq_xyz[1], _eq_xyz[0])) % 360

# Convert RA from [0,360) to centered (-180,180] for sky map display
# Convention: 180° (East) on left, 0° center, -180° (West) on right


def _ra_to_centered(ra):
    """Map RA from [0, 360) to (-180, 180]: values > 180 become negative."""
    return np.where(ra > 180, ra - 360, ra)


def _split_at_wraparound(ra, dec, threshold=90):
    """Insert NaN where RA jumps by more than threshold degrees."""
    out_ra, out_dec = [ra[0]], [dec[0]]
    for i in range(1, len(ra)):
        if abs(ra[i] - ra[i - 1]) > threshold:
            out_ra.append(np.nan)
            out_dec.append(np.nan)
        out_ra.append(ra[i])
        out_dec.append(dec[i])
    return np.array(out_ra), np.array(out_dec)


ECL_RA, ECL_DEC = _split_at_wraparound(
    _ra_to_centered(_ECL_RA_360), _ECL_DEC)
GAL_RA, GAL_DEC = _split_at_wraparound(
    _ra_to_centered(_GAL_RA_360), _GAL_DEC)

# ---------------------------------------------------------------------------
# NEOMOD3 population model (Nesvorny et al. 2024, Icarus 411, Table 3)
# Half-magnitude bins: (H1, H2, dN, N_cumulative, N_min, N_max)
# dN = estimated NEOs in bin; N = cumulative N(H < H2)
# N_min/N_max = 1-sigma bounds on cumulative
# ---------------------------------------------------------------------------

NEOMOD3_BINS = [
    # H1      H2     dN       N(H2)    N_min    N_max
    (15.25, 15.75,    61,      130,      124,      137),
    (15.75, 16.25,   104,      234,      219,      250),
    (16.25, 16.75,   156,      390,      365,      416),
    (16.75, 17.25,   218,      608,      579,      639),
    (17.25, 17.75,   328,      936,      898,      977),
    (17.75, 18.25,   513,     1450,     1400,     1510),
    (18.25, 18.75,   790,     2240,     2170,     2320),
    (18.75, 19.25,  1170,     3410,     3310,     3500),
    (19.25, 19.75,  1640,     5050,     4920,     5170),
    (19.75, 20.25,  2160,     7210,     7030,     7370),
    (20.25, 20.75,  2720,     9920,     9700,    10100),
    (20.75, 21.25,  3500,    13400,    13100,    13700),
    (21.25, 21.75,  4710,    18100,    17800,    18500),
    (21.75, 22.25,  6730,    24900,    24400,    25400),
    (22.25, 22.75, 10400,    35300,    34500,    36000),
    (22.75, 23.25, 17300,    52500,    51400,    53600),
    (23.25, 23.75, 31100,    83600,    81800,    85300),
    (23.75, 24.25, 60800,   144000,   142000,   147000),
    (24.25, 24.75,121000,   266000,   260000,   272000),
    (24.75, 25.25,229000,   494000,   482000,   506000),
    (25.25, 25.75,411000,   905000,   882000,   928000),
    (25.75, 26.25,728000,  1630000,  1590000,  1680000),
    (26.25, 26.75,1290000, 2920000,  2840000,  3000000),
    (26.75, 27.25,2250000, 5170000,  5000000,  5340000),
    (27.25, 27.75,3950000, 9120000,  8750000,  9490000),
]

NEOMOD3_DF = pd.DataFrame(
    NEOMOD3_BINS,
    columns=["h1", "h2", "dn_model", "n_cumul", "n_min", "n_max"],
)
NEOMOD3_DF["h_center"] = (NEOMOD3_DF["h1"] + NEOMOD3_DF["h2"]) / 2
NEOMOD3_DF["bin_label"] = NEOMOD3_DF.apply(
    lambda r: f"{r['h1']:.2f}\u2013{r['h2']:.2f}", axis=1
)

# Half-magnitude bin edges for digitizing discovered NEO H values
H_BIN_EDGES = np.arange(15.25, 28.25, 0.5)
H_BIN_CENTERS = (H_BIN_EDGES[:-1] + H_BIN_EDGES[1:]) / 2

# ---------------------------------------------------------------------------
# Size reference lines: H magnitude for selected diameter thresholds
# Standard uses fixed p_v = 0.14 (Harris & Chodas 2021).
# NEOMOD3 uses size-dependent debiased albedos (Nesvorny et al. 2024,
#   arXiv:2404.18805): p_v,ref ~ 0.15 for H<18, ~0.16 for 18<H<22,
#   ~0.18 for H>22.
# ---------------------------------------------------------------------------
SIZE_REFS = {
    "standard": [
        (16.25, "2 km"),
        (17.75, "1 km"),
        (19.25, "500 m"),
        (20.75, "250 m"),
        (22.0,  "140 m"),
        (22.75, "100 m"),
        (24.25, "50 m"),
        (26.25, "20 m"),
        (27.75, "10 m"),
    ],
    "neomod3": [
        (16.2, "2 km"),
        (17.7, "1 km"),
        (19.1, "500 m"),
        (20.6, "250 m"),
        (21.9, "140 m"),
        (22.5, "100 m"),
        (24.0, "50 m"),
        (26.0, "20 m"),
        (27.5, "10 m"),
    ],
}
# Index of the 140m entry in SIZE_REFS lists (for completeness annotation)
_140M_IDX = 4

# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------

THEMES = {
    "dark": dict(
        template="plotly_dark",
        paper="#1e1e1e",
        plot="#1e1e1e",
        page="#1e1e1e",
        text="#e0e0e0",
        subtext="#888888",
        control_text="#cccccc",
        input_text="#dddddd",
        mark_color="#aaaaaa",
        table_header="#333333",
        table_cell="#1e1e1e",
        table_font="#dddddd",
        model_outline="white",
        hr_color="#444444",
    ),
    "light": dict(
        template="plotly_white",
        paper="white",
        plot="white",
        page="#f5f5f5",
        text="#222222",
        subtext="#555555",
        control_text="#333333",
        input_text="#222222",
        mark_color="#555555",
        table_header="#e0e0e0",
        table_cell="#ffffff",
        table_font="#222222",
        model_outline="#333333",
        hr_color="#cccccc",
    ),
}


def theme(name):
    return THEMES.get(name, THEMES["light"])


# Customize Plotly templates: dark-mode hover labels and spike lines
pio.templates["plotly_dark"].layout.update(
    hoverlabel=dict(bgcolor="#2a2a2a", font_color="#e0e0e0",
                    bordercolor="#555555"),
    xaxis_spikecolor="#888888",
    yaxis_spikecolor="#888888",
)
pio.templates["plotly_white"].layout.update(
    hoverlabel=dict(bgcolor="white", font_color="#222222",
                    bordercolor="#cccccc"),
    xaxis_spikecolor="#999999",
    yaxis_spikecolor="#999999",
)


# Plotly modebar config — enable PNG download with 2x resolution
GRAPH_CONFIG = {
    "toImageButtonOptions": {
        "format": "png",
        "scale": 2,
    },
    "displaylogo": False,
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

LOAD_SQL = """
WITH neo_list AS (
    SELECT
        mo.packed_primary_provisional_designation AS packed_desig,
        mo.unpacked_primary_provisional_designation AS unpacked_desig,
        ni.permid IS NOT NULL AS is_numbered,
        ni.permid AS asteroid_number,
        CASE WHEN ni.permid IS NULL
             THEN mo.unpacked_primary_provisional_designation
        END AS provisional_desig,
        ni.unpacked_primary_provisional_designation AS num_provid,
        mo.h,
        mo.orbit_type_int,
        mo.q, mo.e, mo.i
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
        ON ni.packed_primary_provisional_designation
         = mo.packed_primary_provisional_designation
    WHERE mo.q <= 1.30
),
discovery_obs_all AS (
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),
discovery_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obsid, NULLIF(trkid, '') AS trkid, obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),
tracklet_obs_all AS (
    SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn obs ON obs.trkid = di.trkid
    WHERE di.trkid IS NOT NULL
      AND ABS(EXTRACT(EPOCH FROM (obs.obstime - di.obstime))) / 3600.0 <= 12.0
    UNION ALL
    SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn obs ON obs.obsid = di.obsid
    WHERE di.trkid IS NULL
),
discovery_tracklet_stats AS (
    SELECT
        unpacked_desig,
        AVG(ra) AS avg_ra_deg,
        AVG(dec) AS avg_dec_deg,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            mag + CASE band
                WHEN 'V' THEN 0.0
                WHEN 'v' THEN 0.0
                WHEN 'B' THEN -0.8
                WHEN 'U' THEN -1.3
                WHEN 'R' THEN 0.4
                WHEN 'I' THEN 0.8
                WHEN 'g' THEN -0.35
                WHEN 'r' THEN 0.14
                WHEN 'i' THEN 0.32
                WHEN 'z' THEN 0.26
                WHEN 'y' THEN 0.32
                WHEN 'u' THEN 2.5
                WHEN 'w' THEN -0.13
                WHEN 'c' THEN -0.05
                WHEN 'o' THEN 0.33
                WHEN 'G' THEN 0.28
                WHEN 'J' THEN 1.2
                WHEN 'H' THEN 1.4
                WHEN 'K' THEN 1.7
                WHEN 'C' THEN 0.4
                WHEN 'W' THEN 0.4
                WHEN 'L' THEN 0.2
                WHEN 'Y' THEN 0.7
                WHEN '' THEN -0.8
                ELSE 0.0
            END
        ) FILTER (WHERE mag IS NOT NULL) AS median_v_mag,
        COUNT(*) AS nobs,
        EXTRACT(EPOCH FROM (MAX(obstime) - MIN(obstime))) / 86400.0
            AS span_days,
        (array_agg(ra  ORDER BY obstime ASC))[1]  AS first_ra,
        (array_agg(dec ORDER BY obstime ASC))[1]  AS first_dec,
        (array_agg(ra  ORDER BY obstime DESC))[1] AS last_ra,
        (array_agg(dec ORDER BY obstime DESC))[1] AS last_dec
    FROM tracklet_obs_all
    GROUP BY unpacked_desig
)
SELECT
    di.unpacked_desig AS designation,
    EXTRACT(YEAR FROM di.obstime)::int AS disc_year,
    EXTRACT(MONTH FROM di.obstime)::int AS disc_month,
    di.obstime::date AS disc_date,
    di.stn AS station_code,
    neo.h,
    neo.orbit_type_int,
    neo.q, neo.e, neo.i,
    dts.avg_ra_deg,
    dts.avg_dec_deg,
    dts.median_v_mag,
    dts.nobs AS tracklet_nobs,
    CASE WHEN dts.span_days > 0 THEN
        2.0 * DEGREES(ASIN(SQRT(
            SIN(RADIANS(dts.last_dec - dts.first_dec) / 2.0) ^ 2
            + COS(RADIANS(dts.first_dec)) * COS(RADIANS(dts.last_dec))
              * SIN(RADIANS(dts.last_ra - dts.first_ra) / 2.0) ^ 2
        ))) / dts.span_days
    END AS rate_deg_per_day,
    CASE WHEN dts.span_days > 0 THEN
        (360.0 + DEGREES(ATAN2(
            SIN(RADIANS(dts.last_ra - dts.first_ra))
                * COS(RADIANS(dts.last_dec)),
            COS(RADIANS(dts.first_dec)) * SIN(RADIANS(dts.last_dec))
            - SIN(RADIANS(dts.first_dec)) * COS(RADIANS(dts.last_dec))
              * COS(RADIANS(dts.last_ra - dts.first_ra))
        )))::numeric % 360.0
    END AS position_angle_deg
FROM discovery_info di
JOIN neo_list neo ON neo.unpacked_desig = di.unpacked_desig
LEFT JOIN discovery_tracklet_stats dts
    ON dts.unpacked_desig = di.unpacked_desig
ORDER BY di.obstime
"""


APPARITION_SQL = """
WITH neo_list AS MATERIALIZED (
    SELECT
        mo.unpacked_primary_provisional_designation AS unpacked_desig,
        ni.permid IS NOT NULL AS is_numbered,
        ni.permid AS asteroid_number,
        CASE WHEN ni.permid IS NULL
             THEN mo.unpacked_primary_provisional_designation
        END AS provisional_desig,
        ni.unpacked_primary_provisional_designation AS num_provid
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
        ON ni.packed_primary_provisional_designation
         = mo.packed_primary_provisional_designation
    WHERE mo.q <= 1.30
),
discovery_obs_all AS (
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),
discovery_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),
neo_discovery AS MATERIALIZED (
    SELECT
        di.unpacked_desig AS designation,
        di.obstime AS disc_obstime,
        neo.asteroid_number,
        COALESCE(neo.provisional_desig, neo.num_provid) AS provid_key
    FROM discovery_info di
    JOIN neo_list neo ON neo.unpacked_desig = di.unpacked_desig
)
SELECT nd.designation, o.station_code, nd.disc_obstime,
       o.first_obs, o.first_post_disc
FROM neo_discovery nd
CROSS JOIN LATERAL (
    SELECT stn AS station_code,
           MIN(obstime) AS first_obs,
           MIN(CASE WHEN obstime >= nd.disc_obstime
                    THEN obstime END) AS first_post_disc
    FROM obs_sbn
    WHERE (permid = nd.asteroid_number OR provid = nd.provid_key)
      AND obstime BETWEEN nd.disc_obstime - INTERVAL '200 days'
                    AND nd.disc_obstime + INTERVAL '200 days'
    GROUP BY stn
) o
"""

CACHE_MAX_AGE_SEC = 86400  # 1 day

# Parse flags once at import time (prevent reloader from re-querying)
_REFRESH_ONLY = "--refresh-only" in sys.argv
if _REFRESH_ONLY:
    sys.argv.remove("--refresh-only")
_FORCE_REFRESH = _REFRESH_ONLY or "--refresh" in sys.argv
if "--refresh" in sys.argv:
    sys.argv.remove("--refresh")
_HOST = "127.0.0.1"
if "--host" in sys.argv:
    idx = sys.argv.index("--host")
    _HOST = sys.argv[idx + 1]
    del sys.argv[idx:idx + 2]
_DEBUG = "--debug" in sys.argv
if _DEBUG:
    sys.argv.remove("--debug")
_MAINTENANCE_MSG = None
if "--maintenance" in sys.argv:
    idx = sys.argv.index("--maintenance")
    if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
        _MAINTENANCE_MSG = sys.argv[idx + 1]
        del sys.argv[idx:idx + 2]
    else:
        _MAINTENANCE_MSG = "System maintenance in progress. Some features may be temporarily unavailable."
        del sys.argv[idx:idx + 1]


def _load_cached_query(sql, prefix, label):
    """Load query result from cache file or database.

    Returns (DataFrame, meta_file_path).
    """
    sql_hash = hashlib.md5(sql.encode()).hexdigest()[:8]
    cache_file = os.path.join(_APP_DIR, f".{prefix}_{sql_hash}.csv")
    meta_file = cache_file.replace(".csv", ".meta")

    use_cache = False
    if not _FORCE_REFRESH and os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < CACHE_MAX_AGE_SEC:
            use_cache = True
            print(f"Loading cached {label} from {cache_file} "
                  f"(age: {age/3600:.1f} h)")
        else:
            print(f"{label} cache is {age/3600:.1f} h old "
                  "\u2014 refreshing")
    elif _FORCE_REFRESH:
        print(f"--refresh: re-querying {label}")

    if use_cache:
        return pd.read_csv(cache_file), meta_file

    print(f"Querying database for {label}...")
    from datetime import datetime, timezone
    query_time = datetime.now(timezone.utc)
    with connect() as conn:
        result = timed_query(conn, sql, label=label)
    result.to_csv(cache_file, index=False)
    with open(meta_file, "w") as f:
        f.write(query_time.strftime("%Y-%m-%d %H:%M UTC"))
    print(f"Cached {len(result):,} rows to {cache_file}")
    return result, meta_file


def load_data():
    """Load NEO discovery data from DB or cache (refreshed daily)."""
    raw, meta_file = _load_cached_query(
        LOAD_SQL, "neo_cache", "NEO discoveries")

    # Sanitize H magnitude: sentinel values (0, -9.99) in mpc_orbits
    # represent missing data, not real measurements.  Treat as unknown.
    raw.loc[raw["h"] <= 0, "h"] = np.nan

    # Override H with NEA.txt values where available.
    # NEA.txt is the MPC's curated NEA catalog and is currently the most
    # reliable H source.  When MPC finishes mpc_orbits cleanup, this
    # override can be removed.
    #
    # Three cases for each object:
    #   - In NEA.txt with valid H  -> use NEA.txt H
    #   - In NEA.txt with H=99.99  -> set H to NaN (unreliable)
    #   - Not in NEA.txt at all    -> NaN for asteroids; keep mpc_orbits H
    #     only for comets and borderline objects (q > 1.30) that aren't
    #     expected to appear in the curated NEA catalog
    try:
        h_lookup = load_nea_h_lookup(_APP_DIR, force_refresh=_FORCE_REFRESH)
        raw["h_mpc"] = raw["h"]  # preserve original for reference
        raw["in_nea_catalog"] = raw["designation"].isin(h_lookup)

        def _resolve_h(row):
            desig = row["designation"]
            if desig in h_lookup:
                val = h_lookup[desig]
                if val is not None:
                    return val  # NEA.txt has a valid H
                return np.nan  # NEA.txt says H=99.99 (unreliable)
            # Not in NEA.txt — keep H only for comets and borderline
            q = row.get("q", 0)
            desig_str = str(desig)
            is_comet = desig_str.startswith(("C/", "P/", "D/"))
            is_borderline = q > 1.30
            if is_comet or is_borderline:
                return row["h_mpc"]
            return np.nan  # asteroid not in NEA catalog

        raw["h_nea"] = raw.apply(_resolve_h, axis=1)
        raw["h"] = raw["h_nea"]

        n_in_nea = raw["in_nea_catalog"].sum()
        n_changed = ((raw["h"] != raw["h_mpc"])
                     | (raw["h"].isna() != raw["h_mpc"].isna())).sum()
        n_nulled = (raw["h"].isna() & raw["h_mpc"].notna()).sum()
        print(f"NEA.txt H applied: {n_in_nea:,} in catalog, "
              f"{n_changed:,} values changed, "
              f"{n_nulled:,} set to unknown")
    except Exception as e:
        print(f"Warning: NEA.txt H override skipped: {e}")

    # Derived columns
    raw["station_name"] = (raw["station_code"].map(STATION_NAMES)
                           .fillna(raw["station_code"]))
    raw["project"] = (raw["station_code"].map(STATION_TO_PROJECT)
                      .fillna("Others"))

    def h_bin(h):
        if pd.isna(h):
            return "Unknown H"
        for label, lo, hi in H_BINS:
            if (lo is None or h >= lo) and (hi is None or h < hi):
                return label
        return "Unknown H"

    raw["size_class"] = raw["h"].apply(h_bin)

    # Compute signed solar elongation at discovery
    if "disc_date" in raw.columns and "avg_ra_deg" in raw.columns:
        obs_dates = pd.to_datetime(raw["disc_date"])
        jd_offset = (obs_dates - pd.Timestamp("2000-01-01")).dt.days.values
        T = jd_offset / 36525.0
        L0 = (280.466 + 36000.77 * T) % 360
        M = (357.529 + 35999.05 * T) % 360
        C = 1.915 * np.sin(np.radians(M))
        sun_lon = (L0 + C) % 360
        obliquity = 23.439 - 0.013 * T
        sun_ra = np.degrees(np.arctan2(
            np.cos(np.radians(obliquity)) * np.sin(np.radians(sun_lon)),
            np.cos(np.radians(sun_lon)))) % 360
        sun_dec = np.degrees(np.arcsin(
            np.sin(np.radians(obliquity)) * np.sin(np.radians(sun_lon))))
        ra = raw["avg_ra_deg"].astype(float).values
        dec = raw["avg_dec_deg"].astype(float).values
        cos_elong = (np.sin(np.radians(dec)) * np.sin(np.radians(sun_dec))
                     + np.cos(np.radians(dec)) * np.cos(np.radians(sun_dec))
                       * np.cos(np.radians(ra - sun_ra)))
        elong = np.degrees(np.arccos(np.clip(cos_elong, -1, 1)))
        dra = (ra - sun_ra + 360) % 360
        sign = np.where(dra <= 180, 1, -1)
        raw["solar_elong_deg"] = np.where(
            raw["avg_ra_deg"].notna(), sign * elong, np.nan)

    # Pre-compute half-magnitude bin index
    raw["h_bin_idx"] = np.where(
        raw["h"].notna(),
        np.digitize(raw["h"], H_BIN_EDGES) - 1,
        -1,
    ).astype(int)

    # Read query timestamp
    if os.path.exists(meta_file):
        with open(meta_file) as f:
            timestamp = f.read().strip()
    else:
        timestamp = "unknown"

    return raw, timestamp


# ---------------------------------------------------------------------------
# Apparition data: lazy-loaded on first Tab 3 access
# ---------------------------------------------------------------------------

def _postprocess_apparition(df_raw):
    """Add derived columns to station-level apparition data from SQL."""
    df_raw = df_raw.copy()
    df_raw["disc_obstime"] = pd.to_datetime(df_raw["disc_obstime"])
    df_raw["first_obs"] = pd.to_datetime(df_raw["first_obs"])
    df_raw["first_post_disc"] = pd.to_datetime(df_raw["first_post_disc"])
    df_raw["project"] = (df_raw["station_code"].map(STATION_TO_PROJECT)
                         .fillna("Others"))
    df_raw["days_from_disc"] = (
        (df_raw["first_obs"] - df_raw["disc_obstime"])
        .dt.total_seconds() / 86400
    )
    return df_raw


_df_apparition = None


def load_apparition_data():
    """Lazy-load apparition station data (cache or query)."""
    global _df_apparition
    if _df_apparition is not None:
        return _df_apparition

    sql_hash = hashlib.md5(APPARITION_SQL.encode()).hexdigest()[:8]
    cache_file = os.path.join(
        _APP_DIR, f".apparition_cache_{sql_hash}.csv")
    meta_file = cache_file.replace(".csv", ".meta")

    use_cache = False
    if not _FORCE_REFRESH and os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < CACHE_MAX_AGE_SEC:
            use_cache = True
            print(f"Loading cached apparition data from "
                  f"{cache_file} (age: {age/3600:.1f} h)")
        else:
            print(f"Apparition cache is {age/3600:.1f} h old "
                  "\u2014 refreshing")
    elif _FORCE_REFRESH:
        print("--refresh: re-querying apparition data")

    if use_cache:
        _df_apparition = pd.read_csv(
            cache_file,
            parse_dates=["first_obs", "disc_obstime",
                         "first_post_disc"])
        print(f"Loaded {len(_df_apparition):,} cached station rows")
        return _df_apparition

    print("Querying database for apparition observations "
          "(this takes 3\u20138 min on first run)...")
    from datetime import datetime, timezone
    query_time = datetime.now(timezone.utc)
    with connect() as conn:
        raw = timed_query(conn, APPARITION_SQL,
                          label="apparition observations")
    print(f"Got {len(raw):,} station-level rows")

    _df_apparition = _postprocess_apparition(raw)
    _df_apparition.to_csv(cache_file, index=False)
    with open(meta_file, "w") as f:
        f.write(query_time.strftime("%Y-%m-%d %H:%M UTC"))
    print(f"Cached {len(_df_apparition):,} rows to {cache_file}")

    return _df_apparition


# ---------------------------------------------------------------------------
# Multi-survey comparison helpers
# ---------------------------------------------------------------------------

def build_survey_sets(df_main, df_app, year_range, size_filter,
                      exclude_precovery):
    """Build per-project sets of NEO designations from apparition data.

    Returns (dict[project \u2192 set[designation]], set[designation] eligible).
    """
    y0, y1 = year_range
    eligible = df_main[
        (df_main["disc_year"] >= y0) & (df_main["disc_year"] <= y1)]
    if size_filter != "all":
        eligible = eligible[eligible["size_class"] == size_filter]
    desig_set = set(eligible["designation"])

    tkl = df_app[df_app["designation"].isin(desig_set)]
    if exclude_precovery:
        tkl = tkl[tkl["first_post_disc"].notna()]

    survey_sets = {}
    for proj, grp in tkl.groupby("project"):
        survey_sets[proj] = set(grp["designation"])
    return survey_sets, desig_set


# ---------------------------------------------------------------------------
# Follow-up timing helpers
# ---------------------------------------------------------------------------

def build_followup_data(df_main, df_app, year_range, size_filter):
    """Compute per-survey follow-up timing from apparition data.

    For each NEO, identifies when each *different* survey project first
    observed it after discovery.  The discovery survey's own stations are
    excluded so only cross-survey follow-up is counted.

    Returns (DataFrame, int total_neos).
    DataFrame columns: designation, project (follow-up), disc_project,
        disc_year, days_to_followup, fu_rank.
    fu_rank = 1 means this project was the first outside survey to observe.
    """
    y0, y1 = year_range
    eligible = df_main[
        (df_main["disc_year"] >= y0) & (df_main["disc_year"] <= y1)]
    if size_filter != "all":
        eligible = eligible[eligible["size_class"] == size_filter]

    if len(eligible) == 0:
        return pd.DataFrame(), 0

    disc_info = eligible.set_index("designation")[
        ["station_code", "project", "disc_year"]].rename(
        columns={"station_code": "disc_station",
                 "project": "disc_project"})

    app = df_app[
        df_app["designation"].isin(disc_info.index)
        & df_app["first_post_disc"].notna()
    ].copy()

    if len(app) == 0:
        return pd.DataFrame(), len(eligible)

    app = app.join(disc_info, on="designation")

    # Exclude same survey project as the discoverer
    app = app[app["project"] != app["disc_project"]]

    if len(app) == 0:
        return pd.DataFrame(), len(eligible)

    app["days_to_followup"] = (
        (app["first_post_disc"] - app["disc_obstime"])
        .dt.total_seconds() / 86400
    )

    # Aggregate to project level: fastest station per project per NEO
    app = (app.groupby(["designation", "project", "disc_project",
                        "disc_year"])
           ["days_to_followup"].min().reset_index())

    # Rank projects by follow-up speed within each NEO
    app = app.sort_values(["designation", "days_to_followup"])
    app["fu_rank"] = app.groupby("designation").cumcount() + 1

    return app, len(eligible)


def _make_response_curve(fu_data, total_neos, max_days, t, height):
    """CDF: fraction of NEOs with N+ follow-up surveys within X days."""
    fig = go.Figure()

    colors = ["#4363d8", "#f58231", "#3cb44b"]
    labels = ["1st follow-up survey", "2nd survey", "3rd survey"]

    for rank in [1, 2, 3]:
        days = (fu_data[fu_data["fu_rank"] == rank]["days_to_followup"]
                .sort_values().values)
        days = days[days <= max_days]
        if len(days) == 0:
            continue
        y = np.arange(1, len(days) + 1) / total_neos * 100
        fig.add_trace(go.Scatter(
            x=days, y=y, mode="lines",
            name=labels[rank - 1],
            line=dict(color=colors[rank - 1], width=2.5),
            hovertemplate=(
                f"{labels[rank - 1]}<br>"
                "Day %{x:.0f}: %{y:.1f}% of NEOs"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Follow-up response curve",
        xaxis=dict(title="Days from discovery", range=[0, max_days]),
        yaxis=dict(title="% of NEOs observed", range=[0, 105]),
        legend=dict(yanchor="bottom", y=0.02, xanchor="right", x=0.98),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def _make_survey_response_box(fu_data, max_days, t, height):
    """Box plots of follow-up time by survey (horizontal)."""
    if len(fu_data) == 0:
        return _empty_figure("No follow-up data", t, height)

    proj_data = fu_data[fu_data["days_to_followup"] <= max_days]

    stats = (proj_data.groupby("project")["days_to_followup"]
             .agg(["median", "count"]).reset_index())
    stats = stats[stats["count"] >= 10].sort_values("median",
                                                     ascending=False)

    fig = go.Figure()
    for _, row in stats.iterrows():
        proj = row["project"]
        subset = proj_data[proj_data["project"] == proj]
        color = PROJECT_COLORS.get(proj, "#a9a9a9")
        fig.add_trace(go.Box(
            x=subset["days_to_followup"],
            name=proj,
            marker_color=color,
            line_color=color,
            boxmean=True,
            orientation="h",
        ))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Follow-up response time by survey",
        xaxis=dict(title="Days from discovery", range=[0, max_days]),
        showlegend=False,
        margin=dict(l=140, r=20, t=60, b=60),
    )
    return fig


def _make_followup_network(fu_data, t, height):
    """Heatmap: discovery survey -> first follow-up survey."""
    if len(fu_data) == 0:
        return _empty_figure("No follow-up data", t, height)

    first_fu = fu_data[fu_data["fu_rank"] == 1]

    pairs = (first_fu.groupby(["disc_project", "project"])
             .agg(count=("days_to_followup", "size"),
                  median_days=("days_to_followup", "median"))
             .reset_index())

    disc_surveys = (first_fu["disc_project"].value_counts()
                    .head(8).index.tolist())
    fu_surveys = (first_fu["project"].value_counts()
                  .head(8).index.tolist())

    if len(disc_surveys) < 2 or len(fu_surveys) < 2:
        return _empty_figure(
            "Not enough survey pairs for heatmap", t, height)

    n_d, n_f = len(disc_surveys), len(fu_surveys)
    matrix = np.zeros((n_d, n_f))
    text_matrix = [[""] * n_f for _ in range(n_d)]
    hover_matrix = [[""] * n_f for _ in range(n_d)]

    for _, row in pairs.iterrows():
        if (row["disc_project"] in disc_surveys
                and row["project"] in fu_surveys):
            i = disc_surveys.index(row["disc_project"])
            j = fu_surveys.index(row["project"])
            matrix[i][j] = row["count"]
            text_matrix[i][j] = f"{int(row['count']):,}"
            hover_matrix[i][j] = (
                f"{row['disc_project']} \u2192 {row['project']}<br>"
                f"{int(row['count']):,} NEOs<br>"
                f"Median: {row['median_days']:.0f} days"
            )

    fig = go.Figure(go.Heatmap(
        z=matrix, x=fu_surveys, y=disc_surveys,
        text=text_matrix,
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorscale="Blues",
        showscale=True,
        colorbar=dict(title="NEOs"),
        hovertext=hover_matrix,
        hovertemplate="%{hovertext}<extra></extra>",
    ))
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"],
        height=height,
        title="First follow-up survey network",
        xaxis=dict(title="First follow-up by", side="bottom"),
        yaxis=dict(title="Discovered by", autorange="reversed"),
        margin=dict(l=140, r=20, t=60, b=80),
    )
    return fig


def _make_followup_trend(fu_data, t, height):
    """Median days to first follow-up by discovery year."""
    if len(fu_data) == 0:
        return _empty_figure("No follow-up data", t, height)

    first_fu = fu_data[fu_data["fu_rank"] == 1]

    by_year = first_fu.groupby("disc_year")["days_to_followup"].agg(
        ["median", "count"]).reset_index()
    q25 = first_fu.groupby("disc_year")["days_to_followup"].quantile(
        0.25).reset_index(name="q25")
    q75 = first_fu.groupby("disc_year")["days_to_followup"].quantile(
        0.75).reset_index(name="q75")
    by_year = by_year.merge(q25, on="disc_year").merge(q75, on="disc_year")
    by_year = by_year[by_year["count"] >= 5]

    if len(by_year) == 0:
        return _empty_figure("Not enough data for trend", t, height)

    fig = go.Figure()

    # IQR band
    fig.add_trace(go.Scatter(
        x=list(by_year["disc_year"]) + list(by_year["disc_year"])[::-1],
        y=list(by_year["q75"]) + list(by_year["q25"])[::-1],
        fill="toself",
        fillcolor="rgba(67, 99, 216, 0.15)",
        line=dict(width=0),
        name="25th\u201375th percentile",
        hoverinfo="skip",
    ))

    # Median line
    fig.add_trace(go.Scatter(
        x=by_year["disc_year"], y=by_year["median"],
        mode="lines+markers",
        name="Median days",
        line=dict(color="#4363d8", width=2.5),
        marker=dict(size=6),
        customdata=np.stack([
            by_year["q25"].values, by_year["q75"].values,
            by_year["count"].values,
        ], axis=-1),
        hovertemplate=(
            "Year %{x}<br>"
            "Median: %{y:.1f} days<br>"
            "IQR: %{customdata[0]:.0f}\u2013%{customdata[1]:.0f} days<br>"
            "N=%{customdata[2]:,.0f} NEOs"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Median days to first follow-up by year",
        xaxis=dict(title="Discovery year", dtick=5),
        yaxis=dict(title="Days to first follow-up"),
        legend=dict(yanchor="top", y=0.98, xanchor="right", x=0.98),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def _hex_to_rgba(hex_color, alpha=0.25):
    """Convert hex color to rgba string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _empty_figure(message, t, height):
    """Return a blank figure with a centered message."""
    fig = go.Figure()
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["paper"],
        height=height,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(
            text=message, x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=16, color=t["subtext"]),
        )],
    )
    return fig


def _circle_trace(cx, cy, r, color, name):
    """Return a go.Scatter trace drawing a filled circle."""
    theta = np.linspace(0, 2 * np.pi, 80)
    return go.Scatter(
        x=cx + r * np.cos(theta),
        y=cy + r * np.sin(theta),
        mode="lines",
        fill="toself",
        fillcolor=_hex_to_rgba(color, 0.25),
        line=dict(color=color, width=2.5),
        name=name,
        showlegend=False,
        hoverinfo="skip",
    )


def _make_venn1(s, name, color, t, height):
    """Create a single-set diagram showing one circle with its count."""
    fig = go.Figure()
    cx, cy, r = 5.0, 3.5, 2.5
    fig.add_trace(_circle_trace(cx, cy, r, color, name))
    fig.add_annotation(
        x=cx, y=cy, text=f"<b>{len(s):,}</b>",
        showarrow=False, font=dict(size=24, color=t["text"]))
    fig.add_annotation(
        x=cx, y=cy + r + 0.5,
        text=f"<b>{name}</b>",
        showarrow=False, font=dict(size=14, color=color))
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["paper"],
        height=height,
        title="NEOs detected during discovery apparition",
        xaxis=dict(range=[0, 10], showgrid=False, zeroline=False,
                   showticklabels=False, visible=False),
        yaxis=dict(range=[-0.5, 7.5], showgrid=False, zeroline=False,
                   showticklabels=False, visible=False,
                   scaleanchor="x"),
        margin=dict(l=20, r=20, t=60, b=40),
    )
    return fig


def _make_venn2(sets, names, colors, t, height):
    """Create a 2-set Venn diagram using filled scatter circles."""
    A, B = sets
    a_only = len(A - B)
    b_only = len(B - A)
    both = len(A & B)

    fig = go.Figure()

    r = 2.3
    cx = [3.3, 6.7]
    cy = [3.5, 3.5]

    for i in range(2):
        fig.add_trace(_circle_trace(
            cx[i], cy[i], r, colors[i], names[i]))

    # Region counts — positions are geometric centroids of each region
    fig.add_annotation(x=3.0, y=3.5, text=f"<b>{a_only:,}</b>",
                       showarrow=False,
                       font=dict(size=20, color=t["text"]))
    fig.add_annotation(x=5.0, y=3.5, text=f"<b>{both:,}</b>",
                       showarrow=False,
                       font=dict(size=20, color=t["text"]))
    fig.add_annotation(x=7.0, y=3.5, text=f"<b>{b_only:,}</b>",
                       showarrow=False,
                       font=dict(size=20, color=t["text"]))

    # Set labels above circles
    for i in range(2):
        fig.add_annotation(
            x=cx[i], y=cy[i] + r + 0.5,
            text=f"<b>{names[i]}</b><br>({len(sets[i]):,} total)",
            showarrow=False,
            font=dict(size=13, color=colors[i]))

    fig.add_annotation(
        x=5.0, y=0.3,
        text="Circle sizes not proportional \u2014 see counts",
        showarrow=False,
        font=dict(size=10, color=t["subtext"]))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["paper"],
        height=height,
        title="NEOs co-detected during discovery apparition",
        xaxis=dict(range=[-0.5, 10.5], showgrid=False,
                   zeroline=False, showticklabels=False,
                   visible=False),
        yaxis=dict(range=[-0.5, 7.5], showgrid=False,
                   zeroline=False, showticklabels=False,
                   visible=False, scaleanchor="x"),
        margin=dict(l=20, r=20, t=60, b=40),
    )
    return fig


def _make_venn3(sets, names, colors, t, height):
    """Create a 3-set Venn diagram using filled scatter circles."""
    A, B, C = sets
    abc = A & B & C
    ab_only = (A & B) - C
    ac_only = (A & C) - B
    bc_only = (B & C) - A
    a_only = A - B - C
    b_only = B - A - C
    c_only = C - A - B

    fig = go.Figure()

    r = 2.2
    cx = [3.5, 6.5, 5.0]
    cy = [4.8, 4.8, 2.2]

    for i in range(3):
        fig.add_trace(_circle_trace(
            cx[i], cy[i], r, colors[i], names[i]))

    # Region annotations — positions are geometric centroids of each region
    regions = [
        (2.9, 5.1, a_only),
        (7.1, 5.1, b_only),
        (5.0, 1.5, c_only),
        (5.0, 5.2, ab_only),
        (3.9, 3.3, ac_only),
        (6.1, 3.3, bc_only),
        (5.0, 3.9, abc),
    ]
    for x, y, val in regions:
        fig.add_annotation(
            x=x, y=y, text=f"<b>{len(val):,}</b>",
            showarrow=False, font=dict(size=16, color=t["text"]))

    # Set labels
    label_pos = [(3.5, 7.5), (6.5, 7.5), (5.0, -0.5)]
    for i in range(3):
        fig.add_annotation(
            x=label_pos[i][0], y=label_pos[i][1],
            text=f"<b>{names[i]}</b><br>({len(sets[i]):,} total)",
            showarrow=False,
            font=dict(size=12, color=colors[i]))

    fig.add_annotation(
        x=5.0, y=-1.0,
        text="Circle sizes not proportional \u2014 see counts",
        showarrow=False,
        font=dict(size=10, color=t["subtext"]))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["paper"],
        height=height,
        title="NEOs co-detected during discovery apparition",
        xaxis=dict(range=[-0.5, 10.5], showgrid=False,
                   zeroline=False, showticklabels=False,
                   visible=False),
        yaxis=dict(range=[-1.5, 8.5], showgrid=False,
                   zeroline=False, showticklabels=False,
                   visible=False, scaleanchor="x"),
        margin=dict(l=20, r=20, t=60, b=40),
    )
    return fig


def _make_survey_reach(survey_sets, t, height):
    """Horizontal bar chart of unique NEOs detected per survey."""
    items = sorted(survey_sets.items(), key=lambda x: len(x[1]))
    names = [k for k, v in items]
    counts = [len(v) for k, v in items]
    bar_colors = [PROJECT_COLORS.get(n, "#a9a9a9") for n in names]

    fig = go.Figure(go.Bar(
        y=names, x=counts, orientation="h",
        marker_color=bar_colors,
        hovertemplate="%{y}: %{x:,} NEOs<extra></extra>",
        text=[f"{c:,}" for c in counts],
        textposition="outside",
    ))
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        title="NEOs detected per survey (apparition window)",
        xaxis_title="Unique NEOs",
        height=height,
        margin=dict(l=120, r=60),
    )
    return fig


def _make_pairwise_heatmap(survey_sets, t, height):
    """Asymmetric co-detection percentage matrix."""
    names = sorted(survey_sets.keys(),
                   key=lambda n: -len(survey_sets[n]))
    # Keep only surveys with meaningful detection counts
    names = [n for n in names if len(survey_sets[n]) >= 10]
    if len(names) < 2:
        return _empty_figure(
            "Not enough surveys for heatmap", t, height)

    n = len(names)
    matrix = np.zeros((n, n))
    text_matrix = [[""] * n for _ in range(n)]

    for i, ni in enumerate(names):
        si = survey_sets[ni]
        for j, nj in enumerate(names):
            sj = survey_sets[nj]
            overlap = len(si & sj)
            pct = overlap / len(si) * 100 if len(si) > 0 else 0
            matrix[i][j] = pct
            if i == j:
                text_matrix[i][j] = f"{len(si):,}"
            else:
                text_matrix[i][j] = f"{pct:.0f}%"

    fig = go.Figure(go.Heatmap(
        z=matrix, x=names, y=names,
        text=text_matrix,
        texttemplate="%{text}",
        textfont=dict(size=11),
        colorscale="Blues",
        zmin=0, zmax=100,
        showscale=False,
        hovertemplate=(
            "%{y} \u2192 %{x}: %{text}<extra></extra>"),
    ))
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"],
        title="Pairwise co-detection (% of row survey's NEOs)",
        height=height,
        xaxis=dict(title="Also detected by", side="bottom"),
        yaxis=dict(title="Survey", autorange="reversed"),
        margin=dict(l=120, r=20, t=60, b=80),
    )
    return fig


def _make_comparison_summary(survey_sets, all_desigs, t, height):
    """Summary statistics table for multi-survey comparison."""
    desig_survey_count = {}
    for desig in all_desigs:
        desig_survey_count[desig] = sum(
            1 for s in survey_sets.values() if desig in s)

    total = len(all_desigs)
    detected_any = sum(
        1 for n in desig_survey_count.values() if n > 0)
    by_1 = sum(1 for n in desig_survey_count.values() if n == 1)
    by_2 = sum(1 for n in desig_survey_count.values() if n == 2)
    by_3plus = sum(1 for n in desig_survey_count.values() if n >= 3)
    survey_counts = [n for n in desig_survey_count.values() if n > 0]
    mean_s = np.mean(survey_counts) if survey_counts else 0
    median_s = np.median(survey_counts) if survey_counts else 0

    def pct(n):
        return f" ({n / total * 100:.1f}%)" if total > 0 else ""

    labels = [
        "Total NEOs in selection",
        "Detected by any survey (apparition)",
        "Single survey only",
        "Exactly 2 surveys",
        "3 or more surveys",
        "Mean surveys per NEO",
        "Median surveys per NEO",
    ]
    values = [
        f"{total:,}",
        f"{detected_any:,}{pct(detected_any)}",
        f"{by_1:,}{pct(by_1)}",
        f"{by_2:,}{pct(by_2)}",
        f"{by_3plus:,}{pct(by_3plus)}",
        f"{mean_s:.2f}",
        f"{median_s:.1f}",
    ]

    fig = go.Figure(go.Table(
        header=dict(
            values=["Statistic", "Value"],
            fill_color=t["table_header"],
            font=dict(color=t["text"], size=13),
            align="left",
        ),
        cells=dict(
            values=[labels, values],
            fill_color=t["table_cell"],
            font=dict(color=t["table_font"], size=12),
            align="left",
        ),
    ))
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"],
        title="Multi-survey Detection Summary",
        height=height,
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig


# ---------------------------------------------------------------------------
# Discovery circumstances helpers
# ---------------------------------------------------------------------------

def _make_sky_map(dff, color_by, group_by, t, height):
    """RA/Dec scatter of discovery positions with ecliptic/galactic planes.

    Uses centered RA: 180° (E) on left, 0° center, -180° (W) on right.
    """
    fig = go.Figure()

    # Ecliptic plane
    fig.add_trace(go.Scatter(
        x=ECL_RA, y=ECL_DEC, mode="lines",
        line=dict(color="gold", width=1.5, dash="dash"),
        name="Ecliptic", hoverinfo="skip",
    ))
    # Galactic plane
    fig.add_trace(go.Scatter(
        x=GAL_RA, y=GAL_DEC, mode="lines",
        line=dict(color="gray", width=1.5, dash="dash"),
        name="Galactic plane", hoverinfo="skip",
    ))

    valid = dff[dff["avg_ra_deg"].notna() & dff["avg_dec_deg"].notna()].copy()
    if len(valid) == 0:
        fig.update_layout(
            template=t["template"],
            paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
            height=height,
            title="Discovery sky positions (no data)",
        )
        return fig

    # Convert RA to centered coordinates for plotting
    valid["ra_c"] = np.where(
        valid["avg_ra_deg"] > 180,
        valid["avg_ra_deg"] - 360,
        valid["avg_ra_deg"])

    if color_by == "year":
        fig.add_trace(go.Scattergl(
            x=valid["ra_c"], y=valid["avg_dec_deg"],
            mode="markers",
            marker=dict(size=3, opacity=0.3,
                        color=valid["disc_year"],
                        colorscale="Viridis", showscale=True,
                        colorbar=dict(title="Year")),
            name="NEOs",
            hovertemplate=(
                "RA %{customdata:.1f}\u00b0  Dec %{y:.1f}\u00b0<br>"
                "%{text}<extra></extra>"
            ),
            customdata=valid["avg_ra_deg"],
            text=valid["designation"],
        ))
    elif color_by == "size":
        for i, (label, _, _) in enumerate(H_BINS):
            subset = valid[valid["size_class"] == label]
            if len(subset) == 0:
                continue
            fig.add_trace(go.Scattergl(
                x=subset["ra_c"], y=subset["avg_dec_deg"],
                mode="markers",
                marker=dict(size=3, opacity=0.3,
                            color=SIZE_COLORS[i]),
                name=label,
                hovertemplate=(
                    "RA %{customdata:.1f}\u00b0  Dec %{y:.1f}\u00b0<br>"
                    "%{text}<extra></extra>"
                ),
                customdata=subset["avg_ra_deg"],
                text=subset["designation"],
            ))
    else:
        # Color by survey project
        col = "project" if group_by != "station" else "station_name"
        if col == "project":
            groups = [p for p in PROJECT_ORDER
                      if p in valid[col].unique()]
            cmap = PROJECT_COLORS
        else:
            groups = valid[col].value_counts().head(10).index.tolist()
            cmap = {}
        for gname in groups:
            subset = valid[valid[col] == gname]
            if len(subset) == 0:
                continue
            fig.add_trace(go.Scattergl(
                x=subset["ra_c"], y=subset["avg_dec_deg"],
                mode="markers",
                marker=dict(size=3, opacity=0.3,
                            color=cmap.get(gname)),
                name=gname,
                hovertemplate=(
                    "RA %{customdata:.1f}\u00b0  Dec %{y:.1f}\u00b0<br>"
                    "%{text}<extra></extra>"
                ),
                customdata=subset["avg_ra_deg"],
                text=subset["designation"],
            ))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Discovery sky positions",
        xaxis=dict(
            title="Right Ascension (\u00b0)",
            range=[180, -180], dtick=30,
        ),
        yaxis=dict(title="Dec (\u00b0)", range=[-90, 90], dtick=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def _make_mag_distribution(dff, color_by, group_by, t, height):
    """Histogram of apparent V magnitude at discovery."""
    valid = dff[dff["median_v_mag"].notna()]
    if len(valid) == 0:
        return _empty_figure("No magnitude data", t, height)

    fig = go.Figure()

    if color_by == "size":
        for i, (label, _, _) in enumerate(H_BINS):
            subset = valid[valid["size_class"] == label]
            if len(subset) == 0:
                continue
            fig.add_trace(go.Histogram(
                x=subset["median_v_mag"], name=label,
                marker_color=SIZE_COLORS[i],
                xbins=dict(start=10, end=28, size=0.5),
                hovertemplate="V=%{x:.1f}: %{y}<extra></extra>",
            ))
    elif color_by == "survey":
        col = "project" if group_by != "station" else "station_name"
        if col == "project":
            groups = [p for p in PROJECT_ORDER
                      if p in valid[col].unique()]
            cmap = PROJECT_COLORS
        else:
            groups = valid[col].value_counts().head(10).index.tolist()
            cmap = {}
        for gname in groups:
            subset = valid[valid[col] == gname]
            if len(subset) == 0:
                continue
            fig.add_trace(go.Histogram(
                x=subset["median_v_mag"], name=gname,
                marker_color=cmap.get(gname),
                xbins=dict(start=10, end=28, size=0.5),
                hovertemplate="V=%{x:.1f}: %{y}<extra></extra>",
            ))
    else:
        fig.add_trace(go.Histogram(
            x=valid["median_v_mag"], name="NEOs",
            marker_color="#607D8B",
            xbins=dict(start=10, end=28, size=0.5),
            hovertemplate="V=%{x:.1f}: %{y}<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Apparent V magnitude at discovery",
        xaxis=dict(title="Apparent V magnitude"),
        yaxis=dict(title="Count"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def _make_rate_plot(dff, color_by, group_by, t, height):
    """Scatter of rate of motion vs absolute magnitude H."""
    valid = dff[dff["rate_deg_per_day"].notna() & dff["h"].notna()]
    n_excluded = len(dff) - len(
        dff[dff["rate_deg_per_day"].notna()])

    if len(valid) == 0:
        return _empty_figure("No rate data", t, height)

    fig = go.Figure()

    if color_by == "year":
        fig.add_trace(go.Scattergl(
            x=valid["h"], y=valid["rate_deg_per_day"],
            mode="markers",
            marker=dict(size=3, opacity=0.3,
                        color=valid["disc_year"],
                        colorscale="Viridis", showscale=True,
                        colorbar=dict(title="Year")),
            name="NEOs",
            hovertemplate=(
                "H=%{x:.1f}  Rate=%{y:.2f} \u00b0/day<br>"
                "%{text}<extra></extra>"
            ),
            text=valid["designation"],
        ))
    elif color_by == "size":
        for i, (label, _, _) in enumerate(H_BINS):
            subset = valid[valid["size_class"] == label]
            if len(subset) == 0:
                continue
            fig.add_trace(go.Scattergl(
                x=subset["h"], y=subset["rate_deg_per_day"],
                mode="markers",
                marker=dict(size=3, opacity=0.3,
                            color=SIZE_COLORS[i]),
                name=label,
                hovertemplate=(
                    "H=%{x:.1f}  Rate=%{y:.2f} \u00b0/day<br>"
                    "%{text}<extra></extra>"
                ),
                text=subset["designation"],
            ))
    else:
        col = "project" if group_by != "station" else "station_name"
        if col == "project":
            groups = [p for p in PROJECT_ORDER
                      if p in valid[col].unique()]
            cmap = PROJECT_COLORS
        else:
            groups = valid[col].value_counts().head(10).index.tolist()
            cmap = {}
        for gname in groups:
            subset = valid[valid[col] == gname]
            if len(subset) == 0:
                continue
            fig.add_trace(go.Scattergl(
                x=subset["h"], y=subset["rate_deg_per_day"],
                mode="markers",
                marker=dict(size=3, opacity=0.3,
                            color=cmap.get(gname)),
                name=gname,
                hovertemplate=(
                    "H=%{x:.1f}  Rate=%{y:.2f} \u00b0/day<br>"
                    "%{text}<extra></extra>"
                ),
                text=subset["designation"],
            ))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Rate of motion vs. absolute magnitude",
        xaxis=dict(title="Absolute magnitude H"),
        yaxis=dict(title="Rate (\u00b0/day)", type="log"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    if n_excluded > 0:
        fig.add_annotation(
            text=f"{n_excluded:,} single-obs tracklets excluded",
            xref="paper", yref="paper", x=0.98, y=0.02,
            showarrow=False,
            font=dict(size=10, color=t["subtext"]),
            xanchor="right",
        )
    return fig


def _make_pa_rose(dff, t, height):
    """Polar histogram of position angle of motion."""
    valid = dff[dff["position_angle_deg"].notna()]
    n_excluded = len(dff) - len(valid)

    if len(valid) == 0:
        return _empty_figure("No position angle data", t, height)

    bin_size = 15
    bins = np.arange(0, 360, bin_size)
    counts, _ = np.histogram(valid["position_angle_deg"], bins=np.append(bins, 360))

    fig = go.Figure(go.Barpolar(
        r=counts, theta=bins + bin_size / 2,
        width=bin_size,
        marker_color="#607D8B",
        marker_line_color=t["paper"],
        marker_line_width=0.5,
        hovertemplate="PA %{theta:.0f}\u00b0: %{r:,}<extra></extra>",
    ))

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"],
        height=height,
        title="Position angle of motion",
        polar=dict(
            angularaxis=dict(
                direction="clockwise", rotation=90,
                tickmode="array",
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
            ),
            bgcolor=t["plot"],
        ),
        margin=dict(l=40, r=40, t=60, b=40),
    )
    if n_excluded > 0:
        fig.add_annotation(
            text=f"{n_excluded:,} single-obs excluded",
            xref="paper", yref="paper", x=0.98, y=0.02,
            showarrow=False,
            font=dict(size=10, color=t["subtext"]),
            xanchor="right",
        )
    return fig


def _make_elongation_hist(dff, color_by, group_by, t, height):
    """Solar elongation histogram with opposition (180\u00b0) centred."""
    valid = dff[dff["solar_elong_deg"].notna()]
    if len(valid) == 0:
        return _empty_figure("No elongation data", t, height)

    # Transform so opposition (±180°) maps to x=0 (centre) and
    # near-Sun (small elongation) maps to the edges (±180).
    # sign preserved: +evening(E), -morning(W).
    elong = valid["solar_elong_deg"].values
    sign = np.sign(elong)
    x_opp = sign * (180.0 - np.abs(elong))

    bin_size = 5
    fig = go.Figure()

    def _add_hist(x_data, **kwargs):
        fig.add_trace(go.Histogram(
            x=x_data,
            xbins=dict(start=-180, end=180, size=bin_size),
            **kwargs,
        ))

    if color_by == "size":
        for i, (label, _, _) in enumerate(H_BINS):
            mask = valid["size_class"].values == label
            if not mask.any():
                continue
            _add_hist(
                x_opp[mask], name=label,
                marker_color=SIZE_COLORS[i],
                hovertemplate="%{y}<extra></extra>",
            )
    elif color_by == "survey":
        col = "project" if group_by != "station" else "station_name"
        if col == "project":
            groups = [p for p in PROJECT_ORDER
                      if p in valid[col].unique()]
            cmap = PROJECT_COLORS
        else:
            groups = valid[col].value_counts().head(10).index.tolist()
            cmap = {}
        col_vals = valid[col].values
        for gname in groups:
            mask = col_vals == gname
            if not mask.any():
                continue
            _add_hist(
                x_opp[mask], name=gname,
                marker_color=cmap.get(gname),
                hovertemplate="%{y}<extra></extra>",
            )
    else:
        _add_hist(
            x_opp, name="NEOs",
            marker_color="#607D8B",
            hovertemplate="%{y}<extra></extra>",
        )

    # Custom tick labels: show actual solar elongation at each position
    # x_opp=0 → elong 180° (opposition), x_opp=±180 → elong 0° (Sun)
    tickvals = list(range(-180, 181, 30))
    ticktext = [f"{180 - abs(v)}\u00b0" for v in tickvals]

    fig.update_layout(
        barmode="stack",
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        height=height,
        title="Solar elongation at discovery",
        xaxis=dict(title="Solar Elongation",
                   range=[-180, 180],
                   tickmode="array",
                   tickvals=tickvals, ticktext=ticktext),
        yaxis=dict(title="Count"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=80),
    )
    # Axis annotations: Sun at edges, Opposition at centre
    fig.add_annotation(
        text="\u2190 Morning sky", xref="paper", yref="paper",
        x=0.22, y=-0.15, showarrow=False,
        font=dict(size=11, color=t["subtext"]), xanchor="center",
    )
    fig.add_annotation(
        text="Evening sky \u2192", xref="paper", yref="paper",
        x=0.78, y=-0.15, showarrow=False,
        font=dict(size=11, color=t["subtext"]), xanchor="center",
    )
    fig.add_annotation(
        text="\u2600", xref="paper", yref="paper",
        x=0.0, y=-0.15, showarrow=False,
        font=dict(size=12, color=t["subtext"]), xanchor="left",
    )
    fig.add_annotation(
        text="\u2600", xref="paper", yref="paper",
        x=1.0, y=-0.15, showarrow=False,
        font=dict(size=12, color=t["subtext"]), xanchor="right",
    )
    fig.add_annotation(
        text="Opposition", xref="paper", yref="paper",
        x=0.5, y=-0.15, showarrow=False,
        font=dict(size=11, color=t["subtext"]), xanchor="center",
    )
    return fig


# ---------------------------------------------------------------------------
# Dash app
# ---------------------------------------------------------------------------

app = Dash(__name__, suppress_callback_exceptions=True,
           title="Planetary Defense Dashboard")
server = app.server  # Flask WSGI server for gunicorn deployment


@server.after_request
def _add_cache_headers(response):
    """Prevent browser from caching CSS/JS assets during development."""
    if response.content_type and ("css" in response.content_type
                                  or "javascript" in response.content_type):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

# ---------------------------------------------------------------------------
# Data loading — background thread so the server starts immediately
# ---------------------------------------------------------------------------

# For --refresh-only, load synchronously (no server needed)
if _REFRESH_ONLY:
    df, query_timestamp = load_data()
    df_apparition = load_apparition_data()
    print("Cache refresh complete.")
    sys.exit(0)

# For normal operation, load in background thread
df = None
df_apparition = None
query_timestamp = "loading..."
year_min, year_max = 1898, 2026
_data_ready = threading.Event()
_data_error = None


def _load_all_data():
    """Load both datasets in a background thread."""
    global df, df_apparition, query_timestamp, year_min, year_max, _data_error
    try:
        df, query_timestamp = load_data()
        df_apparition = load_apparition_data()
        year_min = int(df["disc_year"].min())
        year_max = int(df["disc_year"].max())
        print(f"Data ready: {len(df):,} NEOs, "
              f"{len(df_apparition):,} apparition rows")
    except Exception as e:
        _data_error = str(e)
        print(f"ERROR loading data: {e}")
    finally:
        _data_ready.set()


_loader_thread = threading.Thread(target=_load_all_data, daemon=True)
_loader_thread.start()
# Pre-load MPS archive bundle index so first timeline render isn't delayed
threading.Thread(target=_load_mps_bundles, daemon=True).start()

# Label style helper
LABEL_STYLE = {"fontFamily": "sans-serif", "fontSize": "13px"}
# RadioItems label style — "inherit" lets the page-container color propagate
RADIO_LABEL_STYLE = {"color": "inherit", "fontFamily": "sans-serif"}
RADIO_STYLE = {"fontFamily": "sans-serif"}
DOWNLOAD_BTN_STYLE = {
    "padding": "6px 14px",
    "fontSize": "12px",
    "fontFamily": "sans-serif",
    "cursor": "pointer",
    "whiteSpace": "nowrap",
}

# ---------------------------------------------------------------------------
# Observatory site buttons — sites known to work with NEOfixer ephemeris API
# ---------------------------------------------------------------------------

_OBS_SITES = ["I52", "J95", "T14", "H21", "474"]
_OBS_SITES_DEFAULT = "I52"


app.layout = html.Div(
    id="page-container",
    style={
        "minHeight": "100vh", "padding": "20px",
        # Initial CSS variable values (dark theme defaults, overwritten
        # immediately by the theme callback on page load)
        "backgroundColor": "#1e1e1e", "color": "#e0e0e0",
        "--subtext-color": "#888888",
        "--hr-color": "#444444",
        "--paper-bg": "#1e1e1e",
        "--tab-border": "#444444",
    },
    children=[
        # ── Maintenance banner ────────────────────────────────────────
        html.Div(
            _MAINTENANCE_MSG,
            style={
                "padding": "10px 20px",
                "marginBottom": "12px",
                "borderRadius": "6px",
                "fontFamily": "sans-serif",
                "fontSize": "14px",
                "fontWeight": "600",
                "backgroundColor": "#f57f17",
                "color": "#000",
                "textAlign": "center",
            },
        ) if _MAINTENANCE_MSG else html.Div(),
        # ── Refresh banner (shown when cron job is updating caches) ──
        html.Div(id="refresh-banner"),
        dcc.Interval(id="refresh-check", interval=30_000, n_intervals=0),
        # ── Loading banner (shown while data loads at startup) ────────
        html.Div(id="loading-banner"),
        dcc.Interval(id="loading-check", interval=2_000, n_intervals=0),
        # ── Download components (hidden, one per tab) ─────────────────
        dcc.Download(id="download-discovery"),
        dcc.Download(id="download-neomod"),
        dcc.Download(id="download-comparison"),
        dcc.Download(id="download-followup"),
        dcc.Download(id="download-circumstances"),
        # ── Banner: logo + title + shared controls ───────────────────
        html.Div(
            style={"display": "flex", "gap": "15px", "alignItems": "center",
                    "marginBottom": "12px", "flexWrap": "wrap"},
            children=[
                html.A(
                    href="https://catalina.lpl.arizona.edu",
                    target="_blank",
                    title="Catalina Sky Survey",
                    children=html.Img(
                        src="/assets/CSS_logo_transparent.png",
                        style={
                            "height": "98px", "width": "98px",
                            "borderRadius": "50%",
                            "background": "white", "padding": "3px",
                        },
                    ),
                ),
                # Title + subtitle + service health (takes remaining space)
                html.Div(
                    style={"marginRight": "auto"},
                    children=[
                        html.H1(
                            "Planetary Defense Dashboard",
                            style={"fontFamily": "sans-serif",
                                   "marginBottom": "0", "marginTop": "0"},
                        ),
                        html.P(
                            id="subtitle-text",
                            className="subtext",
                            style={"fontFamily": "sans-serif",
                                   "marginTop": "2px",
                                   "marginBottom": "0"},
                        ),
                        html.Div(id="service-health-bar"),
                    ],
                ),
                # Shared controls
                html.Div(children=[
                    html.Label("Group by", style=LABEL_STYLE),
                    dcc.RadioItems(
                        id="group-by",
                        options=[
                            {"label": " Combined", "value": "combined"},
                            {"label": " Project", "value": "project"},
                            {"label": " Station", "value": "station"},
                        ],
                        value="combined",
                        inline=True,
                        style=RADIO_STYLE,
                        labelStyle=RADIO_LABEL_STYLE,
                    ),
                ]),
                html.Div(children=[
                    html.Label("Plot height", style=LABEL_STYLE),
                    dcc.RadioItems(
                        id="plot-height",
                        options=[
                            {"label": " Short", "value": "500"},
                            {"label": " Normal", "value": "700"},
                            {"label": " Tall", "value": "900"},
                        ],
                        value="700",
                        inline=True,
                        style=RADIO_STYLE,
                        labelStyle=RADIO_LABEL_STYLE,
                    ),
                ]),
                html.Div(children=[
                    html.Label("Theme", style=LABEL_STYLE),
                    dcc.RadioItems(
                        id="theme-toggle",
                        options=[
                            {"label": " Light", "value": "light"},
                            {"label": " Dark", "value": "dark"},
                        ],
                        value="dark",
                        inline=True,
                        style=RADIO_STYLE,
                        labelStyle=RADIO_LABEL_STYLE,
                    ),
                ]),
                html.Div(children=[
                    html.Label("Reset", style=LABEL_STYLE),
                    html.Div(
                        style={"display": "flex", "gap": "6px"},
                        children=[
                            html.Button(
                                "Tab", id="reset-tab-btn",
                                n_clicks=0,
                                style={
                                    "padding": "4px 12px",
                                    "fontSize": "12px",
                                    "fontFamily": "sans-serif",
                                    "cursor": "pointer",
                                },
                            ),
                            html.Button(
                                "All", id="reset-all-btn",
                                n_clicks=0,
                                style={
                                    "padding": "4px 12px",
                                    "fontSize": "12px",
                                    "fontFamily": "sans-serif",
                                    "cursor": "pointer",
                                },
                            ),
                        ],
                    ),
                ]),
            ],
        ),
        # ── Service health check (banner-level) ────────────────────
        dcc.Store(id="service-health-data", data={}),
        dcc.Interval(id="service-health-poll", interval=300_000,
                     n_intervals=0),  # every 5 minutes
        # ── Tab navigation ───────────────────────────────────────────
        # ── MPEC stores and intervals ─────────────────────────────
        dcc.Store(id="mpec-selected-path", data=None),
        dcc.Store(id="mpec-detail-data", storage_type="memory"),
        dcc.Store(id="mpec-auto-mode", data=True),
        dcc.Store(id="mpec-enrich-data", data=None),
        dcc.Store(id="mpec-item-paths", data=[]),
        dcc.Store(id="mpec-restore-list", data=0),
        # Hidden input written by keyboard.js — triggers nav callback
        dcc.Input(id="mpec-kb-nav", type="text", value="",
                  style={"display": "none"}),
        # Hidden input for designation search (set by keyboard.js)
        dcc.Input(id="mpec-desig-search", type="text", value="",
                  style={"display": "none"}),
        # Section open/closed state (persists across MPEC nav + tab switches)
        dcc.Store(id="mpec-section-state", storage_type="session",
                  data={"0": False, "1": False, "2": False, "3": False,
                        "4": False, "5": False, "6": False, "7": False}),
        # Hidden input written by keyboard.js — section state sync
        dcc.Input(id="mpec-section-state-input", type="text", value="",
                  style={"display": "none"}),
        dcc.Interval(id="mpec-refresh", interval=900_000,
                     n_intervals=0),  # 15 min
        dcc.Interval(id="mpec-enrich-poll", interval=60_000,
                     n_intervals=0, max_intervals=10, disabled=True),
        dcc.Tabs(
            id="tabs",
            value="tab-mpec",
            className="nav-tabs",
            children=[
                # ━━━ Tab 0: MPEC Browser ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                dcc.Tab(
                    label="MPEC Browser",
                    value="tab-mpec",
                    className="nav-tab",
                    selected_className="nav-tab--selected",
                    children=[
                        html.Div(
                            style={"paddingTop": "15px", "display": "flex",
                                   "gap": "20px", "minHeight": "600px"},
                            children=[
                                # ── Left panel: MPEC list ──
                                html.Div(
                                    style={
                                        "width": "30%", "minWidth": "280px",
                                        "maxHeight": "calc(85vh - 40px)",
                                        "overflowY": "auto",
                                        "borderRight":
                                            "1px solid var(--hr-color, #ccc)",
                                        "paddingRight": "15px",
                                        "display": "flex",
                                        "flexDirection": "column",
                                    },
                                    children=[
                                        # Auto-mode indicator row
                                        html.Div(
                                            id="mpec-auto-indicator",
                                            style={
                                                "display": "flex",
                                                "justifyContent": "space-between",
                                                "alignItems": "center",
                                                "marginBottom": "8px",
                                                "fontFamily": "sans-serif",
                                                "fontSize": "12px",
                                            },
                                            children=[
                                                html.Span(
                                                    id="mpec-auto-label",
                                                    children="",
                                                ),
                                                html.Div(
                                                    style={"display": "flex",
                                                           "alignItems": "center",
                                                           "gap": "8px"},
                                                    children=[
                                                        html.Button(
                                                            "Follow latest",
                                                            id="mpec-follow-btn",
                                                            n_clicks=0,
                                                            style={
                                                                "fontSize": "11px",
                                                                "padding": "2px 10px",
                                                                "display": "none",
                                                            },
                                                        ),
                                                        html.Span(
                                                            "? shortcuts",
                                                            title="Press ? for keyboard shortcuts",
                                                            style={
                                                                "fontSize": "11px",
                                                                "color": "var(--subtext-color, #888)",
                                                                "cursor": "default",
                                                                "fontFamily": "monospace",
                                                            },
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        ),
                                        dcc.Input(
                                            id="mpec-search",
                                            type="text",
                                            placeholder="Search designation or MPEC ID...",
                                            debounce=True,
                                            className="mpec-search-input",
                                            style={
                                                "width": "100%",
                                                "fontSize": "13px",
                                                "fontFamily": "sans-serif",
                                                "padding": "6px 10px",
                                                "marginBottom": "8px",
                                                "borderRadius": "4px",
                                                "boxSizing": "border-box",
                                                "border": "none",
                                            },
                                        ),
                                        html.Div(
                                            id="mpec-list-panel",
                                            style={
                                                "flex": "1",
                                                "overflowY": "auto",
                                            },
                                            children=[
                                                html.Div(
                                                    "Loading recent MPECs...",
                                                    style={"fontFamily": "sans-serif",
                                                           "fontSize": "14px",
                                                           "color": "var(--subtext-color, #888)"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                # ── Right panel: MPEC detail ──
                                html.Div(
                                    style={
                                        "width": "70%",
                                        "maxHeight": "calc(85vh - 40px)",
                                        "overflowY": "auto",
                                        "paddingLeft": "5px",
                                    },
                                    children=[
                                        html.Div(
                                            id="mpec-detail-summary",
                                            children=[
                                                html.Div(
                                                    "Select an MPEC from the list.",
                                                    style={"fontFamily": "sans-serif",
                                                           "fontSize": "14px",
                                                           "color": "var(--subtext-color, #888)",
                                                           "paddingTop": "20px"},
                                                ),
                                            ],
                                        ),
                                        dcc.Loading(
                                            html.Div(id="mpec-obs-timeline"),
                                            type="circle",
                                            color="#5b8def",
                                        ),
                                        dcc.Store(id="obs-timeline-click-sink"),
                                        dcc.Store(
                                            id="obs-site-selected",
                                            data=_OBS_SITES_DEFAULT,
                                        ),
                                        dcc.Loading(
                                            html.Div(id="mpec-obs-chart"),
                                            type="circle",
                                            color="#5b8def",
                                        ),
                                        html.Div(
                                            id="mpec-detail-panel",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                # ━━━ Tab 1: Discovery by Year ━━━━━━━━━━━━━━━━━━━━━━━━
                dcc.Tab(
                    label="Discoveries by Year",
                    value="tab-discovery",
                    className="nav-tab",
                    selected_className="nav-tab--selected",
                    children=[
                        html.Div(style={"paddingTop": "15px"}, children=[
                            # Controls row
                            html.Div(
                                style={"display": "flex", "gap": "30px",
                                        "flexWrap": "wrap",
                                        "marginBottom": "15px"},
                                children=[
                                    html.Div(
                                        style={"flex": "1",
                                               "minWidth": "300px"},
                                        children=[
                                            html.Label("Year Range",
                                                       style=LABEL_STYLE),
                                            dcc.RangeSlider(
                                                id="year-range",
                                                min=year_min, max=year_max,
                                                value=[1995, year_max],
                                                marks={
                                                    y: {"label": str(y)}
                                                    for y in range(
                                                        year_min,
                                                        year_max + 1, 5)
                                                },
                                                tooltip={
                                                    "placement": "bottom",
                                                    "always_visible":
                                                        False},
                                            ),
                                        ],
                                    ),
                                    html.Div(children=[
                                        html.Label("Size class",
                                                   style=LABEL_STYLE),
                                        dcc.Dropdown(
                                            id="size-filter",
                                            options=(
                                                [{"label": "All sizes",
                                                  "value": "all"},
                                                 {"label": "Split sizes",
                                                  "value": "split"}]
                                                + [{"label": l, "value": l}
                                                   for l, _, _ in H_BINS]
                                            ),
                                            value="split",
                                            clearable=False,
                                            style={"width": "270px"},
                                        ),
                                    ]),
                                    html.Div(children=[
                                        html.Label("View",
                                                   style=LABEL_STYLE),
                                        dcc.RadioItems(
                                            id="cumulative-toggle",
                                            options=[
                                                {"label": " Per year",
                                                 "value": "annual"},
                                                {"label": " Cumulative",
                                                 "value": "cumulative"},
                                            ],
                                            value="annual",
                                            inline=True,
                                            style=RADIO_STYLE,
                                            labelStyle=RADIO_LABEL_STYLE,
                                        ),
                                    ]),
                                    html.Div(
                                        style={"alignSelf": "flex-end"},
                                        children=[
                                            html.Button(
                                                "Download CSV",
                                                id="btn-download-discovery",
                                                n_clicks=0,
                                                style=DOWNLOAD_BTN_STYLE,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            # Main chart
                            dcc.Graph(id="discovery-bar",
                                      config=GRAPH_CONFIG),
                            # Secondary row
                            html.Div(
                                style={"display": "flex", "gap": "20px",
                                        "flexWrap": "wrap"},
                                children=[
                                    dcc.Graph(
                                        id="size-histogram",
                                        style={"flex": "1",
                                               "minWidth": "400px",
                                               "height": "350px"},
                                        config=GRAPH_CONFIG),
                                    dcc.Graph(
                                        id="top-stations-table",
                                        style={"flex": "1",
                                               "minWidth": "400px",
                                               "height": "350px"},
                                        config=GRAPH_CONFIG),
                                ],
                            ),
                        ]),
                    ],
                ),
                # ━━━ Tab 2: Size Distribution vs. NEOMOD3 ━━━━━━━━━━━
                dcc.Tab(
                    label="Size Distribution vs. NEOMOD3",
                    value="tab-neomod",
                    className="nav-tab",
                    selected_className="nav-tab--selected",
                    children=[
                        html.Div(style={"paddingTop": "15px"}, children=[
                            # Discovery years — full width
                            html.Div(
                                style={"marginBottom": "10px"},
                                children=[
                                    html.Label("Discovery years",
                                               style=LABEL_STYLE),
                                    dcc.RangeSlider(
                                        id="h-year-range",
                                        min=year_min,
                                        max=year_max,
                                        value=[year_min, year_max],
                                        marks={
                                            y: {"label": str(y)}
                                            for y in range(
                                                year_min,
                                                year_max + 1, 10)
                                        },
                                        tooltip={
                                            "placement": "bottom",
                                            "always_visible": False},
                                    ),
                                ],
                            ),
                            # Controls row
                            html.Div(
                                style={"display": "flex", "gap": "20px",
                                        "flexWrap": "wrap",
                                        "alignItems": "flex-end",
                                        "marginBottom": "10px"},
                                children=[
                                    html.Div(
                                        style={"flex": "1",
                                               "minWidth": "300px"},
                                        children=[
                                            html.Label("H range",
                                                       style=LABEL_STYLE),
                                            dcc.RangeSlider(
                                                id="h-range",
                                                min=15.25, max=27.75,
                                                value=[16.25, 22.75],
                                                step=0.5,
                                                marks={
                                                    h: {"label": str(h)}
                                                    for h in range(16, 28)
                                                },
                                                tooltip={
                                                    "placement": "bottom",
                                                    "always_visible":
                                                        False},
                                            ),
                                        ],
                                    ),
                                    html.Div(children=[
                                        html.Label("Y scale",
                                                   style=LABEL_STYLE),
                                        dcc.RadioItems(
                                            id="h-yscale",
                                            options=[
                                                {"label": " Log",
                                                 "value": "log"},
                                                {"label": " Linear",
                                                 "value": "linear"},
                                            ],
                                            value="linear",
                                            inline=True,
                                            style=RADIO_STYLE,
                                            labelStyle=RADIO_LABEL_STYLE,
                                        ),
                                    ]),
                                    html.Div(children=[
                                        html.Label("Mode",
                                                   style=LABEL_STYLE),
                                        dcc.RadioItems(
                                            id="h-mode",
                                            options=[
                                                {"label": " Differential",
                                                 "value": "diff"},
                                                {"label": " Cumulative",
                                                 "value": "cumul"},
                                            ],
                                            value="cumul",
                                            inline=True,
                                            style=RADIO_STYLE,
                                            labelStyle=RADIO_LABEL_STYLE,
                                        ),
                                    ]),
                                    html.Div(children=[
                                        html.Label("Size lines",
                                                   style=LABEL_STYLE),
                                        dcc.RadioItems(
                                            id="size-mapping",
                                            options=[
                                                {"label": " Standard "
                                                 "(p\u1D65=0.14)",
                                                 "value": "standard"},
                                                {"label": " NEOMOD3 "
                                                 "(variable p\u1D65)",
                                                 "value": "neomod3"},
                                            ],
                                            value="neomod3",
                                            inline=True,
                                            style=RADIO_STYLE,
                                            labelStyle=RADIO_LABEL_STYLE,
                                        ),
                                    ]),
                                    html.Div(
                                        children=[
                                            dcc.Checklist(
                                                id="comp-labels-toggle",
                                                options=[
                                                    {"label": " Show "
                                                     "% labels",
                                                     "value": "show"}],
                                                value=["show"],
                                                style=RADIO_STYLE,
                                                labelStyle=
                                                    RADIO_LABEL_STYLE,
                                            ),
                                        ],
                                        style={"alignSelf": "flex-end"},
                                    ),
                                    html.Div(
                                        style={"alignSelf": "flex-end"},
                                        children=[
                                            html.Button(
                                                "Download CSV",
                                                id="btn-download-neomod",
                                                n_clicks=0,
                                                style=DOWNLOAD_BTN_STYLE,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            # Distribution chart
                            dcc.Graph(id="h-distribution",
                                      config=GRAPH_CONFIG),
                            html.P(
                                "Half-magnitude bins (Nesvorny et al. "
                                "2024, Icarus 411). Solid bars = "
                                "discovered NEOs; outlined bars stacked "
                                "on top = estimated undiscovered "
                                "(NEOMOD3 total minus discovered); "
                                "line = per-bin completeness.",
                                className="subtext",
                                style={"fontFamily": "sans-serif",
                                       "marginTop": "6px"},
                            ),
                            # ── NEOMOD3 reference table ──────────────
                            html.Hr(
                                style={"margin": "30px 0 20px 0"}),
                            html.H2(
                                "NEOMOD3 Population Model Reference",
                                style={"fontFamily": "sans-serif",
                                       "marginBottom": "5px"},
                            ),
                            html.P(
                                "Nesvorny et al. 2024, Icarus 411, "
                                "Table 3. Half-magnitude bins with "
                                "estimated population, 1\u03C3 bounds, "
                                "and current discovery completeness "
                                "from MPC database.",
                                className="subtext",
                                style={"fontFamily": "sans-serif",
                                       "marginTop": "0"},
                            ),
                            dcc.Graph(id="neomod3-table",
                                      config=GRAPH_CONFIG),
                        ]),
                    ],
                ),
                # ━━━ Tab 3: Multi-survey Comparison ━━━━━━━━━━━━━━━━━
                dcc.Tab(
                    label="Multi-survey Comparison",
                    value="tab-comparison",
                    className="nav-tab",
                    selected_className="nav-tab--selected",
                    children=[
                        html.Div(style={"paddingTop": "15px"}, children=[
                            # Year slider — full width
                            html.Div(
                                style={"marginBottom": "10px"},
                                children=[
                                    html.Label("Discovery years",
                                               style=LABEL_STYLE),
                                    dcc.RangeSlider(
                                        id="comp-year-range",
                                        min=year_min,
                                        max=year_max,
                                        value=[2004, year_max],
                                        marks={
                                            y: {"label": str(y)}
                                            for y in range(
                                                year_min,
                                                year_max + 1, 5)
                                        },
                                        tooltip={
                                            "placement": "bottom",
                                            "always_visible": False},
                                    ),
                                ],
                            ),
                            # Controls row
                            html.Div(
                                style={"display": "flex", "gap": "20px",
                                        "flexWrap": "wrap",
                                        "alignItems": "flex-end",
                                        "marginBottom": "15px"},
                                children=[
                                    html.Div(children=[
                                        html.Label("Size class",
                                                   style=LABEL_STYLE),
                                        dcc.Dropdown(
                                            id="comp-size-filter",
                                            options=(
                                                [{"label": "All sizes",
                                                  "value": "all"}]
                                                + [{"label": l,
                                                    "value": l}
                                                   for l, _, _ in H_BINS]
                                            ),
                                            value="all",
                                            clearable=False,
                                            style={"width": "270px"},
                                        ),
                                    ]),
                                    html.Div(children=[
                                        html.Label("Surveys for Venn "
                                                   "(max 3)",
                                                   style=LABEL_STYLE),
                                        dcc.Dropdown(
                                            id="comp-survey-select",
                                            options=[
                                                {"label": p, "value": p}
                                                for p in PROJECT_ORDER],
                                            value=["Catalina Survey",
                                                   "Pan-STARRS",
                                                   "ATLAS"],
                                            multi=True,
                                            style={"width": "350px"},
                                        ),
                                    ]),
                                    html.Div(children=[
                                        html.Label("Precovery",
                                                   style=LABEL_STYLE),
                                        dcc.RadioItems(
                                            id="comp-precovery",
                                            options=[
                                                {"label":
                                                    " Post-discovery",
                                                 "value": "post_only"},
                                                {"label":
                                                    " Include precoveries",
                                                 "value": "include"},
                                            ],
                                            value="post_only",
                                            inline=True,
                                            style=RADIO_STYLE,
                                            labelStyle=
                                                RADIO_LABEL_STYLE,
                                        ),
                                    ]),
                                    html.Div(
                                        style={"alignSelf": "flex-end"},
                                        children=[
                                            html.Button(
                                                "Download CSV",
                                                id="btn-download-comparison",
                                                n_clicks=0,
                                                style=DOWNLOAD_BTN_STYLE,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            # MPC codes reference
                            html.Details(
                                style={"marginBottom": "12px",
                                       "fontFamily": "sans-serif",
                                       "fontSize": "12px"},
                                children=[
                                    html.Summary(
                                        "Survey group MPC codes",
                                        style={"cursor": "pointer",
                                               "fontWeight": "bold",
                                               "fontSize": "13px"}),
                                    html.Div(
                                        style={"display": "flex",
                                               "flexWrap": "wrap",
                                               "gap": "8px 24px",
                                               "padding": "8px 0"},
                                        children=[
                                            html.Span(
                                                f"{proj}: "
                                                f"{', '.join(sorted(stns))}",
                                            )
                                            for proj in PROJECT_ORDER
                                            if proj in PROJECT_STATIONS
                                            for stns in
                                                [PROJECT_STATIONS[proj]]
                                        ],
                                    ),
                                ],
                            ),
                            # 2x2 visualization grid
                            dcc.Loading(
                                type="default",
                                children=[
                                    html.Div(
                                        style={
                                            "display": "grid",
                                            "gridTemplateColumns":
                                                "1fr 1fr",
                                            "gap": "10px"},
                                        children=[
                                            dcc.Graph(
                                                id="venn-diagram",
                                                config=GRAPH_CONFIG),
                                            dcc.Graph(
                                                id="survey-reach",
                                                config=GRAPH_CONFIG),
                                            dcc.Graph(
                                                id="pairwise-heatmap",
                                                config=GRAPH_CONFIG),
                                            dcc.Graph(
                                                id="comparison-summary",
                                                config=GRAPH_CONFIG),
                                        ],
                                    ),
                                ],
                            ),
                        ]),
                    ],
                ),
                # ━━━ Tab 4: Follow-up Timing ━━━━━━━━━━━━━━━━━━━━━━━━━
                dcc.Tab(
                    label="Follow-up Timing",
                    value="tab-followup",
                    className="nav-tab",
                    selected_className="nav-tab--selected",
                    children=[
                        html.Div(style={"paddingTop": "15px"}, children=[
                            # Year slider — full width
                            html.Div(
                                style={"marginBottom": "10px"},
                                children=[
                                    html.Label("Discovery years",
                                               style=LABEL_STYLE),
                                    dcc.RangeSlider(
                                        id="fu-year-range",
                                        min=year_min,
                                        max=year_max,
                                        value=[2004, year_max],
                                        marks={
                                            y: {"label": str(y)}
                                            for y in range(
                                                year_min,
                                                year_max + 1, 5)
                                        },
                                        tooltip={
                                            "placement": "bottom",
                                            "always_visible": False},
                                    ),
                                ],
                            ),
                            # Controls row
                            html.Div(
                                style={"display": "flex", "gap": "20px",
                                        "flexWrap": "wrap",
                                        "alignItems": "flex-end",
                                        "marginBottom": "15px"},
                                children=[
                                    html.Div(children=[
                                        html.Label("Size class",
                                                   style=LABEL_STYLE),
                                        dcc.Dropdown(
                                            id="fu-size-filter",
                                            options=(
                                                [{"label": "All sizes",
                                                  "value": "all"}]
                                                + [{"label": l,
                                                    "value": l}
                                                   for l, _, _ in H_BINS]
                                            ),
                                            value="all",
                                            clearable=False,
                                            style={"width": "270px"},
                                        ),
                                    ]),
                                    html.Div(
                                        style={"width": "250px"},
                                        children=[
                                            html.Label("Max days shown",
                                                       style=LABEL_STYLE),
                                            dcc.Slider(
                                                id="fu-max-days",
                                                min=7, max=200,
                                                value=90,
                                                marks={
                                                    7: "7", 30: "30",
                                                    90: "90", 200: "200",
                                                },
                                                tooltip={
                                                    "placement": "bottom",
                                                    "always_visible":
                                                        False},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"alignSelf": "flex-end"},
                                        children=[
                                            html.Button(
                                                "Download CSV",
                                                id="btn-download-followup",
                                                n_clicks=0,
                                                style=DOWNLOAD_BTN_STYLE,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            # Note
                            html.P(
                                "Follow-up = first post-discovery "
                                "observation by a different survey "
                                "project. The discovery survey's own "
                                "stations are excluded.",
                                className="subtext",
                                style={"fontFamily": "sans-serif",
                                       "marginBottom": "10px"},
                            ),
                            # 2x2 viz grid
                            html.Div(
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "1fr 1fr",
                                    "gap": "10px"},
                                children=[
                                    dcc.Graph(id="response-curve",
                                              config=GRAPH_CONFIG),
                                    dcc.Graph(id="survey-response",
                                              config=GRAPH_CONFIG),
                                    dcc.Graph(id="followup-network",
                                              config=GRAPH_CONFIG),
                                    dcc.Graph(id="followup-trend",
                                              config=GRAPH_CONFIG),
                                ],
                            ),
                        ]),
                    ],
                ),
                # ━━━ Tab 5: Discovery Circumstances ━━━━━━━━━━━━━━━━━━━
                dcc.Tab(
                    label="Discovery Circumstances",
                    value="tab-circumstances",
                    className="nav-tab",
                    selected_className="nav-tab--selected",
                    children=[
                        html.Div(style={"paddingTop": "15px"}, children=[
                            # Year slider — full width
                            html.Div(
                                style={"marginBottom": "10px"},
                                children=[
                                    html.Label("Discovery years",
                                               style=LABEL_STYLE),
                                    dcc.RangeSlider(
                                        id="circ-year-range",
                                        min=year_min,
                                        max=year_max,
                                        value=[2004, year_max],
                                        marks={
                                            y: {"label": str(y)}
                                            for y in range(
                                                year_min,
                                                year_max + 1, 5)
                                        },
                                        tooltip={
                                            "placement": "bottom",
                                            "always_visible": False},
                                    ),
                                ],
                            ),
                            # Controls row
                            html.Div(
                                style={"display": "flex", "gap": "20px",
                                        "flexWrap": "wrap",
                                        "alignItems": "flex-end",
                                        "marginBottom": "15px"},
                                children=[
                                    html.Div(children=[
                                        html.Label("Size class",
                                                   style=LABEL_STYLE),
                                        dcc.Dropdown(
                                            id="circ-size-filter",
                                            options=(
                                                [{"label": "All sizes",
                                                  "value": "all"}]
                                                + [{"label": l,
                                                    "value": l}
                                                   for l, _, _ in H_BINS]
                                            ),
                                            value="all",
                                            clearable=False,
                                            style={"width": "270px"},
                                        ),
                                    ]),
                                    html.Div(children=[
                                        html.Label("Color by",
                                                   style=LABEL_STYLE),
                                        dcc.RadioItems(
                                            id="circ-color-by",
                                            options=[
                                                {"label": " Survey",
                                                 "value": "survey"},
                                                {"label": " Size class",
                                                 "value": "size"},
                                                {"label": " Year",
                                                 "value": "year"},
                                            ],
                                            value="survey",
                                            inline=True,
                                            style=RADIO_STYLE,
                                            labelStyle=
                                                RADIO_LABEL_STYLE,
                                        ),
                                    ]),
                                    html.Div(
                                        style={"alignSelf": "flex-end"},
                                        children=[
                                            html.Button(
                                                "Download CSV",
                                                id="btn-download-circumstances",
                                                n_clicks=0,
                                                style=DOWNLOAD_BTN_STYLE,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            # Full-width sky map
                            dcc.Graph(id="sky-map",
                                      config=GRAPH_CONFIG),
                            # 2x2 grid for remaining plots
                            html.Div(
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "1fr 1fr",
                                    "gap": "20px 10px",
                                    "marginTop": "20px"},
                                children=[
                                    dcc.Graph(id="mag-distribution",
                                              config=GRAPH_CONFIG),
                                    dcc.Graph(id="elongation-hist",
                                              config=GRAPH_CONFIG),
                                    dcc.Graph(id="rate-plot",
                                              config=GRAPH_CONFIG),
                                    dcc.Graph(id="pa-rose",
                                              config=GRAPH_CONFIG),
                                ],
                            ),
                        ]),
                    ],
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Theme callback — update page background + text colors via CSS variables
# ---------------------------------------------------------------------------

@app.callback(
    Output("page-container", "style"),
    Input("theme-toggle", "value"),
)
def update_theme(theme_name):
    t = theme(theme_name)
    return {
        "backgroundColor": t["page"],
        "color": t["text"],
        "minHeight": "100vh",
        "padding": "20px",
        "--subtext-color": t["subtext"],
        "--hr-color": t["hr_color"],
        "--paper-bg": t["paper"],
        "--tab-border": t["hr_color"],
    }


# ---------------------------------------------------------------------------
# Service health check — banner-level connectivity status
# ---------------------------------------------------------------------------

@app.callback(
    Output("service-health-bar", "children"),
    Output("service-health-data", "data"),
    Input("service-health-poll", "n_intervals"),
)
def update_service_health(_n):
    """Periodically check external service connectivity."""
    import threading

    results = {}

    def _check():
        nonlocal results
        results = check_service_health()

    # Run in a thread with a timeout so we don't block callbacks
    t = threading.Thread(target=_check, daemon=True)
    t.start()
    t.join(timeout=15)

    if not results:
        # Timed out or not yet checked
        return html.Div(), {}

    _ss = {"fontFamily": "sans-serif", "fontSize": "11px"}
    dots = []
    for name in ["NEOfixer", "MPC", "JPL", "Sentry", "NEOCC"]:
        ok = results.get(name, False)
        color = "#4caf50" if ok else "#f5a623"
        dots.append(html.Span(children=[
            html.Span("\u25cf ", className="color-explicit",
                      style={"--explicit-color": color}),
            name,
        ], style={**_ss, "marginRight": "10px"}))

    bar = html.Div(
        style={"display": "flex", "flexWrap": "wrap",
               "alignItems": "center", "gap": "2px",
               "padding": "2px 12px", "marginBottom": "4px"},
        children=[
            html.Span("Services: ", style={**_ss,
                       "color": "var(--subtext-color, #888)",
                       "marginRight": "6px"}),
            *dots,
        ],
    )
    return bar, results


# ---------------------------------------------------------------------------
# Observability site selector — buttons + custom input → Store
# ---------------------------------------------------------------------------

@app.callback(
    Output("obs-site-selected", "data"),
    Input({"type": "obs-site-btn", "code": ALL}, "n_clicks"),
    Input({"type": "obs-site-custom", "code": ALL}, "value"),
    prevent_initial_call=True,
)
def select_obs_site(btn_clicks, custom_values):
    """Update selected site from button click or custom code entry."""
    trigger = ctx.triggered_id
    if isinstance(trigger, dict):
        if trigger.get("type") == "obs-site-btn":
            return trigger["code"]
        if trigger.get("type") == "obs-site-custom":
            val = custom_values[0] if custom_values else ""
            if val and len(val.strip()) >= 2:
                return val.strip().upper()
    return no_update



# ---------------------------------------------------------------------------
# Refresh-banner callback — show notice when cron job is updating caches
# ---------------------------------------------------------------------------

_SENTINEL_FILE = os.path.join(_APP_DIR, ".refreshing")


@app.callback(
    Output("refresh-banner", "children"),
    Input("refresh-check", "n_intervals"),
)
def check_refresh_status(_n):
    if os.path.exists(_SENTINEL_FILE):
        return html.Div(
            f"Data refresh in progress \u2014 results shown are from "
            f"the previous update ({query_timestamp}).",
            style={
                "backgroundColor": "#fff3cd",
                "color": "#856404",
                "padding": "10px 20px",
                "borderRadius": "4px",
                "marginBottom": "10px",
                "fontFamily": "sans-serif",
                "fontSize": "14px",
                "textAlign": "center",
                "border": "1px solid #ffc107",
            },
        )
    return None


# ---------------------------------------------------------------------------
# Loading-banner callback — shown while data loads at startup
# ---------------------------------------------------------------------------

@app.callback(
    Output("loading-banner", "children"),
    Output("loading-check", "disabled"),
    Output("subtitle-text", "children"),
    Input("loading-check", "n_intervals"),
)
def check_loading_status(_n):
    if _data_ready.is_set():
        if _data_error:
            banner = html.Div(
                f"Error loading data: {_data_error}",
                style={
                    "backgroundColor": "#f8d7da",
                    "color": "#721c24",
                    "padding": "10px 20px",
                    "borderRadius": "4px",
                    "marginBottom": "10px",
                    "fontFamily": "sans-serif",
                    "fontSize": "14px",
                    "textAlign": "center",
                    "border": "1px solid #f5c6cb",
                },
            )
            return banner, True, "Data load failed"
        count = f"{len(df):,}" if df is not None else "?"
        subtitle = f"Source: MPC/SBN database ({count} NEO discoveries)"
        return None, True, subtitle
    return html.Div(
        "Loading data from cache (please wait)...",
        style={
            "backgroundColor": "#cce5ff",
            "color": "#004085",
            "padding": "10px 20px",
            "borderRadius": "4px",
            "marginBottom": "10px",
            "fontFamily": "sans-serif",
            "fontSize": "14px",
            "textAlign": "center",
            "border": "1px solid #b8daff",
        },
    ), False, "Loading data..."


# ---------------------------------------------------------------------------
# Reset callback — restore default control values
# ---------------------------------------------------------------------------

def _get_defaults():
    """Return default control values using current year_min/year_max."""
    return {
        # Tab 1
        "year-range": [1995, year_max],
        "size-filter": "split",
        "cumulative-toggle": "annual",
        # Tab 2
        "h-year-range": [year_min, year_max],
        "h-range": [16.25, 22.75],
        "h-yscale": "linear",
        "h-mode": "cumul",
        "size-mapping": "neomod3",
        "comp-labels-toggle": ["show"],
        # Tab 3
        "comp-year-range": [2004, year_max],
        "comp-size-filter": "all",
        "comp-survey-select": ["Catalina Survey", "Pan-STARRS", "ATLAS"],
        "comp-precovery": "post_only",
        # Tab 4
        "fu-year-range": [2004, year_max],
        "fu-size-filter": "all",
        "fu-max-days": 90,
        # Tab 5
        "circ-year-range": [2004, year_max],
        "circ-size-filter": "all",
        "circ-color-by": "survey",
        # Shared
        "group-by": "combined",
        "plot-height": "700",
    }

_TAB_KEYS = {
    "tab-mpec": set(),  # no resettable controls
    "tab-discovery": {"year-range", "size-filter", "cumulative-toggle"},
    "tab-neomod": {"h-year-range", "h-range", "h-yscale", "h-mode",
                    "size-mapping", "comp-labels-toggle"},
    "tab-comparison": {"comp-year-range", "comp-size-filter",
                       "comp-survey-select", "comp-precovery"},
    "tab-followup": {"fu-year-range", "fu-size-filter", "fu-max-days"},
    "tab-circumstances": {"circ-year-range", "circ-size-filter",
                          "circ-color-by"},
}
_SHARED_KEYS = {"group-by", "plot-height"}

# Output order must match the tuple returned by reset_controls
_RESET_ORDER = [
    "year-range", "size-filter", "cumulative-toggle",
    "h-year-range", "h-range", "h-yscale", "h-mode",
    "size-mapping", "comp-labels-toggle",
    "comp-year-range", "comp-size-filter", "comp-survey-select",
    "comp-precovery",
    "fu-year-range", "fu-size-filter", "fu-max-days",
    "circ-year-range", "circ-size-filter", "circ-color-by",
    "group-by", "plot-height",
]


@app.callback(
    [Output(k, "value", allow_duplicate=True) for k in _RESET_ORDER],
    Input("reset-tab-btn", "n_clicks"),
    Input("reset-all-btn", "n_clicks"),
    State("tabs", "value"),
    prevent_initial_call=True,
)
def reset_controls(_tab_clicks, _all_clicks, active_tab):
    triggered = ctx.triggered_id
    defaults = _get_defaults()
    if triggered == "reset-all-btn":
        reset_keys = set(defaults)
    elif triggered == "reset-tab-btn":
        reset_keys = _TAB_KEYS.get(active_tab, set()) | _SHARED_KEYS
    else:
        raise PreventUpdate
    return tuple(
        defaults[k] if k in reset_keys else no_update
        for k in _RESET_ORDER
    )


# ---------------------------------------------------------------------------
# Discovery-by-year callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("discovery-bar", "figure"),
    Output("size-histogram", "figure"),
    Output("top-stations-table", "figure"),
    Input("year-range", "value"),
    Input("group-by", "value"),
    Input("size-filter", "value"),
    Input("cumulative-toggle", "value"),
    Input("theme-toggle", "value"),
    Input("plot-height", "value"),
    Input("tabs", "value"),
)
def update_charts(year_range, group_by, size_filter, view_mode, theme_name,
                  plot_height, _tab):
    if df is None:
        raise PreventUpdate
    t = theme(theme_name)
    y0, y1 = year_range
    filtered = df[(df["disc_year"] >= y0) & (df["disc_year"] <= y1)]

    if size_filter not in ("all", "split"):
        filtered = filtered[filtered["size_class"] == size_filter]

    # -- Main bar chart --
    if size_filter == "split":
        # Stack by size class (overrides Group by)
        color_col = "size_class"
        counts = filtered.groupby(
            ["disc_year", color_col]).size().reset_index(name="count")

        if view_mode == "cumulative":
            all_years = range(
                int(counts["disc_year"].min()),
                int(counts["disc_year"].max()) + 1)
            all_groups = counts[color_col].unique()
            full_idx = pd.MultiIndex.from_product(
                [all_years, all_groups], names=["disc_year", color_col])
            counts = (counts.set_index(["disc_year", color_col])
                      .reindex(full_idx, fill_value=0).reset_index())
            counts = counts.sort_values("disc_year")
            counts["count"] = counts.groupby(color_col)["count"].cumsum()

        bar_fig = go.Figure()
        for i, (label, _, _) in enumerate(H_BINS):
            gdata = counts[counts[color_col] == label]
            if len(gdata) > 0:
                bar_fig.add_trace(go.Bar(
                    x=gdata["disc_year"], y=gdata["count"], name=label,
                    marker_color=SIZE_COLORS[i],
                    hovertemplate=("Year %{x}<br>" + label
                                   + ": %{y:,}<extra></extra>"),
                ))

    elif group_by == "combined":
        counts = filtered.groupby("disc_year").size().reset_index(name="count")
        if view_mode == "cumulative":
            counts = counts.sort_values("disc_year")
            counts["count"] = counts["count"].cumsum()
        bar_fig = go.Figure(go.Bar(
            x=counts["disc_year"], y=counts["count"],
            marker_color="#607D8B",
            hovertemplate="Year %{x}<br>%{y:,} discoveries<extra></extra>",
        ))
    else:
        color_col = "project" if group_by == "project" else "station_name"
        counts = filtered.groupby(
            ["disc_year", color_col]).size().reset_index(name="count")

        if view_mode == "cumulative":
            all_years = range(
                int(counts["disc_year"].min()),
                int(counts["disc_year"].max()) + 1)
            all_groups = counts[color_col].unique()
            full_idx = pd.MultiIndex.from_product(
                [all_years, all_groups], names=["disc_year", color_col])
            counts = (counts.set_index(["disc_year", color_col])
                      .reindex(full_idx, fill_value=0).reset_index())
            counts = counts.sort_values("disc_year")
            counts["count"] = counts.groupby(color_col)["count"].cumsum()

        if group_by == "project":
            color_order = [p for p in PROJECT_ORDER
                           if p in counts[color_col].unique()]
            color_map = PROJECT_COLORS
        else:
            top = (counts.groupby(color_col)["count"]
                   .sum().nlargest(15).index.tolist())
            counts.loc[~counts[color_col].isin(top), color_col] = "Others"
            counts = (counts.groupby(["disc_year", color_col])
                      .sum().reset_index())
            color_order = top + (
                ["Others"] if "Others" in counts[color_col].values else [])
            color_map = None

        bar_fig = go.Figure()
        for gname in color_order:
            gdata = counts[counts[color_col] == gname]
            bar_fig.add_trace(go.Bar(
                x=gdata["disc_year"], y=gdata["count"], name=gname,
                marker_color=(color_map or {}).get(gname),
                hovertemplate=("Year %{x}<br>" + gname
                               + ": %{y:,}<extra></extra>"),
            ))

    title = "NEO Discoveries"
    if size_filter == "split":
        title += " by Size Class"
    elif group_by != "combined":
        title += f" by {'Project' if group_by == 'project' else 'Station'}"
    if size_filter not in ("all", "split"):
        title += f" \u2014 {size_filter}"
    if view_mode == "cumulative":
        title += " (Cumulative)"

    chart_h = int(plot_height)
    bar_fig.update_layout(
        barmode="stack",
        height=chart_h,
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        title=title,
        bargap=0.1,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        xaxis=dict(title="Year",
                   dtick=1 if (y1 - y0) <= 15 else 5),
        yaxis=dict(title="Discoveries"),
    )

    # -- Size distribution histogram --
    size_order = [l for l, _, _ in H_BINS] + ["Unknown H"]
    size_counts = filtered["size_class"].value_counts().reindex(
        size_order).dropna()
    size_fig = go.Figure(go.Bar(
        x=size_counts.index, y=size_counts.values,
        marker_color=["#440154", "#31688e", "#35b779", "#90d743", "#fde725"]
        [:len(size_counts)],
    ))
    size_fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        title="Size Distribution (selected range)",
        xaxis_title="Size Class (H magnitude)",
        yaxis_title="Count",
        showlegend=False,
    )

    # -- Top stations table --
    top_df = (
        filtered.groupby(["station_code", "station_name", "project"])
        .size().reset_index(name="discoveries")
        .sort_values("discoveries", ascending=False).head(15)
    )
    table_fig = go.Figure(go.Table(
        header=dict(
            values=["Station", "Project", "Discoveries"],
            fill_color=t["table_header"],
            font=dict(color=t["text"], size=13),
            align="left",
        ),
        cells=dict(
            values=[
                top_df["station_code"] + " " + top_df["station_name"],
                top_df["project"],
                top_df["discoveries"].map("{:,}".format),
            ],
            fill_color=t["table_cell"],
            font=dict(color=t["table_font"], size=12),
            align="left",
        ),
    ))
    table_fig.update_layout(
        title="Top 15 Discovery Sites (selected range)",
        template=t["template"],
        paper_bgcolor=t["paper"],
        margin=dict(l=10, r=10, t=40, b=10),
    )

    return bar_fig, size_fig, table_fig


# ---------------------------------------------------------------------------
# H-magnitude distribution callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("h-distribution", "figure"),
    Input("h-year-range", "value"),
    Input("group-by", "value"),
    Input("h-range", "value"),
    Input("h-yscale", "value"),
    Input("h-mode", "value"),
    Input("size-mapping", "value"),
    Input("comp-labels-toggle", "value"),
    Input("theme-toggle", "value"),
    Input("plot-height", "value"),
    Input("tabs", "value"),
)
def update_h_distribution(h_year_range, group_by, h_range, yscale, h_mode,
                          size_mapping, comp_labels, theme_name, plot_height,
                          _tab):
    if df is None:
        raise PreventUpdate
    t = theme(theme_name)
    hy0, hy1 = h_year_range
    # Snap slider values to nearest bin center to avoid floating-point drift
    h_lo = round(h_range[0] * 4) / 4  # snap to 0.25 grid
    h_hi = round(h_range[1] * 4) / 4
    filtered = df[(df["disc_year"] >= hy0) & (df["disc_year"] <= hy1)]

    # Only rows with valid H in the bin range
    valid = filtered[
        (filtered["h_bin_idx"] >= 0)
        & (filtered["h_bin_idx"] < len(H_BIN_CENTERS))
    ].copy()

    # Mask of bin indices within the selected H range
    bin_mask = (H_BIN_CENTERS >= h_lo) & (H_BIN_CENTERS <= h_hi)
    vis_centers = H_BIN_CENTERS[bin_mask]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # ── Total count per bin (for completeness) ───────────────────
    total_per_bin = np.zeros(len(H_BIN_CENTERS))
    for idx, cnt in valid["h_bin_idx"].value_counts().items():
        if 0 <= idx < len(total_per_bin):
            total_per_bin[idx] = cnt

    # Slice to visible range
    vis_total = total_per_bin[bin_mask]

    # In cumulative mode, count ALL discovered with H < each bin's upper
    # edge (including objects brighter than our first bin at H=15.25).
    # This matches NEOMOD3's N_cumul = N(H < H2) definition.
    if h_mode == "cumul":
        h_vals = filtered["h"]
        vis_cumul = np.array([
            int((h_vals < H_BIN_EDGES[i + 1]).sum())
            for i, m in enumerate(bin_mask) if m
        ])

    # ── Discovered bars (stacked by group or combined) ───────────
    if group_by == "combined":
        if h_mode == "diff":
            y_vals = vis_total
        else:
            y_vals = vis_cumul
        fig.add_trace(
            go.Bar(
                x=vis_centers, y=y_vals,
                name="Discovered",
                marker_color="#607D8B",
                width=0.36,
                hovertemplate="%{x:.2f}<br>Discovered: %{y:,}<extra></extra>",
            ),
            secondary_y=False,
        )
    else:
        color_col = "project" if group_by == "project" else "station_name"
        if group_by == "project":
            groups = [p for p in PROJECT_ORDER
                      if p in valid[color_col].unique()]
            colors = PROJECT_COLORS
        else:
            top = valid[color_col].value_counts().nlargest(10).index.tolist()
            valid.loc[~valid[color_col].isin(top), color_col] = "Others"
            filtered.loc[
                ~filtered[color_col].isin(top), color_col
            ] = "Others"
            groups = top + (
                ["Others"] if "Others" in valid[color_col].values else [])
            colors = {}

        for gname in groups:
            subset = valid[valid[color_col] == gname]
            counts = np.zeros(len(H_BIN_CENTERS))
            for idx, cnt in subset["h_bin_idx"].value_counts().items():
                if 0 <= idx < len(counts):
                    counts[idx] = cnt
            vis_counts = counts[bin_mask]
            if h_mode == "cumul":
                # True cumulative per group: count objects with H < each
                # bin upper edge, including objects brighter than first bin.
                # Stacking works because each object belongs to exactly one
                # group — sum of per-group cumulatives = combined cumulative.
                grp_h = filtered.loc[
                    filtered[color_col] == gname, "h"
                ]
                vis_counts = np.array([
                    int((grp_h < H_BIN_EDGES[i + 1]).sum())
                    for i, m in enumerate(bin_mask) if m
                ])
            fig.add_trace(
                go.Bar(
                    x=vis_centers, y=vis_counts, name=gname,
                    marker_color=colors.get(gname),
                    width=0.36,
                    hovertemplate=("%{x:.2f}<br>" + gname
                                   + ": %{y:,}<extra></extra>"),
                ),
                secondary_y=False,
            )

    # ── NEOMOD3 undiscovered remainder ──────────────────────────
    # The "remaining" bar stacks on top of discovered so the total
    # height = model prediction.  Clamped to 0 when discovered > model.
    nm = NEOMOD3_DF[
        (NEOMOD3_DF["h_center"] >= h_lo) & (NEOMOD3_DF["h_center"] <= h_hi)
    ].copy()

    model_col = "dn_model" if h_mode == "diff" else "n_cumul"

    # For differential: lookup per-bin discovered count
    # For cumulative: count ALL discovered with H < bin upper edge,
    #   including objects brighter than our first bin (H < 15.25).
    #   NEOMOD3 N_cumul is N(H < H2), so we must match that definition.
    diff_by_center = dict(zip(vis_centers, vis_total))

    if h_mode == "cumul":
        h_vals = filtered["h"]
        cumul_by_center = {}
        for _, row in nm.iterrows():
            cumul_by_center[row["h_center"]] = int((h_vals < row["h2"]).sum())

    def get_disc(hc):
        if h_mode == "diff":
            return diff_by_center.get(hc, 0)
        return cumul_by_center.get(hc, 0)

    remainder = []
    disc_for_hover = []
    for _, row in nm.iterrows():
        disc = get_disc(row["h_center"])
        disc_for_hover.append(disc)
        remainder.append(max(0, row[model_col] - disc))
    nm["remainder"] = remainder
    nm["disc_count"] = disc_for_hover

    model_outline_color = "rgba(160,160,160,0.6)" if theme_name == "dark" \
        else "rgba(120,120,120,0.5)"
    remainder_label = "Est. undiscovered" if h_mode == "diff" \
        else "Est. undiscovered (cumul)"
    fig.add_trace(
        go.Bar(
            x=nm["h_center"], y=nm["remainder"],
            name=remainder_label,
            marker=dict(
                color="rgba(0,0,0,0)",
                line=dict(color=model_outline_color, width=0.75),
            ),
            width=0.36,
            customdata=np.stack([
                nm[model_col].values,
                np.array(remainder),
            ], axis=-1),
            hovertemplate=(
                "%{x:.2f}<br>"
                "NEOMOD3 total: %{customdata[0]:,}<br>"
                "Undiscovered: %{customdata[1]:,}<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # ── Completeness line with 1-sigma error bars ───────────────
    # Error bars come from NEOMOD3's N_min/N_max (1σ on cumulative).
    # For differential mode, scale dN by the fractional uncertainty
    # from the cumulative bounds: dN_lo = dN * N_min/N, dN_hi = dN * N_max/N.
    # In cumulative mode, N_cumul = N(H < H2) so completeness points
    # belong at the right bin edge (h2), not the center.
    # In differential mode, dN covers the full bin so center is correct.
    comp_x, comp_y, err_lo, err_hi = [], [], [], []
    for _, row in nm.iterrows():
        hc = row["h_center"]
        disc = get_disc(hc)
        if h_mode == "cumul":
            model_val = row["n_cumul"]
            model_lo = row["n_min"]
            model_hi = row["n_max"]
        else:
            model_val = row["dn_model"]
            # Scale dN by fractional cumulative bounds
            frac_lo = row["n_min"] / row["n_cumul"] if row["n_cumul"] else 1
            frac_hi = row["n_max"] / row["n_cumul"] if row["n_cumul"] else 1
            model_lo = model_val * frac_lo
            model_hi = model_val * frac_hi
        if model_val > 0:
            comp = min(disc / model_val * 100, 100)
            # Higher model → lower completeness and vice versa
            c_lo = min(disc / model_hi * 100, 100) if model_hi > 0 else 0
            c_hi = min(disc / model_lo * 100, 100) if model_lo > 0 else 100
            comp_x.append(row["h2"] if h_mode == "cumul" else hc)
            comp_y.append(comp)
            err_lo.append(comp - c_lo)
            err_hi.append(c_hi - comp)

    show_labels = "show" in (comp_labels or [])

    fig.add_trace(
        go.Scatter(
            x=comp_x, y=comp_y,
            name="Completeness (%)",
            mode="lines+markers",
            line=dict(color="#ff6961", width=2.5, dash="dot"),
            marker=dict(size=5),
            error_y=dict(
                type="data",
                symmetric=False,
                array=err_hi,
                arrayminus=err_lo,
                color="rgba(255,105,97,0.4)",
                thickness=1.5,
                width=3,
            ),
            hovertemplate=(
                "%{x:.2f}<br>"
                "Completeness: %{y:.1f}%<br>"
                "1\u03C3 range: %{customdata[0]:.1f}\u2013%{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
            customdata=list(zip(
                [comp_y[i] - err_lo[i] for i in range(len(comp_y))],
                [comp_y[i] + err_hi[i] for i in range(len(comp_y))],
            )),
        ),
        secondary_y=True,
    )

    # Completeness labels as annotations
    if show_labels:
        label_bg = "rgba(30,30,30,0.85)" if theme_name == "dark" \
            else "rgba(255,255,255,0.85)"
        for i in range(len(comp_x)):
            fig.add_annotation(
                x=comp_x[i], y=comp_y[i], yref="y2",
                text=f"{comp_y[i]:.0f}%",
                showarrow=False,
                xshift=18,
                font=dict(size=9, color="#ff6961"),
                bgcolor=label_bg,
                borderpad=1,
            )

    # Scale secondary y-axis so 100% aligns with the rightmost bin's
    # model value on the primary axis (linear/sqrt modes only).
    rightmost_model = nm[model_col].iloc[-1] if len(nm) > 0 else 1
    if yscale != "log":
        y_primary_max = rightmost_model * 1.1
        fig.update_yaxes(
            range=[0, y_primary_max],
            secondary_y=False,
        )
    fig.update_yaxes(
        range=[0, 110],
        showticklabels=False,
        title_text="",
        showgrid=False,
        side="right",
        secondary_y=True,
    )
    # Reclaim the space reserved for the hidden secondary axis
    fig.update_layout(xaxis_domain=[0, 1])

    # Size reference lines from selected H-diameter mapping
    for h_val, label in SIZE_REFS[size_mapping]:
        fig.add_vline(x=h_val, line=dict(color="#ffcc00", width=1, dash="dash"),
                      annotation_text=label, annotation_position="top",
                      annotation_font_color="#ffcc00")

    # Annotate cumulative completeness at the 140m threshold
    h_140m = SIZE_REFS[size_mapping][_140M_IDX][0]
    if h_mode == "cumul" and h_lo <= h_140m <= h_hi:
        # Interpolate NEOMOD3 model N(<h_140m) between surrounding bin edges
        h_vals_all = filtered["h"]
        n_disc_140m = int((h_vals_all < h_140m).sum())
        # Find the bin containing h_140m
        n_model_140m = None
        for j, row in NEOMOD3_DF.iterrows():
            if row["h1"] <= h_140m < row["h2"]:
                n_prev = NEOMOD3_DF.iloc[j - 1]["n_cumul"] if j > 0 else (
                    row["n_cumul"] - row["dn_model"])
                frac = (h_140m - row["h1"]) / (row["h2"] - row["h1"])
                n_model_140m = n_prev + frac * (row["n_cumul"] - n_prev)
                break
        if n_model_140m and n_model_140m > 0:
            comp_140m = min(n_disc_140m / n_model_140m * 100, 100)
            fig.add_annotation(
                x=h_140m, y=comp_140m, yref="y2",
                text=f" {comp_140m:.0f}% at H={h_140m}",
                showarrow=True, arrowhead=2, arrowcolor=t["text"],
                ax=45, ay=-28,
                font=dict(size=12, color=t["text"]),
            )

    mode_label = "Differential" if h_mode == "diff" else "Cumulative"
    # Compute x-axis range that clips cleanly at bin edges (no half-bin overhang)
    x_range = [h_lo - 0.25, h_hi + 0.25]

    year_note = f" \u2014 {hy0}\u2013{hy1}" if hy0 != year_min or hy1 != year_max \
        else ""
    fig.update_layout(
        barmode="stack",
        height=int(plot_height),
        margin=dict(r=20),
        template=t["template"],
        paper_bgcolor=t["paper"], plot_bgcolor=t["plot"],
        title=(f"NEO Discoveries vs. NEOMOD3 ({mode_label}, half-mag bins)"
               + year_note),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        xaxis=dict(
            title="Absolute magnitude H",
            range=x_range,
            dtick=1,
        ),
    )
    fig.add_annotation(
        text=f"MPC data queried {query_timestamp} \u00b7 {len(df):,} NEOs (q \u2264 1.30 AU)",
        xref="paper", yref="paper",
        x=0.02, y=-0.08,
        showarrow=False,
        font=dict(size=10, color=t["subtext"]),
    )
    y_label = "NEOs per bin" if h_mode == "diff" else "Cumulative N(<H)"
    fig.update_yaxes(
        title_text=y_label,
        type="log" if yscale == "log" else "linear",
        secondary_y=False,
    )

    return fig


# ---------------------------------------------------------------------------
# NEOMOD3 reference table callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("neomod3-table", "figure"),
    Input("h-year-range", "value"),
    Input("theme-toggle", "value"),
    Input("tabs", "value"),
)
def update_neomod3_table(h_year_range, theme_name, _tab):
    if df is None:
        raise PreventUpdate
    t = theme(theme_name)
    hy0, hy1 = h_year_range
    filtered = df[(df["disc_year"] >= hy0) & (df["disc_year"] <= hy1)]

    # Count discovered NEOs per half-magnitude bin
    valid = filtered[
        (filtered["h_bin_idx"] >= 0)
        & (filtered["h_bin_idx"] < len(H_BIN_CENTERS))
    ]
    disc_per_bin = np.zeros(len(H_BIN_CENTERS))
    for idx, cnt in valid["h_bin_idx"].value_counts().items():
        if 0 <= idx < len(disc_per_bin):
            disc_per_bin[idx] = cnt

    # Build table rows aligned to NEOMOD3 bins
    # Cumulative completeness uses count of ALL discovered with H < H2
    # (including objects brighter than first bin edge) to match NEOMOD3's
    # N_cumul = N(H < H2) definition.
    h_vals = filtered["h"]
    rows = []
    for _, row in NEOMOD3_DF.iterrows():
        bin_idx = int(round((row["h_center"] - H_BIN_CENTERS[0]) / 0.5))
        disc = int(disc_per_bin[bin_idx]) if 0 <= bin_idx < len(disc_per_bin) else 0
        disc_below_h2 = int((h_vals < row["h2"]).sum())
        comp_diff = min(disc / row["dn_model"] * 100, 100) \
            if row["dn_model"] > 0 else 0
        comp_cumul = min(disc_below_h2 / row["n_cumul"] * 100, 100) \
            if row["n_cumul"] > 0 else 0
        rows.append({
            "bin": row["bin_label"],
            "dn_model": f"{row['dn_model']:,.0f}",
            "n_cumul": f"{row['n_cumul']:,.0f}",
            "n_range": f"{row['n_min']:,.0f}\u2013{row['n_max']:,.0f}",
            "disc": f"{disc:,}",
            "disc_cumul": f"{disc_below_h2:,}",
            "comp_diff": f"{comp_diff:.1f}%",
            "comp_cumul": f"{comp_cumul:.1f}%",
        })

    tbl = pd.DataFrame(rows)
    fig = go.Figure(go.Table(
        header=dict(
            values=["H bin", "Model dN", "Model N(&lt;H)",
                    "N 1\u03C3 range", "Discovered", "Disc. cumul.",
                    "Compl. (bin)", "Compl. (cumul.)"],
            fill_color=t["table_header"],
            font=dict(color=t["text"], size=12),
            align="center",
        ),
        cells=dict(
            values=[tbl[c] for c in tbl.columns],
            fill_color=t["table_cell"],
            font=dict(color=t["table_font"], size=11),
            align=["center", "right", "right", "center",
                   "right", "right", "right", "right"],
        ),
    ))
    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"],
        margin=dict(l=10, r=10, t=10, b=10),
        height=700,
    )
    return fig


# ---------------------------------------------------------------------------
# Multi-survey comparison callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("venn-diagram", "figure"),
    Output("survey-reach", "figure"),
    Output("pairwise-heatmap", "figure"),
    Output("comparison-summary", "figure"),
    Input("comp-year-range", "value"),
    Input("comp-size-filter", "value"),
    Input("comp-survey-select", "value"),
    Input("comp-precovery", "value"),
    Input("theme-toggle", "value"),
    Input("plot-height", "value"),
    Input("tabs", "value"),
)
def update_comparison(year_range, size_filter, survey_select,
                      precovery, theme_name, plot_height, active_tab):
    if active_tab != "tab-comparison" or df is None or df_apparition is None:
        raise PreventUpdate

    t = theme(theme_name)
    height = int(plot_height)
    exclude_precovery = precovery == "post_only"

    survey_sets, eligible = build_survey_sets(
        df, df_apparition, year_range, size_filter, exclude_precovery)

    # Venn diagram
    survey_select = survey_select or []
    if len(survey_select) < 1:
        venn_fig = _empty_figure(
            "Select 1\u20133 surveys for Venn diagram", t, height)
    elif len(survey_select) == 1:
        s = survey_sets.get(survey_select[0], set())
        c = PROJECT_COLORS.get(survey_select[0], "#a9a9a9")
        venn_fig = _make_venn1(s, survey_select[0], c, t, height)
    elif len(survey_select) == 2:
        venn_sets = [survey_sets.get(s, set()) for s in survey_select]
        venn_colors = [PROJECT_COLORS.get(s, "#a9a9a9")
                       for s in survey_select]
        venn_fig = _make_venn2(
            venn_sets, survey_select, venn_colors, t, height)
    else:
        sel = survey_select[:3]
        venn_sets = [survey_sets.get(s, set()) for s in sel]
        venn_colors = [PROJECT_COLORS.get(s, "#a9a9a9") for s in sel]
        venn_fig = _make_venn3(
            venn_sets, sel, venn_colors, t, height)

    reach_fig = _make_survey_reach(survey_sets, t, height)
    heatmap_fig = _make_pairwise_heatmap(survey_sets, t, height)
    summary_fig = _make_comparison_summary(
        survey_sets, eligible, t, height)

    return venn_fig, reach_fig, heatmap_fig, summary_fig


# ---------------------------------------------------------------------------
# Follow-up timing callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("response-curve", "figure"),
    Output("survey-response", "figure"),
    Output("followup-network", "figure"),
    Output("followup-trend", "figure"),
    Input("fu-year-range", "value"),
    Input("fu-size-filter", "value"),
    Input("fu-max-days", "value"),
    Input("theme-toggle", "value"),
    Input("plot-height", "value"),
    Input("tabs", "value"),
)
def update_followup(year_range, size_filter, max_days, theme_name,
                    plot_height, active_tab):
    if active_tab != "tab-followup" or df is None or df_apparition is None:
        raise PreventUpdate

    t = theme(theme_name)
    height = int(plot_height)

    fu_data, total = build_followup_data(
        df, df_apparition, year_range, size_filter)

    if total == 0 or len(fu_data) == 0:
        empty = _empty_figure(
            "No follow-up data for selection", t, height)
        return empty, empty, empty, empty

    curve = _make_response_curve(fu_data, total, max_days, t, height)
    boxes = _make_survey_response_box(fu_data, max_days, t, height)
    network = _make_followup_network(fu_data, t, height)
    trend = _make_followup_trend(fu_data, t, height)

    return curve, boxes, network, trend


# ---------------------------------------------------------------------------
# Discovery circumstances callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("sky-map", "figure"),
    Output("mag-distribution", "figure"),
    Output("elongation-hist", "figure"),
    Output("rate-plot", "figure"),
    Output("pa-rose", "figure"),
    Input("circ-year-range", "value"),
    Input("circ-size-filter", "value"),
    Input("circ-color-by", "value"),
    Input("group-by", "value"),
    Input("theme-toggle", "value"),
    Input("plot-height", "value"),
    Input("tabs", "value"),
)
def update_circumstances(year_range, size_filter, color_by, group_by,
                          theme_name, plot_height, active_tab):
    if active_tab != "tab-circumstances" or df is None:
        raise PreventUpdate

    t = theme(theme_name)
    height = int(plot_height)
    y0, y1 = year_range

    filtered = df[(df["disc_year"] >= y0) & (df["disc_year"] <= y1)]
    if size_filter != "all":
        filtered = filtered[filtered["size_class"] == size_filter]

    sky = _make_sky_map(filtered, color_by, group_by, t, height)
    mag = _make_mag_distribution(filtered, color_by, group_by, t, height)
    elong = _make_elongation_hist(filtered, color_by, group_by, t, height)
    rate = _make_rate_plot(filtered, color_by, group_by, t, height)
    pa = _make_pa_rose(filtered, t, height)

    return sky, mag, elong, rate, pa


# ---------------------------------------------------------------------------
# MPEC Browser callbacks
# ---------------------------------------------------------------------------

_MPEC_CACHE_DIR = os.path.join(_APP_DIR, ".mpec_cache")

# Badge styles
_BADGE_STYLE = {
    "display": "inline-block",
    "padding": "2px 8px",
    "borderRadius": "4px",
    "fontSize": "11px",
    "fontWeight": "600",
    "fontFamily": "sans-serif",
    "marginLeft": "8px",
    "verticalAlign": "middle",
}
_DISCOVERY_BADGE = {**_BADGE_STYLE,
                    "backgroundColor": "#2e7d32", "color": "white"}
_RECOVERY_BADGE = {**_BADGE_STYLE,
                   "backgroundColor": "#1565c0", "color": "white"}
_PHA_BADGE = {**_BADGE_STYLE,
              "backgroundColor": "#c62828", "color": "white"}
_140M_BADGE = {**_BADGE_STYLE,
               "backgroundColor": "#e65100", "color": "white"}
_1KM_BADGE = {**_BADGE_STYLE,
              "backgroundColor": "#b71c1c", "color": "white"}
_DOU_BADGE = {**_BADGE_STYLE,
              "backgroundColor": "#7b1fa2", "color": "white"}
_RETRACTION_BADGE = {**_BADGE_STYLE,
                     "backgroundColor": "#d84315", "color": "white"}
_EDITORIAL_BADGE = {**_BADGE_STYLE,
                    "backgroundColor": "#e68a00", "color": "white"}
_IDENTIFICATION_BADGE = {**_BADGE_STYLE,
                         "backgroundColor": "#00838f", "color": "white"}

# List item styles
_MPEC_ITEM_STYLE = {
    "padding": "10px 12px",
    "marginBottom": "6px",
    "borderRadius": "6px",
    "cursor": "pointer",
    "fontFamily": "sans-serif",
    "border": "1px solid var(--hr-color, #ccc)",
    "boxShadow": "none",
    "transition": "background-color 0.15s",
}
_MPEC_ITEM_SELECTED = {
    **_MPEC_ITEM_STYLE,
    "border": "1px solid #5b8def",
    "boxShadow": "inset 3px 0 0 #5b8def",
}


_MPEC_TYPE_LABELS = {
    "discovery": ("Discovery", _DISCOVERY_BADGE),
    "recovery": ("Recovery", _RECOVERY_BADGE),
    "dou": ("DOU", _DOU_BADGE),
    "retraction": ("Retraction", _RETRACTION_BADGE),
    "editorial": ("Editorial", _EDITORIAL_BADGE),
    "identification": ("Identification", _IDENTIFICATION_BADGE),
}


def _mpec_badge(mpec_type):
    label, style = _MPEC_TYPE_LABELS.get(mpec_type, ("Editorial", _EDITORIAL_BADGE))
    return html.Span(label, className="mpec-badge", style=style)


def _get_cached_summary(mpec_path):
    """Extract orbit summary from a cached MPEC (fast, disk-only)."""
    if not mpec_path:
        return None
    safe_name = mpec_path.replace("/", "_").strip("_") + ".txt"
    cache_path = os.path.join(_MPEC_CACHE_DIR, safe_name)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r") as f:
            text = f.read()
    except OSError:
        return None
    import re as _re
    summary = {}
    # Extract UTC time from MPEC header: "Issued YYYY Month DD, HH:MM UT"
    m_time = _re.search(r"Issued\s+\d{4}\s+\w+\s+\d{1,2},\s*(\d{2}:\d{2})\s*UT",
                         text)
    if m_time:
        summary["utc_time"] = m_time.group(1)

    # Extract discovery station from observations (disc='*' at col 12)
    obs_start = text.find("Observations:")
    if obs_start >= 0:
        obs_end = text.find("Observer detail", obs_start)
        if obs_end < 0:
            obs_end = len(text)
        for line in text[obs_start:obs_end].split("\n"):
            if len(line) > 12 and line[12] == "*" and len(line) >= 80:
                summary["disc_stn"] = line[77:80].strip()
                break

    # Extract orbital elements section to avoid false matches elsewhere
    oe_start = text.find("Orbital elements")
    if oe_start < 0:
        return summary or None
    # Section ends at next known header or end of text
    oe_end = len(text)
    for hdr in ["Residual", "Ephemeris:", "Observer detail"]:
        idx = text.find(hdr, oe_start + 20)
        if idx > 0 and idx < oe_end:
            oe_end = idx
    oe_text = text[oe_start:oe_end]

    # Earth MOID (appears on first line of section)
    m = _re.search(r"Earth MOID\s*=\s*([\d.]+)", oe_text)
    if m:
        summary["moid"] = float(m.group(1))
    # Check explicit PHA flag from MPC
    if "PHA," in oe_text or "PHA " in oe_text:
        summary["is_pha_explicit"] = True
    # H and G from the P/H/G/U line
    m = _re.search(r"H\s+([\d.]+)\s+G\s+([\d.]+)", oe_text)
    if m:
        summary["H"] = float(m.group(1))
    # a, e from dedicated element lines (start-of-line)
    m = _re.search(r"^a\s+([\d.]+)", oe_text, _re.MULTILINE)
    if m:
        summary["a"] = float(m.group(1))
    m = _re.search(r"^e\s+([\d.]+)", oe_text, _re.MULTILINE)
    if m:
        summary["e"] = float(m.group(1))
    m = _re.search(r"Incl\.\s+([\d.]+)", oe_text)
    if m:
        summary["i"] = float(m.group(1))
    # Derive q
    if "a" in summary and "e" in summary:
        summary["q"] = summary["a"] * (1 - summary["e"])
    # Extract designation for orbit classification
    from lib.mpec_parser import _extract_designation
    desig = _extract_designation(text) or ""
    summary["designation"] = desig

    # Classify orbit
    q = summary.get("q")
    if q is not None:
        summary["is_neo"] = q <= 1.3
        a = summary.get("a", 0)
        e = summary.get("e", 0)
        cls = _classify_orbit(a, e, q, designation=desig)
        if cls:
            summary["class"] = cls
        # PHA: explicit flag from MPC, or MOID <= 0.05 AU and H <= 22
        moid = summary.get("moid")
        h_val = summary.get("H")
        if summary.get("is_pha_explicit"):
            summary["is_pha"] = True
        elif moid is not None and h_val is not None:
            summary["is_pha"] = moid <= 0.05 and h_val <= 22.0
    return summary


def _build_mpec_list_item(entry, idx):
    """Build a clickable MPEC list card."""
    summary = _get_cached_summary(entry.get("path"))
    # Build summary annotation line
    annot_parts = []
    _sub = {"fontSize": "11px", "color": "var(--subtext-color, #888)",
            "fontFamily": "monospace"}
    annot_spans = []
    badge_spans = []
    if summary:
        disc_stn = summary.get("disc_stn", "")
        if disc_stn:
            annot_spans.append(html.Span(disc_stn))
        cls = summary.get("class", "")
        if cls:
            annot_spans.append(html.Span(cls))
        h_val = summary.get("H")
        if h_val is not None:
            annot_spans.append(html.Span(f"H={h_val:.1f}"))
        moid = summary.get("moid")
        if moid is not None:
            annot_spans.append(html.Span(f"MOID={moid:.3f}"))
        if summary.get("is_pha"):
            badge_spans.append(html.Span("PHA", className="mpec-badge", style=_PHA_BADGE))
        # Size badges based on H magnitude
        if h_val is not None and h_val <= 17.75:
            badge_spans.append(html.Span("1km", className="mpec-badge", style=_1KM_BADGE))
        elif h_val is not None and h_val <= 22.0 and not summary.get("is_pha"):
            badge_spans.append(html.Span("140m", className="mpec-badge", style=_140M_BADGE))

    # Build title line: "2026 CX2" + smaller "(MPEC 2026-C119)"
    title = entry.get("title", "")
    mpec_id = entry.get("mpec_id", "")

    title_children = [
        html.Span(title, style={"fontSize": "14px", "fontWeight": "600"}),
    ]
    if mpec_id:
        title_children.append(html.Span(
            f" ({mpec_id})",
            style={"fontSize": "12px", "fontWeight": "400",
                   "color": "var(--subtext-color, #888)"}))

    children = [
        html.Div(
            style={"display": "flex", "justifyContent": "space-between",
                   "alignItems": "center"},
            children=[
                html.Span(children=title_children),
                _mpec_badge(entry.get("type", "discovery")),
            ],
        ),
        html.Div(
            (entry.get("date", "") +
             (f"  {summary['utc_time']} UT" if summary and summary.get("utc_time") else "")),
            style={"fontSize": "12px",
                   "color": "var(--subtext-color, #888)",
                   "marginTop": "2px"},
        ),
    ]
    if annot_spans or badge_spans:
        # Interleave text spans with dot separators
        interleaved = []
        for i, sp in enumerate(annot_spans):
            if i > 0:
                interleaved.append(html.Span(" \u00b7 "))
            interleaved.append(sp)
        annot_row = [html.Span(children=interleaved, style=_sub)] if interleaved else []
        badge_row = html.Span(children=badge_spans,
                              style={"marginLeft": "auto"}) if badge_spans else None
        row_children = annot_row + ([badge_row] if badge_row else [])
        children.append(html.Div(
            children=row_children,
            style={"display": "flex", "justifyContent": "space-between",
                   "alignItems": "center", "marginTop": "3px"},
        ))

    return html.Div(
        id={"type": "mpec-item", "index": idx},
        n_clicks=0,
        style=_MPEC_ITEM_STYLE,
        children=children,
        **{"data-path": entry.get("path", "")},
    )


def _classify_orbit(a, e, q, designation=""):
    """Classify NEO orbit from elements."""
    # Comets don't get asteroid orbit class labels
    if designation and designation.startswith(("C/", "P/", "D/")):
        return "Comet"
    if q is None:
        return ""
    if q > 1.3:
        return "non-NEO"
    if a is not None and e is not None:
        Q = a * (1 + e)
        if a < 1.0 and Q < 0.983:
            return "Atira"
        if a < 1.0:
            return "Aten"
    if q <= 1.017:
        return "Apollo"
    return "Amor"


def _get_orbit_class(oe, detail=None):
    """Return the orbit class label (e.g. 'Apollo') from elements."""
    if not oe:
        return ""
    a = oe.get("a")
    e = oe.get("e")
    q = oe.get("q")
    desig = detail.get("designation", "") if detail else ""
    return _classify_orbit(a, e, q, designation=desig)


def _is_pha(oe, detail=None):
    """Check if object is a PHA from elements and raw text."""
    if not oe:
        return False
    oe_raw = detail.get("orbital_elements_raw", "") if detail else ""
    if "PHA," in oe_raw or "PHA " in oe_raw:
        return True
    moid = oe.get("earth_moid")
    h_val = oe.get("H")
    if moid is not None and h_val is not None:
        return moid <= 0.05 and h_val <= 22.0
    return False


def _build_orbit_info_line(oe, detail=None):
    """Build a single-line H / MOID / U / arc / obs summary."""
    if not oe:
        return html.Div()

    h_val = oe.get("H")
    moid = oe.get("earth_moid")

    parts = []
    if h_val is not None:
        parts.append(html.Span(f"H {h_val:.1f}"))
    if moid is not None:
        parts.append(html.Span(f"MOID {moid:.3f} au"))

    u_val = oe.get("U")
    if u_val is not None:
        parts.append(html.Span(f"U {int(u_val)}"))
    if detail:
        arc = detail.get("arc_days")
        if arc is not None:
            parts.append(html.Span(f"arc {arc:.0f} days"))
        n_obs = detail.get("n_obs")
        if n_obs:
            parts.append(html.Span(f"obs {n_obs}"))

    if not parts:
        return html.Div()

    interleaved = []
    for i, sp in enumerate(parts):
        if i > 0:
            interleaved.append(html.Span(" \u00b7 "))
        interleaved.append(sp)

    return html.Div(
        children=interleaved,
        style={"fontFamily": "monospace", "fontSize": "15px",
               "color": "var(--subtext-color, #888)",
               "marginTop": "1px", "marginBottom": "10px"},
    )


def _linkify_preamble(text):
    """Convert MPEC references and URLs in preamble text to clickable links.

    Patterns matched:
    - "M.P.E.C. 2026-C105" → link to that MPEC on MPC
    - "MPEC 2024-F104" → link to that MPEC on MPC
    - "https://www.minorplanetcenter.net/" → clickable link
    """
    import re as _re
    _LINK_STYLE = {"color": "#5b8def", "textDecoration": "none"}
    # Combined pattern: MPEC references and the MPC URL
    pattern = _re.compile(
        r"(M\.P\.E\.C\.\s+(\d{4}-[A-Z]\d+))"   # "M.P.E.C. 2026-C105"
        r"|(MPEC\s+(\d{4}-[A-Z]\d+))"            # "MPEC 2024-F104"
        r"|(https://www\.minorplanetcenter\.net/)" # MPC URL
    )
    parts = []
    pos = 0
    for m in pattern.finditer(text):
        # Add plain text before this match
        if m.start() > pos:
            parts.append(html.Span(text[pos:m.start()]))
        if m.group(1):
            # M.P.E.C. reference
            url = mpec_id_to_url(m.group(2))
            parts.append(html.A(m.group(1), href=url, target="_blank",
                                style=_LINK_STYLE) if url
                         else html.Span(m.group(1)))
        elif m.group(3):
            # MPEC reference (in revision lines)
            url = mpec_id_to_url(m.group(4))
            parts.append(html.A(m.group(3), href=url, target="_blank",
                                style=_LINK_STYLE) if url
                         else html.Span(m.group(3)))
        elif m.group(5):
            # MPC URL
            parts.append(html.A(m.group(5), href=m.group(5),
                                target="_blank", style=_LINK_STYLE))
        pos = m.end()
    # Trailing text
    if pos < len(text):
        parts.append(html.Span(text[pos:]))
    return parts if parts else [html.Span(text)]


_DEFAULT_SECTION_STATE = {
    "0": False, "1": False, "2": False, "3": False,
    "4": False, "5": False, "6": False, "7": False,
}


def _build_mpec_detail(detail, section_state=None, in_recent=True):
    """Build the right-panel detail view for a selected MPEC."""
    if not detail:
        return html.Div("Could not load MPEC.",
                        style={"fontFamily": "sans-serif",
                               "color": "var(--subtext-color, #888)"})

    if section_state is None:
        section_state = _DEFAULT_SECTION_STATE

    def _is_open(idx):
        return section_state.get(str(idx), _DEFAULT_SECTION_STATE.get(str(idx), False))

    designation = detail.get("designation", detail.get("title", ""))
    mpec_id = detail.get("mpec_id", "")
    date = detail.get("date", "")
    mpec_type = detail.get("type", "discovery")
    mpec_url = detail.get("mpec_url", "")

    # Detect identification MPECs ("1993 TA = 1985 FF") and recover
    # the subject designation from the packed obs80 observations.
    identification_title = ""
    is_editorial = mpec_type not in ("discovery", "recovery")
    if " = " in designation and not is_editorial:
        identification_title = designation  # preserve for subtitle
        mpec_type = "identification"
        obs_text = detail.get("observations", "")
        if obs_text:
            packed_obs = obs_text.strip().split("\n")[0][:12].strip()
            if packed_obs:
                try:
                    designation = unpack_designation(packed_obs)
                except Exception:
                    pass  # keep original designation

    # Resolve designation to current identity (discovery/recovery only)
    resolved = None
    if not is_editorial and designation:
        try:
            resolved = resolve_designation(designation)
        except Exception:
            resolved = None

    # Build packed designation for external links (skip for editorials)
    packed = ""
    if designation and not is_editorial:
        try:
            packed = pack_designation(designation).strip()
        except Exception:
            packed = ""

    # External links — use resolved designation for better lookup on
    # external services (permanent number or current primary designation)
    links = []
    link_desig = designation  # default to MPEC designation
    if resolved and resolved["permid"]:
        link_desig = resolved["permid"]
    elif resolved and resolved["is_secondary"] and resolved["primary_desig"]:
        link_desig = resolved["primary_desig"]
    link_packed = ""
    if link_desig:
        try:
            link_packed = pack_designation(link_desig).strip()
        except Exception:
            link_packed = packed  # fall back to original
    if not link_packed:
        link_packed = packed
    link_nospace = link_desig.replace(" ", "") if link_desig else ""
    if link_packed:
        links.append(html.A(
            "NEOfixer",
            href=f"https://neofixer.arizona.edu/site/500/{link_packed}",
            target="_blank", style=_link_btn_style()))
        links.append(html.A(
            "JPL SBDB",
            href=f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={link_packed}",
            target="_blank", style=_link_btn_style()))
        if link_nospace:
            links.append(html.A(
                "NEOCC",
                href=f"https://neo.ssa.esa.int/search-for-asteroids?sum=1&des={link_nospace}",
                target="_blank", style=_link_btn_style()))
        links.append(html.A(
            "MPC Explorer",
            href=f"https://data.minorplanetcenter.net/explorer/?tab=Designated&search={link_desig}",
            target="_blank", style=_link_btn_style()))
        links.append(html.A(
            "MPC DB",
            href=f"https://www.minorplanetcenter.net/db_search/show_object?utf8=✓&object_id={link_desig}",
            target="_blank", style=_link_btn_style()))
    if mpec_url:
        links.append(html.A("MPEC", href=mpec_url, target="_blank",
                            style=_link_btn_style()))

    # Parse observations to find discovery station (skip for editorials)
    disc_stn = None
    obs_text = detail.get("observations", "")
    if obs_text and not is_editorial:
        _, disc_stn = _build_obs_section(obs_text)

    # Parse discoverer info from observer credits
    observers = detail.get("observers", "")
    disc_info_line = _build_discoverer_line(observers, disc_stn) if not is_editorial else html.Div()

    # Build orbit summary line and class label from parsed elements.
    # Prefer DB-resolved orbit class (precise) over MPEC element classification.
    oe = detail.get("orbital_elements", {})
    orbit_class = _get_orbit_class(oe, detail) if not is_editorial else ""
    if resolved and resolved.get("orbit_class"):
        orbit_class = resolved["orbit_class"]
    is_pha = _is_pha(oe, detail) if not is_editorial else False
    orbit_info = _build_orbit_info_line(oe, detail) if not is_editorial else html.Div()

    # Assemble accordion sections.
    #
    # Discovery / Recovery: full section treatment:
    #   0. Preamble, 1. Observations, 2. Observer details,
    #   3. Comparison with prediction (recovery only),
    #   4. Orbital elements, 5. Residuals, 6. Ephemeris, 7. Copyright
    #
    # All other types (DOU, Retraction, Editorial): single section
    # with the full content, labeled by type.
    is_recovery = (mpec_type == "recovery")
    sections = []
    header = detail.get("header", "")

    if is_editorial:
        # Single section with full content, labeled by type.
        # Use a distinct id so toggle events don't overwrite section-0
        # state (which is the Preamble for discovery/recovery MPECs).
        _section_labels = {"dou": "Daily Orbit Update",
                           "retraction": "Retraction",
                           "editorial": "Editorial"}
        section_label = _section_labels.get(mpec_type, "Editorial")
        content = header or "(no content)"
        sections.append(_mpec_section(
            section_label, _linkify_preamble(content) if header else content,
            open_default=True, mono=True, section_id="mpec-section-editorial",
            max_height=None))
    else:
        if header:
            sections.append(_mpec_section(
                "Preamble", _linkify_preamble(header),
                open_default=_is_open(0),
                mono=True, section_id="mpec-section-0"))
        else:
            sections.append(_mpec_section(
                "Preamble", "(no header)", open_default=_is_open(0),
                mono=False, section_id="mpec-section-0"))

        obs_label = "Additional Observations" if is_recovery else "Observations"
        if obs_text:
            obs_section, _ = _build_obs_section(
                obs_text, open_default=_is_open(1),
                section_id="mpec-section-1", label=obs_label)
            sections.append(obs_section)
        else:
            sections.append(_mpec_section(
                obs_label, "(none)", open_default=_is_open(1),
                mono=False, section_id="mpec-section-1"))

        if observers:
            obs_credit = _build_observer_sections(
                observers, disc_stn, open_default=_is_open(2),
                section_id="mpec-section-2")
            if obs_credit:
                sections.append(obs_credit)
            else:
                sections.append(_mpec_section(
                    "Observer details", "(none)", open_default=_is_open(2),
                    mono=False, section_id="mpec-section-2"))
        else:
            sections.append(_mpec_section(
                "Observer details", "(none)", open_default=_is_open(2),
                mono=False, section_id="mpec-section-2"))

        comparison = detail.get("comparison", "")
        if comparison:
            sections.append(_mpec_section(
                "Comparison with prediction", comparison,
                open_default=_is_open(3), mono=True,
                section_id="mpec-section-3"))

        oe_raw = detail.get("orbital_elements_raw", "")
        if oe_raw:
            sections.append(_mpec_section(
                "Orbital elements", oe_raw, open_default=_is_open(4),
                mono=True, section_id="mpec-section-4"))
        else:
            sections.append(_mpec_section(
                "Orbital elements", "(none)", open_default=_is_open(4),
                mono=False, section_id="mpec-section-4"))

        residuals = detail.get("residuals", "")
        if residuals:
            sections.append(_build_residuals_section(
                residuals, disc_stn, obs_text,
                open_default=_is_open(5), section_id="mpec-section-5"))
        else:
            sections.append(_mpec_section(
                "Residuals", "(none)", open_default=_is_open(5),
                mono=False, section_id="mpec-section-5"))

        ephemeris = detail.get("ephemeris", "")
        if ephemeris:
            sections.append(_mpec_section(
                "Ephemeris", ephemeris, open_default=_is_open(6),
                mono=True, section_id="mpec-section-6"))
        else:
            sections.append(_mpec_section(
                "Ephemeris", "(none)", open_default=_is_open(6),
                mono=False, section_id="mpec-section-6"))

        copyright_line = detail.get("copyright", "")
        if copyright_line:
            sections.append(_mpec_section(
                "Copyright", _linkify_preamble(copyright_line),
                open_default=_is_open(7),
                mono=False, section_id="mpec-section-7"))
        else:
            sections.append(_mpec_section(
                "Copyright", "(none)", open_default=_is_open(7),
                mono=False, section_id="mpec-section-7"))

    # Larger badge styles for summary (not used in MPEC list)
    _SUMMARY_BADGE = {"display": "inline-block", "padding": "3px 10px",
                      "borderRadius": "4px", "fontSize": "13px",
                      "fontWeight": "600", "fontFamily": "sans-serif",
                      "marginLeft": "10px", "verticalAlign": "middle"}

    # Line 1: designation + badge + orbit class + PHA (inline)
    line1_children = [
        html.Span(designation,
                   style={"fontFamily": "sans-serif", "fontSize": "26px",
                          "fontWeight": "700"}),
    ]
    _type_label, _type_badge_style = _MPEC_TYPE_LABELS.get(
        mpec_type, ("Editorial", _EDITORIAL_BADGE))
    line1_children.append(html.Span(
        _type_label, className="mpec-badge", style={**_SUMMARY_BADGE,
                            "backgroundColor": _type_badge_style["backgroundColor"],
                            "color": _type_badge_style["color"]}))
    if orbit_class:
        line1_children.append(html.Span(
            orbit_class,
            style={"fontFamily": "sans-serif", "fontSize": "18px",
                   "fontWeight": "600", "marginLeft": "10px",
                   "verticalAlign": "middle"}))
    if is_pha:
        line1_children.append(html.Span(
            "PHA", className="mpec-badge", style={**_SUMMARY_BADGE,
                          "backgroundColor": "#c62828",
                          "color": "white"}))
    # Size badges based on H magnitude (NEOs only)
    _NEO_CLASSES = {"Atira", "Aten", "Apollo", "Amor",
                    "Interior Earth Object", "Dual-status (NEO/comet)"}
    is_neo = orbit_class in _NEO_CLASSES
    h_for_badge = oe.get("H")
    if is_neo and h_for_badge is not None and h_for_badge <= 17.75:
        line1_children.append(html.Span(
            "1km", className="mpec-badge", style={**_SUMMARY_BADGE,
                          "backgroundColor": "#b71c1c",
                          "color": "white"}))
    elif is_neo and h_for_badge is not None and h_for_badge <= 22.0 and not is_pha:
        line1_children.append(html.Span(
            "140m", className="mpec-badge", style={**_SUMMARY_BADGE,
                          "backgroundColor": "#e65100",
                          "color": "white"}))

    if resolved:
        id_text = ""
        has_secondary = resolved["is_secondary"] and resolved["primary_desig"]
        has_number = resolved["is_numbered"] and resolved["permid"]
        if has_secondary and has_number:
            name_suffix = f" {resolved['iau_name']}" if resolved["iau_name"] else ""
            id_text = f"{resolved['primary_desig']} ({resolved['permid']}{name_suffix})"
        elif has_secondary:
            id_text = resolved["primary_desig"]
        elif has_number:
            name_suffix = f" {resolved['iau_name']}" if resolved["iau_name"] else ""
            id_text = f"{resolved['permid']}{name_suffix}"
        if id_text:
            line1_children.append(html.Span(
                id_text,
                style={"fontFamily": "sans-serif", "fontSize": "26px",
                       "fontWeight": "700",
                       "marginLeft": "auto", "whiteSpace": "nowrap"}))

    # Line 2: linked MPEC ID + date + prev/next nav
    # mpec_id may already contain "MPEC " prefix (from web fetch / API)
    # or may be bare "2026-C105" (from cache). Normalize for display.
    _bare_id = mpec_id.replace("MPEC ", "", 1).strip() if mpec_id else ""
    mpec_display = f"MPEC {_bare_id}" if _bare_id else ""
    if mpec_display and mpec_url:
        mpec_id_el = html.A(
            mpec_display, href=mpec_url, target="_blank",
            style={"fontFamily": "sans-serif", "fontSize": "16px",
                   "color": "#5b8def", "textDecoration": "none"})
    else:
        mpec_id_el = html.Span(
            mpec_display,
            style={"fontFamily": "sans-serif", "fontSize": "16px",
                   "color": "var(--subtext-color, #888)"})

    # Compute ISO date for the date picker display
    _nav_date_iso = ""
    if date:
        try:
            from datetime import datetime as _dt
            _nav_date_iso = _dt.strptime(
                date.split(",")[0].strip(), "%Y %b %d").strftime("%Y-%m-%d")
        except Exception:
            pass
    if not _nav_date_iso and mpec_id:
        import re as _re2
        _m = _re2.search(r"(\d{4})-([A-Z])", mpec_id)
        if _m:
            _letters = "ABCDEFGHJKLMNOPQRSTUVWXY"
            _idx = _letters.find(_m.group(2))
            if _idx >= 0:
                _mo = _idx // 2 + 1
                _dy = 1 if _idx % 2 == 0 else 16
                _nav_date_iso = f"{int(_m.group(1)):04d}-{_mo:02d}-{_dy:02d}"

    # MPEC navigation row: Earliest / Prev / Next / Most Recent … Random
    _EARLIEST_MPEC_PATH = "/mpec/J93/J93S01.html"
    prev_path = detail.get("prev_path", "")
    next_path = detail.get("next_path", "")
    _nav_btn = {"display": "inline-block", "padding": "4px 12px",
                "borderRadius": "4px", "fontSize": "13px",
                "fontFamily": "sans-serif", "fontWeight": "500",
                "border": "1px solid var(--hr-color, #ccc)",
                "color": "inherit",
                "backgroundColor": "var(--paper-bg, white)",
                "cursor": "pointer"}
    _nav_btn_subtle = {**_nav_btn, "fontSize": "12px", "padding": "3px 10px",
                       "color": "var(--subtext-color, #888)"}
    _nav_disabled = {**_nav_btn, "visibility": "hidden",
                     "padding": "4px 12px"}
    nav_children = [
        html.Div(style={"flex": "1"}),
        html.Div(
            style={"display": "flex", "gap": "2px", "alignItems": "center"},
            children=[
                html.Button(
                    "\u21e4 Earliest", id="mpec-nav-earliest",
                    **{"data-path": _EARLIEST_MPEC_PATH},
                    style=_nav_btn_subtle),
                html.Button(
                    "\u2190 Prev", id="mpec-nav-prev",
                    **{"data-path": prev_path or ""},
                    style=_nav_btn if prev_path else _nav_disabled),
                dcc.Input(
                    id="mpec-nav-date", type="date",
                    value=_nav_date_iso,
                    min="1993-09-16",
                    style={**_nav_btn, "width": "130px",
                           "padding": "3px 6px", "fontSize": "12px"},
                ),
                html.Button(
                    "Next \u2192", id="mpec-nav-next",
                    **{"data-path": next_path or ""},
                    style=_nav_btn if next_path else _nav_disabled),
                html.Button(
                    "Most Recent \u21e5", id="mpec-nav-latest",
                    style=_nav_btn_subtle),
            ],
        ),
        html.Div(style={"flex": "1", "display": "flex",
                         "justifyContent": "flex-end"}),
        html.Button(
            "Random", id="mpec-nav-random",
            style=_nav_btn_subtle),
    ]
    nav_row = html.Div(
        nav_children,
        style={"display": "flex", "alignItems": "center",
               "marginBottom": "8px",
               "position": "sticky", "top": "0",
               "zIndex": "10",
               "backgroundColor": "var(--paper-bg, white)",
               "paddingTop": "4px", "paddingBottom": "4px"})

    _SUMMARY_HEIGHT = "150px"  # fixed height so all MPECs align

    summary = html.Div(children=[
        # Navigation row
        nav_row,
        # Summary section (fixed height)
        html.Div(
            style={"marginBottom": "10px", "minHeight": _SUMMARY_HEIGHT,
                   "display": "flex", "flexDirection": "column"},
            children=[
                html.Div(children=[
                    # Line 1: designation + badge + class + PHA
                    html.Div(children=line1_children,
                             style={"display": "flex",
                                    "alignItems": "center",
                                    "flexWrap": "wrap",
                                    "marginBottom": "10px"}),
                    # Identification subtitle (e.g. "1993 TA = 1985 FF")
                    html.Div(
                        identification_title,
                        style={"fontFamily": "sans-serif",
                               "fontSize": "15px", "fontStyle": "italic",
                               "color": "var(--subtext-color, #888)",
                               "marginBottom": "6px"},
                    ) if identification_title else None,
                    # Line 2: MPEC ID (linked) + date
                    html.Div(children=[
                        mpec_id_el,
                        html.Span(f"  {date}",
                                   style={"fontFamily": "sans-serif",
                                          "fontSize": "16px",
                                          "color": "var(--subtext-color, #888)",
                                          "marginLeft": "10px"}),
                    ], style={"marginBottom": "10px"}),
                    # Line 3: discoverer
                    orbit_info,
                    # Line 4: orbit params (combined)
                    disc_info_line,
                ]),
                # Spacer pushes annotations to bottom
                html.Div(style={"flex": "1"}),
                # Bottom row: Sentry/NEOCC annotations + direct lookup note
                html.Div(
                    style={"display": "flex", "alignItems": "flex-end"},
                    children=[
                        html.Div(id="mpec-risk-line",
                                 style={"flex": "1"}),
                    ] + ([html.Span(
                        "Direct lookup",
                        style={"fontFamily": "sans-serif",
                               "fontSize": "11px",
                               "color": "var(--subtext-color, #888)",
                               "fontStyle": "italic",
                               "whiteSpace": "nowrap"})]
                         if not in_recent else []),
                ),
            ],
        ),
        # External links row
        html.Div(
            style={"display": "flex", "gap": "8px", "marginBottom": "14px",
                   "flexWrap": "wrap", "alignItems": "flex-end"},
            children=links + ([
                html.Span(style={"flex": "1"}),  # spacer pushes right
                html.Span("NEOfixer download:",
                          style={"fontSize": "11px", "whiteSpace": "nowrap",
                                 "color": "var(--subtext-color, #888)",
                                 "fontFamily": "sans-serif",
                                 "alignSelf": "center"}),
                html.A("Orbit",
                       href=f"https://neofixerapi.arizona.edu/orbit/?object={link_packed}",
                       target="_blank", style=_link_btn_style()),
                html.A("Obs",
                       href=f"https://neofixerapi.arizona.edu/obs/?object={link_packed}",
                       target="_blank", style=_link_btn_style()),
                html.A("ADES",
                       href=f"https://neofixerapi.arizona.edu/obs/?object={link_packed}&format=xml",
                       target="_blank", style=_link_btn_style()),
            ] if link_packed else []),
        ) if links else html.Div(),
    ])

    section_panel = html.Div(children=sections)

    return summary, section_panel


def _link_btn_style():
    return {
        "display": "inline-block",
        "padding": "5px 14px",
        "borderRadius": "4px",
        "fontSize": "13px",
        "fontFamily": "sans-serif",
        "fontWeight": "500",
        "textDecoration": "none",
        "border": "1px solid var(--hr-color, #ccc)",
        "color": "inherit",
        "backgroundColor": "var(--paper-bg, white)",
    }


# ---------------------------------------------------------------------------
# Observability chart (NEOfixer ephemeris)
# ---------------------------------------------------------------------------

_MIN_ALTITUDE = 20  # typical CSS minimum working altitude


def _obs_site_buttons(selected_site):
    """Build the site selector row (buttons + custom input)."""
    base = {"fontSize": "12px", "fontFamily": "monospace",
            "padding": "3px 10px", "marginRight": "4px",
            "cursor": "pointer", "borderRadius": "3px"}
    active = {**base, "fontWeight": "700",
              "borderColor": "#5b8def",
              "boxShadow": "0 0 0 1px #5b8def"}
    buttons = []
    for code in _OBS_SITES:
        buttons.append(html.Button(
            code,
            id={"type": "obs-site-btn", "code": code},
            n_clicks=0,
            style=active if code == selected_site else base,
        ))
    return html.Div(
        children=[
            html.Span("Site: ",
                       style={"fontSize": "12px",
                              "color": "var(--subtext-color, #aaa)",
                              "marginRight": "6px",
                              "fontFamily": "sans-serif"}),
            *buttons,
            dcc.Input(id={"type": "obs-site-custom", "code": "input"},
                      type="text", placeholder="code", debounce=True,
                      className="obs-site-input",
                      style={"width": "70px", "fontSize": "12px",
                             "fontFamily": "monospace",
                             "padding": "3px 6px", "marginLeft": "4px",
                             "borderRadius": "3px",
                             "border": "none"}),
        ],
        style={"display": "flex", "alignItems": "center",
               "flexWrap": "wrap", "padding": "8px 10px 4px"},
    )


def _build_observability_section(packed_desig, designation, site="I52",
                                 chart_height=300):
    """Build observability chart using NEOfixer ephemeris data."""
    from datetime import datetime, timezone

    # Fetch ephemeris for requested site
    ephem_data = fetch_neofixer_ephem(site, packed_desig)
    if not ephem_data or not ephem_data.get("entries"):
        return None

    entries = ephem_data["entries"]
    if len(entries) < 10:
        return None

    # Parse into arrays
    times = []
    alts = []
    mags = []
    expts = []
    rates = []
    sky_brs = []
    for e in entries:
        iso = e.get("ISO_time", "")
        if not iso:
            continue
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        times.append(t)
        alts.append(e.get("alt", -90))
        mags.append(e.get("mag"))
        expts.append(e.get("ExpT"))
        rates.append(e.get("motion_rate"))
        sky_brs.append(e.get("SkyBr", 0))

    if not times:
        return None

    now = datetime.now(timezone.utc)

    # Find nights: periods where altitude > 0 and SkyBr > 19 (dark sky)
    # Show up to 5 nights from now
    from datetime import timedelta
    t_start = now - timedelta(hours=6)
    t_end = now + timedelta(days=5)

    # Filter to time window
    filtered_t = []
    filtered_alt = []
    filtered_mag = []
    filtered_expt = []
    filtered_rate = []
    hover_texts = []
    for i, t in enumerate(times):
        if t_start <= t <= t_end:
            filtered_t.append(t)
            filtered_alt.append(alts[i])
            m = mags[i]
            filtered_mag.append(m)
            filtered_expt.append(expts[i])
            filtered_rate.append(rates[i])
            # Hover text
            parts = [t.strftime("%Y-%m-%d %H:%M UT")]
            parts.append(f"Alt: {alts[i]:.1f}\u00b0")
            if m is not None:
                parts.append(f"V: {m:.1f}")
            if expts[i] is not None:
                parts.append(f"Exp: {expts[i]:.0f}s")
            if rates[i] is not None:
                parts.append(f"Rate: {rates[i]:.1f}\u00b0/d")
            hover_texts.append("<br>".join(parts))

    if not filtered_t:
        return None

    # Build figure
    fig = go.Figure()

    # Horizon band (alt < 0)
    fig.add_hrect(y0=-90, y1=0, fillcolor="rgba(50,50,50,0.3)",
                  line_width=0, layer="below")

    # Minimum working altitude line (as a trace so it renders reliably
    # in dynamically-sized containers — add_hline uses paper coords that
    # can fail on first paint)
    fig.add_trace(go.Scattergl(
        x=[filtered_t[0], filtered_t[-1]],
        y=[_MIN_ALTITUDE, _MIN_ALTITUDE],
        mode="lines",
        line={"color": "rgba(255,165,0,0.5)", "width": 1, "dash": "dash"},
        name=f"Min alt {_MIN_ALTITUDE}\u00b0",
        hoverinfo="skip",
        showlegend=True,
    ))

    # Altitude trace — color by whether object is observable
    # (above min alt and sky is dark)
    obs_colors = []
    for i, alt in enumerate(filtered_alt):
        if alt >= _MIN_ALTITUDE:
            obs_colors.append("#3cb44b")  # green = observable
        elif alt >= 0:
            obs_colors.append("#f0ad4e")  # amber = low
        else:
            obs_colors.append("#999")     # grey = below horizon

    fig.add_trace(go.Scattergl(
        x=filtered_t,
        y=filtered_alt,
        mode="lines",
        line={"color": "#3cb44b", "width": 2},
        name=f"Altitude ({site})",
        hovertext=hover_texts,
        hoverinfo="text",
        fill="tozeroy",
        fillcolor="rgba(60, 180, 75, 0.08)",
    ))

    # Magnitude on secondary y-axis
    valid_mag_t = []
    valid_mag_v = []
    mag_hover = []
    for i, m in enumerate(filtered_mag):
        if m is not None and filtered_alt[i] >= 0:
            valid_mag_t.append(filtered_t[i])
            valid_mag_v.append(m)
            mag_hover.append(f"V={m:.1f}")

    if valid_mag_v:
        fig.add_trace(go.Scattergl(
            x=valid_mag_t,
            y=valid_mag_v,
            mode="lines",
            line={"color": "#f032e6", "width": 1.5, "dash": "dot"},
            name="V mag",
            yaxis="y2",
            hovertext=mag_hover,
            hoverinfo="text",
        ))

    # Current time marker (as a trace — shapes with yref="paper" can
    # fail to render in dynamically-sized containers)
    fig.add_trace(go.Scattergl(
        x=[now, now],
        y=[-10, 90],
        mode="lines",
        line={"color": "rgba(255,80,80,0.7)", "width": 1.5},
        name="Now",
        hoverinfo="skip",
        showlegend=True,
    ))

    # Night shading — approximate using sky brightness data or
    # simple time-based heuristic.  Mark sunset/sunrise bands.
    # For Mt. Lemmon (lat ~32.4°N), rough sunset ~01:30 UT, sunrise ~13:30 UT
    # in February.  We'll shade these bands.
    for day_offset in range(-1, 6):
        night_start = now.replace(hour=1, minute=30, second=0,
                                  microsecond=0) + timedelta(days=day_offset)
        night_end = night_start.replace(hour=13, minute=30)
        if night_end < t_start or night_start > t_end:
            continue
        ns = night_start.isoformat()
        ne = night_end.isoformat()
        tw_s = (night_start - timedelta(hours=1)).isoformat()
        tw_e = (night_end + timedelta(hours=1)).isoformat()
        # Twilight bands (approximate)
        fig.add_vrect(x0=tw_s, x1=ns,
                      fillcolor="rgba(30,30,80,0.1)", line_width=0,
                      layer="below")
        fig.add_vrect(x0=ne, x1=tw_e,
                      fillcolor="rgba(30,30,80,0.1)", line_width=0,
                      layer="below")
        # Dark time
        fig.add_vrect(x0=ns, x1=ne,
                      fillcolor="rgba(15,15,50,0.08)", line_width=0,
                      layer="below")

    # Find peak observable altitude and annotate
    peak_alt = -90
    peak_idx = 0
    for i, alt in enumerate(filtered_alt):
        if alt > peak_alt:
            peak_alt = alt
            peak_idx = i

    # Key statistics text
    stats_parts = []
    if peak_alt > 0:
        stats_parts.append(f"Peak alt: {peak_alt:.0f}\u00b0")
        peak_mag = filtered_mag[peak_idx]
        if peak_mag is not None:
            stats_parts.append(f"V at peak: {peak_mag:.1f}")
        peak_expt = filtered_expt[peak_idx]
        if peak_expt is not None:
            stats_parts.append(f"Exp: {peak_expt:.0f}s")
        peak_rate = filtered_rate[peak_idx]
        if peak_rate is not None:
            stats_parts.append(f"Rate: {peak_rate:.1f}\u00b0/d")

    fig.update_layout(
        height=chart_height,
        margin={"l": 50, "r": 50, "t": 45, "b": 40},
        xaxis={"title": "", "gridcolor": "rgba(128,128,128,0.15)"},
        yaxis={"title": "Altitude (\u00b0)", "range": [-10, 90],
               "gridcolor": "rgba(128,128,128,0.15)"},
        yaxis2={"title": "V mag", "overlaying": "y", "side": "right",
                "autorange": "reversed",
                "gridcolor": "rgba(128,128,128,0.05)"},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "sans-serif", "size": 12, "color": "#aaa"},
        legend={"orientation": "h", "y": 1.18, "x": 0,
                "font": {"size": 11}},
        hovermode="x unified",
    )

    # Build the section
    chart_div = dcc.Graph(
        figure=fig,
        config={"displayModeBar": "hover",
                "modeBarButtonsToRemove": [
                    "lasso2d", "select2d", "autoScale2d"],
                "toImageButtonOptions": {
                    "format": "png", "scale": 2},
                "displaylogo": False},
        responsive=True,
        style={"height": f"{chart_height}px"},
    )

    _stats_style = {"fontFamily": "sans-serif", "fontSize": "11px",
                    "color": "var(--subtext-color, #888)"}
    stats_line = html.Div(
        style={"display": "flex", "justifyContent": "space-between",
               "padding": "0 10px 6px"},
        children=[
            html.Span(
                " \u2502 ".join(stats_parts) if stats_parts else "Below horizon",
                style=_stats_style),
            html.Span("powered by NEOfixer",
                       style={**_stats_style, "fontStyle": "italic"}),
        ],
    )

    return html.Div(children=[
        _obs_site_buttons(site),
        chart_div,
        stats_line,
    ], style={"padding": "4px"})


# Alternating tracklet background colors (light, theme-aware)
_TRACKLET_COLORS = [
    "rgba(100, 150, 255, 0.18)",  # blue tint
    "rgba(100, 200, 130, 0.18)",  # green tint
    "rgba(200, 150, 80, 0.18)",   # amber tint
    "rgba(180, 100, 200, 0.18)",  # purple tint
    "rgba(200, 100, 100, 0.18)",  # red tint
    "rgba(100, 200, 200, 0.18)",  # teal tint
]


def _build_obs_section(obs_text, open_default=False, section_id=None,
                        label="Observations"):
    """Build the Observations accordion with tracklet color-coding.

    Returns (section_element, discovery_station_code).
    """
    lines = obs_text.split("\n")
    # Find the discovery station (line with '*' at column 12)
    disc_stn = None
    disc_key = None
    for line in lines:
        if len(line) > 12 and line[12] == "*" and len(line) >= 80:
            disc_stn = line[77:80].strip()
            date_part = line[15:25].strip()
            day_key = date_part.split(".")[0] if "." in date_part else date_part
            disc_key = f"{disc_stn}:{day_key}"
            break

    # Group lines by station code (columns 78-80 in 80-col format)
    # and date (columns 16-25).  A tracklet = same station + same night.
    tracklet_groups = []
    current_key = None
    current_lines = []
    for line in lines:
        if len(line) >= 80:
            stn = line[77:80].strip()
            date_part = line[15:25].strip()  # "YYYY MM DD"
            # Use station + integer date as tracklet key
            day_key = date_part.split(".")[0] if "." in date_part else date_part
            key = f"{stn}:{day_key}"
        elif line.strip():
            key = current_key  # continuation line
        else:
            key = None  # blank line

        if key != current_key and current_lines:
            tracklet_groups.append((current_key, current_lines))
            current_lines = []
        current_key = key
        current_lines.append(line)

    if current_lines:
        tracklet_groups.append((current_key, current_lines))

    # Assign colors to unique station-date tracklets
    seen_keys = {}
    color_idx = 0
    children = []
    # Discovery tracklet color — stronger green highlight
    _DISC_BG = "rgba(60, 180, 75, 0.22)"
    for key, grp_lines in tracklet_groups:
        is_disc_tracklet = (key == disc_key)
        if key and key not in seen_keys:
            if is_disc_tracklet:
                seen_keys[key] = _DISC_BG
            else:
                seen_keys[key] = _TRACKLET_COLORS[
                    color_idx % len(_TRACKLET_COLORS)]
                color_idx += 1
        bg = seen_keys.get(key, "transparent")
        for line in grp_lines:
            # Mark discovery observation (has '*' at column 13)
            is_disc_obs = len(line) > 12 and line[12] == "*"
            style = {
                "backgroundColor": bg,
                "fontWeight": "700" if is_disc_obs else "normal",
            }
            if is_disc_tracklet:
                style["boxShadow"] = "inset 3px 0 0 #3cb44b"
            children.append(html.Div(line, style=style))

    content_style = {
        "padding": "10px",
        "fontSize": "13px",
        "lineHeight": "1.5",
        "overflowX": "auto",
        "maxHeight": "400px",
        "overflowY": "auto",
        "fontFamily": "monospace",
        "whiteSpace": "pre",
    }

    props = {
        "open": open_default,
        "style": {"marginBottom": "12px",
                  "border": "1px solid var(--hr-color, #ccc)",
                  "borderRadius": "6px"},
        "children": [
            html.Summary(
                label,
                style={"padding": "10px 14px", "cursor": "pointer",
                       "fontFamily": "sans-serif", "fontWeight": "600",
                       "fontSize": "14px",
                       "backgroundColor": "var(--paper-bg, white)",
                       "borderRadius": "6px"},
            ),
            html.Div(children=children, style=content_style),
        ],
    }
    if section_id is not None:
        props["id"] = section_id
    section = html.Details(**props)
    return section, disc_stn


def _build_discoverer_line(observers_text, disc_stn):
    """Parse discovery station block to extract site ID, name, observers.

    Returns a compact Div: "G96 Mt. Lemmon Survey — D. Rankin, E. Smith"
    MPC observer blocks use double-spacing between sentences.
    Observer list continues until "Measurers" or telescope description.
    """
    if not observers_text or not disc_stn:
        return html.Div()
    import re as _re
    blocks = _re.split(r"(?=^[A-Z0-9]{3} )", observers_text, flags=_re.MULTILINE)
    for block in blocks:
        block = block.strip()
        stn_match = _re.match(r"^([A-Z0-9]{3})\s+", block)
        if not stn_match or stn_match.group(1) != disc_stn:
            continue
        # Site name: from after station code to first double-spaced period
        name_m = _re.match(r"^[A-Z0-9]{3}\s+(.+?)\.\s{2,}", block, _re.DOTALL)
        site_name = " ".join(name_m.group(1).split()) if name_m else ""
        # Observer(s): from "Observer(s) " up to ".  Measurer" if present,
        # otherwise up to ".  " followed by a digit (telescope description).
        obs_m = _re.search(
            r"Observers?\s+(.+?)\.(?=\s{2,}Measurer)", block, _re.DOTALL)
        if not obs_m:
            # No measurers — observers run to period before telescope desc
            obs_m = _re.search(
                r"Observers?\s+(.+?)\.(?=\s{2,}\d)", block, _re.DOTALL)
        if not obs_m:
            # Fallback: observers to end of block
            obs_m = _re.search(
                r"Observers?\s+(.+)\.", block, _re.DOTALL)
        observer = " ".join(obs_m.group(1).split()) if obs_m else ""

        parts = [
            html.Span(f"{disc_stn} {site_name}",
                       style={"fontWeight": "600"}),
        ]
        if observer:
            parts.append(html.Span(f" \u2014 {observer}",
                         style={"color": "var(--subtext-color, #888)"}))
        return html.Div(
            children=parts,
            style={"fontFamily": "sans-serif", "fontSize": "15px",
                   "marginTop": "2px", "marginBottom": "10px"},
        )
    return html.Div()


def _build_observer_sections(observers_text, disc_stn, followup_stn=None,
                              open_default=False, section_id=None):
    """Build Observer details section with discovery station highlighted.

    Returns a single collapsible Details section (closed by default).
    """
    import re as _re
    if not observers_text:
        return None

    # Split into station blocks
    blocks = _re.split(r"(?=^[A-Z0-9]{3} )", observers_text, flags=_re.MULTILINE)
    children = []
    _block_style = {
        "padding": "4px 8px",
        "fontSize": "13px",
        "lineHeight": "1.5",
        "fontFamily": "sans-serif",
        "whiteSpace": "pre-wrap",
    }

    for block in blocks:
        block = block.rstrip()
        if not block:
            continue
        stn_match = _re.match(r"^([A-Z0-9]{3}) ", block)
        stn_code = stn_match.group(1) if stn_match else None

        style = {**_block_style}
        if stn_code and stn_code == disc_stn:
            style["backgroundColor"] = "rgba(60, 180, 75, 0.15)"
            style["boxShadow"] = "inset 3px 0 0 #3cb44b"
            style["borderRadius"] = "4px"
        children.append(html.Div(block, style=style))

    if not children:
        return None

    content_div = html.Div(
        children=children,
        style={"padding": "10px", "maxHeight": "400px",
               "overflowY": "auto"},
    )
    props = {
        "open": open_default,
        "style": {"marginBottom": "12px",
                  "border": "1px solid var(--hr-color, #ccc)",
                  "borderRadius": "6px"},
        "children": [
            html.Summary(
                "Observer details",
                style={"padding": "10px 14px", "cursor": "pointer",
                       "fontFamily": "sans-serif", "fontWeight": "600",
                       "fontSize": "14px",
                       "backgroundColor": "var(--paper-bg, white)",
                       "borderRadius": "6px"},
            ),
            content_div,
        ],
    }
    if section_id is not None:
        props["id"] = section_id
    return html.Details(**props)


def _build_residuals_section(residuals_text, disc_stn, obs_text,
                              open_default=False, section_id=None):
    """Build Residuals section with discovery tracklet entries highlighted.

    Residual entries look like: "260210 G96  0.5+  0.1-"
    Multiple entries per line, separated by whitespace.
    """
    import re as _re
    # Derive YYMMDD for discovery date from observations
    disc_yymmdd = None
    if disc_stn and obs_text:
        for line in obs_text.split("\n"):
            if len(line) > 12 and line[12] == "*" and len(line) >= 80:
                # Date is at cols 15-25: "2026 02 10.xxxxx"
                date_part = line[15:25].strip()
                # Extract YYYY MM DD
                m = _re.match(r"(\d{4})\s+(\d{2})\s+(\d{2})", date_part)
                if m:
                    disc_yymmdd = m.group(1)[2:] + m.group(2) + m.group(3)
                break

    if not disc_yymmdd or not disc_stn:
        return _mpec_section("Residuals", residuals_text,
                             open_default=open_default, mono=True,
                             section_id=section_id)

    # The discovery tracklet residual marker: "YYMMDD STN"
    disc_marker = f"{disc_yymmdd} {disc_stn}"

    # Parse each line and highlight spans matching discovery tracklet
    lines = residuals_text.split("\n")
    children = []
    _DISC_BG = "rgba(60, 180, 75, 0.22)"
    for line in lines:
        if disc_marker in line:
            # Highlight individual entries containing the marker
            # Each entry is ~20 chars: "YYMMDD STN  RA+  Dec-"
            parts = []
            pos = 0
            while pos < len(line):
                idx = line.find(disc_marker, pos)
                if idx < 0:
                    parts.append(html.Span(line[pos:]))
                    break
                if idx > pos:
                    parts.append(html.Span(line[pos:idx]))
                # Find the end of this entry (next entry starts with digit
                # after whitespace, or end of line)
                entry_end = idx + len(disc_marker)
                # Grab the residual values that follow
                rest = line[entry_end:]
                m = _re.match(r"(\s+\S+\s+\S+)", rest)
                if m:
                    entry_end += len(m.group(1))
                parts.append(html.Span(
                    line[idx:entry_end],
                    style={"backgroundColor": _DISC_BG,
                           "borderRadius": "2px"}))
                pos = entry_end
            children.append(html.Div(children=parts))
        else:
            children.append(html.Div(line))

    content_div = html.Div(
        children=children,
        style={
            "padding": "10px", "fontSize": "13px", "lineHeight": "1.5",
            "overflowX": "auto", "maxHeight": "400px", "overflowY": "auto",
            "fontFamily": "monospace", "whiteSpace": "pre",
        },
    )
    props = {
        "open": open_default,
        "style": {"marginBottom": "12px",
                  "border": "1px solid var(--hr-color, #ccc)",
                  "borderRadius": "6px"},
        "children": [
            html.Summary(
                "Residuals",
                style={"padding": "10px 14px", "cursor": "pointer",
                       "fontFamily": "sans-serif", "fontWeight": "600",
                       "fontSize": "14px",
                       "backgroundColor": "var(--paper-bg, white)",
                       "borderRadius": "6px"},
            ),
            content_div,
        ],
    }
    if section_id is not None:
        props["id"] = section_id
    return html.Details(**props)


def _mpec_section(title, content, open_default=False, mono=True,
                   section_id=None, max_height="400px"):
    """Build a collapsible section using html.Details/Summary."""
    content_style = {
        "padding": "10px",
        "fontSize": "13px",
        "lineHeight": "1.5",
        "overflowX": "auto",
    }
    if max_height:
        content_style["maxHeight"] = max_height
        content_style["overflowY"] = "auto"
    if mono:
        content_style["fontFamily"] = "monospace"
        content_style["whiteSpace"] = "pre"
    else:
        content_style["fontFamily"] = "sans-serif"
        content_style["whiteSpace"] = "pre-wrap"

    props = {
        "open": open_default,
        "style": {"marginBottom": "12px",
                  "border": "1px solid var(--hr-color, #ccc)",
                  "borderRadius": "6px"},
        "children": [
            html.Summary(
                title,
                style={"padding": "10px 14px", "cursor": "pointer",
                       "fontFamily": "sans-serif", "fontWeight": "600",
                       "fontSize": "14px",
                       "backgroundColor": "var(--paper-bg, white)",
                       "borderRadius": "6px"},
            ),
            html.Div(content, style=content_style),
        ],
    }
    if section_id is not None:
        props["id"] = section_id

    return html.Details(**props)


def _prefetch_mpec_details(entries):
    """Background-fetch all MPEC details so disk cache populates."""
    for entry in entries:
        path = entry.get("path", "")
        if not path:
            continue
        safe_name = path.replace("/", "_").strip("_") + ".txt"
        cache_path = os.path.join(_MPEC_CACHE_DIR, safe_name)
        if os.path.exists(cache_path):
            continue
        try:
            fetch_mpec_detail(path, cache_dir=_MPEC_CACHE_DIR)
        except Exception as e:
            print(f"Prefetch error for {path}: {e}")


@app.callback(
    Output("mpec-list-panel", "children"),
    Output("mpec-selected-path", "data"),
    Output("mpec-item-paths", "data"),
    Input("mpec-refresh", "n_intervals"),
    Input("tabs", "value"),
    Input("mpec-restore-list", "data"),
    State("mpec-auto-mode", "data"),
    State("mpec-selected-path", "data"),
)
def refresh_mpec_list(_n, active_tab, _restore, auto_mode, current_path):
    if active_tab != "tab-mpec":
        return no_update, no_update, no_update
    entries = fetch_recent_mpecs()
    if not entries:
        return ([html.Div("No MPECs available.",
                          style={"fontFamily": "sans-serif", "fontSize": "14px",
                                 "color": "var(--subtext-color, #888)"})],
                no_update, [])
    # Pre-fetch all MPECs in background so annotations appear on next render
    threading.Thread(target=_prefetch_mpec_details, args=(entries,),
                     daemon=True).start()
    items = [_build_mpec_list_item(e, i) for i, e in enumerate(entries)]
    paths = [e.get("path", "") for e in entries]

    # Auto-select: pick the latest MPEC (first in list)
    if auto_mode:
        return items, entries[0]["path"], paths

    return items, no_update, paths


@app.callback(
    Output("mpec-selected-path", "data", allow_duplicate=True),
    Output("mpec-auto-mode", "data"),
    Output("mpec-restore-list", "data", allow_duplicate=True),
    Input({"type": "mpec-item", "index": dash.ALL}, "n_clicks"),
    Input("mpec-follow-btn", "n_clicks"),
    State("mpec-item-paths", "data"),
    State("mpec-restore-list", "data"),
    prevent_initial_call=True,
)
def select_mpec(item_clicks, follow_clicks, item_paths, restore_count):
    triggered = ctx.triggered_id

    # "Follow latest" button re-enables auto mode and restores list
    if triggered == "mpec-follow-btn":
        entries = fetch_recent_mpecs()
        if entries:
            return entries[0]["path"], True, (restore_count or 0) + 1
        raise PreventUpdate

    # User clicked an MPEC item — disable auto mode
    if isinstance(triggered, dict) and triggered.get("type") == "mpec-item":
        if not any(item_clicks):
            raise PreventUpdate
        idx = triggered["index"]
        if item_paths and idx < len(item_paths):
            return item_paths[idx], False, no_update

    raise PreventUpdate


@app.callback(
    Output("mpec-selected-path", "data", allow_duplicate=True),
    Output("mpec-auto-mode", "data", allow_duplicate=True),
    Input("mpec-kb-nav", "value"),
    prevent_initial_call=True,
)
def keyboard_navigate(value):
    """Handle keyboard navigation from keyboard.js."""
    if not value:
        raise PreventUpdate
    # JS appends "|<timestamp>" to force uniqueness — strip it
    path = value.rsplit("|", 1)[0] if "|" in value else value
    if not path:
        raise PreventUpdate
    if path == "PIN":
        # F key toggle: switch from Following to Pinned (no path change)
        return no_update, False
    return path, False


@app.callback(
    Output("mpec-selected-path", "data", allow_duplicate=True),
    Output("mpec-auto-mode", "data", allow_duplicate=True),
    Output("mpec-list-panel", "children", allow_duplicate=True),
    Output("mpec-item-paths", "data", allow_duplicate=True),
    Input("mpec-desig-search", "value"),
    prevent_initial_call=True,
)
def search_designation(value):
    """Resolve a designation to its MPEC(s) via the MPC API."""
    if not value:
        raise PreventUpdate
    query = value.rsplit("|", 1)[0] if "|" in value else value
    query = query.strip()
    if not query:
        raise PreventUpdate

    results = lookup_mpecs_by_designation(query)
    if not results:
        raise PreventUpdate

    if len(results) == 1:
        return results[0]["path"], False, no_update, no_update

    # Multiple results — build a list panel showing all MPECs
    header = html.Div(
        f"{len(results)} MPECs for {results[0].get('title') or query}",
        style={"fontSize": "13px", "fontWeight": "700",
               "fontFamily": "sans-serif", "padding": "8px 12px 4px",
               "color": "var(--subtext-color, #888)"},
    )
    items = []
    for i, r in enumerate(results):
        items.append(html.Div(
            id={"type": "mpec-item", "index": i},
            n_clicks=0,
            style=_MPEC_ITEM_SELECTED if i == 0 else _MPEC_ITEM_STYLE,
            children=[
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between",
                           "alignItems": "center"},
                    children=[
                        html.Span([
                            html.Span(r.get("title", ""),
                                      style={"fontSize": "14px",
                                             "fontWeight": "600"}),
                            html.Span(
                                f" ({r.get('mpec_id', '')})",
                                style={"fontSize": "12px", "fontWeight": "400",
                                       "color": "var(--subtext-color, #888)"}),
                        ]),
                    ],
                ),
                html.Div(
                    r.get("date", ""),
                    style={"fontSize": "12px",
                           "color": "var(--subtext-color, #888)",
                           "marginTop": "2px"},
                ),
            ],
            **{"data-path": r.get("path", "")},
        ))

    paths = [r.get("path", "") for r in results]
    return results[0]["path"], False, [header] + items, paths


@app.callback(
    Output({"type": "mpec-item", "index": dash.ALL}, "style"),
    Input("mpec-selected-path", "data"),
    State("mpec-item-paths", "data"),
    prevent_initial_call=True,
)
def highlight_selected_mpec(selected_path, item_paths):
    """Highlight the selected MPEC in the list."""
    if not item_paths:
        raise PreventUpdate
    styles = []
    for path in item_paths:
        if path == selected_path:
            styles.append(_MPEC_ITEM_SELECTED)
        else:
            styles.append(_MPEC_ITEM_STYLE)
    return styles


@app.callback(
    Output("mpec-auto-label", "children"),
    Output("mpec-auto-label", "style"),
    Output("mpec-follow-btn", "style"),
    Input("mpec-auto-mode", "data"),
)
def update_auto_indicator(auto_mode):
    if auto_mode:
        return (
            "\u25CF Following latest",
            {"color": "#2e7d32", "fontWeight": "600"},
            {"fontSize": "11px", "padding": "2px 10px", "display": "none"},
        )
    return (
        "\u25CB Pinned",
        {"color": "var(--subtext-color, #888)"},
        {"fontSize": "11px", "padding": "2px 10px", "display": "inline-block"},
    )


@app.callback(
    Output("mpec-detail-summary", "children"),
    Output("mpec-detail-panel", "children"),
    Output("mpec-enrich-poll", "disabled"),
    Output("mpec-enrich-poll", "n_intervals"),
    Output("mpec-enrich-data", "data"),
    Input("mpec-selected-path", "data"),
    State("mpec-section-state", "data"),
)
def show_mpec_detail(path, section_state):
    if not path:
        placeholder = html.Div("Select an MPEC from the list.",
                               style={"fontFamily": "sans-serif", "fontSize": "14px",
                                      "color": "var(--subtext-color, #888)",
                                      "paddingTop": "20px"})
        return placeholder, html.Div(), True, 0, None
    detail = fetch_mpec_detail(path, cache_dir=_MPEC_CACHE_DIR)
    if not detail:
        err = html.Div("Could not load MPEC.",
                        style={"fontFamily": "sans-serif",
                               "color": "var(--subtext-color, #888)",
                               "paddingTop": "20px"})
        return err, html.Div(), True, 0, None
    # Pass whether this MPEC is in the recent list
    recent = fetch_recent_mpecs()
    recent_paths = {e.get("path") for e in recent}
    in_recent = path in recent_paths
    summary, sections = _build_mpec_detail(detail, section_state,
                                           in_recent=in_recent)
    # Skip enrichment polling for DOUs/editorials (no object to query)
    mpec_type = detail.get("type", "discovery")
    enable_enrich = mpec_type in ("discovery", "recovery")
    return summary, sections, not enable_enrich, 0, None


@app.callback(
    Output("mpec-section-state", "data"),
    Input("mpec-section-state-input", "value"),
    State("mpec-section-state", "data"),
    prevent_initial_call=True,
)
def sync_section_state(json_val, current_state):
    """Sync section open/closed state from JS toggle events."""
    if not json_val:
        raise PreventUpdate
    import json
    # JS appends "|<timestamp>" to force uniqueness — strip it
    raw = json_val.rsplit("|", 1)[0] if "|" in json_val else json_val
    try:
        new_state = json.loads(raw)
        if isinstance(new_state, dict):
            return new_state
    except (json.JSONDecodeError, TypeError):
        pass
    raise PreventUpdate


# ---------------------------------------------------------------------------
# Observation timeline
# ---------------------------------------------------------------------------

def _build_obs_timeline(ades_data, designation, chart_height=250):
    """Build observation history timeline from ADES data.

    Returns html.Details wrapping a Plotly figure + stats line.

    Marker shapes:
        star     — discovery tracklet
        diamond  — tracklet published in an MPEC
        circle   — tracklet published in another document (MPS, etc.)
        circle-open — tracklet with no resolved publication link
    """
    import re as _re
    tracklets = ades_data.get("tracklets", [])

    if not tracklets:
        return html.Details(
            open=False,
            style={"marginBottom": "12px",
                   "border": "1px solid var(--hr-color, #ccc)",
                   "borderRadius": "6px"},
            children=[
                html.Summary(
                    f"Observation history — {designation}",
                    style={"padding": "10px 14px", "cursor": "pointer",
                           "fontFamily": "sans-serif", "fontWeight": "600",
                           "fontSize": "14px",
                           "backgroundColor": "var(--paper-bg, white)",
                           "borderRadius": "6px"},
                ),
                html.Div("No observation data available.",
                         style={"padding": "10px", "fontFamily": "sans-serif",
                                "fontSize": "12px",
                                "color": "var(--subtext-color, #888)"}),
            ],
        )

    # Pre-resolve all unique refs to URLs in one pass
    all_refs = set()
    for t in tracklets:
        all_refs.update(t["refs"])
    ref_url_cache = {}
    for ref in all_refs:
        m = _re.match(r"MPEC (\d{4}-\w+)", ref)
        if m:
            ref_url_cache[ref] = mpec_id_to_url(m.group(1))
            continue
        m = _re.match(r"MPS\s+(\d+)", ref)
        if m:
            ref_url_cache[ref] = resolve_mps_url(m.group(1))
            continue
        ref_url_cache[ref] = ""

    def _ref_url(ref):
        return ref_url_cache.get(ref, "")

    def _is_mpec_ref(ref):
        return bool(_re.match(r"MPEC \d{4}-\w+", ref))

    # Ensure chart is tall enough for all project lines
    n_projects = len({t["project"] for t in tracklets})
    min_height = max(n_projects * 28 + 80, 180)
    chart_height = max(chart_height, min_height)

    fig = go.Figure()
    fig.update_layout(
        height=chart_height,
        margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=11, color="#aaa"),
        xaxis=dict(
            type="date",
            gridcolor="rgba(128,128,128,0.15)",
            zeroline=False,
            rangeslider=dict(visible=True, thickness=0.08),
        ),
        yaxis=dict(
            type="category",
            gridcolor="rgba(128,128,128,0.15)",
            zeroline=False,
            autorange="reversed",
            fixedrange=True,
        ),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=10),
            itemdoubleclick=False,
        ),
        hovermode="closest",
    )

    # Build traces by project, separating discovery tracklets
    by_project = {}
    for t in tracklets:
        by_project.setdefault(t["project"], []).append(t)

    for proj, trk_list in by_project.items():
        regular = [t for t in trk_list if not t["is_discovery"]]
        disc = [t for t in trk_list if t["is_discovery"]]
        color = PROJECT_COLORS.get(proj, "#d4bc9a")

        for subset, is_disc in [(regular, False), (disc, True)]:
            if not subset:
                continue
            times = [t["first_obs"] for t in subset]
            projects = [proj] * len(subset)
            hovers = []
            urls = []
            for t in subset:
                parts = [f"{t['stn']} · {t['first_obs'][:10]}",
                         f"{t['n_obs']} obs"]
                if t["mag_median"] is not None:
                    parts.append(f"mag {t['mag_median']} {t['band']}")
                if t["refs"]:
                    parts.append("<br>".join(sorted(t["refs"])))
                hovers.append("<br>".join(parts))
                # Link to first MPEC ref, else first MPS ref
                mpec_refs = [r for r in t["refs"]
                             if _is_mpec_ref(r)]
                mps_refs = [r for r in t["refs"]
                            if _re.match(r"MPS\s", r)]
                url = ""
                if mpec_refs:
                    url = _ref_url(sorted(mpec_refs)[0])
                elif mps_refs:
                    url = _ref_url(sorted(mps_refs)[0])
                urls.append(url)

            # Symbols: star=discovery, diamond=MPEC, circle=other pub,
            # circle-open=no link
            if is_disc:
                symbols = "star"
            else:
                symbols = ["diamond" if any(_is_mpec_ref(r)
                            for r in t["refs"]) else "circle"
                           for t in subset]

            fig.add_trace(go.Scattergl(
                x=times, y=projects,
                mode="markers",
                marker=dict(
                    size=12 if is_disc else 9,
                    symbol=symbols,
                    color=color,
                    opacity=0.85,
                    line=dict(width=1, color="white") if is_disc else {},
                ),
                name=proj,
                text=hovers,
                hoverinfo="text",
                customdata=urls,
                legendgroup=proj,
                showlegend=(not is_disc),
            ))

    # Discovery vertical dashed line
    disc_tracklets = [t for t in tracklets if t["is_discovery"]]
    if disc_tracklets:
        disc_time = disc_tracklets[0]["first_obs"]
        fig.add_vline(
            x=disc_time, line_dash="dash",
            line_color="rgba(128,128,128,0.5)", line_width=1,
        )

    # Deduplicate legend entries (multiple traces per project)
    seen_legend = set()
    for trace in fig.data:
        lg = trace.legendgroup
        if lg in seen_legend:
            trace.showlegend = False
        else:
            seen_legend.add(lg)

    # Stats line
    n_tracklets = len(tracklets)
    stations = {t["stn"] for t in tracklets}
    first_date = tracklets[0]["first_obs"][:10] if tracklets else ""
    last_date = tracklets[-1]["first_obs"][:10] if tracklets else ""
    disc_t = [t for t in tracklets if t["is_discovery"]]
    disc_info = ""
    if disc_t:
        d = disc_t[0]
        disc_info = f" · disc: {d['first_obs'][:10]} ({d['stn']})"

    stats_text = (f"{n_tracklets} tracklets · {len(stations)} stations · "
                  f"{first_date} – {last_date}{disc_info}")

    stats_line = html.Div(
        style={"display": "flex", "justifyContent": "space-between",
               "fontFamily": "sans-serif", "fontSize": "11px",
               "color": "var(--subtext-color, #888)", "padding": "0 10px 6px"},
        children=[
            html.Span(stats_text),
            html.Span("powered by NEOfixer",
                       style={"fontStyle": "italic"}),
        ],
    )

    return html.Details(
        open=True,
        style={"marginBottom": "12px",
               "border": "1px solid var(--hr-color, #ccc)",
               "borderRadius": "6px"},
        children=[
            html.Summary(
                f"Observation history — {designation}",
                style={"padding": "10px 14px", "cursor": "pointer",
                       "fontFamily": "sans-serif", "fontWeight": "600",
                       "fontSize": "14px",
                       "backgroundColor": "var(--paper-bg, white)",
                       "borderRadius": "6px"},
            ),
            dcc.Graph(id="obs-timeline-graph", figure=fig,
                      config={"displayModeBar": "hover",
                              "modeBarButtonsToRemove": [
                                  "lasso2d", "select2d",
                                  "autoScale2d"],
                              "toImageButtonOptions": {
                                  "format": "png", "scale": 2},
                              "displaylogo": False,
                              "scrollZoom": True,
                              "doubleClick": "reset"},
                      style={"padding": "0 4px"}),
            stats_line,
        ],
    )


# Clientside callback: click a tracklet marker to open its MPC ref URL
app.clientside_callback(
    """
    function(clickData) {
        if (clickData && clickData.points && clickData.points.length) {
            var url = clickData.points[0].customdata;
            if (url) { window.open(url, "mpc_pub"); }
        }
        return null;
    }
    """,
    Output("obs-timeline-click-sink", "data"),
    Input("obs-timeline-graph", "clickData"),
    prevent_initial_call=True,
)


@app.callback(
    Output("mpec-obs-timeline", "children"),
    Input("mpec-selected-path", "data"),
    Input("plot-height", "value"),
)
def update_obs_timeline(path, plot_height):
    """Fetch ADES data and render observation timeline."""
    if not path:
        return html.Div()

    detail = fetch_mpec_detail(path, cache_dir=_MPEC_CACHE_DIR)
    if not detail:
        return html.Div()

    mpec_type = detail.get("type", "discovery")
    if mpec_type not in ("discovery", "recovery"):
        return html.Div()

    designation = detail.get("designation", "")
    if not designation:
        return html.Div()

    # Handle identification MPECs — extract subject from obs80
    if " = " in designation:
        obs_text = detail.get("observations", "")
        if obs_text:
            packed_obs = obs_text.strip().split("\n")[0][:12].strip()
            if packed_obs:
                try:
                    designation = unpack_designation(packed_obs)
                except Exception:
                    pass

    # Resolve to current identity (permanent number if available)
    # — mirrors the download-button logic in _build_mpec_detail
    link_desig = designation
    try:
        resolved = resolve_designation(designation)
        if resolved and resolved["permid"]:
            link_desig = resolved["permid"]
        elif resolved and resolved["is_secondary"] and resolved["primary_desig"]:
            link_desig = resolved["primary_desig"]
    except Exception:
        pass

    try:
        packed = pack_designation(link_desig).strip()
    except Exception:
        packed = ""
    if not packed:
        try:
            packed = pack_designation(designation).strip()
        except Exception:
            return html.Div()
    if not packed:
        return html.Div()

    ades_data = fetch_neofixer_ades(packed, STATION_TO_PROJECT)
    if not ades_data:
        # Non-NEO or fetch failed — collapsed section
        return html.Details(
            open=False,
            style={"marginBottom": "12px",
                   "border": "1px solid var(--hr-color, #ccc)",
                   "borderRadius": "6px"},
            children=[
                html.Summary(
                    f"Observation history — {designation}",
                    style={"padding": "10px 14px", "cursor": "pointer",
                           "fontFamily": "sans-serif", "fontWeight": "600",
                           "fontSize": "14px",
                           "backgroundColor": "var(--paper-bg, white)",
                           "borderRadius": "6px"},
                ),
                html.Div("Not available (NEOs only, via NEOfixer).",
                         style={"padding": "10px", "fontFamily": "sans-serif",
                                "fontSize": "12px",
                                "color": "var(--subtext-color, #888)"}),
            ],
        )

    chart_h = max(int(plot_height) // 2, 220) if plot_height else 250

    return _build_obs_timeline(
        ades_data, designation, chart_height=chart_h,
    )


# ---------------------------------------------------------------------------
# Observability chart callback
# ---------------------------------------------------------------------------

def _obs_details_wrapper(site, designation, content, open_default=True):
    """Wrap observability content in a Details/Summary accordion."""
    return html.Details(
        open=open_default,
        style={"marginBottom": "12px",
               "border": "1px solid var(--hr-color, #ccc)",
               "borderRadius": "6px"},
        children=[
            html.Summary(
                f"Current observability \u2014 {site} ({designation})",
                style={"padding": "10px 14px", "cursor": "pointer",
                       "fontFamily": "sans-serif", "fontWeight": "600",
                       "fontSize": "14px",
                       "backgroundColor": "var(--paper-bg, white)",
                       "borderRadius": "6px"},
            ),
            content,
        ],
    )


@app.callback(
    Output("mpec-obs-chart", "children"),
    Input("mpec-selected-path", "data"),
    Input("obs-site-selected", "data"),
    Input("plot-height", "value"),
)
def update_obs_chart(path, site, plot_height):
    if not path:
        return html.Div()

    site = site or _OBS_SITES_DEFAULT
    chart_h = max(int(plot_height) // 2, 250) if plot_height else 350

    detail = fetch_mpec_detail(path, cache_dir=_MPEC_CACHE_DIR)
    if not detail:
        return html.Div()

    designation = detail.get("designation", "")
    packed = ""
    if designation:
        try:
            packed = pack_designation(designation).strip()
        except Exception:
            packed = ""
    if not packed:
        return html.Div()

    try:
        chart_content = _build_observability_section(
            packed, designation, site=site, chart_height=chart_h)
    except Exception as e:
        print(f"Observability chart error: {e}")
        chart_content = None

    if chart_content:
        return _obs_details_wrapper(site, designation, chart_content)

    # No data — collapsed; still show site buttons so user can try a different site
    return _obs_details_wrapper(site, designation, html.Div(children=[
        _obs_site_buttons(site),
        html.Div("No ephemeris available from NEOfixer for this object or site.",
                 style={"fontFamily": "sans-serif", "fontSize": "12px",
                        "color": "var(--subtext-color, #888)",
                        "padding": "10px"}),
    ]), open_default=False)


# ---------------------------------------------------------------------------
# Enrichment callback — fetches SBDB, Sentry, NEOfixer, NEOCC
# ---------------------------------------------------------------------------

def _build_risk_line(sentry, neocc_risk, designation=""):
    """Build compact Sentry/NEOCC risk status for MPEC detail header."""
    import urllib.parse
    parts = []
    _ss = {"fontFamily": "sans-serif", "fontSize": "13px"}
    _dim = {"color": "var(--subtext-color, #888)"}
    _link = {"color": "inherit", "textDecoration": "underline",
             "textUnderlineOffset": "2px"}

    encoded = urllib.parse.quote(designation) if designation else ""

    # Sentry status
    if sentry is not None:
        if sentry.get("on_list"):
            ip_raw = sentry.get("ip", "?")
            try:
                ip_val = float(ip_raw)
                ip = f"{ip_val:.2e}" if ip_val < 0.01 else f"{ip_val:.4f}"
            except (ValueError, TypeError):
                ip = str(ip_raw)
            ts_max = sentry.get("ts_max", "0")
            ps_cum = sentry.get("ps_cum", "")
            risk_color = "#c62828" if str(ts_max) != "0" else "#f57f17"
            sentry_url = (f"https://cneos.jpl.nasa.gov/sentry/details.html"
                          f"#?des={encoded}")
            parts.append(html.Span(children=[
                html.Span("Sentry: ", style={**_ss, "fontWeight": "600",
                           "color": risk_color}),
                html.A(f"Torino {ts_max}, IP={ip}, Palermo={ps_cum}",
                       href=sentry_url, target="_blank",
                       className="color-explicit",
                       style={**_ss, **_link,
                              "--explicit-color": risk_color,
                              "fontWeight": "600"}),
            ]))
        # If not on list, say nothing (normal case)
    else:
        parts.append(html.Span(
            "Sentry: checking\u2026",
            className="color-explicit",
            style={**_ss, "--explicit-color": "var(--subtext-color, #888)"}))

    # NEOCC status
    if neocc_risk:
        lines = [l for l in neocc_risk.strip().split("\n") if l.strip()]
        if lines:
            desig_nospace = designation.replace(" ", "")
            neocc_url = (f"https://neo.ssa.esa.int/"
                         f"search-for-asteroids?tab=closeapp&des={desig_nospace}")
            parts.append(html.Span(children=[
                html.Span("NEOCC: ", style={**_ss, "fontWeight": "600",
                           "color": "#f57f17"}),
                html.A(f"listed ({len(lines)} VI)",
                       href=neocc_url, target="_blank",
                       className="color-explicit",
                       style={**_ss, **_link,
                              "--explicit-color": "#f57f17",
                              "fontWeight": "600"}),
            ]))
    # If not listed, say nothing (normal case)

    if not parts:
        return html.Div()

    interleaved = []
    for i, sp in enumerate(parts):
        if i > 0:
            interleaved.append(html.Span(
                " \u00b7 ", style={**_ss, **_dim}))
        interleaved.append(sp)

    return html.Div(
        children=interleaved,
        style={"marginTop": "2px", "marginBottom": "2px"},
    )



@app.callback(
    Output("mpec-risk-line", "children", allow_duplicate=True),
    Output("mpec-enrich-poll", "disabled", allow_duplicate=True),
    Output("mpec-enrich-data", "data", allow_duplicate=True),
    Input("mpec-enrich-poll", "n_intervals"),
    Input("mpec-selected-path", "data"),
    State("mpec-enrich-data", "data"),
    prevent_initial_call="initial_duplicate",
)
def enrich_mpec_detail(n_intervals, path, prev_data):
    """Poll external APIs for per-object risk info."""
    if not path:
        return html.Div(), True, None

    # Get the detail so we have the designation
    detail = fetch_mpec_detail(path, cache_dir=_MPEC_CACHE_DIR)
    if not detail:
        return html.Div(), True, None

    # Skip enrichment for DOUs/editorials — no object to query
    if detail.get("type") not in ("discovery", "recovery"):
        return html.Div(), True, None

    designation = detail.get("designation", "")
    packed = ""
    if designation:
        try:
            packed = pack_designation(designation).strip()
        except Exception:
            packed = ""

    # Fetch from APIs (cached with 5-min TTL)
    sbdb = fetch_sbdb(designation) if designation else None
    sentry = fetch_sentry(designation) if designation else None
    neofixer = fetch_neofixer_orbit(packed) if packed else None
    neocc_risk = fetch_neocc_risk(designation) if designation else None

    # Track which sources responded (to decide whether to keep polling)
    sources_pending = 0
    if designation and sbdb is None:
        sources_pending += 1
    if packed and neofixer is None:
        sources_pending += 1
    if designation and sentry is None:
        sources_pending += 1

    # Build Sentry/NEOCC risk line for MPEC header
    risk_line = _build_risk_line(sentry, neocc_risk, designation)

    # Stop polling if all sources responded or max intervals reached
    stop_poll = (sources_pending == 0) or (n_intervals >= 10)

    enrichment_state = {
        "sbdb_ok": sbdb is not None,
        "sentry_ok": sentry is not None,
        "neofixer_ok": neofixer is not None,
        "neocc_ok": neocc_risk is not None,
    }

    return risk_line, stop_poll, enrichment_state


# ---------------------------------------------------------------------------
# Download CSV callbacks
# ---------------------------------------------------------------------------

# Columns to export for the discovery dataset (excludes internal indices)
_DISCOVERY_EXPORT_COLS = [
    "designation", "disc_year", "disc_month", "station_code", "station_name",
    "project", "h", "h_nea", "h_mpc", "size_class",
    "orbit_type_int", "q", "e", "i",
    "avg_ra_deg", "avg_dec_deg", "median_v_mag", "tracklet_nobs",
    "rate_deg_per_day", "position_angle_deg", "solar_elong_deg",
]


@app.callback(
    Output("download-discovery", "data"),
    Input("btn-download-discovery", "n_clicks"),
    State("year-range", "value"),
    State("size-filter", "value"),
    prevent_initial_call=True,
)
def download_discovery(n_clicks, year_range, size_filter):
    if not n_clicks or df is None:
        raise PreventUpdate
    y0, y1 = year_range
    filtered = df[(df["disc_year"] >= y0) & (df["disc_year"] <= y1)]
    if size_filter not in ("all", "split"):
        filtered = filtered[filtered["size_class"] == size_filter]
    cols = [c for c in _DISCOVERY_EXPORT_COLS if c in filtered.columns]
    return send_data_frame(
        filtered[cols].to_csv, "neo_discoveries.csv", index=False)


@app.callback(
    Output("download-neomod", "data"),
    Input("btn-download-neomod", "n_clicks"),
    State("h-year-range", "value"),
    State("h-range", "value"),
    prevent_initial_call=True,
)
def download_neomod(n_clicks, h_year_range, h_range):
    if not n_clicks or df is None:
        raise PreventUpdate
    hy0, hy1 = h_year_range
    h_lo = round(h_range[0] * 4) / 4
    h_hi = round(h_range[1] * 4) / 4
    filtered = df[(df["disc_year"] >= hy0) & (df["disc_year"] <= hy1)]
    valid = filtered[
        (filtered["h_bin_idx"] >= 0)
        & (filtered["h_bin_idx"] < len(H_BIN_CENTERS))
    ].copy()
    valid["h_bin_center"] = H_BIN_CENTERS[valid["h_bin_idx"]]
    valid = valid[
        (valid["h_bin_center"] >= h_lo) & (valid["h_bin_center"] <= h_hi)]
    # Build per-bin summary with NEOMOD3 comparison
    bin_counts = valid.groupby("h_bin_idx").size()
    rows = []
    for idx in range(len(H_BIN_CENTERS)):
        center = H_BIN_CENTERS[idx]
        if center < h_lo or center > h_hi:
            continue
        discovered = int(bin_counts.get(idx, 0))
        neomod_row = NEOMOD3_DF[
            (NEOMOD3_DF["h_center"] - center).abs() < 0.01]
        if len(neomod_row):
            nr = neomod_row.iloc[0]
            rows.append({
                "h_bin": f"{nr['h1']:.2f}-{nr['h2']:.2f}",
                "h_center": center,
                "discovered": discovered,
                "neomod3_estimated": int(nr["dn_model"]),
                "neomod3_cumulative": int(nr["n_cumul"]),
                "neomod3_min": int(nr["n_min"]),
                "neomod3_max": int(nr["n_max"]),
                "completeness_pct": round(
                    discovered / nr["dn_model"] * 100, 1)
                if nr["dn_model"] > 0 else None,
            })
    out = pd.DataFrame(rows)
    return send_data_frame(
        out.to_csv, "neo_size_distribution_vs_neomod3.csv", index=False)


@app.callback(
    Output("download-comparison", "data"),
    Input("btn-download-comparison", "n_clicks"),
    State("comp-year-range", "value"),
    State("comp-size-filter", "value"),
    State("comp-precovery", "value"),
    prevent_initial_call=True,
)
def download_comparison(n_clicks, year_range, size_filter, precovery):
    if not n_clicks or df is None or df_apparition is None:
        raise PreventUpdate
    exclude_precovery = precovery == "post_only"
    survey_sets, eligible = build_survey_sets(
        df, df_apparition, year_range, size_filter, exclude_precovery)
    # Build per-survey summary
    rows = []
    for proj in PROJECT_ORDER:
        s = survey_sets.get(proj, set())
        if s:
            rows.append({
                "survey": proj,
                "neos_observed": len(s),
                "fraction_of_eligible": round(
                    len(s) / len(eligible) * 100, 1)
                if eligible else 0,
            })
    out = pd.DataFrame(rows)
    out.loc[len(out)] = {
        "survey": "TOTAL eligible",
        "neos_observed": len(eligible),
        "fraction_of_eligible": 100.0,
    }
    return send_data_frame(
        out.to_csv, "neo_survey_comparison.csv", index=False)


@app.callback(
    Output("download-followup", "data"),
    Input("btn-download-followup", "n_clicks"),
    State("fu-year-range", "value"),
    State("fu-size-filter", "value"),
    prevent_initial_call=True,
)
def download_followup(n_clicks, year_range, size_filter):
    if not n_clicks or df is None or df_apparition is None:
        raise PreventUpdate
    fu_data, total = build_followup_data(
        df, df_apparition, year_range, size_filter)
    if len(fu_data) == 0:
        raise PreventUpdate
    return send_data_frame(
        fu_data.to_csv, "neo_followup_timing.csv", index=False)


@app.callback(
    Output("download-circumstances", "data"),
    Input("btn-download-circumstances", "n_clicks"),
    State("circ-year-range", "value"),
    State("circ-size-filter", "value"),
    prevent_initial_call=True,
)
def download_circumstances(n_clicks, year_range, size_filter):
    if not n_clicks or df is None:
        raise PreventUpdate
    y0, y1 = year_range
    filtered = df[(df["disc_year"] >= y0) & (df["disc_year"] <= y1)]
    if size_filter != "all":
        filtered = filtered[filtered["size_class"] == size_filter]
    cols = [c for c in _DISCOVERY_EXPORT_COLS if c in filtered.columns]
    return send_data_frame(
        filtered[cols].to_csv, "neo_discovery_circumstances.csv", index=False)


# ---------------------------------------------------------------------------
# Enforce max 3 surveys for Venn
# ---------------------------------------------------------------------------

@app.callback(
    Output("comp-survey-select", "value"),
    Input("comp-survey-select", "value"),
    prevent_initial_call=True,
)
def cap_survey_selection(value):
    if value and len(value) > 3:
        return value[:3]
    raise PreventUpdate


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\nStarting Dash server at http://{_HOST}:8050/")
    print("Data loading in background..." if not _data_ready.is_set()
          else "Data ready.")
    app.run(host=_HOST, debug=_DEBUG, use_reloader=False)
