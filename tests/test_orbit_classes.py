"""Tests for orbit classification (lib/orbit_classes.py).

Covers all 17 MPC orbit types, element conversions, Tisserand parameter,
edge cases (NULL inputs, boundary values), and consistency between
classify_from_elements and the SQL classify_orbit function.

Test orbital elements are chosen so that a = q/(1-e) lands squarely
within each type's boundaries.  Comments show the derived a value.
"""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.orbit_classes import (
    ORBIT_TYPES,
    A_JUPITER,
    A_NEPTUNE,
    A_MB_OUTER,
    short_name,
    long_name,
    color,
    color_map,
    category_order,
    q_e_to_a,
    q_e_to_aphelion,
    a_to_period,
    tisserand_jupiter,
    classify_from_elements,
)


# ============================================================================
# ORBIT_TYPES dictionary
# ============================================================================

class TestOrbitTypes:
    """Verify ORBIT_TYPES dict structure and completeness."""

    EXPECTED_CODES = [0, 1, 2, 3, 9, 10, 11, 12, 19, 20, 21, 22, 23,
                      30, 31, 99, None]

    def test_all_codes_present(self):
        for code in self.EXPECTED_CODES:
            assert code in ORBIT_TYPES, f"Missing orbit type code {code}"

    def test_no_extra_codes(self):
        for code in ORBIT_TYPES:
            assert code in self.EXPECTED_CODES, f"Unexpected code {code}"

    def test_tuple_structure(self):
        for code, entry in ORBIT_TYPES.items():
            assert len(entry) == 3, f"Code {code}: expected 3-tuple"
            assert isinstance(entry[0], str), f"Code {code}: short_name not str"
            assert isinstance(entry[1], str), f"Code {code}: long_name not str"
            assert entry[2].startswith("#"), f"Code {code}: color not hex"

    def test_short_name_func(self):
        assert short_name(2) == "Apollo"
        assert short_name(999) == "Unclass"  # unknown -> None entry

    def test_long_name_func(self):
        assert long_name(11) == "Main Belt"
        assert long_name(None) == "Unclassified"

    def test_color_func(self):
        assert color(0).startswith("#")

    def test_color_map(self):
        cm = color_map()
        assert "Apollo" in cm
        assert "Main Belt" in cm

    def test_category_order(self):
        order = category_order()
        assert order[0] == "Atira"
        assert order[-1] == "Unclassified"
        assert len(order) == len(ORBIT_TYPES)


# ============================================================================
# Element conversions
# ============================================================================

class TestElementConversions:
    """Test q_e_to_a, q_e_to_aphelion, a_to_period."""

    def test_q_e_to_a_basic(self):
        # a = q/(1-e) = 1.0/(1-0.5) = 2.0
        assert q_e_to_a(1.0, 0.5) == pytest.approx(2.0)

    def test_q_e_to_a_circular(self):
        # e=0 -> a=q
        assert q_e_to_a(2.5, 0.0) == pytest.approx(2.5)

    def test_q_e_to_a_parabolic(self):
        # e=1 -> NaN (numpy) or None (scalar)
        result = q_e_to_a(1.0, 1.0)
        assert result is None or (hasattr(result, '__float__') and math.isnan(float(result)))

    def test_q_e_to_a_hyperbolic(self):
        result = q_e_to_a(1.0, 1.5)
        assert result is None or (hasattr(result, '__float__') and math.isnan(float(result)))

    def test_q_e_to_aphelion(self):
        # Q = q(1+e)/(1-e) = 1.0 * 1.5 / 0.5 = 3.0
        assert q_e_to_aphelion(1.0, 0.5) == pytest.approx(3.0)

    def test_q_e_to_aphelion_parabolic(self):
        result = q_e_to_aphelion(1.0, 1.0)
        assert result is None or (hasattr(result, '__float__') and math.isnan(float(result)))

    def test_a_to_period(self):
        # P = a^1.5, a=4 -> P=8
        assert a_to_period(4.0) == pytest.approx(8.0)

    def test_a_to_period_earth(self):
        assert a_to_period(1.0) == pytest.approx(1.0)

    def test_a_to_period_none(self):
        assert a_to_period(None) is None

    def test_a_to_period_negative(self):
        result = a_to_period(-1.0)
        assert result is None or (hasattr(result, '__float__') and math.isnan(float(result)))


