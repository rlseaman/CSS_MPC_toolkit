"""Tests for MPEC parser (lib/mpec_parser.py).

Covers designation extraction and MPEC type classification.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.mpec_parser import _extract_designation, classify_mpec


class TestExtractDesignation:
    """Test _extract_designation for various MPEC formats."""

    def test_bold_asteroid(self):
        text = "  **2026 CE3**\n"
        assert _extract_designation(text) == "2026 CE3"

    def test_centered_asteroid(self):
        text = "                       2026 CT4\n"
        assert _extract_designation(text) == "2026 CT4"

    def test_comet_c(self):
        text = "                       COMET  C/2026 A1 (MAPS)\n"
        assert _extract_designation(text) == "C/2026 A1 (MAPS)"

    def test_comet_p(self):
        text = "                       COMET  P/2025 B2 (Smith)\n"
        assert _extract_designation(text) == "P/2025 B2 (Smith)"

    def test_comet_without_prefix(self):
        text = "                       C/2024 G3 (ATLAS)\n"
        assert _extract_designation(text) == "C/2024 G3 (ATLAS)"

    def test_interstellar_3i(self):
        text = "                       COMET  3I/ATLAS\n"
        assert _extract_designation(text) == "3I/ATLAS"

    def test_interstellar_1i(self):
        text = "                       COMET  1I/\u02BBOumuamua\n"
        assert _extract_designation(text) == "1I/\u02BBOumuamua"

    def test_interstellar_2i(self):
        text = "                       COMET  2I/Borisov\n"
        assert _extract_designation(text) == "2I/Borisov"

    def test_interstellar_no_comet_prefix(self):
        text = "                       3I/ATLAS\n"
        assert _extract_designation(text) == "3I/ATLAS"

    def test_full_mpec_header(self):
        text = """
                         M.P.E.C. 2026-D56

                       COMET  3I/ATLAS

     The following observations were received.
"""
        assert _extract_designation(text) == "3I/ATLAS"

    def test_no_designation(self):
        text = "Some random text with no designation\n"
        assert _extract_designation(text) is None


class TestClassifyMpec:
    """Test classify_mpec for discovery/recovery/editorial classification."""

    def test_dou_title(self):
        assert classify_mpec("DAILY ORBIT UPDATE") == "dou"

    def test_dou_content(self):
        assert classify_mpec("", "DAILY ORBIT UPDATE (2026 Feb 19)") == "dou"

    def test_retraction(self):
        assert classify_mpec("RETRACTION OF 2026 AB") == "retraction"

    def test_editorial(self):
        assert classify_mpec("EDITORIAL NOTICE") == "editorial"

    def test_editorial_in_content(self):
        assert classify_mpec("Notice", "\n  EDITORIAL\n\nSome text") == "editorial"

    def test_additional_observations(self):
        assert classify_mpec("2026 CE3", "Additional Observations\n") == "recovery"

    def test_revision(self):
        assert classify_mpec("2026 CE3", "Revision to MPEC 2026-C01\n") == "recovery"

    def test_current_year_discovery(self):
        """Current-year designation = discovery."""
        import datetime
        year = datetime.date.today().year
        desig = f"{year} CE3"
        assert classify_mpec(desig, f"**{desig}**\nObservations:\n") == "discovery"

    def test_prior_year_recovery(self):
        """Prior-year designation = recovery."""
        assert classify_mpec("2025 XY", "**2025 XY**\nObservations:\n") == "recovery"

    def test_comet_prior_year_recovery(self):
        assert classify_mpec(
            "COMET C/2025 A1",
            "COMET  C/2025 A1 (MAPS)\nObservations:\n"
        ) == "recovery"

    def test_comet_current_year_discovery(self):
        import datetime
        year = datetime.date.today().year
        assert classify_mpec(
            f"COMET C/{year} B2",
            f"COMET  C/{year} B2\nObservations:\n"
        ) == "discovery"

    def test_interstellar_recovery_from_obs_dates(self):
        """Interstellar object with no year in designation — use obs dates."""
        pre_text = """
                       COMET  3I/ATLAS

Observations:
0003I        eC2025 11 29.21566012 08 01.050-00 05 33.83         13.2 GWED056J86
0003I        eC2026 02 19.12345612 08 01.050-00 05 33.83         13.2 GWED056J86
"""
        assert classify_mpec("COMET 3I/ATLAS", pre_text) == "recovery"

    def test_interstellar_discovery_current_year_obs(self):
        """Interstellar object discovered this year."""
        import datetime
        year = datetime.date.today().year
        pre_text = f"""
                       COMET  4I/Foo

Observations:
0004I        eC{year} 01 15.12345612 08 01.050-00 05 33.83       13.2 GWED056J86
"""
        assert classify_mpec("COMET 4I/Foo", pre_text) == "discovery"

    def test_title_only_prior_year(self):
        assert classify_mpec("2024 AB") == "recovery"

    def test_title_only_current_year(self):
        import datetime
        year = datetime.date.today().year
        assert classify_mpec(f"{year} ZZ") == "discovery"

    def test_no_title_no_content(self):
        assert classify_mpec("") == "editorial"
