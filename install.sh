#!/usr/bin/env bash
# Installs the `ap` CLI (editable, so kit/ and policy/ edits take effect immediately).
set -euo pipefail
cd "$(dirname "$0")"
uv tool install --editable --force .
echo "installed: $(command -v ap || echo '~/.local/bin/ap (open a new shell)')"
