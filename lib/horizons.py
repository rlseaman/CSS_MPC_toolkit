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

# One ephemeris row, QUANTITIES='1,9' format:
#    " 2026-May-17 00:00     06 17 10.46 +21 18 00.8   21.684   3.551"
#  year-monthAbbr-day  hr:mn   rah ram ras   ±decd decm decs   APmag  S-brt
_DATE_LINE = re.compile(
    r"^\s*(\d{4})-([A-Za-z]+)-(\d{2})\s+(\d{2}):(\d{2})\s+"
    r"(\d{1,2})\s+(\d{2})\s+([\d.]+)\s+"
    r"([+-]\d{1,2})\s+(\d{2})\s+([\d.]+)"
    r"(?:\s+(\S+))?"   # APmag (may be 'n.a.')
    r"(?:\s+(\S+))?"   # S-brt (may be 'n.a.')
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
    soe = text.find("$$SOE")
    eoe = text.find("$$EOE")
    if soe < 0 or eoe < 0:
        return pd.DataFrame(columns=["obstime", "ra", "dec", "v_pred"])
    rows = []
    for line in text[soe + 5:eoe].splitlines():
        m = _DATE_LINE.match(line)
        if not m:
            continue
        y, mon, d, hr, mn, rh, rm, rs, dd, dm, ds, vmag, _ = m.groups()
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
        rows.append((obstime, ra, dec, v))
    return pd.DataFrame(rows, columns=["obstime", "ra", "dec", "v_pred"])


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
    h = _cache_key(cmd, t_start_s, t_stop_s, step, observer)
    cache_path = os.path.join(_CACHE_DIR, f"{h}.parquet")
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < _CACHE_TTL_SEC:
            return pd.read_parquet(cache_path)

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
        "QUANTITIES": "'1,9'",
    }
    r = requests.get(_HORIZONS_URL, params=params, timeout=timeout)
    r.raise_for_status()
    df = _parse_response(r.json().get("result", ""))
    if len(df):
        df.to_parquet(cache_path)
    return df
