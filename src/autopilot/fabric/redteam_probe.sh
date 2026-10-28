#!/usr/bin/env bash
# Red-team probe: runs INSIDE a runner sandbox. Every attack must FAIL; one that succeeds is a leak and fails the probe.
# Usage: LANE=ci|exec|trusted redteam_probe.sh      Exit status = number of leaks (0 = sealed). Never prints secret values.
# Do not run this on a normal workstation: it deliberately probes private addresses.
set -u
LANE="${LANE:?set LANE}"
leaks=0

tcp() { timeout 4 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null; }   # true when a TCP connection opens
must_fail() { local name="$1"; shift; if "$@"; then echo "LEAK  $name"; leaks=$((leaks+1)); else echo "ok    $name"; fi; }
must_pass() { local name="$1"; shift; if "$@"; then echo "ok    $name"; else echo "BROKEN $name (allowed path unreachable; probe would be vacuous)"; leaks=$((leaks+1)); fi; }

gw="$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')"

# 1. lateral movement: private ranges, gateway, cloud metadata, loopback services of the host
for ip in ${gw:-} 192.168.0.1 192.168.1.1 10.0.0.1 172.16.0.1 100.100.100.100 169.254.169.254; do
  must_fail "lan/metadata $ip:80" tcp "$ip" 80
  must_fail "lan $ip:22" tcp "$ip" 22
done

# 2. arbitrary internet host and a raw IP over 443 (an IP not resolved through the allowlisting resolver is unreachable)
must_fail "arbitrary host example.com:443" tcp example.com 443
must_fail "raw ip 1.1.1.1:443 (DoH/CDN)" tcp 1.1.1.1 443

# 3. DNS escapes: other resolvers, DoT, tunnelling through a name that is not on the list
must_fail "direct DNS 1.1.1.1:53" tcp 1.1.1.1 53
must_fail "DoT 1.1.1.1:853" tcp 1.1.1.1 853
must_fail "resolve a random name" bash -c 'getent hosts "ap-$RANDOM-$RANDOM.attacker-example.com" >/dev/null 2>&1'

# 4. IPv6 is off the table
must_fail "ipv6 egress" bash -c 'timeout 4 bash -c "exec 3<>/dev/tcp/2606:4700:4700::1111/443" 2>/dev/null'

# 5. host and credential exposure inside the sandbox
must_fail "docker socket present" test -e /var/run/docker.sock
must_fail "host ssh keys readable" bash -c 'ls /root/.ssh/id_* "$HOME"/.ssh/id_* 2>/dev/null | grep -q .'
must_fail "gh credentials present" bash -c 'test -e "$HOME/.config/gh/hosts.yml"'
case "$LANE" in
  exec) ;;                                    # the model token is allowed to exist here, and only here
  *) must_fail "Claude token in env ($LANE lane)" bash -c '[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}${ANTHROPIC_API_KEY:-}" ]' ;;
esac

# 6. resource limits (a fork bomb must hit a cap, not the host)
must_fail "unlimited pids" bash -c 'p=$(cat /sys/fs/cgroup/pids.max 2>/dev/null || echo max); [ "$p" = max ]'

# 7. lane isolation of allowed hosts, and a sanity check that the allowed path works
must_pass "github.com:443 reachable" tcp github.com 443
case "$LANE" in
  ci)      must_pass "registry reachable" tcp registry.npmjs.org 443; must_fail "anthropic from ci lane" tcp api.anthropic.com 443 ;;
  exec)    must_pass "anthropic reachable" tcp api.anthropic.com 443;  must_fail "registry from exec lane" tcp registry.npmjs.org 443 ;;
  trusted) must_fail "registry from trusted lane" tcp registry.npmjs.org 443; must_fail "anthropic from trusted lane" tcp api.anthropic.com 443 ;;
esac

echo "leaks: $leaks"
exit "$leaks"
