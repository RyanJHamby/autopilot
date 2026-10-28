import sys

import pytest

from autopilot.apx import cilane

PY = sys.executable


def test_parse_commands_rejects_metacharacters():
    assert cilane.parse_commands({"commands": ["pytest -q", "ruff check ."]}) == ["pytest -q", "ruff check ."]
    for bad in ["pytest; rm -rf /", "a && b", "echo $(id)", "x | y", "a'b"]:
        with pytest.raises(ValueError):
            cilane.parse_commands({"commands": [bad]})
    assert cilane.parse_commands({}) == []


def test_env_is_scrubbed():
    src = {"PATH": "/usr/bin", "GITHUB_TOKEN": "g", "CLAUDE_CODE_OAUTH_TOKEN": "c", "AWS_SECRET_ACCESS_KEY": "a"}
    env = cilane.ci_env("/h", src)
    assert set(env) == {"PATH", "HOME", "CI"}


def test_runs_in_checkout_without_shell_and_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "leak-me")
    (tmp_path / "probe.py").write_text("import os,sys\nsys.exit(0 if 'GITHUB_TOKEN' not in os.environ and os.getcwd() else 1)\n")
    home = tmp_path / "h"
    home.mkdir()
    res = cilane.run_commands(tmp_path, [f"{PY} probe.py"], home=home)
    assert res[0].ok, res[0].output


def test_stops_at_first_failure_and_reports_skipped(tmp_path):
    (tmp_path / "bad.py").write_text("import sys; print('boom'); sys.exit(2)\n")
    home = tmp_path / "h"
    home.mkdir()
    cmds = [f"{PY} bad.py", f"{PY} -c pass"]
    res = cilane.run_commands(tmp_path, cmds, home=home)
    assert len(res) == 1 and not res[0].ok and res[0].note == "exit 2"
    ok, md = cilane.summarize(res, cmds)
    assert not ok and "SKIPPED" in md and "boom" in md


def test_timeout_and_missing_command(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    r = cilane.run_commands(tmp_path, [f"{PY} -c import_time_sleep"], home=home, timeout_each=5)
    assert not r[0].ok
    (tmp_path / "slow.py").write_text("import time; time.sleep(30)\n")
    r = cilane.run_commands(tmp_path, [f"{PY} slow.py"], home=home, timeout_each=1)
    assert r[0].note.startswith("timed out")
    r = cilane.run_commands(tmp_path, ["definitely-not-a-binary"], home=home)
    assert r[0].note == "command not found"


def test_empty_plan_is_not_a_pass():
    ok, md = cilane.summarize([], [])
    assert not ok and "nothing was checked" in md


def test_all_green_summary(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    cmds = [f"{PY} -c pass"]
    ok, md = cilane.summarize(cilane.run_commands(tmp_path, cmds, home=home), cmds)
    assert ok and md.startswith("- PASS")
