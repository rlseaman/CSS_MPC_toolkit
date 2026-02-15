"""
External API clients for NEO data enrichment.

Thin wrappers for JPL SBDB/Sentry, NEOfixer, and ESA NEOCC APIs.
All functions return dicts (or None on failure) with short TTL caching
since orbits update as data centers reprocess after MPEC publication.

Usage:
    from lib.api_clients import fetch_sbdb, fetch_sentry, fetch_neofixer_orbit
"""

import json
import time
import urllib.request
import urllib.parse

# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 300  # 5 minutes
_cache = {}  # key -> (timestamp, value)


def _cached(key, func):
    """Return cached value if fresh, otherwise call func and cache result."""
    now = time.time()
    if key in _cache:
        ts, val = _cache[key]
        if now - ts < _CACHE_TTL:
            return val
    try:
        val = func()
    except Exception as e:
        print(f"API error [{key}]: {e}")
        return None
    _cache[key] = (now, val)
    return val


def _get_json(url, timeout=10):
    """Fetch URL and parse as JSON."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "CSS-MPC-Toolkit/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _get_text(url, timeout=10):
    """Fetch URL and return as text, or None on 404."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "CSS-MPC-Toolkit/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# ---------------------------------------------------------------------------
# JPL SBDB
# ---------------------------------------------------------------------------

def fetch_sbdb(designation):
    """Fetch structured data from JPL Small-Body Database.

    Args:
        designation: Object designation (e.g. "2026 CE3" or packed "K26C03E")

    Returns:
        dict with keys: orbit_class, condition_code, data_arc, n_obs, moid,
        t_jup, H, G, elements, close_approaches, or None on failure.
    """
    encoded = urllib.parse.quote(designation)
    url = (f"https://ssd-api.jpl.nasa.gov/sbdb.api"
           f"?sstr={encoded}&phys-par=1&ca-data=1&vi-data=1")

    def _fetch():
        data = _get_json(url)
        if not data or "object" not in data:
            return None
        obj = data.get("object", {})
        orbit = data.get("orbit", {})
        elements = orbit.get("elements", [])
        phys = data.get("phys_par", [])

        # Parse elements into a flat dict
        elem_dict = {}
        for el in elements:
            name = el.get("name", "")
            val = el.get("value", "")
            try:
                elem_dict[name] = float(val)
            except (ValueError, TypeError):
                elem_dict[name] = val

        # Parse physical parameters
        phys_dict = {}
        for p in phys:
            name = p.get("name", "")
            val = p.get("value", "")
            try:
                phys_dict[name] = float(val)
            except (ValueError, TypeError):
                phys_dict[name] = val

        # Close approaches
        ca_data = data.get("ca_data", [])
        ca_fields = data.get("ca_fields", [])
        close_approaches = []
        if ca_data and ca_fields:
            for row in ca_data[:10]:  # limit to 10 closest
                ca = dict(zip(ca_fields, row))
                close_approaches.append(ca)

        # Sentry/vi data
        vi_data = data.get("vi_data", None)

        orbit_class = orbit.get("class", {})

        result = {
            "fullname": obj.get("fullname", ""),
            "orbit_class": orbit_class.get("name", ""),
            "orbit_class_short": orbit_class.get("short_name", ""),
            "condition_code": orbit.get("condition_code", ""),
            "data_arc": orbit.get("data_arc", ""),
            "n_obs": orbit.get("n_obs_used", ""),
            "moid": elem_dict.get("moid", None),
            "moid_jup": elem_dict.get("moid_jup", None),
            "t_jup": orbit.get("t_jup", ""),
            "H": phys_dict.get("H", elem_dict.get("H", None)),
            "G": phys_dict.get("G", None),
            "elements": elem_dict,
            "close_approaches": close_approaches,
            "vi_data": vi_data,
            "source": "JPL SBDB",
        }
        return result

    return _cached(f"sbdb:{designation}", _fetch)


# ---------------------------------------------------------------------------
# JPL Sentry (impact risk)
# ---------------------------------------------------------------------------

