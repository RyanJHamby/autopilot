#!/usr/bin/env bash
# Is this server fit to be the always-on apx host?   bash deploy/linux/preflight.sh
# READ-ONLY: no sudo, changes nothing, sends nothing except one request each to GitHub and Anthropic to see that they answer.
# Prints PASS / WARN / FAIL / INFO per check and exits 1 if any FAIL. Run it on the new server before bootstrap.sh (docs/apx-linux-host.md).
set -u

fails=0
say() { printf '%s\n' "$*"; }
pass() { say "PASS  $*"; }
warn() { say "WARN  $*"; }
info() { say "INFO  $*"; }
fail() { say "FAIL  $*"; fails=$((fails + 1)); }

[ "$(uname -s)" = Linux ] || { say "this check is for a Linux server"; exit 2; }
[ "$(id -u)" != 0 ] || info "running as root; this check does not need it"

# shellcheck disable=SC1091  # a system file that is not part of this repo
. /etc/os-release 2>/dev/null || true
case "${ID:-}" in
  debian | ubuntu) pass "${PRETTY_NAME:-$ID}: the bootstrap script supports Debian and Ubuntu" ;;
  *) fail "${PRETTY_NAME:-unknown OS}: bootstrap.sh needs Debian or Ubuntu (apt)" ;;
esac
info "kernel $(uname -r), $(uname -m)"
kmajor="$(uname -r | cut -d. -f1)"
kminor="$(uname -r | cut -d. -f2 | tr -cd 0-9)"
if [ "${kmajor:-0}" -gt 5 ] || { [ "${kmajor:-0}" = 5 ] && [ "${kminor:-0}" -ge 10 ]; }; then pass "kernel is new enough for nftables NAT in the inet family"
else fail "kernel $(uname -r) is too old for the egress rules (need 5.10 or newer)"; fi

if [ -d /run/systemd/system ]; then pass "systemd is running"; else fail "systemd is not running; the units need it"; fi
if command -v nft >/dev/null 2>&1; then pass "nft is installed"; else info "nft not installed yet (bootstrap.sh installs it)"; fi

mem_gb=$(($(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1048576))
if [ "$mem_gb" -ge 15 ]; then pass "about ${mem_gb} GB RAM"
elif [ "$mem_gb" -ge 7 ]; then warn "about ${mem_gb} GB RAM: enough for the daemon, tight for a big Next.js build"
else fail "about ${mem_gb} GB RAM: too little"; fi

free_gb="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -cd 0-9)"
if [ "${free_gb:-0}" -ge 30 ]; then pass "${free_gb} GB free on /"
elif [ "${free_gb:-0}" -ge 15 ]; then warn "${free_gb} GB free on /: releases, venvs and node_modules add up"
else fail "${free_gb:-?} GB free on /: need about 15 GB at least"; fi

for t in git curl python3; do if command -v "$t" >/dev/null 2>&1; then pass "$t found"; else fail "$t missing"; fi; done
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then pass "python $(python3 -c 'import platform; print(platform.python_version())') is 3.11 or newer"; else fail "python is older than 3.11"; fi
fi
for t in node npm uv; do if command -v "$t" >/dev/null 2>&1; then pass "$t found"; else warn "$t missing (needed to build or test some repos; see docs/apx-linux-host.md)"; fi; done

# Private repos apx runs CI for (APX_PRIVATE_CI, comma-separated, same value as in the apx environment): every tool their CI needs must be
# on the PATH apx-ci will have, or their required checks would fail on the host instead of on the code.
if [ -n "${APX_PRIVATE_CI:-}" ]; then
  root="$(cd "$(dirname "$0")/../.." && pwd)"
  ci_path="/usr/local/bin:${APX_CI_HOME:-/home/apx-ci}/.local/bin:/usr/bin:/bin"
  if command -v python3 >/dev/null 2>&1; then
    out="$(PYTHONPATH="$root/src" python3 -m autopilot.apx.repo_ci check-tools "$APX_PRIVATE_CI" --path "$ci_path" 2>&1)" || true
    while IFS= read -r line; do
      case "$line" in PASS*) pass "${line#PASS  }" ;; FAIL*) fail "${line#FAIL  }" ;; *) [ -z "$line" ] || info "$line" ;; esac
    done <<EOF_TOOLS
$out
EOF_TOOLS
  else fail "python3 missing, so the tools for APX_PRIVATE_CI repos cannot be checked"; fi
else
  info "APX_PRIVATE_CI is not set: no private-repo CI is configured for this host (set it to check admin, control, pawl, agent-kit tools)"
fi

# Per-repo toolchains (src/autopilot/apx/repo_toolchains.json): stencil needs Node 20, autopilot Node 22, so each repo's declared
# directory under <shared>/toolchains must exist, hold the right version and not be writable by the sandbox account. Checked for every
# repo apx is set up for (APX_INSTALLATIONS plus APX_PRIVATE_CI), so it only runs once apx.env exists.
if [ -n "${APX_INSTALLATIONS:-}${APX_PRIVATE_CI:-}" ]; then
  root="$(cd "$(dirname "$0")/../.." && pwd)"
  if command -v python3 >/dev/null 2>&1; then
    out="$(PYTHONPATH="$root/src" python3 -m autopilot.apx.toolchains check "${APX_INSTALLATIONS:-},${APX_PRIVATE_CI:-}" --root "${APX_SHARED:-/srv/apx}/toolchains" 2>&1)" || true
    while IFS= read -r line; do
      case "$line" in PASS*) pass "${line#PASS  }" ;; FAIL*) fail "${line#FAIL  }" ;; *) [ -z "$line" ] || info "$line" ;; esac
    done <<EOF_TCHAINS
$out
EOF_TCHAINS
  else fail "python3 missing, so the toolchains for the configured repos cannot be checked"; fi
else
  info "APX_INSTALLATIONS is not set: per-repo toolchains (Node 20 / 22) are not checked; re-run this after apx.env exists"
fi

for u in apx apx-ci apx-agent; do if id "$u" >/dev/null 2>&1; then info "account $u already exists"; else info "account $u not created yet (bootstrap.sh creates it)"; fi; done
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet apx.timer 2>/dev/null; then
  warn "apx.timer is already active on THIS machine: never run two live hosts (docs/apx-host-move.md)"
fi

if [ -r /etc/ssh/sshd_config ] || [ -d /etc/ssh/sshd_config.d ]; then
  pw="$(grep -rhiE '^\s*PasswordAuthentication' /etc/ssh/sshd_config /etc/ssh/sshd_config.d 2>/dev/null | head -1)"
  info "ssh password setting before hardening: ${pw:-default}"
fi
info "this host should hold nothing but apx's own secrets: no personal files, no gh login, no ssh keys to other machines"

for url in https://api.github.com https://api.anthropic.com; do
  code="$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$url" 2>/dev/null)"
  case "$code" in 000 | "") fail "cannot reach $url" ;; *) pass "$url answers (HTTP $code)" ;; esac
done

say ""
if [ "$fails" = 0 ]; then say "No blockers. Next: DRY_RUN=1 ADMIN_USER=you bash deploy/linux/bootstrap.sh"; else say "$fails blocker(s) above. Fix them before using this server."; exit 1; fi
