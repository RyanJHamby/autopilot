"""#291: a private repo apx runs from repo_ci.json (APX_PRIVATE_CI) gets its default-branch head checked, and nothing else changes."""

from pathlib import Path

import pytest
from test_apx_planner import NOW, Fake, issue, pr

from autopilot.apx import daemon as dm
from autopilot.apx import executor as ex
from autopilot.apx import planner, repo_ci
from autopilot.apx.ledger import Ledger

PRIV = "RyanJHamby/admin"
SPEC = repo_ci.parse_spec(
    PRIV,
    {
        "checks": [
            {"context": "ci", "steps": ["make check"]},
            {"context": "guardrails", "steps": ["make guardrails"]},
        ],
        "tools": ["make"],
    },
)


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setattr(repo_ci, "load_specs", lambda path=repo_ci.SPEC_FILE: {PRIV: SPEC})
    monkeypatch.setattr(planner, "ALLOWED_REPOS", set(planner.ALLOWED_REPOS) | {PRIV})
    return dm.Settings(
        owner="RyanJHamby",
        app_id=1,
        key_path=str(tmp_path / "key"),
        installations={PRIV: 1},
        oauth_file=str(tmp_path / "oauth"),
        kit_repo="RyanJHamby/autopilot",
        kit_ref="main",
        private_ci=frozenset({PRIV}),
        shadow=False,
        agent_user="apx-agent",  # an agent account exists, so only the private_ci rule keeps agents off
    )


def run_plan(settings, **fake):
    return planner.plan(Fake(**fake), Ledger(), dm.plan_repos(settings), now=NOW)[PRIV]


def main_actions(result):
    return [(a.kind, a.ref, a.detail) for a in result["actions"] if a.kind == "check-main"]


def apx_run(name, conclusion="success"):
    return {"name": name, "conclusion": conclusion, "status": "completed", "app": {"slug": "autopilot-apx"}}


def test_an_unchecked_main_head_gets_one_check_main_per_context(settings):
    r = run_plan(settings)
    got = main_actions(r)
    assert [(k, ref) for k, ref, _ in got] == [("check-main", "msha")] * 2
    assert [d.partition(planner.MAIN_CTX_SEP)[2] for _, _, d in got] == ["ci", "guardrails"]


def test_an_already_checked_head_gets_no_check_main(settings):
    r = run_plan(settings, checks={"msha": [apx_run("ci"), apx_run("guardrails")]})
    assert main_actions(r) == []


def test_only_the_context_without_a_run_is_planned_and_a_red_one_is_reported(settings):
    r = run_plan(settings, checks={"msha": [apx_run("ci", "failure")]})
    assert [d.partition(planner.MAIN_CTX_SEP)[2] for _, _, d in main_actions(r)] == ["guardrails"]
    assert "main is red: ci" in r["note"]


def test_a_spec_repo_never_gets_agent_or_merge_actions_even_with_work_waiting(settings):
    meta = dm.plan_repos(settings)[PRIV]
    assert (meta["loop"], meta["merge"], meta["agents"]) == (False, False, False)
    r = run_plan(settings, open=[pr(1, "agent/5-1", "s1", repo=PRIV)], issues=[issue(4)])
    kinds = {a.kind for a in r["actions"]}
    assert kinds <= {"check-pr", "check-main"} and "check-main" in kinds
    # a red main changes nothing for these repos either
    r = run_plan(settings, issues=[issue(4)], checks={"msha": [apx_run("ci", "failure")]})
    assert {a.kind for a in r["actions"]} <= {"check-pr", "check-main"}


# --- executor: the existing spec lane, narrowed to the context the action names ---


class RecApi:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {}

    def checks(self):
        return [(c[2]["name"], c[2].get("status"), c[2].get("conclusion")) for c in self.calls if c[1].endswith("/check-runs")]


def test_check_main_on_a_spec_repo_runs_only_the_named_context_through_the_spec_lane(settings):
    ran = []

    def ci_checks(co, checks):
        ran.append([c["context"] for c in checks])
        return {c["context"]: (c["context"] == "ci", "out") for c in checks}

    d = ex.Deps(lambda repo, sha: Path("/x"), lambda *a: (True, ""), lambda co: (True, ""), lambda *a: None, ci_checks=ci_checks)
    api = RecApi()
    ctx = dm.check_contexts(settings)
    acts = [
        planner.Action("check-main", PRIV, "m" * 40, f"main head not yet checked{planner.MAIN_CTX_SEP}{c}")
        for c in ("ci", "guardrails")
    ]
    log = ex.execute(api, Ledger(), d, acts, contexts=ctx, head_refs={}, dry_run=False, private_repos=frozenset({PRIV}))
    assert ran == [["ci"], ["guardrails"]]
    assert api.checks() == [
        ("ci", "in_progress", None),
        ("ci", "completed", "success"),
        ("guardrails", "in_progress", None),
        ("guardrails", "completed", "failure"),
    ]
    assert "green" in log[0] and "failed (main is red)" in log[1]
