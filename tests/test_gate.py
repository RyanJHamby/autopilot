import datetime as dt

import gate

NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)


def run(hours_ago, conclusion="success", status="completed", hard=False):
    t = (NOW - dt.timedelta(hours=hours_ago)).isoformat()
    return {"created_at": t, "conclusion": conclusion, "status": status, "hard": hard}


A = {"mode": "standard", "tier": "A"}


def test_allows_and_routes_models():
    d = gate.decide(A, [], 0, role="implementer", now=NOW)
    assert d.allow and (d.model, d.effort, d.max_turns, d.remaining) == ("sonnet", "medium", 25, 2)
    assert gate.decide(A, [], 0, role="triage", now=NOW).model == "haiku"
    assert gate.decide({"mode": "yolo", "tier": "B"}, [], 0, role="implementer", now=NOW).max_turns == 60


def test_dormant_and_tier_c_closed():
    assert not gate.decide({"mode": "dormant", "tier": "A"}, [], 0, role="implementer", now=NOW).allow
    assert not gate.decide({"mode": "standard", "tier": "C"}, [], 0, role="implementer", now=NOW).allow


def test_daily_cap_rolls_over_24h():
    runs = [run(1), run(5)]
    assert not gate.decide(A, runs, 0, role="implementer", now=NOW).allow
    assert gate.decide(A, [run(1), run(30)], 0, role="implementer", now=NOW).allow


def test_open_pr_cap_applies_to_implementer_only():
    assert not gate.decide(A, [], 3, role="implementer", now=NOW).allow
    assert gate.decide(A, [], 3, role="reviewer", now=NOW).allow


def test_circuit_breaker():
    runs = [run(30, "failure"), run(40, "failure")]
    d = gate.decide(A, runs, 0, role="implementer", now=NOW)
    assert not d.allow and "circuit breaker" in d.reason
    assert gate.decide(A, [run(30, "failure"), run(40, "success")], 0, role="implementer", now=NOW).allow


def test_hard_runs_opus_only_tier_a_and_once_a_day():
    d = gate.decide(A, [], 0, role="implementer", hard=True, now=NOW)
    assert (d.model, d.effort, d.max_turns) == ("opus", "high", 30)
    assert not gate.decide(A, [run(1, hard=True)], 0, role="implementer", hard=True, now=NOW).allow
    assert gate.decide({"mode": "standard", "tier": "B"}, [], 0, role="implementer", hard=True, now=NOW).model == "sonnet"


def test_budget_overrides_from_repo_yaml():
    cfg = {**A, "budget": {"runs_per_day": {"A": 1}}}
    assert not gate.decide(cfg, [run(1)], 0, role="implementer", now=NOW).allow


def test_pick_issues_order_and_filters():
    L = lambda *n: [{"name": x} for x in n]
    issues = [
        {"number": 1, "labels": L("agent-ready"), "createdAt": "2026-10-01"},
        {"number": 2, "labels": L("agent-ready", "p0"), "createdAt": "2026-10-05"},
        {"number": 3, "labels": L("agent-ready", "hold"), "createdAt": "2026-09-01"},
        {"number": 4, "labels": L("agent-ready"), "createdAt": "2026-09-15"},
        {"number": 5, "labels": L("bug"), "createdAt": "2026-08-01"},
    ]
    assert gate.pick_issues(issues, ["agent/4-fix-thing"], 5) == [2, 1]
    assert gate.pick_issues(issues, [], 1) == [2]
