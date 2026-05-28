"""Shared constants for the `lib` package."""

# Canonical User-Agent for outbound HTTP requests from interactive paths.
# Identifies the dashboard so external services (JPL, MPC, NEOfixer, NEOCC)
# can attribute traffic to us, and embeds a contact URL + email so they can
# reach us before they block our IP.  Standardised 2026-05-28 across
# `api_clients`, `mpec_parser`, `horizons`, `sbdb_moid`, and `neo_list`.
# The four `neo_consensus_*` modules keep a local `USER_AGENT` carrying a
# `(consensus ingest)` tag so the nightly batch is distinguishable from
# interactive traffic in upstream access logs.
USER_AGENT = ("CSS-MPC-Toolkit/1.0 "
              "(+https://hotwireduniverse.org; contact@hotwireduniverse.org)")
