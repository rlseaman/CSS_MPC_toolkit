# Schema: NEA Discovery Tracklets

## Output CSV

**Filename:** `NEA_discovery_tracklets.csv`

| Column | Type | Example | Description |
|--------|------|---------|-------------|
| `primary_designation` | text | `433` or `2024 AA1` | Asteroid number (for numbered) or provisional designation (for unnumbered) |
| `packed_primary_provisional_designation` | text | `00433` or `K24A01A` | MPC packed format designation |
| `avg_mjd_discovery_tracklet` | numeric(6) | `60345.123456` | Mean Modified Julian Date of all observations in the discovery tracklet |
| `avg_ra_deg` | numeric(5) | `123.45678` | Mean Right Ascension in decimal degrees (J2000) |
| `avg_dec_deg` | numeric(5) | `-12.34567` | Mean Declination in decimal degrees (J2000) |
| `median_v_magnitude` | numeric(2) | `21.30` | Median apparent V-band magnitude, with band corrections applied |
| `discovery_site_code` | text | `703` | MPC observatory code where the discovery observation was made |

## Sort Order

Rows are sorted with numbered asteroids first (by number, ascending), then
unnumbered asteroids (by provisional designation, alphabetically).

## Designation Formats

### Numbered Asteroids

Objects that have received a permanent number from the MPC.

- **primary_designation:** The number as a string, e.g., `433`, `99942`
- **packed:** Right-justified zero-padded for numbers < 100000 (`00433`),
  letter-prefixed for 100000-619999 (`A0345` = 100345),
  tilde-prefixed base-62 for >= 620000 (`~0000` = 620000)

### Unnumbered Asteroids

Objects identified only by provisional designation.

- **primary_designation:** Standard MPC format, e.g., `2024 AA1`, `1995 XA`
- **packed:** Century letter + year + half-month + cycle + letter,
  e.g., `K24A01A` = 2024 AA1

## Band Corrections

Magnitudes reported in non-V bands are corrected to approximate V-band using
offsets from the MPC's [Band Conversion table](https://minorplanetcenter.net/iau/info/BandConversion.txt).
See [docs/band_corrections.md](../docs/band_corrections.md) for the full
correction table.

## NULL Handling

- `median_v_magnitude` may be NULL if no observations in the tracklet have
  a reported magnitude
- All other columns are non-NULL for matched NEAs

## Coverage

NEAs present in NEA.txt but lacking a discovery observation (`disc = '*'`)
in obs_sbn will not appear in the output. As of 2026-02-07, this affects
2 of 40,807 NEAs (2009 US19 and 2024 TZ7).

For ~7% of NEAs where the discovery observation has no tracklet identifier
(`trksub IS NULL`), statistics are computed from the single discovery
observation rather than the full tracklet.
