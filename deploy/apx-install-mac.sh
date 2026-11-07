#!/bin/bash
# Move apx into its own macOS account. Run ONCE by the owner:   sudo bash deploy/apx-install-mac.sh
# Preview first (no sudo, changes nothing):                      DRY_RUN=1 bash deploy/apx-install-mac.sh
#
# What it does (and nothing else):
#   - checks the `apx` account exists and is NOT an admin
#   - copies the App key, App id and Claude token from the owner's ~/.apx into /Users/apx/.apx (600/700, owned by apx)
#   - rewrites the settings file so every path points at /Users/apx and ONLY the repos in REPOS are enabled
#   - copies the `uv` and `claude` binaries into /Users/apx/.local/bin (apx cannot read the owner's home)
#   - clones the (public) autopilot repo into /Users/apx/autopilot and syncs its Python environment
#   - runs the doctor as apx
# It does NOT install the timer (see deploy/launchd/com.autopilot.apx.daemon.plist) and deletes nothing. The owner's own
# copy of the secrets in ~/.apx stays until you remove it after the doctor passes as apx.
set -euo pipefail

OWNER_HOME="${OWNER_HOME:-/Users/ryanhamby}"
APX_HOME="/Users/apx"
REPOS="${REPOS:-RyanJHamby/autopilot}"          # shadow week: autopilot only. Add stencil/drillpad-workspace later.
INSTALLATION_ID="${INSTALLATION_ID:-}"
DRY_RUN="${DRY_RUN:-0}"

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN: $*"; else "$@"; fi; }
as_apx() { if [ "$DRY_RUN" = 1 ]; then say "DRY-RUN (as apx): $*"; else sudo -u apx -H "$@"; fi; }
need() { [ -e "$1" ] || { say "missing: $1"; exit 1; }; }

[ "$DRY_RUN" = 1 ] || [ "$(id -u)" = 0 ] || { say "run with sudo (or DRY_RUN=1 to preview)"; exit 1; }

# --- preconditions -----------------------------------------------------------------------------------------------
id apx >/dev/null 2>&1 || { say "the apx account does not exist"; exit 1; }
if dseditgroup -o checkmember -m apx admin 2>/dev/null | grep -q "is a member"; then say "apx must NOT be an admin"; exit 1; fi
[ -d "$APX_HOME" ] || { say "$APX_HOME does not exist"; exit 1; }
for f in app.pem app.id apx.env claude-oauth; do need "$OWNER_HOME/.apx/$f"; done
need "$OWNER_HOME/.local/bin/uv"
CLAUDE_BIN="$(readlink "$OWNER_HOME/.local/bin/claude" 2>/dev/null || true)"; need "$CLAUDE_BIN"
say "claude binary: $CLAUDE_BIN"

# --- secrets (mode 600 in a 700 directory, owned by apx) ---------------------------------------------------------
run install -d -m 700 -o apx -g staff "$APX_HOME/.apx" "$APX_HOME/.apx/work" "$APX_HOME/.local" "$APX_HOME/.local/bin" "$APX_HOME/Library/Logs"
for f in app.pem claude-oauth; do run install -m 600 -o apx -g staff "$OWNER_HOME/.apx/$f" "$APX_HOME/.apx/$f"; done
run install -m 644 -o apx -g staff "$OWNER_HOME/.apx/app.id" "$APX_HOME/.apx/app.id"   # the public App id, not a secret

# --- settings: paths -> apx home, and only the chosen repos -------------------------------------------------------
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
python3 - "$OWNER_HOME/.apx/apx.env" "$OWNER_HOME" "$APX_HOME" "$REPOS" "$INSTALLATION_ID" > "$TMP" <<'PY'
import sys
src, owner_home, apx_home, repos, inst = sys.argv[1:]
keep = set(r for r in repos.split(",") if r)
out = []
for line in open(src).read().splitlines():
    if line.startswith("APX_INSTALLATIONS="):
        pairs = [p for p in line.split("=", 1)[1].split(",") if p.split("=")[0] in keep]
        if not pairs:
            sys.exit("none of REPOS found in APX_INSTALLATIONS")
        line = "APX_INSTALLATIONS=" + ",".join(pairs)
    out.append(line.replace(owner_home + "/.apx", apx_home + "/.apx"))
print("\n".join(out))
PY
run install -m 600 -o apx -g staff "$TMP" "$APX_HOME/.apx/apx.env"

# --- tools apx cannot reach in the owner's home -------------------------------------------------------------------
run install -m 755 -o apx -g staff "$OWNER_HOME/.local/bin/uv" "$APX_HOME/.local/bin/uv"
run install -m 755 -o apx -g staff "$CLAUDE_BIN" "$APX_HOME/.local/bin/claude"

# --- code: the autopilot repo is public, so no credentials are needed ---------------------------------------------
if [ "$DRY_RUN" = 1 ] || [ ! -d "$APX_HOME/autopilot/.git" ]; then
  as_apx git clone --quiet https://github.com/RyanJHamby/autopilot.git "$APX_HOME/autopilot"
else
  as_apx git -C "$APX_HOME/autopilot" pull --quiet --ff-only
fi
as_apx env PATH="$APX_HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" sh -c "cd $APX_HOME/autopilot && uv sync --quiet"

# --- prove it, as apx ---------------------------------------------------------------------------------------------
say ""
say "Running the doctor as apx..."
as_apx env PATH="$APX_HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" sh -c \
  "set -a; . $APX_HOME/.apx/apx.env; set +a; cd $APX_HOME/autopilot && uv run python -m autopilot.apx.daemon --doctor"
say ""
say "Done. Next: after the doctor passes, remove your own copy of the secrets:  $OWNER_HOME/.apx/app.pem and claude-oauth"
