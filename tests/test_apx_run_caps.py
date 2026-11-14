# ruff: noqa: F811  (pytest fixtures imported from test_apx_daemon are used as parameters)
"""Every apx agent run carries BOTH caps, --max-turns and --max-budget-usd, and its record keeps what the CLI says it cost.

The dollar caps are policy/portfolio.yaml `defaults.max_budget_usd`, per role (same keys as `max_turns`). They are placeholders for
the owner to confirm. A run with no resolvable cap does not start. `--max-budget-usd` is checked by the CLI between turns, so it can
overshoot; `--max-turns` stays the hard stop.
"""

import json
import math
import sys
from pathlib import Path

import pytest
import yaml
from runner import Task
from test_apx_daemon import REPO, Api, env, fake_claude, mac_homes, remote  # noqa: F401

from autopilot.apx import agent_job
from autopilot.apx import claude_runner as cr
from autopilot.apx import daemon as dm
from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO = ROOT / "policy" / "portfolio.yaml"


def caps():
    from autopilot.apx import caps as c  # imported lazily so a missing module fails these tests, not collection

    return c


def argv(**over):
    kw = dict(model="sonnet", effort="medium", max_turns=40, max_budget_usd=3.0, tools=["Read"])
    kw.update(over)
    return cr.build_argv("claude", "P", **kw)


def flag(a, name):
    return a[a.index(name) + 1]


# ---- argv -------------------------------------------------------------------------------------------------------------------


def test_argv_has_both_caps_and_json_output():
    a = argv()
    assert flag(a, "--max-turns") == "40" and flag(a, "--max-budget-usd") == "3.00" and flag(a, "--output-format") == "json"


def test_a_budget_cannot_be_left_out():
    with pytest.raises(TypeError):
        cr.build_argv("claude", "P", model="sonnet", effort="medium", max_turns=40, tools=[])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        cr.ClaudeRunner("t", home=Path("/tmp"), commands=[], prompt="P")  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", [0, 0.0, -1, -0.01, math.nan, math.inf, True, False, "3", "abc", None, [3], 1e6])
def test_a_budget_that_is_not_a_sane_positive_number_is_refused(bad):
    with pytest.raises(ValueError):
        argv(max_budget_usd=bad)


@pytest.mark.parametrize("bad", [0, -3, True, "x", None, 10_000])
def test_turns_are_checked_too(bad):
    with pytest.raises(ValueError):
        argv(max_turns=bad)


def test_budget_is_formatted_to_cents_without_exponent():
    assert flag(argv(max_budget_usd=0.5), "--max-budget-usd") == "0.50"
    assert flag(argv(max_budget_usd=2), "--max-budget-usd") == "2.00"
    assert flag(argv(max_budget_usd=0.004), "--max-budget-usd") == "0.01"  # never rounds a positive cap down to zero


# ---- reading the CLI's answer -----------------------------------------------------------------------------------------------


def run_with(tmp_path, out_json, rc=0, **kw):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    binary = fake_claude(tmp_path, f"print({out_json!r})\nsys.exit({rc})")
    wt = tmp_path / "wt"
    wt.mkdir(exist_ok=True)
    r = cr.ClaudeRunner("tok", home=home, commands=["pytest -q"], prompt="P", binary=binary, max_budget_usd=kw.pop("budget", 2.5))
    return r.run(Task(issue=1, prompt="", model="sonnet", max_turns=7), wt)


def test_the_runner_passes_both_caps_to_the_process(tmp_path):
    seen = tmp_path / "argv.json"
    binary = fake_claude(tmp_path, f'json.dump(sys.argv[1:], open({str(seen)!r}, "w"))\nprint(json.dumps({{"result": "ok"}}))')
    home = tmp_path / "h"
    home.mkdir()
    cr.ClaudeRunner("t", home=home, commands=[], prompt="P", binary=binary, max_budget_usd=2.5).run(
        Task(issue=1, prompt="", model="sonnet", max_turns=7), tmp_path
    )
    a = json.loads(seen.read_text())
    assert flag(a, "--max-turns") == "7" and flag(a, "--max-budget-usd") == "2.50"