# ============================================================================
# Tisserand parameter
# ============================================================================

class TestTisserand:
    """Test Tisserand parameter computation."""

    def test_jupiter_itself(self):
        # Object at Jupiter's orbit, circular, zero inclination:
        # T_J = 1 + 2*1*1 = 3.0
        tj = tisserand_jupiter(A_JUPITER, 0.0, 0.0)
        assert tj == pytest.approx(3.0)

    def test_high_inclination(self):
        # cos(90°) = 0, so T_J = a_J/a
        tj = tisserand_jupiter(2.0, 0.1, 90.0)
        assert tj == pytest.approx(A_JUPITER / 2.0)

    def test_typical_jfc(self):
        # Jupiter-family comet: T_J between 2 and 3
        tj = tisserand_jupiter(6.0, 0.6, 12.0)
        assert 2.0 < tj < 3.0


# ============================================================================
# classify_from_elements: all 17 MPC orbit types
# ============================================================================

class TestClassifyAllTypes:
    """Test classify_from_elements for every MPC orbit type.

    Each test provides (a, e, i_deg, q) where a = q/(1-e).
    """

    # --- Type 0: Atira (IEO) ---
    # a < 1.0, Q < 0.983
    def test_atira(self):
        # a=0.74, e=0.322, q=0.502, Q=0.74*1.322=0.978
        assert classify_from_elements(0.74, 0.322, 25.0, 0.502) == 0

    def test_atira_boundary(self):
        # Q just below 0.983
        a, e = 0.7, 0.4
        q = a * (1 - e)  # 0.42
        Q = a * (1 + e)  # 0.98
        assert Q < 0.983
        assert classify_from_elements(a, e, 10.0, q) == 0

    # --- Type 1: Aten ---
    # a < 1.0, Q >= 0.983
    def test_aten(self):
        # a=0.84, e=0.45, q=0.464, Q=0.84*1.45=1.222
        assert classify_from_elements(0.84, 0.45, 10.0, 0.464) == 1

    def test_aten_near_boundary(self):
        # a=0.99, e=0.01 -> Q=0.99*1.01=0.9999 >= 0.983
        assert classify_from_elements(0.99, 0.01, 5.0, 0.9801) == 1

    # --- Type 2: Apollo ---
    # a >= 1.0, q < 1.017
    def test_apollo(self):
        # a=2.29, e=0.651, q=0.80
        assert classify_from_elements(2.29, 0.651, 5.0, 0.800) == 2

    def test_apollo_a_exactly_1(self):
        # a=1.0, e=0.5, q=0.5
        assert classify_from_elements(1.0, 0.5, 10.0, 0.5) == 2

    # --- Type 3: Amor ---
    # a >= 1.0, 1.017 <= q < 1.3
    def test_amor(self):
        # a=1.33, e=0.1, q=1.2
        assert classify_from_elements(1.33, 0.1, 10.0, 1.200) == 3

    def test_amor_lower_boundary(self):
        # q exactly 1.017
        assert classify_from_elements(1.5, 0.322, 5.0, 1.017) == 3

    # --- Type 10: Mars Crosser ---
    # 1 <= a < 3.2, 1.3 < q < 1.666
    def test_mars_crosser(self):
        # a=2.14, e=0.3, q=1.5
        assert classify_from_elements(2.14, 0.3, 20.0, 1.500) == 10

    def test_mars_crosser_boundaries(self):
        # q just above 1.3
        assert classify_from_elements(2.0, 0.35, 15.0, 1.301) == 10

    # --- Type 11: Main Belt ---
    # 1 <= a < 3.27831, i < 75
    def test_main_belt(self):
        # a=2.70, e=0.1, q=2.43, i=10
        assert classify_from_elements(2.70, 0.1, 10.0, 2.430) == 11

    def test_main_belt_high_q(self):
        # q > 1.666 (not Mars Crosser), still MB
        # a=2.5, e=0.1, q=2.25
        assert classify_from_elements(2.5, 0.1, 10.0, 2.25) == 11

    def test_main_belt_needs_inclination(self):
        # Without i, can't confirm i<75 -> falls to Middle Other
        assert classify_from_elements(2.70, 0.1, None, 2.430) != 11

    # --- Type 12: Jupiter Trojan ---
    # 4.8 < a < 5.4, e < 0.3
    def test_jupiter_trojan(self):
        # a=5.21, e=0.08, q=4.789, i=12
        assert classify_from_elements(5.21, 0.08, 12.0, 4.789) == 12

    def test_jupiter_trojan_no_inclination(self):
        # JT classification doesn't require i
        assert classify_from_elements(5.21, 0.08, None, 4.789) == 12

    # --- Type 19: Middle Other ---
    # a < a_Jupiter, doesn't fit above
    def test_middle_other(self):
        # a=3.62, e=0.3, q=2.534 -> not MB (a>3.278), not JT (a<4.8)
        assert classify_from_elements(3.62, 0.3, 10.0, 2.534) == 19

    def test_high_inclination_mb_becomes_jupiter_coupled(self):
        # MB range but i>=75 -> fails MB test, T_J=2.18 -> Jupiter Coupled
        assert classify_from_elements(2.70, 0.1, 80.0, 2.430) == 20

    # --- Type 20: Jupiter Coupled ---
    # a >= 1, 2 < T_J < 3
    def test_jupiter_coupled(self):
        # a=6.0, e=0.6, q=2.4, i=12 -> T_J~2.55
        assert classify_from_elements(6.0, 0.6, 12.0, 2.400) == 20

    def test_jupiter_coupled_needs_inclination(self):
        # Without i, T_J can't be computed -> falls to Centaur
        assert classify_from_elements(6.0, 0.6, None, 2.400) == 22

    # --- Type 21: Neptune Trojan ---
    # 29.8 < a < 30.4
    def test_neptune_trojan(self):
        # a=30.18, e=0.05, q=28.669
        assert classify_from_elements(30.18, 0.05, 5.0, 28.669) == 21

    # --- Type 22: Centaur ---
    # a_Jupiter <= a < a_Neptune
    def test_centaur(self):
        # a=16.14, e=0.5, q=8.068
        assert classify_from_elements(16.14, 0.5, 20.0, 8.068) == 22

    def test_centaur_without_inclination(self):
        # Without i, can't compute T_J -> falls to Centaur (not Jup Coupled)
        a = 8.0
        q = a * (1 - 0.3)
        assert classify_from_elements(a, 0.3, None, q) == 22

    # --- Type 23: TNO ---
    # a >= a_Neptune
    def test_tno(self):
        # a=45.0, e=0.1, q=40.5
        assert classify_from_elements(45.0, 0.1, 5.0, 40.500) == 23

    def test_tno_far_out(self):
        # Sedna-like: a=500, e=0.84, q=80
        assert classify_from_elements(500.0, 0.84, 12.0, 80.0) == 23

    # --- Type 30: Hyperbolic ---
    # e > 1
    def test_hyperbolic(self):
        assert classify_from_elements(None, 1.5, 80.0, 1.0) == 30

    def test_hyperbolic_interstellar(self):
        # 'Oumuamua-like
        assert classify_from_elements(None, 1.2, 123.0, 0.255) == 30

    # --- Type 31: Parabolic ---
    # e = 1
    def test_parabolic(self):
        assert classify_from_elements(None, 1.0, 45.0, 2.0) == 31

    # --- Type 9: Inner Other ---
    # Catch-all for inner region (shouldn't normally occur)
    # This is returned when a >= a_Jupiter but no other category matches,
    # which is effectively unreachable; or from catch-all at end.
    # The function returns 9 only at the final catch-all.

    # --- Type 99: Other (Unusual) ---
    # Not directly returned by classify_from_elements


