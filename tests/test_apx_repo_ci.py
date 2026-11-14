"""apx runs the CI of the private repos (admin, control, pawl, agent-kit) because hosted Actions is off, and posts the check names
their branch protection already requires. The per-repo spec is DATA (src/autopilot/apx/repo_ci.json), not code."""

from pathlib import Path

import pytest
from test_apx_daemon import REPO, env

from autopilot.apx import cilane, planner, repo_ci, sandbox_job
from autopilot.apx import daemon as dm
from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

ADMIN, CONTROL, PAWL, KIT = (f"RyanJHamby/{r}" for r in ("admin", "control", "pawl", "agent-kit"))
ROOT = Path(__file__).resolve().parent.parent


def specs():
    return repo_ci.load_specs()


def test_settings_opt_in_validation(tmp_path):
    inst = f"{REPO}=11,{ADMIN}=12,{PAWL}=13"
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=REPO + "=11"))
    assert s.private_ci == frozenset()  # nothing runs for them until the owner opts in
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, APX_PRIVATE_CI=f"{ADMIN},{PAWL}"))
    assert s.private_ci == {ADMIN, PAWL}
    assert [c.context for c in s.private_checks(ADMIN)] == ["ci"]
    assert s.private_checks(REPO) == ()
    assert not s.full_loop(ADMIN) and not s.agents_allowed(ADMIN)  # checks only, even once shadow mode is off
    off = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, APX_PRIVATE_CI=f"{ADMIN},{PAWL}", APX_SHADOW="0"))
    assert not off.full_loop(ADMIN) and off.full_loop(REPO)
    for bad in (
        {"APX_PRIVATE_CI": CONTROL},  # not installed
        {"APX_PRIVATE_CI": REPO},  # installed but has no spec
        {"APX_PRIVATE_CI": "RyanJHamby/resume"},
    ):
        with pytest.raises(dm.ConfigError):
            dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, **bad))
    with pytest.raises(dm.ConfigError):  # installed in the App but not opted in: it would have no check names to post
        dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst))
    with pytest.raises(dm.ConfigError):  # an installed private repo that is not in scope at all
        dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=f"{REPO}=11,RyanJHamby/resume=9"))


def test_planner_input_for_a_private_repo_is_checks_only(tmp_path):
    inst = f"{REPO}=11,{ADMIN}=12,{CONTROL}=13"
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, APX_PRIVATE_CI=f"{ADMIN},{CONTROL}", APX_SHADOW="0"))
    meta = dm.plan_repos(s)
    assert meta[ADMIN]["contexts"] == ["ci"] and meta[CONTROL]["contexts"] == ["check", "plan-coverage"]
    for r in (ADMIN, CONTROL):
        assert meta[r]["loop"] is False and meta[r]["merge"] is False and meta[r]["agents"] is False
        assert meta[r]["main_check"] is False and meta[r]["spec_ci"] is True
    assert meta[REPO]["contexts"] == ["guard / guard", "build"] and "spec_ci" not in meta[REPO]
    ctx = dm.check_contexts(s)
    assert ctx[ADMIN]["checks"][0]["context"] == "ci" and ctx[REPO] == {"guard": "guard / guard", "ci": "build"}


def test_private_repo_is_in_planner_scope_only_when_it_has_a_spec():
    assert {ADMIN, CONTROL, PAWL, KIT} <= planner.ALLOWED_REPOS


class Api:
    def __init__(self, variables=None):
        self.calls, self.variables = [], variables or {}

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if "/actions/variables/" in path:
            name = path.rsplit("/", 1)[1]
            if name not in self.variables:
                raise planner.GitHubError(404, "nope", "nope")
            return {"value": self.variables[name]}
        return {}

    def checks(self):
        return [(c[2]["name"], c[2].get("status"), c[2].get("conclusion")) for c in self.calls if c[1].endswith("/check-runs")]


def test_private_repo_needs_no_actions_variable_but_still_honours_pause():
    assert planner.enabled(Api(), ADMIN, opted_in=True) == (True, "ok")
    ok, why = planner.enabled(Api({"AUTOPILOT_PAUSED": "true"}), ADMIN, opted_in=True)
    assert not ok and "PAUSED" in why
    assert not planner.enabled(Api(), ADMIN)[0]  # the old rule for every other repo is unchanged


def checks_for(repo):
    return [{"context": c.context, "steps": [list(x) for x in c.steps]} for c in specs()[repo].checks]


def spec_deps(results=None, checkout_err=False, ci_err=False):
    calls = []

    def checkout(repo, sha):
        calls.append("checkout")
        if checkout_err:
            raise OSError("disk")
        return Path("/x")

    def guard(co, ref):
        calls.append("guard")
        return True, ""

    def ci(co):
        calls.append("ci")
        return True, ""

    def ci_checks(co, checks):
        calls.append("ci_checks")
        if ci_err:
            raise RuntimeError("boom")
        return {c["context"]: (results or {}).get(c["context"], (True, "- PASS")) for c in checks}

    d = ex.Deps(checkout, guard, ci, lambda *a: None, ci_checks=ci_checks)
    d.calls = calls  # type: ignore[attr-defined]
    return d