def test_cost_and_the_resolved_model_id_come_from_the_json(tmp_path):
    out = json.dumps(
        {
            "result": "done",
            "num_turns": 4,
            "total_cost_usd": 0.4321,
            "modelUsage": {"claude-sonnet-X": {"costUSD": 0.40}, "claude-haiku-Y": {"costUSD": 0.0321}},
        }
    )
    res = run_with(tmp_path, out)
    assert res.usage.turns == 4 and res.usage.cost_usd == pytest.approx(0.4321)
    assert res.usage.model_id == "claude-sonnet-X"  # the model that did most of the work, not the alias that was asked for


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"modelUsage": {}},
        {"modelUsage": None},
        {"modelUsage": "nope"},
        {"modelUsage": {"": {"costUSD": 1}}},
        {"modelUsage": {"m": "x"}},
    ],
)
def test_a_missing_or_odd_model_usage_gives_no_model_id_and_never_a_crash(tmp_path, extra):
    res = run_with(tmp_path, json.dumps({"result": "r", "num_turns": 1, **extra}))
    assert res.usage.model_id is None and res.usage.turns == 1


@pytest.mark.parametrize("bad", [None, "1.5", -1, True, "nan", [1]])
def test_a_cost_that_is_not_a_plain_non_negative_number_is_recorded_as_unknown(tmp_path, bad):
    res = run_with(tmp_path, json.dumps({"result": "r", "total_cost_usd": bad}))
    assert res.usage.cost_usd is None


def test_a_zero_cost_is_recorded_as_zero_not_unknown(tmp_path):
    assert run_with(tmp_path, json.dumps({"result": "r", "total_cost_usd": 0})).usage.cost_usd == 0.0


def test_a_run_that_stops_on_its_cap_still_reports_what_it_spent(tmp_path):
    out = json.dumps(
        {
            "is_error": True,
            "subtype": "error_max_budget_usd",
            "result": "budget",
            "num_turns": 6,
            "total_cost_usd": 3.07,
            "modelUsage": {"claude-sonnet-X": {"costUSD": 3.07}},
        }
    )
    with pytest.raises(cr.RunnerError) as e:
        run_with(tmp_path, out)
    u = e.value.usage
    assert u.cost_usd == pytest.approx(3.07) and u.model_id == "claude-sonnet-X" and u.turns == 6
    assert "budget" in str(e.value)


# ---- where the caps come from -----------------------------------------------------------------------------------------------


def test_portfolio_has_a_budget_for_every_role_that_has_a_turn_cap_and_says_they_are_placeholders():
    text = PORTFOLIO.read_text()
    d = yaml.safe_load(text)["defaults"]
    assert set(d["max_budget_usd"]) == set(d["max_turns"])
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 50 for v in d["max_budget_usd"].values())
    before = text.split("max_budget_usd:")[0][-600:]
    assert "PLACEHOLDER" in before and "owner" in before.lower()


def test_budget_for_reads_the_portfolio_defaults():
    c = caps()
    d = yaml.safe_load(PORTFOLIO.read_text())["defaults"]["max_budget_usd"]
    for role, usd in d.items():
        assert c.budget_for(role) == pytest.approx(usd)


def test_an_unknown_role_or_unreadable_policy_means_no_cap_so_no_run(tmp_path, monkeypatch):
    c = caps()
    with pytest.raises(c.CapError):
        c.budget_for("nonsense")
    for text in ("", "{{{ bad", "- a\n", "defaults: {}\n", "defaults: {max_budget_usd: {standard: 0}}\n",
                 "defaults: {max_budget_usd: {standard: yes}}\n", "defaults: {max_budget_usd: {standard: .inf}}\n",
                 "defaults: {max_budget_usd: {standard: 99999}}\n"):
        p = tmp_path / "p.yaml"
        p.write_text(text)
        monkeypatch.setattr(c, "PORTFOLIO_FILE", p)
        with pytest.raises(c.CapError):
            c.budget_for("standard")
    monkeypatch.setattr(c, "PORTFOLIO_FILE", tmp_path / "missing.yaml")
    with pytest.raises(c.CapError):
        c.budget_for("standard")


