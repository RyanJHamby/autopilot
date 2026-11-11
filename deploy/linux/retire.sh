#!/usr/bin/env bash
# Stop apx on THIS Linux host. Only one live host, ever (docs/apx-host-move.md).
#   sudo bash deploy/linux/retire.sh            # previews: changes nothing
#   sudo DO=1 bash deploy/linux/retire.sh       # stops and disables the apx and updater timers (reversible: enable them again)
# It never deletes keys, tokens, releases or accounts, and it leaves the egress rules and resolver running (they only restrict).
# Revoking the App key is a step in the GitHub UI (yours); removing secrets from this disk is a separate command the doc gives you after.
set -u

DO="${DO:-0}"
UNITS="apx.timer apx-updater.timer apx.service apx-updater.service"
say() { printf '%s\n' "$*"; }

[ "$(id -u)" = 0 ] || { say "run with sudo (this previews unless DO=1)"; exit 1; }
command -v systemctl >/dev/null 2>&1 || { say "systemctl not found; nothing to stop on this host"; exit 0; }

for u in $UNITS; do
  if systemctl is-active --quiet "$u" 2>/dev/null || systemctl is-enabled --quiet "$u" 2>/dev/null; then
    if [ "$DO" = 1 ]; then
      case "$u" in
        *.timer) if systemctl disable --now "$u"; then say "stopped and disabled $u"; else say "could not stop $u"; fi ;;
        *) if systemctl stop "$u"; then say "stopped $u"; else say "could not stop $u"; fi ;;
      esac
    else
      say "would stop $u"
    fi
  else
    say "$u is not active or enabled here"
  fi
done

say ""
say "Secrets still on this disk (NOT touched by this script):"
for f in /home/apx/.apx/app.pem /home/apx/.apx/apx.env /home/apx-agent/.apx/claude-oauth; do [ -e "$f" ] && say "  $f"; done
[ "$DO" = 1 ] || say "Preview only. Re-run with DO=1 to stop the timers."
