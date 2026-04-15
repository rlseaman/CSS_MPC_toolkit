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
   - Threshold: 20 requests / 10 seconds
   - Action: Block for 10 seconds (only option on free tier;
     mathematically equivalent to 120/min)
   - Rationale: scoped narrowly to the Dash callback endpoint so
     static asset fetches and the initial GET aren't rate-limited;
     threshold sized to clear realistic interactive bursts
     (rapid filter changes can fire 15–20 POSTs/s) while catching
     sustained scraping.

### Verification

Rate-limit rule verified firing correctly on 2026-04-15:
30 back-to-back POSTs to `/_dash-update-component` returned
`415 × 20` (passed to origin) followed by `429 × 10` (blocked at edge),
elapsed 3 s.

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
