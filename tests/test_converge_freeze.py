"""The weekly `ap standard converge --apply` job edits GitHub issues on every portfolio repo, so the work-hours freeze applies to it.

Two layers, because launchd runs a missed job on wake (a Mac asleep at 19:00 may wake at 10:00 on a weekday):
  1. the schedule in the plist is outside policy/time.yaml's window, checked against the policy itself so the two cannot drift;
  2. the run refuses to start inside the window, using the one resolver (autopilot.freeze), failing closed.
"""

import argparse
import datetime as dt
import inspect
import json
import plistlib
import re
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from autopilot import freeze
from autopilot.converge import command

ROOT = Path(__file__).resolve().parent.parent
PLIST = ROOT / "deploy/launchd/com.autopilot.standard.converge.plist"
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def et(y, mo, d, h, m=0):
    return dt.datetime(y, mo, d, h, m, tzinfo=ET)


MON_9AM = et(2026, 11, 16, 9)
MON_7PM = et(2026, 11, 16, 19)


# ---- layer 1: the schedule against the policy -------------------------------------------------------------------------------


def firings(schedule) -> list[tuple[int, int, int]]:
    """Every (python weekday, hour, minute) a launchd StartCalendarInterval can fire. A missing key is a wildcard, as in launchd;
    launchd's Weekday 0 and 7 are both Sunday."""
    entries = schedule if isinstance(schedule, list) else [schedule]
    out = []
    for e in entries:
        days = [e["Weekday"]] if "Weekday" in e else range(0, 7)
        hours = [e["Hour"]] if "Hour" in e else range(24)
        minutes = [e["Minute"]] if "Minute" in e else range(60)
        for d in days:
            for h in hours:
                for m in minutes:
                    out.append(((d - 1) % 7, h, m))
    return out


def violations(schedule, policy: freeze.Policy) -> list[str]:
    """Firings that land inside the window, or inside the wind-down just before it, on any weekday from effective_from for two years
    (so both DST changes are covered; the job is scheduled in the Mac's local time, which is ET for the owner)."""
    bad = []
    start = policy.effective_from
    for wd, h, m in firings(schedule):
        for week in range(0, 105):
            day = start + dt.timedelta(days=(wd - start.weekday()) % 7 + 7 * week)
            when = dt.datetime.combine(day, dt.time(h, m), tzinfo=ET)
            v = freeze.check(policy, when)
            if v.frozen or v.wind_down:
                bad.append(f"{when:%a %Y-%m-%d %H:%M %Z}: {v.reason}")
                break
    return bad


@pytest.fixture(scope="module")
def policy():
    return freeze.load(freeze.DEFAULT_FILE)


def plist():
    return plistlib.loads(PLIST.read_bytes())


def test_the_plist_schedule_is_outside_the_policy_window(policy):
    assert violations(plist()["StartCalendarInterval"], policy) == []


def test_the_checker_itself_catches_the_old_monday_0900_schedule(policy):
    old = {"Weekday": 1, "Hour": 9, "Minute": 0}
    assert violations(old, policy) and "work-hours freeze" in violations(old, policy)[0]
    assert violations({"Weekday": 1, "Hour": 8, "Minute": 15}, policy)  # inside the 20-minute wind-down before 08:30
    assert violations({"Weekday": 3, "Hour": 18, "Minute": 29}, policy)
    assert violations({"Hour": 19, "Minute": 0}, policy) == []  # every day at 19:00 is fine
    assert violations({"Weekday": 2}, policy)  # a missing Hour and Minute are wildcards, so this fires all day
    assert violations([{"Weekday": 6, "Hour": 10, "Minute": 0}, {"Weekday": 2, "Hour": 12, "Minute": 0}], policy)  # one bad entry in a list


def test_launchd_weekday_zero_and_seven_are_both_sunday():
    assert firings({"Weekday": 0, "Hour": 1, "Minute": 0}) == firings({"Weekday": 7, "Hour": 1, "Minute": 0}) == [(6, 1, 0)]


def test_the_plist_has_no_other_way_to_start_the_job(policy):
    p = plist()
    assert p["RunAtLoad"] is False
    for key in ("StartInterval", "WatchPaths", "QueueDirectories", "KeepAlive", "StartOnMount"):
        assert key not in p, f"{key} would start the job outside the schedule"


def test_the_schedule_is_still_weekly():
    s = plist()["StartCalendarInterval"]
    assert isinstance(s, dict) and set(s) == {"Weekday", "Hour", "Minute"}


# ---- layer 2: the run refuses inside the window -----------------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    def set_(instant):
        monkeypatch.setattr(command, "_clock", lambda: instant)

    return set_


@pytest.fixture
def status(tmp_path, monkeypatch):
    path = tmp_path / "last.json"
    monkeypatch.setattr(command, "STATUS", path)
    monkeypatch.setattr(command, "HISTORY", tmp_path / "history.jsonl")
    return path


def ns(**kw):
    return argparse.Namespace(**{"owner": None, "root": "", "json": False, "all": False, "apply": True, "only": None, **kw})


class NoRun:
    """A subprocess stand-in that fails the test if anything at all is run (gh, git)."""

    calls: list = []

    def __call__(self, cmd, *a, **k):
        NoRun.calls.append(cmd)
        raise AssertionError(f"converge ran {cmd[:3]} inside the freeze")


def boom_portfolio():
    raise AssertionError("the portfolio was read: the freeze check must come first")


def go(**kw):
    return command.cmd_converge(ns(**kw), load_portfolio=boom_portfolio, run=NoRun())


