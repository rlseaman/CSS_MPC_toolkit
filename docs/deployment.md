# NEO Discovery Statistics Explorer — Deployment Guide

Provisioning and operating the Dash web application on a RHEL/Rocky Linux
server with daily automated data refreshes.

## Architecture Overview

```
                  ┌────────────────────────────┐
  Browser ──────▶│ nginx (reverse proxy :443)  │
                  └──────────┬─────────────────┘
                             │ proxy_pass :8050
                  ┌──────────▼─────────────────┐
                  │  gunicorn (WSGI, 2 workers) │
                  │  app.discovery_stats:server  │
                  └──────────┬─────────────────┘
                             │ psycopg2
                  ┌──────────▼─────────────────┐
                  │  sibyl (PostgreSQL 15.2)     │
                  └────────────────────────────┘
```

The app runs as a systemd service behind nginx. A daily cron job refreshes
the CSV caches from PostgreSQL. During refresh, the live app displays a
yellow banner informing users that updated data is being prepared.

## 1. Prerequisites

| Component       | Version  | Purpose                          |
|-----------------|----------|----------------------------------|
| RHEL / Rocky    | 8 or 9   | Server OS                        |
| Python          | 3.10+    | Application runtime              |
| PostgreSQL libs | 15+      | `psycopg2` (client only)         |
| nginx           | any      | Reverse proxy, TLS termination   |
| git             | any      | Deploy from repository           |

The server needs network access to `sibyl` on port 5432 (PostgreSQL) and
a `~/.pgpass` entry for `claude_ro` on the account running the app.

## 2. System Setup

```bash
# Install system packages
sudo dnf install -y python3.11 python3.11-devel gcc nginx git \
    postgresql15-libs

# Create a service account (optional — can use an existing account)
sudo useradd -r -m -s /bin/bash neo-dash
sudo su - neo-dash
```

## 3. Application Install

```bash
# Clone the repository
git clone https://github.com/rlseaman/CSS_SBN_derived.git
cd CSS_SBN_derived

# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

### Database Credentials

Create `~/.pgpass` for the service account:

```
sibyl:5432:mpc_sbn:claude_ro:PASSWORD_HERE
```

```bash
chmod 600 ~/.pgpass
```

Verify connectivity:

```bash
psql -h sibyl -U claude_ro mpc_sbn -c "SELECT COUNT(*) FROM mpc_orbits"
```

### Initial Cache Population

The first run queries PostgreSQL and builds two CSV caches. This takes
2–4 minutes and must succeed before starting the service:

```bash
cd CSS_SBN_derived
source venv/bin/activate
python app/discovery_stats.py --refresh-only
```

This writes cache files to `app/`:

| File pattern                    | Contents                | Rows   |
|---------------------------------|-------------------------|--------|
| `.neo_cache_XXXXXXXX.csv`       | NEO discovery data      | ~44K   |
| `.apparition_cache_XXXXXXXX.csv`| Apparition observations | ~362K  |
| Corresponding `.meta` files     | Query timestamp (UTC)   | —      |

The `XXXXXXXX` is an MD5 hash of the SQL — it changes only when the
query text changes (code update), not on each refresh.

## 4. Gunicorn Service

### systemd Unit File

Create `/etc/systemd/system/neo-dash.service`:

```ini
[Unit]
Description=NEO Discovery Statistics Explorer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=neo-dash
Group=neo-dash
WorkingDirectory=/home/neo-dash/CSS_SBN_derived
Environment=PATH=/home/neo-dash/CSS_SBN_derived/venv/bin:/usr/bin
ExecStart=/home/neo-dash/CSS_SBN_derived/venv/bin/gunicorn \
    --bind 127.0.0.1:8050 \
    --workers 2 \
    --timeout 120 \
    --access-logfile /var/log/neo-dash/access.log \
    --error-logfile /var/log/neo-dash/error.log \
    app.discovery_stats:server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Log directory

```bash
sudo mkdir -p /var/log/neo-dash
sudo chown neo-dash:neo-dash /var/log/neo-dash
```

### Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable neo-dash
sudo systemctl start neo-dash

