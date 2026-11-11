#!/usr/bin/env bash
# Turn a fresh Debian or Ubuntu server into the apx host. Run ONCE by the owner, as root, from a clone of this repo:
#   DRY_RUN=1 ADMIN_USER=you bash deploy/linux/bootstrap.sh     # preview: prints what it would do, changes nothing (no root needed)
#   ADMIN_USER=you bash deploy/linux/bootstrap.sh               # do it
# It is idempotent: a second run changes nothing it already set up.
#
# What it does (and nothing else):
#   - installs the few packages apx needs, and turns on automatic security updates
#   - creates the four accounts: apx (holds the secrets), apx-ci (runs PR code), apx-agent (runs the model), apx-dns (the resolver)
#     none of them is an admin, none can log in, each home is mode 700
#   - one sudoers rule each: apx may act as apx-ci and as apx-agent, nothing else (checked with visudo before it is installed)
#   - lays out /srv/apx: a Python venv, releases/<sha>, a `current` link, and the updater's own copy
#   - renders and installs the egress allowlist (nftables rules + a dnsmasq config) for the three sandbox lanes, checked before it is loaded
#   - installs the systemd units and starts ONLY the egress rules and the resolver. The apx and updater timers are installed but NOT
#     enabled: you enable them after the doctor passes. Shadow mode stays on until APX_SHADOW=0 is set in apx.env.
#   - hardens SSH (key-only, no root, only ADMIN_USER), but only after checking ADMIN_USER already has a key, so it cannot lock you out
# It does NOT install any secret (the GitHub App key and the Claude token are copied in by you afterwards, see docs/apx-linux-host.md),
# it installs no uv/node/claude toolchain (see the doc: those are owner decisions), and it deletes nothing.
#
# Knobs (environment): ADMIN_USER (required), DRY_RUN, APX_CODE_URL, APX_SHA, CONTROL_HOST, PIP_PACKAGES,
#   SKIP_PACKAGES / SKIP_SYSTEMD / SKIP_SSHD (=1, for testing in a container that has no systemd or sshd).
set -euo pipefail

SHARED=/srv/apx
ADMIN_USER="${ADMIN_USER:-}"
DRY_RUN="${DRY_RUN:-0}"
CODE_URL="${APX_CODE_URL:-https://github.com/RyanJHamby/autopilot.git}"
WANT_SHA="${APX_SHA:-}"
CONTROL_HOST="${CONTROL_HOST:-}"
PIP_PACKAGES="${PIP_PACKAGES:-pyyaml pytest}"
SKIP_PACKAGES="${SKIP_PACKAGES:-0}"
SKIP_SYSTEMD="${SKIP_SYSTEMD:-0}"
SKIP_SSHD="${SKIP_SSHD:-0}"
here="$(cd "$(dirname "$0")" && pwd)"
ACCOUNTS=(apx apx-ci apx-agent)
fails=0

say() { printf '%s\n' "$*"; }
pass() { say "PASS  $*"; }
fail() { say "FAIL  $*"; fails=$((fails + 1)); }
run() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN: $*"; else "$@"; fi; }
as() { # as USER cmd...
  local who="$1"
  shift
  if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN (as $who): $*"; else setpriv --reuid="$(id -u "$who")" --regid="$(id -g "$who")" --init-groups env HOME="$(home_of "$who")" "$@"; fi
}
home_of() { getent passwd "$1" | cut -d: -f6; }
# Write a file only if its content changed, so a second run is a no-op. Args: owner:group mode path (content on stdin).
put() {
  local own="$1" mode="$2" path="$3" tmp
  tmp="$(mktemp)"
  cat >"$tmp"
  if [ -f "$path" ] && cmp -s "$tmp" "$path"; then rm -f "$tmp"; say "unchanged: $path"; return 0; fi
  if [ "$DRY_RUN" = 1 ]; then rm -f "$tmp"; say "DRY-RUN: write $path ($own, $mode)"; return 0; fi
  install -D -m "$mode" -o "${own%:*}" -g "${own#*:}" "$tmp" "$path"
  rm -f "$tmp"
  say "wrote: $path"
}