def test_apply_at_0900_et_on_a_weekday_touches_nothing_and_says_why(clock, status, capsys):
    clock(MON_9AM)
    assert go() == 0
    assert "work-hours freeze" in capsys.readouterr().out
    body = json.loads(status.read_text())
    assert body["skipped"] and "freeze" in body["skipped"] and body["ok"] is True and body["errors"] == []


def test_it_does_not_touch_the_real_status_or_history_when_it_refuses(clock, status):
    clock(MON_9AM)
    go()
    assert not (status.parent / "history.jsonl").exists()


def test_json_mode_reports_the_refusal_as_json(clock, status, capsys):
    clock(MON_9AM)
    assert go(json=True) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is False and "freeze" in out["frozen"]


def test_the_same_run_outside_the_window_goes_ahead(clock, status):
    """The control for the tests above: at 19:00 the portfolio IS read, so a refusal at 09:00 is the freeze and nothing else."""
    clock(MON_7PM)
    with pytest.raises(AssertionError, match="portfolio was read"):
        go()


def test_a_dry_run_only_reads_so_it_is_not_held(clock, status):
    clock(MON_9AM)
    with pytest.raises(AssertionError, match="portfolio was read"):
        go(apply=False)


@pytest.mark.parametrize(
    "utc_iso, held",
    [
        ("2026-11-16T13:29:00+00:00", False),  # 08:29 EST
        ("2026-11-16T13:30:00+00:00", True),  # 08:30 EST
        ("2026-11-16T23:29:00+00:00", True),  # 18:29 EST
        ("2026-11-16T23:30:00+00:00", False),  # 18:30 EST
        ("2027-03-15T12:29:00+00:00", False),  # 08:29 EDT, the Monday after spring-forward
        ("2027-03-15T12:30:00+00:00", True),  # 08:30 EDT: a fixed -5 offset would call this free
        ("2027-03-15T22:30:00+00:00", False),  # 18:30 EDT: a fixed -5 offset would call this frozen
        ("2026-11-21T15:00:00+00:00", False),  # Saturday
        ("2026-11-13T14:00:00+00:00", False),  # a weekday before effective_from
    ],
)
def test_dst_and_the_edges_follow_new_york_time(clock, status, utc_iso, held):
    clock(dt.datetime.fromisoformat(utc_iso))
    if held:
        assert go() == 0 and json.loads(status.read_text())["skipped"]
    else:
        with pytest.raises(AssertionError, match="portfolio was read"):
            go()


def test_lift_dates_from_time_yaml_let_that_day_run(clock, status, tmp_path, monkeypatch):
    p = tmp_path / "time.yaml"
    p.write_text(freeze.DEFAULT_FILE.read_text().replace("dates: []", "dates: [2026-11-17]"))
    monkeypatch.setattr(command, "POLICY_FILE", p)
    clock(et(2026, 11, 17, 9))
    with pytest.raises(AssertionError, match="portfolio was read"):
        go()
    clock(et(2026, 11, 18, 9))
    assert go() == 0


@pytest.mark.parametrize("text", ["", "{{{ no", "- a\n", "timezone: UTC\n"])
def test_a_broken_policy_file_means_the_default_window_and_no_lift(clock, status, tmp_path, monkeypatch, text):
    p = tmp_path / "time.yaml"
    p.write_text(text)
    monkeypatch.setattr(command, "POLICY_FILE", p)
    clock(MON_9AM)
    assert go() == 0 and json.loads(status.read_text())["skipped"]
    clock(MON_7PM)
    with pytest.raises(AssertionError, match="portfolio was read"):
        go()


def test_a_missing_policy_file_is_frozen_in_the_window(clock, status, tmp_path, monkeypatch):
    monkeypatch.setattr(command, "POLICY_FILE", tmp_path / "nope.yaml")
    clock(MON_9AM)
    assert go() == 0 and json.loads(status.read_text())["skipped"]


def test_a_resolver_that_raises_means_frozen_even_at_a_free_time(clock, status, monkeypatch):
    clock(MON_7PM)

    def bad(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(freeze, "check_file", bad)
    assert go() == 0 and "resolver" in json.loads(status.read_text())["skipped"]


@pytest.mark.parametrize("bad", [dt.datetime(2026, 11, 16, 19), None, "later"])
def test_a_clock_that_is_naive_or_wrong_means_frozen(status, monkeypatch, bad):
    monkeypatch.setattr(command, "_clock", lambda: bad)
    assert go() == 0 and json.loads(status.read_text())["skipped"]


def test_a_clock_that_raises_means_frozen(status, monkeypatch):
    def boom():
        raise OSError("no clock")

    monkeypatch.setattr(command, "_clock", boom)
    assert go() == 0 and json.loads(status.read_text())["skipped"]


def test_there_is_no_override(clock, status, monkeypatch):
    clock(MON_9AM)
    for name in ("CONVERGE_FORCE", "AUTOPILOT_FREEZE_OFF", "FREEZE_OVERRIDE", "APX_ACTIVE_WINDOW"):
        monkeypatch.setenv(name, "1")
    assert go() == 0 and json.loads(status.read_text())["skipped"]
    for fn in (command.frozen_reason, command.cmd_converge):
        bad = [p for p in inspect.signature(fn).parameters if re.search(r"force|override|skip|bypass|ignore|unfreeze|lift", p)]
        assert not bad, bad
    helptext = subprocess.run(["uv", "run", "ap", "standard", "converge", "--help"], cwd=ROOT, capture_output=True, text=True).stdout
    assert helptext and not re.search(r"--(force|override|skip|bypass|ignore)", helptext)


def test_the_gate_uses_the_one_resolver_and_the_real_policy_file():
    assert command.POLICY_FILE == freeze.DEFAULT_FILE
    src = inspect.getsource(command.frozen_reason)
    assert "check_file" in src and not re.search(r"timedelta|ZoneInfo|weekday\(", src)
