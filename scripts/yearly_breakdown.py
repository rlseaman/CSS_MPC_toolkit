#!/usr/bin/env python3
"""
Parse the MPC YearlyBreakdown page and summarize NEO discovery stats
by station code.

Source: https://www.minorplanetcenter.net/iau/lists/YearlyBreakdown.html

The page lists per-year PHA and NEA discoveries by observatory code in a
fixed-width <pre> block.  Each year block has lines like:

  Code   # PHA       # NEA           #Atens          #Apollos        #Amors
                  All 1km H<22    All 1km H<22    All 1km H<22    All 1km H<22
   F51       5    87/   1/  16     9/   0/   0    49/   0/   7    29/   1/   9

This script downloads the page, parses all year blocks, and prints a
summary table of stations meeting a minimum discovery threshold.

Usage:
    python scripts/yearly_breakdown.py             # default: >= 50 NEOs
    python scripts/yearly_breakdown.py --min 20    # lower threshold
    python scripts/yearly_breakdown.py --all       # no threshold
    python scripts/yearly_breakdown.py --project    # roll up by project
    python scripts/yearly_breakdown.py --sort pha   # sort by PHAs
    python scripts/yearly_breakdown.py --sort first  # sort by first year
    python scripts/yearly_breakdown.py --current     # show current-year activity
"""

import argparse
import re
import sys
import urllib.request
from collections import defaultdict

URL = "https://www.minorplanetcenter.net/iau/lists/YearlyBreakdown.html"

# ---------------------------------------------------------------------------
# Project groupings — mirrors STATION_TO_PROJECT in app/discovery_stats.py
# ---------------------------------------------------------------------------
STATION_TO_PROJECT = {
    "704": "LINEAR", "G45": "LINEAR", "P07": "LINEAR",
    "566": "NEAT", "608": "NEAT", "644": "NEAT",
    "691": "Spacewatch", "291": "Spacewatch",
    "699": "LONEOS",
    "703": "Catalina Survey", "E12": "Catalina Survey",
    "G96": "Catalina Survey",
    "I52": "Catalina Survey", "V06": "Catalina Survey",
    "G84": "Catalina Survey",
    "V00": "Bok NEO Survey",
    "F51": "Pan-STARRS", "F52": "Pan-STARRS",
    "C51": "NEOWISE",
    "T05": "ATLAS", "T07": "ATLAS", "T08": "ATLAS",
    "T03": "ATLAS", "M22": "ATLAS", "W68": "ATLAS", "R17": "ATLAS",
    "X05": "Rubin/LSST",
    "I41": "Other-US", "U68": "Other-US", "U74": "Other-US",
    "W84": "Other-US",
    "675": "Palomar Mountain",
    "693": "Catalina Survey",
}

# Brief project labels (max 10 chars) for the station-level table
PROJECT_SHORT = {
    "LINEAR": "LINEAR",
    "NEAT": "NEAT",
    "Spacewatch": "Spacewatch",
    "LONEOS": "LONEOS",
    "Catalina Survey": "CSS",
    "Bok NEO Survey": "Bok",
    "Pan-STARRS": "Pan-STARRS",
    "NEOWISE": "NEOWISE",
    "ATLAS": "ATLAS",
    "Rubin/LSST": "Rubin/LSST",
    "Other-US": "Other-US",
    "Independent Surveys": "Independnt",
    "Palomar Mountain": "Palomar",
    "Historical": "Historical",
}

PROJECT_ORDER = [
    "LINEAR", "NEAT", "Spacewatch", "LONEOS",
    "Catalina Survey", "Catalina Follow-up",
    "Pan-STARRS", "NEOWISE", "ATLAS",
    "Bok NEO Survey", "Rubin/LSST", "Other-US",
    "Palomar Mountain", "Independent Surveys",
    "Historical", "Others",
]

