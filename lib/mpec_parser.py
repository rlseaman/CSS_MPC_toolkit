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

import email.utils
import json
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

def mpec_id_to_url(mpec_id):
    """Convert an MPEC ID like '2026-C105' to a full MPC URL.

    The packed path for MPEC 2026-C105 is /mpec/K26/K26CA5.html where:
    - 2026 → K26 (K = century 20)
    - C105 → CA5 (numbers ≥100 pack as letter+digit: 100=A0 … 369=Z9)
    """
    m = re.match(r"(\d{4})-([A-Z])(\d+)", mpec_id)
    if not m:
        return ""
    year, half_month, num_str = int(m.group(1)), m.group(2), int(m.group(3))

    # Pack century: 1800→I, 1900→J, 2000→K
    century_letter = chr(ord("A") + (year // 100 - 10))
    yy = f"{year % 100:02d}"
    packed_year = f"{century_letter}{yy}"

    # Pack number: 1-99 → two digits, 100+ → letter+digit
    if num_str <= 99:
        packed_num = f"{num_str:02d}"
    else:
        hundreds = (num_str - 100) // 10
        ones = num_str % 10
        packed_num = f"{chr(ord('A') + hundreds)}{ones}"

    packed = f"{packed_year}{half_month}{packed_num}"
    return f"{_MPC_BASE}/mpec/{packed_year}/{packed}.html"


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
        self.prev_path = ""
        self.next_path = ""
        self._last_href = ""

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self._in_pre = True
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href", "")
            self._last_href = href
        elif tag == "img":
            src = dict(attrs).get("src", "")
            if "LArrow" in src and self._last_href:
                self.prev_path = self._last_href
            elif "RArrow" in src and self._last_href:
                self.next_path = self._last_href

    def handle_endtag(self, tag):
        if tag == "pre":
            self._in_pre = False
            self.pre_text = "".join(self._pre_parts)
        elif tag == "title":
            self._in_title = False
        elif tag == "a":
            self._last_href = ""

    def handle_data(self, data):
        if self._in_pre:
            self._pre_parts.append(data)
        elif self._in_title:
            self.title += data


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_mpec(title, pre_text=""):
    """Classify an MPEC as discovery, recovery, dou, retraction, or editorial.

    Args:
        title: MPEC title text (e.g. "2026 CE3" or "DAILY ORBIT UPDATE")
        pre_text: Full pre-formatted content (for fallback classification)

    Returns:
        "discovery", "recovery", "dou", "retraction", or "editorial"
    """
    upper = (title or "").upper()
    if "DAILY ORBIT UPDATE" in upper:
        return "dou"
    if "RETRACTION" in upper:
        return "retraction"
    if "EDITORIAL" in upper:
        return "editorial"

    # Check pre_text for DOU/editorial/recovery indicators
    if pre_text:
        pre_upper = pre_text[:2000].upper()
        if "DAILY ORBIT UPDATE" in pre_upper:
            return "dou"
        if "RETRACTION" in pre_upper:
            return "retraction"
        # Match "EDITORIAL" as a standalone line (not part of "editorial
        # announcements" or similar phrases in boilerplate)
        if re.search(r"^\s*EDITORIAL", pre_text[:2000], re.MULTILINE):
            return "editorial"
        if "Revision to MPEC" in pre_text or "Additional Observations" in pre_text:
            return "recovery"

    # Year-based heuristic: compare designation year to MPEC issue year.
    # A designation from a prior year implies recovery/follow-up, not
    # first discovery.  Works for both title-only and full-content MPECs.
    import datetime
    current_year = datetime.date.today().year
    # Try designation year from title or content:
    #   "2026 CE3", "C/2026 A1", "COMET C/2026 A1", "**2025 XY**"
    desig_year = None
    combined = title or ""
    if pre_text:
        combined = pre_text[:2000]
    m = re.search(r"(?:[CPD]/)(\d{4})\s+\w", combined)
    if not m:
        m = re.search(r"\b(\d{4})\s+[A-Z]{1,2}\d*\b", combined)
    if m:
        desig_year = int(m.group(1))
    if desig_year is not None:
        if desig_year < current_year:
            return "recovery"
        return "discovery"

    # No year in designation (interstellar objects like 3I/ATLAS, numbered
    # comets, etc.).  Check if earliest observation predates the MPEC year.
    if pre_text:
        obs_years = re.findall(
            r"[A-Za-z](\d{4})\s+\d{2}\s+\d", pre_text[:5000])
        if obs_years:
            earliest_obs = min(int(y) for y in obs_years)
            if earliest_obs < current_year:
                return "recovery"

    # Default: if we have content, assume discovery
    if pre_text:
        return "discovery"

    if not title:
        return "editorial"

    return "discovery"


# ---------------------------------------------------------------------------
# Parsing MPEC content
# ---------------------------------------------------------------------------

_SECTION_PATTERNS = {
    "observations": re.compile(
        r"^(?:Available\s+|Additional\s+)?Observations?:",
        re.MULTILINE | re.IGNORECASE),
    "observer_details": re.compile(r"^Observer details?:", re.MULTILINE),
    "orbital_elements": re.compile(r"^Orbital elements?\b.*:",
                                       re.MULTILINE | re.IGNORECASE),
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
    # Find all section start positions.
    # Use the LAST match for each pattern — recovery MPECs have
    # "Residuals in seconds of arc" both as a brief comparison block
    # (before orbital elements) and as the full block (after).
    positions = []
    for name in _SECTION_ORDER:
        pat = _SECTION_PATTERNS[name]
        last_match = None
        for m in pat.finditer(pre_text):
            last_match = m
        if last_match:
            positions.append((last_match.start(), last_match.end(), name))

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

    # Patterns anchored to line start where needed to avoid false matches
    # (e.g., "e" in "Node", "a" in "PHA")
    patterns = {
        "epoch": r"Epoch\s+(.+?)\s+TT",
        "M": r"^M\s+([\d.]+)",
        "n": r"^n\s+([\d.]+)",
        "a": r"^a\s+([\d.]+)",
        "e": r"^e\s+([\d.]+)",
        "peri": r"Peri\.\s+([\d.]+)",
        "node": r"Node\s+([\d.]+)",
        "incl": r"Incl\.\s+([\d.]+)",
        "H": r"\bH\s+([\d.]+)",
        "G": r"\bG\s+([\d.]+)",
        "earth_moid": r"Earth MOID\s*=\s*([\d.]+)",
        "q": r"^q\s+([\d.]+)",
        "period": r"^P\s+([\d.]+)",
        "U": r"\bU\s+(\d+)",
    }

    for key, pat in patterns.items():
        m = re.search(pat, text, re.MULTILINE)
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
    or just as a line with the designation.  Also handles comets like
    "COMET  C/2026 A1 (MAPS)" and interstellar objects like
    "COMET  3I/ATLAS".
    """
    # Look for **DESIGNATION** pattern (bold markers)
    m = re.search(r"\*\*(\d{4}\s+\w+\d*)\*\*", pre_text)
    if m:
        return m.group(1).strip()

    # Look for a line that's just a designation (centered)
    for line in pre_text.split("\n")[:30]:
        stripped = line.strip().strip("*")
        # Asteroid: "2026 CE3"
        m2 = re.match(r"^(\d{4}\s+[A-Z]{1,2}\d*)$", stripped.strip())
        if m2:
            return m2.group(1)
        # Comet: "COMET  C/2026 A1 (MAPS)" or "COMET P/2025 B2 (Smith)"
        m2 = re.match(
            r"^(?:COMET\s+)?([CPD]/\d{4}\s+\w+(?:\s+\(.*?\))?)$",
            stripped.strip())
        if m2:
            return m2.group(1).strip()
        # Interstellar object: "COMET  3I/ATLAS" or "COMET  1I/'Oumuamua"
        m2 = re.match(
            r"^(?:COMET\s+)?(\d+I/\S+(?:\s+\(.*?\))?)$",
            stripped.strip())
        if m2:
            return m2.group(1).strip()

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

    # A discovery MPEC must contain observations; if none are present
    # but we have a designation, it's a recovery announcement.
    if (mpec_type == "discovery"
            and designation
            and "observations" not in sections):
        mpec_type = "recovery"

    # Parse orbital elements if present
    orbital_elements = {}
    if "orbital_elements" in sections:
        orbital_elements = _parse_orbital_elements(sections["orbital_elements"])

    # Extract MPEC date from header
    date = ""
    header = sections.get("header", "")
    m = re.search(
        r"Issued\s+(\d{4})\s+(\w+)\.?\s+(\d{1,2}),?\s*(\d{2}:\d{2})?\s*UT",
        header)
    if m:
        year, month_str, day = m.group(1), m.group(2)[:3], m.group(3)
        date = f"{year} {month_str} {day}"
        if m.group(4):
            date += f", {m.group(4)} UT"

    mpec_url = f"{_MPC_BASE}{path}" if path else ""

    # Count observations and compute arc from observation lines
    obs_text = sections.get("observations", "")
    n_obs = 0
    obs_dates = []
    for line in obs_text.split("\n"):
        if len(line) >= 80:
            n_obs += 1
            date_part = line[15:32].strip()
            m_d = re.match(r"(\d{4})\s+(\d{2})\s+([\d.]+)", date_part)
            if m_d:
                try:
                    obs_dates.append(
                        float(m_d.group(1)) * 10000
                        + float(m_d.group(2)) * 100
                        + float(m_d.group(3)))
                except ValueError:
                    pass

    arc_days = None
    if obs_dates and len(obs_dates) >= 2:
        # Approximate arc in days from first to last obs
        first = obs_dates[0]
        last = obs_dates[-1]
        y1, r1 = divmod(first, 10000)
        m1, d1 = divmod(r1, 100)
        y2, r2 = divmod(last, 10000)
        m2, d2 = divmod(r2, 100)
        arc_days = (y2 - y1) * 365.25 + (m2 - m1) * 30.44 + (d2 - d1)

    # Fallback: extract obs count and arc from orbital elements summary line
    # e.g. "From 8 observations 1977 Aug. 21-1978 Jan. 6, mean residual 0".71."
    if n_obs == 0:
        oe_raw = sections.get("orbital_elements", "")
        m_from = re.search(
            r"From\s+(\d+)\s+observations?\s+"
            r"(\d{4})\s+(\w+)\.?\s+([\d.]+)"
            r"(?:\s*-\s*(\d{4})\s+(\w+)\.?\s+([\d.]+))?",
            oe_raw)
        if m_from:
            n_obs = int(m_from.group(1))
            _months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                        "May": 5, "Jun": 6, "June": 6, "Jul": 7,
                        "July": 7, "Aug": 8, "Sep": 9, "Sept": 9,
                        "Oct": 10, "Nov": 11, "Dec": 12}
            if m_from.group(5):
                y1 = int(m_from.group(2))
                mo1 = _months.get(m_from.group(3), 1)
                d1 = float(m_from.group(4))
                y2 = int(m_from.group(5))
                mo2 = _months.get(m_from.group(6), 1)
                d2 = float(m_from.group(7))
                arc_days = ((y2 - y1) * 365.25
                            + (mo2 - mo1) * 30.44
                            + (d2 - d1))

    # For recovery MPECs, extract the "comparison with prediction" block
    # from observer_details.  It starts with "First and last observations"
    # and runs to the end of that section's content.
    comparison = ""
    obs_details = sections.get("observer_details", "")
    comp_match = re.search(
        r"^(First and last observations.*)", obs_details,
        re.MULTILINE | re.DOTALL)
    if comp_match:
        comparison = comp_match.group(1).strip()
        # Remove from observer_details
        obs_details = obs_details[:comp_match.start()].rstrip()
        sections["observer_details"] = obs_details

    # Extract copyright/author line from raw pre_text.  Modern MPECs have
    # "(C) Copyright" or "Copyright"; older ones have an author name on
    # the left and "M.P.E.C. YYYY-XXX" on the right.  Strip it from the
    # ephemeris content so it isn't duplicated.
    copyright_line = ""
    ephemeris_text = sections.get("ephemeris", "")
    for raw_line in reversed(pre_text.split("\n")):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if ("Copyright" in stripped or "(C)" in stripped
                or "M.P.E.C." in stripped):
            copyright_line = stripped
        break  # only check the last non-blank line

    # Remove copyright line from ephemeris if present
    if copyright_line and ephemeris_text:
        eph_lines = ephemeris_text.split("\n")
        cleaned = [ln for ln in eph_lines if copyright_line not in ln]
        ephemeris_text = "\n".join(cleaned).rstrip()

    return {
        "mpec_id": mpec_id,
        "date": date,
        "title": title,
        "designation": designation,
        "type": mpec_type,
        "header": sections.get("header", ""),
        "observations": obs_text,
        "n_obs": n_obs,
        "arc_days": round(arc_days, 1) if arc_days is not None else None,
        "orbital_elements": orbital_elements,
        "orbital_elements_raw": sections.get("orbital_elements", ""),
        "residuals": sections.get("residuals", ""),
        "ephemeris": ephemeris_text,
        "observers": sections.get("observer_details", ""),
        "comparison": comparison,
        "copyright": copyright_line,
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
    Includes all MPEC types (discovery, recovery, editorial).
    Cached for 15 minutes.
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
        nav_path = os.path.join(cache_dir, safe_name.replace(".txt", ".nav"))
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                pre_text = f.read()
            # Extract mpec_id and title from cached content
            page_parser = _MPECPageParser()
            # We stored just the pre text; reconstruct minimal parse
            title_line = ""
            for line in pre_text.split("\n")[:30]:
                s = line.strip().strip("*")
                # Asteroid: "2026 CE3"
                m = re.match(r"^(\d{4}\s+[A-Z]{1,2}\d*)$", s.strip())
                if m:
                    title_line = m.group(1)
                    break
                # Comet: "COMET  C/2026 A1 (MAPS)" or "C/2026 A1 (Name)"
                m = re.match(
                    r"^(?:COMET\s+)?([CPD]/\d{4}\s+\w+(?:\s+\(.*?\))?)$",
                    s.strip())
                if m:
                    title_line = m.group(1).strip()
                    break
            mpec_m = re.search(r"M\.P\.E\.C\.\s+(\S+)", pre_text)
            mpec_id = mpec_m.group(1) if mpec_m else ""
            result = parse_mpec_content(
                pre_text, mpec_id=mpec_id, title=title_line, path=mpec_path)
            # Load cached nav links; backfill from web if missing.
            # If the cached nav has no next_path, re-fetch: a newer
            # MPEC may have been published since the cache was written.
            _nav_cached_prev = ""
            _nav_cached_next = ""
            if os.path.exists(nav_path):
                try:
                    with open(nav_path, "r") as f:
                        lines = f.read().split("\n")
                    _nav_cached_prev = lines[0] if len(lines) > 0 else ""
                    _nav_cached_next = lines[1] if len(lines) > 1 else ""
                except OSError:
                    pass
            if _nav_cached_next:
                # Cache is complete (has both prev and next)
                result["prev_path"] = _nav_cached_prev
                result["next_path"] = _nav_cached_next
            else:
                # No next_path cached — re-fetch to check for newer MPEC
                try:
                    html_text = _fetch_url(f"{_MPC_BASE}{mpec_path}")
                    nav_parser = _MPECPageParser()
                    nav_parser.feed(html_text)
                    result["prev_path"] = nav_parser.prev_path
                    result["next_path"] = nav_parser.next_path
                    if nav_parser.prev_path or nav_parser.next_path:
                        with open(nav_path, "w") as f:
                            f.write(f"{nav_parser.prev_path}\n"
                                    f"{nav_parser.next_path}\n")
                except Exception:
                    # Fall back to whatever was cached
                    result["prev_path"] = _nav_cached_prev
                    result["next_path"] = _nav_cached_next
            return result

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
        nav_path = os.path.join(cache_dir, safe_name.replace(".txt", ".nav"))
        try:
            with open(cache_path, "w") as f:
                f.write(pre_text)
        except OSError:
            pass
        # Cache nav links (prev/next MPEC paths)
        if page_parser.prev_path or page_parser.next_path:
            try:
                with open(nav_path, "w") as f:
                    f.write(f"{page_parser.prev_path}\n{page_parser.next_path}\n")
            except OSError:
                pass

    result = parse_mpec_content(pre_text, mpec_id=mpec_id, title=title,
                                path=mpec_path)
    result["prev_path"] = page_parser.prev_path
    result["next_path"] = page_parser.next_path
    return result


# ---------------------------------------------------------------------------
# Designation → MPEC lookup via MPC API
# ---------------------------------------------------------------------------

_API_URL = "https://data.minorplanetcenter.net/api/mpecs"
_desig_lookup_cache = {}


def lookup_mpecs_by_designation(designation):
    """Look up MPECs associated with a designation via the MPC API.

    Args:
        designation: Any designation format the API accepts (e.g.
            "2026 CY1", "K24Y04R", "433", "C/2026 A1").

    Returns:
        List of dicts sorted by pubdate ascending (earliest first):
        [{"mpec_id": "MPEC 2026-C89", "path": "/mpec/K26/K26C89.html",
          "title": "2026 CY1", "date": "2026 Feb 13"}, ...]
        Returns [] for no matches.
    """
    query = designation.strip()
    if not query:
        return []
    key = query.upper()
    if key in _desig_lookup_cache:
        return _desig_lookup_cache[key]

    payload = json.dumps([query]).encode("utf-8")
    req = urllib.request.Request(
        _API_URL,
        data=payload,
        method="GET",
        headers={"User-Agent": "CSS-MPC-Toolkit/1.0",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"MPEC API lookup error for {query!r}: {e}")
        return []

    # Response is a dict keyed by designation; collect all MPEC entries
    items = []
    if isinstance(raw, dict):
        for desig_key, mpec_list in raw.items():
            if isinstance(mpec_list, list):
                items.extend(mpec_list)
    elif isinstance(raw, list):
        items = raw

    results = []
    for item in items:
        link = item.get("link", "")
        # Strip domain prefix to get path
        path = re.sub(r"^https?://[^/]+", "", link)
        raw_id = item.get("fullname", "")
        mpec_id = f"MPEC {raw_id}" if raw_id else ""
        title = item.get("title", "")
        pubdate = item.get("pubdate", "")
        # Parse RFC 2822 date for reliable sorting; format for display
        parsed = email.utils.parsedate(pubdate)
        sort_key = time.mktime(parsed) if parsed else 0
        display_date = time.strftime("%Y %b %d", parsed) if parsed else pubdate
        results.append({
            "mpec_id": mpec_id,
            "path": path,
            "title": title,
            "date": display_date,
            "_sort": sort_key,
        })

    # Sort by pubdate ascending (earliest first)
    results.sort(key=lambda r: r["_sort"])
    _desig_lookup_cache[key] = results
    return results
