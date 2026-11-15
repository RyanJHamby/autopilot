"""Sprints: a time-boxed run allowance for ONE yolo repo, started only by the owner applying the `sprint` label.

During an active sprint the repo's runs_per_day cap is replaced by the sprint's run count; its per-run cap is the sprint's; its dollar
limit counts the ledger's cost_usd since the sprint started, with an unknown cost charged at the run's cap (spend.py's rule). The
freeze, shadow mode, max_open_agent_prs and global_usd_per_day still apply. Values in repo.yaml can only lower policy's (or the
built-in) limits. When a limit is hit or the window ends, the sprint ends with a summary in the note and the ledger.
"""

import datetime as dt
import sqlite3

import pytest
from test_apx_planner import NOW, REPO, Fake, issue, pr

from autopilot.apx import caps, doctor, planner, sprint
from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger

OWNER = "RyanJHamby"
CAPS = "defaults:\n  max_budget_usd: {standard: 3.00, yolo: 5.00, hard: 8.00, triage: 0.50, reviewer: 1.00}\n"
YOLO = "mode: yolo\ntier: A\n"
META = {"contexts": ["guard / guard", "build"], "agents": True}


@pytest.fixture(autouse=True)
def policy(tmp_path, monkeypatch):
    def write(extra: str = "") -> None:
        p = tmp_path / "portfolio.yaml"
        p.write_text(CAPS + extra)
        monkeypatch.setattr(caps, "PORTFOLIO_FILE", p)

    write()
    return write


def hrs(h):
    return NOW - dt.timedelta(hours=h)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def label_event(at, actor=OWNER, name="sprint"):
    return {"event": "labeled", "label": {"name": name}, "actor": {"login": actor}, "created_at": iso(at)}


class SprintFake(Fake):
    """The planner Fake, plus the open issues/PRs carrying the `sprint` label."""

    def __init__(self, sprint_items=(), **kw):
        super().__init__(**kw)
        self.sprint_items = list(sprint_items)

    def __call__(self, method, path, body=None):
        if method == "GET" and "labels=sprint" in path:
            return self.sprint_items
        return super().__call__(method, path, body)


def sprint_item(n=50, at=None, actor=OWNER):
    """An open issue labelled `sprint` and its events (the label applied `at` by `actor`)."""
    return {"number": n, "labels": [{"name": "sprint"}], "user": {"login": OWNER}}, {n: [label_event(at or hrs(1), actor)]}


def fake(cfg=YOLO, started=None, actor=OWNER, issues=5, **kw):
    items, events = ([], {})
    if started is not False:
        it, events = sprint_item(at=started or hrs(1), actor=actor)
        items = [it]
    return SprintFake(sprint_items=items, events=events, cfg=cfg, issues=[issue(n) for n in range(2, 2 + issues)], **kw)


def done(led, at, cost, budget=2.0, conclusion="success", issue_n=1):
    rid = led.start(REPO, issue_n, now=at, budget_usd=budget)
    led.finish(rid, conclusion, cost_usd=cost, now=at)
    return rid


def plan(f, led, meta=META):
    return planner.plan(f, led, {REPO: dict(meta)}, now=NOW)[REPO]


def runs(r):
    return [a for a in r["actions"] if a.kind in ("run-agent", "fix-ci")]


def two_runs_before_the_sprint():
    led = Ledger()
    done(led, hrs(5), 0.5, budget=5.0)
    done(led, hrs(4), 0.5, budget=5.0)
    return led


# --- the sprint replaces runs_per_day ---


def test_without_a_sprint_the_daily_cap_holds():
    r = plan(fake(started=False), two_runs_before_the_sprint())
    assert runs(r) == [] and "daily run cap" in r["note"]


def test_a_sprint_replaces_runs_per_day_with_its_run_count_and_per_run_cap():
    r = plan(fake(), two_runs_before_the_sprint())
    got = runs(r)
    assert len(got) == 4  # sprint default: 4 runs (and 4 x $2.00 fits $8.00), even though tier A's 2/day is already used
    assert all("budget=2.00" in a.detail for a in got)  # the sprint's per-run cap, below yolo's 5.00
    assert "sprint active" in r["note"]


def test_runs_already_made_in_the_sprint_count_against_it():
    led = Ledger()
    done(led, hrs(0.5), 1.0)
    done(led, hrs(0.4), 1.0)
    done(led, hrs(0.3), 1.0)
    assert len(runs(plan(fake(), led))) == 1


# --- the dollar limit (unknown cost counts at the run's cap) ---


def test_dollar_limit_stops_runs_and_unknown_cost_counts_at_its_cap():
    led = Ledger()
    done(led, hrs(0.5), None, budget=2.0, conclusion="failure")  # no reported cost: charged its 2.00 cap
    done(led, hrs(0.4), 3.5)
    r = plan(fake(), led)  # 5.50 used of 8.00: one more 2.00 run fits, a second does not
    assert len(runs(r)) == 1