# ---------------------------------------------------------------------------
# Station names from MPC ObsCodes
# (https://minorplanetcenter.net/iau/lists/ObsCodesF.html)
# Covers all codes that have appeared in YearlyBreakdown as of 2026-03-28.
# New codes will show as blank until this dict is updated.
# ---------------------------------------------------------------------------
STATION_NAMES = {
    "010": "Caussols",
    "012": "Uccle",
    "024": "Heidelberg-Konigstuhl",
    "026": "Berne-Zimmerwald",
    "029": "Hamburg-Bergedorf",
    "033": "Karl Schwarzschild Obs., Tautenburg",
    "045": "Vienna",
    "046": "Klet Observatory",
    "049": "Uppsala-Kvistaberg",
    "069": "Baldone",
    "071": "NAO Rozhen, Smolyan",
    "074": "Boyden Observatory, Bloemfontein",
    "078": "Johannesburg",
    "095": "Crimea-Nauchnyi",
    "104": "San Marcello Pistoiese",
    "106": "Crni Vrh",
    "113": "Volkssternwarte Drebach",
    "114": "Engelhardt Obs., Zelenchukskaya",
    "118": "Modra Observatory",
    "119": "Abastuman",
    "120": "Visnjan",
    "152": "Moletai Astronomical Observatory",
    "185": "Obs. Astronomique Jurassien-Vicques",
    "198": "Wildberg",
    "221": "IAS Observatory, Hakos",
    "240": "Herrenberg Sternwarte",
    "246": "Klet Observatory-KLENOT",
    "247": "Roving Observer",
    "290": "Mt. Graham-VATT",
    "291": "Spacewatch II",
    "300": "Bisei Spaceguard Center-BATTeRS",
    "304": "Las Campanas Observatory",
    "309": "Cerro Paranal",
    "327": "Peking Obs., Xinglong Station",
    "333": "Desert Eagle Observatory",
    "372": "Geisei",
    "381": "Tokyo-Kiso",
    "385": "Nihondaira Observatory",
    "391": "Sendai Obs., Ayashi Station",
    "399": "Kushiro",
    "400": "Kitami",
    "402": "Dynic Astronomical Observatory",
    "408": "Nyukasa",
    "411": "Oizumi",
    "413": "Siding Spring Observatory",
    "428": "Reedy Creek",
    "446": "Kingsnake Observatory, Seguin",
    "461": "Univ. of Szeged, Piszkesteto",
    "493": "Calar Alto",
    "500": "Geocentric",
    "511": "Haute Provence",
    "548": "Berlin",
    "557": "Ondrejov",
    "561": "Piszkesteto Stn. (Konkoly)",
    "566": "Haleakala-NEAT/GEODSS",
    "568": "Maunakea",
    "595": "Farra d'Isonzo",
    "599": "Campo Imperatore-CINEOS",
    "608": "Haleakala-AMOS (NEAT)",
    "620": "Obs. Astronomico de Mallorca",
    "621": "Bergisch Gladbach",
    "644": "Palomar Mountain/NEAT",
    "661": "Rothney Astrophysical Obs., Priddis",
    "662": "Lick Observatory, Mount Hamilton",
    "673": "Table Mountain Obs., Wrightwood",
    "675": "Palomar Mountain",
    "678": "Fountain Hills",
    "683": "Goodricke-Pigott Obs., Tucson",
    "688": "Lowell Obs., Anderson Mesa",
    "690": "Lowell Observatory, Flagstaff",
    "691": "Spacewatch",
    "693": "Catalina Station, Tucson",
    "695": "Kitt Peak",
    "699": "LONEOS",
    "703": "Catalina Sky Survey",
    "704": "LINEAR",
    "705": "Apache Point",
    "734": "Farpoint Observatory, Eskridge",
    "760": "Goethe Link Obs., Brooklyn",
    "805": "Santiago-Cerro El Roble",
    "807": "Cerro Tololo, La Serena",
    "808": "El Leoncito",
    "809": "ESO, La Silla",
    "823": "Fitchburg",
    "858": "Tebbutt Observatory, Edgewood",
    "883": "Shizuoka",
    "888": "Gekko",
    "896": "Yatsugatake South Base",
    "910": "Caussols-ODAS",
    "926": "Tenagra II Obs., Nogales",
    "941": "Obs. Pla D'Arguines",
    "950": "La Palma",
    "A44": "Altschwendt",
    "A50": "Andrushivka Astronomical Obs.",
    "A77": "Obs. Chante-Perdrix, Dauban",
    "B01": "Taunus Observatory, Frankfurt",
    "B74": "Santa Maria de Montmagastrell",
    "C41": "MASTER-II, Kislovodsk",
    "C51": "WISE/NEOWISE",
    "C55": "Kepler",
    "C57": "TESS",
    "C85": "Obs. Cala d'Hort, Ibiza",
    "C94": "MASTER-II, Tunka",
    "C95": "SATINO Remote Obs., Haute Provence",
    "D00": "ASC-Kislovodsk Observatory",
    "D29": "Purple Mountain Obs., XuYi (CNEOST)",
    "D35": "Lulin Observatory",
    "E12": "Siding Spring Survey (CSS)",
    "F51": "Pan-STARRS 1, Haleakala",
    "F52": "Pan-STARRS 2, Haleakala",
    "F84": "Hibiscus Obs., Punaauia",
    "G03": "Capricornus Obs., Csokako",
    "G32": "Elena Remote Obs., San Pedro de Atacama",
    "G37": "Lowell Discovery Telescope",
    "G45": "Space Surveillance Telescope, Atom",
    "G78": "Desert Wanderer Obs., El Centro",
    "G84": "CSS SkyCenter, Mt. Lemmon",
    "G89": "Kachina Obs., Flagstaff",
    "G92": "Jarnac Obs., Vail",
    "G96": "Mt. Lemmon Survey (CSS)",
    "H15": "ISON-NM Observatory, Mayhill",
    "H21": "Astronomical Research Obs., Westfield",
    "H27": "Moonglow Obs., Warrensburg",
    "H36": "Sandlot Obs., Scranton",
    "H55": "Astronomical Research Obs., Charleston",
    "I08": "Alianza S4, Cerro Burek",
    "I16": "IAA-AI Atacama, San Pedro de Atacama",
    "I41": "Palomar Mountain-ZTF",
    "I52": "Steward Obs., Mt. Lemmon",
    "I93": "St Pardon de Conques",
    "J04": "ESA Optical Ground Station, Tenerife",
    "J13": "La Palma-Liverpool Telescope",
    "J43": "Oukaimeden Obs., Marrakech",
    "J75": "OAM Observatory, La Sagra",
    "K19": "PASTIS Obs., Banon",
    "K88": "GINOP-KHK, Piszkesteto",
    "K95": "MASTER-SAAO, Sutherland",
    "L51": "MARGO, Nauchnyi",
    "L87": "Moonbase South Obs., Hakos",
    "L96": "ISON-Byurakan Observatory",
    "M11": "Novaastro Obs., Banon",
    "M22": "ATLAS South Africa, Sutherland",
    "M57": "Wide-field Mufara Telescope, Isnello",
    "N56": "JIST, Ali, Tibet",
    "N86": "Xingming Obs.-KATS, Nanshan",
    "N87": "Nanshan Station, Xinjiang Obs.",
    "N89": "Xingming Obs. #2, Nanshan",
    "N94": "Altay Astronomical Observatory",
    "O18": "WFST, Lenghu",
    "O75": "ISON-Hureltogoot Observatory",
    "P07": "Space Surveillance Telescope, HEH",
    "Q57": "KMTNet-SSO",
    "Q60": "ISON-SSO, Siding Spring",
    "Q62": "iTelescope, Siding Spring",
    "Q66": "Siding Spring-Janess-G, JAXA",
    "R17": "ATLAS-TDO",
    "T05": "ATLAS-HKO, Haleakala",
    "T08": "ATLAS-MLO, Mauna Loa",
    "T09": "Subaru Telescope, Maunakea",
    "T14": "CFHT, Maunakea",
    "U63": "Burnt Tree Hill Obs., Cle Elum",
    "U68": "SynTrack, Auberry",
    "U74": "SynTrack 2, Auberry",
    "V00": "Kitt Peak-Bok",
    "V03": "Big Water",
    "V06": "CSS-Kuiper",
    "V11": "Saguaro Obs., Tucson",
    "W16": "Pleasant Groves Observatory",
    "W57": "ESA TBT, La Silla",
    "W68": "ATLAS Chile, Rio Hurtado",
    "W76": "CHILESCOPE, Rio Hurtado",
    "W84": "Cerro Tololo-DECam",
    "W86": "Cerro Tololo-LCO B",
    "W93": "KMTNet-CTIO",
    "W94": "MAPS, San Pedro de Atacama",
    "W95": "Obs. Panameno, San Pedro de Atacama",
    "X05": "Rubin Observatory (LSST)",
    "X07": "iTelescope Deep Sky Chile",
    "X19": "Santel Obs., El Leoncito",
    "X74": "Obs. Campo dos Amarais",
    "Y00": "SONEAR, Oliveira",
    "Y01": "SONEAR 2, Belo Horizonte",
    "Y05": "SONEAR Wykrota-CEAMIG",
    "Y66": "Two-meter Twin Telescope, TTT2",
    "Y89": "Proxima Centauri Obs., Valdin",
    "Z84": "Calar Alto-Schmidt",
}

