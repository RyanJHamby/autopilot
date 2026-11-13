"""The Claude Code version floor (autonomy hardening plan, work item W0-19): one policy value, one shared check.

Everything fails closed: a binary that is missing, output that does not parse, a policy file that is missing or malformed, or a
floor that is not a plain version all refuse. Nothing here runs the real `claude`: the probe is injected.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from autopilot import claude_floor as cf

ROOT = Path(__file__).resolve().parents[1]
FLOOR_FILE = ROOT / "policy" / "claude.yaml"


# --- the policy file ---
def test_the_policy_file_holds_the_floor_as_a_plain_version():
    data = yaml.safe_load(FLOOR_FILE.read_text())
    assert isinstance(data["min_version"], str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["min_version"])
    assert cf.load_floor() == tuple(int(x) for x in data["min_version"].split("."))


def test_the_floor_is_2_1_302_the_stricter_of_the_two_values_in_the_plan():
    assert cf.load_floor() == (2, 1, 302)


def test_the_number_lives_in_one_place():
    """No other source file may hard-code the floor or the CVE floor it covers."""
    hits = []
    for p in (ROOT / "src").rglob("*.py"):
        if p.name == "claude_floor.py":
            continue
        text = p.read_text()
        if re.search(r"\b2\.1\.(302|163)\b", text):
            hits.append(str(p.relative_to(ROOT)))
    assert hits == []


@pytest.mark.parametrize(
    "text",
    ["", "min_version: 2.1\n", "min_version: 2.1.302.4\n", "min_version: v2.1.302\n", "min_version: 2.1.302-beta\n",
     "min_version: 2\n", "min_version: [2, 1, 302]\n", "min_version: 2.1.x\n", "other: 2.1.302\n", ": : not yaml [\n", "- 2.1.302\n"],
)  # fmt: skip
def test_a_malformed_floor_file_refuses(tmp_path, text):
    p = tmp_path / "claude.yaml"
    p.write_text(text)
    with pytest.raises(cf.FloorError):
        cf.load_floor(p)


def test_a_missing_floor_file_refuses(tmp_path):
    with pytest.raises(cf.FloorError):
        cf.load_floor(tmp_path / "nope.yaml")


def test_a_floor_can_be_read_from_another_file(tmp_path):
    p = tmp_path / "claude.yaml"
    p.write_text('min_version: "3.0.1"\n')
    assert cf.load_floor(p) == (3, 0, 1)


# --- parsing what `claude --version` prints ---
@pytest.mark.parametrize(
    "text,want",
    [("2.1.323 (Claude Code)", (2, 1, 323)), ("2.1.323 (Claude Code)\n", (2, 1, 323)), ("  2.1.302  ", (2, 1, 302)),
     ("2.1.302", (2, 1, 302)), ("10.0.0 (Claude Code)", (10, 0, 0)), ("2.1.1000 (Claude Code)", (2, 1, 1000))],
)  # fmt: skip
def test_real_version_output_shapes_parse(text, want):
    assert cf.parse_version(text) == want


@pytest.mark.parametrize(
    "text",
    ["", "   ", "claude", "Claude Code 2.1.323", "2.1", "2.1.302-beta (Claude Code)", "2.1.302-rc.1", "v2.1.302", "2.1.3o2",
     "2.1.302.1 (Claude Code)", "-2.1.302", "2.1.302\n2.1.400", "command not found: claude", "2.1.๓๐๒", "2.1.302abc"],
)  # fmt: skip
def test_anything_that_is_not_a_plain_version_does_not_parse(text):
    assert cf.parse_version(text) is None


# --- the comparison ---
FLOOR = (2, 1, 302)


@pytest.mark.parametrize(
    "text,ok",
    [("2.1.302 (Claude Code)", True), ("2.1.301 (Claude Code)", False), ("2.1.303 (Claude Code)", True),
     ("2.1.1000 (Claude Code)", True), ("2.1.99 (Claude Code)", False), ("2.2.0 (Claude Code)", True),
     ("2.0.999 (Claude Code)", False), ("3.0.0 (Claude Code)", True), ("1.99.999 (Claude Code)", False),
     ("2.1.323 (Claude Code)", True), ("2.1.163 (Claude Code)", False)],
)  # fmt: skip
def test_versions_compare_numerically_part_by_part(text, ok):
    got, detail = cf.verdict(text, FLOOR)
    assert got is ok
    assert "2.1.302" in detail


@pytest.mark.parametrize("text", ["", "garbage", "2.1.302-beta", "2.1"])
def test_unparsable_output_refuses_and_says_so(text):
    ok, detail = cf.verdict(text, FLOOR)
    assert ok is False
    assert "version" in detail.lower()


def test_the_verdict_names_the_installed_version_and_the_floor():
    ok, detail = cf.verdict("2.1.250 (Claude Code)", FLOOR)
    assert (ok, "2.1.250" in detail, "2.1.302" in detail) == (False, True, True)


# --- running the binary ---
def fake_run(stdout="2.1.323 (Claude Code)\n", rc=0, exc=None, calls=None):
    def run(cmd, **kw):
        if calls is not None:
            calls.append((list(cmd), kw))
        if exc:
            raise exc
        return subprocess.CompletedProcess(cmd, rc, stdout, "")

    return run


def test_probe_runs_the_binary_with_version_only_and_a_timeout():
    calls = []
    out = cf.probe("claude", run=fake_run(calls=calls))
    assert out.strip() == "2.1.323 (Claude Code)"
    cmd, kw = calls[0]
    assert cmd == ["claude", "--version"]
    assert kw.get("timeout")


@pytest.mark.parametrize(
    "run",
    [fake_run(exc=FileNotFoundError()), fake_run(exc=PermissionError()), fake_run(exc=subprocess.TimeoutExpired("claude", 30)),
     fake_run(rc=1), fake_run(rc=127, stdout="")],
)  # fmt: skip
def test_a_missing_or_failing_binary_refuses(run):
    with pytest.raises(cf.FloorError):
        cf.probe("claude", run=run)


# --- the machine check used by every caller ---
def test_machine_check_passes_at_or_above_the_floor():
    ok, detail = cf.machine_check(probe=lambda b: "2.1.323 (Claude Code)")
    assert ok is True and "2.1.323" in detail


def test_machine_check_fails_below_the_floor():
    ok, detail = cf.machine_check(probe=lambda b: "2.1.301 (Claude Code)")
    assert ok is False and "2.1.301" in detail


def test_machine_check_fails_when_the_binary_cannot_be_probed():
    def boom(b):
        raise cf.FloorError("claude is not installed")

    ok, detail = cf.machine_check(probe=boom)
    assert ok is False and "not installed" in detail


def test_machine_check_fails_closed_when_the_floor_file_is_broken(tmp_path):
    p = tmp_path / "claude.yaml"
    p.write_text("min_version: nope\n")
    ok, detail = cf.machine_check(probe=lambda b: "9.9.9 (Claude Code)", floor_path=p)
    assert ok is False and "floor" in detail.lower()


def test_machine_check_fails_closed_when_the_probe_crashes_unexpectedly():
    def boom(b):
        raise RuntimeError("surprise")

    ok, _ = cf.machine_check(probe=boom)
    assert ok is False


def test_there_is_no_argument_that_lowers_the_floor():
    import inspect

    params = set(inspect.signature(cf.machine_check).parameters) | set(inspect.signature(cf.verdict).parameters)
    assert not params & {"min_version", "floor_override", "force", "skip", "allow_old"}


# --- for callers that already ran the binary themselves (the launcher and the agent account) ---
def test_check_result_uses_the_exit_code_and_the_text():
    assert cf.check_result(0, "2.1.323 (Claude Code)")[0] is True
    assert cf.check_result(0, "2.1.301 (Claude Code)")[0] is False
    ok, detail = cf.check_result(1, "2.1.323 (Claude Code)")
    assert ok is False and "exit" in detail
    assert cf.check_result(127, "")[0] is False
    assert cf.check_result(0, "")[0] is False


def test_check_result_fails_closed_on_a_broken_floor_file(tmp_path):
    p = tmp_path / "claude.yaml"
    p.write_text("min_version: nope\n")
    assert cf.check_result(0, "9.9.9 (Claude Code)", floor_path=p)[0] is False
