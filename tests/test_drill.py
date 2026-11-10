"""drill: each drill reports `caught` only when the control really catches the planted defect."""

import os

import pytest

from autopilot import cli, drill, trace
from autopilot.standard import engine


def outcomes(only=None):
    return {r.id: r.outcome for r in drill.run_all(only)}


def test_every_drill_reports_the_expected_outcome():
    assert outcomes() == {
        "baseline-green": "green",
        "hollow-link-skipped": "caught",
        "hollow-link-no-assertion": "limit",
        "guard-protected-paths": "caught",
        "guard-ignores-humans": "caught",
        "guard-test-deletion": "caught",
        "day0-baseline": "green",
        "day0-hook-not-executable": "caught",
        "day0-hook-no-setup": "caught",
        "day0-secret-scan-removed": "caught",
        "day0-workflow-lint-removed": "caught",
        "day0-cooldown-removed": "caught",
        "day0-old-repo-not-broken": "caught",
        "day0-quick-empty": "limit",
    }


def test_the_command_exits_zero_when_all_controls_hold(capsys):
    assert cli.main(["drill"]) == 0
    assert "limit" in capsys.readouterr().out


def test_an_unknown_drill_name_is_an_error(capsys):
    assert cli.main(["drill", "nope"]) == 2


def test_a_trace_that_calls_everything_green_is_reported_as_missed(monkeypatch):
    monkeypatch.setattr(trace, "trace", lambda spec, cases: [trace.Row("pytest x", "green", "")])
    got = outcomes(["hollow-link"])
    assert got["hollow-link-skipped"] == "missed"


def test_a_trace_that_starts_seeing_assertionless_tests_flags_the_limit_as_fixed(monkeypatch):
    monkeypatch.setattr(trace, "trace", lambda spec, cases: [trace.Row("pytest x", "skipped", "")])
    assert outcomes(["hollow-link"])["hollow-link-no-assertion"] == "limit-fixed"


def test_a_guard_that_flags_nothing_is_reported_as_missed(monkeypatch):
    monkeypatch.setattr(drill, "guard_violations", lambda diff, agent: [])
    got = outcomes(["guard-on-diff"])
    assert got["guard-protected-paths"] == "missed" and got["guard-test-deletion"] == "missed"


def test_a_guard_that_blocks_humans_is_reported_as_missed(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(drill, "guard_violations", lambda diff, agent: [SimpleNamespace(check="protected-path", path="x")])
    assert outcomes(["guard-on-diff"])["guard-ignores-humans"] == "missed"


def test_a_fixture_that_does_not_pass_is_baseline_failed_not_a_pass(monkeypatch):
    monkeypatch.setattr(engine, "exit_code", lambda results, strict=False: 1)
    assert outcomes(["baseline-green"])["baseline-green"] == "baseline-failed"


def test_a_drill_that_crashes_is_reported_not_swallowed(monkeypatch):
    def boom(tmp):
        raise RuntimeError("boom")

    monkeypatch.setitem(drill.DRILLS, "baseline-green", boom)
    (r,) = drill.run_all(["baseline-green"])
    assert r.outcome == "baseline-failed" and "RuntimeError: boom" in r.detail


@pytest.mark.parametrize("bad", ["missed", "baseline-failed", "limit-fixed"])
def test_a_bad_outcome_makes_the_command_exit_one(monkeypatch, bad, capsys):
    monkeypatch.setattr(drill, "run_all", lambda only=None: [drill.DrillResult("d", bad, "")])
    assert cli.main(["drill"]) == 1


def test_drills_leave_the_working_directory_untouched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(os.listdir(tmp_path))
    drill.run_all()
    assert sorted(os.listdir(tmp_path)) == before


def test_the_fixture_is_removed_after_the_drills(monkeypatch):
    seen = []
    real = drill.DRILLS["baseline-green"]

    def spy(tmp):
        seen.append(tmp)
        return real(tmp)

    monkeypatch.setitem(drill.DRILLS, "baseline-green", spy)
    drill.run_all(["baseline-green"])
    assert seen and not seen[0].exists()