# ---------------------------------------------------------------------------
# DB NEO discovery counts from mpc_sbn (q <= 1.30 definition)
# Generated 2026-03-29 via sql/station_discovery_profile.sql
# ---------------------------------------------------------------------------
DB_NEO_COUNTS = {
    "G96": 13153, "F51": 9050, "F52": 4135, "703": 3886, "704": 2477,
    "V00": 1257, "691": 861, "T08": 570, "C51": 481, "T05": 470,
    "E12": 458, "I41": 408, "W84": 371, "K88": 341, "W94": 337,
    "U68": 331, "644": 298, "699": 289, "G45": 193, "W68": 168,
    "L51": 153, "M22": 152, "675": 148, "608": 110, "W16": 98,
    "291": 91, "J75": 91, "568": 69, "P07": 68, "381": 57,
    "L87": 56, "D29": 55, "413": 53, "Y00": 43, "X05": 39,
    "O18": 36, "566": 31, "N94": 31, "809": 29, "X74": 29,
    "106": 27, "J04": 24, "K19": 22, "I52": 19, "J43": 18,
    "095": 16, "T09": 16, "309": 13, "R17": 13, "950": 12,
    "U74": 12, "926": 11, "Z84": 9, "Q66": 9, "033": 8,
    "461": 8, "807": 7, "599": 7, "010": 7, "H15": 7,
    "W93": 7, "N56": 7, "327": 6, "683": 6, "I08": 6,
    "G03": 6, "W57": 6, "333": 5, "012": 5, "805": 5,
    "T14": 5, "Q60": 5, "695": 4, "046": 4, "024": 4,
    "411": 4, "760": 4, "621": 4, "910": 4, "428": 4,
    "114": 4, "Y05": 4, "662": 4, "247": 4, "O75": 4,
    "688": 3, "493": 3, "198": 3, "A50": 3, "Q62": 3,
    "246": 3, "026": 3, "I16": 3, "I93": 3, "500": 3,
    "Y89": 3, "M11": 3, "400": 2, "300": 2, "557": 2,
    "078": 2, "H21": 2, "808": 2, "941": 2, "690": 2,
    "673": 2, "408": 2, "152": 2, "H36": 2, "029": 2,
    "402": 2, "118": 2, "C85": 2, "N87": 2, "G37": 2,
    "J13": 2, "N86": 2, "872": 2, "C94": 2, "G78": 2,
    "249": 2, "U63": 2, "M57": 2, "705": 1, "A77": 1,
    "120": 1, "399": 1, "G32": 1, "372": 1, "D35": 1,
    "734": 1, "678": 1, "711": 1, "104": 1, "B74": 1,
    "511": 1, "049": 1, "595": 1, "G92": 1, "290": 1,
    "A44": 1, "185": 1, "F84": 1, "H55": 1, "B01": 1,
    "385": 1, "888": 1, "620": 1, "G89": 1, "446": 1,
    "754": 1, "069": 1, "693": 1, "113": 1, "C95": 1,
    "323": 1, "D00": 1, "W86": 1, "119": 1, "896": 1,
    "561": 1, "W76": 1, "897": 1, "304": 1, "V03": 1,
    "045": 1, "074": 1, "858": 1, "N89": 1, "468": 1,
    "K95": 1, "V06": 1, "X19": 1, "W95": 1, "240": 1,
    "X07": 1, "C57": 1, "I47": 1, "823": 1, "548": 1,
    "883": 1, "C55": 1, "V11": 1, "221": 1, "Z17": 1,
    "L32": 1, "Y66": 1, "661": 1, "L96": 1, "Y01": 1,
    "Q57": 1, "H27": 1,
}


