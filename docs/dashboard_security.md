# Dashboard Security Posture

## Overview

Security notes for the publicly-reachable Planetary Defense Dashboard
at `https://hotwireduniverse.org` (and `www.`).  The dashboard is
intentionally public — it serves read-only views over publicly-sourced
MPC data, with no user input, no credentials, and no write paths — so
the threat model is narrow: **availability and abuse**, not
confidentiality or integrity.

## Current Setup (as of 2026-04-15)

### Attack-surface posture

- **No inbound ports on home router** — the Mac Mini reaches Cloudflare
  via an outbound `cloudflared` tunnel; no port forwarding.
- **Home origin IP not in DNS** — all records for `hotwireduniverse.org`
  and `www.` are proxied CNAMEs to Cloudflare's edge
  (104.21.x.x / 172.67.x.x / 2606:4700:x).  An attacker who doesn't
  already know the ISP IP cannot bypass Cloudflare.
- **Read-only app** — no login, no sessions, no state mutation.
- **Public data** — all displayed data is derived from the public MPC
  database; exfiltration is a non-threat by definition.
- **`suppress_callback_exceptions=True`** in Dash config (prevents
  traceback leakage in responses).
- **Dash debug mode off** (no `/debug` code-execution surface).

### Cloudflare protections enabled

1. **Bot Fight Mode** (Security → Bots) — free-plan JS challenges
   against obvious bot fingerprints.
2. **Rate limiting rule** (Security → WAF → Rate limiting):
   - Name: `Dash callback rate limit`
   - Expression:
     `(http.request.uri.path contains "/_dash-update-component" and http.request.method eq "POST")`
   - Characteristics: IP address
   - Threshold: **200 requests / 10 seconds** (revised 2026-04-15,
     see "Threshold sizing" below)
   - Action: Block for 10 seconds (only option on free tier)
   - Rationale: scoped narrowly to the Dash callback endpoint so
     static asset fetches and the initial GET aren't rate-limited.
     Threshold covers sustained rapid interactive use while still
     catching sustained scraping (30+ req/sec).

### Threshold sizing

Each MPEC click triggers roughly 8 Dash callbacks, each a separate
POST to `/_dash-update-component` (show detail, observation timeline,
observability chart, enrichment poll, item-style update, plus the
click handler itself).  The first rule set on 2026-04-15 used
20/10s based on a naïve assumption of "a few POSTs per click" —
in reality even slow human exploration (3-4 clicks per 10s) hits
24–32 POSTs and trips the rule, causing the browser to silently
drop callbacks and the MPEC viewer to appear stuck after 3-5 clicks.
Raised to 200/10s later the same day.

Budget bands, for future recalibration:

| Traffic pattern | POSTs / 10s |
|---|---|
| Casual click exploration (2–3 clicks/10s × 8) | 16–24 |
| Rapid click exploration (5–10 clicks/10s × 8) | 40–80 |
| Aggressive but still-human clicking (~15 clicks/10s) | ~120 |
| Scraper / sustained abuse (30+ req/sec) | 300+ |

200/10s fits the "aggressive human" band with margin and still
catches the abuse band.

### Verification

Rate-limit rule verified firing correctly on 2026-04-15 with the
original 20/10s threshold: 30 back-to-back POSTs to
`/_dash-update-component` returned `415 × 19` (passed to origin —
Dash rejects empty POST bodies) followed by `429 × 11` (blocked at
edge), elapsed 3 s.  After raising to 200/10s, the same probe
should return `415 × 30` (all passed).

### Outbound politeness: 5 req/s throttle to MPC

The 200/10s front door admits up to 20 req/sec in short bursts,
which could in principle drive ~20 req/sec of MPC fetches if a
caller targets never-cached MPEC paths.  Since "MPC blacklisting
our user-agent" is the most plausible material denial-of-service
scenario for the dashboard, add a defense-in-depth outbound
throttle at `lib/mpec_parser.py::_mpc_throttle`: a thread-safe
paced scheduler that enforces a minimum 200 ms gap between any
outbound MPC request (5 req/sec absolute ceiling).  Applies to:

- `_fetch_url` — individual MPEC pages + `RecentMPECs.html`
- `lookup_mpecs_by_designation` — MPC's `data.minorplanetcenter.net/api/mpecs`

