import datetime as dt

import gate

NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)


def run(hours_ago, conclusion="success", status="completed", hard=False):
    t = (NOW - dt.timedelta(hours=hours_ago)).isoformat()
    return {"created_at": t, "conclusion": conclusion, "status": status, "hard": hard}


A = {"mode": "standard", "tier": "A"}


def test_allows_and_routes_models():
    d = gate.decide(A, [], 0, role="implementer", now=NOW)
    assert d.allow and (d.model, d.effort, d.max_turns, d.remaining) == ("sonnet", "medium", 40, 2)
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
    assert (d.model, d.effort, d.max_turns) == ("opus", "high", 45)
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
        if a[0] in ("pr", "api"):
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


def test_merged_agent_pr_is_detected_and_retry_overrides():
    pulls = [
        {"head": {"ref": "agent/48-fix"}, "merged_at": "2026-10-16T10:00:00Z"},
        {"head": {"ref": "agent/50-x"}, "merged_at": None},
        {"head": {"ref": "feature/51-x"}, "merged_at": "2026-10-16T10:00:00Z"},
    ]
    merged = gate.merged_agent_issues(pulls)
    assert merged == {48}
    assert gate.skip_merged(48, {"agent-ready"}, merged)
    assert not gate.skip_merged(48, {"agent-ready", "retry"}, merged)
    assert not gate.skip_merged(50, {"agent-ready"}, merged)


def test_dispatch_skips_issue_with_merged_agent_pr_unless_retry():
    L = lambda *n: [{"name": x} for x in n]

    def make(labels):
        def gh(*a):
            if a[0] in ("run", "pr"):
                return []
            if a[0] == "api":
                return [{"head": {"ref": "agent/48-fix"}, "merged_at": "2026-10-16T10:00:00Z"}]
            if a[:2] == ("issue", "view"):
                return {"labels": L(*labels)}
            raise AssertionError(a)

        return gh

    cfg = {"mode": "standard", "tier": "A"}
    fired = []
    assert gate.cmd_dispatch(cfg, 48, gh=make(["agent-ready"]), run=lambda *a: fired.append(a), sleep=lambda s: None) == 0
    assert not fired
    assert (
        gate.cmd_dispatch(cfg, 48, gh=make(["agent-ready", "retry"]), run=lambda *a: fired.append(a), sleep=lambda s: None) == 1
    )


def test_owner_hold_blocks_until_it_expires():
    import datetime as dt

    now = dt.datetime(2026, 10, 16, 15, tzinfo=dt.timezone.utc)
    cfg = {"tier": "A", "mode": "standard", "hold_until": "2026-10-16T21:00:00Z"}
    d = gate.decide(cfg, [], 0, role="implementer", now=now)
    assert not d.allow and "hold" in d.reason
    cfg["hold_until"] = "2026-10-16T10:00:00Z"
    assert gate.decide(cfg, [], 0, role="implementer", now=now).allow


def test_inflight_issues_are_not_dispatched_twice():
    runs = [
        {"status": "in_progress", "displayTitle": "agent #48 "},
        {"status": "queued", "displayTitle": "agent #42 [hard]"},
        {"status": "completed", "displayTitle": "agent #46 "},
    ]
    assert gate.inflight_issues(runs) == {48, 42}
    issues = [{"number": n, "labels": [{"name": "agent-ready"}], "createdAt": f"2026-10-0{n % 9 + 1}"} for n in (48, 42, 46)]
    branches = [f"agent/{n}-inflight" for n in gate.inflight_issues(runs)]
    assert gate.pick_issues(issues, branches, 5) == [46]


def test_chain_triggers_are_in_the_dispatch_caller_and_gated():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "kit"
    caller = (root / "callers/agent-dispatch.yml").read_text()
    wf = (root / "workflows/dispatch.yml").read_text()
    assert "workflow_run:" in caller and '"agent-exec"' in caller and "push:" in caller
    assert "github.event.workflow_run.name == 'agent-exec'" in wf and "AUTOPILOT_PAUSED != 'true'" in wf
