#!/usr/bin/env python3
"""
Validate ADES XML files against general.xsd (IAU ADES version 2022).

Uses the general.xsd schema from the ADES-Master repository:
  https://github.com/IAU-ADES/ADES-Master

Usage:
    python3 -m lib.ades_validate neocp_live.xml
    python3 -m lib.ades_validate --verbose neocp_live.xml
    python3 -m lib.ades_validate --max-errors 5 neocp_live.xml

Requires: lxml (pip install lxml)
"""

import argparse
import os
import sys

try:
    from lxml import etree
except ImportError:
    print("Error: lxml not installed. Run: pip install lxml", file=sys.stderr)
    sys.exit(1)


def find_schema():
    """Locate general.xsd relative to this script."""
    here = os.path.dirname(os.path.abspath(__file__))
    xsd_path = os.path.join(here, os.pardir, "schema", "general.xsd")
    xsd_path = os.path.normpath(xsd_path)
    if not os.path.isfile(xsd_path):
        return None
    return xsd_path


def validate(xml_path, xsd_path, max_errors=0, verbose=False):
    """Validate an ADES XML file against general.xsd.

    Args:
        xml_path: Path to the XML file to validate.
        xsd_path: Path to general.xsd.
        max_errors: Stop after this many errors (0 = report all).
        verbose: Print each observation count and additional context.

    Returns:
        True if valid, False if errors found.
    """
    # Parse the XSD
    try:
        xsd_doc = etree.parse(xsd_path)
        schema = etree.XMLSchema(xsd_doc)
    except etree.XMLSchemaParseError as e:
        print(f"Schema error in {xsd_path}: {e}", file=sys.stderr)
        return False

    # Parse the XML
    try:
        doc = etree.parse(xml_path)
    except etree.XMLSyntaxError as e:
        print(f"XML syntax error: {e}", file=sys.stderr)
        return False

    root = doc.getroot()

    # Quick stats
    n_optical = len(root.findall("optical"))
    n_obsblock = len(root.findall("obsBlock"))
    if verbose:
        print(f"File: {xml_path}")
        print(f"Root element: <{root.tag}> version={root.get('version', '?')}")
        print(f"Standalone <optical> elements: {n_optical}")
        print(f"<obsBlock> elements: {n_obsblock}")
        # Count optical inside obsBlocks too
        n_block_optical = len(root.findall(".//obsBlock/obsData/optical"))
        if n_block_optical:
            print(f"<optical> inside obsBlocks: {n_block_optical}")
        print()

    # Validate
    is_valid = schema.validate(doc)

    if is_valid:
        total = n_optical + len(root.findall(".//obsBlock/obsData/optical"))
        print(f"VALID -- {total} optical observation(s)")
        return True

    # Report errors
    errors = schema.error_log
    n_errors = len(errors)
    limit = max_errors if max_errors > 0 else n_errors

    print(f"INVALID -- {n_errors} error(s) found\n")

    for i, error in enumerate(errors):
        if i >= limit:
            remaining = n_errors - limit
            print(f"... and {remaining} more error(s). "
                  f"Use --max-errors 0 to show all.")
            break

        print(f"  Line {error.line}: {error.message}")

        # For verbose mode, show the element context
        if verbose and error.line:
            try:
                with open(xml_path) as f:
                    lines = f.readlines()
                    line_idx = error.line - 1
                    if 0 <= line_idx < len(lines):
                        print(f"    > {lines[line_idx].rstrip()}")
            except (IOError, IndexError):
                pass

    print()
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate ADES XML against general.xsd"
    )
    parser.add_argument("xml_file", help="ADES XML file to validate")
    parser.add_argument("--xsd", help="Path to general.xsd (auto-detected by default)")
    parser.add_argument("--max-errors", type=int, default=20,
                        help="Max errors to display (0=all, default=20)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show file stats and error context")
    args = parser.parse_args()

    xsd_path = args.xsd or find_schema()
    if not xsd_path:
        print("Error: Cannot find schema/general.xsd. "
              "Use --xsd to specify path.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.xml_file):
        print(f"Error: File not found: {args.xml_file}", file=sys.stderr)
        sys.exit(1)

    ok = validate(args.xml_file, xsd_path,
                  max_errors=args.max_errors, verbose=args.verbose)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
