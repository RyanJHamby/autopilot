#!/usr/bin/env bash
# Run deploy/linux/bootstrap.sh for real inside a throwaway Debian container and check what it builds: the accounts, the file layout and
# permissions, the sudo rules, the generated egress rules, and that the sandbox accounts cannot reach the orchestrator's secrets.
#   scripts/linux-bootstrap-test.sh
# This proves the script and the account/permission split on a real Linux userland. It does NOT prove systemd behaviour, sshd, or
# anything about the real VPS: the container has no systemd or sshd, so those steps are skipped here (SKIP_SYSTEMD, SKIP_SSHD).
# Safety, each pinned by tests/test_linux_bootstrap_script.py:
#   - only COMMITTED files go in (git archive), mounted read-only; your home folder is not mounted;
#   - the one extra permission is NET_ADMIN (to syntax-check the nft rules), inside the container's own network namespace only;
#   - the container is deleted when it exits, and so is the temporary export.
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
set -u
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails + 1)); }
check() { if eval "$2" >/dev/null 2>&1; then pass "$1"; else fail "$1"; fi; }
echo "kernel: $(uname -sr)"
apt-get update -qq >/dev/null && apt-get install -y -qq git sudo nftables util-linux systemd iproute2 netcat-openbsd >/dev/null 2>&1
# a local stand-in for the public repo (the real run clones it from GitHub)
cp -r /src /work && cd /work
git init -q && git add -A && git -c user.name=t -c user.email=t@example.invalid commit -qm export
chmod -R a+rX /work
git config --system --add safe.directory "*"
export APX_CODE_URL=/work SKIP_SYSTEMD=1 SKIP_SSHD=1 PIP_PACKAGES=pyyaml
B=/work/deploy/linux/bootstrap.sh
useradd --create-home owner

echo "--- refusals change nothing"
ADMIN_USER= bash $B >/dev/null 2>&1; [ $? -ne 0 ] && pass "no ADMIN_USER is refused" || fail "no ADMIN_USER was accepted"
ADMIN_USER=apx bash $B >/dev/null 2>&1; [ $? -ne 0 ] && pass "ADMIN_USER=apx is refused" || fail "ADMIN_USER=apx accepted"
ADMIN_USER=owner SKIP_SSHD=0 SKIP_PACKAGES=1 bash $B 2>&1 | grep -q "lock yourself out" && pass "restricting ssh without an authorized key is refused" || fail "no lockout guard"
check "refusals created no accounts" "! id apx"

echo "--- a dry run changes nothing"
DRY_RUN=1 ADMIN_USER=owner SKIP_PACKAGES=1 bash $B >/tmp/dry.out 2>&1; rc=$?
[ $rc -eq 0 ] && pass "dry run exits 0" || { fail "dry run exit $rc"; tail -5 /tmp/dry.out; }
grep -q "^DRY-RUN" /tmp/dry.out && pass "dry run says what it would do" || fail "dry run printed nothing"
check "dry run created no accounts" "! id apx && ! id apx-ci"
check "dry run created no shared tree" "! [ -e /srv/apx ] && ! [ -e /etc/apx ]"

echo "--- the real run"
ADMIN_USER=owner bash $B >/tmp/run1.out 2>&1; rc=$?
[ $rc -eq 0 ] && pass "bootstrap exits 0" || { fail "bootstrap exit $rc"; tail -25 /tmp/run1.out; }
grep -q "^FAIL" /tmp/run1.out && { fail "bootstrap reported a failed check"; grep "^FAIL" /tmp/run1.out; } || pass "no failed checks inside bootstrap"
for u in apx apx-ci apx-agent; do
  check "$u exists, cannot log in" "id $u && getent passwd $u | grep -q nologin"
  check "$u home is mode 700" "[ \"\$(stat -c %a /home/$u)\" = 700 ]"
  check "$u is not an admin" "! id -nG $u | tr \" \" \"\n\" | grep -qxE \"sudo|admin|wheel|adm\""
done
check "sudoers rules are 0440 root" "[ \"\$(stat -c %a:%U /etc/sudoers.d/apx-ci)\" = 440:root ] && [ \"\$(stat -c %a:%U /etc/sudoers.d/apx-agent)\" = 440:root ]"
check "sudoers rules are valid" "visudo -c"
check "venv, release, current link and updater copy exist" "[ -x /srv/apx/venv/bin/python ] && [ -L /srv/apx/current ] && [ -d /srv/apx/updater/.git ] && ls /srv/apx/releases | grep -qE \"^[0-9a-f]{40}$\""
check "the shared tree is owned by apx" "[ \"\$(stat -c %U /srv/apx/current/src)\" = apx ]"
check "the generated rules pass nft -c" "nft -c -f /etc/apx/apx.nft"
check "the rules name the real uids" "grep -q \"skuid $(id -u apx-ci) jump lane_ci\" /etc/apx/apx.nft && grep -q \"skuid $(id -u apx-agent) jump lane_exec\" /etc/apx/apx.nft"
check "the resolver config has no default upstream" "grep -qx no-resolv /etc/apx/dnsmasq.conf"

