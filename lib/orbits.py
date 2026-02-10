"""
Parameterized query builders for the mpc_orbits table.

Generates (sql, params) tuples suitable for use with lib.db.timed_query().
Never uses SELECT *; always explicit column lists.  Supports filtering by
orbit type, magnitude range, orbital element ranges, and MOID thresholds.

Usage:
    from lib.db import connect, timed_query
    from lib.orbits import build_orbit_query

    sql, params = build_orbit_query(orbit_types=[2, 3], h_range=(18, 26))
    with connect() as conn:
        df = timed_query(conn, sql, params, label="Apollo+Amor H>18")
"""

from lib.orbit_classes import A_JUPITER


# ---------------------------------------------------------------------------
# Core orbital element columns available as flat fields
# ---------------------------------------------------------------------------
# NOTE: mpc_orbits stores cometary elements (q, e, i, node, argperi,
# peri_time) for ALL objects, but Keplerian elements (a, mean_anomaly,
# period, mean_motion) only for ~43% of objects.  The DERIVED_COLUMNS
# dict below provides COALESCE expressions that compute missing values
# from the cometary elements that are always present.

CORE_COLUMNS = [
    "packed_primary_provisional_designation",
    "unpacked_primary_provisional_designation",
    "orbit_type_int",
    "q", "e", "i", "node", "argperi", "peri_time",
    "a", "mean_anomaly", "period", "mean_motion",
    "h", "g", "epoch_mjd",
    "earth_moid",
    "u_param", "nopp", "nobs_total", "nobs_total_sel",
]

# Derived column expressions: compute Keplerian elements from cometary
# elements when the flat column is NULL.
#   a = q / (1 - e)                for e < 1 (elliptical)
#   Q = a * (1 + e) = q*(1+e)/(1-e)  aphelion distance
#   period = a^1.5                 in years (Kepler's third law, heliocentric)
DERIVED_COLUMNS = {
    "a": "COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END)",
    "aphelion_q": "CASE WHEN e < 1 THEN COALESCE(a, q / NULLIF(1.0 - e, 0)) * (1.0 + e) END",
    "period_yr": "COALESCE(period, CASE WHEN e < 1 THEN POWER(q / NULLIF(1.0 - e, 0), 1.5) END)",
}

UNCERTAINTY_COLUMNS = [
    "q_unc", "e_unc", "i_unc", "node_unc", "argperi_unc", "peri_time_unc",
]

