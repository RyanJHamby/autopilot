import datetime as dt

from autopilot.apx import daemon as dm
from autopilot.apx.ledger import Ledger
from autopilot.apx.usage import repo_usage, usage_line

NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=dt.timezone.utc)
MIDNIGHT = dt.datetime(2026, 10, 29, 0, 0, tzinfo=dt.timezone.utc)
R = "o/a"


def hrs(h):
    return NOW - dt.timedelta(hours=h)


def done(L, issue, at, conclusion="success", turns=None, kind="run", repo=R):
    rid = L.start(repo, issue, now=at, kind=kind)
    L.finish(rid, conclusion, turns=turns, now=at)
    return rid


def test_counts_outcomes_fixes_and_turns_for_today():
    L = Ledger()
    done(L, 1, hrs(3), "success", turns=10)
    done(L, 2, hrs(2), "failure", turns=7)
    done(L, 3, hrs(1), "success", turns=None, kind="fix")
    L.start(R, 4, now=hrs(0.5))  # still running: started, neither ok nor failed
    u = repo_usage(L, R, cap=2, now=NOW)
    t = u.today
    assert (t.started, t.ok, t.failed, t.fixes) == (4, 2, 1, 1)
    assert (t.turns, t.turns_unrecorded) == (17, 1)
    assert u.to_dict()["today"]["started"] == 4


def test_skipped_and_cancelled_are_not_failures_and_not_spent():
    L = Ledger()
    done(L, 1, hrs(2), "skipped")
    done(L, 2, hrs(1), "cancelled")
    u = repo_usage(L, R, cap=2, now=NOW)
    assert u.today.failed == 0 and u.used_24h == 0 and u.remaining == 2


def test_remaining_cap_matches_the_gate_rolling_24h_window():
    L = Ledger()
    done(L, 1, hrs(30))  # outside 24h: not counted against the cap
    done(L, 2, hrs(5))
    done(L, 3, hrs(1), kind="fix")  # fixes share the cap
    u = repo_usage(L, R, cap=2, now=NOW)
    assert u.used_24h == 2 and u.remaining == 0
    assert repo_usage(L, R, cap=5, now=NOW).remaining == 3
    assert repo_usage(L, R, now=NOW).remaining is None  # unknown cap is reported, not invented


def test_utc_midnight_boundary_today_includes_exactly_midnight_only():
    L = Ledger()
    done(L, 1, MIDNIGHT - dt.timedelta(microseconds=1))  # yesterday, 23:59:59.999999
    done(L, 2, MIDNIGHT)  # exactly 00:00:00 is today
    u = repo_usage(L, R, cap=2, now=NOW)
    assert u.today.started == 1
    assert u.week.started == 2


def test_week_window_is_seven_days_and_excludes_other_repos():
    L = Ledger()
    done(L, 1, NOW - dt.timedelta(days=7, seconds=1))  # just outside
    done(L, 2, NOW - dt.timedelta(days=7))  # exactly on the edge: inside
    done(L, 3, NOW - dt.timedelta(days=2))
    done(L, 4, hrs(1), repo="o/other")
    u = repo_usage(L, R, cap=2, now=NOW)
    assert u.week.started == 2 and u.today.started == 0


def test_a_repo_with_no_rows_is_all_zero():
    u = repo_usage(Ledger(), "o/none", cap=2, now=NOW)
    assert u.today.started == 0 and u.week.started == 0 and u.today.turns == 0
    assert u.used_24h == 0 and u.remaining == 2


def test_usage_line_shape_and_daemon_lines():
    L = Ledger()
    done(L, 1, hrs(2))
    done(L, 2, hrs(1), kind="fix")
    line = usage_line(repo_usage(L, R, cap=2, now=NOW))
    assert line == "o/a: usage last 24h 2 runs (0 of 2 left), 1 fixes, 7d: 2 runs"
    assert usage_line(repo_usage(L, R, now=NOW)) == "o/a: usage last 24h 2 runs, 1 fixes, 7d: 2 runs"
    lines = dm.usage_lines(L, {R: {}, "o/none": {}})
    assert len(lines) == 2 and lines[1].startswith("o/none: usage last 24h 0 runs")


def test_status_line_counts_the_rolling_24h_not_the_utc_day():
    # a run 3h before midnight is in yesterday's UTC day but inside the gate's 24h window: line and 'left' must agree
    L = Ledger()
    done(L, 1, MIDNIGHT - dt.timedelta(hours=3))
    u = repo_usage(L, R, cap=2, now=NOW)
    assert u.today.started == 0 and u.day.started == 1 and u.remaining == 1
    assert usage_line(u) == "o/a: usage last 24h 1 runs (1 of 2 left), 0 fixes, 7d: 1 runs"
