#!/usr/bin/env bash
# Does the kernel really enforce the egress rules from autopilot.apx.nftrules? Run as root INSIDE A THROWAWAY CONTAINER with only
# NET_ADMIN (scripts/linux-egress-test.sh does exactly that). It builds a fake internet on the loopback device, loads the real rules and
# the real resolver config, and tries to break out as each of the three accounts. Every "blocked" case is paired with a control: the
# same connection made by an unrestricted account must succeed, so a refusal can only come from the rules and never from a missing listener.
#
# It refuses to run if the table already exists (a real host with rules loaded), because it would replace them.
# This is the container check only. The probe on the real VPS (P3) is a separate, later step and is not covered by a pass here.
set -uo pipefail

src="${APX_SRC:-$(cd "$(dirname "$0")/../.." && pwd)}"
work="$(mktemp -d)"
pids=()
fails=0
passes=0

cleanup() {
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null; done
  rm -rf "$work"
}
trap cleanup EXIT

say() { printf '%s\n' "$*"; }
pass() { passes=$((passes + 1)); say "PASS  $*"; }
fail() { fails=$((fails + 1)); say "FAIL  $*"; }

[ "$(id -u)" = 0 ] || { say "must run as root, in a throwaway container"; exit 2; }
if nft list table inet apx >/dev/null 2>&1; then say "table inet apx already exists; refusing to replace a live ruleset"; exit 2; fi

PY="${PYTHON:-python3}"
export PYTHONPATH="$src/src"

# --- accounts (numeric uids are what the rules match) --------------------------------------------------------------------------------
for u in apx apx-ci apx-agent; do id "$u" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$u"; done
uid_of() { id -u "$1"; }
gid_of() { id -g "$1"; }
as() { # as USER cmd...  (no supplementary groups, so nothing leaks in from root)
  local who="$1"
  shift
  setpriv --reuid="$(uid_of "$who")" --regid="$(gid_of "$who")" --clear-groups "$@"
}
CONTROL=nobody

# --- the fake internet ---------------------------------------------------------------------------------------------------------------
GH=203.0.113.10 API=203.0.113.20 NPM=203.0.113.30 STRAY=198.51.100.7 PRIVATE=10.99.0.5
for ip in $GH $API $NPM $STRAY $PRIVATE; do ip addr add "$ip/32" dev lo; done
ip -6 addr show dev lo | grep -q '::1' && HAVE6=1 || HAVE6=0

cat >"$work/fakes.py" <<'PYEOF'
import socket, struct, sys, threading

ANSWERS = {
    "github.com": "203.0.113.10", "api.github.com": "203.0.113.10", "raw.githubusercontent.com": "203.0.113.10",
    "api.anthropic.com": "203.0.113.20", "registry.npmjs.org": "203.0.113.30", "pypi.org": "203.0.113.30",
    "codeload.github.com": "10.99.0.5",  # an allowed name that resolves into a private range: DNS rebinding
}
DEFAULT = "198.51.100.7"  # any other name; if this ever resolves for a sandbox account, the DNS redirect failed

def dns():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.2", 53))
    while True:
        data, addr = s.recvfrom(512)
        qid = data[:2]
        i, labels = 12, []
        while data[i]:
            n = data[i]; labels.append(data[i + 1:i + 1 + n].decode()); i += n + 1
        qtype = struct.unpack("!H", data[i + 1:i + 3])[0]
        question = data[12:i + 5]
        name = ".".join(labels).lower()
        if qtype == 1:
            ip = ANSWERS.get(name, DEFAULT)
            ans = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + socket.inet_aton(ip)
            s.sendto(qid + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + question + ans, addr)
        else:
            s.sendto(qid + b"\x81\x80\x00\x01\x00\x00\x00\x00\x00\x00" + question, addr)

def listen(host, port, family=socket.AF_INET):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port)); s.listen(16)
    while True:
        c, _ = s.accept(); c.close()

threading.Thread(target=dns, daemon=True).start()
for h in ("203.0.113.10", "203.0.113.20", "203.0.113.30", "198.51.100.7", "10.99.0.5"):
    for p in (443, 80):
        threading.Thread(target=listen, args=(h, p), daemon=True).start()