Under normal use the throttle is invisible (the cache handles
most traffic, and sparse requests absorb its idle budget with
0 ms latency).  Under hostile load, concurrent callers serialize
fairly — verified with 10 concurrent threads emerging at exactly
~200 ms intervals.  MPC will see at most 5 req/sec from us
regardless of what the frontend is doing.

## Hardening Backlog

Three items deliberately deferred.  None are urgent given the threat
model, but each is worth doing when time allows.  Ordered by
effort-per-risk-reduction.

### 1. Put Dash under launchd on the Mini

**Problem:** `cloudflared` already runs under `launchd` (agent
`com.cloudflare.tunnel`, survives reboots), but the Dash process does
not.  It's started via `nohup` by `scripts/deploy_to_mini.sh` Step 3
and tracked via `~/CSS_MPC_toolkit/app/.dash.pid`.  A Mini reboot
(macOS update, power cut) brings the tunnel back but not Dash —
the site returns 502 until someone manually re-runs the deploy.

**Fix:** create `~/Library/LaunchAgents/com.rlseaman.dashboard.plist`
with `KeepAlive=true`, `RunAtLoad=true`, invoking
`./venv/bin/python app/discovery_stats.py --serve-only`
from `/Users/robertseaman/CSS_MPC_toolkit`.  Update
`deploy_to_mini.sh` Step 3 to `launchctl kickstart -k` the agent
instead of killing the PID file and `nohup`-ing anew.

**Effort:** ~30 minutes.

**Risk reduction:** restores availability automatically after any
reboot, not just after a manual deploy.  Small but real.

### 2. Swap Flask dev server for gunicorn or waitress

**Problem:** the app runs on Flask's built-in development server.
`app/dash.log` on the Mini shows:

```
WARNING: This is a development server. Do not use it in a
production deployment. Use a production WSGI server instead.
```

Concrete weaknesses: single-threaded by default (slow requests block
others); weaker error isolation (an unhandled callback exception can
crash the whole process); not hardened against malformed HTTP.  Fine
behind Cloudflare's rate limiting for small audiences, but it's the
weakest link in the serving stack.

**Fix:** on macOS, `waitress` is simpler than `gunicorn` (pure
Python, no fork/exec issues).  Install into the venv, then:

```
./venv/bin/waitress-serve --port=8050 --threads=4 \
    --call 'app.discovery_stats:_get_server'
```

Requires exposing a `_get_server()` helper, or using `app.server`
directly since Dash wraps Flask.  The existing `app.run_server(...)`
call stays in place as a dev-only path.  Pair with item #1 so launchd
invokes waitress, not python directly.

**Effort:** 30–60 minutes including a sweep of all five tabs under
multi-threaded serving (look for module-global state that assumes
single-threaded access — there shouldn't be any, but worth verifying).

**Risk reduction:** removes the largest "known weak link" in the
stack.  Also improves concurrent-user responsiveness, which may
matter if the dashboard ever gets modest traffic.

### 3. Periodic dependency audit

**Problem:** pandas 3.0, Dash 4.1, Flask 3.1, etc. all receive security
updates.  Not urgent for a read-only data app where the realistic
threat is "crash the service" rather than "achieve RCE," but now that
the app is on the public internet, known-CVE drift is worth checking.

**Fix:** every ~3 months:

```
./venv/bin/pip list --outdated
./venv/bin/pip install pip-audit
./venv/bin/pip-audit
```

Review, bump `requirements.txt` conservatively (avoid crossing major
versions without testing all tabs), and redeploy.  Pin by version
range so `pip install -r requirements.txt` stays reproducible.

**Effort:** 15 minutes per audit unless a CVE forces a major bump.

**Risk reduction:** catches CVEs before they become exploitable.
Low-probability but cheap insurance.

## Intentionally NOT Doing

- **Cloudflare Access / auth of any kind** — the dashboard's purpose
  is public outreach; auth defeats that purpose.
- **Origin certificate pinning** — no inbound ports, so moot.
- **Custom WAF rule ladder** — one rate-limit rule is sufficient for
  the actual traffic profile.  More rules add maintenance cost and
  false-positive risk without material gain.

All of these remain options if the threat model ever shifts (e.g.,
if the app ever accepts user input, stores state, or serves
non-public data).