def test_dollar_limit_reached_ends_the_sprint_with_no_new_runs():
    led = Ledger()
    done(led, hrs(0.5), None, budget=2.0, conclusion="failure")
    done(led, hrs(0.4), 4.5)  # 6.50 used: 1.50 left, below the 2.00 per-run cap
    r = plan(fake(), led)
    assert runs(r) == []
    assert "sprint ended (dollar limit)" in r["note"] and "2 run(s)" in r["note"] and "$6.50" in r["note"]


def test_in_flight_run_counts_at_its_cap():
    led = Ledger()
    led.start(REPO, 1, now=hrs(0.5), budget_usd=2.0)
    for _ in range(2):
        done(led, hrs(0.4), 2.5)
    r = plan(fake(), led)
    assert runs(r) == [] and "sprint ended (dollar limit)" in r["note"]  # 7.00 committed: no 2.00 run fits


# --- the window ---


def test_window_expiry_stops_new_sprint_runs_and_ends_it():
    led = Ledger()
    for h in (4.5, 4.4, 4.3, 4.2):
        done(led, hrs(h), 0.25)
    r = plan(fake(started=hrs(4.6)), led)  # default window 4h: it closed 0.6h ago
    assert runs(r) == []
    assert "sprint ended (window ended)" in r["note"] and "4 run(s)" in r["note"]


def test_run_limit_ends_the_sprint():
    led = Ledger()
    for h in (0.5, 0.4, 0.3, 0.2):
        done(led, hrs(h), 0.1)
    r = plan(fake(), led)
    assert runs(r) == [] and "sprint ended (run limit)" in r["note"]


# --- what a sprint never bypasses ---


def test_the_global_dollar_ceiling_still_wins(policy):
    policy("  global_usd_per_day: 3.0\n")
    r = plan(fake(), Ledger())
    assert len(runs(r)) == 1 and "global spend ceiling" in r["note"]


def test_the_freeze_still_holds_sprint_runs(tmp_path):
    acts = runs(plan(fake(), Ledger()))
    assert acts
    led = Ledger(str(tmp_path / "l.sqlite"))
    log = ex.execute(lambda *a, **k: {}, led, None, acts, contexts={}, head_refs={}, dry_run=False, gate=lambda kind: "freeze: test")  # type: ignore[arg-type]
    assert all(line.startswith("held run-agent") for line in log)
    assert led.db.execute("select count(*) from runs").fetchone()[0] == 0


def test_shadow_mode_still_means_checks_only():
    r = plan(fake(), Ledger(), meta={"contexts": ["guard / guard", "build"], "agents": False, "loop": False})
    assert runs(r) == [] and r["note"] == "shadow: checks only"


def test_max_open_agent_prs_still_applies():
    f = fake(open=[pr(i, f"agent/{90 + i}-x", f"s{i}") for i in range(3)], checks={f"s{i}": [] for i in range(3)})
    r = plan(f, Ledger())
    assert not [a for a in r["actions"] if a.kind == "run-agent"] and "agent PRs already open" in r["note"]


# --- who can start one ---


def test_a_label_applied_by_someone_else_is_ignored():
    r = plan(fake(actor="stranger"), two_runs_before_the_sprint())
    assert runs(r) == [] and "daily run cap" in r["note"]
    assert "not applied by the owner" in r["note"]


def test_the_latest_label_event_decides():
    it, _ = sprint_item()
    f = fake(started=False)
    f.sprint_items = [it]
    f.events = {50: [label_event(hrs(2)), label_event(hrs(1), actor="stranger")]}
    assert runs(plan(f, two_runs_before_the_sprint())) == []


def test_unreadable_events_mean_no_sprint():
    f = fake()
    f.events = {50: [label_event(hrs(1))] * 100}  # a full page: the latest event may be on the next one
    assert runs(plan(f, two_runs_before_the_sprint())) == []


def test_a_standard_mode_repo_is_refused():
    r = plan(fake(cfg="mode: standard\ntier: A\n"), two_runs_before_the_sprint())
    assert runs(r) == [] and "sprint needs mode: yolo" in r["note"]


# --- limits: repo.yaml lowers, never raises ---


def test_builtin_defaults_without_a_policy_block():
    assert sprint.policy_limits() == sprint.Limits(window_h=4.0, runs=4, usd=8.0, per_run_usd=2.0)


def test_policy_block_sets_the_ceilings(policy):
    policy("  sprint: {window_h: 2, runs: 3, usd: 5.0, per_run_usd: 1.5}\n")
    assert sprint.policy_limits() == sprint.Limits(window_h=2.0, runs=3, usd=5.0, per_run_usd=1.5)


def test_repo_values_cannot_exceed_policy(policy):
    policy("  sprint: {window_h: 2, runs: 3, usd: 5.0, per_run_usd: 1.5}\n")
    lim, note = sprint.limits_for({"sprint": {"window_h": 1, "runs": 10, "usd": 50, "per_run_usd": 1.0}})
    assert lim == sprint.Limits(window_h=1.0, runs=3, usd=5.0, per_run_usd=1.0)
    assert "runs" in note and "usd" in note


