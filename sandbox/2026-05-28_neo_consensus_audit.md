# NEO Consensus tab — alias + disagreement audit (snapshot 2026-05-28)

Snapshot probe of `css_neo_consensus.source_membership` (250,885 rows) and the
displayed `v_membership_wide` view (41,969 NEA primaries) against
`current_identifications` + `numbered_identifications`.

Reproducible via `psql -h /tmp -U claude_ro mpc_sbn -f sql/consensus_audit.sql`.

NEA scope only (`v_membership_wide` already applies `WHERE NOT is_comet`).

## Headlines

| metric | value |
|---|---|
| primaries displayed (NEA) | 41,969 |
| all-six-agree | 41,604 |
| disagreements | **365** |
| secondary-designation aliases across all sources | **15 rows** |
| disagreements that would close upon collapsing aliases | **7 → 358** |

The alias problem at this layer is **tiny**: 15 rows out of a quarter-million,
1.9 % of disagreements. The substantive 358 are real semantic differences
between the lists, not data-lineage errors.

## NEOfixer comets are a feature, not a bug

NEOfixer ships **137 periodic comets** (1P/Halley, 2P/Encke, 12P, 13P, …, 218P,
including the 141P-A/D/H/I fragments) in its NEO endpoint.  Every one of those
rows has `is_comet=true` in `source_membership`, and `v_membership_wide`'s
`WHERE NOT is_comet` filter omits them from the displayed tab.  So they do
**not** contribute to any of the 365 disagreements above; they're correctly
filtered and not visible in the NEO Consensus comparison.  Worth telling
NEOfixer "we see these, we drop them at display time per our NEA-only scope,
let us know if that's wrong on either side."

## Per-source exception tables

### MPC (NEA.txt) — 2 alias rows (case B, both still listed)

| reported in NEA.txt | resolves to | note |
|---|---|---|
| `2010 MZ112` | `2026 AA14` | also reported by Lowell |
| `2025 XU` | `2010 HK22` | also reported by Lowell |

Both primaries are in all six sources, so each row is a redundant entry
in NEA.txt under a secondary form.

### Lowell (astorb.dat.gz) — 9 alias rows (7 B, 2 D-comet)

| reported in astorb | resolves to | case |
|---|---|---|
| `2010 MZ112` | `2026 AA14` | B (also in mpc) |
| `2025 XU` | `2010 HK22` | B (also in mpc) |
| `2026 DU14` | `2011 EC41` | B |
| `2026 EG2` | `2005 XY4` | B |
| `2026 EK1` | `2015 EX` | B |
| `2026 FM` | `2026 EU3` | B |
| `2026 GF` | `2001 MS3` | B |
| `2025 MN229` | `P/1994 P1` (= 141P/Machholz 2) | D comet |
| `2025 NR197` | `P/1818 W1` (= 2P/Encke)        | D comet |

### CNEOS (JPL SBDB) — 2 alias rows (both D-comet)

| reported | resolves to |
|---|---|
| `2025 MN229` | `P/1994 P1` (= 141P/Machholz 2) |
| `2025 NR197` | `P/1818 W1` (= 2P/Encke)        |

### NEOCC (ESA allneo.lst) — 2 alias rows (both D-comet)

| reported | resolves to |
|---|---|
| `2025 MN229` | `P/1994 P1` (= 141P/Machholz 2) |
| `2025 NR197` | `P/1818 W1` (= 2P/Encke)        |

### NEOfixer — 0 alias rows; separate issues:

#### Issue 1: 137 periodic comets in the NEA-scope endpoint
Feature on NEOfixer's side (it tracks NECs), correctly tagged
`is_comet=true` by our ingestor and filtered by `v_membership_wide`.
Mentioned here so CSS / NEOfixer team can confirm intent.

