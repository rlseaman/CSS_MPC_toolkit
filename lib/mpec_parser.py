"""
MPEC (Minor Planet Electronic Circular) parser.

Fetches and parses recent MPECs from minorplanetcenter.net for display
in the dashboard's MPEC Browser tab.  Handles three MPEC types:

- Discovery: new object with provisional designation
- Recovery/Revision: updated orbit for a known object
- Editorial: DAILY ORBIT UPDATE (filtered out)

Caching:
- Recent MPECs list: 15-minute TTL in memory
- Individual MPEC pages: cached to disk permanently (MPECs don't change)

Usage:
    from lib.mpec_parser import fetch_recent_mpecs, fetch_mpec_detail
"""

import os
import re
import time
import urllib.request
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MPC_BASE = "https://www.minorplanetcenter.net"
_RECENT_URL = f"{_MPC_BASE}/mpec/RecentMPECs.html"
_LIST_TTL_SEC = 900  # 15 minutes

# In-memory cache for the recent list
_list_cache = {"data": None, "ts": 0}


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

def _parse_recent_mpecs_html(html_text):
    """Parse RecentMPECs.html using regex to extract MPEC entries.

    The HTML structure per entry is:
        <li><a href="/mpec/K26/K26CB9.html"><i>MPEC</i> 2026-C119</a> (date)
           <ul><li>TITLE</ul>

    Returns list of dicts with keys: mpec_id, path, title, date.
    """
    # Match: <a href="PATH"><i>MPEC</i> ID</a> (DATE) ... <li>TITLE
    pattern = re.compile(
        r'<a\s+href="(/mpec/[^"]+)">'   # capture path
        r'<i>MPEC</i>\s*'                # literal MPEC in italics
        r'([^<]+)</a>'                    # capture ID (e.g. "2026-C119")
        r'\s*\(([^)]+)\)'                # capture date
        r'.*?<li>([^<]+)',               # capture title from nested <li>
        re.DOTALL,
    )
    results = []
    for m in pattern.finditer(html_text):
        path = m.group(1).strip()
        mpec_id = "MPEC " + m.group(2).strip()
        date = m.group(3).strip()
        title = m.group(4).strip()
        results.append({
            "mpec_id": mpec_id,
            "path": path,
            "title": title,
            "date": date,
        })
    return results


class _MPECPageParser(HTMLParser):
    """Extract content from an individual MPEC page."""

    def __init__(self):
        super().__init__()
        self._in_pre = False
        self._pre_parts = []
        self._in_title = False
        self.title = ""
        self.pre_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self._in_pre = True
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self._in_pre = False
            self.pre_text = "".join(self._pre_parts)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_pre:
            self._pre_parts.append(data)
        elif self._in_title:
            self.title += data


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_mpec(title, pre_text=""):
    """Classify an MPEC as discovery, recovery, or editorial.

    Args:
        title: MPEC title text (e.g. "2026 CE3" or "DAILY ORBIT UPDATE")
        pre_text: Full pre-formatted content (for fallback classification)

    Returns:
        "discovery", "recovery", or "editorial"
    """
    if not title:
        return "editorial"
    upper = title.upper()
    if "DAILY ORBIT UPDATE" in upper:
        return "editorial"
    if "EDITORIAL" in upper:
        return "editorial"

    # Check pre_text for recovery indicators
    if pre_text:
        if "Revision to MPEC" in pre_text or "Additional Observations" in pre_text:
            return "recovery"

    # If we have pre_text but no recovery indicators, it's a discovery
    if pre_text:
        return "discovery"

    # Without pre_text, use heuristic on title: current year = likely discovery
    # Older year or numbered object = likely recovery
    import datetime
    current_year = datetime.date.today().year
    m = re.match(r"(\d{4})\s+\w", title)
    if m and int(m.group(1)) == current_year:
        return "discovery"
    if m and int(m.group(1)) < current_year:
        return "recovery"

    return "discovery"


# ---------------------------------------------------------------------------
# Parsing MPEC content
# ---------------------------------------------------------------------------

