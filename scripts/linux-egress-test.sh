#!/usr/bin/env bash
# Check, on a real Linux kernel, that the apx egress rules do what they claim: deploy/linux/egress-selftest.sh builds a fake internet inside
# a throwaway container, loads the real rules and resolver config, and tries to break out as each of the three accounts.
#   scripts/linux-egress-test.sh
# This proves the RULES work on a Linux kernel. It does not prove anything about the real VPS (its own probe comes at provisioning).
# Safety, each pinned by tests/test_linux_egress_script.py:
#   - only COMMITTED files go in (git archive), mounted read-only; your home folder is not mounted;
#   - the one extra permission is NET_ADMIN, which only affects the container's own network namespace; no --privileged, no host network;
#   - the container is deleted when it exits, and so is the temporary export.
# Needs Docker, and network inside the container for apt (nftables, dnsmasq, iproute2).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
docker_bin="${DOCKER:-$(command -v docker || echo /Applications/Docker.app/Contents/Resources/bin/docker)}"
image="${LINUX_TEST_IMAGE:-python:3.13-slim}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git -C "$here" archive HEAD | tar -x -C "$tmp"
# The single quotes are deliberate: everything here must run INSIDE the container.
# shellcheck disable=SC2016
"$docker_bin" run --rm --cap-add NET_ADMIN -v "$tmp:/src:ro" "$image" bash -c '
set -e
echo "kernel: $(uname -sr)"
apt-get update -qq >/dev/null && apt-get install -y -qq nftables dnsmasq iproute2 >/dev/null 2>&1
nft --version
dnsmasq --version | head -1
bash /src/deploy/linux/egress-selftest.sh
'
