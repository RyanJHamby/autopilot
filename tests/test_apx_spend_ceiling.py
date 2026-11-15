"""Global dollar ceiling across all repos: policy/portfolio.yaml `defaults.global_usd_per_day` (rolling 24h).

Absent key: no extra ceiling (today's behaviour), and the usage line says "global_usd_per_day not set". Present but invalid: fail closed,
no agent runs or CI fixes anywhere. Spend is the ledger's cost_usd for runs started in the last 24h, plus the run's own dollar cap for
every run that is still in flight or finished without a reported cost. Checks, rebases and merges are never held by it.
"""

import datetime as dt
import sqlite3

import pytest
from test_apx_planner import NOW, REPO, Fake, issue, pr

from autopilot.apx import caps, planner, spend
from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

OTHER = "RyanJHamby/autopilot"
META = {"contexts": ["guard / guard", "build"], "agents": True}
CAPS = "defaults:\n  max_budget_usd: {standard: 3.00, yolo: 5.00, hard: 8.00, triage: 0.50, reviewer: 1.00}\n"


@pytest.fixture
def policy(tmp_path, monkeypatch):
    def write(extra: str = "") -> None:
        p = tmp_path / "portfolio.yaml"
        p.write_text(CAPS + extra)
        monkeypatch.setattr(caps, "PORTFOLIO_FILE", p)

    return write


def hrs(h):
    return NOW - dt.timedelta(hours=h)


def finished(led, repo, at, cost, budget=3.0, conclusion="success"):
    rid = led.start(repo, 1, now=at, budget_usd=budget)
    led.finish(rid, conclusion, cost_usd=cost, now=at)
    return rid


def agent_kinds(result):
    return [(r, a.kind) for r, v in result.items() for a in v["actions"] if a.kind in ("run-agent", "fix-ci")]


def busy():
    return Fake(issues=[issue(4)], open=[pr(1, "feature/own", "s1")], checks={"s1": []})


# --- the policy key ---


def test_absent_key_means_no_extra_ceiling(policy):
    policy()
    assert caps.global_usd_per_day() is None


@pytest.mark.parametrize("value", ["12.5", "12", "0"])
def test_valid_values(policy, value):
    policy(f"  global_usd_per_day: {value}\n")
    assert caps.global_usd_per_day() == float(value)


@pytest.mark.parametrize("value", ["-1", "'12'", "yes", ".nan", ".inf", "[1]", "null"])
def test_present_but_invalid_fails_closed(policy, value):
    policy(f"  global_usd_per_day: {value}\n")
    with pytest.raises(caps.CapError, match="global_usd_per_day"):
        caps.global_usd_per_day()


def test_unreadable_policy_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(caps, "PORTFOLIO_FILE", tmp_path / "missing.yaml")
    with pytest.raises(caps.CapError):
        caps.global_usd_per_day()


# --- summing the ledger ---


def test_reported_costs_are_summed_across_repos():
    led = Ledger()
    finished(led, REPO, hrs(1), 0.40)
    finished(led, OTHER, hrs(2), 1.10)
    finished(led, "RyanJHamby/drillpad-workspace", hrs(23), 0.50)
    assert spend.used_24h(led, now=NOW, fallback=8.0) == pytest.approx(2.00)


def test_window_rolls_off_after_24h():
    led = Ledger()
    finished(led, REPO, hrs(24.5), 2.00)
    finished(led, REPO, hrs(23.5), 0.25)
    assert spend.used_24h(led, now=NOW, fallback=8.0) == pytest.approx(0.25)
    assert spend.used_24h(led, now=NOW + dt.timedelta(hours=1), fallback=8.0) == 0.0


def test_unknown_cost_counts_at_its_cap():
    led = Ledger()
    finished(led, REPO, hrs(1), None, budget=5.0, conclusion="failure")
    finished(led, REPO, hrs(1), None, budget=3.0, conclusion="timed_out")
    assert spend.used_24h(led, now=NOW, fallback=8.0) == pytest.approx(8.0)


def test_unknown_cost_with_no_recorded_cap_counts_at_the_fallback():
    led = Ledger()
    finished(led, REPO, hrs(1), None, budget=None)  # a row from before the ledger recorded caps
    assert spend.used_24h(led, now=NOW, fallback=8.0) == pytest.approx(8.0)


def test_in_flight_counts_at_its_cap_even_if_older_than_the_window():
    led = Ledger()
    led.start(REPO, 1, now=hrs(1), budget_usd=3.0)
    led.start(OTHER, 2, now=hrs(30), budget_usd=5.0)
    assert spend.used_24h(led, now=NOW, fallback=8.0) == pytest.approx(8.0)


def test_runs_that_never_reached_the_model_cost_nothing():
    led = Ledger()
    finished(led, REPO, hrs(1), None, conclusion="skipped")
    finished(led, REPO, hrs(1), None, conclusion="cancelled")
    assert spend.used_24h(led, now=NOW, fallback=8.0) == 0.0