def fetch_sentry(designation):
    """Fetch Sentry impact risk data from JPL.

    Args:
        designation: Object designation (e.g. "2024 YR4")

    Returns:
        dict with impact probability, Palermo/Torino scales, or None if
        not on watchlist or on error.
    """
    encoded = urllib.parse.quote(designation)
    url = f"https://ssd-api.jpl.nasa.gov/sentry.api?des={encoded}"

    def _fetch():
        try:
            data = _get_json(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"on_list": False}
            raise
        if not data or "summary" not in data:
            return {"on_list": False}
        summary = data["summary"]
        return {
            "on_list": True,
            "designation": summary.get("des", designation),
            "ip": summary.get("ip", ""),        # cumulative impact prob
            "ps_cum": summary.get("ps_cum", ""),  # Palermo scale cumul
            "ps_max": summary.get("ps_max", ""),  # Palermo scale max
            "ts_max": summary.get("ts_max", ""),  # Torino scale max
            "energy": summary.get("energy", ""),
            "n_imp": summary.get("n_imp", ""),   # number of VIs
            "v_inf": summary.get("v_inf", ""),
            "h": summary.get("h", ""),
            "diameter": summary.get("diameter", ""),
            "last_obs": summary.get("last_obs", ""),
            "source": "JPL Sentry",
        }

    return _cached(f"sentry:{designation}", _fetch)


# ---------------------------------------------------------------------------
# NEOfixer (CSS service — independent Find_Orb solutions)
# ---------------------------------------------------------------------------

_NEOFIXER_BASE = "https://neofixerapi.arizona.edu"


def fetch_neofixer_orbit(packed_desig):
    """Fetch orbit from NEOfixer API.

    Args:
        packed_desig: MPC packed designation (e.g. "K26C03E")

    Returns:
        dict with orbital elements, MOIDs, H, U, RMS, n_obs, or None.
    """
    encoded = urllib.parse.quote(packed_desig.strip())
    url = f"{_NEOFIXER_BASE}/orbit/?object={encoded}"

    def _fetch():
        data = _get_json(url)
        if not data:
            return None
        # JSON-RPC wrapper: result.objects.{packed}
        packed_clean = packed_desig.strip()
        if isinstance(data, dict) and "result" in data:
            objects = data["result"].get("objects", {})
            obj = objects.get(packed_clean)
            if not obj:
                return None
        elif isinstance(data, list) and data:
            obj = data[0]
        elif isinstance(data, dict):
            obj = data
        else:
            return None

        elem = obj.get("elements", {})
        moids = elem.get("MOIDs", {})
        obs_info = obj.get("observations", {})

        return {
            "elements": {
                "a": _float(elem.get("a")),
                "e": _float(elem.get("e")),
                "i": _float(elem.get("i")),
                "node": _float(elem.get("asc_node")),
                "peri": _float(elem.get("arg_per")),
                "M": _float(elem.get("M")),
                "q": _float(elem.get("q")),
                "Q": _float(elem.get("Q")),
                "epoch": elem.get("epoch_iso", ""),
                "P": _float(elem.get("P")),
            },
            "H": _float(elem.get("H")),
            "G": _float(elem.get("G")),
            "U": _float(elem.get("U")),
            "rms": _float(elem.get("rms_residual")),
            "weighted_rms": _float(elem.get("weighted_rms_residual")),
            "n_obs": obs_info.get("count", ""),
            "n_used": obs_info.get("used", ""),
            "arc_start": obs_info.get("earliest_used iso", ""),
            "arc_end": obs_info.get("latest_used iso", ""),
            "earth_moid": _float(moids.get("Earth")),
            "venus_moid": _float(moids.get("Venus")),
            "mars_moid": _float(moids.get("Mars")),
            "jupiter_moid": _float(moids.get("Jupiter")),
            "neo_prob": _float(obj.get("elements", {}).get("p_NEO")),
            "orbit_class": "",  # NEOfixer doesn't classify
            "source": "NEOfixer (Find_Orb)",
            "_raw": obj,
        }

    return _cached(f"neofixer_orbit:{packed_desig}", _fetch)


