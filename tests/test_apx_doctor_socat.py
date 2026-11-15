"""Claude Code's Linux sandbox needs socat as well as bubblewrap. Incident (2026-11-15): with bubblewrap installed, the first agent run
that got going (stencil #22) wrote in its PR body: "Bash fails in this environment because the sandbox needs `socat`, which isn't
installed, and running outside the sandbox is blocked." It wrote code without running a test. Claude Code's sandboxing docs list both
packages for Linux (https://code.claude.com/docs/en/sandboxing, "Set up Linux and WSL2")."""

import pytest
from test_apx_doctor import run_agent_doctor, settings
from test_apx_doctor_bwrap import BwrapAgent

from autopilot.apx import doctor as dr
from autopilot.apx import hostenv, sandbox

NAME = "agent account has socat for Claude Code's sandbox"


class SocatAgent(BwrapAgent):
    """The agent account with a working bubblewrap and a socat that is there or not."""

    def __init__(self, socat="/usr/bin/socat", **kw):
        super().__init__(**kw)
        self.socat = socat

    def run(self, argv, **kw):
        if argv[:1] == ["/bin/sh"] and argv[-1:] == ["socat"]:
            self.calls.append((argv, kw))
            R = lambda rc, out="": type("R", (), {"returncode": rc, "stdout": out, "stderr": ""})()  # noqa: E731
            return R(0, self.socat + "\n") if self.socat else R(1)
        return super().run(argv, **kw)


@pytest.fixture
def linux(monkeypatch, tmp_path):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)
    monkeypatch.setattr(dr, "MANAGED_SETTINGS", tmp_path / "no-managed-settings.json")


def agent_settings(tmp_path):
    return settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent")


def test_missing_socat_fails_with_the_install_hint(tmp_path, linux):
    c = run_agent_doctor(agent_settings(tmp_path), SocatAgent(socat=""))[NAME]
    assert not c.ok
    assert c.detail == "socat missing: Claude Code's sandbox can't run shell commands (sudo apt-get install -y socat)"


def test_socat_on_the_agents_job_path_passes(tmp_path, linux):
    s = agent_settings(tmp_path)
    agent = SocatAgent()
    c = run_agent_doctor(s, agent)[NAME]
    assert c.ok and c.detail == "/usr/bin/socat"
    lookup = [kw for argv, kw in agent.calls if argv[:1] == ["/bin/sh"] and argv[-1:] == ["socat"]]
    assert lookup and lookup[0]["env"]["PATH"] == sandbox.job_path(s.agent_home())  # the PATH the agent's claude runs with


def test_a_broken_sudo_fails_the_socat_check_and_not_the_doctor(tmp_path, linux):
    class Dead(SocatAgent):
        def run(self, argv, **kw):
            if argv[-1:] == ["socat"]:
                raise RuntimeError("sudo failed")
            return super().run(argv, **kw)

    c = run_agent_doctor(agent_settings(tmp_path), Dead())[NAME]
    assert not c.ok and "could not run as the agent account" in c.detail


def test_on_macos_there_is_no_socat_check(tmp_path, monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)
    agent = SocatAgent(socat="")
    out = run_agent_doctor(agent_settings(tmp_path), agent)
    assert NAME not in out
    assert not any("socat" in " ".join(argv) for argv, _ in agent.calls)


def test_without_an_agent_account_there_is_no_socat_check(tmp_path, linux):
    out = run_agent_doctor(settings(tmp_path, ci_user="apx-ci"))
    assert NAME not in out
