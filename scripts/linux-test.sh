#!/usr/bin/env bash
# Run this repo's tests on a real Linux kernel, in a throwaway container. For checking what a Mac cannot: apx's own CI lane will run this
# suite on a Linux host, and a simulated platform cannot catch what a real one does (it missed two tests that a real run caught).
#   scripts/linux-test.sh                       # the apx tests
#   scripts/linux-test.sh tests/test_engine.py  # any pytest arguments
# Safety, each pinned by tests/test_linux_test_script.py:
#   - only COMMITTED files go in (git archive), so untracked notes, keys and local files never reach the container;
#   - they are mounted read-only, your home folder is not mounted, and the container is not privileged;
#   - the container is deleted when it exits, and so is the temporary export.
# Needs Docker. It downloads the image and a few apt/pip packages inside the container (network), which is the point of the exercise.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
docker_bin="${DOCKER:-$(command -v docker || echo /Applications/Docker.app/Contents/Resources/bin/docker)}"
image="${LINUX_TEST_IMAGE:-python:3.13-slim}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git -C "$here" archive HEAD | tar -x -C "$tmp"
[ "$#" -gt 0 ] || set -- 'tests/test_apx_*.py'
# The single quotes are deliberate: $(uname) and "$@" must expand INSIDE the container, not on this machine.
# shellcheck disable=SC2016
"$docker_bin" run --rm -v "$tmp:/src:ro" -e UV_PYTHON_DOWNLOADS=never -e UV_PYTHON=python3 "$image" bash -c '
set -e
echo "kernel: $(uname -sr)"
apt-get update -qq >/dev/null && apt-get install -y -qq git openssl >/dev/null 2>&1
pip install -q uv 2>&1 | tail -1
mkdir /work && cp -r /src/. /work && cd /work
git init -q
uv sync -q 2>&1 | tail -2
uv run pytest -q -p no:cacheprovider $@
' _ "$@"