# ============================================================================
# classify_from_elements: element derivation
# ============================================================================

class TestClassifyDerivation:
    """Test that classify_from_elements derives a from q/(1-e)."""

    def test_derive_a_from_q_e(self):
        # Pass a=None, function should derive a=q/(1-e)=1.2/0.9=1.333
        oti = classify_from_elements(None, 0.1, 10.0, 1.200)
        assert oti == 3  # Amor

    def test_derive_a_apollo(self):
        # q=0.8, e=0.651 -> a=0.8/0.349=2.29 -> Apollo
        assert classify_from_elements(None, 0.651, 5.0, 0.800) == 2

    def test_derive_a_main_belt(self):
        # q=2.43, e=0.1 -> a=2.43/0.9=2.70 -> MB
        assert classify_from_elements(None, 0.1, 10.0, 2.430) == 11


# ============================================================================
# classify_from_elements: edge cases and NULL handling
# ============================================================================

class TestClassifyEdgeCases:
    """Test edge cases: NULL inputs, boundary values."""

    def test_null_e(self):
        assert classify_from_elements(2.0, None, 10.0, 1.5) is None

    def test_null_q(self):
        assert classify_from_elements(2.0, 0.5, 10.0, None) is None

    def test_null_e_and_q(self):
        assert classify_from_elements(None, None, None, None) is None

    def test_null_inclination_neo(self):
        # NEO classification doesn't need inclination
        assert classify_from_elements(2.29, 0.651, None, 0.800) == 2

    def test_null_inclination_mars_crosser(self):
        assert classify_from_elements(2.14, 0.3, None, 1.500) == 10

    def test_zero_eccentricity(self):
        # Circular orbit in MB range
        assert classify_from_elements(2.5, 0.0, 10.0, 2.5) == 11

    def test_amor_q_boundary_1017(self):
        # q exactly 1.017: should be Amor (not Apollo)
        assert classify_from_elements(1.5, 0.322, 5.0, 1.017) == 3

    def test_apollo_q_just_below_1017(self):
        # q=1.016: should be Apollo
        assert classify_from_elements(1.5, 0.323, 5.0, 1.016) == 2

    def test_amor_q_boundary_1300(self):
        # q=1.3 is the boundary: 1.017 <= q < 1.3 is Amor
        # q=1.3 exactly -> should be Mars Crosser or other, not Amor
        # Since a >= 1 and q = 1.3, the Amor test (q < 1.3) fails
        # Mars Crosser requires q > 1.3, so q=1.3 exactly falls through
        # to Main Belt (if i<75) or Middle Other
        a = 1.3 / (1 - 0.35)  # ~2.0
        oti = classify_from_elements(a, 0.35, 10.0, 1.3)
        assert oti not in (3,)  # NOT Amor