#### Issue 2: thin Mars-Crosser shell (38 only-NEOfixer rows)
Every one has NEOfixer's `nf_q ≤ 1.300` but **MPC's q > 1.30** for almost all —
i.e. NEOfixer's orbit puts them as NEAs while MPC's orbit puts them as Mars
Crossers.  Per the user's clarification "should be omitted if `q > 1.3 au`",
the current `lib/neo_consensus_neofixer.py` smart q-rule (which only drops
when *NF's own* `q > 1.3`) should add: also drop when `mpc_orbits.q > 1.3`.
Sample:

| desig | nf_q | mpc_q | mpc_e | H |
|---|---|---|---|---|
| 2013 ST24 | 1.234 | 1.392 | 0.189 | 21.3 |
| 2013 TU4  | 1.090 | 1.351 | 0.209 | 20.3 |
| 2020 FH7  | 1.087 | 1.329 | 0.256 | 20.9 |
| 2013 RA74 | 1.281 | 1.326 | 0.286 | 22.9 |
| 2001 DC77 | 1.269 | 1.315 | 0.488 | 19.9 |
| …         |  …    | …     |   …   |  …   |

### mpc_orbits — 0 alias rows. Clean.

### Stale (1 designation, 6 rows across 5 sources)
`2026 JG2` appears in mpc / mpc_orbits / cneos / neocc / lowell / neofixer
but `current_identifications` snapshot doesn't yet contain it.  Will resolve
at the next MPC pull — benign staleness.

## Disagreement composition — why "missing NEOfixer" is the largest class

Top patterns of the 365 disagreements (1 = source has it, 0 = source lacks it):

| mpc | mpcorb | cneos | neocc | nf | low | n  | pattern |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 1 | 1 | **0** | 1 | **99** | **missing only NEOfixer** |
| 0 | 1 | 0 | 0 | 0 | 0 | 71 | in `mpc_orbits` only |
| 0 | 0 | 0 | 0 | 1 | 0 | 38 | only NEOfixer (Mars-Crosser shell above) |
| 1 | 1 | 0 | 1 | 0 | 1 | 35 | missing CNEOS + NEOfixer |
| 0 | 0 | 0 | 0 | 0 | 1 | 21 | only Lowell |
| 1 | 1 | 1 | 1 | 1 | 0 | 17 | missing only Lowell |
| 1 | 0 | 1 | 1 | 0 | 1 | 11 | missing `mpc_orbits` + NEOfixer |
| 0 | 0 | 1 | 0 | 1 | 0 |  8 | CNEOS + NEOfixer only |
| 1 | 1 | 1 | 0 | 1 | 0 |  7 | missing NEOCC + Lowell |
| …   |   |   |   |   |   |  … |  … |

About **40 % of all disagreements involve NEOfixer being absent** (99 + 35 +
11 + scattering = ~150).

### MISSING-FROM-NEOFIXER (n = 99) — two populations

q distribution for the 99:

| q bin (0.05 AU) | count |
|---|---|
| 0.25–0.50 | 13 |
| 0.50–0.95 | 41 |
| 0.95–1.15 | 16 |
| 1.15–1.30 |  5 |
| **1.30** (q ∈ [1.291, 1.300]) | **22** |
| > 1.30 (mpc_orbits boundary) | 2 |

H distribution: median **27.4**, max 33.7, with a clear peak at H = 29–31.

**Population A — boundary-q (22 objects).**  q clustered just below 1.30 AU
(samples 1.2918–1.3000). NEOfixer's own orbit puts q slightly above 1.3, the
current smart q-rule drops them (NF orbit "solid" + NF q > 1.3), while MPC's
orbit keeps them on NEA.txt. Working as intended.

**Population B — faint NEAs (~77 objects).** q across the full NEA range,
median H = 27.4, **half are H ≥ 27**.  Includes recognisable cases like
`2008 TC4` (q = 0.35, H = 21.6).  Pattern strongly suggests NEOfixer
prioritises objects with adequate arc / observability for follow-up
planning; single-tracklet or recently-recovered faint NEAs drop out.

This is the population CSS / NEOfixer might want to understand — happy to
generate a designation-level CSV for it if useful.

## Rubin (X05) implicated in the comet aliases (confirmed empirically)

| comet primary | permid | X05 obs in 2025 | first obs | last obs |
|---|---|---|---|---|
| `P/1994 P1` | **141P/Machholz 2** | 10 | 2025-06-25 | 2025-07-14 |
| `P/1818 W1` | **2P/Encke**         | 23 | 2025-07-11 | 2025-07-21 |

X05 wasn't *formally* the discoverer (the discovery flags transferred to the
comets' real first observations in 1818 and 1994), but in both cases X05 is
the station whose 2025 tracklets MPC initially assigned the provisional
designations `2025 MN229` and `2025 NR197` to, then identified as the known
comets.  Exactly the commissioning phenomenon the user described.

## Recommendations

1. **Display-side flag + checkbox on the Consensus tab.**  Add an
   `is_alias` column and a "Hide secondary designations" checkbox.  At
   15 rows total, this is a *diagnostic surface*, not a UI cleanup —
   useful for the per-source reports to remain visible inside the app.
2. **Per-source exception tables above are the headline deliverable.**
   Each is short enough to email the source organisation.
3. **For NEOfixer (CSS-managed), there is a substantive ingestor change to
   consider:** extend the smart q-rule in `lib/neo_consensus_neofixer.py` to
   also omit when `mpc_orbits.q > 1.3` (today's rule only checks NEOfixer's
   own q).  Would drop the 38-row Mars-Crosser shell.
4. **Re-run this audit monthly.**  Numbers shift as MPC links new objects.
   `sql/consensus_audit.sql` runs in ~3 s on Gizmo.
