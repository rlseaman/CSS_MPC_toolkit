"""
MPC data format conversion utilities.

Converts between MPC 80-column observation format fields and modern
representations (ADES, decimal degrees, ISO 8601).

Reference:
  - MPC 80-column format: https://www.minorplanetcenter.net/iau/info/ObsFormat.html
  - ADES standard: https://github.com/IAU-ADES/ADES-Master
  - Catalog codes: https://www.minorplanetcenter.net/iau/info/CatalogueCodes.html
"""


# ---------------------------------------------------------------------------
# Catalog code mapping: MPC single-char -> ADES astCat name
# ---------------------------------------------------------------------------
MPC_CAT_TO_ADES = {
    "a": "USNOA1",
    "b": "USNOSA1",
    "c": "USNOA2",
    "d": "USNOSA2",
    "e": "UCAC1",
    "f": "Tycho1",
    "g": "Tycho2",
    "h": "GSC1.0",
    "i": "GSC1.1",
    "j": "GSC1.2",
    "k": "GSC2.2",
    "l": "ACT",
    "m": "GSCACT",
    "n": "SDSSDR8",
    "o": "USNOB1",
    "p": "PPM",
    "q": "UCAC4",
    "r": "UCAC2",
    "s": "USNOB2",
    "t": "PPMXL",
    "u": "UCAC3",
    "v": "NOMAD",
    "w": "CMC14",
    "x": "Hip2",
    "y": "Hip",
    "z": "GSC",
    "A": "AC",
    "B": "SAO1984",
    "C": "SAO",
    "D": "AGK3",
    "E": "FK4",
    "F": "ACRS",
    "G": "LickGas",
    "H": "Ida93",
    "I": "Perth70",
    "J": "COSMOS",
    "K": "Yale",
    "L": "2MASS",
    "M": "GSC2.3",
    "N": "SDSSDR7",
    "O": "SSTRC1",
    "P": "MPOSC3",
    "Q": "CMC15",
    "R": "SSTRC4",
    "S": "URAT1",
    "T": "URAT2",
    "U": "Gaia1",
    "V": "Gaia2",
    "W": "Gaia3",
    "X": "Gaia3E",
    "Y": "UCAC5",
    "Z": "ATLAS2",
    "0": "IHW",
    "1": "PS1DR1",
    "2": "PS1DR2",
    "3": "GaiaInt",
    "4": "GZ",
    "5": "UBAD",
    "6": "Gaia16",
}

# Reverse mapping for encoding
ADES_CAT_TO_MPC = {v: k for k, v in MPC_CAT_TO_ADES.items()}


# ---------------------------------------------------------------------------
# Observation mode mapping: MPC col-15 code -> ADES mode
# ---------------------------------------------------------------------------
MPC_MODE_TO_ADES = {
    "C": "CCD",
    "B": "CMO",     # CMOS
    "V": "VID",
    "T": "TDI",
    "P": "PHO",
    "E": "ENC",
    "M": "MIC",
    "e": "PMT",     # encoder / photoelectric
    "O": "OCC",
    "A": "PHO",     # photographic (aperture corrected)
    "N": "PHO",     # photographic (normal astrograph)
    " ": "PHO",     # blank = photographic (historical default)
    "S": "CCD",     # satellite-based CCD
    "s": "CCD",     # satellite-based CCD (second line)
    "X": "CCD",     # roving observer
    "x": "CCD",     # roving observer (second line)
}

# Reverse mapping
ADES_MODE_TO_MPC = {
    "CCD": "C",
    "CMO": "B",
    "VID": "V",
    "TDI": "T",
    "PHO": "P",
    "ENC": "E",
    "MIC": "M",
    "PMT": "e",
    "OCC": "O",
}


# ---------------------------------------------------------------------------
# Band mapping: MPC single-char -> ADES band code
# ---------------------------------------------------------------------------
MPC_BAND_TO_ADES = {
    "B": "Bj",
    "V": "Vj",
    "R": "Rc",
    "I": "Ic",
    "J": "J",
    "H": "H",
    "K": "K",
    "U": "Uj",
    "W": "W",
    "u": "Sg",      # Sloan u' -> SDSS g (approximate)
    "g": "Sg",
    "r": "Sr",
    "i": "Si",
    "z": "Sz",
    "w": "Pw",      # Pan-STARRS w
    "y": "Py",      # Pan-STARRS y
    "G": "G",       # Gaia G
    "T": "Gr",      # Gaia RP? context-dependent
    "o": "Ao",      # ATLAS orange
    "c": "Ac",      # ATLAS cyan
    "C": "CV",      # Clear (V-equivalent)
    "L": "CV",      # Luminance (approx clear)
    " ": "",        # unknown
}