def test_cap_error_is_a_value_error_so_the_planner_fails_closed_on_it():
    assert issubclass(caps().CapError, ValueError)


# ---- planner and detail -----------------------------------------------------------------------------------------------------


def test_a_dry_run_pass_plans_agent_runs_with_the_standard_budget(tmp_path, monkeypatch):
    from test_apx_daemon import _gate_factory

    monkeypatch.delenv("APX_LIVE", raising=False)
    s = dm.Settings.from_env(env(tmp_path, APX_SHADOW="0", APX_AGENT_USER="apx-agent"))
    out = dm.run_once(s, api_factory=_gate_factory())
    line = next(x for x in out if x.startswith("DRY-RUN run-agent"))
    assert f"turns=40 budget={caps().budget_for('standard'):.2f}" in line


def test_parse_detail_reads_the_budget_and_falls_back_to_the_standard_cap_never_to_none():
    c = caps()
    assert dm.parse_detail("model=sonnet effort=low turns=10 budget=1.25")["budget"] == 1.25
    assert dm.parse_detail("model=sonnet effort=low turns=10")["budget"] == c.budget_for("standard")
    for bad in ("0", "-1", "nan", "inf", "x", "", "1e9"):
        with pytest.raises(ValueError):
            dm.parse_detail(f"model=sonnet effort=low turns=10 budget={bad}")


def test_a_later_budget_token_cannot_raise_an_earlier_one():
    """A fix-ci detail is the PR text plus the run detail; two budget= tokens must resolve to the lower, not the last."""
    assert dm.parse_detail("budget=5.00 model=sonnet turns=10 budget=1.00")["budget"] == 1.0
    assert dm.parse_detail("budget=1.00 model=sonnet turns=10 budget=5.00")["budget"] == 1.0


# ---- work_on_issue / fix_pr hand the caps to the process --------------------------------------------------------------------


def test_work_on_issue_without_an_agent_account_passes_both_caps_and_returns_cost_and_model(tmp_path):
    rem, sha = remote(tmp_path)
    s = dm.Settings.from_env(env(tmp_path))
    seen = tmp_path / "argv.json"
    b = fake_claude(
        tmp_path,
        f"""
        json.dump(sys.argv[1:], open({str(seen)!r}, "w"))
        open("feature.py", "w").write("x = 1\\n")
        print(json.dumps({{"result": "added", "num_turns": 3, "total_cost_usd": 0.31, "modelUsage": {{"claude-sonnet-X": {{"costUSD": 0.31}}}}}}))
        """,
    )
    r = dm.work_on_issue(s, Api(sha), lambda repo: None, REPO, 4, 99, "model=sonnet effort=low turns=10 budget=1.50", binary=b, url=str(rem))
    a = json.loads(seen.read_text())
    assert flag(a, "--max-turns") == "10" and flag(a, "--max-budget-usd") == "1.50"
    assert r.ok and r.cost_usd == pytest.approx(0.31) and r.model_id == "claude-sonnet-X"


def test_a_run_that_hit_its_budget_is_a_failed_run_that_still_records_the_cost(tmp_path):
    rem, sha = remote(tmp_path)
    s = dm.Settings.from_env(env(tmp_path))
    b = fake_claude(
        tmp_path,
        """
        print(json.dumps({"is_error": True, "subtype": "error_max_budget_usd", "result": "b", "num_turns": 2, "total_cost_usd": 1.62,
                          "modelUsage": {"claude-sonnet-X": {"costUSD": 1.62}}}))
        """,
    )
    r = dm.work_on_issue(s, Api(sha), lambda repo: None, REPO, 4, 98, "model=sonnet effort=low turns=10 budget=1.50", binary=b, url=str(rem))
    assert not r.ok and r.cost_usd == pytest.approx(1.62) and r.model_id == "claude-sonnet-X" and r.turns == 2