echo "--- the split, with a stand-in secret"
install -d -m 700 -o apx -g apx /home/apx/.apx
printf "not-a-real-key" > /home/apx/.apx/app.pem; chown apx:apx /home/apx/.apx/app.pem; chmod 600 /home/apx/.apx/app.pem
for u in apx-ci apx-agent; do
  check "$u cannot read apx secret" "! setpriv --reuid=\$(id -u $u) --regid=\$(id -g $u) --init-groups cat /home/apx/.apx/app.pem"
  check "$u cannot list apx home" "! setpriv --reuid=\$(id -u $u) --regid=\$(id -g $u) --init-groups ls /home/apx"
  check "$u cannot become apx" "! setpriv --reuid=\$(id -u $u) --regid=\$(id -g $u) --init-groups sudo -n -u apx id"
done
check "apx-ci cannot sudo to apx-agent" "! setpriv --reuid=\$(id -u apx-ci) --regid=\$(id -g apx-ci) --init-groups sudo -n -u apx-agent id"
check "apx can act as apx-ci" "setpriv --reuid=\$(id -u apx) --regid=\$(id -g apx) --init-groups sudo -n -u apx-ci id -un | grep -qx apx-ci"
check "apx cannot act as the owner or root" "! setpriv --reuid=\$(id -u apx) --regid=\$(id -g apx) --init-groups sudo -n -u owner id && ! setpriv --reuid=\$(id -u apx) --regid=\$(id -g apx) --init-groups sudo -n id"

echo "--- controls: weaken the split on purpose; the same probes must now see the leak (so a pass above means something)"
chmod 755 /home/apx /home/apx/.apx; chmod 644 /home/apx/.apx/app.pem
check "CONTROL: with apx home opened up, apx-ci CAN read the secret" "setpriv --reuid=\$(id -u apx-ci) --regid=\$(id -g apx-ci) --init-groups cat /home/apx/.apx/app.pem"
chmod 700 /home/apx /home/apx/.apx; chmod 600 /home/apx/.apx/app.pem
check "CONTROL: restored, apx-ci cannot read it again" "! setpriv --reuid=\$(id -u apx-ci) --regid=\$(id -g apx-ci) --init-groups cat /home/apx/.apx/app.pem"
echo "apx-ci ALL=(apx) NOPASSWD: ALL" > /etc/sudoers.d/zz-control; chmod 440 /etc/sudoers.d/zz-control
check "CONTROL: with a sudo rule added, apx-ci CAN become apx" "setpriv --reuid=\$(id -u apx-ci) --regid=\$(id -g apx-ci) --init-groups sudo -n -u apx id"
rm -f /etc/sudoers.d/zz-control
check "CONTROL: rule removed, apx-ci cannot become apx again" "! setpriv --reuid=\$(id -u apx-ci) --regid=\$(id -g apx-ci) --init-groups sudo -n -u apx id"

echo "--- the units"
cp /work/deploy/linux/systemd/* /etc/systemd/system/ 2>/dev/null
v="$(systemd-analyze verify /etc/systemd/system/apx-nft.service /etc/systemd/system/apx-dns.service /etc/systemd/system/apx.service /etc/systemd/system/apx.timer /etc/systemd/system/apx-updater.service /etc/systemd/system/apx-updater.timer 2>&1)"
PROBLEM="unknown (key|section|lvalue)|bad (setting|unit)|invalid|failed to parse|not a valid|unknown key"
printf "[Service]\nBogusKey=1\nExecStart=/bin/true\n" > /tmp/bad.service
if systemd-analyze verify /tmp/bad.service 2>&1 | grep -iE "$PROBLEM" >/dev/null; then pass "CONTROL: systemd-analyze flags a broken unit"; else fail "CONTROL: systemd-analyze did not flag a broken unit, so the check below proves nothing"; fi
if echo "$v" | grep -iE "$PROBLEM"; then fail "systemd-analyze found a problem in our units"; else pass "systemd-analyze verify found no syntax problem in our six units"; fi
echo "verify output (informational):"; echo "$v" | head -12

echo "--- a second run changes nothing"
snap() { { find /srv/apx /etc/apx /etc/sudoers.d /home -path /srv/apx/venv -prune -o -path "*/.git" -prune -o -printf "%p %m %u %g %l\n"; cat /etc/apx/apx.nft /etc/apx/dnsmasq.conf /etc/sudoers.d/apx-ci /etc/sudoers.d/apx-agent; ls /srv/apx/releases; } 2>/dev/null | sort | sha256sum | cut -d" " -f1; }
before="$(snap)"
ADMIN_USER=owner bash $B >/tmp/run2.out 2>&1; rc=$?
[ $rc -eq 0 ] && pass "second run exits 0" || { fail "second run exit $rc"; tail -15 /tmp/run2.out; }
[ "$(snap)" = "$before" ] && pass "second run left the tree, rules and sudoers byte-identical" || fail "second run changed something"
grep -q "unchanged: /etc/apx/apx.nft" /tmp/run2.out && pass "second run says the rules were unchanged" || fail "second run rewrote the rules"