# --- preconditions ---------------------------------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || { say "this is for a Linux server"; exit 1; }
if [ "$DRY_RUN" != 1 ] && [ "$(id -u)" != 0 ]; then say "run as root (or DRY_RUN=1 to preview)"; exit 1; fi
[ -n "$ADMIN_USER" ] || { say "set ADMIN_USER to your own admin account on this server"; exit 1; }
case "$ADMIN_USER" in apx | apx-ci | apx-agent | apx-dns | root) say "ADMIN_USER must be your own account, not $ADMIN_USER"; exit 1 ;; esac
[[ "$ADMIN_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { say "ADMIN_USER is not a plain account name"; exit 1; }
if [ -n "$CONTROL_HOST" ] && ! [[ "$CONTROL_HOST" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]]; then
  say "CONTROL_HOST must be a plain lowercase hostname"; exit 1
fi
[ -d "$here/../../src/autopilot/apx" ] || { say "run this from a checkout of the autopilot repo"; exit 1; }
if [ "$DRY_RUN" != 1 ]; then
  id "$ADMIN_USER" >/dev/null 2>&1 || { say "the account $ADMIN_USER does not exist on this server"; exit 1; }
  if [ "$SKIP_SSHD" != 1 ]; then
    ak="$(home_of "$ADMIN_USER")/.ssh/authorized_keys"
    [ -s "$ak" ] || { say "refusing to restrict SSH: $ak is missing or empty, so you could lock yourself out. Add your public key first."; exit 1; }
  fi
fi

# --- packages ----------------------------------------------------------------------------------------------------------------------
if [ "$SKIP_PACKAGES" != 1 ]; then
  command -v apt-get >/dev/null 2>&1 || { say "needs apt (Debian or Ubuntu)"; exit 1; }
  run env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  # dnsmasq-base, not dnsmasq: the full package starts its own resolver on port 53, which we neither want nor need.
  run env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
    git curl ca-certificates openssl sudo util-linux nftables dnsmasq-base iproute2 netcat-openbsd \
    python3 python3-venv python3-pip unattended-upgrades
  put root:root 644 /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
fi

# --- accounts ----------------------------------------------------------------------------------------------------------------------
for u in "${ACCOUNTS[@]}"; do
  if id "$u" >/dev/null 2>&1; then
    say "$u already exists; leaving it"
  else
    run useradd --create-home --home-dir "/home/$u" --shell /usr/sbin/nologin --user-group "$u"
  fi
  run chmod 700 "/home/$u"
done
id apx-dns >/dev/null 2>&1 || run useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --user-group apx-dns
if [ "$DRY_RUN" != 1 ]; then
  for u in "${ACCOUNTS[@]}" apx-dns; do
    if id -nG "$u" | tr ' ' '\n' | grep -qxE 'sudo|admin|wheel|adm|docker'; then fail "$u is in a privileged group"; else pass "$u is a standard account"; fi
  done
fi

# --- directories and tool homes ---------------------------------------------------------------------------------------------------
run install -d -m 700 -o apx -g apx /home/apx/.apx /home/apx/.local /home/apx/.local/bin
run install -d -m 700 -o apx-ci -g apx-ci /home/apx-ci/work /home/apx-ci/.local /home/apx-ci/.local/bin
run install -d -m 700 -o apx-agent -g apx-agent /home/apx-agent/work /home/apx-agent/.apx /home/apx-agent/.local /home/apx-agent/.local/bin
# Shared and world-readable, NOT writable by the sandbox: the code it runs and the interpreter it uses.
run install -d -m 755 -o apx -g apx "$SHARED" "$SHARED/kit" "$SHARED/releases" /etc/apx

# --- the sudoers rules, checked before they are installed ---------------------------------------------------------------------------
for target in apx-ci apx-agent; do
  line="apx ALL=($target) NOPASSWD:SETENV: ALL"
  f="/etc/sudoers.d/$target"
  if [ -f "$f" ] && [ "$(cat "$f")" = "$line" ]; then say "unchanged: $f"; continue; fi
  if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN: visudo -cf then install '$line' as $f (root:root 0440)"; continue; fi
  tmp="$(mktemp)"
  printf '%s\n' "$line" >"$tmp"
  if ! visudo -cf "$tmp" >/dev/null; then rm -f "$tmp"; say "sudoers syntax check failed for $target; nothing installed"; exit 1; fi
  install -m 440 -o root -g root "$tmp" "$f"
  rm -f "$tmp"
  say "wrote: $f"
done

# --- code and python ---------------------------------------------------------------------------------------------------------------
# The autopilot repo is public, so cloning needs no credentials. apx owns the clone; the sandbox may read it but not write it.
if [ "$DRY_RUN" = 1 ] || [ ! -d "$SHARED/autopilot/.git" ]; then
  as apx git clone --quiet "$CODE_URL" "$SHARED/autopilot"
else
  say "$SHARED/autopilot exists; leaving it (the updater moves releases, not this clone)"
fi
if [ -n "$WANT_SHA" ]; then
  [[ "$WANT_SHA" =~ ^[0-9a-f]{40}$ ]] || { say "APX_SHA must be a full 40-character commit id"; exit 1; }
  as apx git -C "$SHARED/autopilot" checkout -q --detach "$WANT_SHA"
fi
if [ "$DRY_RUN" = 1 ]; then
  SHA=0000000000000000000000000000000000000000
else
  SHA="$(as apx git -C "$SHARED/autopilot" rev-parse HEAD)"  # as apx: git refuses a repo another account owns
fi
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { say "bad commit id $SHA"; exit 1; }
say "release: $SHA"

[ "$DRY_RUN" != 1 ] && [ -x "$SHARED/venv/bin/python" ] || as apx python3 -m venv "$SHARED/venv"
# shellcheck disable=SC2086  # PIP_PACKAGES is a space-separated list on purpose
as apx "$SHARED/venv/bin/python" -m pip install --quiet --disable-pip-version-check $PIP_PACKAGES
# pip installs under apx's umask (077); the no-secrets test account must be able to read the packages.
run chmod -R go+rX "$SHARED/venv"
if [ "$DRY_RUN" = 1 ] || [ ! -d "$SHARED/releases/$SHA" ]; then
  as apx git clone -q --no-hardlinks "$SHARED/autopilot" "$SHARED/releases/$SHA"
  as apx git -C "$SHARED/releases/$SHA" checkout -q --detach "$SHA"
fi
if [ "$DRY_RUN" = 1 ] || [ ! -e "$SHARED/current" ]; then as apx ln -s "releases/$SHA" "$SHARED/current"; fi
if [ "$DRY_RUN" = 1 ] || [ ! -d "$SHARED/updater" ]; then as apx git clone -q --no-hardlinks "$SHARED/autopilot" "$SHARED/updater"; fi
as apx git -C "$SHARED/updater" checkout -q --detach "$SHA"
run chmod -R go+rX "$SHARED/releases" "$SHARED/updater" "$SHARED/autopilot"

# --- the egress allowlist ----------------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: render /etc/apx/apx.nft and /etc/apx/dnsmasq.conf from autopilot.apx.nftrules with the real uids, check both, install"
else
  render_env=(env PYTHONPATH="$SHARED/current/src")
  nft_tmp="$(mktemp)"
  dns_tmp="$(mktemp)"
  trap 'rm -f "$nft_tmp" "$dns_tmp"' EXIT
  "${render_env[@]}" python3 -m autopilot.apx.nftrules nft --uid "apx=$(id -u apx)" --uid "apx-ci=$(id -u apx-ci)" --uid "apx-agent=$(id -u apx-agent)" >"$nft_tmp"
  dns_args=(dnsmasq)
  [ -z "$CONTROL_HOST" ] || dns_args+=(--control-host "$CONTROL_HOST")
  "${render_env[@]}" python3 -m autopilot.apx.nftrules "${dns_args[@]}" >"$dns_tmp"
  nft -c -f "$nft_tmp" || { say "nft rejected the generated rules; nothing installed"; exit 1; }
  dnsmasq --test --conf-file="$dns_tmp" 2>&1 | grep -qi 'syntax check OK' || { say "dnsmasq rejected the generated config; nothing installed"; exit 1; }
  put root:root 644 /etc/apx/apx.nft <"$nft_tmp"
  put root:root 644 /etc/apx/dnsmasq.conf <"$dns_tmp"
fi

# --- services ------------------------------------------------------------------------------------------------------------------------
if [ "$SKIP_SYSTEMD" != 1 ]; then
  for unit in apx-nft.service apx-dns.service apx.service apx.timer apx-updater.service apx-updater.timer; do
    put root:root 644 "/etc/systemd/system/$unit" <"$here/systemd/$unit"
  done
  run systemctl daemon-reload
  run systemctl enable --now apx-nft.service
  run systemctl enable apx-dns.service
  run systemctl reload apx-nft.service
  run systemctl restart apx-dns.service  # a changed config is only read on start
  say "NOT enabled (you do this after the doctor passes): apx.timer, apx-updater.timer"
fi

# --- ssh -------------------------------------------------------------------------------------------------------------------------------
if [ "$SKIP_SSHD" != 1 ]; then
  put root:root 644 /etc/ssh/sshd_config.d/10-apx.conf <<EOF
# apx host: key-only, no root, only the owner's admin account. Written by deploy/linux/bootstrap.sh. sshd uses the FIRST value it
# sees, and the 10- prefix puts this ahead of a provider's own drop-ins.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers $ADMIN_USER
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
EOF
  if [ "$DRY_RUN" != 1 ]; then
    sshd -t || { say "sshd rejected its configuration; leaving ssh as it is. Fix /etc/ssh/sshd_config.d/10-apx.conf"; exit 1; }
    systemctl reload ssh 2>/dev/null || systemctl reload sshd
  fi
fi

# --- prove the split, from both sides ------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: would check that apx can run commands as apx-ci and apx-agent, and that neither can reach apx's home or each other's"
else
  say ""
  for target in apx-ci apx-agent; do
    who="$(setpriv --reuid="$(id -u apx)" --regid="$(id -g apx)" --init-groups sudo -n -u "$target" /usr/bin/id -un 2>/dev/null || true)"
    if [ "$who" = "$target" ]; then pass "apx can run commands as $target"; else fail "apx cannot run commands as $target"; fi
    if setpriv --reuid="$(id -u "$target")" --regid="$(id -g "$target")" --init-groups sudo -n -u apx /usr/bin/id >/dev/null 2>&1; then
      fail "$target can become apx: the split is NOT in place"
    else
      pass "$target cannot become apx"
    fi
  done
  for pair in "apx-ci:/home/apx" "apx-agent:/home/apx" "apx-ci:/home/apx-agent" "apx-agent:/home/apx-ci" "apx-ci:/srv/apx/kit/.probe"; do
    who="${pair%%:*}" path="${pair#*:}"
    case "$path" in
      */.probe) # the shared tree must be readable but NOT writable by the sandbox
        if setpriv --reuid="$(id -u "$who")" --regid="$(id -g "$who")" --init-groups sh -c "touch '$path'" 2>/dev/null; then
          rm -f "$path"; fail "$who can write into the shared tree"
        else pass "$who cannot write into the shared tree"; fi ;;
      *)
        if setpriv --reuid="$(id -u "$who")" --regid="$(id -g "$who")" --init-groups ls "$path" >/dev/null 2>&1; then
          fail "$who can read $path"
        else pass "$who cannot read $path"; fi ;;
    esac
  done
  if setpriv --reuid="$(id -u apx-ci)" --regid="$(id -g apx-ci)" --init-groups test -r "$SHARED/current/src/autopilot/apx/daemon.py"; then
    pass "apx-ci can read the code it runs"
  else fail "apx-ci cannot read the shared code"; fi
fi

say ""
if [ "$fails" != 0 ]; then say "$fails check(s) failed above. Do not go on until they are fixed."; exit 1; fi
cat <<EOF
Done. Next, by you (docs/apx-linux-host.md has the details):
  1. install the NEW App key and model token (never copied from the old host), and /home/apx/.apx/apx.env (paths and ids only)
  2. run the doctor as apx:  sudo -u apx -H sh -c 'set -a; . /home/apx/.apx/apx.env; set +a; PYTHONPATH=$SHARED/current/src $SHARED/venv/bin/python -m autopilot.apx.daemon --doctor'
  3. only then:  systemctl enable --now apx.timer apx-updater.timer     (shadow mode is on until APX_SHADOW=0 is set)
EOF