# ---------------------------------------------------------------------------
# MPC packed date -> ISO 8601
# ---------------------------------------------------------------------------
def mpc_date_to_iso8601(date_str):
    """Convert MPC 80-column date field to ISO 8601 UTC.

    Args:
        date_str: 17-character string from obs80 positions 16-32,
                  e.g. "2024 12 27.238073"

    Returns:
        ISO 8601 string, e.g. "2024-12-27T05:42:49.51Z"
        Precision of fractional seconds matches the input.
    """
    s = date_str.strip()
    parts = s.split()
    if len(parts) != 3:
        raise ValueError(f"Cannot parse MPC date: {date_str!r}")

    year = parts[0]
    month = parts[1].zfill(2)
    day_frac = parts[2]

    dot_pos = day_frac.index(".")
    day = int(day_frac[:dot_pos])
    frac_str = day_frac[dot_pos:]  # includes the dot
    frac = float(frac_str)

    total_seconds = frac * 86400.0
    hours = int(total_seconds // 3600)
    remaining = total_seconds - hours * 3600
    minutes = int(remaining // 60)
    secs = remaining - minutes * 60

    # Determine fractional second precision from input
    # Input decimal places on the day fraction map to time precision:
    #   5 decimal places on day -> ~0.86s -> 0 decimal places on seconds
    #   6 -> ~0.086s -> 1 decimal place
    #   7 -> ~0.0086s -> 2 decimal places
    #   8 -> ~0.00086s -> 3 decimal places
    input_decimals = len(frac_str) - 1  # minus the dot character
    if input_decimals <= 5:
        sec_decimals = 0
    else:
        sec_decimals = input_decimals - 5

    if sec_decimals == 0:
        secs_rounded = int(round(secs))
    else:
        # Round to the target precision, then check for carry
        factor = 10 ** sec_decimals
        secs_rounded = round(secs * factor) / factor

    # Handle seconds rounding up to 60 -> carry to minutes/hours
    if secs_rounded >= 60:
        secs_rounded -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        hours += 1

    if sec_decimals == 0:
        sec_str = f"{int(secs_rounded):02d}"
    else:
        sec_str = f"{secs_rounded:0{3 + sec_decimals}.{sec_decimals}f}"

    return f"{year}-{month}-{day:02d}T{hours:02d}:{minutes:02d}:{sec_str}Z"


# ---------------------------------------------------------------------------
# RA sexagesimal -> decimal degrees
# ---------------------------------------------------------------------------
def ra_hms_to_deg(ra_str):
    """Convert RA from MPC 80-column HH MM SS.sss to decimal degrees.

    Args:
        ra_str: 12-character string from obs80 positions 33-44,
                e.g. "08 56 40.968" or "09 30 31.27 "

    Returns:
        RA in decimal degrees [0, 360).
    """
    s = ra_str.strip()
    parts = s.split()
    if len(parts) != 3:
        raise ValueError(f"Cannot parse RA: {ra_str!r}")

    h = int(parts[0])
    m = int(parts[1])
    sec = float(parts[2])

    deg = (h + m / 60.0 + sec / 3600.0) * 15.0

    # Determine output precision from input
    if "." in parts[2]:
        input_decimals = len(parts[2].split(".")[1])
        # SS.sss -> degrees: each decimal on seconds = ~1 decimal on degrees
        # but *15 conversion adds ~1.2 extra digits of significance
        output_decimals = input_decimals + 2
    else:
        output_decimals = 4

    return round(deg, output_decimals)


# ---------------------------------------------------------------------------
# Dec sexagesimal -> decimal degrees
# ---------------------------------------------------------------------------
def dec_dms_to_deg(dec_str):
    """Convert Dec from MPC 80-column sDD MM SS.ss to decimal degrees.

    Args:
        dec_str: 12-character string from obs80 positions 45-56,
                 e.g. "-00 16 11.93" or "+27 20 08.99"

    Returns:
        Declination in decimal degrees [-90, 90].
    """
    s = dec_str.strip()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")

    parts = s.split()
    if len(parts) != 3:
        raise ValueError(f"Cannot parse Dec: {dec_str!r}")

    d = int(parts[0])
    m = int(parts[1])
    sec = float(parts[2])

    deg = sign * (d + m / 60.0 + sec / 3600.0)

    if "." in parts[2]:
        input_decimals = len(parts[2].split(".")[1])
        output_decimals = input_decimals + 2
    else:
        output_decimals = 4

    return round(deg, output_decimals)


# ---------------------------------------------------------------------------
# Catalog, mode, and band code conversion
# ---------------------------------------------------------------------------
def mpc_cat_to_ades(code):
    """Map MPC single-character catalog code to ADES astCat name."""
    return MPC_CAT_TO_ADES.get(code, "")


def mpc_mode_to_ades(code):
    """Map MPC observation type code (col 15) to ADES mode."""
    return MPC_MODE_TO_ADES.get(code, "UNK")


def mpc_band_to_ades(code):
    """Map MPC photometric band character to ADES band code."""
    return MPC_BAND_TO_ADES.get(code, code if code.strip() else "")


# ---------------------------------------------------------------------------
# MPC packed designation <-> unpacked
# ---------------------------------------------------------------------------

# Century encoding for packed designations
_CENTURY_PACK = {"I": "18", "J": "19", "K": "20"}
_CENTURY_UNPACK = {v: k for k, v in _CENTURY_PACK.items()}

# Letter-to-number encoding for half-month and cycle count
_LETTER_NUM = {}
for _i, _c in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"):
    _LETTER_NUM[_c] = _i


def _decode_cycle(packed_cycle):
    """Decode the cycle count portion of a packed provisional designation.

    Positions 5-6 of the 7-char packed form encode a base-62 number:
    00 = 0, 01 = 1, ..., 99 = 99, A0 = 100, ..., z9 = 619, ...
    """
    if len(packed_cycle) != 2:
        return 0
    high = packed_cycle[0]
    low = packed_cycle[1]
    if high.isdigit():
        return int(packed_cycle)
    return _LETTER_NUM.get(high, 0) * 10 + int(low)


def unpack_designation(packed):
    """Unpack an MPC packed designation to human-readable form.

    Delegates to the mpc_designation library which handles all formats
    including tilde-encoded numbers >= 620000, comets, and satellites.

    Examples:
        >>> unpack_designation("K24Y04R")
        '2024 YR4'
        >>> unpack_designation("00433  ")
        '433'
        >>> unpack_designation("~0fr6")
        '780896'
    """
    from mpc_designation import unpack as _unpack
    s = packed.strip()
    if not s:
        return ""
    try:
        return _unpack(s)
    except Exception:
        return s


def pack_designation(unpacked):
    """Pack a human-readable designation into MPC packed form.

    Delegates to the mpc_designation library which handles all formats
    including tilde-encoded numbers >= 620000, comets, and satellites.

    Examples:
        >>> pack_designation("2024 YR4")
        'K24Y04R'
        >>> pack_designation("433")
        '00433'
        >>> pack_designation("780896")
        '~0fr6'
    """
    from mpc_designation import pack as _pack
    s = unpacked.strip()
    if not s:
        return s
    try:
        return _pack(s)
    except Exception:
        return s


# ---------------------------------------------------------------------------
# Parse obs80 line into a dict of ADES-compatible fields
# ---------------------------------------------------------------------------
def parse_obs80(obs80, rmsra=None, rmsdec=None, rmscorr=None, rmstime=None):
    """Parse an MPC 80-column observation line into ADES-ready fields.

    Args:
        obs80: 80-character observation string
        rmsra: RA uncertainty in arcseconds (from database column)
        rmsdec: Dec uncertainty in arcseconds (from database column)
        rmscorr: RA-Dec correlation (from database column)
        rmstime: Time uncertainty in seconds (from database column)

    Returns:
        Dictionary of ADES field names to values. Empty/None values
        are omitted.
    """
    # Pad to at least 80 chars
    line = obs80.ljust(80)

    result = {}

    # Designation (cols 1-12)
    packed_desig = line[0:12].strip()
    if packed_desig:
        unpacked = unpack_designation(packed_desig)
        # Determine if numbered or provisional
        if unpacked.isdigit():
            result["permID"] = unpacked
        else:
            result["provID"] = unpacked

    # Discovery flag (col 13)
    disc = line[12]
    if disc in ("*", "+"):
        result["disc"] = disc

    # Note / program code (col 14)
    # Alphabetic characters are publishable notes; numeric and other
    # characters are observer program codes (assigned by MPC).
    col14 = line[13]
    if col14.strip():
        if col14.isalpha():
            result["notes"] = col14
        elif col14.isalnum() or col14 == '_':
            # ADES ProgType is [A-Za-z0-9_]{1,2}; drop chars like '|'
            result["prog"] = col14

    # Mode (col 15)
    mode_code = line[14]
    mode = mpc_mode_to_ades(mode_code)
    if mode:
        result["mode"] = mode

    # Observation time (cols 16-32)
    date_str = line[15:32]
    if date_str.strip():
        result["obsTime"] = mpc_date_to_iso8601(date_str)

    # RA (cols 33-44)
    ra_str = line[32:44]
    if ra_str.strip():
        result["ra"] = ra_hms_to_deg(ra_str)

    # Dec (cols 45-56)
    dec_str = line[44:56]
    if dec_str.strip():
        result["dec"] = dec_dms_to_deg(dec_str)

    # Magnitude (cols 66-70)
    mag_str = line[65:70].strip()
    if mag_str:
        try:
            result["mag"] = float(mag_str)
        except ValueError:
            pass

    # Band (col 71)
    band_code = line[70]
    band = mpc_band_to_ades(band_code)
    if band:
        result["band"] = band

    # Catalog code (col 72)
    cat_code = line[71]
    cat = mpc_cat_to_ades(cat_code)
    if cat:
        result["astCat"] = cat

    # Station (cols 78-80)
    stn = line[77:80].strip()
    if stn:
        result["stn"] = stn

    # Database-sourced uncertainty fields
    if rmsra is not None:
        result["rmsRA"] = float(rmsra)
    if rmsdec is not None:
        result["rmsDec"] = float(rmsdec)
    if rmscorr is not None:
        result["rmsCorr"] = float(rmscorr)
    if rmstime is not None:
        result["rmsTime"] = float(rmstime)

    return result


# ---------------------------------------------------------------------------
# Self-test when run directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Date conversion tests
    # 6 decimal places on day -> 1 decimal place on seconds
    assert mpc_date_to_iso8601("2024 12 27.238073") == "2024-12-27T05:42:49.5Z"
    # 5 decimal places on day -> 0 decimal places on seconds
    assert mpc_date_to_iso8601("2026 02 07.11530") == "2026-02-07T02:46:02Z"
    # 6 decimal places on day -> 1 decimal place on seconds
    assert mpc_date_to_iso8601("2026 02 09.213539") == "2026-02-09T05:07:29.8Z"
    # 8 decimal places -> 3 decimal places on seconds
    assert mpc_date_to_iso8601("2026 02 08.76638905") == "2026-02-08T18:23:36.014Z"

    # RA conversion tests
    assert abs(ra_hms_to_deg("08 56 40.968") - 134.17070) < 0.00001
    assert abs(ra_hms_to_deg("09 30 31.27 ") - 142.63029) < 0.0001

    # Dec conversion tests
    assert abs(dec_dms_to_deg("-00 16 11.93") - (-0.26998)) < 0.0001
    assert abs(dec_dms_to_deg("+27 20 08.99") - 27.33583) < 0.0001

    # Designation tests
    assert unpack_designation("K24Y04R") == "2024 YR4"
    assert unpack_designation("00433  ") == "433"
    assert unpack_designation("00433") == "433"
    assert unpack_designation("J95X00A") == "1995 XA"
    assert unpack_designation("K20C03D") == "2020 CD3"
    assert unpack_designation("~0fr6") == "780896"
    assert pack_designation("2024 YR4") == "K24Y04R"
    assert pack_designation("433") == "00433"
    assert pack_designation("1995 XA") == "J95X00A"
    assert pack_designation("2020 CD3") == "K20C03D"
    assert pack_designation("780896") == "~0fr6"

    # Catalog mapping
    assert mpc_cat_to_ades("V") == "Gaia2"
    assert mpc_cat_to_ades("W") == "Gaia3"
    assert mpc_cat_to_ades("X") == "Gaia3E"
    assert mpc_cat_to_ades("L") == "2MASS"

    # Mode mapping
    assert mpc_mode_to_ades("C") == "CCD"
    assert mpc_mode_to_ades("B") == "CMO"

    # Full obs80 parse test
    obs = "     A11guOI* C2024 12 27.23807308 56 40.968-00 16 11.93         16.54oV     W68"
    fields = parse_obs80(obs, rmsra=0.197, rmsdec=0.161, rmscorr=-0.596)
    assert fields["disc"] == "*"
    assert fields["mode"] == "CCD"
    assert fields["stn"] == "W68"
    assert fields["astCat"] == "Gaia2"
    assert abs(fields["ra"] - 134.17070) < 0.001
    assert abs(fields["dec"] - (-0.26998)) < 0.001
    assert fields["rmsRA"] == 0.197
    assert fields["rmsCorr"] == -0.596

    print("All tests passed.")
