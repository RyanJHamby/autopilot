#!/bin/bash
# Create the unprivileged sandbox account for apx (backlog S1) and everything the split needs. Run ONCE by the owner:
#   DRY_RUN=1 bash deploy/apx-ci-account.sh      # preview: prints what it would do, changes nothing, needs no sudo
#   sudo bash deploy/apx-ci-account.sh           # do it (it prompts for the new account's password)
#
# The point: the account that holds the GitHub App key and the Claude token (`apx`) must not be the account that runs a PR's
# code. `apx-ci` runs it instead, has no secrets, and apx can start commands as it through ONE sudoers line:
#     apx ALL=(apx-ci) NOPASSWD:SETENV: ALL
# That line lets apx act as apx-ci and nothing else; apx-ci has no way back to apx. It is syntax-checked with `visudo -cf` before it is
# installed. The script deletes nothing and does not touch the owner's account.
set -euo pipefail

CI=apx-ci
ORCH=apx
CI_HOME="/Users/$CI"
SHARED="${SHARED:-/Users/Shared/apx}"
OWNER_HOME="${OWNER_HOME:-/Users/ryanhamby}"
DRY_RUN="${DRY_RUN:-0}"
SUDOERS_FILE="/etc/sudoers.d/apx-ci"
SUDOERS_LINE="$ORCH ALL=($CI) NOPASSWD:SETENV: ALL"

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN: $*"; else "$@"; fi; }
as_orch() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN (as $ORCH): $*"; else sudo -u "$ORCH" -H "$@"; fi; }

if [ "$DRY_RUN" != 1 ]; then
  [ "$(id -u)" = 0 ] || { say "run with sudo (or DRY_RUN=1 to preview)"; exit 1; }
  id "$ORCH" >/dev/null 2>&1 || { say "the $ORCH account does not exist; run deploy/apx-install-mac.sh first"; exit 1; }
  [ -x "$OWNER_HOME/.local/bin/uv" ] || { say "missing $OWNER_HOME/.local/bin/uv"; exit 1; }
fi

# --- the account ----------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ] || ! id "$CI" >/dev/null 2>&1; then
  run sysadminctl -addUser "$CI" -fullName "apx CI sandbox" -home "$CI_HOME" -shell /bin/zsh -password -
else
  say "$CI already exists; leaving it"
fi
if [ "$DRY_RUN" != 1 ] && dseditgroup -o checkmember -m "$CI" admin 2>/dev/null | grep -q "is a member"; then
  say "$CI must NOT be an admin"; exit 1
fi

# --- its home: private, with just the tools a build needs -----------------------------------------------------------
run install -d -m 700 -o "$CI" -g staff "$CI_HOME" "$CI_HOME/work" "$CI_HOME/.local" "$CI_HOME/.local/bin" "$CI_HOME/.cargo" "$CI_HOME/.cargo/bin"
run install -m 755 -o "$CI" -g staff "$OWNER_HOME/.local/bin/uv" "$CI_HOME/.local/bin/uv"
for t in rustc cargo; do
  src=/opt/homebrew/bin/$t  # Apple Silicon Homebrew; Intel Macs keep it under /usr/local
  [ -e "$src" ] || src=/usr/local/bin/$t
  run ln -sf "$src" "$CI_HOME/.cargo/bin/$t"
done
run chown -h -R "$CI:staff" "$CI_HOME/.cargo"

# --- shared, world-readable, NOT writable by the sandbox: the code it runs, the kit cache, and a python with PyYAML --------
run install -d -m 755 -o "$ORCH" -g staff "$SHARED" "$SHARED/kit"
if [ "$DRY_RUN" = 1 ] || [ ! -d "$SHARED/autopilot/.git" ]; then
  as_orch git clone --quiet https://github.com/RyanJHamby/autopilot.git "$SHARED/autopilot"
else
  as_orch git -C "$SHARED/autopilot" pull --quiet --ff-only
fi
as_orch /Users/$ORCH/.local/bin/uv venv --quiet "$SHARED/venv"
as_orch /Users/$ORCH/.local/bin/uv pip install --quiet --python "$SHARED/venv/bin/python" pyyaml
run chmod -R go+rX "$SHARED"

# --- the single sudoers rule, syntax-checked before it is installed --------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: write '$SUDOERS_LINE' to a temp file, run 'visudo -cf' on it, then install it as $SUDOERS_FILE (root:wheel, 0440)"
else
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  printf '%s\n' "$SUDOERS_LINE" > "$TMP"
  visudo -cf "$TMP" >/dev/null || { say "sudoers syntax check failed; nothing installed"; exit 1; }
  install -m 440 -o root -g wheel "$TMP" "$SUDOERS_FILE"
fi

# --- prove it, from both sides ---------------------------------------------------------------------------------------
say ""
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: would check that $ORCH can run a command as $CI, and that $CI CANNOT read $ORCH's key"
else
  who="$(sudo -u "$ORCH" -H sudo -n -u "$CI" /usr/bin/id -un 2>/dev/null || true)"
  [ "$who" = "$CI" ] && say "PASS  $ORCH can run commands as $CI" || { say "FAIL  $ORCH cannot run commands as $CI"; exit 1; }
  if sudo -u "$CI" /bin/cat "/Users/$ORCH/.apx/app.pem" >/dev/null 2>&1; then
    say "FAIL  $CI can read $ORCH's App key: the split is NOT in place"; exit 1
  else
    say "PASS  $CI cannot read $ORCH's App key"
  fi
fi

say ""
say "Add these lines to /Users/$ORCH/.apx/apx.env (as $ORCH), refresh the clone, then run the doctor:"
say "  APX_CI_USER=$CI"
say "  APX_CI_WORK=$CI_HOME/work"
say "  APX_SHARED=$SHARED"
say "Whenever you refresh /Users/$ORCH/autopilot also refresh $SHARED/autopilot (the code the sandbox runs):"
say "  sudo -u $ORCH -H git -C $SHARED/autopilot pull --ff-only"