_SECTION_PATTERNS = {
    "observations": re.compile(r"^Observations?:", re.MULTILINE),
    "observer_details": re.compile(r"^Observer details?:", re.MULTILINE),
    "orbital_elements": re.compile(r"^Orbital elements?:", re.MULTILINE),
    "residuals": re.compile(r"^Residuals?\b", re.MULTILINE),
    "ephemeris": re.compile(r"^Ephemeris:?\s*$", re.MULTILINE),
}

# Order sections appear in a typical MPEC
_SECTION_ORDER = [
    "observations", "observer_details", "orbital_elements",
    "residuals", "ephemeris",
]


def _extract_sections(pre_text):
    """Split MPEC pre-formatted text into named sections."""
    # Find all section start positions
    positions = []
    for name in _SECTION_ORDER:
        pat = _SECTION_PATTERNS[name]
        m = pat.search(pre_text)
        if m:
            positions.append((m.start(), m.end(), name))

    # Sort by position
    positions.sort(key=lambda x: x[0])

    sections = {}
    for i, (start, end, name) in enumerate(positions):
        # Content runs from end of header to start of next section
        if i + 1 < len(positions):
            content = pre_text[end:positions[i + 1][0]]
        else:
            content = pre_text[end:]
        sections[name] = content.strip("\n\r")

    # Extract header (everything before the first section)
    if positions:
        sections["header"] = pre_text[:positions[0][0]].strip()
    else:
        sections["header"] = pre_text.strip()

    return sections


def _parse_orbital_elements(text):
    """Parse orbital elements block into a dict of values."""
    elements = {}

    patterns = {
        "epoch": r"Epoch\s+(.+?)\s+TT",
        "M": r"M\s+([\d.]+)",
        "n": r"n\s+([\d.]+)",
        "a": r"a\s+([\d.]+)",
        "e": r"e\s+([\d.]+)",
        "peri": r"Peri\.\s+([\d.]+)",
        "node": r"Node\s+([\d.]+)",
        "incl": r"Incl\.\s+([\d.]+)",
        "H": r"H\s+([\d.]+)",
        "G": r"G\s+([\d.]+)",
        "earth_moid": r"Earth MOID\s*=\s*([\d.]+)",
        "q": r"q\s+([\d.]+)",
        "period": r"P\s+([\d.]+)\s*years?",
    }

    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            val = m.group(1)
            if key == "epoch":
                elements[key] = val.strip()
            else:
                try:
                    elements[key] = float(val)
                except ValueError:
                    elements[key] = val

    # Derive q from a and e if not directly found
    if "q" not in elements and "a" in elements and "e" in elements:
        elements["q"] = elements["a"] * (1 - elements["e"])

    return elements


def _extract_designation(pre_text):
    """Extract the object designation from MPEC pre-formatted text.

    The designation appears as a centered bold line like **2026 CE3**
    or just as a line with the designation.
    """
    # Look for **DESIGNATION** pattern (bold markers)
    m = re.search(r"\*\*(\d{4}\s+\w+\d*)\*\*", pre_text)
    if m:
        return m.group(1).strip()

    # Look for a line that's just a designation (centered)
    for line in pre_text.split("\n")[:30]:
        stripped = line.strip().strip("*")
        m2 = re.match(r"^(\d{4}\s+[A-Z]{1,2}\d*)$", stripped.strip())
        if m2:
            return m2.group(1)

    return None


