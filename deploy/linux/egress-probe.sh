#!/usr/bin/env bash
# The probe that matters: on the REAL host, try to break out of the egress allowlist as each sandbox account. Run as root, after bootstrap:
#   sudo bash deploy/linux/egress-probe.sh
# Every "must fail" attempt has to fail; the allowed path (GitHub on 443) has to work, otherwise a refusal could just mean no connectivity.
# Prints ok / LEAK / BROKEN per attempt and exits with the number of problems. The container version of these checks is
# scripts/linux-egress-test.sh; passing that proves the rules, passing THIS proves the host. Neither is a claim about a persistent attacker.
# Limits: an address that is not live fails either way, so a few probes only prove something where a device answers. Anything an allowed
# name resolves to is reachable on 443 by design (see docs/apx-linux-host.md, "what the allowlist does not close").
# The helpers below are called indirectly, through must_fail and must_pass.
# shellcheck disable=SC2329
set -u

problems=0
[ "$(id -u)" = 0 ] || { echo "run as root (it switches to each sandbox account itself)"; exit 2; }
if ! { command -v nft >/dev/null 2>&1 && nft list table inet apx >/dev/null 2>&1; }; then echo "table inet apx is not loaded: run bootstrap.sh and start apx-nft.service first"; exit 2; fi

as() { local who="$1"; shift; setpriv --reuid="$(id -u "$who")" --regid="$(id -g "$who")" --init-groups "$@"; }
tcp() { as "$WHO" nc -z -w 4 "$@" >/dev/null 2>&1; }
tcp6() { as "$WHO" nc -6 -z -w 4 "$@" >/dev/null 2>&1; }
must_fail() { local name="$1"; shift; if "$@"; then echo "LEAK    $WHO: $name"; problems=$((problems + 1)); else echo "ok      $WHO: $name"; fi; }
must_pass() { local name="$1"; shift; if "$@"; then echo "ok      $WHO: $name"; else echo "BROKEN  $WHO: $name (the allowed path is down, so the probe proves nothing)"; problems=$((problems + 1)); fi; }
# resolve NAME via SERVER over UDP/53 as $WHO, printing the first A record or nothing
ask() {
  as "$WHO" python3 -c '
import socket, struct, sys
server, name = sys.argv[1], sys.argv[2]
q = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\x00\x00\x01\x00\x01"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3)
try:
    s.sendto(q, (server, 53)); r = s.recv(512)
except OSError:
    sys.exit(0)
if struct.unpack("!H", r[6:8])[0]:
    print(socket.inet_ntoa(r[-4:]))
' "$1" "$2"
}
dns_works() { [ -n "$(ask "$1" "$2")" ]; }

gw="$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')"
for WHO in apx-ci apx-agent apx; do
  echo "--- $WHO   gateway: ${gw:-unknown}"
  for ip in ${gw:-} 10.0.0.1 192.168.0.1 192.168.1.1 172.16.0.1 100.64.0.1 169.254.169.254 127.0.0.53; do
    must_fail "private/metadata $ip:80" tcp "$ip" 80
    must_fail "private/metadata $ip:443" tcp "$ip" 443
  done
  must_fail "an arbitrary public host on 443 (1.1.1.1)" tcp 1.1.1.1 443
  must_fail "IPv6 to a public resolver" tcp6 2606:4700:4700::1111 443
  must_fail "ssh to github (port 22)" tcp github.com 22
  must_fail "DoT to 1.1.1.1:853" tcp 1.1.1.1 853
  must_fail "another resolver (1.1.1.1:53) answering an unlisted name" dns_works 1.1.1.1 example.com
  must_fail "the allowlist resolver answering an unlisted name" dns_works 127.0.0.1 example.com
  must_pass "an allowlisted name resolves through the redirected resolver" dns_works 9.9.9.9 github.com
  must_pass "github over 443 still works" tcp api.github.com 443
done

echo
echo "known gaps: names the allowlist permits are reachable on 443 by design; their addresses are shared with other customers of the same hosts"
if [ "$problems" = 0 ]; then echo "sealed: every must-fail failed, every allowed path worked"; else echo "$problems problem(s)"; fi
exit "$problems"