def _sandbox_run_capturing(store, res=None):
    def run(req, tok):
        store.append(req)
        return (res or {"ok": False, "error": "stop here", "turns": 3, "cost_usd": 0.5, "model_id": "claude-opus-Z"}), []

    return run


def test_the_agent_account_request_carries_both_caps_and_its_cost_comes_back(tmp_path, mac_homes):
    s = dm.Settings.from_env(env(tmp_path, APX_AGENT_USER="apx-agent"))
    seen = []
    r = dm.work_on_issue(
        s, Api("a" * 40), lambda repo: None, REPO, 4, 1, "model=sonnet effort=low turns=12 budget=2.00",
        read_token_for=lambda repo: "RO", run_agent=_sandbox_run_capturing(seen),
    )
    assert seen[0]["max_turns"] == 12 and seen[0]["max_budget_usd"] == 2.0
    assert not r.ok and r.cost_usd == 0.5 and r.model_id == "claude-opus-Z" and r.turns == 3


def test_fix_pr_request_carries_both_caps_too(tmp_path, mac_homes):
    import test_apx_fix_ci as fx

    s = dm.Settings.from_env(env(tmp_path, APX_AGENT_USER="apx-agent"))
    seen = []
    r = dm.fix_pr(
        s, fx.Api(), REPO, 4, 7, fx.HEAD, "model=sonnet effort=low turns=9 budget=0.75", ["build"],
        read_token_for=lambda repo: "RO", run_agent=_sandbox_run_capturing(seen),
    )
    assert seen[0]["max_turns"] == 9 and seen[0]["max_budget_usd"] == 0.75 and r.cost_usd == 0.5 and r.model_id == "claude-opus-Z"


# ---- the sandboxed job ------------------------------------------------------------------------------------------------------


def job_req(tmp_path, binary, **over):
    import test_apx_agent as ta

    rem, sha = ta.make_remote(tmp_path)
    req = {
        "repo": REPO, "base_sha": sha, "base_branch": "main", "issue": 4, "prompt": "P", "model": "sonnet", "effort": "low",
        "max_turns": 10, "max_budget_usd": 2.0, "commands": [], "work_root": str(tmp_path / "work"), "binary": binary,
        "url": str(rem), "oauth_file": str(tmp_path / "oauth"),
    }
    (tmp_path / "oauth").write_text("tok\n")
    req.update(over)
    return req


def test_the_job_returns_cost_and_model_id_for_a_good_run(tmp_path):
    b = fake_claude(
        tmp_path,
        """
        open("new.py", "w").write("x = 1\\n")
        print(json.dumps({"result": "ok", "num_turns": 2, "total_cost_usd": 0.2, "modelUsage": {"claude-sonnet-X": {"costUSD": 0.2}}}))
        """,
    )
    out = agent_job.run_agent(job_req(tmp_path, b), None)
    assert out["ok"] and out["cost_usd"] == pytest.approx(0.2) and out["model_id"] == "claude-sonnet-X"


def test_the_job_refuses_a_request_with_no_budget(tmp_path):
    b = fake_claude(tmp_path, 'print(json.dumps({"result": "ok"}))')
    req = job_req(tmp_path, b)
    del req["max_budget_usd"]
    with pytest.raises(KeyError):
        agent_job.run_agent(req, None)


