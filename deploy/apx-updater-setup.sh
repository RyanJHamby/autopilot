#!/bin/bash
# Phase 1 of the apx safe updater (docs/apx-updater-design.md). ADDITIVE: it changes nothing the running daemon uses.
#   DRY_RUN=1 sudo bash deploy/apx-updater-setup.sh     # preview
#   sudo bash deploy/apx-updater-setup.sh               # do it
# It (1) puts pytest + pyyaml in the shared venv so the updater can test a new tree, (2) stages the CURRENT commit of the manual
# checkout as the first release and points `current` at it, (3) makes the updater's own copy (never auto-updated), and (4) installs
# the updater timer in DRY-RUN mode (it only prints what it would do). Phase 2 (deploy/apx-switch-to-current.sh) moves the daemon.
set -euo pipefail

SHARED="${SHARED:-/Users/Shared/apx}"
ORCH=apx
DRY_RUN="${DRY_RUN:-0}"
SRC="$SHARED/autopilot"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/launchd/com.autopilot.apx.updater.plist"
PLIST_DST=/Library/LaunchDaemons/com.autopilot.apx.updater.plist

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN: $*"; else "$@"; fi; }
as_orch() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN (as $ORCH): $*"; else sudo -u "$ORCH" -H "$@"; fi; }

if [ "$DRY_RUN" != 1 ]; then
  [ "$(id -u)" = 0 ] || { say "run with sudo (or DRY_RUN=1 to preview)"; exit 1; }
  [ -d "$SRC/.git" ] || { say "no checkout at $SRC"; exit 1; }
  [ -f "$PLIST_SRC" ] || { say "missing $PLIST_SRC"; exit 1; }
fi

SHA="$(sudo -u "$ORCH" git -C "$SRC" rev-parse HEAD 2>/dev/null || echo 0000000000000000000000000000000000000000)"
case "$SHA" in *[!0-9a-f]*) say "bad sha $SHA"; exit 1;; esac
[ ${#SHA} = 40 ] || { say "bad sha $SHA"; exit 1; }
say "first release: $SHA"

as_orch /Users/apx/.local/bin/uv pip install --python "$SHARED/venv/bin/python" pytest pyyaml
# uv installs under the orchestrator's umask (077); the no-secrets test account must be able to read the packages.
as_orch chmod -R go+rX "$SHARED/venv"
as_orch mkdir -p "$SHARED/releases"
if [ ! -d "$SHARED/releases/$SHA" ]; then
  as_orch git clone -q --no-hardlinks "$SRC" "$SHARED/releases/$SHA"
  as_orch git -C "$SHARED/releases/$SHA" checkout -q --detach "$SHA"
fi
[ -e "$SHARED/current" ] || as_orch ln -s "releases/$SHA" "$SHARED/current"
[ -d "$SHARED/updater" ] || as_orch git clone -q --no-hardlinks "$SRC" "$SHARED/updater"
as_orch git -C "$SHARED/updater" checkout -q --detach "$SHA"
as_orch chmod -R go+rX "$SHARED/releases" "$SHARED/updater"

run cp "$PLIST_SRC" "$PLIST_DST"
run chown root:wheel "$PLIST_DST"
run chmod 644 "$PLIST_DST"
run launchctl bootstrap system "$PLIST_DST"
say "done. Check:  cat $SHARED/update.json   (after about 5 minutes; it should say 'dry-run: would consider ...')"
say "Stop the updater any time:  sudo launchctl bootout system/com.autopilot.apx.updater"
