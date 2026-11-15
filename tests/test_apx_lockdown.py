"""Emergency egress lockdown for the apx accounts on the Linux host: one command cuts all their outbound traffic, one command undoes it.

The rendered table always carries a `lockdown` uid set and a drop for it as the first rule of the output hook, and always includes the
root-owned lockdown directory, so a reload (`nft -f`) re-applies an active lockdown in the same transaction. The helper only adds to or
flushes that set and writes or removes the flag file; it never deletes, flushes or reloads the table. Where this container allows it
(root, nft, unshare), the rules are also loaded into a throwaway network namespace and the lockdown is checked against the kernel."""

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from autopilot.apx import nftrules

ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "deploy" / "linux"
HELPER = LINUX / "lockdown.sh"
PROBE = LINUX / "egress-probe.sh"
UNIT = LINUX / "systemd" / "apx-nft.service"
UIDS = {"apx": 1001, "apx-ci": 1002, "apx-agent": 1003}
SHELLCHECK_09 = Path("/tmp/sc09/x/usr/bin/shellcheck")
DROP = "meta skuid @lockdown counter drop"


def code(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))


def output_rules(text: str) -> list[str]:
    body = re.search(r"chain output \{(.*?)\n  \}", text, re.S).group(1)
    return [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("type ")]


# --- the rendered rules -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("port", [5354, 5399])
def test_the_lockdown_drop_is_the_first_output_rule_so_it_comes_before_every_lane_and_every_accept(port):
    text = nftrules.render_nft(UIDS, dns_port=port)
    r = output_rules(text)
    assert r[0] == DROP, r
    assert all(f"meta skuid {u} jump" in " ".join(r[1:]) for u in UIDS.values()), "every account still goes to its lane after the drop"
    assert re.search(r"set lockdown \{\s+typeof meta skuid\s+\}", text), "an empty uid set by default: lockdown off"


def test_the_lockdown_set_is_never_rendered_with_members_so_a_plain_reload_only_locks_via_the_flag():
    assert "elements" not in nftrules.render_nft(UIDS)


def test_the_lockdown_directory_is_always_included_after_the_table_so_a_reload_reapplies_an_active_lockdown():
    text = nftrules.render_nft(UIDS)
    assert text.rstrip().splitlines()[-1] == 'include "/etc/apx-lockdown/*.nft"'
    assert text.index("table inet apx {") < text.index("include ")
    custom = nftrules.render_nft(UIDS, lockdown_dir="/tmp/x-lock")
    assert custom.rstrip().splitlines()[-1] == 'include "/tmp/x-lock/*.nft"'


def test_the_default_lockdown_directory_is_outside_etc_apx_which_the_apx_account_owns():
    assert nftrules.LOCKDOWN_DIR == "/etc/apx-lockdown"
    assert not nftrules.LOCKDOWN_DIR.startswith("/etc/apx/")


@pytest.mark.parametrize("bad", ["relative/dir", '/etc/a"b', "/etc/a b", "/etc/a\nb", "/etc/../tmp", "/", "/etc/x/", ""])
def test_a_lockdown_directory_that_could_break_the_include_is_refused(bad):
    with pytest.raises(ValueError):
        nftrules.render_nft(UIDS, lockdown_dir=bad)


