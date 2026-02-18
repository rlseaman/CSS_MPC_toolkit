# CSS MPC Toolkit — Project Overview

## Intent

This project — **CSS MPC Toolkit** — exists to extract,
transform, and present value-added datasets from the Minor Planet
Center's database, with a particular focus on Near-Earth Object
discovery statistics. The MPC database is the authoritative global
clearinghouse for asteroid and comet astrometry, but the raw tables
(526M+ observations, 1.5M orbits) are not easily interrogated for the
kinds of questions that matter to the survey community: *who is finding
NEOs, how fast, how completely, and how well is the follow-up network
functioning?* This project bridges that gap, turning a replication of
the MPC PostgreSQL database into actionable analytics.

## Stakeholder

You are a member of the Catalina Sky Survey at the University of
Arizona's Lunar and Planetary Laboratory — the most prolific NEO
discovery survey in history. As a stakeholder, you sit at the
intersection of operations and science: you care about CSS's
contribution to planetary defense, but you also care about the broader
ecosystem of surveys that discover, confirm, and characterize NEOs. The
project carries the "SBN" label (Small Bodies Node of NASA's Planetary
Data System), suggesting these derived products are intended to be
archival-quality, reproducible, and potentially deliverable to NASA as
part of CSS's data obligations.

## The Planetary Defense Community

The Planetary Defense community is the global network of observers,
modelers, and agencies tasked with finding and characterizing all NEOs
that could impact Earth. This includes the survey telescopes (CSS,
Pan-STARRS, ATLAS, the upcoming Rubin/LSST), follow-up networks (dozens
of smaller stations worldwide), orbit computers at the MPC and JPL, and
the coordinating bodies — NASA's Planetary Defense Coordination Office
(PDCO) and the IAU.

## What motivates the Planetary Defense community?

A central question driving the field has been *completeness*: what
fraction of the hazardous population have we found, and how quickly
are we closing the gap? Congress mandated finding 90% of NEOs larger
than 140 meters, and we've only found about 50% of them.

This is not the only goal, tools like NEOfixer (https://neofixer.arizona.edu)
focus on improving the catalog of objects that are already known by
reducing on-sky uncertainties with the resulting improvement to
their orbits.

A solid Planetary Defense also implies and requires a robust
Planetary Science community focus on small bodies in the solar system.
This is far broader than this single project can grapple with. We seek
to provide infrastructure to better enable researchers (professionals
and amateurs) to better grapple with their own projects.

## The Dashboard

The interactive Dash application (`discovery_stats.py`) is one
deliverable so far. It can provide an example for one paradigm for
building additional community tools, whether developed at CSS or elsewhere.

Its five tabs tell one coherent story: Tab 1 shows the historical arc
of discovery (who found what, when), Tab 2 benchmarks that progress
against the NEOMOD3 debiased population model (how complete are we,
really?), Tab 3 examines survey overlap and co-detection during discovery
apparitions (are surveys duplicating effort or covering complementary sky?),
Tab 4 quantifies the follow-up network's response time (how optimally does
the community secure orbits after initial detection?), and Tab 5 maps the
discovery circumstances themselves (where on the sky, at what brightness
and rate of motion). There are other coherent stories.

### Open question: What other stories?

The current dashboard tells a discovery-survey-performance story. Other
coherent narratives that the same infrastructure could support include:

- **Population story** — How does the size distribution evolve over
  time? Are we finding smaller objects faster, or just more of the same?
- **Individual-object lifecycle** — From NEOCP candidate to
  well-characterized orbit: how long does it take, and where are the
  bottlenecks?
- **Observing strategy** — Given finite telescope time, what is the
  optimal allocation between discovery and follow-up? Between different
  sky regions or solar elongations?
- **Planetary science** — Physical properties, taxonomic types, and
  dynamical families for the broader small-body population (beyond NEOs)