def test_repo_values_cannot_exceed_the_builtin_defaults_either():
    lim, _ = sprint.limits_for({"sprint": {"runs": 99, "usd": 999, "window_h": 48}})
    assert lim == sprint.Limits(window_h=4.0, runs=4, usd=8.0, per_run_usd=2.0)


@pytest.mark.parametrize("bad", ["{runs: -1}", "{runs: 1.5}", "{usd: .nan}", "{usd: yes}", "{window_h: 0}", "{nope: 1}", "[1]"])
def test_invalid_repo_values_refuse_the_sprint(bad):
    import yaml

    with pytest.raises(sprint.SprintError):
        sprint.limits_for({"sprint": yaml.safe_load(bad)})


@pytest.mark.parametrize("bad", ["{runs: 0}", "{per_run_usd: 80}", "'x'"])
def test_invalid_policy_refuses_the_sprint_and_normal_caps_apply(policy, bad):
    policy(f"  sprint: {bad}\n")
    r = plan(fake(), two_runs_before_the_sprint())
    assert runs(r) == [] and "sprint refused" in r["note"]


def test_lowered_values_shape_the_plan():
    r = plan(fake(cfg=YOLO + "sprint: {runs: 2, per_run_usd: 1.0}\n"), Ledger())
    got = runs(r)
    assert len(got) == 2 and all("budget=1.00" in a.detail for a in got)


# --- the summary at the end ---


def test_summary_recorded_in_the_ledger_at_end():
    led = Ledger()
    for h in (0.5, 0.4, 0.3, 0.2):
        done(led, hrs(h), 0.5)
    merged = {"number": 7, "head": {"ref": "agent/3-x", "sha": "m"}, "merged_at": iso(hrs(0.1))}
    old = {"number": 6, "head": {"ref": "agent/2-x", "sha": "o"}, "merged_at": iso(hrs(3))}
    f = fake(closed=[merged, old])
    planned = planner.plan(f, led, {REPO: dict(META)}, now=NOW)
    assert "1 merged PR(s)" in planned[REPO]["note"]
    sprint.record(led, planned, NOW)
    row = led.db.execute("select * from sprints").fetchone()
    assert (row["reason"], row["runs"], row["merged"], row["cost_usd"]) == ("run limit", 4, 1, pytest.approx(2.0))
    assert row["ended_at"] is not None


def test_an_ended_sprint_stays_ended_even_if_costs_come_in_lower():
    led = Ledger()
    rid = led.start(REPO, 1, now=hrs(0.5), budget_usd=2.0)
    for _ in range(2):
        done(led, hrs(0.4), 2.9)  # 5.80 + the in-flight 2.00 = 7.80: no 2.00 run fits, ended
    sprint.record(led, planner.plan(fake(), led, {REPO: dict(META)}, now=NOW), NOW)
    led.finish(rid, "success", cost_usd=0.1, now=NOW)  # now only 5.90 is spent, which alone would leave room for one run
    r = plan(fake(), led)
    assert runs(r) == [] and "sprint ended (dollar limit)" in r["note"]


def test_active_sprint_is_recorded_and_removed_label_ends_it():
    led = Ledger()
    sprint.record(led, planner.plan(fake(), led, {REPO: dict(META)}, now=NOW), NOW)
    assert led.db.execute("select ended_at from sprints").fetchone()["ended_at"] is None
    sprint.record(led, planner.plan(fake(started=False), led, {REPO: dict(META)}, now=NOW), NOW)
    assert led.db.execute("select reason from sprints").fetchone()["reason"] == "label removed or replaced"


def test_after_the_window_the_normal_cap_applies_again():
    led = Ledger()
    r = plan(fake(started=hrs(5)), led)
    assert len(runs(r)) == 2  # tier A's normal 2/day, nothing ran in the last 24h


# --- doctor ---


def test_doctor_lists_active_sprints_with_what_is_left(tmp_path):
    path = str(tmp_path / "l.sqlite")
    led = Ledger(path)
    sprint.record(led, planner.plan(fake(), led, {REPO: dict(META)}, now=NOW), NOW)
    done(led, hrs(0.5), 1.25)
    led.db.close()
    c = doctor.sprint_check(path, now=NOW)
    assert c.ok and REPO in c.detail
    assert "3 of 4 runs" in c.detail and "$6.75 of $8.00" in c.detail and "3h00m" in c.detail


def test_doctor_with_no_sprints_or_an_old_ledger(tmp_path):
    path = str(tmp_path / "old.sqlite")
    sqlite3.connect(path).execute("create table runs (id integer)").connection.commit()
    assert doctor.sprint_check(path, now=NOW).detail.startswith("none active")
    assert doctor.sprint_check(str(tmp_path / "missing.sqlite"), now=NOW).ok
