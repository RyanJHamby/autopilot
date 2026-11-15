"""The doctor checks, as the agent account and through the same launcher as the other agent checks, that Claude Code's sandbox can
start. Incident (2026-11-15): the first agent runs on the Linux host failed with `claude exited 1: Claude Code could not start:
bubblewrap is required for subprocess env scrubbing and isolation`, while every doctor check had passed. On Ubuntu 24.04 bwrap can also
be present and still be blocked by AppArmor's unprivileged-userns restriction."""

import json
import subprocess

import pytest
from test_apx_doctor import AgentStub, run_agent_doctor, settings

from autopilot.apx import doctor as dr
from autopilot.apx import hostenv, sandbox

NAME = "agent account can start Claude Code's sandbox (bubblewrap)"
PROBE_TAIL = ["--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "/bin/true"]


class BwrapAgent(AgentStub):
    """The agent account, with a bubblewrap that is missing, blocked, slow, or fine. Records every call it gets."""

    def __init__(self, found="/usr/bin/bwrap", rc=0, stderr="", hang=False, **kw):
        super().__init__(**kw)
        self.found, self.rc, self.stderr, self.hang, self.calls = found, rc, stderr, hang, []

    def run(self, argv, **kw):
        self.calls.append((argv, kw))
        R = lambda rc, out="", err="": type("R", (), {"returncode": rc, "stdout": out, "stderr": err})()  # noqa: E731
        if argv[:1] == ["/bin/sh"] and argv[-1:] == ["bwrap"]:
            return R(0, self.found + "\n") if self.found else R(1)
        if argv[:1] == ["/bin/sh"] and argv[-2:-1] == ["sh"] and argv[-1].endswith("bwrap"):  # test -x on a configured path
            return R(0 if self.found == argv[-1] else 1)
        if argv[1:] == PROBE_TAIL:
            if self.hang:
                raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
            return R(self.rc, "", self.stderr)
        return super().run(argv, **kw)


@pytest.fixture
def linux(monkeypatch, tmp_path):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    monkeypatch.setattr(dr, "MANAGED_SETTINGS", tmp_path / "no-managed-settings.json")


def agent_settings(tmp_path):
    return settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent")


def test_missing_bwrap_fails_with_the_install_hint(tmp_path, linux):
    c = run_agent_doctor(agent_settings(tmp_path), BwrapAgent(found=""))[NAME]
    assert not c.ok
    assert c.detail == "bubblewrap missing: Claude Code can't start its sandbox (sudo apt-get install -y bubblewrap)"


def test_a_probe_blocked_by_the_userns_restriction_fails_with_the_apparmor_hint(tmp_path, linux):
    err = "bwrap: setting up uid map: Permission denied\nmore detail that is not shown\n"
    c = run_agent_doctor(agent_settings(tmp_path), BwrapAgent(rc=1, stderr=err))[NAME]
    assert not c.ok
    assert c.detail.startswith("/usr/bin/bwrap: bwrap: setting up uid map: Permission denied; ")
    assert "more detail" not in c.detail
    assert "AppArmor userns restriction" in c.detail and "docs/apx-linux-host.md" in c.detail
    assert "don't disable the restriction system-wide" in c.detail


def test_any_other_probe_failure_still_fails_and_says_its_exit_code_when_silent(tmp_path, linux):
    c = run_agent_doctor(agent_settings(tmp_path), BwrapAgent(rc=1, stderr=""))[NAME]
    assert not c.ok and "exit 1" in c.detail


def test_a_hanging_probe_fails_after_ten_seconds_and_never_crashes_the_doctor(tmp_path, linux):
    agent = BwrapAgent(hang=True)
    c = run_agent_doctor(agent_settings(tmp_path), agent)[NAME]
    assert not c.ok and "timed out after 10s" in c.detail


def test_a_working_sandbox_passes_and_was_probed_as_the_agent_on_its_job_path(tmp_path, linux):
    s = agent_settings(tmp_path)
    agent = BwrapAgent()
    c = run_agent_doctor(s, agent)[NAME]
    assert c.ok and c.detail == "/usr/bin/bwrap"
    lookup = [kw for argv, kw in agent.calls if argv[:1] == ["/bin/sh"] and argv[-1:] == ["bwrap"]]
    probe = [(argv, kw) for argv, kw in agent.calls if argv[1:] == PROBE_TAIL]
    assert lookup and lookup[0]["env"]["PATH"] == sandbox.job_path(s.agent_home())  # the PATH the agent's claude runs with
    assert probe and probe[0][0][0] == "/usr/bin/bwrap" and probe[0][1]["timeout"] == 10


def test_a_bwrap_path_in_claude_codes_managed_settings_is_the_one_probed(tmp_path, linux, monkeypatch):
    managed = tmp_path / "managed-settings.json"
    managed.write_text(json.dumps({"sandbox": {"bwrapPath": "/opt/tools/bwrap"}}))
    monkeypatch.setattr(dr, "MANAGED_SETTINGS", managed)
    agent = BwrapAgent(found="/opt/tools/bwrap")
    c = run_agent_doctor(agent_settings(tmp_path), agent)[NAME]
    assert c.ok and c.detail == "/opt/tools/bwrap (sandbox.bwrapPath)"
    assert any(argv[0] == "/opt/tools/bwrap" and argv[1:] == PROBE_TAIL for argv, _ in agent.calls)
    missing = run_agent_doctor(agent_settings(tmp_path), BwrapAgent(found="/usr/bin/bwrap"))[NAME]
    assert not missing.ok and "/opt/tools/bwrap" in missing.detail and "bubblewrap missing" in missing.detail


def test_on_macos_there_is_no_bubblewrap_check(tmp_path, monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)
    agent = BwrapAgent(found="")
    out = run_agent_doctor(agent_settings(tmp_path), agent)
    assert NAME not in out
    assert not any("bwrap" in " ".join(argv) for argv, _ in agent.calls)


def test_without_an_agent_account_there_is_no_bubblewrap_check(tmp_path, linux):
    out = run_agent_doctor(settings(tmp_path, ci_user="apx-ci"))
    assert NAME not in out
