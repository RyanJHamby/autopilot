#!/bin/bash
# Create the model's account (backlog S1b) and move the Claude token into it. Run ONCE by the owner, AFTER deploy/apx-ci-account.sh:
#   DRY_RUN=1 bash deploy/apx-agent-account.sh   # preview: prints what it would do, changes nothing, needs no sudo
#   sudo bash deploy/apx-agent-account.sh        # do it (it prompts for the new account's password)
#
# After this the Claude token lives ONLY in apx-agent's home. apx-agent holds nothing that can write to GitHub (it gets a short-lived,
# read-only, single-repo token for each checkout) and cannot read the App key; the orchestrator (apx) holds the App key and never sees
# the Claude token. The model's changes come back as data and apx makes the commit.
# One sudoers line lets apx act as apx-agent and nothing else:   apx ALL=(apx-agent) NOPASSWD:SETENV: ALL   (checked with visudo first)
# The ONLY thing this script deletes is apx's old copy of the Claude token, and only after apx-agent has been shown to read its own.
set -euo pipefail

AGENT=apx-agent
CI=apx-ci
ORCH=apx
AGENT_HOME="/Users/$AGENT"
SHARED="${SHARED:-/Users/Shared/apx}"
OWNER_HOME="${OWNER_HOME:-/Users/ryanhamby}"
OLD_TOKEN="/Users/$ORCH/.apx/claude-oauth"
NEW_TOKEN="$AGENT_HOME/.apx/claude-oauth"
DRY_RUN="${DRY_RUN:-0}"
KEEP_OLD_TOKEN="${KEEP_OLD_TOKEN:-0}"
SUDOERS_FILE="/etc/sudoers.d/apx-agent"
SUDOERS_LINE="$ORCH ALL=($AGENT) NOPASSWD:SETENV: ALL"

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN: $*"; else "$@"; fi; }
fail() { say "FAIL  $*"; exit 1; }

if [ "$DRY_RUN" != 1 ]; then
  [ "$(id -u)" = 0 ] || { say "run with sudo (or DRY_RUN=1 to preview)"; exit 1; }
  id "$ORCH" >/dev/null 2>&1 || { say "the $ORCH account does not exist"; exit 1; }
  id "$CI" >/dev/null 2>&1 || { say "run deploy/apx-ci-account.sh first (it creates the shared code area)"; exit 1; }
  [ -f "$OLD_TOKEN" ] || [ -f "$NEW_TOKEN" ] || { say "no Claude token found at $OLD_TOKEN"; exit 1; }
  CLAUDE_BIN="$(readlink "$OWNER_HOME/.local/bin/claude" 2>/dev/null || true)"
  [ -x "$CLAUDE_BIN" ] || { say "cannot find the claude binary under $OWNER_HOME/.local/bin"; exit 1; }
else
  CLAUDE_BIN="$OWNER_HOME/.local/share/claude/versions/<current>"
fi

# --- the account -----------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ] || ! id "$AGENT" >/dev/null 2>&1; then
  run sysadminctl -addUser "$AGENT" -fullName "apx model sandbox" -home "$AGENT_HOME" -shell /bin/zsh -password -
else
  say "$AGENT already exists; leaving it"
fi
if [ "$DRY_RUN" != 1 ] && dseditgroup -o checkmember -m "$AGENT" admin 2>/dev/null | grep -q "is a member"; then
  fail "$AGENT must NOT be an admin"
fi

# --- its home: private, with the claude binary and its own work area --------------------------------------------------
run install -d -m 700 -o "$AGENT" -g staff "$AGENT_HOME" "$AGENT_HOME/work" "$AGENT_HOME/.apx" "$AGENT_HOME/.local" "$AGENT_HOME/.local/bin"
run install -m 755 -o "$AGENT" -g staff "$CLAUDE_BIN" "$AGENT_HOME/.local/bin/claude"

# --- the Claude token: copy in, prove the agent can read it, only then remove the orchestrator's copy -------------------
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: install -m 600 -o $AGENT -g staff $OLD_TOKEN $NEW_TOKEN"
elif [ -f "$OLD_TOKEN" ]; then
  install -m 600 -o "$AGENT" -g staff "$OLD_TOKEN" "$NEW_TOKEN"
fi

# --- the single sudoers rule, syntax-checked before it is installed ---------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: write '$SUDOERS_LINE' to a temp file, run 'visudo -cf' on it, then install it as $SUDOERS_FILE (root:wheel, 0440)"
else
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  printf '%s\n' "$SUDOERS_LINE" > "$TMP"
  visudo -cf "$TMP" >/dev/null || { say "sudoers syntax check failed; nothing installed"; exit 1; }
  install -m 440 -o root -g wheel "$TMP" "$SUDOERS_FILE"
fi

# --- prove it from every side -----------------------------------------------------------------------------------------
say ""
if [ "$DRY_RUN" = 1 ]; then
  say "DRY-RUN: would check that $ORCH can run a command as $AGENT; that $AGENT cannot read $ORCH's App key or home; that $CI cannot read"
  say "DRY-RUN: $AGENT's token; that $AGENT can read its own token and run claude; then remove $ORCH's old copy of the token"
else
  who="$(sudo -u "$ORCH" -H sudo -n -u "$AGENT" /usr/bin/id -un 2>/dev/null || true)"
  [ "$who" = "$AGENT" ] && say "PASS  $ORCH can run commands as $AGENT" || fail "$ORCH cannot run commands as $AGENT"
  if sudo -u "$AGENT" /bin/cat "/Users/$ORCH/.apx/app.pem" >/dev/null 2>&1; then fail "$AGENT can read $ORCH's App key: the split is NOT in place"; fi
  say "PASS  $AGENT cannot read $ORCH's App key"
  if sudo -u "$AGENT" /bin/ls "/Users/$ORCH/.apx" >/dev/null 2>&1; then fail "$AGENT can list $ORCH's home: the split is NOT in place"; fi
  say "PASS  $AGENT cannot read $ORCH's home"
  if sudo -u "$CI" /bin/cat "$NEW_TOKEN" >/dev/null 2>&1; then fail "$CI can read the model's token: the accounts are not separated"; fi
  say "PASS  $CI (the account that runs PR code) cannot read the model's token"
  sudo -u "$AGENT" /bin/test -r "$NEW_TOKEN" || fail "$AGENT cannot read its own token"
  say "PASS  $AGENT can read its own Claude token"
  sudo -u "$AGENT" "$AGENT_HOME/.local/bin/claude" --version >/dev/null 2>&1 || fail "$AGENT cannot run the claude CLI"
  say "PASS  $AGENT can run the claude CLI"
  if [ -f "$OLD_TOKEN" ] && [ "$KEEP_OLD_TOKEN" != 1 ]; then
    rm -f "$OLD_TOKEN"
    say "DONE  removed $ORCH's copy of the Claude token (the only thing this script deletes)"
  fi
fi

say ""
say "Next, as $ORCH: add this line to /Users/$ORCH/.apx/apx.env and delete any APX_OAUTH_FILE line (the token is no longer there):"
say "  APX_AGENT_USER=$AGENT"
say "Refresh the code both accounts run, then run the doctor:"
say "  sudo -u $ORCH -H git -C /Users/$ORCH/autopilot pull --ff-only"
say "  sudo -u $ORCH -H git -C $SHARED/autopilot pull --ff-only"
