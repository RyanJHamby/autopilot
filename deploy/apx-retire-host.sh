#!/bin/bash
# Stop apx on THIS Mac after the new host is live (docs/apx-host-move.md, step 6). Only one live host, ever.
#   sudo bash deploy/apx-retire-host.sh          # previews: changes nothing
#   DO=1 sudo bash deploy/apx-retire-host.sh     # stops the apx launchd jobs (reversible: `launchctl bootstrap` them again)
# It never deletes keys, tokens, releases or accounts. Revoking the old App key is a step in the GitHub UI (yours), and removing the
# old secrets from this disk is a separate command the runbook gives you after you have revoked it.
set -u

DO="${DO:-0}"
JOBS="com.autopilot.apx com.autopilot.apx.updater"
say() { printf '%s\n' "$*"; }

[ "$(id -u)" = 0 ] || { say "run with sudo (this previews unless DO=1)"; exit 1; }

for j in $JOBS; do
  if launchctl print "system/$j" >/dev/null 2>&1; then
    if [ "$DO" = 1 ]; then
      launchctl bootout "system/$j" && say "stopped $j" || say "could not stop $j"
    else
      say "would stop $j"
    fi
  else
    say "$j is not loaded here"
  fi
done

say ""
say "Secrets still on this disk (NOT touched by this script):"
for f in /Users/apx/.apx/app.pem /Users/apx/.apx/apx.env /Users/apx/.apx/claude-oauth /Users/ryanhamby/.apx; do
  [ -e "$f" ] && say "  $f"
done
[ "$DO" = 1 ] || say "Preview only. Re-run with DO=1 to stop the jobs."