def pr_action(repo):
    return Action("check-pr", repo, "a" * 40, "PR #3")


def run(repo, d, api=None, gate=None):
    api = api or Api()
    log = ex.execute(
        api,
        Ledger(":memory:"),
        d,
        [pr_action(repo)],
        contexts={repo: {"checks": checks_for(repo)}},
        head_refs={(repo, "a" * 40): "agent/x"},
        dry_run=False,
        private_repos=frozenset({repo}),
        gate=gate,
    )
    return api, log


def test_posts_exactly_the_required_names_pending_then_completed_and_never_runs_guard():
    d = spec_deps()
    api, log = run(CONTROL, d)
    assert api.checks() == [
        ("check", "in_progress", None),
        ("plan-coverage", "in_progress", None),
        ("check", "completed", "success"),
        ("plan-coverage", "completed", "success"),
    ]
    assert d.calls == ["checkout", "ci_checks"]  # no guard kit on a repo that has no repo.yaml
    assert "success" in log[0] or "True" in log[0]


def test_one_failing_check_fails_only_its_own_context():
    api, _ = run(CONTROL, spec_deps({"plan-coverage": (False, "- FAIL x")}))
    assert ("check", "completed", "success") in api.checks() and ("plan-coverage", "completed", "failure") in api.checks()


@pytest.mark.parametrize("kw", [{"checkout_err": True}, {"ci_err": True}])
def test_a_crashed_lane_still_completes_every_context_as_failure(kw):
    api, _ = run(CONTROL, spec_deps(**kw))
    done = [c for c in api.checks() if c[1] == "completed"]
    assert sorted(done) == [("check", "completed", "failure"), ("plan-coverage", "completed", "failure")]


def test_freeze_window_starts_nothing():
    d = spec_deps()
    api, log = run(ADMIN, d, gate=lambda kind: "freeze: work hours")
    assert d.calls == [] and api.calls == []
    assert log[0].startswith("held check-pr") and "freeze" in log[0]


def test_dry_run_touches_nothing():
    api = Api()
    d = spec_deps()
    log = ex.execute(api, Ledger(":memory:"), d, [pr_action(ADMIN)], contexts={}, head_refs={}, dry_run=True)
    assert api.calls == [] and d.calls == [] and log[0].startswith("DRY-RUN")


def test_sandbox_job_in_spec_mode_runs_commands_as_data_with_no_guard(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(sandbox_job.gitops, "checkout_pr", lambda *a, **k: tmp_path)
    monkeypatch.setattr(sandbox_job.gitops, "prune_work", lambda *a, **k: None)

    def boom(*a, **k):
        raise AssertionError("guard must not run")

    monkeypatch.setattr(sandbox_job.guardlane, "run_guard", boom)

    def fake_run(co, cmds, **k):
        seen.append(cmds)
        return [cilane.CmdResult(c if isinstance(c, str) else c[0], True, 0.1, "") for c in cmds]

    monkeypatch.setattr(sandbox_job.cilane, "run_commands", fake_run)
    req = {
        "mode": "checks",
        "repo": ADMIN,
        "sha": "a" * 40,
        "base_branch": "main",
        "work_root": str(tmp_path / "w"),
        "checks": checks_for(ADMIN),
    }
    out = sandbox_job.run_job(req, None)
    assert out["checks"]["ci"][0] is True and "guard" not in out
    assert [c for c, _ in seen[0]] == ["gitleaks detect --source . --no-banner --redact", "scripts/ci-test.sh"]


def test_sandbox_job_refuses_an_unsafe_command_in_a_request(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_job.gitops, "checkout_pr", lambda *a, **k: tmp_path)
    monkeypatch.setattr(sandbox_job.gitops, "prune_work", lambda *a, **k: None)
    req = {"mode": "checks", "repo": ADMIN, "sha": "a" * 40, "base_branch": "main", "work_root": str(tmp_path / "w"),
           "checks": [{"context": "ci", "steps": [["curl x | sh", ""]]}]}  # fmt: skip
    with pytest.raises(ValueError):
        sandbox_job.run_job(req, None)


def test_the_allowed_set_is_read_from_the_ci_spec_not_a_second_list():
    base = {"RyanJHamby/autopilot", "RyanJHamby/drillpad-workspace", "RyanJHamby/stencil"}
    assert planner.ALLOWED_REPOS == base | set(repo_ci.load_specs())
    from autopilot.apx import doctor

    assert doctor.ALLOWED_REPOS is planner.ALLOWED_REPOS  # the doctor's scope checks use that one set
    assert "RyanJHamby/resume" not in planner.ALLOWED_REPOS


def test_apx_app_doc_lists_exactly_the_allowed_repos():
    text = (ROOT / "docs" / "apx-app.md").read_text()
    section = text.split("## 2.")[1].split("## 3.")[0]
    assert "exactly three" not in section
    for repo in planner.ALLOWED_REPOS:
        assert f"`{repo.split('/')[1]}`" in section, repo