def test_ledger_records_the_cap_and_upgrades_an_old_file(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("create table runs (id integer primary key autoincrement, repo text not null, issue integer not null, "
               "hard integer not null default 0, created_at text not null, finished_at text, "
               "status text not null default 'in_progress', conclusion text, model text, turns integer)")
    db.commit()
    db.close()
    led = Ledger(str(path))
    led.start(REPO, 1, now=hrs(1), budget_usd=2.5)
    assert led.db.execute("select budget_usd from runs").fetchone()[0] == 2.5


def test_executor_records_the_action_budget_on_the_ledger_row():
    led = Ledger()
    d = ex.Deps(lambda r, s: None, lambda c, r: (True, ""), lambda c: (True, ""),
                lambda repo, issue, rid: ex.IssueResult(True, pr_number=5, turns=1, model="sonnet"))
    ex.execute(lambda *a, **k: {}, led, d, [Action("run-agent", REPO, "4", "model=sonnet budget=2.50")],
               contexts={}, head_refs={}, dry_run=False)
    assert led.db.execute("select budget_usd from runs").fetchone()[0] == 2.5


# --- the planner ---


def test_planner_absent_key_keeps_todays_behaviour(policy):
    policy()
    r = planner.plan(busy(), Ledger(), {REPO: META}, now=NOW)
    assert agent_kinds(r) == [(REPO, "run-agent")]
    assert "global spend ceiling" not in r[REPO]["note"]


def test_planner_invalid_key_holds_every_agent_run_but_not_checks(policy):
    policy("  global_usd_per_day: -5\n")
    r = planner.plan(busy(), Ledger(), {REPO: META}, now=NOW)
    assert agent_kinds(r) == []
    assert [a.kind for a in r[REPO]["actions"]] == ["check-pr"]
    assert "global_usd_per_day" in r[REPO]["note"] and "fail closed" in r[REPO]["note"]


def test_planner_under_the_ceiling_runs(policy):
    policy("  global_usd_per_day: 12.00\n")
    led = Ledger()
    finished(led, OTHER, hrs(2), 8.99)
    assert agent_kinds(planner.plan(busy(), led, {REPO: META}, now=NOW)) == [(REPO, "run-agent")]  # 8.99 + 3.00 <= 12


def test_planner_over_the_ceiling_holds_runs_with_a_clear_note(policy):
    policy("  global_usd_per_day: 12.00\n")
    led = Ledger()
    finished(led, OTHER, hrs(2), 9.01)
    r = planner.plan(busy(), led, {REPO: META}, now=NOW)
    assert agent_kinds(r) == []
    assert [a.kind for a in r[REPO]["actions"]] == ["check-pr"]
    assert "global spend ceiling: $9.01 of $12.00 used in 24h" in r[REPO]["note"]


def test_planner_counts_runs_planned_earlier_in_the_same_pass(policy):
    policy("  global_usd_per_day: 5.00\n")
    r = planner.plan(busy(), Ledger(), {REPO: META, OTHER: META}, now=NOW)
    assert agent_kinds(r) == [(REPO, "run-agent")]  # 3 fits, 3 + 3 does not
    assert "global spend ceiling: $0.00 of $5.00 used in 24h" in r[OTHER]["note"]


def test_planner_holds_ci_fixes_too(policy):
    policy("  global_usd_per_day: 1.00\n")
    f = Fake(open=[pr(1, "agent/4-x", "s1")],
             checks={"s1": [{"name": n, "status": "completed", "conclusion": c, "app": {"slug": planner.APX_APP_SLUG}}
                            for n, c in (("guard / guard", "success"), ("build", "failure"))]})
    r = planner.plan(f, Ledger(), {REPO: {**META, "ci_contexts": ["build"]}}, now=NOW)
    assert agent_kinds(r) == []


def test_usage_line_reports_the_24h_total_and_ceiling(policy):
    led = Ledger()
    finished(led, REPO, hrs(1), 1.25)
    policy()
    assert spend.spend_line(led, now=NOW) == "all repos: spend last 24h $1.25 (global_usd_per_day not set)"
    policy("  global_usd_per_day: 12\n")
    assert spend.spend_line(led, now=NOW) == "all repos: spend last 24h $1.25 of $12.00 ceiling"
    policy("  global_usd_per_day: nope\n")
    assert "fail closed" in spend.spend_line(led, now=NOW)


def test_daemon_logs_the_spend_line_once_and_a_broken_meter_never_breaks_a_pass(policy):
    from autopilot.apx import daemon

    policy()
    assert daemon.spend_lines(Ledger()) == ["all repos: spend last 24h $0.00 (global_usd_per_day not set)"]
    assert daemon.spend_lines(None)[0].startswith("spend meter unavailable")  # type: ignore[arg-type]