def test_the_job_reports_cost_even_when_the_run_errors(tmp_path, monkeypatch, capsys):
    b = fake_claude(
        tmp_path,
        'print(json.dumps({"is_error": True, "result": "b", "num_turns": 2, "total_cost_usd": 2.1, "modelUsage": {"claude-sonnet-X": {"costUSD": 2.1}}}))',
    )
    req = job_req(tmp_path, b)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(req)))
    assert agent_job.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert "error" in out and out["cost_usd"] == pytest.approx(2.1) and out["model_id"] == "claude-sonnet-X" and out["turns"] == 2


# ---- the run record ---------------------------------------------------------------------------------------------------------


def make_deps(result):
    def work(repo, issue, run_id):
        if isinstance(result, Exception):
            raise result
        return result

    return ex.Deps(checkout=lambda r, s: None, guard=lambda c, h: (True, ""), ci=lambda c: (True, ""), work_on_issue=work,
                   fix_ci=lambda *a: result)


def row(led, run_id=1):
    return dict(led.db.execute("select model, model_id, cost_usd, turns, conclusion from runs where id=?", (run_id,)).fetchone())


def test_the_ledger_row_keeps_the_resolved_model_id_and_total_cost(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"))
    res = ex.IssueResult(True, "s", pr_number=5, turns=4, model="sonnet", model_id="claude-sonnet-X", cost_usd=0.42)
    assert ex.run_agent(lambda *a, **k: {}, led, make_deps(res), Action("run-agent", REPO, "4", "")) == "success"
    assert row(led) == {"model": "sonnet", "model_id": "claude-sonnet-X", "cost_usd": 0.42, "turns": 4, "conclusion": "success"}


def test_a_failed_run_keeps_its_cost_too(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"))
    res = ex.IssueResult(False, "s", problems="b", turns=2, model="sonnet", model_id="claude-sonnet-X", cost_usd=1.62)
    assert ex.run_agent(lambda *a, **k: {}, led, make_deps(res), Action("run-agent", REPO, "4", "")) == "failure"
    assert row(led)["cost_usd"] == 1.62 and row(led)["conclusion"] == "failure"


def test_a_run_with_no_reported_cost_is_null_not_zero(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"))
    ex.run_agent(lambda *a, **k: {}, led, make_deps(ex.IssueResult(True, "s", pr_number=5)), Action("run-agent", REPO, "4", ""))
    assert row(led)["cost_usd"] is None and row(led)["model_id"] is None


def test_a_fix_run_records_them_too(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"))
    sha = "a" * 40
    import test_apx_fix_ci as fx

    api = fx.Api(sha=sha)
    res = ex.IssueResult(True, "s", pr_number=7, turns=3, model="sonnet", model_id="claude-sonnet-X", cost_usd=0.1)
    out = ex.run_fix(api, led, make_deps(res), Action("fix-ci", REPO, f"7:{sha}", "x"))
    assert out == "success" and row(led)["cost_usd"] == 0.1 and row(led)["model_id"] == "claude-sonnet-X"


def test_an_old_ledger_file_is_upgraded_in_place(tmp_path):
    import sqlite3

    p = tmp_path / "old.sqlite"
    db = sqlite3.connect(p)
    db.execute("create table runs (id integer primary key autoincrement, repo text not null, issue integer not null, hard integer not null default 0, "
               "created_at text not null, finished_at text, status text not null default 'in_progress', conclusion text, model text, turns integer)")
    db.execute("insert into runs (repo, issue, created_at) values ('r', 1, '2026-01-01T00:00:00Z')")
    db.commit()
    db.close()
    led = Ledger(str(p))
    cols = {r["name"] for r in led.db.execute("pragma table_info(runs)")}
    assert {"model_id", "cost_usd"} <= cols
    led.finish(1, "success", model="sonnet", model_id="m", cost_usd=0.5)
    assert row(led, 1)["cost_usd"] == 0.5


def test_finish_without_the_new_fields_still_works_for_old_callers(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"))
    rid = led.start(REPO, 4)
    led.finish(rid, "failure", model="sonnet", turns=1)
    assert row(led, rid)["cost_usd"] is None