# JSONB field extraction: (json_path, cast_type)
# cast_type is "numeric" or "text" — determines SQL CAST
JSONB_FIELDS = {
    "orbit_quality":  ("mpc_orb_jsonb->'orbit_fit_statistics'->>'orbit_quality'", "text"),
    "snr":            ("mpc_orb_jsonb->'orbit_fit_statistics'->>'SNR'",            "numeric"),
    "arc_length":     ("mpc_orb_jsonb->'orbit_fit_statistics'->>'arc_length'",     "text"),
    "normalized_rms": ("mpc_orb_jsonb->'orbit_fit_statistics'->>'normalized_RMS'", "numeric"),
    "mars_moid":      ("mpc_orb_jsonb->'moid_data'->>'Mars'",                     "numeric"),
    "venus_moid":     ("mpc_orb_jsonb->'moid_data'->>'Venus'",                    "numeric"),
    "jupiter_moid":   ("mpc_orb_jsonb->'moid_data'->>'Jupiter'",                  "numeric"),
    "orbit_type_str": ("mpc_orb_jsonb->'categorization'->>'orbit_type_str'",       "text"),
    "g1":             ("mpc_orb_jsonb->'magnitude_data'->>'G1'",                   "numeric"),
    "g2":             ("mpc_orb_jsonb->'magnitude_data'->>'G2'",                   "numeric"),
    "g12":            ("mpc_orb_jsonb->'magnitude_data'->>'G12'",                  "numeric"),
}


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def build_orbit_query(
    columns=None,
    orbit_types=None,
    h_range=None,
    a_range=None,
    e_range=None,
    q_range=None,
    i_range=None,
    earth_moid_max=None,
    include_unclassified=False,
    include_tisserand=False,
    include_uncertainties=False,
    include_jsonb_fields=None,
    limit=None,
    count_only=False,
):
    """
    Build a parameterized SELECT query against mpc_orbits.

    Parameters
    ----------
    columns : list of str, optional
        Column names to select.  Defaults to CORE_COLUMNS.
    orbit_types : list of int, optional
        Filter to these orbit_type_int values.
    h_range : tuple of (float, float), optional
        (min_h, max_h) inclusive range for h magnitude.
    a_range : tuple of (float, float), optional
        (min_a, max_a) inclusive range for semi-major axis.
    e_range : tuple of (float, float), optional
        (min_e, max_e) inclusive range for eccentricity.
    q_range : tuple of (float, float), optional
        (min_q, max_q) inclusive range for perihelion distance.
    i_range : tuple of (float, float), optional
        (min_i, max_i) inclusive range for inclination.
    earth_moid_max : float, optional
        Maximum Earth MOID in AU.
    include_unclassified : bool
        If True and orbit_types is set, also include NULL orbit_type_int.
    include_tisserand : bool
        If True, add a computed Tisserand parameter column.
    include_uncertainties : bool
        If True, include uncertainty columns.
    include_jsonb_fields : list of str, optional
        Keys from JSONB_FIELDS to extract (e.g., ["orbit_quality", "snr"]).
    limit : int, optional
        LIMIT clause.
    count_only : bool
        If True, return COUNT(*) instead of rows.

    Returns
    -------
    tuple of (str, list)
        (sql, params) ready for timed_query().
    """
    params = []

    if count_only:
        select_parts = ["COUNT(*)"]
    else:
        cols = list(columns or CORE_COLUMNS)
        if include_uncertainties:
            cols.extend(UNCERTAINTY_COLUMNS)

        # Replace columns that have derived expressions
        select_parts = []
        for col in cols:
            if col in DERIVED_COLUMNS:
                select_parts.append(f"{DERIVED_COLUMNS[col]} AS {col}")
            else:
                select_parts.append(col)

        # Derived a expression for use in Tisserand computation
        a_expr = DERIVED_COLUMNS["a"]

        if include_tisserand:
            tj_expr = (
                f"{A_JUPITER} / NULLIF(({a_expr}), 0) + "
                f"2.0 * COS(RADIANS(i)) * "
                f"SQRT(GREATEST(({a_expr}) / {A_JUPITER} * (1.0 - e * e), 0))"
            )
            select_parts.append(f"({tj_expr}) AS tisserand_j")

        if include_jsonb_fields:
            for key in include_jsonb_fields:
                if key in JSONB_FIELDS:
                    json_path, cast_type = JSONB_FIELDS[key]
                    if cast_type == "text":
                        select_parts.append(f"({json_path}) AS {key}")
                    else:
                        select_parts.append(f"CAST({json_path} AS {cast_type}) AS {key}")

    select_clause = ", ".join(select_parts)

    # WHERE conditions
    conditions = []

    if orbit_types is not None:
        placeholders = ", ".join(["%s"] * len(orbit_types))
        if include_unclassified:
            conditions.append(f"(orbit_type_int IN ({placeholders}) OR orbit_type_int IS NULL)")
        else:
            conditions.append(f"orbit_type_int IN ({placeholders})")
        params.extend(orbit_types)

    if h_range is not None:
        conditions.append("h >= %s AND h <= %s")
        params.extend(h_range)

    if a_range is not None:
        a_expr_where = DERIVED_COLUMNS["a"]
        conditions.append(f"({a_expr_where}) >= %s AND ({a_expr_where}) <= %s")
        params.extend(a_range)

    if e_range is not None:
        conditions.append("e >= %s AND e <= %s")
        params.extend(e_range)

    if q_range is not None:
        conditions.append("q >= %s AND q <= %s")
        params.extend(q_range)

    if i_range is not None:
        conditions.append("i >= %s AND i <= %s")
        params.extend(i_range)

    if earth_moid_max is not None:
        conditions.append("earth_moid <= %s")
        params.append(earth_moid_max)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    limit_clause = ""
    if limit is not None and not count_only:
        limit_clause = f"LIMIT {int(limit)}"

    sql = f"SELECT {select_clause} FROM mpc_orbits {where_clause} {limit_clause}"
    return sql.strip(), params


# ---------------------------------------------------------------------------
# NULL rate survey
# ---------------------------------------------------------------------------