def fetch_page(url=URL):
    """Download the YearlyBreakdown page and return the text."""
    req = urllib.request.Request(url, headers={"User-Agent": "CSS-MPC-Toolkit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("iso-8859-1")


def parse_pre_block(html):
    """Extract the <pre>...</pre> content."""
    m = re.search(r"<pre>(.*?)</pre>", html, re.DOTALL)
    if not m:
        print("ERROR: could not find <pre> block", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def parse_data_line(line):
    """Parse a station data line.

    Returns (code, pha, nea_all, nea_1km, nea_h22,
             aten_all, aten_1km, aten_h22,
             apollo_all, apollo_1km, apollo_h22,
             amor_all, amor_1km, amor_h22)
    or None if the line doesn't match.
    """
    line = line.rstrip()
    if not line or line.startswith("Code") or line.startswith(" " * 10):
        return None

    m = re.match(
        r"\s*(\S+)\s+"          # station code
        r"(\d+)\s+"             # PHA count
        r"(\d+)/\s*(\d+)/\s*(\d+)\s+"    # NEA all/1km/H<22
        r"(\d+)/\s*(\d+)/\s*(\d+)\s+"    # Aten all/1km/H<22
        r"(\d+)/\s*(\d+)/\s*(\d+)\s+"    # Apollo all/1km/H<22
        r"(\d+)/\s*(\d+)/\s*(\d+)",      # Amor all/1km/H<22
        line,
    )
    if not m:
        return None

    code = m.group(1)
    nums = [int(m.group(i)) for i in range(2, 15)]
    return (code, *nums)


_ACCUM_KEYS = [
    "pha", "nea_all", "nea_1km", "nea_h22",
    "aten", "aten_1km", "aten_h22",
    "apollo", "apollo_1km", "apollo_h22",
    "amor", "amor_1km", "amor_h22",
]


def _new_accum():
    d = {k: 0 for k in _ACCUM_KEYS}
    d["first_year"] = None
    d["last_year"] = None
    d["yearly_neos"] = {}  # year_str -> nea_all count
    return d


def _year_sort_key(y):
    """Sort key for year labels: '<1971' sorts before all numeric years."""
    if y is None:
        return ""
    if y.startswith("<"):
        return "0000"
    return y


def _add_accum(target, source):
    """Add source counts into target."""
    for k in _ACCUM_KEYS:
        target[k] += source[k]
    # Merge yearly_neos
    for y, n in source.get("yearly_neos", {}).items():
        target.setdefault("yearly_neos", {})[y] = (
            target.get("yearly_neos", {}).get(y, 0) + n)
    # Merge year ranges
    if source["first_year"] is not None:
        if (target["first_year"] is None
                or _year_sort_key(source["first_year"])
                < _year_sort_key(target["first_year"])):
            target["first_year"] = source["first_year"]
    if source["last_year"] is not None:
        if (target["last_year"] is None
                or _year_sort_key(source["last_year"])
                > _year_sort_key(target["last_year"])):
            target["last_year"] = source["last_year"]


def _year_label(raw):
    """Shorten 'Before 1971' for display."""
    return "<1971" if raw == "Before 1971" else raw


def parse_yearly_breakdown(html, since=None):
    """Parse all year blocks and accumulate per-station totals.

    If since is set (e.g. 2000), only years >= since are accumulated.
    "Before 1971" is treated as year 0 for filtering purposes.

    Returns dict[code] -> accum dict with counts and first/last year.
    """
    pre = parse_pre_block(html)
    stations = defaultdict(_new_accum)

    current_year = None
    skip_block = False
    for line in pre.split("\n"):
        # Year header: <b>2026</b> or <b>Before 1971</b>
        ym = re.match(r"\s*<b>(.*?)</b>", line)
        if ym:
            current_year = ym.group(1).strip()
            if since is not None:
                try:
                    skip_block = int(current_year) < since
                except ValueError:
                    # "Before 1971" — skip if since > 0
                    skip_block = True
            continue

        if skip_block:
            continue

        # Skip Total lines and header lines
        stripped = line.strip()
        if stripped.startswith("Total") or stripped.startswith("Code") or not stripped:
            continue
        if "All" in stripped and "1km" in stripped:
            continue

        parsed = parse_data_line(line)
        if parsed is None:
            continue

        code = parsed[0]
        s = stations[code]
        s["pha"] += parsed[1]
        s["nea_all"] += parsed[2]
        s["nea_1km"] += parsed[3]
        s["nea_h22"] += parsed[4]
        s["aten"] += parsed[5]
        s["aten_1km"] += parsed[6]
        s["aten_h22"] += parsed[7]
        s["apollo"] += parsed[8]
        s["apollo_1km"] += parsed[9]
        s["apollo_h22"] += parsed[10]
        s["amor"] += parsed[11]
        s["amor_1km"] += parsed[12]
        s["amor_h22"] += parsed[13]

        if parsed[2] > 0 and current_year:
            label = _year_label(current_year)
            s["yearly_neos"][current_year] = parsed[2]
            if s["last_year"] is None:
                s["last_year"] = label
            s["first_year"] = label

    return dict(stations)


def _is_independent(station_data):
    """A station qualifies as Independent Survey if it had >10 NEO
    discoveries in the current year or either of the two previous years.

    The 'current year' is the most recent year in the YearlyBreakdown data.
    """
    yn = station_data.get("yearly_neos", {})
    if not yn:
        return False
    # Find the most recent year in the entire dataset (already parsed
    # in reverse chronological order, so max of numeric years)
    numeric_years = [int(y) for y in yn if y.isdigit()]
    if not numeric_years:
        return False
    # We use a fixed window: check the three most recent calendar years
    # present in the full dataset.  The caller passes the max year.
    return False  # placeholder — actual check is in _classify_independent


def _classify_independent(stations):
    """Return set of station codes that qualify as Independent Surveys.

    Criteria: >10 NEO discoveries in the current year or either of the
    two previous years.  Only unmapped stations (not in STATION_TO_PROJECT)
    are eligible.
    """
    # Find the most recent year across all stations
    max_year = 0
    for s in stations.values():
        for y in s.get("yearly_neos", {}):
            if y.isdigit():
                max_year = max(max_year, int(y))
    if max_year == 0:
        return set()

    window = [str(max_year), str(max_year - 1), str(max_year - 2)]
    independent = set()
    for code, s in stations.items():
        if code in STATION_TO_PROJECT:
            continue
        yn = s.get("yearly_neos", {})
        if any(yn.get(y, 0) > 10 for y in window):
            independent.add(code)
    return independent


def roll_up_projects(stations):
    """Aggregate station-level data into project-level totals.

    Returns list of (label, accum_dict, station_codes_list) sorted by
    PROJECT_ORDER, then by NEO count for unlisted projects.
    """
    independent_codes = _classify_independent(stations)
    projects = {}  # label -> (accum, [codes])

    for code, s in stations.items():
        proj = STATION_TO_PROJECT.get(code)
        if proj is None:
            proj = ("Independent Surveys" if code in independent_codes
                    else "Others")
        if proj not in projects:
            projects[proj] = (_new_accum(), [])
        accum, codes = projects[proj]
        _add_accum(accum, s)
        codes.append(code)

    # Split "Others" into "Historical" (last year <= 1995) and "Others"
    if "Others" in projects:
        others_accum, others_codes = projects.pop("Others")
        hist_accum = _new_accum()
        hist_codes = []
        remain_accum = _new_accum()
        remain_codes = []
        for code in others_codes:
            s = stations[code]
            last = s.get("last_year") or ""
            # "<1971" and any 4-digit year <= "1995" count as historical
            is_hist = (last.startswith("<")
                       or (last.isdigit() and int(last) <= 1999))
            if is_hist:
                _add_accum(hist_accum, s)
                hist_codes.append(code)
            else:
                _add_accum(remain_accum, s)
                remain_codes.append(code)
        if hist_codes:
            projects["Historical"] = (hist_accum, hist_codes)
        if remain_codes:
            projects["Others"] = (remain_accum, remain_codes)

    return [(proj, accum, sorted(codes))
            for proj, (accum, codes) in projects.items()]


# Sort key functions: return (primary, tiebreaker) where tiebreaker is
# -nea_all so ties in the primary key still sort by total NEOs desc.
SORT_KEYS = {
    "total": lambda d: (-d["nea_all"],),
    "pha":   lambda d: (-d["pha"], -d["nea_all"]),
    "1km":   lambda d: (-d["nea_1km"], -d["nea_all"]),
    "140m":  lambda d: (-d["nea_h22"], -d["nea_all"]),
    "first": lambda d: (_year_sort_key(d["first_year"] or "9999"),
                        -d["nea_all"]),
    "last":  lambda d: (_year_sort_key(d["last_year"] or "0000"),
                        -d["nea_all"]),
}


def _detect_current_year(stations):
    """Detect the current year from the parsed data.

    Returns the most recent numeric year that appears in any station's
    yearly_neos.  This is derived from the web page, not the calendar,
    so it tracks the MPC's publishing cadence.
    """
    max_year = 0
    for s in stations.values():
        for y in s.get("yearly_neos", {}):
            if y.isdigit():
                max_year = max(max_year, int(y))
    return max_year


def _compute_current_change(data, current_year):
    """Compute current-year counts and year-over-year change indicators.

    Returns (current_year, prev_year, doy, results) where results is a
    list of (count_str, change_str) tuples, one per row.
    Change is "+" if projected current-year rate exceeds previous year
    by >15%, "-" if below by >15%, blank if within 15% or insufficient
    data (both years < 5 combined).
    """
    from datetime import date
    today = date.today()
    doy = today.timetuple().tm_yday
    frac = doy / 365.0

    cur = str(current_year)
    prev = str(current_year - 1)

    results = []
    for d in data:
        yn = d.get("yearly_neos", {})
        n_cur = yn.get(cur, 0)
        n_prev = yn.get(prev, 0)

        n_cur_str = str(n_cur) if n_cur > 0 else ""

        # Need enough data in both years to be meaningful
        if n_prev + n_cur < 5:
            results.append((n_cur_str, ""))
            continue

        if n_prev == 0:
            change = "+" if n_cur > 0 else ""
            results.append((n_cur_str, change))
            continue

        projected = n_cur / frac
        ratio = projected / n_prev
        if ratio > 1.15:
            change = "+"
        elif ratio < 0.85:
            change = "-"
        else:
            change = ""
        results.append((n_cur_str, change))
    return doy, results


def _db_compare_indicator(yb_count, db_count):
    """Compare DB count to YearlyBreakdown count.

    ">" means DB has more than YB, "<" means DB has less.
    ">>" / "<<" for >5%, ">>>" / "<<<" for >25%.
    Blank if difference < 0.5% (functionally equivalent).
    "0" if DB has no record.

    Double/triple arrows require minimum absolute differences
    (3 for >>, 5 for >>>) to avoid misleading indicators on
    small counts.
    """
    if db_count is None:
        return "0"
    if db_count == 0 and yb_count > 0:
        return "0"
    if yb_count == db_count:
        return ""
    diff = db_count - yb_count  # positive = DB has more
    absdiff = abs(diff)
    if yb_count == 0:
        return ">>>" if diff >= 5 else ">>" if diff >= 3 else ">"
    pct = absdiff / yb_count
    # Below 1%: functionally equivalent
    if pct < 0.01:
        return ""
    ratio = db_count / yb_count
    if diff > 0:
        if ratio > 1.25 and absdiff >= 5:
            return ">>>"
        if ratio > 1.05 and absdiff >= 3:
            return ">>"
        return ">"
    else:
        if ratio < 0.75 and absdiff >= 5:
            return "<<<"
        if ratio < 0.95 and absdiff >= 3:
            return "<<"
        return "<"


def print_table(stations, min_neos=50, by_project=False, sort_by="total",
                sort_explicit=False, show_current=False, db_compare=False):
    """Print a formatted summary table."""
    col_keys = ["nea_all", "pha", "nea_1km", "nea_h22",
                "aten", "apollo", "amor"]
    col_headers = ["NEOs", "PHAs", "1km+", "H<22",
                   "Aten", "Apol", "Amor"]

    sort_fn = SORT_KEYS.get(sort_by, SORT_KEYS["total"])

    if by_project:
        rolled = roll_up_projects(stations)
        rows = [(proj, accum, codes)
                for proj, accum, codes in rolled
                if accum["nea_all"] >= min_neos]
        if not rows:
            print(f"No projects with >= {min_neos} NEO discoveries.")
            return

        rows.sort(key=lambda r: sort_fn(r[1]))

        labels = [proj for proj, _, _ in rows]
        data = [accum for _, accum, _ in rows]
        right_strs = []
        for _, _, codes in rows:
            if len(codes) > 10:
                right_strs.append(f"{len(codes)} MPC codes")
            else:
                right_strs.append(", ".join(codes))
        right_header = "Stations"
    else:
        filtered = [
            (code, s)
            for code, s in stations.items()
            if s["nea_all"] >= min_neos
        ]

        if min_neos == 0 and not sort_explicit:
            # --all default: group by project (descending project total),
            # then by descending station NEOs within each project
            rolled = roll_up_projects(stations)
            proj_totals = {proj: accum["nea_all"]
                           for proj, accum, _ in rolled}
            indep_codes = _classify_independent(stations)
            def _proj_station_key(r):
                code, s = r
                proj = STATION_TO_PROJECT.get(code)
                if proj is None:
                    if code in indep_codes:
                        proj = "Independent Surveys"
                    else:
                        last = s.get("last_year") or ""
                        is_hist = (last.startswith("<")
                                   or (last.isdigit() and int(last) <= 1999))
                        proj = "Historical" if is_hist else "Others"
                return (-proj_totals.get(proj, 0), -s["nea_all"])
            filtered.sort(key=_proj_station_key)
        else:
            filtered.sort(key=lambda r: sort_fn(r[1]))

        if not filtered:
            print(f"No stations with >= {min_neos} NEO discoveries.")
            return

        labels = [code for code, _ in filtered]
        data = [s for _, s in filtered]
        right_strs = [STATION_NAMES.get(code, "") for code in labels]
        right_header = "Name"

    # DB comparison column
    if db_compare:
        if by_project:
            # Sum DB counts for constituent stations of each project
            db_strs = []
            for _, _, codes in rows:
                db_total = sum(DB_NEO_COUNTS.get(c, 0) for c in codes)
                yb_total = sum(
                    stations.get(c, {}).get("nea_all", 0) for c in codes)
                db_strs.append(_db_compare_indicator(yb_total, db_total))
        else:
            db_strs = []
            for code, d in zip(labels, data):
                db_n = DB_NEO_COUNTS.get(code)
                db_strs.append(_db_compare_indicator(d["nea_all"], db_n))
    else:
        db_strs = None

    # Compute totals
    totals = {k: sum(d[k] for d in data) for k in col_keys}

    # Column widths
    label_header = "Project" if by_project else "Code"
    label_width = max(len(label_header), max(len(l) for l in labels))

    # Project-short column (station view only)
    if not by_project:
        independent_codes = _classify_independent(stations)
        def _proj_short(code):
            proj = STATION_TO_PROJECT.get(code)
            if proj:
                return PROJECT_SHORT.get(proj, "")
            if code in independent_codes:
                return PROJECT_SHORT.get("Independent Surveys", "Independnt")
            # Unmapped: check if Historical based on last year
            s = stations.get(code, {})
            last = s.get("last_year") or ""
            is_hist = (last.startswith("<")
                       or (last.isdigit() and int(last) <= 1999))
            if is_hist:
                return PROJECT_SHORT.get("Historical", "Historical")
            return ""  # Others — blank
        proj_strs = [_proj_short(code) for code in labels]
        proj_w = max(10, max((len(p) for p in proj_strs), default=10))
    else:
        proj_strs = None
        proj_w = 0

    num_widths = []
    for i, k in enumerate(col_keys):
        w = max(len(col_headers[i]), len(str(totals[k])))
        num_widths.append(w)

    all_firsts = [d["first_year"] or "" for d in data]
    all_lasts = [d["last_year"] or "" for d in data]
    first_w = max(5, max(len(y) for y in all_firsts))
    last_w = max(4, max(len(y) for y in all_lasts))

    # Current-year / Chng columns
    if show_current:
        current_year = _detect_current_year(stations)
        doy, changes = _compute_current_change(data, current_year)
        cur_strs = [c[0] for c in changes]
        chng_strs = [c[1] for c in changes]
        cur_header = str(current_year)
        cur_w = max(len(cur_header),
                    max((len(s) for s in cur_strs), default=4))
    else:
        cur_strs = None
        chng_strs = None
        current_year = None
        doy = None

    def fmt_row(label, proj_short, nums, db_ind="", first="", last="",
                n_cur="", chng="", right=""):
        parts = [f"{label:>{label_width}}"]
        if proj_strs is not None:
            parts.append(f"{proj_short:<{proj_w}}")
        # First numeric column (NEOs), then DB indicator, then rest
        parts.append(f"{nums[0]:>{num_widths[0]}}")
        if db_compare:
            parts.append(f"{db_ind:>3}")
        for v, w in zip(nums[1:], num_widths[1:]):
            parts.append(f"{v:>{w}}")
        parts.append(f"{first:>{first_w}}")
        parts.append(f"{last:>{last_w}}")
        if show_current:
            parts.append(f"{n_cur:>{cur_w}}")
            parts.append(f"{chng:>4}")
        parts.append(f"  {right}")
        return "  ".join(parts)

    # Header and separator
    hdr = fmt_row(label_header,
                  "Proj" if proj_strs is not None else "",
                  col_headers,
                  db_ind="DB" if db_compare else "",
                  first="First", last="Last",
                  n_cur=cur_header if show_current else "",
                  chng="Chng" if show_current else "",
                  right=right_header)
    sep_test = fmt_row(label_header,
                       "Proj" if proj_strs is not None else "",
                       col_headers,
                       db_ind="---" if db_compare else "",
                       first="First", last="Last",
                       n_cur="----" if show_current else "",
                       chng="----" if show_current else "",
                       right="")
    sep_len = len(sep_test.rstrip())
    print(hdr)
    print("-" * sep_len)

    pshorts = proj_strs or [""] * len(labels)
    if cur_strs is None:
        cur_strs = [""] * len(labels)
        chng_strs = [""] * len(labels)
    if db_strs is None:
        db_strs = [""] * len(labels)
    for label, d, ps, dbi, nc, chng, rstr in zip(
            labels, data, pshorts, db_strs,
            cur_strs, chng_strs, right_strs):
        nums = [d[k] for k in col_keys]
        first = d["first_year"] or ""
        last = d["last_year"] or ""
        print(fmt_row(label, ps, nums, db_ind=dbi, first=first, last=last,
                      n_cur=nc, chng=chng, right=rstr))

    print("-" * sep_len)
    total_ps = "" if proj_strs is None else ""
    if show_current:
        total_cur = sum(
            d.get("yearly_neos", {}).get(str(current_year), 0)
            for d in data)
        total_cur_str = str(total_cur) if total_cur > 0 else ""
    else:
        total_cur_str = ""
    print(fmt_row("Total", total_ps,
                  [totals[k] for k in col_keys],
                  first="", last="",
                  n_cur=total_cur_str, chng="", right=""))
    kind = "projects" if by_project else "stations"
    if sort_by != "total":
        sort_label = sort_by
    elif min_neos == 0 and not sort_explicit and not by_project:
        sort_label = "project, then NEOs"
    else:
        sort_label = "total NEOs"

    if by_project:
        # Find the window years used for Independent classification
        max_year = 0
        for s in stations.values():
            for y in s.get("yearly_neos", {}):
                if y.isdigit():
                    max_year = max(max_year, int(y))
        print(f"\n{len(labels)} {kind}")
        print(f"\nIndependent Survey: any unaffiliated station with >10 NEO"
              f" discoveries in {max_year}, {max_year-1}, or {max_year-2}.")
        print(f"Historical: unaffiliated stations whose last discovery"
              f" was 1999 or earlier.")
    else:
        threshold_str = ("" if min_neos == 0
                         else f" with >= {min_neos} NEO discoveries")
        print(f"\n{len(labels)} {kind}{threshold_str}"
              f" (sorted by {sort_label})")

    if show_current and current_year:
        prev_year = current_year - 1
        print(f"\nChng: \"+\" if projected {current_year} rate exceeds"
              f" {prev_year} by >15%,"
              f" \"-\" if below by >15% (day {doy}/365).")

    if db_compare:
        # Stations in DB but not in YB, filtered by current threshold
        yb_stns = set(stations.keys())
        db_only = sorted(
            c for c in DB_NEO_COUNTS
            if c not in yb_stns
            and DB_NEO_COUNTS[c] >= min_neos
            and DB_NEO_COUNTS[c] > 0)
        if db_only:
            codes_str = ", ".join(
                f"{c}({DB_NEO_COUNTS[c]})" for c in db_only)
            print(f"\nIn DB but missing from YB: {codes_str}")
        print(f"\nDB: mpc_sbn vs YB."
              f" \">\" more in DB, \">>\" >5%, \">>>\" >25%."
              f" \"<\" less, \"0\" not in DB. Blank if <1%.")


def write_markdown(filename, stations, min_neos=50, by_project=False,
                   sort_by="total", sort_explicit=False,
                   show_current=False, db_compare=False):
    """Write the table as a Markdown file with pipe tables.

    Captures the same output as print_table but formatted for Markdown.
    Convert to PDF with: python scripts/md2pdf.py <file.md>
    """
    import io
    from contextlib import redirect_stdout
    from datetime import datetime, timezone

    buf = io.StringIO()
    with redirect_stdout(buf):
        print_table(stations, min_neos=min_neos, by_project=by_project,
                    sort_by=sort_by, sort_explicit=sort_explicit,
                    show_current=show_current, db_compare=db_compare)
    raw = buf.getvalue()

    # Parse the fixed-width output into a markdown pipe table
    lines = raw.split("\n")
    md_lines = []

    # Title
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = "NEO Discovery Statistics by Project" if by_project \
            else "NEO Discovery Statistics by Station"
    md_lines.append(f"# {title}")
    md_lines.append("")
    md_lines.append(f"Source: MPC YearlyBreakdown | Generated: {now}")
    md_lines.append("")
    md_lines.append("```")
    for line in lines:
        md_lines.append(line)
    md_lines.append("```")

    with open(filename, "w") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"Wrote {filename}")
    print(f"Convert to PDF: python scripts/md2pdf.py {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Parse MPC YearlyBreakdown and summarize NEO "
                    "discovery stats by station or project.")
    parser.add_argument("--min", type=int, default=50,
                        help="Minimum total NEO discoveries to display "
                             "(default: 50)")
    parser.add_argument("--all", action="store_true",
                        help="Show all stations/projects (no minimum)")
    parser.add_argument("--project", action="store_true",
                        help="Roll up stations into project groups")
    parser.add_argument("--sort", default="total",
                        choices=["total", "pha", "1km", "140m",
                                 "first", "last"],
                        help="Sort order (default: total)")
    parser.add_argument("--current", action="store_true",
                        help="Add current-year count and year-over-year "
                             "change indicator columns")
    parser.add_argument("--db_compare", action="store_true",
                        help="Add DB column comparing YearlyBreakdown "
                             "to mpc_sbn database counts")
    parser.add_argument("--md", default=None, metavar="FILE",
                        help="Write output as Markdown file "
                             "(convert to PDF with scripts/md2pdf.py)")
    parser.add_argument("--since", type=int, default=None,
                        help="Only accumulate discoveries from this "
                             "year onward (e.g. --since 2000)")
    parser.add_argument("--url", default=URL,
                        help="Override the URL to fetch")
    args = parser.parse_args()

    threshold = 0 if args.all else args.min

    print(f"Fetching {args.url} ...")
    html = fetch_page(args.url)
    since_msg = f" (since {args.since})" if args.since else ""
    print(f"Parsing yearly breakdown data{since_msg}...")
    stations = parse_yearly_breakdown(html, since=args.since)
    # Detect if --sort was explicitly passed on the command line
    sort_explicit = any(a.startswith("--sort") for a in sys.argv[1:])

    print(f"Found {len(stations)} station codes.\n")

    common_args = dict(
        min_neos=threshold, by_project=args.project,
        sort_by=args.sort, sort_explicit=sort_explicit,
        show_current=args.current, db_compare=args.db_compare,
    )
    print_table(stations, **common_args)

    if args.md:
        write_markdown(args.md, stations, **common_args)


if __name__ == "__main__":
    main()