echo "--- the daemon and updater import with the venv bootstrap built, and the doctor runs as apx on a real Linux userland"
APXPY="setpriv --reuid=\$(id -u apx) --regid=\$(id -g apx) --init-groups env HOME=/home/apx PYTHONPATH=/srv/apx/current/src /srv/apx/venv/bin/python"
check "the daemon and the updater import as apx with the bootstrap venv" "$APXPY -c \"import autopilot.apx.daemon, autopilot.apx.update_main, autopilot.apx.status\""
cat > /home/apx/.apx/apx.env <<EOF2
APX_APP_ID=1
APX_KEY_PATH=/home/apx/.apx/app.pem
APX_INSTALLATIONS=RyanJHamby/autopilot=1
APX_KIT_REPO=RyanJHamby/autopilot-kit
APX_KIT_REF=0000000000000000000000000000000000000000
APX_CI_USER=apx-ci
APX_AGENT_USER=apx-agent
EOF2
chown apx:apx /home/apx/.apx/apx.env; chmod 600 /home/apx/.apx/apx.env
setpriv --reuid=$(id -u apx) --regid=$(id -g apx) --init-groups sh -c "cd /srv/apx/current && set -a && . /home/apx/.apx/apx.env && set +a && env HOME=/home/apx PYTHONPATH=/srv/apx/current/src /srv/apx/venv/bin/python -m autopilot.apx.daemon --doctor" >/tmp/doctor.out 2>&1; drc=$?
grep -q Traceback /tmp/doctor.out && fail "the doctor crashed" || pass "the doctor ran without a traceback (exit $drc; a fake key and no token mean some checks fail here, by design)"
grep -iE "admin|home|sandbox" /tmp/doctor.out | head -12

echo "--- the other scripts run"
bash /work/deploy/linux/preflight.sh >/tmp/pre.out 2>&1; prc=$?
{ [ $prc -le 1 ] && grep -q "^PASS  python" /tmp/pre.out; } && pass "preflight runs read-only and reports (exit $prc; FAILs are expected here: no systemd in a container)" || fail "preflight crashed (exit $prc)"
DO=0 bash /work/deploy/linux/retire.sh >/tmp/ret.out 2>&1; rrc=$?
{ [ $rrc -eq 0 ] && grep -q "Preview only" /tmp/ret.out; } && pass "retire previews and changes nothing by default" || fail "retire preview broke (exit $rrc)"

echo "--- the egress probe, against the real internet from inside the container"
nft -f /etc/apx/apx.nft && pass "the installed rules load" || fail "the installed rules did not load"
chmod 644 /etc/apx/dnsmasq.conf
setpriv --reuid=$(id -u apx-dns) --regid=$(id -g apx-dns) --clear-groups --inh-caps=+net_admin --ambient-caps=+net_admin --bounding-set=-all,+net_admin \
  dnsmasq --keep-in-foreground --conf-file=/etc/apx/dnsmasq.conf --pid-file= >/tmp/dnsmasq.out 2>&1 &
sleep 1
check "CONTROL: an unrestricted account can reach a public address on 443 (so the probe refusing it means something)" "setpriv --reuid=\$(id -u nobody) --regid=\$(id -g nobody) --clear-groups nc -z -w 4 1.1.1.1 443"
bash /work/deploy/linux/egress-probe.sh >/tmp/probe.out 2>&1; erc=$?
grep -E "^(LEAK|BROKEN|sealed|[0-9]+ problem)" /tmp/probe.out
[ $erc -eq 0 ] && pass "the probe found no leak and the allowed path worked, for all three accounts" || fail "the probe reported problems (exit $erc)"
[ "$(grep -c "^ok" /tmp/probe.out)" -ge 45 ] && pass "the probe ran its full set of attempts ($(grep -c "^ok" /tmp/probe.out) ok)" || fail "the probe ran too few attempts"

echo "--- control: punch a hole in the apx-ci lane; the probe must now report leaks for apx-ci, and only for it"
nft insert rule inet apx lane_ci accept
bash /work/deploy/linux/egress-probe.sh >/tmp/probe2.out 2>&1; erc2=$?
[ $erc2 -ne 0 ] && pass "CONTROL: the probe exits non-zero when a lane leaks" || fail "CONTROL: the probe missed an open lane"
grep -q "^LEAK    apx-ci: an arbitrary public host on 443" /tmp/probe2.out && pass "CONTROL: it names the leak (apx-ci, arbitrary public host)" || fail "CONTROL: leak not named"
grep -q "^LEAK    apx-agent" /tmp/probe2.out && fail "CONTROL: it blamed apx-agent for apx-ci hole" || pass "CONTROL: the other lanes are still reported sealed"

echo
echo "failed: $fails"
[ "$fails" = 0 ]
'