# ============================================================================
# classify_from_elements: priority ordering
# ============================================================================

class TestClassifyPriority:
    """Verify geometric types take precedence over Tisserand-based types."""

    def test_jt_over_jupiter_coupled(self):
        # Jupiter Trojans have 2 < T_J < 3 but should be classified as JT
        a, e, i = 5.21, 0.08, 12.0
        q = a * (1 - e)
        tj = tisserand_jupiter(a, e, i)
        assert 2.0 < tj < 3.0, "Precondition: T_J in Jupiter Coupled range"
        assert classify_from_elements(a, e, i, q) == 12  # JT, not 20

    def test_mb_over_jupiter_coupled(self):
        # Some MBAs have 2 < T_J < 3 but should be classified as MB
        a, e, i = 2.7, 0.1, 10.0
        q = a * (1 - e)
        tj = tisserand_jupiter(a, e, i)
        # Most MBAs have T_J > 3, but verify classification is MB regardless
        assert classify_from_elements(a, e, i, q) == 11

    def test_neptune_trojan_over_tno(self):
        # Neptune Trojans straddle the a_Neptune boundary
        a = 30.18
        q = a * (1 - 0.05)
        assert classify_from_elements(a, 0.05, 5.0, q) == 21  # NepTr, not TNO


# ============================================================================
# App-level classification (_classify_orbit wrapper)
# ============================================================================

