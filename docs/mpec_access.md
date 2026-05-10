# MPEC Access: Querying Historical Minor Planet Electronic Circulars

**Status:** Research / scoping note, 2026-05-02. No implementation yet.
**Motivation:** Enable MPEC-level questions ("which MPECs report
observations from station V00?", "tally MPECs by year by station",
"find Editorial MPECs mentioning the CSS follow-up program") that the
current toolkit cannot answer from `obs_sbn` alone.
**Related:** [`source_tables.md`](source_tables.md) §`obs_sbn.ref` — the
`ref` column is mutable and loses the discovery-MPEC pointer once an
observation is republished in an MPS supplement, so `obs_sbn` is *not*
a historical MPEC index.

## The use case

The MPEC Browser tab in the dashboard already lets a user open one
MPEC at a time. The questions we cannot currently answer:

- List all MPECs that mention a given station code (e.g. V00).
- Tally MPECs by year × station × type (Discovery, Daily Orbit Update,
  Editorial, Retraction, …).
- Search MPEC narrative text for arbitrary phrases (programme names,
  observer credits, comet redesignations, named collaborators).

These are MPEC-document questions, not observation questions. The
underlying data lives in MPEC bodies, and `obs_sbn` only carries a
snapshot of the *most recent* publication per observation.

## Existing data sources, surveyed

### NASA ADS — metadata only
MPECs have ADS bibcodes in the form `YYYYMPEC....X..NNNL` and are
searchable by `bibstem:MPEC` plus designation. **Bodies are not in the
ADS full-text index** — `body:V00` returns nothing useful. ADS treats
MPECs as bibliographic stubs (title + first author).

### MPC's own MPEC search (`/mpcops/mpecs/`, REST API documented at
`docs.minorplanetcenter.net`) supports designation, MPEC title, and
MPEC number with date range. **No body-level search.** No documented
bulk-download endpoint, no rsync feed.

### NEOCC, NEODyS, JPL SBDB/CNEOS, AstDyS
All ingest the *observations* from new MPECs (NEOCC polls every 30
min) but expose object/orbit-level views, not MPEC-document search.

### Community packages
Asteroid Institute `mpcq`, `astroquery.mpc`, `pympc`,
`seap-udea/MPCDatabase` — all object/observation-level. None index
MPEC bodies.

### MPEC Watch (the closest existing thing)
**The most relevant prior art.** Built by Quanzhi Ye and Taegon
Hibbitts at the SBN-MPC node, U. Maryland, since Jan 2022; refreshed
nightly; covers 1993 → present. Site:
<https://sbnmpc.astro.umd.edu/mpecwatch/>. Code:
<https://github.com/Yeqzids/mpecwatch> (Python, 288 commits, last
change Oct 2025).

What MPEC Watch does:

- Parses every MPEC body, classifies into Editorial / Discovery /
  OrbitUpdate / DOU / ListUpdate / Retraction / Other.
- Splits Discoveries into NEA / PHA / Comet / Sat / TNO / Unusual /
  Interstellar / Unknown.
- Builds per-station, per-survey, per-observer/measurer/facility
  pages with annual breakdowns.
- Stores results in a local **SQLite** with tables `MPEC`, `Objects`,
  `MPECObjects`, `DOUIdentifier`, `LastRun`, `MPEC_Stations`, plus a
  per-station dynamic `station_<code>` table.

What it does **not** do:

- Publish the SQLite, JSON, or any other machine-readable artifact.
  `.gitignore` excludes `*.db*` and `*.json`. No GitHub releases.
- Expose an API. CSV download buttons exist on individual yearly
  tables, populated client-side by bootstrap-table.
- Carry a license. Code reuse is murky; data licensing inherits from
  MPC.
- Honour `Crawl-delay: 20`. The scraper has no `time.sleep()` and no
  robots.txt check; it does not skip the K00–K16 disallow block.

#### Classified V00 stats from MPEC Watch (verbatim, 2026-05-01 build)

URL: <https://sbnmpc.astro.umd.edu/mpecwatch/byStation/station_V00.html>
("V00 Kitt Peak-Bok"). First V00 entry late 2019; cumulative **~2,028
MPECs** mention V00 across 2020–2026. Annual breakdown:

| Year     | Total | Discovery | OrbitUpdate | DOU | Follow-Up | 1st F/U |
|----------|------:|----------:|------------:|----:|----------:|--------:|
| 2026 YTD |   259 |       181 |          18 |  41 |        15 |       4 |
| 2025     |   568 |       360 |          54 | 101 |        42 |      11 |
| 2024     |   391 |       219 |          29 |  80 |        48 |      15 |
| 2023     |   278 |       151 |          27 |  68 |        25 |       7 |
| 2022     |   306 |       187 |          17 |  70 |        21 |      11 |
| 2021     |   165 |        91 |          17 |  41 |        12 |       4 |
| 2020     |    61 |        34 |           2 |  16 |         6 |       3 |

No Editorial or Retraction MPECs reference V00 in this window.

These are the numbers we'd need to be able to reproduce — and
extend with arbitrary additional cuts — from a local index.

## Why `obs_sbn` doesn't answer the V00 question

`obs_sbn.ref` carries a publication reference per observation, but it
is **overwritten** each time the observation is republished. Once an
observation lands in an MPS supplement (typically within a year of
the original MPEC), the MPEC pointer is lost from `obs_sbn`. See
[`source_tables.md`](source_tables.md) §`obs_sbn.ref` for the empirical
V00 counts that demonstrate the rolling one-year snapshot.

