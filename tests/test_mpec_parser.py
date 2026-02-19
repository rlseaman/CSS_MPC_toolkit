"""Tests for MPEC parser designation extraction (lib/mpec_parser.py)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.mpec_parser import _extract_designation


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
