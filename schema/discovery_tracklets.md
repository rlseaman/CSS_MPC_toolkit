# Schema: NEO Discovery Tracklets

## Output CSV

**Filename:** `NEO_discovery_tracklets.csv`

| # | Column | Type | Example | Description |
|---|--------|------|---------|-------------|
| 1 | `primary_designation` | text | `433` or `2024 AA1` | Asteroid number (for numbered) or provisional designation (for unnumbered) |
| 2 | `packed_primary_provisional_designation` | text | `00433` or `K24A01A` | MPC packed format designation |
| 3 | `avg_mjd_discovery_tracklet` | numeric(6) | `60345.123456` | Mean Modified Julian Date of all observations in the discovery tracklet |
| 4 | `avg_ra_deg` | numeric(5) | `123.45678` | Mean Right Ascension in decimal degrees (J2000) |
| 5 | `avg_dec_deg` | numeric(5) | `-12.34567` | Mean Declination in decimal degrees (J2000) |
| 6 | `median_v_magnitude` | numeric(2) | `21.30` | Median apparent V-band magnitude, with band corrections applied |
| 7 | `nobs` | integer | `4` | Number of observations in the discovery tracklet |
| 8 | `span_hours` | numeric(4) | `1.2345` | Time span from first to last observation in the tracklet, in hours. Zero for single-observation tracklets |
| 9 | `rate_deg_per_day` | numeric(4) | `12.3456` | Great-circle rate of motion between first and last observation, in degrees/day (Haversine). NULL for single-observation tracklets |
| 10 | `position_angle_deg` | numeric(2) | `135.67` | Position angle of motion: 0°=N, 90°=E, range [0, 360). Spherical bearing formula. NULL for single-observation tracklets |
| 11 | `discovery_site_code` | text | `703` | MPC observatory code where the discovery observation was made |
| 12 | `discovery_site_name` | text | `Catalina Sky Survey` | Observatory name from the `obscodes` table. NULL if code not in `obscodes` |

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
- `rate_deg_per_day` and `position_angle_deg` are NULL for single-observation
  tracklets (where `span_hours = 0`)
- `discovery_site_name` may be NULL if the observatory code is not in `obscodes`
- All other columns are non-NULL for matched NEAs

## Coverage

NEOs are selected from `mpc_orbits` using orbital criteria
(`q < 1.32 AU` or `orbit_type_int IN (0, 1, 2, 3, 20)`). This includes
near-Earth comets. Objects without orbits in `mpc_orbits` are excluded.

NEOs lacking a discovery observation (`disc = '*'`) in `obs_sbn` will not
appear in the output. As of 2026-02-08, this affects 2009 US19 and
2024 TZ7. Additionally, 2020 GZ1 has no orbit in `mpc_orbits`.

Total output: 43,629 NEO discovery tracklets.

For ~7% of NEAs where the discovery observation has no tracklet identifier
(`trksub IS NULL`), statistics are computed from the single discovery
observation rather than the full tracklet.
