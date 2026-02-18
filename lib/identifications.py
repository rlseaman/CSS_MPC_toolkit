"""
Designation resolution via current_identifications and numbered_identifications.

Resolves an MPEC designation to its current primary designation, permanent
number, IAU name, and orbit classification.  Uses lazy per-designation
caching so each designation is looked up at most once per server process
lifetime.

Usage:
    from lib.identifications import resolve_designation

    info = resolve_designation("1977 QQ5")
    # {'mpec_desig': '1977 QQ5', 'primary_desig': '1977 QQ5',
    #  'permid': '7977', 'iau_name': None,
    #  'is_secondary': False, 'is_numbered': True,
    #  'orbit_class': 'Mars-crossing'}
"""

from mpc_designation import pack, detect_format

from lib.db import connect
from lib.orbit_classes import classify_from_elements, long_name

# Module-level cache: original designation string -> result dict
_cache = {}


def _empty_result(designation):
    return {
        "mpec_desig": designation,
        "primary_desig": None,
        "permid": None,
        "iau_name": None,
        "is_secondary": False,
        "is_numbered": False,
        "orbit_class": None,
    }


def resolve_designation(designation):
    """Resolve a designation to its current identity.

    Returns dict with keys:
        mpec_desig     — the input designation (always set)
        primary_desig  — current primary provisional designation (or None)
        permid         — permanent MPC number as string (or None)
        iau_name       — IAU name like "Eros" (or None)
        is_secondary   — True if the input is a secondary (merged) designation
        is_numbered    — True if the object has a permanent number
        orbit_class    — long name from ORBIT_TYPES (e.g., "Mars-crossing") or None
    """
    if designation in _cache:
        return _cache[designation]

    result = _empty_result(designation)

    if not designation or not designation.strip():
        _cache[designation] = result
        return result

    try:
        fmt = detect_format(designation)
    except Exception:
        _cache[designation] = result
        return result

    is_permanent = fmt.get("type") == "permanent"

    if is_permanent:
        result = _resolve_by_permid(designation, result)
    else:
        try:
            packed = pack(designation)
        except Exception:
            _cache[designation] = result
            return result
        result = _resolve_by_packed(designation, packed, result)

    # Only cache when the DB query succeeded.  If the DB was
    # unreachable, _db_ok won't be set — don't cache so the next
    # request retries.
    if result.pop("_db_ok", False):
        _cache[designation] = result
    return result


def _lookup_orbit_class(cur, packed_primary):
    """Query mpc_orbits for orbit classification by packed primary designation.

    Falls back to classify_from_elements() when orbit_type_int is NULL.

    Returns long_name string (e.g., "Mars-crossing") or None.
    """
    if not packed_primary:
        return None
    cur.execute("""
        SELECT orbit_type_int,
               q::double precision,
               e::double precision,
               i::double precision
        FROM mpc_orbits
        WHERE packed_primary_provisional_designation = %s
        LIMIT 1
    """, (packed_primary,))
    row = cur.fetchone()
    if not row:
        return None
    oti, q, e, i = row
    if oti is not None:
        return long_name(oti)
    # Fallback: classify from elements
    if q is not None and e is not None:
        a = q / (1.0 - e) if e < 1.0 else None
        fallback_oti = classify_from_elements(a, e, i, q)
        if fallback_oti is not None:
            return long_name(fallback_oti)
    return None


def _resolve_by_permid(designation, result):
    """Resolve a permanent number (e.g., '433') via numbered_identifications."""
    try:
        with connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT permid, iau_name,
                       unpacked_primary_provisional_designation
                FROM numbered_identifications
                WHERE permid = %s
            """, (designation,))
            row = cur.fetchone()

            if row:
                result["permid"] = row[0]
                result["iau_name"] = row[1]
                result["primary_desig"] = row[2]
                result["is_numbered"] = True
                result["is_secondary"] = False
                # Look up orbit class using packed primary from ni
                cur.execute("""
                    SELECT packed_primary_provisional_designation
                    FROM numbered_identifications
                    WHERE permid = %s
                """, (designation,))
                ni_packed = cur.fetchone()
                if ni_packed:
                    result["orbit_class"] = _lookup_orbit_class(
                        cur, ni_packed[0])

            result["_db_ok"] = True
            cur.close()
    except Exception:
        pass

    return result


def _resolve_by_packed(designation, packed, result):
    """Resolve a packed provisional designation through the identification chain.

    Sets result["_db_ok"] = True when the DB query succeeded (even if
    no rows were found), so callers can distinguish "not found" from
    "DB error".
    """
    try:
        with connect() as conn:
            cur = conn.cursor()

            # Step 1: Look up in current_identifications by secondary
            cur.execute("""
                SELECT packed_primary_provisional_designation,
                       unpacked_primary_provisional_designation,
                       numbered
                FROM current_identifications
                WHERE packed_secondary_provisional_designation = %s
            """, (packed,))
            ci_row = cur.fetchone()

            if not ci_row:
                result["_db_ok"] = True
                cur.close()
                return result

            packed_primary = ci_row[0]
            unpacked_primary = ci_row[1]
            is_numbered = ci_row[2] or False

            result["primary_desig"] = unpacked_primary
            result["is_secondary"] = (packed_primary != packed)
            result["is_numbered"] = is_numbered

            # Step 2: If numbered, look up in numbered_identifications
            if is_numbered:
                cur.execute("""
                    SELECT permid, iau_name
                    FROM numbered_identifications
                    WHERE packed_primary_provisional_designation = %s
                """, (packed_primary,))
                ni_row = cur.fetchone()
                if ni_row:
                    result["permid"] = ni_row[0]
                    result["iau_name"] = ni_row[1]

            # Step 3: Look up orbit classification
            result["orbit_class"] = _lookup_orbit_class(
                cur, packed_primary)

            result["_db_ok"] = True
            cur.close()
    except Exception:
        pass

    return result
