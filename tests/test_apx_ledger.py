import datetime as dt

import gate

from autopilot.apx.ledger import Ledger

NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)
A = {"mode": "standard", "tier": "A"}


def ago(h):
    return NOW - dt.timedelta(hours=h)


def test_history_is_newest_first_and_per_repo():
    L = Ledger()
    a = L.start("o/a", 1, now=ago(5))
    L.finish(a, "success", now=ago(5))
    L.start("o/a", 2, hard=True, now=ago(1))
    L.start("o/b", 9, now=ago(2))
    h = L.runs("o/a")
    assert [r["status"] for r in h] == ["in_progress", "completed"]
    assert h[0]["hard"] is True and h[1]["conclusion"] == "success"
    assert len(L.runs("o/b")) == 1


def test_inflight_issues_excludes_finished_and_other_repos():
    L = Ledger()
    r = L.start("o/a", 1, now=ago(2))
    L.start("o/a", 2, now=ago(1))
    L.start("o/b", 3, now=ago(1))
    L.finish(r, "success")
    assert L.inflight_issues("o/a") == {2}


def test_daily_cap_matches_gate_decide():
    L = Ledger()
    for i in range(2):  # tier A allows 2 per day in the gate defaults
        r = L.start("o/a", i, now=ago(3 + i))
        L.finish(r, "success", now=ago(3 + i))
    d = gate.decide(A, L.runs("o/a"), 0, role="implementer", now=NOW)
    assert not d.allow and "daily run cap" in d.reason
    # a run older than 24h no longer counts
    L2 = Ledger()
    r = L2.start("o/a", 1, now=ago(30))
    L2.finish(r, "success", now=ago(30))
    assert gate.decide(A, L2.runs("o/a"), 0, role="implementer", now=NOW).allow


def test_circuit_breaker_matches_gate_decide():
    L = Ledger()
    for i in range(3):
        r = L.start("o/a", i, now=ago(40 + i))
        L.finish(r, "failure", now=ago(40 + i))
    d = gate.decide(A, L.runs("o/a"), 0, role="implementer", now=NOW)
    assert not d.allow and "circuit breaker" in d.reason


def test_abandon_stale_unblocks_crashed_runs():
    L = Ledger()
    L.start("o/a", 1, now=ago(5))
    L.start("o/a", 2, now=ago(0.1))
    assert L.abandon_stale(dt.timedelta(hours=1), now=NOW) == 1
    assert L.inflight_issues("o/a") == {2}
    assert L.runs("o/a")[-1]["conclusion"] == "timed_out"