def parse_mpec_content(pre_text, mpec_id="", title="", path=""):
    """Parse full MPEC pre-formatted content into a structured dict.

    Returns:
        dict with keys: mpec_id, date, title, designation, type,
        observations, orbital_elements, residuals, ephemeris,
        observers, mpec_url, sections (raw section texts)
    """
    sections = _extract_sections(pre_text)
    designation = _extract_designation(pre_text) or title
    mpec_type = classify_mpec(title, pre_text)

    # Parse orbital elements if present
    orbital_elements = {}
    if "orbital_elements" in sections:
        orbital_elements = _parse_orbital_elements(sections["orbital_elements"])

    # Extract MPEC date from header
    date = ""
    header = sections.get("header", "")
    m = re.search(r"Issued\s+(\d{4}\s+\w+\s+\d{1,2})", header)
    if m:
        date = m.group(1)

    mpec_url = f"{_MPC_BASE}{path}" if path else ""

    return {
        "mpec_id": mpec_id,
        "date": date,
        "title": title,
        "designation": designation,
        "type": mpec_type,
        "observations": sections.get("observations", ""),
        "orbital_elements": orbital_elements,
        "orbital_elements_raw": sections.get("orbital_elements", ""),
        "residuals": sections.get("residuals", ""),
        "ephemeris": sections.get("ephemeris", ""),
        "observers": sections.get("observer_details", ""),
        "mpec_url": mpec_url,
    }


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _fetch_url(url):
    """Fetch URL content as string with timeout."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "CSS-MPC-Toolkit/1.0",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_recent_mpecs(force=False):
    """Fetch and parse the recent MPECs list.

    Returns list of dicts with keys: mpec_id, path, title, date, type.
    Filters out DAILY ORBIT UPDATEs. Cached for 15 minutes.
    """
    now = time.time()
    if not force and _list_cache["data"] and (now - _list_cache["ts"]) < _LIST_TTL_SEC:
        return _list_cache["data"]

    try:
        html_text = _fetch_url(_RECENT_URL)
    except Exception as e:
        print(f"Error fetching RecentMPECs: {e}")
        return _list_cache["data"] or []

    parsed = _parse_recent_mpecs_html(html_text)

    results = []
    for entry in parsed:
        title = entry.get("title", "")
        mpec_type = classify_mpec(title)
        if mpec_type == "editorial":
            continue
        entry["type"] = mpec_type
        results.append(entry)

    _list_cache["data"] = results
    _list_cache["ts"] = now
    return results


def fetch_mpec_detail(mpec_path, cache_dir=None):
    """Fetch and parse an individual MPEC page.

    Args:
        mpec_path: URL path like "/mpec/K26/K26CB9.html"
        cache_dir: Directory for disk cache (optional)

    Returns:
        Parsed MPEC dict from parse_mpec_content()
    """
    # Check disk cache
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        safe_name = mpec_path.replace("/", "_").strip("_") + ".txt"
        cache_path = os.path.join(cache_dir, safe_name)
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                pre_text = f.read()
            # Extract mpec_id and title from cached content
            page_parser = _MPECPageParser()
            # We stored just the pre text; reconstruct minimal parse
            title_line = ""
            for line in pre_text.split("\n")[:30]:
                s = line.strip().strip("*")
                m = re.match(r"^(\d{4}\s+[A-Z]{1,2}\d*)$", s.strip())
                if m:
                    title_line = m.group(1)
                    break
            mpec_m = re.search(r"M\.P\.E\.C\.\s+(\S+)", pre_text)
            mpec_id = mpec_m.group(1) if mpec_m else ""
            return parse_mpec_content(
                pre_text, mpec_id=mpec_id, title=title_line, path=mpec_path)

    url = f"{_MPC_BASE}{mpec_path}"
    try:
        html_text = _fetch_url(url)
    except Exception as e:
        print(f"Error fetching MPEC {mpec_path}: {e}")
        return None

    page_parser = _MPECPageParser()
    page_parser.feed(html_text)

    pre_text = page_parser.pre_text
    page_title = page_parser.title

    # Extract title portion (after " : ")
    title = ""
    if " : " in page_title:
        title = page_title.split(" : ", 1)[1].strip()

    # Extract MPEC ID from page title
    mpec_id = ""
    m = re.match(r"(MPEC\s+\S+)", page_title)
    if m:
        mpec_id = m.group(1)

    # Cache to disk
    if cache_dir and pre_text:
        safe_name = mpec_path.replace("/", "_").strip("_") + ".txt"
        cache_path = os.path.join(cache_dir, safe_name)
        try:
            with open(cache_path, "w") as f:
                f.write(pre_text)
        except OSError:
            pass

    return parse_mpec_content(pre_text, mpec_id=mpec_id, title=title,
                              path=mpec_path)
