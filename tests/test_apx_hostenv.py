"""Where apx's accounts live and how it asks the OS about them, on macOS and on Linux.

The Mac is where apx runs today and its behaviour must not move: every Mac default here is the value that was hard-coded before. The Linux
cases are what a rebuilt VPS host needs. Platform is simulated by patching `hostenv.is_darwin`, so this runs the same anywhere, which matters
because apx's own CI lane will run this suite on the Linux host."""

import types

import pytest
from test_apx_daemon import REPO, _agent_settings, _IssueApi, env

from autopilot.apx import daemon as dm
from autopilot.apx import doctor as dr
from autopilot.apx import hostenv, status


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)
    monkeypatch.setattr(hostenv.pwd, "getpwnam", _missing)


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    monkeypatch.setattr(hostenv.pwd, "getpwnam", _missing)


def _missing(name):
    raise KeyError(name)


# --- home_of ----------------------------------------------------------------------------------------------------------------------


def test_a_known_account_gets_the_home_the_operating_system_says(monkeypatch):
    monkeypatch.setattr(hostenv.pwd, "getpwnam", lambda n: types.SimpleNamespace(pw_dir=f"/var/lib/{n}"))
    assert hostenv.home_of("apx-ci") == "/var/lib/apx-ci"


def test_an_account_that_does_not_exist_yet_gets_its_conventional_home(mac, monkeypatch):
    assert hostenv.home_of("apx-ci") == "/Users/apx-ci"
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    assert hostenv.home_of("apx-ci") == "/home/apx-ci"


def test_the_shared_directory_default_follows_the_platform(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)
    assert hostenv.default_shared_dir() == "/Users/Shared/apx"
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    assert hostenv.default_shared_dir() == "/srv/apx"


# --- Settings ---------------------------------------------------------------------------------------------------------------------


def test_on_macos_every_default_is_exactly_what_it_was_before(mac, tmp_path):
    s = dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci", APX_AGENT_USER="apx-agent", APX_OAUTH_FILE=""))
    assert s.ci_work == "/Users/apx-ci/work"
    assert s.shared_dir == "/Users/Shared/apx"
    assert s.oauth_file == "/Users/apx-agent/.apx/claude-oauth"
    assert (s.ci_home(), s.agent_home()) == ("/Users/apx-ci", "/Users/apx-agent")
    assert s.agent_work_root() == "/Users/apx-agent/work" and s.agent_bin() == "/Users/apx-agent/.local/bin/claude"


def test_on_linux_the_same_settings_land_in_linux_places(linux, tmp_path):
    s = dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci", APX_AGENT_USER="apx-agent", APX_OAUTH_FILE=""))
    assert s.ci_work == "/home/apx-ci/work"
    assert s.shared_dir == "/srv/apx"
    assert s.oauth_file == "/home/apx-agent/.apx/claude-oauth"
    assert s.agent_work_root() == "/home/apx-agent/work" and s.agent_bin() == "/home/apx-agent/.local/bin/claude"


def test_a_real_account_home_beats_the_convention(linux, monkeypatch, tmp_path):
    monkeypatch.setattr(hostenv.pwd, "getpwnam", lambda n: types.SimpleNamespace(pw_dir=f"/var/lib/{n}"))
    s = dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci", APX_AGENT_USER="apx-agent", APX_OAUTH_FILE=""))
    assert (s.ci_work, s.oauth_file) == ("/var/lib/apx-ci/work", "/var/lib/apx-agent/.apx/claude-oauth")


@pytest.mark.parametrize("fixture", ["mac", "linux"])
def test_an_explicit_setting_always_wins_on_either_platform(fixture, request, tmp_path):
    request.getfixturevalue(fixture)
    s = dm.Settings.from_env(
        env(
            tmp_path,
            APX_CI_USER="apx-ci",
            APX_AGENT_USER="apx-agent",
            APX_CI_WORK="/data/ci",
            APX_SHARED="/opt/apx",
            APX_AGENT_WORK="/data/agent",
            APX_AGENT_BINARY="/opt/claude",
            APX_OAUTH_FILE="/etc/apx/oauth",
        )
    )
    assert (s.ci_work, s.shared_dir, s.oauth_file) == ("/data/ci", "/opt/apx", "/etc/apx/oauth")
    assert (s.agent_work_root(), s.agent_bin()) == ("/data/agent", "/opt/claude")


