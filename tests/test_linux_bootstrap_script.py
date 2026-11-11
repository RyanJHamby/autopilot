"""Static pins for the Linux host kit (deploy/linux). The behaviour itself is checked on a real Linux userland by scripts/linux-bootstrap-test.sh;
these keep a later edit from quietly removing a safety property, and keep the units and the Python defaults saying the same thing."""

import configparser
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "deploy" / "linux"
BOOTSTRAP = LINUX / "bootstrap.sh"
RUNNER = ROOT / "scripts" / "linux-bootstrap-test.sh"
UNITS = sorted((LINUX / "systemd").glob("apx*"))


def code(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))


def unit(name: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None, delimiters=("=",))
    cp.optionxform = str  # type: ignore[assignment]
    cp.read_string((LINUX / "systemd" / name).read_text())
    return cp


# --- scripts -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("script", [BOOTSTRAP, RUNNER], ids=["bootstrap", "runner"])
def test_valid_bash_and_executable(script):
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    assert script.stat().st_mode & 0o111


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
@pytest.mark.parametrize("script", [BOOTSTRAP, RUNNER], ids=["bootstrap", "runner"])
def test_shellcheck_is_clean(script):
    r = subprocess.run(["shellcheck", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_bootstrap_supports_a_dry_run_and_needs_root_only_for_the_real_run():
    c = code(BOOTSTRAP)
    assert 'DRY_RUN="${DRY_RUN:-0}"' in c and 'if [ "$DRY_RUN" != 1 ] && [ "$(id -u)" != 0 ]' in c


def test_the_ssh_lockout_guard_runs_before_anything_is_changed():
    c = code(BOOTSTRAP)
    guard = c.index("you could lock yourself out")
    assert guard < c.index("apt-get update") < c.index("useradd") < c.index("sshd_config.d")


def test_ssh_is_key_only_root_less_and_limited_to_the_admin():
    c = code(BOOTSTRAP)
    for line in ("PermitRootLogin no", "PasswordAuthentication no", "KbdInteractiveAuthentication no", "AllowUsers $ADMIN_USER"):
        assert line in c, line
    assert c.index("sshd -t") < c.index("systemctl reload ssh"), "the config is checked before sshd is told to use it"


def test_sudoers_rules_are_syntax_checked_before_install_and_grant_only_the_two_accounts():
    c = code(BOOTSTRAP)
    assert c.index("visudo -cf") < c.index('install -m 440 -o root -g root "$tmp" "$f"')
    assert 'line="apx ALL=($target) NOPASSWD:SETENV: ALL"' in c and "for target in apx-ci apx-agent" in c
    assert "NOPASSWD: ALL" not in c.replace("NOPASSWD:SETENV: ALL", "")


def test_the_sandbox_accounts_are_never_admins_and_cannot_log_in():
    c = code(BOOTSTRAP)
    assert "--shell /usr/sbin/nologin" in c and "--create-home" in c
    assert re.search(r"grep -qxE 'sudo\|admin\|wheel\|adm\|docker'", c)
    assert 'chmod 700 "/home/$u"' in c


def test_the_shared_tree_is_not_writable_by_the_sandbox():
    c = code(BOOTSTRAP)
    assert 'install -d -m 755 -o apx -g apx "$SHARED"' in c and "chmod -R go+rX" in c
    assert "go+w" not in c and "777" not in c and "a+w" not in c


def test_bootstrap_installs_no_secret_and_no_unpinned_toolchain_and_never_pipes_a_download_to_a_shell():
    c = code(BOOTSTRAP)
    for word in ("app.pem", "claude-oauth", "setup-token", "ANTHROPIC", "GITHUB_TOKEN"):
        assert word not in c, word
    assert not re.search(r"curl[^\n]*\|\s*(ba)?sh", c) and not re.search(r"wget[^\n]*\|\s*(ba)?sh", c)
    assert "nodesource" not in c.lower() and "astral.sh" not in c


def test_the_resolver_package_is_dnsmasq_base_so_no_stray_resolver_runs_on_port_53():
    block = code(BOOTSTRAP).split("apt-get install", 1)[1].split("put root:root", 1)[0]
    packages = set(
        re.findall(r"[a-z0-9][a-z0-9+.-]+", " ".join(ln for ln in block.splitlines() if not ln.strip().startswith("-")))
    )
    assert "dnsmasq-base" in packages and "dnsmasq" not in packages


def test_timers_are_installed_but_not_enabled_so_the_owner_decides_when_apx_goes_live():
    c = code(BOOTSTRAP)
    commands = [ln.strip() for ln in c.splitlines() if re.match(r"\s*(run\s+)?systemctl\b", ln)]
    assert commands and not any(".timer" in ln and "enable" in ln for ln in commands), commands
    assert "enable --now apx-nft.service" in c


def test_no_macos_paths_leak_into_the_linux_kit():
    for p in [BOOTSTRAP, *UNITS]:
        assert "/Users/" not in p.read_text(), p.name


def test_the_test_runner_adds_only_net_admin_mounts_read_only_and_cleans_up():
    c = code(RUNNER)
    assert re.findall(r"--cap-add\s+(\S+)", c) == ["NET_ADMIN"]
    assert 'git -C "$here" archive HEAD' in c and re.search(r'-v "\$tmp:/src:ro"', c)
    assert "--rm" in c and re.search(r"trap 'rm -rf \"\$tmp\"' EXIT", c)
    for danger in ("--privileged", "$HOME", "/Users/", "--network host", "--pid host", "docker.sock"):
        assert danger not in c, danger


# --- units -------------------------------------------------------------------------------------------------------------------------


def test_every_unit_the_bootstrap_installs_exists_and_nothing_else_is_installed():
    named = set(re.findall(r"apx[a-z-]*\.(?:service|timer)", re.search(r"for unit in ([^;]+);", code(BOOTSTRAP)).group(1)))
    assert named == {p.name for p in UNITS}


def test_the_units_use_the_same_directories_as_the_python_defaults():
    from autopilot.apx import hostenv

    shared = "/srv/apx"
    assert hostenv.default_shared_dir() == shared or hostenv.is_darwin()
    for name in ("apx.service", "apx-updater.service"):
        text = (LINUX / "systemd" / name).read_text()
        assert shared in text and "/home/apx/.apx/apx.env" in text
    assert re.search(r"^SHARED=/srv/apx$", code(BOOTSTRAP), re.M)


def test_apx_cannot_start_unless_the_egress_rules_and_resolver_are_up():
    for name in ("apx.service", "apx-updater.service"):
        u = unit(name)["Unit"]
        assert {"apx-nft.service", "apx-dns.service"} <= set(u["Requires"].split()), name
        assert {"apx-nft.service", "apx-dns.service"} <= set(u["After"].split()), name
    assert "apx-nft.service" in unit("apx-dns.service")["Unit"]["Requires"]


def test_the_executor_runs_as_apx_and_keeps_setuid_sudo_working():
    for name in ("apx.service", "apx-updater.service"):
        s = unit(name)["Service"]
        assert s["User"] == "apx" and s["Type"] == "oneshot"
        assert "NoNewPrivileges" not in s, "sudo is setuid and is how untrusted steps drop to the sandbox accounts"
        assert s["PrivateTmp"] == "yes" and s["ProtectSystem"] == "full"
    s = unit("apx.service")["Service"]
    assert "--once --live" in s["ExecStart"] and "APX_LIVE=1" in s["ExecStart"]
    assert s["MemoryMax"] and s["TasksMax"], "limits on the unit also cover the sandboxed children"


def test_the_resolver_has_no_privilege_but_net_admin_and_is_not_root():
    s = unit("apx-dns.service")["Service"]
    assert s["User"] == "apx-dns"
    assert s["AmbientCapabilities"] == "CAP_NET_ADMIN" and s["CapabilityBoundingSet"] == "CAP_NET_ADMIN"
    assert s["NoNewPrivileges"] == "yes" and "--user" not in s["ExecStart"]
    assert "--conf-file=/etc/apx/dnsmasq.conf" in s["ExecStart"]


def test_the_rules_are_checked_before_they_are_loaded_and_removed_on_stop():
    s = unit("apx-nft.service")["Service"]
    assert s["ExecStartPre"].startswith("/usr/sbin/nft -c -f /etc/apx/apx.nft")
    assert s["ExecStart"] == "/usr/sbin/nft -f /etc/apx/apx.nft" and s["ExecStop"] == "/usr/sbin/nft delete table inet apx"


@pytest.mark.parametrize("timer", ["apx.timer", "apx-updater.timer"])
def test_timers_start_nothing_until_enabled_and_say_how_to_stop(timer):
    t = (LINUX / "systemd" / timer).read_text()
    assert "NOT enabled" in t and "disable --now" in t or "Stop" in t
    assert unit(timer)["Timer"]["OnUnitInactiveSec"] == "2min"
