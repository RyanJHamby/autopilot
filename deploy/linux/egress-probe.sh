#!/usr/bin/env bash
# The probe that matters: on the REAL host, try to break out of the egress allowlist as each sandbox account. Run as root, after bootstrap:
#   sudo bash deploy/linux/egress-probe.sh
# Every "must fail" attempt has to fail; the allowed path (GitHub on 443) has to work, otherwise a refusal could just mean no connectivity.
# Prints ok / LEAK / BROKEN per attempt and exits with the number of problems. The container version of these checks is
# scripts/linux-egress-test.sh; passing that proves the rules, passing THIS proves the host. Neither is a claim about a persistent attacker.
# Limits: an address that is not live fails either way, so a few probes only prove something where a device answers. Anything an allowed
# name resolves to is reachable on 443 by design (see docs/apx-linux-host.md, "what the allowlist does not close").
# Loopback: the probe opens its own throwaway listeners (as root, on 127.0.0.1 and ::1; they accept and close, they serve nothing) and removes them on
# exit. ci and agent must reach the unprivileged IPv4 port, the orchestrator account must not, nobody may reach the privileged port or ::1.
# Each loopback refusal is paired with a control: root must be able to connect first, otherwise the case is reported BROKEN, not ok.
# The helpers below are called indirectly, through must_fail and must_pass.
# shellcheck disable=SC2329
set -u

problems=0
[ "$(id -u)" = 0 ] || { echo "run as root (it switches to each sandbox account itself)"; exit 2; }
if ! { command -v nft >/dev/null 2>&1 && nft list table inet apx >/dev/null 2>&1; }; then echo "table inet apx is not loaded: run bootstrap.sh and start apx-nft.service first"; exit 2; fi

work="$(mktemp -d)"
lpid=""
trap '[ -z "$lpid" ] || kill "$lpid" 2>/dev/null; rm -rf "$work"' EXIT
# prints "PRIV HIGH V6" (V6 is 0 when the host has no ::1), then keeps the three listeners open
python3 -c '
import random, socket, sys, threading
def bind(host, port, fam=socket.AF_INET):
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port)); s.listen(16)
    return s
priv = None
for p in random.sample(range(600, 1000), 400):
    try:
        ls = [bind("127.0.0.1", p)]; priv = p; break
    except OSError:
        pass
if priv is None:
    sys.exit(1)
high = bind("127.0.0.1", 0); ls.append(high)
v6 = 0
try:
    s6 = bind("::1", 0, socket.AF_INET6); ls.append(s6); v6 = s6.getsockname()[1]
except OSError:
    pass
def serve(s):
    while True:
        c, _ = s.accept(); c.close()
for s in ls:
    threading.Thread(target=serve, args=(s,), daemon=True).start()
print(priv, high.getsockname()[1], v6, flush=True)
threading.Event().wait()
' >"$work/ports" 2>/dev/null &
lpid=$!
for _ in $(seq 1 50); do [ -s "$work/ports" ] && break; sleep 0.1; done
read -r lo_priv lo_high lo_v6 <"$work/ports" || true
[ -n "${lo_priv:-}" ] || { echo "could not start the throwaway loopback listeners"; exit 2; }

# shellcheck disable=SC2317  # shellcheck 0.9 (Ubuntu 24.04) wrongly calls helpers defined after an early exit unreachable; 0.10+ does not
as() { local who="$1"; shift; setpriv --reuid="$(id -u "$who")" --regid="$(id -g "$who")" --init-groups "$@"; }
# shellcheck disable=SC2317  # shellcheck 0.9 (Ubuntu 24.04) wrongly calls helpers defined after an early exit unreachable; 0.10+ does not
tcp() { as "$WHO" nc -z -w 4 "$@" >/dev/null 2>&1; }
# shellcheck disable=SC2317  # shellcheck 0.9 (Ubuntu 24.04) wrongly calls helpers defined after an early exit unreachable; 0.10+ does not
tcp6() { as "$WHO" nc -6 -z -w 4 "$@" >/dev/null 2>&1; }
must_fail() { local name="$1"; shift; if "$@"; then echo "LEAK    $WHO: $name"; problems=$((problems + 1)); else echo "ok      $WHO: $name"; fi; }
must_pass() { local name="$1"; shift; if "$@"; then echo "ok      $WHO: $name"; else echo "BROKEN  $WHO: $name (the allowed path is down, so the probe proves nothing)"; problems=$((problems + 1)); fi; }
# control_ok HOST PORT [6]: root (no restrictions) must reach the listener, or a refusal for a sandbox account proves nothing
control_ok() {
  if nc ${3:+-6} -z -w 4 "$1" "$2" >/dev/null 2>&1; then return 0; fi
  echo "BROKEN  $WHO: control as root could not connect to $1:$2, so the loopback case proves nothing"; problems=$((problems + 1)); return 1
}
# resolve NAME via SERVER over UDP/53 as $WHO, printing the first A record or nothing
# shellcheck disable=SC2317  # shellcheck 0.9 (Ubuntu 24.04) wrongly calls helpers defined after an early exit unreachable; 0.10+ does not
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
# shellcheck disable=SC2317  # shellcheck 0.9 (Ubuntu 24.04) wrongly calls helpers defined after an early exit unreachable; 0.10+ does not
dns_works() { [ -n "$(ask "$1" "$2")" ]; }

gw="$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')"
for WHO in apx-ci apx-agent apx; do
  echo "--- $WHO   gateway: ${gw:-unknown}"
  for ip in ${gw:-} 10.0.0.1 192.168.0.1 192.168.1.1 172.16.0.1 100.64.0.1 169.254.169.254 127.0.0.53; do
    must_fail "private/metadata $ip:80" tcp "$ip" 80
    must_fail "private/metadata $ip:443" tcp "$ip" 443
  done
  control_ok 127.0.0.1 "$lo_priv" && must_fail "loopback tcp to a privileged port ($lo_priv; sshd on 22 is the same rule)" tcp 127.0.0.1 "$lo_priv"
  if [ "$WHO" = apx ]; then
    control_ok 127.0.0.1 "$lo_high" && must_fail "loopback tcp to an unprivileged port ($lo_high): the orchestrator lane has no such rule" tcp 127.0.0.1 "$lo_high"
  else
    must_pass "loopback tcp to an unprivileged port ($lo_high): ci and agent need it to run test suites" tcp 127.0.0.1 "$lo_high"
  fi
  if [ "${lo_v6:-0}" != 0 ]; then
    control_ok ::1 "$lo_v6" 6 && must_fail "loopback tcp to ::1 on an unprivileged port ($lo_v6): IPv6 stays refused" tcp6 ::1 "$lo_v6"
  else
    echo "skip    $WHO: ::1 (this host has no IPv6 loopback)"
  fi
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