def test_the_cli_passes_the_lockdown_directory_through():
    args = ["nft", "--uid", "apx=1001", "--uid", "apx-ci=1002", "--uid", "apx-agent=1003", "--lockdown-dir", "/tmp/x-lock"]
    r = subprocess.run([sys.executable, "-m", "autopilot.apx.nftrules", *args], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == nftrules.render_nft(UIDS, lockdown_dir="/tmp/x-lock")


# --- the helper -----------------------------------------------------------------------------------------------------------------------


def test_the_helper_is_valid_bash_and_executable():
    assert subprocess.run(["bash", "-n", str(HELPER)], capture_output=True).returncode == 0
    assert HELPER.stat().st_mode & 0o111


@pytest.mark.parametrize("script", [HELPER, PROBE], ids=["helper", "probe"])
@pytest.mark.parametrize("binary", ["shellcheck", str(SHELLCHECK_09)], ids=["current", "0.9"])
def test_shellcheck_is_clean(script, binary):
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} is not installed")
    r = subprocess.run([binary, str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_the_helper_only_touches_the_lockdown_set_and_never_the_table_or_the_ruleset():
    c = re.sub(r'\b(say|die) "[^"]*"', "", code(HELPER))  # messages may name commands for the human; only what runs is checked
    for forbidden in ("delete table", "flush ruleset", "flush table", "flush chain", "nft -f", "systemctl", "delete rule", "add rule"):
        assert forbidden not in c, forbidden
    calls = re.findall(r"(?<![\w./-])nft\b[^\n|;&)]*", c)
    assert calls
    allowed = ("nft add element inet apx lockdown", "nft flush set inet apx lockdown", "nft list set inet apx lockdown")
    for call in calls:
        if call.strip() == "nft" or call.startswith("nft >/dev/null"):  # `command -v nft`
            continue
        assert call.startswith(allowed), call


def test_the_helper_needs_root_refuses_root_and_the_admin_and_writes_the_flag_before_the_live_change():
    c = code(HELPER)
    assert '"$(id -u)" != 0' in c
    assert "SUDO_USER" in c and '"$uid" = 0' in c, "never put root or the admin who ran it in the set"
    on = c[c.index("cmd_on()") :]
    assert on.index("mv -f") < on.index("nft add element"), "flag first: if the live change fails, the next reload still locks"
    assert "chmod 700" in c or "install -d -m 700" in c


@pytest.mark.skipif(os.geteuid() == 0, reason="checks the non-root refusal")
def test_the_helper_refuses_to_run_without_root(tmp_path):
    env = {**os.environ, "APX_LOCKDOWN_DIR": str(tmp_path / "d")}
    r = subprocess.run(["bash", str(HELPER), "on"], capture_output=True, text=True, env=env)
    assert r.returncode != 0 and not (tmp_path / "d").exists()


def test_the_helper_rejects_an_unknown_command(tmp_path):
    r = subprocess.run(["bash", str(HELPER), "maybe"], capture_output=True, text=True)
    assert r.returncode == 2 and "on|off|status" in r.stdout + r.stderr


# --- the unit and the probe ----------------------------------------------------------------------------------------------------------


def test_stopping_the_rules_leaves_the_table_and_locks_the_four_accounts_instead_of_opening_egress():
    stop = [ln for ln in UNIT.read_text().splitlines() if ln.startswith("ExecStop=")]
    assert len(stop) == 1
    s = stop[0]
    assert "delete table" not in s and "flush" not in s
    assert "nft add element inet apx lockdown {" in s
    for acct in ("apx", "apx-ci", "apx-agent", "apx-dns"):
        assert f"$$(id -u {acct})" in s, acct


def test_the_probe_has_a_lockdown_mode_that_expects_every_path_refused_and_root_still_out():
    c = code(PROBE)
    assert "--expect-lockdown" in c
    assert "apx-dns" in c, "the resolver account is locked too, so the probe checks it"
    assert "WHO=root" in c, "control: the admin side still reaches github, so 'all refused' cannot mean 'host offline'"
    assert "lockdown is on" in c, "the normal probe refuses to run against a locked host instead of reporting a wall of BROKEN"


def test_bootstrap_installs_the_helper_root_owned_outside_the_apx_tree():
    c = code(LINUX / "bootstrap.sh")
    assert 'put root:root 755 /usr/local/sbin/apx-lockdown <"$here/lockdown.sh"' in c


def test_the_host_doc_has_an_emergency_lockdown_section_with_on_off_status_and_the_timers():
    doc = (ROOT / "docs" / "apx-linux-host.md").read_text()
    sec = doc[doc.index("## Emergency lockdown") :]
    sec = sec[: sec.index("\n## ", 5)] if "\n## " in sec[5:] else sec
    for cmd in ("apx-lockdown on", "apx-lockdown off", "apx-lockdown status", "--expect-lockdown", "disable --now apx.timer apx-updater.timer"):
        assert cmd in sec, cmd


# --- against the kernel, in a throwaway network namespace ---------------------------------------------------------------------------

KERNEL = os.geteuid() == 0 and all(shutil.which(b) for b in ("nft", "unshare", "setpriv", "ip"))


def netns(script: str, tmp_path: Path) -> subprocess.CompletedProcess:
    r = subprocess.run(["unshare", "-n", "bash", "-c", script], capture_output=True, text=True, cwd=tmp_path, timeout=60)
    if r.returncode == 99:
        pytest.skip("this container cannot create a network namespace with nftables: " + r.stderr[-300:])
    return r


@pytest.mark.skipif(not KERNEL, reason="needs root, nft, unshare, setpriv and ip")
def test_the_rendered_rules_pass_nft_check_and_load(tmp_path):
    (tmp_path / "apx.nft").write_text(nftrules.render_nft(UIDS, lockdown_dir=str(tmp_path / "lock")))
    r = netns("nft list tables >/dev/null 2>&1 || exit 99; nft -c -f apx.nft && nft -f apx.nft && nft list set inet apx lockdown", tmp_path)
    assert r.returncode == 0, r.stderr
    assert "elements" not in r.stdout


@pytest.mark.skipif(not KERNEL, reason="needs root, nft, unshare, setpriv and ip")
def test_lockdown_on_survives_a_reload_blocks_the_account_spares_root_and_off_restores_it(tmp_path):
    lock = tmp_path / "lock"
    (tmp_path / "apx.nft").write_text(nftrules.render_nft(UIDS, lockdown_dir=str(lock)))
    script = textwrap.dedent(
        f"""
        set -u
        nft list tables >/dev/null 2>&1 || exit 99
        ip link set lo up
        export APX_LOCKDOWN_DIR={lock} APX_LOCKDOWN_ACCOUNTS="nobody daemon" APX_NFT_FILE={tmp_path}/apx.nft
        nft -f apx.nft
        python3 -c 'import socket,threading
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1", 18080)); s.listen(8)
while True: s.accept()[0].close()' &
        sleep 0.5
        conn() {{ python3 -c 'import socket; socket.create_connection(("127.0.0.1", 18080), timeout=2)' 2>/dev/null; }}
        asnobody() {{ setpriv --reuid=65534 --regid=65534 --clear-groups python3 -c 'import socket; socket.create_connection(("127.0.0.1", 18080), timeout=2)' 2>/dev/null; }}
        asnobody && echo "BEFORE nobody=ok" || echo "BEFORE nobody=blocked"
        bash {HELPER} on; echo "ON rc=$?"
        asnobody && echo "ON nobody=ok" || echo "ON nobody=blocked"
        conn && echo "ON root=ok" || echo "ON root=blocked"
        nft -f apx.nft
        asnobody && echo "RELOAD nobody=ok" || echo "RELOAD nobody=blocked"
        bash {HELPER} status; echo "STATUS rc=$?"
        bash {HELPER} off; echo "OFF rc=$?"
        asnobody && echo "OFF nobody=ok" || echo "OFF nobody=blocked"
        nft -f apx.nft
        asnobody && echo "RELOAD2 nobody=ok" || echo "RELOAD2 nobody=blocked"
        bash {HELPER} status; echo "STATUS2 rc=$?"
        nft list table inet apx >/dev/null && echo "TABLE present"
        kill %1
        """
    )
    r = netns(script, tmp_path)
    out = r.stdout
    for want in (
        "BEFORE nobody=ok",
        "ON rc=0",
        "ON nobody=blocked",
        "ON root=ok",
        "RELOAD nobody=blocked",
        "STATUS rc=0",
        "OFF rc=0",
        "OFF nobody=ok",
        "RELOAD2 nobody=ok",
        "STATUS2 rc=0",
        "TABLE present",
    ):
        assert want in out, f"{want}\n--- stdout\n{out}\n--- stderr\n{r.stderr}"
    assert "lockdown: on" in out and "lockdown: off" in out
    assert not list(lock.glob("*.nft")) if lock.exists() else True


@pytest.mark.skipif(not KERNEL, reason="needs root, nft, unshare, setpriv and ip")
def test_the_helper_refuses_root_and_writes_nothing(tmp_path):
    lock = tmp_path / "lock"
    (tmp_path / "apx.nft").write_text(nftrules.render_nft(UIDS, lockdown_dir=str(lock)))
    script = f"""nft list tables >/dev/null 2>&1 || exit 99
nft -f apx.nft
APX_LOCKDOWN_DIR={lock} APX_LOCKDOWN_ACCOUNTS="nobody root" bash {HELPER} on; echo "rc=$?"
nft list set inet apx lockdown"""
    r = netns(script, tmp_path)
    assert "rc=0" not in r.stdout and "elements" not in r.stdout, r.stdout + r.stderr
    assert not lock.exists() or not list(lock.glob("*.nft"))


@pytest.mark.skipif(not KERNEL, reason="needs root, nft, unshare, setpriv and ip")
def test_the_units_stop_command_locks_the_four_accounts_and_keeps_the_table(tmp_path):
    (tmp_path / "apx.nft").write_text(nftrules.render_nft(UIDS, lockdown_dir=str(tmp_path / "lock")))
    stop = next(ln for ln in UNIT.read_text().splitlines() if ln.startswith("ExecStop="))[len("ExecStop=") :]
    m = re.fullmatch(r"/bin/sh -c '(.*)'", stop)
    assert m, stop
    body = m.group(1).replace("$$", "$")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "id").write_text('#!/bin/sh\ncase "$2" in apx) echo 1001;; apx-ci) echo 1002;; apx-agent) echo 1003;; apx-dns) echo 1004;; esac\n')
    (fake / "id").chmod(0o755)
    script = f"""nft list tables >/dev/null 2>&1 || exit 99
nft -f apx.nft
PATH={fake}:$PATH /bin/sh -c '{body}'; echo "rc=$?"
nft list set inet apx lockdown; nft list chain inet apx lane_ci >/dev/null && echo "LANES kept\""""
    r = netns(script, tmp_path)
    assert "rc=0" in r.stdout and "LANES kept" in r.stdout, r.stdout + r.stderr
    assert re.search(r"elements = \{ 1001, 1002, 1003, 1004 \}", r.stdout), r.stdout