- **Data quality** — Astrometric residuals, photometric consistency,
  and catalog biases across stations and time

Which of these (or others) are most valuable to the community? This
question should inform what the next dashboard or notebook explores.

## Library and Domain Knowledge

The supporting library layer (`lib/`) and SQL scripts encode hard-won
domain knowledge: how to derive semi-major axes from cometary elements
when Keplerian values are missing, how to classify orbits when
`orbit_type_int` is NULL for a third of the catalog, how to group
observations into tracklets, and how to handle the many data quality
quirks in the MPC schema. This institutional knowledge, codified in
reusable Python and SQL, is arguably as valuable as the app itself — it
makes future analysis reproducible rather than locked in someone's head.

## Forward-Looking

The modular architecture — separate lib, SQL, app, and notebook
layers — is designed to support new analyses without rewriting
infrastructure.

## Claude's Suggested Next Steps

1. **Tab 6: Survey Efficiency / Detection Limits** — You have discovery
   circumstances (mag, rate, PA, sky position) per survey. Combining
   these with non-detections or the NEOMOD3 size-frequency distribution
   could yield per-survey detection efficiency curves (completeness as a
   function of H, rate, and galactic latitude). This is the natural next
   analytical question after "what have we found" — *what are we
   missing, and why?*

2. **Deployment hardening** — The app is production-capable in principle
   (cron refresh + CSV cache), but there's no `Dockerfile`, no
   `gunicorn` config, no health endpoint, and no automated cache refresh
   script beyond `--refresh`. Packaging it for a persistent internal
   deployment (even just a systemd service on a lab server)
   would make the dashboard available to the team without someone
   running it locally.

3. **Data export / API layer** — Several of the derived datasets (the
   43K discovery tracklets, the survey co-detection matrix, the
   follow-up timing statistics) would be valuable to collaborators and
   to SBN as standalone data products. Adding a "Download CSV" button
   per tab, or a small Flask/FastAPI endpoint serving the cached data,
   would make the project useful beyond the interactive dashboard.

## Some broader context from Rob

I have found Claude to be a useful tool for working on a variety of
projects, both inside and outside planetary defense. This particular
project, currently called "CSS_MPC_toolkit", is one oddly-shaped piece
in a larger strategy. Maybe we can come up with a better name? I am
also unsure if we have identified the full bumpy contour of this piece.

Here are some goals (they may not yet be complete) of this project:

A. Come up with a more descriptive name. Improve the documentation.

B. Tuning, health checks, and management tools for a replicated copy
   of the MPC/SBN public PostgreSQL database.

C. Helper functions, indexes, SQL schema improvements, SQL usage
   features to add value to what MPC and SBN provide themselves.

D. A library/API to support E and F.

E. A developer/maintainer workbench. This is currently realized as
   diverse Jupyter Notebooks. I have yet to drill down to the
   specificity of issues requiring these.

F. A public dashboard which is both useful for a (narrow) range of
   use cases, and that can serve as an example for other such apps.

There are also some prerequisites and opportunities. Some of these
may be addressed in this project, and others in other projects or
by other stakeholders entirely:

G. Standards. I deleted your somewhat over-enthusiastic mention of
   ADES. Rather, ADES is one standard and it made sense to see what
   could be done to enable its generation from the NEOCP. There are
   other standards. For instance, for nomenclature, see:

      https://github.com/rlseaman/MPC_designations

H. External libraries. These might serve either directly, or as
   example code for refactoring into SQL or something in the internal
   library layer here. I'm not sure we're at the point of elaborating
   the current project yet. And indeed, some features might be better
   implemented as methods in a calling Python application (for
   instance).

I. Data fusion. One way to add value to MPC/SBN assets is to combine
   them with assets from their own flat files, or CNEOS, or NEOfixer.
   I am reticent about encouraging you to pursue these opportunities
   within this project, but users of the infrastructure developed
   here (including other Claude projects) might well have that in
   mind.