threading.Thread(target=listen, args=("127.0.0.1", 8080), daemon=True).start()
if len(sys.argv) > 1 and sys.argv[1] == "ipv6":
    threading.Thread(target=listen, args=("::1", 443, socket.AF_INET6), daemon=True).start()
print("ready", flush=True)
threading.Event().wait()
PYEOF
fake_args=()
[ "$HAVE6" = 1 ] && fake_args=(ipv6)
"$PY" "$work/fakes.py" "${fake_args[@]}" >"$work/fakes.out" 2>&1 &
pids+=("$!")
for _ in $(seq 1 50); do grep -q ready "$work/fakes.out" 2>/dev/null && break; sleep 0.1; done
grep -q ready "$work/fakes.out" || { say "fake internet did not start"; cat "$work/fakes.out"; exit 2; }

# --- the real rules and resolver config ----------------------------------------------------------------------------------------------
"$PY" -m autopilot.apx.nftrules nft --uid "apx=$(uid_of apx)" --uid "apx-ci=$(uid_of apx-ci)" --uid "apx-agent=$(uid_of apx-agent)" >"$work/apx.nft" || exit 2
"$PY" -m autopilot.apx.nftrules dnsmasq --upstream 127.0.0.2 >"$work/dnsmasq.conf" || exit 2

if nft -c -f "$work/apx.nft"; then pass "nft accepts the generated ruleset (syntax check)"; else fail "nft rejected the generated ruleset"; fi
if nft -f "$work/apx.nft" && nft -f "$work/apx.nft"; then pass "the ruleset loads, and loading it again replaces it instead of failing"; else fail "ruleset did not load twice"; fi
if [ "$(nft list tables | grep -c 'inet apx')" = 1 ]; then pass "exactly one apx table after two loads"; else fail "tables stacked up"; fi

if dnsmasq --version | grep -q nftset; then pass "this dnsmasq has nftset support"; else fail "dnsmasq lacks nftset support, so the allowlist cannot be fed"; fi
if dnsmasq --test --conf-file="$work/dnsmasq.conf" 2>&1 | grep -qi 'syntax check OK'; then pass "dnsmasq accepts the generated config"; else fail "dnsmasq rejected the generated config"; fi
dnsmasq --keep-in-foreground --conf-file="$work/dnsmasq.conf" --user=root --pid-file="$work/dnsmasq.pid" >"$work/dnsmasq.out" 2>&1 &
pids+=("$!")
sleep 1
kill -0 "${pids[-1]}" 2>/dev/null || { say "dnsmasq did not stay up"; cat "$work/dnsmasq.out"; exit 2; }
# an arbitrary nameserver address: the redirect, not this file, must decide who answers
printf 'nameserver 8.8.8.8\noptions timeout:1 attempts:1\n' >/etc/resolv.conf

# --- helpers: each prints nothing and returns 0 on success -----------------------------------------------------------------------
tcp() { # tcp USER HOST PORT [v6]
  as "$1" "$PY" -c '
import socket, sys
fam = socket.AF_INET6 if len(sys.argv) > 3 else socket.AF_INET
s = socket.socket(fam, socket.SOCK_STREAM); s.settimeout(3)
try:
    s.connect((sys.argv[1], int(sys.argv[2])))
except OSError:
    sys.exit(1)
' "$2" "$3" ${4:+v6}
}
resolve() { # resolve USER NAME -> prints the address or nothing
  as "$1" "$PY" -c '
import socket, sys
try:
    print(socket.gethostbyname(sys.argv[1]))
except OSError:
    pass
' "$2"
}

rawdns() { # rawdns USER SERVER NAME -> asks SERVER:53 directly (UDP) and prints the first A record, or nothing
  as "$1" "$PY" -c '
import socket, struct, sys
server, name = sys.argv[1], sys.argv[2]
q = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\x00\x00\x01\x00\x01"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
try:
    s.sendto(q, (server, 53)); r = s.recv(512)
except OSError:
    sys.exit(0)
if struct.unpack("!H", r[6:8])[0]:
    print(socket.inet_ntoa(r[-4:]))
' "$2" "$3"
}

