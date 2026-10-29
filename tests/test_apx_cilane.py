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


def test_a_command_that_fails_with_permission_denied_is_a_failed_step_not_a_crash(tmp_path, monkeypatch):
    # on the apx-ci account a missing command raised PermissionError (an unreadable PATH entry), which crashed the lane
    def boom(*a, **k):
        raise PermissionError(13, "Permission denied", "x")

    monkeypatch.setattr(cilane.subprocess, "run", boom)
    home = tmp_path / "h"
    home.mkdir()
    r = cilane.run_commands(tmp_path, ["whatever"], home=home)
    assert not r[0].ok and r[0].note == "command not found"


def test_empty_plan_is_not_a_pass():
    ok, md = cilane.summarize([], [])
    assert not ok and "nothing was checked" in md


def test_all_green_summary(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    cmds = [f"{PY} -c pass"]
    ok, md = cilane.summarize(cilane.run_commands(tmp_path, cmds, home=home), cmds)
    assert ok and md.startswith("- PASS")


def test_ci_steps_come_from_ci_not_the_agent_allowlist():
    cfg = {"commands": ["uv run", "pytest"], "ci": ["uv sync --quiet", {"run": "npm test", "dir": "apps/control-plane"}]}
    assert cilane.parse_ci_steps(cfg) == [("uv sync --quiet", ""), ("npm test", "apps/control-plane")]
    assert cilane.parse_ci_steps({"commands": ["uv run"]}) == []  # the allowlist is never treated as CI


@pytest.mark.parametrize(
    "bad",
    [
        {"run": "npm test", "dir": "../outside"},
        {"run": "npm test", "dir": "/etc"},
        {"run": "npm test", "dir": "a/../../b"},
        {"run": "npm test", "dir": "a b"},
        {"run": "pytest && echo chained"},
        {"run": ""},
        "pytest; id",
    ],
)
def test_ci_steps_reject_unsafe_entries(bad):
    with pytest.raises(ValueError):
        cilane.parse_ci_steps({"ci": [bad]})


def test_step_runs_in_its_subdirectory_and_reports_it(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "where.py").write_text("import os,sys\nsys.exit(0 if os.getcwd().endswith('sub') else 1)\n")
    home = tmp_path / "h"
    home.mkdir()
    steps = [(f"{PY} where.py", "sub")]
    res = cilane.run_commands(tmp_path, steps, home=home)
    assert res[0].ok and res[0].cmd.startswith("sub: ")
    ok, md = cilane.summarize(res, steps)
    assert ok and "sub:" in md


def test_empty_plan_message_points_at_the_ci_key():
    ok, md = cilane.summarize([], [])
    assert not ok and "`ci:`" in md


def test_skipped_steps_show_their_directory():
    steps = [(f"{PY} -c import_nothing_xyz", ""), ("npm test", "apps/cp")]
    res = [cilane.CmdResult("x", False, 0.1, "", "exit 1")]
    ok, md = cilane.summarize(res, steps)
    assert not ok and "SKIPPED `apps/cp: npm test`" in md


def test_a_ci_command_gets_enough_time_for_a_full_suite_by_default():
    import inspect

    assert inspect.signature(cilane.run_commands).parameters["timeout_each"].default >= 1800


def test_toolchain_dirs_are_linked_into_the_scratch_home_and_nothing_else(tmp_path):
    real = tmp_path / "real"
    (real / ".cargo" / "bin").mkdir(parents=True)
    (real / ".cargo" / "bin" / "rustc").write_text("x")
    (real / ".ssh").mkdir()
    (real / ".ssh" / "id_ed25519").write_text("private")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert cilane.link_toolchains(scratch, real, [".cargo", ".rustup"]) == [".cargo"]  # .rustup absent: skipped
    assert (scratch / ".cargo" / "bin" / "rustc").read_text() == "x"
    assert not (scratch / ".ssh").exists()  # credentials are never visible to the PR's code
    assert cilane.link_toolchains(scratch, real, [".cargo"]) == []  # idempotent


@pytest.mark.parametrize("bad", [".ssh/..", "../etc", "/etc", ".cargo/bin", "cargo", ".", "..", ".a b", ""])
def test_toolchain_link_names_must_be_a_single_dot_directory(tmp_path, bad):
    (tmp_path / "real").mkdir()
    (tmp_path / "scratch").mkdir()
    with pytest.raises(ValueError):
        cilane.link_toolchains(tmp_path / "scratch", tmp_path / "real", [bad])


def test_a_ci_command_finds_the_compiler_through_the_linked_home(tmp_path):
    real = tmp_path / "real"
    (real / ".cargo" / "bin").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (tmp_path / "probe.py").write_text(
        "import os,sys\nsys.exit(0 if os.path.exists(os.path.join(os.environ['HOME'], '.cargo', 'bin')) else 1)\n"
    )
    ok = cilane.run_commands(tmp_path, [f"{PY} probe.py"], home=scratch, toolchain_links=[".cargo"], real_home=real)
    assert ok[0].ok, ok[0].output
    scratch2 = tmp_path / "scratch2"
    scratch2.mkdir()
    no = cilane.run_commands(tmp_path, [f"{PY} probe.py"], home=scratch2)  # control: without the link the probe fails
    assert not no[0].ok