Implication: snapshot-style questions ("what is *currently* tagged
to MPEC X in obs_sbn?") work from `obs_sbn.ref`. Historical
MPEC-archive questions need an external corpus.

## Resource estimate for our own crawl

- **Total MPECs:** series began Sep 1993; ~10/day current rate
  dominated by Daily Orbit Updates. Cumulative **~50–70k** as of
  May 2026. MPEC Watch reports **4,449 in 2025** and **1,461 in
  2026 YTD** to give a calibration point.
- **Bytes:** substantive content ~3–4 KB per MPEC, full HTML
  ~12–15 KB. **Whole corpus ≈ 700 MB – 1 GB HTML, ~200–300 MB
  stripped text.**
- **Indexed (Postgres `tsvector` table):** ~300 MB on disk.
- **Politeness budget:** at the documented `Crawl-delay: 20`, a full
  backfill is **~14 days** of background fetch. A targeted backfill
  (one MPEC per NEO discovery, ~44k from `discovery_tracklets`,
  K17+ only) is **~10 days** and ~150 MB on disk.
- **Incremental:** ~10 new MPECs/day; trivially absorbed by an
  hourly poll of `RecentMPECs.html`.

## Politeness and licensing constraints

- `minorplanetcenter.net/robots.txt` sets **`Crawl-delay: 20`** for
  `*`, **disallows `/iau/mpec/K00/` through `/iau/mpec/K16/`** (years
  2000–2016), and blocks Internet Archive, Google, OpenAI, ClaudeBot,
  and most major crawlers. No rsync feed for MPEC bodies.
- The dashboard's existing 5 req/s throttle (in
  `lib/mpec_parser.py::_mpc_throttle`) is fine for *interactive*
  user-driven access but is **~100× faster than the documented limit**
  for any wholesale fetch. Bulk crawler must drop to ≤ 1 req / 20 s.
- Read literally, scraping the K00–K16 archive violates robots.txt.
  Any historical backfill should either restrict to K17+ or obtain
  explicit MPC permission.
- Email `mpc@cfa.harvard.edu` (Peter Vereš / Matt Payne) before
  systematic backfill. They may simply hand over an archive — which
  also resolves the licensing question.

## Recommended path forward

In order, smallest commitment first:

1. **Confirm `obs_sbn.ref` boundaries.** Audit by year: how far back
   the MPEC pointer survives republishing, what fraction of pre-2023
   rows still show an `MPEC` ref vs. an `MPS` ref. This bounds how
   much of the question `obs_sbn` can already answer without crawling.
2. **Borrow MPEC Watch's classification logic.** Their type taxonomy
   (Editorial / Discovery / OrbitUpdate / DOU / ListUpdate /
   Retraction / Other) and station-code parsing are the work we'd
   otherwise rebuild. Code is on GitHub; license is unstated, so
   treat as reference rather than direct dependency until clarified.
3. **Email MPC and the MPEC Watch maintainers** before crawling. The
   path of least resistance is an archive handoff or a sanctioned
   API; absent that, a politeness-coordinated crawl plan.
4. **Targeted backfill.** Discovery MPECs only (~44k, one per NEO from
   `discovery_tracklets`), K17+, ≤ 1 req / 20 s, ~10 days background.
   Reuses the existing `app/.mpec_cache/` shape on disk.
5. **Local index.** Postgres table `mpec_archive(mpec_id, year, type,
   issued_at, body_text, body_tsv)` plus a `mpec_stations(mpec_id,
   stn)` junction. Station tallies become a one-line group-by;
   arbitrary text search becomes a `tsvector` query. Sized at
   ~300 MB indexed for the targeted corpus.
6. **Cross-check against MPEC Watch.** Reproduce the V00 table above
   from our local index as a correctness gate before exposing the
   data to the dashboard or to CSS users.

## Open questions

- Does MPC's `mpcops` REST API ([docs.minorplanetcenter.net](
  https://docs.minorplanetcenter.net/)) include any MPEC-body
  endpoint we missed? The documented MPEC search is
  metadata-only, but the API surface is growing.
- Are MPS bodies (the supplements that overwrite `obs_sbn.ref`)
  themselves indexable? They are persistent (supplements don't get
  re-supplemented), so an MPS index would close the historical gap
  without needing the K00–K16 archive at all.
- Is there a CSS-internal copy of the historical MPEC archive
  predating MPC's robots.txt restrictions that we could use as a
  starting corpus?

## Other issues worth flagging

- MPEC bodies are plain ASCII inside `<pre>` — parsing is trivial.
  Observations are obs80 (handled by `lib/mpc_convert.py`); station
  codes appear in cols 78–80 of each obs line.
- MPEC filenames use a base-62-ish packed serial encoding above 99
  (`K25FM7.html` → `2025-F227`). Same scheme as packed designations,
  so `lib/mpc_convert.py` can be reused.
- Daily Orbit Update MPECs are ~50% of the volume and are largely
  redundant with `obs_sbn` for observation-level questions; they
  are *not* redundant for "which MPECs mention station X."
- No DOI or stable JSON representation of MPECs exists. Any local
  artifact is the project's own; cite MPEC numbers, not local IDs,
  in any user-facing output.
- Non-NEO MPECs (comets, distant objects, asteroid satellites, the
  long-running periodic Daily Orbit Updates) are noise for some
  questions and signal for others — keep type classification
  available as a filter rather than baking it into the schema.
