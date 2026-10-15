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


def test_skipped_and_cancelled_runs_do_not_use_budget():
    runs = [run(1, "skipped"), run(2, "cancelled")]
    d = gate.decide(A, runs, 0, role="implementer", now=NOW)
    assert d.allow and d.remaining == 2
    assert not gate.decide(A, [run(1), run(2, "failure"), run(3, "skipped")], 0, role="implementer", now=NOW).allow


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


def test_dispatch_fires_allowed_issues_and_stops_at_cap():
    L = lambda *n: [{"name": x} for x in n]
    state = {"runs": [], "fired": []}

    def gh(*a):
        if a[0] == "run":
            return state["runs"]
        if a[0] == "pr":
            return []
        if a[:2] == ("issue", "list"):
            return [
                {"number": 7, "labels": L("agent-ready"), "createdAt": "2026-10-01"},
                {"number": 8, "labels": L("agent-ready", "hard"), "createdAt": "2026-10-02"},
                {"number": 9, "labels": L("agent-ready"), "createdAt": "2026-10-03"},
            ]
        if a[:2] == ("issue", "view"):
            n = int(a[2])
            return {"labels": L("agent-ready", "hard") if n == 8 else L("agent-ready")}
        raise AssertionError(a)

    def run(*a):
        state["fired"].append(a)
        n = int(a[a.index("-f") + 1].split("=")[1])
        state["runs"].append(
            {
                "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                "conclusion": None,
                "status": "queued",
                "displayTitle": "agent #%d%s" % (n, " [hard]" if n == 8 else ""),
            }
        )

    n = gate.cmd_dispatch({"mode": "standard", "tier": "A"}, None, gh=gh, run=run, sleep=lambda s: None)
    assert n == 2  # tier A cap = 2/day; third issue is not fired
    assert [a[5] for a in state["fired"]] == ["issue=7", "issue=8"]
    assert "model=opus" in state["fired"][1] and "hard=true" in state["fired"][1]


def test_dispatch_skips_held_issue():
    L = lambda *n: [{"name": x} for x in n]
    fired = []

    def gh(*a):
        if a[0] == "run" or a[0] == "pr":
            return []
        if a[:2] == ("issue", "view"):
            return {"labels": L("agent-ready", "hold")}
        raise AssertionError(a)

    n = gate.cmd_dispatch({"mode": "standard", "tier": "A"}, 5, gh=gh, run=lambda *a: fired.append(a), sleep=lambda s: None)
    assert n == 0 and not fired