ok() { # ok USER LABEL HOST PORT
  if tcp "$1" "$3" "$4"; then pass "$1: $2"; else fail "$1: $2 (should connect)"; fi
}
blocked() { # blocked USER LABEL HOST PORT [v6] : the control account must connect, the sandbox account must not
  if ! tcp "$CONTROL" "$3" "$4" ${5:+v6}; then fail "$1: $2 (control could not connect, so this proves nothing)"; return; fi
  if tcp "$1" "$3" "$4" ${5:+v6}; then fail "$1: $2 (CONNECTED, should be refused)"; else pass "$1: $2"; fi
}
resolves_to() { # resolves_to USER NAME WANT ("" = must not resolve)
  local got
  got="$(resolve "$1" "$2")"
  if [ "$got" = "$3" ]; then pass "$1: $2 -> ${3:-nothing}"; else fail "$1: $2 resolved to '${got}', wanted '${3}'"; fi
}

say "--- DNS: only allowlisted names resolve, and the sandbox accounts cannot pick another resolver"
for u in apx-ci apx-agent apx; do
  resolves_to "$u" evil.example.com ""
  resolves_to "$u" github.com "$GH"
done
resolves_to apx-ci registry.npmjs.org "$NPM"
resolves_to apx-agent api.anthropic.com "$API"
# Asking another resolver directly must not work: the fake upstream at 127.0.0.2 would answer ANY name, so an answer here means the redirect failed.
got="$(rawdns "$CONTROL" 127.0.0.2 evil.example.com)"
if [ "$got" = "$STRAY" ]; then pass "control: an unrestricted account IS answered by the fake upstream (so the next checks mean something)"; else fail "control: fake upstream gave '$got', wanted $STRAY"; fi
for u in apx-ci apx-agent apx; do
  got="$(rawdns "$u" 127.0.0.2 evil.example.com)"
  if [ -z "$got" ]; then pass "$u: a direct query to another resolver is redirected and gets no answer"; else fail "$u: reached another resolver directly and got $got"; fi
done

say "--- connections by lane"
# warm the sets exactly as real use would: by resolving names
resolve apx-ci github.com >/dev/null; resolve apx-ci registry.npmjs.org >/dev/null; resolve apx-ci api.anthropic.com >/dev/null
resolve apx-agent github.com >/dev/null; resolve apx-agent api.anthropic.com >/dev/null
resolve apx github.com >/dev/null
ok apx-ci "github over 443" $GH 443
ok apx-ci "an npm registry over 443" $NPM 443
ok apx-agent "github over 443" $GH 443
ok apx-agent "the model API over 443" $API 443
ok apx "github over 443" $GH 443
blocked apx-ci "the model API (resolved, but only the agent lane may reach it)" $API 443
blocked apx-agent "an npm registry (not in the agent lane)" $NPM 443
blocked apx "an npm registry (not in the orchestrator lane)" $NPM 443
blocked apx "the model API (not in the orchestrator lane)" $API 443

say "--- everything else is refused, for all three accounts"
resolve apx-ci codeload.github.com >/dev/null
for u in apx-ci apx-agent apx; do
  blocked "$u" "an address no allowed name resolved to" $STRAY 443
  blocked "$u" "an allowed address on the wrong port" $GH 80
  blocked "$u" "an allowed name that resolved into a private range (rebinding)" $PRIVATE 443
  blocked "$u" "another service on loopback" 127.0.0.1 8080
  if [ "$HAVE6" = 1 ]; then blocked "$u" "IPv6" ::1 443 v6; else say "SKIP  $u: IPv6 (no ::1 in this container)"; fi
done

say "--- a table that never matches these uids changes nothing for anyone else"
if tcp "$CONTROL" $STRAY 443 && tcp root $STRAY 443; then pass "unrestricted accounts still reach any address"; else fail "rules leaked onto other accounts"; fi

say
say "passed: $passes  failed: $fails"
[ "$fails" = 0 ]
