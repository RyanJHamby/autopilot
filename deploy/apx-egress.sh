#!/bin/bash
# Keep the apx-ci and apx-agent accounts off your home network (backlog S4, first slice; rules in src/autopilot/apx/pfrules.py).
#   bash deploy/apx-egress.sh                       # previews the rules and syntax-checks them: changes nothing, no sudo
#   sudo DO=1 bash deploy/apx-egress.sh             # installs the pf anchor and turns pf on
#   sudo DO=1 UNDO=1 bash deploy/apx-egress.sh      # removes it again (restores the pf.conf backup)
# The rules match only those two accounts, so the host's own traffic and the `apx` account are not affected.
# Not covered (see the module docstring): per-host allowlisting and DNS tunnelling.
set -u

DO="${DO:-0}"
UNDO="${UNDO:-0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANCHOR=com.autopilot.apx
FILE="/etc/pf.anchors/$ANCHOR"
CONF=/etc/pf.conf
BAK="/etc/pf.conf.apx-backup"
say() { printf '%s\n' "$*"; }

rules="$(PYTHONPATH="$ROOT/src" /usr/bin/python3 -m autopilot.apx.pfrules)" || { say "could not generate the rules"; exit 1; }
tmp="$(mktemp -t apx-egress)"
printf '%s\n' "$rules" > "$tmp"
if pfctl -n -f "$tmp" >/dev/null 2>&1; then say "rules pass the pf syntax check"; else say "rules FAIL the pf syntax check; nothing changed"; rm -f "$tmp"; exit 1; fi

if [ "$DO" != 1 ]; then
  say ""; say "$rules"; say ""
  say "Preview only. sudo DO=1 bash deploy/apx-egress.sh installs it; then check with deploy/apx-egress-probe.sh."
  rm -f "$tmp"; exit 0
fi
[ "$(id -u)" = 0 ] || { rm -f "$tmp"; say "run with sudo"; exit 1; }

if [ "$UNDO" = 1 ]; then
  pfctl -a "$ANCHOR" -F rules >/dev/null 2>&1
  if [ -f "$BAK" ]; then cp "$BAK" "$CONF" && pfctl -f "$CONF" >/dev/null 2>&1; say "restored $CONF from $BAK"; else say "no backup at $BAK; $CONF left as is"; fi
  rm -f "$FILE" "$tmp"; say "egress rules removed"; exit 0
fi

[ -f "$BAK" ] || cp "$CONF" "$BAK"                      # one backup, of the original, taken before the first edit
install -m 644 -o root -g wheel "$tmp" "$FILE"; rm -f "$tmp"
grep -q "anchor \"$ANCHOR\"" "$CONF" || printf 'anchor "%s"\nload anchor "%s" from "%s"\n' "$ANCHOR" "$ANCHOR" "$FILE" >> "$CONF"
pfctl -n -f "$CONF" >/dev/null 2>&1 || { cp "$BAK" "$CONF"; say "the edited $CONF failed its syntax check; restored the original"; exit 1; }
pfctl -f "$CONF" >/dev/null 2>&1 && pfctl -E >/dev/null 2>&1
pfctl -a "$ANCHOR" -sr 2>/dev/null | head -3
say "installed. macOS can reset pf.conf on a system update: re-run this script (and the probe) after each one."
