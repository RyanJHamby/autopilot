#!/bin/bash
# Phase 2 of the apx safe updater: run the daemon from the `current` release and let the updater swap releases for real.
#   sudo bash deploy/apx-switch-to-current.sh
# Do this only after phase 1's update.json has shown a sensible dry-run line. It rewrites the daemon plist (a backup is kept next to
# it) and the updater plist, then restarts both. To undo: copy the .bak back over the plist and `launchctl bootout` / `bootstrap`.
set -euo pipefail

SHARED="${SHARED:-/Users/Shared/apx}"
D=/Library/LaunchDaemons/com.autopilot.apx.plist
U=/Library/LaunchDaemons/com.autopilot.apx.updater.plist
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ -L "$SHARED/current" ] || { echo "run phase 1 first (no $SHARED/current)"; exit 1; }
[ -f "$D" ] && [ -f "$U" ] || { echo "missing a plist"; exit 1; }

cp "$D" "$D.bak"
cp "$U" "$U.bak"
/usr/bin/python3 - "$D" "$U" "$SHARED" <<'PY'
import plistlib, sys
d, u, shared = sys.argv[1:4]
p = plistlib.load(open(d, "rb"))
p["WorkingDirectory"] = f"{shared}/current"
p["ProgramArguments"] = ["/bin/sh", "-c",
    f"set -a; . /Users/apx/.apx/apx.env; set +a; export APX_LIVE=1 PYTHONPATH={shared}/current/src; "
    f"exec {shared}/venv/bin/python -m autopilot.apx.daemon --once --live"]
plistlib.dump(p, open(d, "wb"))
q = plistlib.load(open(u, "rb"))
q["ProgramArguments"] = ["/bin/sh", "-c",
    f"set -a; . /Users/apx/.apx/apx.env; set +a; export APX_UPDATE_LIVE=1 PYTHONPATH={shared}/updater/src; "
    f"exec {shared}/venv/bin/python -m autopilot.apx.update_main --live"]
plistlib.dump(q, open(u, "wb"))
PY
chown root:wheel "$D" "$U"
chmod 644 "$D" "$U"
launchctl bootout system/com.autopilot.apx.updater 2>/dev/null || true
launchctl bootout system/com.autopilot.apx 2>/dev/null || true
launchctl bootstrap system "$D"
launchctl bootstrap system "$U"
echo "switched. Check in a few minutes:  PYTHONPATH=$SHARED/current/src /usr/bin/python3 -m autopilot.apx.status --print"
echo "To stop adoption any time:  touch $SHARED/HOLD"