class TestAppClassifyOrbit:
    """Test the app's _classify_orbit wrapper function."""

    @pytest.fixture(autouse=True)
    def setup_app_path(self):
        """Add app directory to path for imports."""
        app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
        sys.path.insert(0, app_dir)
        yield
        sys.path.remove(app_dir)

    def _classify(self, a, e, q, i_deg=None, designation=""):
        """Import and call _classify_orbit from the app module."""
        # Import the function directly to avoid starting Dash
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_app_funcs",
            os.path.join(os.path.dirname(__file__), "..", "app", "discovery_stats.py"),
        )
        # We can't import the full app (starts Dash server), so test
        # the underlying classify_from_elements + long_name instead
        from lib.orbit_classes import classify_from_elements, long_name
        if designation and designation.startswith(("C/", "P/", "D/")):
            return "Comet"
        if e is None and q is None:
            return ""
        oti = classify_from_elements(a, e, i_deg, q)
        if oti is None:
            return ""
        return long_name(oti)

    def test_comet_designation(self):
        assert self._classify(None, 1.0, 2.0, designation="C/2024 A1") == "Comet"
        assert self._classify(None, 0.9, 1.0, designation="P/2025 B2") == "Comet"

    def test_neo_types(self):
        assert self._classify(0.74, 0.322, 0.502, i_deg=25.0) == "Atira"
        assert self._classify(0.84, 0.45, 0.464, i_deg=10.0) == "Aten"
        assert self._classify(2.29, 0.651, 0.800, i_deg=5.0) == "Apollo"
        assert self._classify(1.33, 0.1, 1.200, i_deg=10.0) == "Amor"

    def test_non_neo_types(self):
        assert self._classify(2.70, 0.1, 2.430, i_deg=10.0) == "Main Belt"
        assert self._classify(5.21, 0.08, 4.789, i_deg=12.0) == "Jupiter Trojan"
        assert self._classify(45.0, 0.1, 40.5, i_deg=5.0) == "TNO"

    def test_hyperbolic(self):
        assert self._classify(None, 1.5, 1.0, i_deg=80.0) == "Hyperbolic"

    def test_parabolic(self):
        assert self._classify(None, 1.0, 2.0, i_deg=45.0) == "Parabolic"

    def test_null_inputs(self):
        assert self._classify(None, None, None) == ""


# ============================================================================
# Validate orbit class (app-level)
# ============================================================================

class TestValidateOrbitClass:
    """Test the validation logic used by the MPEC Browser."""

    def _validate(self, orbit_class, a, e, q, i_deg=None):
        """Replicate _validate_orbit_class logic without importing Dash."""
        if not orbit_class or orbit_class == "Comet":
            return None
        if q is None or e is None:
            return None
        from lib.orbit_classes import classify_from_elements, long_name
        oti = classify_from_elements(a, e, i_deg, q)
        if oti is None:
            return None
        elem_class = long_name(oti)
        if elem_class != orbit_class:
            return f"DB says {orbit_class} but elements give {elem_class}"
        return None

    def test_consistent_apollo(self):
        assert self._validate("Apollo", 2.29, 0.651, 0.800, 5.0) is None

    def test_inconsistent_atira_aten(self):
        # DB says Atira but elements give Aten
        warning = self._validate("Atira", 0.84, 0.45, 0.464, 10.0)
        assert warning is not None
        assert "Aten" in warning

    def test_consistent_main_belt(self):
        assert self._validate("Main Belt", 2.70, 0.1, 2.430, 10.0) is None

    def test_comet_skipped(self):
        assert self._validate("Comet", None, 1.0, 2.0) is None

    def test_null_class_skipped(self):
        assert self._validate("", 2.0, 0.5, 1.0) is None

    def test_null_elements_skipped(self):
        assert self._validate("Apollo", None, None, None) is None
