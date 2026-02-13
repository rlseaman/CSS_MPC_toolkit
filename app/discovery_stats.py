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
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
from plotly.subplots import make_subplots

from lib.db import connect, timed_query

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
    "F51": "Pan-STARRS 1",
    "F52": "Pan-STARRS 2",
    "T05": "ATLAS-HKO",
    "T08": "ATLAS-MLO",
    "T03": "ATLAS-Sutherland",
    "M22": "ATLAS-El Sauce",
    "W68": "ATLAS-Río Hurtado",
    "704": "LINEAR",
    "699": "LONEOS",
    "691": "Spacewatch",
    "291": "Spacewatch II",
    "644": "NEAT-Palomar",
    "608": "NEAT-Haleakala",
    "I41": "ZTF",
    "I52": "ZTF",
    "C51": "WISE/NEOWISE",
    "C57": "WISE/NEOWISE",
}

# Station code -> project (for grouped view)
# Groupings match CNEOS site_all.json definitions
STATION_TO_PROJECT = {
    "704": "LINEAR", "G45": "LINEAR", "P07": "LINEAR",
    "566": "NEAT", "608": "NEAT", "644": "NEAT",
    "691": "Spacewatch", "291": "Spacewatch",
    "699": "LONEOS",
    "703": "Catalina", "E12": "Catalina", "G96": "Catalina",
    "I52": "Catalina", "V06": "Catalina",
    "F51": "Pan-STARRS", "F52": "Pan-STARRS",
    "C51": "NEOWISE", "C57": "NEOWISE",
    "T05": "ATLAS", "T07": "ATLAS", "T08": "ATLAS",
    "T03": "ATLAS", "M22": "ATLAS", "W68": "ATLAS",
    "I41": "Other-US", "U68": "Other-US", "V00": "Other-US", "W84": "Other-US",
}

# Stacking order matches CNEOS (bottom to top in the bar chart).
# Plotly stacks traces in list order, so first entry = bottom of stack.
PROJECT_ORDER = [
    "LINEAR",
    "NEAT",
    "Spacewatch",
    "LONEOS",
    "Catalina",
    "Pan-STARRS",
    "NEOWISE",
    "ATLAS",
    "Other-US",
    "Others",
]

# Colors match CNEOS site_all.json exactly
PROJECT_COLORS = {
    "LINEAR": "#4363d8",
    "NEAT": "#f58231",
    "Spacewatch": "#e6194B",
    "LONEOS": "#ffe119",
    "Catalina": "#3cb44b",
    "Pan-STARRS": "#f032e6",
    "NEOWISE": "#469990",
    "ATLAS": "#42d4f4",
    "Other-US": "#9A6324",
    "Others": "#a9a9a9",
}

# H magnitude size classes
H_BINS = [
    ("H < 18 (~1 km+)", None, 18),
    ("18 \u2264 H < 22 (~140 m\u20131 km)", 18, 22),
    ("22 \u2264 H < 25 (~30\u2013140 m)", 22, 25),
    ("25 \u2264 H < 28 (~10\u201330 m)", 25, 28),
    ("H \u2265 28 (< 10 m)", 28, None),
]

# Colors for size-class stacking (viridis palette, matching size histogram)
SIZE_COLORS = ["#440154", "#31688e", "#35b779", "#90d743", "#fde725"]

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
)
SELECT
    di.unpacked_desig AS designation,
    EXTRACT(YEAR FROM di.obstime)::int AS disc_year,
    EXTRACT(MONTH FROM di.obstime)::int AS disc_month,
    di.stn AS station_code,
    neo.h,
    neo.orbit_type_int,
    neo.q, neo.e, neo.i
