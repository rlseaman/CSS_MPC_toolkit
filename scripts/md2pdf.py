#!/usr/bin/env python
"""Convert a Markdown file to a styled PDF.

Uses the Python markdown library for parsing and weasyprint for PDF
rendering.  Supports GitHub-flavored tables, fenced code blocks, and
produces letter-size output with professional typography.

Usage:
    python scripts/md2pdf.py docs/report.md                # -> docs/report.pdf
    python scripts/md2pdf.py docs/report.md -o output.pdf   # explicit output
    python scripts/md2pdf.py docs/report.md --open           # open after generating

Requirements (in venv):
    pip install markdown weasyprint
"""

import argparse
import os
import subprocess
import sys

import markdown
from weasyprint import HTML

_STYLESHEET = """
body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    max-width: 7in;
    margin: 0 auto;
    color: #222;
}
h1 {
    font-size: 18pt;
    border-bottom: 2px solid #333;
    padding-bottom: 6pt;
}
h2 {
    font-size: 14pt;
    border-bottom: 1px solid #999;
    padding-bottom: 4pt;
    margin-top: 24pt;
}
h3 {
    font-size: 12pt;
    margin-top: 18pt;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12pt 0;
    font-size: 9.5pt;
}
th, td {
    border: 1px solid #999;
    padding: 4pt 6pt;
    text-align: left;
}
th {
    background: #f0f0f0;
    font-weight: bold;
}
tr:nth-child(even) {
    background: #fafafa;
}
code {
    font-family: "Menlo", "Consolas", monospace;
    font-size: 9.5pt;
    background: #f4f4f4;
    padding: 1pt 3pt;
}
pre {
    background: #f4f4f4;
    padding: 8pt;
    border-radius: 4pt;
    overflow-x: auto;
    font-size: 8.5pt;
    line-height: 1.35;
}
pre code {
    background: none;
    padding: 0;
}
strong {
    color: #111;
}
@page {
    size: letter;
    margin: 0.75in;
}
"""


def md_to_pdf(md_path, pdf_path):
    """Convert a Markdown file to PDF."""
    with open(md_path) as f:
        md_text = f.read()

    html_body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code"])

    html_doc = (
        '<!DOCTYPE html>\n<html>\n<head><meta charset="utf-8">\n'
        f"<style>{_STYLESHEET}</style>\n"
        f"</head>\n<body>\n{html_body}\n</body></html>"
    )

    HTML(string=html_doc).write_pdf(pdf_path)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown to styled PDF")
    parser.add_argument("input", help="Input Markdown file")
    parser.add_argument("-o", "--output", default=None,
                        help="Output PDF path (default: same name, .pdf)")
    parser.add_argument("--open", action="store_true", dest="open_after",
                        help="Open the PDF after generating")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    if args.output:
        pdf_path = args.output
    else:
        pdf_path = os.path.splitext(args.input)[0] + ".pdf"

    md_to_pdf(args.input, pdf_path)
    size_kb = os.path.getsize(pdf_path) / 1024
    print(f"{pdf_path}  ({size_kb:.0f} KB)")

    if args.open_after:
        subprocess.run(["open", pdf_path])


if __name__ == "__main__":
    main()
