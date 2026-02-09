#!/usr/bin/env python3
"""
ADES XML and PSV export from MPC/SBN NEOCP observation data.

Generates valid ADES format output conforming to general.xsd (IAU ADES
version 2022) from neocp_obs_archive observations, optionally resolving
temporary NEOCP designations to final IAU designations.

Usage:
    python3 -m lib.ades_export --host sibyl --format xml --desig "2024 YR4" -o output.xml
    python3 -m lib.ades_export --host sibyl --format psv --desig "2024 YR4" -o output.psv
    python3 -m lib.ades_export --host sibyl --format xml --all --limit 1000 -o neocp_all.xml

Requires: psycopg2 (pip install psycopg2-binary)
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from lib.mpc_convert import parse_obs80, mpc_cat_to_ades


# ---------------------------------------------------------------------------
# ADES XML generation
# ---------------------------------------------------------------------------

ADES_VERSION = "2022"

# Field order for optical observations in ADES XML (general.xsd)
# Only fields present in the data are emitted.
OPTICAL_FIELD_ORDER = [
    "permID", "provID", "trkSub", "obsID", "obsSubID", "trkID", "trkMPC",
    "mode", "stn",
    "obsTime", "rmsTime",
    "ra", "dec", "rmsRA", "rmsDec", "rmsCorr",
    "astCat",
    "mag", "rmsMag", "band",
    "disc", "notes", "remarks",
]

# PSV default column order and widths
PSV_COLUMNS = [
    ("permID",  7),
    ("provID", 11),
    ("trkSub",  8),
    ("mode",    3),
    ("stn",     4),
    ("obsTime", 25),
    ("ra",      12),
    ("dec",     12),
    ("rmsRA",    7),
    ("rmsDec",   7),
    ("rmsCorr",  7),
    ("astCat",   8),
    ("mag",      6),
    ("band",     3),
    ("disc",     1),
    ("notes",    5),
]


def build_optical_element(fields):
    """Build an <optical> XML element from a field dictionary.

    Args:
        fields: dict of ADES field names to values (from parse_obs80
                or database query).

    Returns:
        xml.etree.ElementTree.Element
    """
    optical = ET.Element("optical")

    for field_name in OPTICAL_FIELD_ORDER:
        if field_name not in fields:
            continue

        value = fields[field_name]
        if value is None or value == "":
            continue

        el = ET.SubElement(optical, field_name)

        # Format numeric values appropriately
        if field_name in ("ra", "dec"):
            el.text = f"{value:.6f}" if isinstance(value, float) else str(value)
        elif field_name in ("rmsRA", "rmsDec"):
            el.text = f"{value:.3f}" if isinstance(value, float) else str(value)
        elif field_name in ("rmsCorr",):
            el.text = f"{value:.3f}" if isinstance(value, float) else str(value)
        elif field_name in ("rmsTime",):
            el.text = f"{value:.3f}" if isinstance(value, float) else str(value)
        elif field_name == "mag":
            el.text = f"{value:.2f}" if isinstance(value, float) else str(value)
        else:
            el.text = str(value)

    return optical


def build_ades_xml(observations):
    """Build a complete ADES XML document from a list of observation dicts.

    Uses the general.xsd structure with standalone <optical> elements
    (no obsContext required).

    Args:
        observations: list of dicts, each with ADES field names as keys.

    Returns:
        xml.etree.ElementTree.Element (root <ades> element)
    """
    root = ET.Element("ades", version=ADES_VERSION)

    for obs in observations:
        optical = build_optical_element(obs)
        root.append(optical)

    return root


def xml_to_string(root, pretty=True):
    """Serialize an XML element tree to a string.

    Args:
        root: ElementTree Element
        pretty: if True, indent the output

    Returns:
        XML string with declaration
    """
    rough = ET.tostring(root, encoding="unicode", xml_declaration=False)

    if pretty:
        dom = minidom.parseString(rough)
        lines = dom.toprettyxml(indent="  ", encoding=None)
        # Remove the minidom XML declaration (we add our own)
        lines = "\n".join(
            line for line in lines.split("\n")
            if not line.startswith("<?xml")
        )
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + lines.strip() + "\n"
    else:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + rough + "\n"


# ---------------------------------------------------------------------------
# ADES PSV generation
# ---------------------------------------------------------------------------

def build_psv(observations, columns=None):
    """Build ADES PSV (pipe-separated values) output.

    Args:
        observations: list of dicts with ADES field names as keys.
        columns: list of (name, width) tuples. Defaults to PSV_COLUMNS.

    Returns:
        String containing the complete PSV document.
    """
    if columns is None:
        columns = PSV_COLUMNS

    lines = []
    lines.append(f"# version={ADES_VERSION}")
    lines.append("")

    # Header record (field names)
    header_parts = []
    for name, width in columns:
        header_parts.append(f"{name:>{width}}" if width > 0 else name)
    lines.append("|".join(header_parts))

    # Data records
    for obs in observations:
        parts = []
        for name, width in columns:
            val = obs.get(name)
            if val is None or val == "":
                formatted = " " * width if width > 0 else ""
            elif name in ("ra", "dec"):
                formatted = f"{val:>{width}.6f}" if isinstance(val, float) else f"{val:>{width}}"
            elif name in ("rmsRA", "rmsDec", "rmsCorr"):
                formatted = f"{val:>{width}.3f}" if isinstance(val, float) else f"{val:>{width}}"
            elif name == "mag":
                formatted = f"{val:>{width}.2f}" if isinstance(val, float) else f"{val:>{width}}"
            else:
                formatted = f"{str(val):>{width}}" if width > 0 else str(val)
            parts.append(formatted)
        lines.append("|".join(parts))

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Database query
# ---------------------------------------------------------------------------

QUERY_BY_DESIG = """
    SELECT oa.obs80, oa.trkid, oa.rmsra, oa.rmsdec, oa.rmscorr, oa.rmstime,
           pd.iau_desig, pd.pkd_desig
    FROM neocp_obs_archive oa
    LEFT JOIN neocp_prev_des pd ON pd.desig = oa.desig
    WHERE pd.iau_desig = %(desig)s
       OR pd.pkd_desig = %(desig)s
       OR oa.desig = %(desig)s
    ORDER BY oa.created_at