# All flat columns in mpc_orbits (excluding id and the JSONB blob).
# Validated against information_schema.columns on 2026-02-10.
ALL_FLAT_COLUMNS = [
    "packed_primary_provisional_designation",
    "unpacked_primary_provisional_designation",
    "orbit_type_int",
    "q", "q_unc",
    "e", "e_unc",
    "i", "i_unc",
    "node", "node_unc",
    "argperi", "argperi_unc",
    "peri_time", "peri_time_unc",
    "a", "a_unc",
    "mean_anomaly", "mean_anomaly_unc",
    "period", "period_unc",
    "mean_motion", "mean_motion_unc",
    "h", "g", "epoch_mjd",
    "earth_moid",
    "u_param", "nopp",
    "arc_length_total", "arc_length_sel",
    "nobs_total", "nobs_total_sel",
    "not_normalized_rms", "normalized_rms",
    "fitting_datetime",
    "yarkovsky", "yarkovsky_unc",
    "srp", "srp_unc",
    "a1", "a1_unc",
    "a2", "a2_unc",
    "a3", "a3_unc",
    "dt", "dt_unc",
    "created_at", "updated_at",
]


def build_null_rates_query(columns=None):
    """
    Build a query that returns NULL counts for each column in a single pass.

    Uses COUNT(*) - COUNT(col) to get NULL count without multiple scans.

    Returns
    -------
    tuple of (str, list)
        (sql, []) — no parameters needed.
    """
    cols = columns or ALL_FLAT_COLUMNS
    parts = []
    for col in cols:
        parts.append(
            f"SELECT '{col}' AS column_name, "
            f"COUNT(*) AS total, "
            f"COUNT(*) - COUNT({col}) AS null_count, "
            f"ROUND(100.0 * (COUNT(*) - COUNT({col})) / COUNT(*), 2) AS null_pct "
            f"FROM mpc_orbits"
        )
    sql = " UNION ALL ".join(parts)
    return sql, []


def build_value_distribution_query(column, n_bins=50, min_val=None, max_val=None):
    """
    Build a server-side histogram query using width_bucket().

    Computes the histogram on the database server to avoid transferring
    all raw values.  Uses actual min/max if not provided.

    If column is in DERIVED_COLUMNS, uses the derived expression
    (e.g., 'a' uses COALESCE(a, q/(1-e)) to include all orbits).

    Parameters
    ----------
    column : str
        Column name to histogram (may be a derived column key).
    n_bins : int
        Number of bins.
    min_val : float, optional
        Override minimum value (uses actual min if not provided).
    max_val : float, optional
        Override maximum value (uses actual max if not provided).

    Returns
    -------
    tuple of (str, list)
    """
    # Use derived expression if available, otherwise raw column
    col_expr = DERIVED_COLUMNS.get(column, column)

    params = []

    if min_val is not None and max_val is not None:
        range_expr = "%s"
        range_expr_max = "%s"
        params.extend([min_val, max_val, min_val, max_val, n_bins, min_val, max_val, n_bins])
        sql = f"""
WITH bounds AS (
    SELECT %s::double precision AS lo, %s::double precision AS hi
),
binned AS (
    SELECT width_bucket({col_expr}, %s, %s, %s) AS bucket
    FROM mpc_orbits
    WHERE ({col_expr}) IS NOT NULL
)
SELECT
    bucket,
    %s + (bucket - 1) * (%s - %s) / %s::double precision AS bin_lo,
    COUNT(*) AS count
FROM binned
WHERE bucket BETWEEN 1 AND %s
GROUP BY bucket
ORDER BY bucket
"""
        params = [min_val, max_val, min_val, max_val, n_bins, min_val, max_val, min_val, n_bins, n_bins]
    else:
        sql = f"""
WITH bounds AS (
    SELECT MIN({col_expr}) AS lo, MAX({col_expr}) AS hi
    FROM mpc_orbits
    WHERE ({col_expr}) IS NOT NULL
),
binned AS (
    SELECT width_bucket({col_expr}, b.lo, b.hi + 1e-10, %s) AS bucket
    FROM mpc_orbits, bounds b
    WHERE ({col_expr}) IS NOT NULL
)
SELECT
    bucket,
    (SELECT lo FROM bounds) + (bucket - 1) * ((SELECT hi FROM bounds) - (SELECT lo FROM bounds)) / %s::double precision AS bin_lo,
    COUNT(*) AS count
FROM binned
WHERE bucket BETWEEN 1 AND %s
GROUP BY bucket
ORDER BY bucket
"""
        params = [n_bins, n_bins, n_bins]

    return sql.strip(), params
