#!/bin/bash
# Is this Mac fit to be the always-on apx host?   bash deploy/apx-host-preflight.sh
# READ-ONLY: no sudo, changes nothing, sends nothing except one HEAD-style request each to GitHub and Anthropic to see if they answer.
# Prints PASS / WARN / FAIL / INFO per check; exits 1 if any FAIL. Run it on the machine that will become the host (docs/apx-host-move.md).
set -u

fails=0
say() { printf '%s\n' "$*"; }
pass() { say "PASS  $*"; }
warn() { say "WARN  $*"; }
info() { say "INFO  $*"; }
fail() { say "FAIL  $*"; fails=$((fails + 1)); }

[ "$(id -u)" != 0 ] || { say "run this as yourself, not root (it is read-only and needs no sudo)"; exit 2; }
[ "$(uname -s)" = Darwin ] || { say "this check is for a Mac host"; exit 2; }

arch="$(uname -m)"
info "chip: $arch (x86_64 = Intel, arm64 = Apple Silicon); homebrew prefix expected: $([ "$arch" = arm64 ] && echo /opt/homebrew || echo /usr/local)"

ver="$(sw_vers -productVersion 2>/dev/null || echo 0)"
major="${ver%%.*}"
if [ "${major:-0}" -ge 14 ] 2>/dev/null; then pass "macOS $ver (still in Apple's security-update window as of late 2026; re-check yearly)"
else fail "macOS $ver: too old to trust with a GitHub App key and a model token (no security updates)"; fi

mem_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
if [ "$mem_gb" -ge 16 ]; then pass "${mem_gb} GB RAM"
elif [ "$mem_gb" -ge 8 ]; then warn "${mem_gb} GB RAM: enough for the daemon, tight for a big Next.js build"
else fail "${mem_gb} GB RAM: too little"; fi

free_gb="$(df -g / 2>/dev/null | awk 'NR==2 {print $4}')"
if [ "${free_gb:-0}" -ge 30 ] 2>/dev/null; then pass "${free_gb} GB free on /"
elif [ "${free_gb:-0}" -ge 15 ] 2>/dev/null; then warn "${free_gb} GB free on /: releases, venvs and node_modules add up"
else fail "${free_gb:-?} GB free on /: need about 15 GB at least"; fi

for t in git python3 curl; do
  command -v "$t" >/dev/null 2>&1 && pass "$t found" || fail "$t missing"
done
for t in brew node npm uv; do
  command -v "$t" >/dev/null 2>&1 && pass "$t found" || warn "$t missing (needed to build/test some repos; install before the CI account setup)"
done

ac_sleep="$(pmset -g custom 2>/dev/null | awk '/AC Power/ {a=1; next} /Battery Power/ {a=0} a && $1=="sleep" {print $2}')"
if [ "$ac_sleep" = 0 ]; then pass "never sleeps on AC power"
else warn "sleeps after ${ac_sleep:-?} min on AC power: run  sudo pmset -c sleep 0 disablesleep 1  once, so a closed lid does not stop apx"; fi
batt="$(pmset -g batt 2>/dev/null | head -2 | tr '\n' ' ')"
info "power: ${batt:-unknown}"
cond="$(system_profiler SPPowerDataType 2>/dev/null | awk -F': ' '/Cycle Count|Condition/ {printf "%s=%s  ", $1, $2}')"
[ -n "$cond" ] && info "battery: $cond(turn on Optimized/limited charging; a laptop kept at 100% for months can swell its battery)"

fv="$(fdesetup status 2>/dev/null | head -1)"
info "disk encryption: ${fv:-unknown} (On protects the keys if the laptop is stolen, but then a reboot waits for a password before apx starts)"

for u in apx apx-ci apx-agent; do
  id "$u" >/dev/null 2>&1 && info "account $u already exists" || info "account $u not created yet (docs/apx-runbook.md, section 0)"
done
launchctl list 2>/dev/null | grep -q 'com.autopilot.apx' && warn "an apx job is already loaded on THIS machine: never run two live hosts (docs/apx-host-move.md)"

for url in https://api.github.com https://api.anthropic.com; do
  code="$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$url" 2>/dev/null)"
  case "$code" in 000|"") fail "cannot reach $url";; *) pass "$url answers (HTTP $code)";; esac
done

say ""
if [ "$fails" = 0 ]; then say "No blockers. Next: docs/apx-host-move.md"; else say "$fails blocker(s) above. Fix them before moving apx here."; exit 1; fi
