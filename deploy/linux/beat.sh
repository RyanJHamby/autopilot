#!/bin/sh
# apx dead-man heartbeat: tell the agent-kit watcher (a Cloudflare Worker) that apx on this host is alive. The Worker alerts the owner
# on Telegram once when no heartbeat has arrived for 45 minutes, and once when they resume. Installed root-owned as
# /usr/local/sbin/apx-beat (outside /srv/apx, which apx owns, so apx cannot change what holds the beat secret) and run by apx-beat.timer.
#
# Alive means: apx finished a pass (a real one or a freeze-time idle heartbeat) in the last APX_BEAT_MAX_AGE_MIN minutes (default 15,
# the same limit as the status watcher), or a pass is running right now (apx.service is activating; a long agent run holds a pass, and
# the unit's own TimeoutStartSec ends a hung one). Otherwise send nothing, and the Worker alerts.
#
# Needs one root-only file passed as a systemd credential named "watcher" (LoadCredential), two lines:
#   WATCHER_URL=https://agent-kit-watcher.<subdomain>.workers.dev
#   WATCHER_BEAT_SECRET=<the Worker's BEAT_SECRET>
# The secret is never printed and never on a command line (curl reads the URL from stdin). Exit 0 for "not alive" and network
# problems (one log line); 1 only for a missing or malformed credential.
set -eu

status="${APX_STATUS:-/srv/apx/status.json}"
max_age_min="${APX_BEAT_MAX_AGE_MIN:-15}"
case "$max_age_min" in '' | *[!0-9]*) echo "apx-beat: APX_BEAT_MAX_AGE_MIN must be a whole number of minutes"; exit 1 ;; esac

cred="${CREDENTIALS_DIRECTORY:-/nonexistent}/watcher"
[ -r "$cred" ] || { echo "apx-beat: no watcher credential (LoadCredential=watcher:...)"; exit 1; }
url="$(sed -n 's/^WATCHER_URL=//p' "$cred" | head -n1)"
secret="$(sed -n 's/^WATCHER_BEAT_SECRET=//p' "$cred" | head -n1)"
if [ "${APX_BEAT_ALLOW_HTTP:-0}" = 1 ]; then url_re='^https?://[A-Za-z0-9.-]+(:[0-9]+)?$'; else url_re='^https://[A-Za-z0-9.-]+(:[0-9]+)?$'; fi
printf '%s' "$url" | grep -Eq "$url_re" || { echo "apx-beat: WATCHER_URL must be https://host with no path or trailing slash"; exit 1; }
printf '%s' "$secret" | grep -Eq '^[A-Za-z0-9_-]+$' || { echo "apx-beat: WATCHER_BEAT_SECRET is missing or has characters other than letters, digits, - and _"; exit 1; }

running="$(systemctl show -p ActiveState --value apx.service 2>/dev/null || true)"
if [ "$running" = activating ]; then
  why="a pass is running"
elif mtime="$(stat -c %Y "$status" 2>/dev/null)"; then
  age=$(($(date +%s) - mtime))
  if [ "$age" -gt $((max_age_min * 60)) ]; then
    echo "apx-beat: apx last finished a pass $((age / 60)) min ago; no heartbeat sent"
    exit 0
  fi
  why="last pass $((age / 60)) min ago"
else
  echo "apx-beat: no status file at $status; no heartbeat sent"
  exit 0
fi

if printf 'url = "%s/beat/%s"\n' "$url" "$secret" | curl -fsS --max-time 10 -X POST --config - >/dev/null 2>&1; then
  echo "apx-beat: heartbeat sent ($why)"
else
  echo "apx-beat: heartbeat failed (watcher unreachable?)"
fi
exit 0