# Verify
sudo systemctl status neo-dash
curl -s http://127.0.0.1:8050/ | head -20
```

### Worker count

Two workers are sufficient — the app serves pre-computed data from CSV
caches and has no long-running requests. Increase to 4 only if
monitoring shows request queuing under load.

## 5. Nginx Reverse Proxy

Create `/etc/nginx/conf.d/neo-dash.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name neo-dash.lpl.arizona.edu;  # adjust to actual hostname

    ssl_certificate     /etc/pki/tls/certs/your-cert.pem;
    ssl_certificate_key /etc/pki/tls/private/your-key.pem;

    # Campus CA chain if using InCommon/Sectigo
    ssl_trusted_certificate /etc/pki/tls/certs/chain.pem;

    location / {
        proxy_pass http://127.0.0.1:8050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Dash long-polling for callbacks
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Static assets (CSS, logo) — served by Dash, but nginx can cache
    location /assets/ {
        proxy_pass http://127.0.0.1:8050/assets/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name neo-dash.lpl.arizona.edu;
    return 301 https://$host$request_uri;
}
```

```bash
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
```

## 6. Firewall and SELinux

### Firewall

```bash
# Open HTTPS (and HTTP for redirect)
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

If campus policy requires restricting source IPs or using a VPN, add
rich rules:

```bash
sudo firewall-cmd --permanent --add-rich-rule='
  rule family="ipv4" source address="150.135.0.0/16"
  service name="https" accept'
```

### SELinux

Allow nginx to connect to the gunicorn backend:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

If the service account's home directory has a non-standard context:

```bash
sudo semanage fcontext -a -t httpd_sys_content_t \
    "/home/neo-dash/CSS_SBN_derived/app/assets(/.*)?"
sudo restorecon -Rv /home/neo-dash/CSS_SBN_derived/app/assets
```

## 7. Daily Data Refresh (Cron)

### Refresh script

Create `scripts/daily_refresh.sh`:

```bash
#!/bin/bash
# Daily cache refresh for NEO Discovery Statistics Explorer
# Intended to be called by cron — writes a sentinel file so the
# running app can display a "refresh in progress" banner.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../app" && pwd)"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SENTINEL="$APP_DIR/.refreshing"
LOG="/var/log/neo-dash/refresh.log"

echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — Starting refresh" >> "$LOG"

# Signal the running app that a refresh is in progress
touch "$SENTINEL"

# Activate venv and run refresh
cd "$PROJECT_DIR"
source venv/bin/activate
python app/discovery_stats.py --refresh-only >> "$LOG" 2>&1
STATUS=$?

# Remove sentinel regardless of success/failure
rm -f "$SENTINEL"

if [ $STATUS -eq 0 ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — Refresh complete" >> "$LOG"
else
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — Refresh FAILED (exit $STATUS)" >> "$LOG"
fi

exit $STATUS
```

```bash
chmod +x scripts/daily_refresh.sh
```

### Crontab

```bash
# Run as the neo-dash user at 06:00 UTC daily (23:00 MST)
sudo -u neo-dash crontab -e
```

```cron
0 6 * * * /home/neo-dash/CSS_SBN_derived/scripts/daily_refresh.sh
```

### How the refresh banner works

1. `daily_refresh.sh` creates `app/.refreshing` (a sentinel file)
2. The running Dash app polls for this file every 30 seconds
   (`dcc.Interval` component)
3. When detected, a yellow banner appears:
   *"Data refresh in progress — results shown are from the previous
   update (2026-02-13 06:00 UTC)."*
4. The script removes the sentinel when done (2–4 minutes)
5. On the next poll, the banner disappears — no restart needed

The gunicorn workers do **not** restart during refresh. They continue
serving the previous day's cached data. The next user request after the
caches are updated will load the new CSVs (on the next app restart or
when caches expire naturally). To pick up new caches immediately, send
a graceful restart:

```bash
sudo systemctl reload neo-dash   # or: kill -HUP <gunicorn-master-pid>
```

To make this automatic, add to the end of `daily_refresh.sh`:

```bash
sudo systemctl reload neo-dash 2>/dev/null || true
```

(This requires a sudoers entry for the service account — see below.)

### Sudoers for reload

```bash
# /etc/sudoers.d/neo-dash
neo-dash ALL=(root) NOPASSWD: /usr/bin/systemctl reload neo-dash
```

## 8. Updating the Application

```bash
sudo su - neo-dash
cd CSS_SBN_derived
git pull origin main

# If requirements changed:
source venv/bin/activate
pip install -r requirements.txt

# Restart to pick up code changes
sudo systemctl restart neo-dash
```

If the SQL queries change (different `LOAD_SQL` or `APPARITION_SQL`),
the MD5 hash in the cache filename changes automatically. The next
refresh (or manual `--refresh-only`) will create new cache files. Old
cache files can be cleaned up:

```bash
rm -f app/.neo_cache_*.csv app/.neo_cache_*.meta
rm -f app/.apparition_cache_*.csv app/.apparition_cache_*.meta
```

## 9. Monitoring

### Health check

```bash
curl -sf http://127.0.0.1:8050/ > /dev/null && echo OK || echo FAIL
```

### Log rotation

Create `/etc/logrotate.d/neo-dash`:

```
/var/log/neo-dash/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    copytruncate
}
```

### Cache age check

If the cron job fails silently, caches go stale. Add a monitoring
check:

```bash
# Alert if neo_cache is older than 36 hours
find /home/neo-dash/CSS_SBN_derived/app -name '.neo_cache_*.csv' \
    -mmin +2160 -exec echo "STALE: {}" \;
```

## 10. Quick Reference

| Action                    | Command                                    |
|---------------------------|--------------------------------------------|
| Start app                 | `sudo systemctl start neo-dash`            |
| Stop app                  | `sudo systemctl stop neo-dash`             |
| Restart (code changes)    | `sudo systemctl restart neo-dash`          |
| Reload (pick up caches)   | `sudo systemctl reload neo-dash`           |
| View logs                 | `journalctl -u neo-dash -f`               |
| View refresh log          | `tail -f /var/log/neo-dash/refresh.log`    |
| Manual refresh            | `scripts/daily_refresh.sh`                 |
| Test DB connectivity      | `psql -h sibyl -U claude_ro mpc_sbn`       |
| Check cache age           | `ls -la app/.neo_cache_*.csv`              |
| Check if refresh running  | `ls app/.refreshing 2>/dev/null && echo Y` |
