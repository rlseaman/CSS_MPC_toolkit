"""MPEC Full Document Viewer — standalone prototype on port 8051.

Renders the complete MPEC as a single annotated document with
tracklet color-coding, discovery highlighting, and station tooltips.
Optional diff panel compares MPC vs NEOfixer (Find_Orb) orbital elements.
"""

import os
import re
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dash import Dash, html, dcc, Input, Output, State, no_update
from lib.mpec_parser import parse_mpec_content
from lib.api_clients import fetch_neofixer_orbit
from lib.mpc_convert import pack_designation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).resolve().parent.parent / "app" / ".mpec_cache"

STATION_NAMES = {
    "703": "Catalina", "G96": "Mt. Lemmon", "E12": "Siding Spring",
    "I52": "Mt. Lemmon-Steward", "V06": "CSS-Kuiper",
    "G84": "Mt. Lemmon SkyCenter", "V00": "Kitt Peak-Bok", "X05": "Rubin",
    "F51": "Pan-STARRS 1", "F52": "Pan-STARRS 2",
    "T05": "ATLAS-HKO", "T08": "ATLAS-MLO", "T07": "ATLAS-SSO",
    "T03": "ATLAS-RIO", "M22": "ATLAS-AEOS", "W68": "ATLAS-STH",
    "R17": "ATLAS-KNO",
    "704": "LINEAR", "699": "LONEOS",
    "691": "Spacewatch", "291": "Spacewatch II",
    "644": "NEAT-Palomar", "608": "NEAT-Haleakala",
    "I41": "ZTF", "C51": "WISE/NEOWISE", "C57": "WISE/NEOWISE",
    "W84": "DECam", "U68": "SynTrack", "U74": "SynTrack 2",
    "H01": "Magdalena Ridge", "807": "Cerro Tololo",
}

TRACKLET_COLORS = [
    "rgba(100, 150, 255, 0.18)",  # blue
    "rgba(100, 200, 130, 0.18)",  # green
    "rgba(200, 150, 80,  0.18)",  # amber
    "rgba(180, 100, 200, 0.18)",  # purple
    "rgba(200, 100, 100, 0.18)",  # red
    "rgba(100, 200, 200, 0.18)",  # teal
]
DISC_TRACKLET_BG = "rgba(60, 180, 75, 0.22)"

# Delta thresholds: (green_lt, yellow_lt) — anything >= yellow_lt is red
DELTA_THRESHOLDS = {
    "a":          (0.001,  0.01),
    "e":          (0.001,  0.01),
    "i":          (0.1,    1.0),
    "peri":       (0.1,    1.0),
    "node":       (0.1,    1.0),
    "M":          (1.0,    5.0),
    "H":          (0.1,    0.5),
    "q":          (0.001,  0.01),
    "earth_moid": (0.001,  0.01),
}