def test_the_agent_request_carries_the_platforms_paths(linux, tmp_path):
    from autopilot.apx.committer import FileChange

    s = _agent_settings(tmp_path)
    seen = {}

    def run_agent(req, token):
        seen["req"] = req
        return {"ok": True, "summary": "did it", "turns": 1}, [FileChange("f.py", "100644", b"x = 1\n")]

    dm.work_on_issue(
        s, _IssueApi(), lambda repo: "WRITE", REPO, 4, 77, "model=sonnet effort=low turns=12",
        read_token_for=lambda repo: "READ", run_agent=run_agent,
    )
    assert seen["req"]["work_root"] == "/home/apx-agent/work" and seen["req"]["binary"] == "/home/apx-agent/.local/bin/claude"


# --- the admin check ----------------------------------------------------------------------------------------------------------------


def test_the_admin_check_asks_the_tool_each_os_actually_has(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)
    assert hostenv.admin_check_argv("apx-ci") == ["/usr/sbin/dseditgroup", "-o", "checkmember", "-m", "apx-ci", "admin"]
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    assert hostenv.admin_check_argv("apx-ci") == ["/usr/bin/id", "-nG", "apx-ci"]


def result(out="", err="", rc=0):
    return types.SimpleNamespace(stdout=out, stderr=err, returncode=rc)


@pytest.mark.parametrize(
    "out,expect_admin",
    [("yes apx-ci is a member of admin", True), ("no apx-ci is NOT a member of admin", False), ("", False)],
)
def test_the_macos_answer_is_read_as_before(mac, out, expect_admin):
    assert hostenv.is_admin(result(out), "apx-ci") is expect_admin


@pytest.mark.parametrize(
    "groups,expect_admin",
    [("apx-ci", False), ("apx-ci users", False), ("apx-ci sudo", True), ("apx-ci admin", True), ("wheel apx-ci", True), ("", False)],
)
def test_on_linux_membership_of_sudo_admin_or_wheel_makes_an_account_an_admin(linux, groups, expect_admin):
    assert hostenv.is_admin(result(groups + "\n"), "apx-ci") is expect_admin


def test_a_group_that_merely_contains_the_word_is_not_an_admin_group(linux):
    assert hostenv.is_admin(result("apx-ci sudoers-readers\n"), "apx-ci") is False


# --- the doctor uses it ------------------------------------------------------------------------------------------------------------


class LinuxStub:
    """The sandbox account as a Linux host sees it: `id -un` answers the name, `id -nG` its groups."""

    def __init__(self, groups="apx-ci"):
        self.groups = groups

    def run(self, argv, **kw):
        R = lambda rc, out="": types.SimpleNamespace(returncode=rc, stdout=out, stderr="")  # noqa: E731
        if argv[:2] == ["/usr/bin/id", "-un"]:
            return R(0, "apx-ci\n")
        if argv[:2] == ["/usr/bin/id", "-nG"]:
            return R(0, self.groups + "\n")
        if argv[0] in ("/bin/cat", "/bin/ls"):
            return R(1)
        return R(0)


def _settings(tmp_path):
    from test_apx_doctor import settings

    return settings(tmp_path, ci_user="apx-ci")


def test_the_doctor_passes_a_standard_linux_account_and_fails_one_in_sudo(linux, tmp_path):
    ok = {c.name: c for c in dr.sandbox_checks(_settings(tmp_path), LinuxStub())}
    assert ok["sandbox account is not an admin"].ok
    bad = {c.name: c for c in dr.sandbox_checks(_settings(tmp_path), LinuxStub(groups="apx-ci sudo"))}
    assert not bad["sandbox account is not an admin"].ok


# --- the notifier -------------------------------------------------------------------------------------------------------------------


def test_the_notifier_uses_osascript_on_macos(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)
    calls = []
    monkeypatch.setattr(status.subprocess, "run", lambda argv, **kw: calls.append(argv))
    status.notify("title", "message")
    assert calls and calls[0][0] == "/usr/bin/osascript" and calls[0][-2:] == ["title", "message"]


def test_the_notifier_does_nothing_on_linux_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    monkeypatch.setattr(status.subprocess, "run", lambda *a, **k: pytest.fail("no subprocess may run on Linux"))
    assert status.notify("title", "message") is None