def fetch_neofixer_targets(site, packed_desig):
    """Fetch targeting/priority data from NEOfixer.

    The targets endpoint returns ALL targets for a site.  We search for
    the specific object by packed designation in the result list.

    Args:
        site: MPC station code (e.g. "I52")
        packed_desig: MPC packed designation

    Returns:
        dict with score, priority, vmag, rate, etc., or None.
    """
    encoded = urllib.parse.quote(packed_desig.strip())
    url = (f"{_NEOFIXER_BASE}/targets/"
           f"?site={site}&objects={encoded}")

    def _fetch():
        data = _get_json(url)
        if not data:
            return None
        # JSON-RPC wrapper
        result = data.get("result", data) if isinstance(data, dict) else data
        # The result contains parallel arrays: ids[], scores[], etc.
        # Or it may be a list of dicts.  Find our object.
        ids = result.get("ids", []) if isinstance(result, dict) else []
        packed_clean = packed_desig.strip()
        if packed_clean in ids:
            idx = ids.index(packed_clean)
            def _get_at(key):
                arr = result.get(key, [])
                return arr[idx] if idx < len(arr) else None
            return {
                "score": _float(_get_at("scores")),
                "priority": _get_at("priorities") or "",
                "cost": _float(_get_at("costs")),
                "importance": _float(_get_at("importances")),
                "urgency": _float(_get_at("urgencies")),
                "vmag": _float(_get_at("vmags")),
                "rate": _float(_get_at("rates")),
                "unc": _float(_get_at("uncs")),
                "elong": _float(_get_at("elongs")),
                "source": "NEOfixer targets",
            }
        return None

    return _cached(f"neofixer_targets:{site}:{packed_desig}", _fetch)


def fetch_neofixer_ephem(site, packed_desig, num=1728):
    """Fetch ephemeris from NEOfixer.

    Args:
        site: MPC station code (e.g. "I52")
        packed_desig: MPC packed designation
        num: Number of ephemeris entries (default 1728 = 18 days @ 15min)

    Returns:
        dict with metadata + list of ephem entries, or None.
        Each entry has: JD, ISO_time, RA, Dec, alt, az, mag, ExpT,
        motion_rate, motionPA, elong, SkyBr, RGB, delta, etc.
    """
    encoded = urllib.parse.quote(packed_desig.strip())
    url = (f"{_NEOFIXER_BASE}/ephem/"
           f"?site={site}&object={encoded}&num={num}")

    def _fetch():
        data = _get_json(url)
        if not data:
            return None
        # JSON-RPC wrapper
        if isinstance(data, dict) and "result" in data:
            result = data["result"]
            return {
                "obscode": result.get("obscode", site),
                "packed": result.get("packed", packed_desig),
                "start_iso": result.get("start iso", ""),
                "n_steps": result.get("n_steps", 0),
                "step_days": result.get("step", 0),
                "entries": result.get("entries", []),
            }
        if isinstance(data, list):
            return {"entries": data}
        return None

    return _cached(f"neofixer_ephem:{site}:{packed_desig}:{num}", _fetch)


# ---------------------------------------------------------------------------
# ESA NEOCC (Near-Earth Object Coordination Centre)
# ---------------------------------------------------------------------------

_NEOCC_BASE = "https://neo.ssa.esa.int/PSDB-portlet/download"


def fetch_neocc_risk(designation):
    """Fetch NEOCC risk assessment.

    Args:
        designation: Designation without spaces (e.g. "2026CE3")

    Returns:
        Raw risk text (fixed-width), or None if not listed.
    """
    desig_nospace = designation.replace(" ", "")
    encoded = urllib.parse.quote(desig_nospace)
    url = f"{_NEOCC_BASE}?file={encoded}.risk"

    def _fetch():
        return _get_text(url)

    return _cached(f"neocc_risk:{desig_nospace}", _fetch)


def fetch_neocc_physical(designation):
    """Fetch NEOCC physical properties.

    Args:
        designation: Designation without spaces (e.g. "2026CE3")

    Returns:
        Raw text, or None if not available.
    """
    desig_nospace = designation.replace(" ", "")
    encoded = urllib.parse.quote(desig_nospace)
    url = f"{_NEOCC_BASE}?file={encoded}.phypro"

    def _fetch():
        return _get_text(url)

    return _cached(f"neocc_physical:{desig_nospace}", _fetch)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _float(val):
    """Safely convert to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def clear_cache():
    """Clear all cached API responses."""
    _cache.clear()