FROM discovery_info di
JOIN neo_list neo ON neo.unpacked_desig = di.unpacked_desig
ORDER BY di.obstime
"""


CACHE_MAX_AGE_SEC = 86400  # 1 day

# Cache filename embeds a short hash of the SQL so it auto-invalidates
# when the query changes.
_SQL_HASH = hashlib.md5(LOAD_SQL.encode()).hexdigest()[:8]
CACHE_FILE = os.path.join(_APP_DIR, f".neo_cache_{_SQL_HASH}.csv")
CACHE_META = CACHE_FILE.replace(".csv", ".meta")  # stores query timestamp


def _read_query_timestamp():
    """Read the ISO timestamp from the cache metadata file."""
    if os.path.exists(CACHE_META):
        with open(CACHE_META) as f:
            return f.read().strip()
    return "unknown"


def load_data():
    """Load NEO discovery data from DB or cache (refreshed daily).

    Use ``--refresh`` on the command line to force a re-query.
    """
    force = "--refresh" in sys.argv
    if force:
        sys.argv.remove("--refresh")  # prevent reloader from re-querying

    use_cache = False
    if not force and os.path.exists(CACHE_FILE):
        age = time.time() - os.path.getmtime(CACHE_FILE)
        if age < CACHE_MAX_AGE_SEC:
            use_cache = True
            print(f"Loading cached data from {CACHE_FILE} "
                  f"(age: {age/3600:.1f} h)")
        else:
            print(f"Cache is {age/3600:.1f} h old \u2014 refreshing from database")
    elif force:
        print("--refresh flag: forcing re-query")

    if use_cache:
        df = pd.read_csv(CACHE_FILE)
    else:
        print("Querying database (this takes ~30s)...")
        from datetime import datetime, timezone
        query_time = datetime.now(timezone.utc)
        with connect() as conn:
            df = timed_query(conn, LOAD_SQL, label="NEO discoveries for Dash")
        df.to_csv(CACHE_FILE, index=False)
        with open(CACHE_META, "w") as f:
            f.write(query_time.strftime("%Y-%m-%d %H:%M UTC"))
        print(f"Cached {len(df):,} rows to {CACHE_FILE}")

    # Derived columns
    df["station_name"] = df["station_code"].map(STATION_NAMES).fillna(df["station_code"])
    df["project"] = df["station_code"].map(STATION_TO_PROJECT).fillna("Others")

    # H magnitude size bin
    def h_bin(h):
        if pd.isna(h):
            return "Unknown H"
        for label, lo, hi in H_BINS:
            if (lo is None or h >= lo) and (hi is None or h < hi):
                return label
        return "Unknown H"

    df["size_class"] = df["h"].apply(h_bin)

    # Pre-compute half-magnitude bin index
    df["h_bin_idx"] = np.where(
        df["h"].notna(),
        np.digitize(df["h"], H_BIN_EDGES) - 1,
        -1,
    ).astype(int)

    return df


# ---------------------------------------------------------------------------
# Dash app
# ---------------------------------------------------------------------------

app = Dash(__name__)

df = load_data()
query_timestamp = _read_query_timestamp()
year_min, year_max = int(df["disc_year"].min()), int(df["disc_year"].max())

# Label style helper
LABEL_STYLE = {"fontFamily": "sans-serif", "fontSize": "13px"}
# RadioItems label style — "inherit" lets the page-container color propagate
RADIO_LABEL_STYLE = {"color": "inherit", "fontFamily": "sans-serif"}
RADIO_STYLE = {"fontFamily": "sans-serif"}

app.layout = html.Div(
    id="page-container",
    style={
        "minHeight": "100vh", "padding": "20px",
        # Initial CSS variable values (light theme defaults, overwritten
        # immediately by the theme callback on page load)
        "backgroundColor": "#f5f5f5", "color": "#222222",
        "--subtext-color": "#555555",
        "--hr-color": "#cccccc",
        "--paper-bg": "white",
        "--tab-border": "#cccccc",
    },
    children=[
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
                # Title + subtitle (takes remaining space)
                html.Div(
                    style={"marginRight": "auto"},
                    children=[
                        html.H1(
                            "NEO Discovery Statistics",
                            style={"fontFamily": "sans-serif",
                                   "marginBottom": "0", "marginTop": "0"},
                        ),
                        html.P(
                            f"Source: MPC/SBN database "
                            f"({len(df):,} NEO discoveries)",
                            className="subtext",
                            style={"fontFamily": "sans-serif",
                                   "marginTop": "2px",
                                   "marginBottom": "0"},
                        ),
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
                            {"label": " Dark", "value": "dark"},
                            {"label": " Light", "value": "light"},
                        ],
                        value="light",
                        inline=True,
                        style=RADIO_STYLE,
                        labelStyle=RADIO_LABEL_STYLE,
                    ),
                ]),
            ],
        ),
        # ── Tab navigation ───────────────────────────────────────────
        dcc.Tabs(
            id="tabs",
            value="tab-discovery",
            className="nav-tabs",
            children=[
                # ━━━ Tab 1: Discovery by Year ━━━━━━━━━━━━━━━━━━━━━━━━
                dcc.Tab(
                    label="Discovery by Year",
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
                            # Controls row
                            html.Div(
                                style={"display": "flex", "gap": "20px",
                                        "flexWrap": "wrap",
                                        "marginBottom": "10px"},
                                children=[
                                    html.Div(
                                        style={"flex": "1",
                                               "minWidth": "300px"},
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
                                                    "always_visible":
                                                        False},
                                            ),
                                        ],
                                    ),
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

    # Completeness labels as annotations with white background
    if show_labels:
        for i in range(len(comp_x)):
            fig.add_annotation(
                x=comp_x[i], y=comp_y[i], yref="y2",
                text=f"{comp_y[i]:.0f}%",
                showarrow=False,
                xshift=18,
                font=dict(size=9, color="#ff6961"),
                bgcolor="rgba(255,255,255,0.85)",
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
                showarrow=True, arrowhead=2, arrowcolor="#000000",
                ax=45, ay=-28,
                font=dict(size=12, color="#000000"),
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
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nStarting Dash server at http://127.0.0.1:8050/")
    app.run(debug=True, use_reloader=False)
