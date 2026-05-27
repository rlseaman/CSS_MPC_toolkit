"""JPL Horizons ephemeris client for finding-chart predictions.

Fetches predicted (RA, Dec) and apparent V magnitude for a minor-planet
target from the SSD Horizons web API, parses the SOE..EOE block, and
caches results on disk per `(object, window, step, observer)` with a
1-week TTL.  Hand-rolled to avoid pulling astroquery into the
dashboard's dependency set.

API docs:  https://ssd-api.jpl.nasa.gov/doc/horizons.html
Endpoint:  https://ssd.jpl.nasa.gov/api/horizons.api
Format:    JSON wrapper around a plain-text result block; quantities
           1 (R.A./Dec ICRF) and 9 (APmag + S-brt) requested.

Object resolution follows Horizons' convention:
- Numbered minor planet: `COMMAND='<permid>;'` (e.g. `'99942;'`)
- Provisional only:      `COMMAND='DES=<provid>;'` (e.g. `'DES=2024 PT5;'`)
The trailing semicolon prevents Horizons from interactively prompting
for ambiguous matches.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from typing import Optional

import numpy as np
import pandas as pd
import requests


_HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
_CACHE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "app", ".horizons_cache"))
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_TTL_SEC = 7 * 24 * 3600

# Be a good citizen to Horizons.  A single user toggling Predictions triggers
# one request (then disk-cached for a week), so this cap is invisible — it only
# serialises bursts.  Paired with a failure cooldown so an outage or an
# unresolved designation isn't re-fetched on every finding-chart re-render
# (slider drags, overlay toggles).
_THROTTLE_INTERVAL = 0.5            # 2 req/s ceiling to ssd.jpl.nasa.gov
_throttle_lock = threading.Lock()
_throttle_next = 0.0

_NEG_TTL_SEC = 120.0               # cooldown after a failure / empty result
_neg_cache: dict[str, float] = {}  # cache-key hash -> cooldown expiry ts


def _throttle() -> None:
    """Block until the Horizons rate budget allows another request."""
    global _throttle_next
    with _throttle_lock:
        now = time.monotonic()
        slot = max(now, _throttle_next)
        _throttle_next = slot + _THROTTLE_INTERVAL
        wait = slot - now
    if wait > 0:
        time.sleep(wait)

# One ephemeris row, QUANTITIES='1,9,23' format:
#    " 2026-May-17 00:00     06 17 10.46 +21 18 00.8   21.684   3.551   38.2942 /T"
#  year-monthAbbr-day  hr:mn   rah ram ras   ±decd decm decs   APmag  S-brt
#    S-O-T (solar elongation, deg) /r-flag (T=trailing sun, L=leading)
_DATE_LINE = re.compile(
    r"^\s*(\d{4})-([A-Za-z]+)-(\d{2})\s+(\d{2}):(\d{2})\s+"
    r"(\d{1,2})\s+(\d{2})\s+([\d.]+)\s+"
    r"([+-]\d{1,2})\s+(\d{2})\s+([\d.]+)"
    r"(?:\s+(\S+))?"   # APmag (may be 'n.a.')
    r"(?:\s+(\S+))?"   # S-brt (may be 'n.a.')
    r"(?:\s+(\S+))?"   # S-O-T (solar elongation, may be 'n.a.')
    r"(?:\s+/[TL])?"   # trailing/leading flag (discarded)
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _object_command(permid: Optional[str], provid: Optional[str]) -> str:
    if permid:
        return f"'{str(permid).strip()};'"
    if provid:
        return f"'DES={str(provid).strip()};'"
    raise ValueError("permid or provid required")


def _cache_key(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()
                       ).hexdigest()[:12]


def _parse_response(text: str) -> pd.DataFrame:
    cols = ["obstime", "ra", "dec", "v_pred", "solar_elong"]
    soe = text.find("$$SOE")
    eoe = text.find("$$EOE")
    if soe < 0 or eoe < 0:
        return pd.DataFrame(columns=cols)
    rows = []
    for line in text[soe + 5:eoe].splitlines():
        m = _DATE_LINE.match(line)
        if not m:
            continue
        (y, mon, d, hr, mn, rh, rm, rs, dd, dm, ds,
         vmag, _sbrt, sot) = m.groups()
        if mon not in _MONTHS:
            continue
        obstime = pd.Timestamp(
            year=int(y), month=_MONTHS[mon], day=int(d),
            hour=int(hr), minute=int(mn))
        ra = 15.0 * (int(rh) + int(rm) / 60.0 + float(rs) / 3600.0)
        sign = -1.0 if dd.startswith("-") else 1.0
        dec = sign * (abs(int(dd)) + int(dm) / 60.0 + float(ds) / 3600.0)
        v = (float(vmag) if vmag and vmag not in ("n.a.", "N.A.")
             else np.nan)
        e = (float(sot) if sot and sot not in ("n.a.", "N.A.")
             else np.nan)
        rows.append((obstime, ra, dec, v, e))
    return pd.DataFrame(rows, columns=cols)


def fetch_predictions(
    *,
    permid: Optional[str] = None,
    provid: Optional[str] = None,
    t_start: pd.Timestamp,
    t_stop: pd.Timestamp,
    step: str = "1 d",
    observer: str = "500",
    timeout: float = 15.0,
) -> pd.DataFrame:
    """Return Horizons ephemeris over [t_start, t_stop].

    Disk-cache hit returns in < 5 ms; miss is a 2–5 s network
    round-trip.  Caller is responsible for handling
    `requests.HTTPError` (e.g. when Horizons is down or doesn't
    recognise the designation) by falling back to the
    observed-only chart.
    """
    cmd = _object_command(permid, provid)
    t_start_s = pd.Timestamp(t_start).strftime("%Y-%m-%d")
    t_stop_s = pd.Timestamp(t_stop).strftime("%Y-%m-%d")
    # QUANTITIES is part of the cache key so a future schema change
    # (adding/dropping columns) invalidates stale parquet files
    # automatically.
    h = _cache_key(cmd, t_start_s, t_stop_s, step, observer, "1,9,23")
    cache_path = os.path.join(_CACHE_DIR, f"{h}.parquet")
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < _CACHE_TTL_SEC:
            return pd.read_parquet(cache_path)

    # Failure cooldown: a recent outage / unresolved designation suppresses
    # re-fetching for _NEG_TTL_SEC.  Return an empty frame, which the caller
    # already renders as the observed-only chart.
    neg_exp = _neg_cache.get(h)
    if neg_exp is not None and time.time() < neg_exp:
        return pd.DataFrame(columns=["obstime", "ra", "dec", "v_pred",
                                     "solar_elong"])

    params = {
        "format": "json",
        "COMMAND": cmd,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": f"'{observer}'",
        "START_TIME": f"'{t_start_s}'",
        "STOP_TIME": f"'{t_stop_s}'",
        "STEP_SIZE": f"'{step}'",
        "QUANTITIES": "'1,9,23'",
    }
    _throttle()
    try:
        r = requests.get(_HORIZONS_URL, params=params, timeout=timeout)
        r.raise_for_status()
    except Exception:
        # Down / rate-limited / unresolved: start a cooldown, then let the
        # caller fall back to the observed-only chart (+ status-line note).
        _neg_cache[h] = time.time() + _NEG_TTL_SEC
        raise
    df = _parse_response(r.json().get("result", ""))
    if len(df):
        df.to_parquet(cache_path)
        _neg_cache.pop(h, None)        # success clears any prior cooldown
    else:
        # 200 OK but no ephemeris rows (designation Horizons can't resolve) —
        # cool down so we don't re-request it on every interaction.
        _neg_cache[h] = time.time() + _NEG_TTL_SEC
    return df