"""

QUERY_ALL = """
    SELECT oa.obs80, oa.trkid, oa.rmsra, oa.rmsdec, oa.rmscorr, oa.rmstime,
           pd.iau_desig, pd.pkd_desig
    FROM neocp_obs_archive oa
    LEFT JOIN neocp_prev_des pd ON pd.desig = oa.desig
    ORDER BY oa.desig, oa.created_at
    LIMIT %(limit)s
"""


def rows_to_ades_fields(rows):
    """Convert database rows to ADES field dictionaries.

    Each row is a tuple: (obs80, trkid, rmsra, rmsdec, rmscorr, rmstime,
                          iau_desig, pkd_desig)

    Returns list of dicts suitable for build_ades_xml or build_psv.
    """
    observations = []
    for row in rows:
        obs80, trkid, rmsra, rmsdec, rmscorr, rmstime, iau_desig, pkd_desig = row

        # Parse the 80-column line
        rmsra_f = float(rmsra) if rmsra is not None else None
        rmsdec_f = float(rmsdec) if rmsdec is not None else None
        rmscorr_f = float(rmscorr) if rmscorr is not None else None
        rmstime_f = float(rmstime) if rmstime is not None else None

        fields = parse_obs80(obs80, rmsra=rmsra_f, rmsdec=rmsdec_f,
                             rmscorr=rmscorr_f, rmstime=rmstime_f)

        # Override designation with resolved IAU designation
        if iau_desig:
            # Remove the temporary NEOCP provID
            fields.pop("provID", None)
            fields.pop("permID", None)
            if iau_desig.strip().isdigit():
                fields["permID"] = iau_desig.strip()
            else:
                fields["provID"] = iau_desig.strip()

        # Add tracklet ID as trkSub
        if trkid:
            fields["trkSub"] = trkid.strip()

        observations.append(fields)

    return observations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export NEOCP observations in ADES XML or PSV format"
    )
    parser.add_argument("--host", default="sibyl",
                        help="PostgreSQL host (default: sibyl)")
    parser.add_argument("--db", default="mpc_sbn",
                        help="Database name (default: mpc_sbn)")
    parser.add_argument("--user", default="claude_ro",
                        help="Database user (default: claude_ro)")
    parser.add_argument("--format", choices=["xml", "psv"], default="xml",
                        help="Output format (default: xml)")
    parser.add_argument("--desig",
                        help="Object designation (IAU, packed, or NEOCP temp)")
    parser.add_argument("--all", action="store_true",
                        help="Export all archived observations")
    parser.add_argument("--limit", type=int, default=10000,
                        help="Row limit for --all (default: 10000)")
    parser.add_argument("-o", "--output",
                        help="Output file (default: stdout)")
    parser.add_argument("--compact", action="store_true",
                        help="Compact XML (no indentation)")

    args = parser.parse_args()

    if not args.desig and not args.all:
        parser.error("Specify --desig or --all")

    if psycopg2 is None:
        print("Error: psycopg2 not installed. Run: pip install psycopg2-binary",
              file=sys.stderr)
        sys.exit(1)

    # Connect and query
    conn = psycopg2.connect(host=args.host, dbname=args.db, user=args.user)
    cur = conn.cursor()

    if args.desig:
        cur.execute(QUERY_BY_DESIG, {"desig": args.desig})
    else:
        cur.execute(QUERY_ALL, {"limit": args.limit})

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print(f"No observations found.", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(rows)} observations...", file=sys.stderr)

    # Convert to ADES fields
    observations = rows_to_ades_fields(rows)

    # Generate output
    if args.format == "xml":
        root = build_ades_xml(observations)
        output = xml_to_string(root, pretty=not args.compact)
    else:
        output = build_psv(observations)

    # Write
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {len(observations)} observations to {args.output}",
              file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
