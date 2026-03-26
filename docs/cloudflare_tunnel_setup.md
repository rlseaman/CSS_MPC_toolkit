# Cloudflare Tunnel — Interim Deployment

Temporary external access to the Planetary Defense Dashboard while
waiting for provisioning of a University of Arizona server.  The app
runs locally on a Mac; Cloudflare Tunnel provides a secure public
HTTPS URL with no port forwarding, no firewall changes, and no
changes to the Dash app's `host="127.0.0.1"` binding.

## Current Setup (2026-03-26)

| Component | Detail |
|-----------|--------|
| Host | M1 Max MacBook Pro, 64 GB, macOS |
| App | `python app/discovery_stats.py` on `localhost:8050` |
| Tunnel | `cloudflared tunnel --url http://localhost:8050` (quick tunnel) |
| URL | Random `https://xxx.trycloudflare.com` (changes on restart) |
| Cloudflare account | Free tier, created 2026-03-26 |
| Domain | Nameservers switched to Cloudflare; propagation pending |

### Verified working on

- iPad (Safari, Wi-Fi and cellular)
- iPhone (Safari — functional but impractical on small screen)

## How It Works

```
iPad/Browser
    │
    │  HTTPS
    ▼
Cloudflare Edge (lax05)
    │
    │  QUIC (outbound from Mac)
    ▼
cloudflared on Mac ──▶ localhost:8050 (Dash app)
```

The tunnel is an **outbound-only** connection from the Mac to
Cloudflare's edge network.  No inbound ports are opened on the Mac
or router.  The app continues to bind to `127.0.0.1` — only
`cloudflared` can reach it locally.

## Quick Tunnel (no account needed)

For ad-hoc testing.  URL is random and changes on every restart.

```bash
# Install (one time)
brew install cloudflared

# Start tunnel (in a dedicated terminal window)
cloudflared tunnel --url http://localhost:8050
```

Look for the `https://....trycloudflare.com` URL in the output.
Ctrl-C to stop.

## Named Tunnel (stable URL, requires account + domain)

After Cloudflare activates the domain (nameserver propagation,
typically 1-4 hours):

```bash
# Authenticate (one time — opens browser)
cloudflared tunnel login

# Create a named tunnel
cloudflared tunnel create neo-dashboard

# Configure the tunnel
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: neo-dashboard
credentials-file: /Users/seaman/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: neo-dashboard.YOURDOMAIN.com
    service: http://localhost:8050
  - service: http_status:404
EOF

# Create DNS record pointing subdomain to tunnel
cloudflared tunnel route dns neo-dashboard neo-dashboard.YOURDOMAIN.com

# Run the tunnel
cloudflared tunnel run neo-dashboard
```

The URL `https://neo-dashboard.YOURDOMAIN.com` will be stable across
restarts.

## Migration to M2 Mac Mini

When the M2 Mac Mini is connected at home (hardwired ethernet):

1. Install `cloudflared` on the Mini: `brew install cloudflared`
2. Copy tunnel credentials: `~/.cloudflared/<TUNNEL_ID>.json` and
   `~/.cloudflared/config.yml`
3. Install as a launch daemon for automatic startup:

```bash
sudo cloudflared service install
sudo launchctl start com.cloudflare.cloudflared
```

4. The DNS record (`neo-dashboard.YOURDOMAIN.com`) does not change —
   Cloudflare routes to whichever machine is running the tunnel.

The MacBook tunnel can then be stopped.

## Pending Hardening Steps

These are recommended by Cloudflare during onboarding but are not
blockers for basic operation:

- **Disable DNSSEC at old hosting provider** — avoids conflicts with
  Cloudflare's DNS.  Find the DNSSEC settings in the old provider's
  domain management panel and turn them off.
- **Origin IP lockdown** — restrict the origin server to accept
  connections only from Cloudflare IP ranges.  Less relevant for
  the tunnel model (where the origin binds to localhost), but good
  practice if the app ever binds to `0.0.0.0`.
- **Cloudflare Access** (optional) — add authentication (email OTP,
  Google/GitHub login) in front of the tunnel so only authorized
  users can reach the dashboard.  Configured in the Cloudflare
  Zero Trust dashboard; free for up to 50 users.

## Relationship to University Deployment

This tunnel setup is a temporary bridge.  The long-term deployment
target is a UA-network server (Rocky Linux) using nginx as a reverse
proxy, as described in `docs/deployment.md`.  The Cloudflare tunnel
could remain as an additional access path if desired, or be
decommissioned once the university server is live.

## Comparison of Deployment Paths

| Aspect | Cloudflare Tunnel (current) | UA Server (planned) |
|--------|----------------------------|---------------------|
| Host | Mac (MacBook, then Mini) | Rocky Linux VM |
| Proxy | Cloudflare edge | nginx reverse proxy |
| TLS | Automatic (Cloudflare) | Campus cert (InCommon) |
| Auth | Optional (Cloudflare Access) | Campus VPN / firewall |
| Uptime | Best-effort (home internet) | University network SLA |
| Daily refresh | Cron on Mac | Cron + systemd service |
| Database access | Via SSH tunnel to sibyl | Direct network access |
