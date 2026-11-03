#!/bin/bash
# Try to reach the home network AS the sandbox account; every attempt must fail. Prints ok / LEAK; exits with the number of leaks.
#   sudo -u apx-ci /bin/bash -s < deploy/apx-egress-probe.sh        (and the same with apx-agent)
# Run it before deploy/apx-egress.sh (expect LEAK lines for anything that answers) and after (expect none).
# Limits: an address with no device behind it fails either way, so only a live gateway or device proves the block. Public hosts on 443 stay open.
set -u

leaks=0
tcp() { nc -z -G 4 "$@" >/dev/null 2>&1; }
must_fail() { local name="$1"; shift; if "$@"; then echo "LEAK  $name"; leaks=$((leaks + 1)); else echo "ok    $name"; fi; }
must_pass() { local name="$1"; shift; if "$@"; then echo "ok    $name"; else echo "BROKEN $name (the allowed path is unreachable, so the probe proves nothing)"; leaks=$((leaks + 1)); fi; }

gw="$(route -n get default 2>/dev/null | awk '/gateway:/ {print $2; exit}')"
echo "running as: $(id -un)   gateway: ${gw:-unknown}"

for ip in ${gw:-} 192.168.0.1 192.168.1.1 10.0.0.1 172.16.0.1 169.254.169.254; do
  must_fail "lan/metadata $ip:80" tcp "$ip" 80
  must_fail "lan/metadata $ip:443" tcp "$ip" 443
done
must_fail "ipv6 egress" nc -6 -z -G 4 2606:4700:4700::1111 443
must_fail "ssh to github (not 443)" tcp github.com 22
must_fail "DoT 1.1.1.1:853" tcp 1.1.1.1 853
must_pass "github over 443 still works" tcp api.github.com 443

echo "known gap: any public address on 443 is reachable (no host allowlist yet)"
[ "$leaks" = 0 ] && echo "sealed against the home network" || echo "$leaks leak(s)"
exit "$leaks"