ELEMENT_LABELS = {
    "a": "a (AU)", "e": "e", "i": "i (°)", "peri": "ω (°)",
    "node": "Ω (°)", "M": "M (°)", "q": "q (AU)",
    "H": "H (mag)", "earth_moid": "MOID (AU)",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_cached_mpecs():
    """Scan cache dir, return dropdown options sorted newest-first."""
    if not CACHE_DIR.is_dir():
        return []
    options = []
    for f in sorted(CACHE_DIR.glob("*.txt"), reverse=True):
        # Filename like mpec_K26_K26C25.html.txt
        stem = f.stem  # mpec_K26_K26C25.html
        # Extract MPEC ID from content (first non-blank line with M.P.E.C.)
        mpec_id = stem.replace("mpec_", "").replace(".html", "")
        options.append({"label": mpec_id, "value": str(f)})
    return options


def _is_obs_line(line):
    """True if line is an MPC 80-column observation (not orbital elements)."""
    if len(line) < 80:
        return False
    # Col 14: observation type code; cols 15-18: 4-digit year
    return (line[14] in "CcSsXxAaEeHhPpRrTtVvWw"
            and line[15:19].strip().isdigit())


def _tracklet_key(line):
    """Extract (station, date_int) from an 80-col observation line."""
    if not _is_obs_line(line):
        return None
    stn = line[77:80].strip()
    try:
        date_int = line[15:25].split(".")[0].strip()
    except Exception:
        date_int = ""
    return (stn, date_int)


def render_full_document(pre_text):
    """Render full MPEC text as a list of styled html.Div elements."""
    lines = pre_text.split("\n")
    children = []

    # Section header patterns (for tracking current section)
    section_re = re.compile(
        r"^(Observations:|Orbital elements:|Residuals|Ephemeris:|"
        r"Observer details:|Further observations:)", re.IGNORECASE)

    # First pass: identify tracklet keys, assign colors, find discovery stn
    tracklet_map = {}  # key -> color
    disc_tracklet = None
    disc_station = None
    color_idx = 0
    for line in lines:
        if len(line) < 80:
            continue
        key = _tracklet_key(line)
        if key is None:
            continue
        if key not in tracklet_map:
            is_disc = len(line) > 12 and line[12] == "*"
            if is_disc:
                tracklet_map[key] = DISC_TRACKLET_BG
                disc_tracklet = key
                disc_station = key[0]
            else:
                tracklet_map[key] = TRACKLET_COLORS[
                    color_idx % len(TRACKLET_COLORS)]
                color_idx += 1

    # Observer-detail paragraphs start with a 3-char station code;
    # continuation lines start with spaces.  Pre-scan to find which
    # line ranges belong to the discovery station.
    disc_observer_lines = set()
    disc_residual_lines = set()
    current_section = ""
    in_disc_observer_para = False
    for i, line in enumerate(lines):
        sm = section_re.match(line.strip())
        if sm:
            current_section = sm.group(1).lower()
            in_disc_observer_para = False

        if current_section.startswith("observer"):
            # New station paragraph: line starts with non-space char
            if line and not line[0].isspace():
                stn_code = line[:3].strip()
                in_disc_observer_para = (stn_code == disc_station)
            if in_disc_observer_para:
                disc_observer_lines.add(i)

    # Second pass: render lines
    DISC_HIGHLIGHT = "rgba(60, 180, 75, 0.13)"
    _entry_start_re = re.compile(r"\d{6} ")
    current_section = ""
    for i, line in enumerate(lines):
        style = {
            "fontFamily": "monospace",
            "fontSize": "13px",
            "whiteSpace": "pre",
            "padding": "1px 8px",
            "margin": "0",
            "lineHeight": "1.5",
            "minHeight": "1.3em",
        }

        sm = section_re.match(line.strip())
        if sm:
            current_section = sm.group(1).lower()

        # Observation lines: tracklet colors + discovery highlighting
        key = _tracklet_key(line) if len(line) >= 80 else None
        if key and key in tracklet_map:
            style["backgroundColor"] = tracklet_map[key]
            is_disc_obs = len(line) > 12 and line[12] == "*"
            if is_disc_obs:
                style["fontWeight"] = "700"
            if key == disc_tracklet:
                style["boxShadow"] = "inset 3px 0 0 #3cb44b"

            # Wrap station code in tooltip span
            stn = line[77:80].strip()
            stn_name = STATION_NAMES.get(stn, stn)
            pre_stn = line[:77]
            stn_part = line[77:80]
            post_stn = line[80:] if len(line) > 80 else ""
            child = html.Div([
                html.Span(pre_stn),
                html.Span(stn_part, title=stn_name, style={
                    "textDecoration": "underline dotted",
                    "cursor": "help",
                }),
                html.Span(post_stn),
            ], style=style)

        # Discovery observer paragraph
        elif i in disc_observer_lines:
            style["backgroundColor"] = DISC_HIGHLIGHT
            style["boxShadow"] = "inset 3px 0 0 #3cb44b"
            child = html.Div(line, style=style)

        # Residual lines: highlight only discovery-station entries
        elif (current_section.startswith("residual")
              and disc_station and _entry_start_re.search(line)):
            # Split line into entries at each "YYMMDD " boundary
            starts = [m.start() for m in _entry_start_re.finditer(line)]
            spans = []
            for j, s in enumerate(starts):
                e = starts[j + 1] if j + 1 < len(starts) else len(line)
                entry_text = line[s:e]
                # Station code follows the 7-char "YYMMDD " prefix
                entry_stn = entry_text[7:10].strip()
                if s > 0 and j == 0:
                    spans.append(html.Span(line[:s]))
                if entry_stn == disc_station:
                    spans.append(html.Span(entry_text, style={
                        "backgroundColor": DISC_HIGHLIGHT,
                        "borderRadius": "2px",
                    }))
                else:
                    spans.append(html.Span(entry_text))
            child = html.Div(spans, style=style)

        else:
            child = html.Div(line if line else "\u00a0", style=style)

        children.append(child)
    return children


def _delta_color(key, delta):
    """Return CSS color for a delta value based on thresholds."""
    if delta is None:
        return "inherit"
    thresholds = DELTA_THRESHOLDS.get(key)
    if not thresholds:
        return "inherit"
    green_lt, yellow_lt = thresholds
    ad = abs(delta)
    if ad < green_lt:
        return "#2ecc71"  # green
    elif ad < yellow_lt:
        return "#f39c12"  # yellow/amber
    else:
        return "#e74c3c"  # red


def build_diff_panel(mpc_elements, neofixer_data):
    """Build comparison table of MPC vs NEOfixer orbital elements."""
    if not neofixer_data:
        return html.Div("NEOfixer data unavailable for this object.",
                         style={"color": "#e74c3c", "padding": "20px",
                                "fontStyle": "italic"})

    nf_elem = neofixer_data.get("elements", {})
    nf_top = neofixer_data  # H, earth_moid at top level

    rows = []
    for key, label in ELEMENT_LABELS.items():
        mpc_val = mpc_elements.get(key)
        if key in ("H", "earth_moid"):
            nf_val = nf_top.get(key)
        else:
            nf_val = nf_elem.get(key)

        delta = None
        if mpc_val is not None and nf_val is not None:
            try:
                delta = float(nf_val) - float(mpc_val)
            except (TypeError, ValueError):
                pass

        fmt = lambda v: f"{v:.6f}" if isinstance(v, float) else (str(v) if v is not None else "—")
        delta_str = f"{delta:+.6f}" if delta is not None else "—"
        d_color = _delta_color(key, delta)

        cell_style = {"padding": "6px 10px", "borderBottom": "1px solid rgba(255,255,255,0.1)"}
        rows.append(html.Tr([
            html.Td(label, style={**cell_style, "fontWeight": "600"}),
            html.Td(fmt(mpc_val), style={**cell_style, "textAlign": "right"}),
            html.Td(fmt(nf_val), style={**cell_style, "textAlign": "right"}),
            html.Td(delta_str, style={
                **cell_style, "textAlign": "right",
                "color": d_color, "fontWeight": "600",
            }),
        ]))

    header = html.Tr([
        html.Th("Element", style={"padding": "8px 10px", "textAlign": "left"}),
        html.Th("MPC", style={"padding": "8px 10px", "textAlign": "right"}),
        html.Th("NEOfixer", style={"padding": "8px 10px", "textAlign": "right"}),
        html.Th("Δ", style={"padding": "8px 10px", "textAlign": "right"}),
    ])

    rms = neofixer_data.get("rms")
    n_obs = neofixer_data.get("n_obs")
    footer_parts = []
    if rms is not None:
        footer_parts.append(f"RMS: {rms:.2f}\"")
    if n_obs is not None:
        footer_parts.append(f"N_obs: {n_obs}")

    return html.Div([
        html.H4("Orbital Elements: MPC vs NEOfixer (Find_Orb)",
                 style={"margin": "0 0 12px 0", "fontSize": "15px"}),
        html.Table([html.Thead(header), html.Tbody(rows)],
                   style={"width": "100%", "borderCollapse": "collapse",
                          "fontSize": "13px", "fontFamily": "monospace"}),
        html.Div(" | ".join(footer_parts),
                 style={"fontSize": "12px", "marginTop": "8px",
                         "opacity": "0.7"}) if footer_parts else None,
    ])


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Dash(__name__)
app.title = "MPEC Full Document Viewer"

app.layout = html.Div(id="page-container", children=[
    # Header
    html.Div([
        html.H2("MPEC Full Document Viewer",
                style={"margin": "0", "fontSize": "20px"}),
        html.Div([
            dcc.Dropdown(
                id="mpec-select",
                options=load_cached_mpecs(),
                placeholder="Select MPEC...",
                style={"width": "260px", "color": "#222"},
            ),
            dcc.Checklist(
                id="diff-toggle",
                options=[{"label": " Diff Mode", "value": "on"}],
                value=[],
                style={"marginLeft": "16px", "display": "flex",
                       "alignItems": "center"},
            ),
            html.Button("Dark", id="theme-btn", n_clicks=0,
                        style={"marginLeft": "16px", "cursor": "pointer",
                               "padding": "4px 12px", "borderRadius": "4px",
                               "border": "1px solid rgba(255,255,255,0.3)",
                               "background": "transparent", "color": "inherit"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
    ], style={"display": "flex", "justifyContent": "space-between",
              "alignItems": "center", "padding": "12px 20px",
              "borderBottom": "1px solid rgba(255,255,255,0.15)"}),

    # Body: document + optional diff panel
    html.Div([
        html.Div(id="doc-panel", style={
            "flex": "0 0 auto", "width": "fit-content",
            "overflow": "auto", "padding": "16px 20px",
            "maxHeight": "calc(100vh - 70px)",
            "margin": "12px", "borderRadius": "6px",
            "border": "1px solid rgba(255, 255, 255, 0.12)",
            "backgroundColor": "rgba(0, 0, 0, 0.15)",
        }),
        html.Div(id="diff-panel", style={
            "width": "380px", "overflow": "auto", "padding": "12px 16px",
            "borderLeft": "1px solid rgba(255,255,255,0.15)",
            "maxHeight": "calc(100vh - 70px)",
            "display": "none",
        }),
    ], style={"display": "flex", "flex": "1", "overflow": "hidden"}),

    # Store parsed data for diff callback
    dcc.Store(id="parsed-store"),
], style={
    "display": "flex", "flexDirection": "column", "height": "100vh",
    "fontFamily": "'Segoe UI', system-ui, sans-serif",
    # Dark theme defaults
    "backgroundColor": "#1a1a2e", "color": "#e0e0e0",
})


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@app.callback(
    Output("doc-panel", "children"),
    Output("parsed-store", "data"),
    Input("mpec-select", "value"),
)
def update_document(filepath):
    if not filepath:
        return html.Div("Select an MPEC to view.",
                         style={"padding": "40px", "opacity": "0.5",
                                "textAlign": "center"}), {}
    try:
        text = Path(filepath).read_text()
    except Exception as e:
        return html.Div(f"Error reading file: {e}",
                         style={"color": "#e74c3c"}), {}

    parsed = parse_mpec_content(text)
    doc_children = render_full_document(text)

    store = {
        "designation": parsed.get("designation", ""),
        "orbital_elements": parsed.get("orbital_elements", {}),
    }
    return doc_children, store


@app.callback(
    Output("diff-panel", "children"),
    Output("diff-panel", "style"),
    Input("diff-toggle", "value"),
    Input("parsed-store", "data"),
)
def update_diff(toggle_val, store_data):
    base_style = {
        "width": "380px", "overflow": "auto", "padding": "12px 16px",
        "borderLeft": "1px solid rgba(255,255,255,0.15)",
        "maxHeight": "calc(100vh - 70px)",
    }
    if "on" not in (toggle_val or []) or not store_data:
        return no_update, {**base_style, "display": "none"}

    desig = store_data.get("designation", "")
    mpc_elem = store_data.get("orbital_elements", {})
    if not desig:
        return html.Div("No designation found in this MPEC.",
                         style={"fontStyle": "italic", "opacity": "0.5"}), \
               {**base_style, "display": "block"}

    try:
        packed = pack_designation(desig)
    except Exception:
        return html.Div(f"Could not pack designation: {desig}",
                         style={"color": "#e74c3c"}), \
               {**base_style, "display": "block"}

    nf_data = fetch_neofixer_orbit(packed)
    panel = build_diff_panel(mpc_elem, nf_data)
    return panel, {**base_style, "display": "block"}


@app.callback(
    Output("page-container", "style"),
    Output("theme-btn", "children"),
    Input("theme-btn", "n_clicks"),
)
def toggle_theme(n):
    dark = (n or 0) % 2 == 0
    if dark:
        return {
            "display": "flex", "flexDirection": "column", "height": "100vh",
            "fontFamily": "'Segoe UI', system-ui, sans-serif",
            "backgroundColor": "#1a1a2e", "color": "#e0e0e0",
        }, "Light"
    else:
        return {
            "display": "flex", "flexDirection": "column", "height": "100vh",
            "fontFamily": "'Segoe UI', system-ui, sans-serif",
            "backgroundColor": "#f5f5f5", "color": "#222",
        }, "Dark"


if __name__ == "__main__":
    app.run(port=8051, debug=True)
