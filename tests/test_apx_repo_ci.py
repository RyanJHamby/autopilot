"""apx runs the CI of the private repos (admin, control, pawl, agent-kit) because hosted Actions is off, and posts the check names
their branch protection already requires. The per-repo spec is DATA (src/autopilot/apx/repo_ci.json), not code."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from test_apx_daemon import REPO, env

from autopilot.apx import cilane
from autopilot.apx import daemon as dm
from autopilot.apx import executor as ex
from autopilot.apx import planner, repo_ci, sandbox_job
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

ADMIN, CONTROL, PAWL, KIT = (f"RyanJHamby/{r}" for r in ("admin", "control", "pawl", "agent-kit"))
ROOT = Path(__file__).resolve().parent.parent


def specs():
    return repo_ci.load_specs()


def test_each_private_repo_has_its_required_context_names_and_commands():
    s = specs()
    assert set(s) == {ADMIN, CONTROL, PAWL, KIT}
    assert [c.context for c in s[ADMIN].checks] == ["ci"]  # classic protection on admin requires exactly `ci`
    assert [c.context for c in s[CONTROL].checks] == ["check", "plan-coverage"]
    assert [c.context for c in s[PAWL].checks] == ["test"]  # the ruleset requires `test` only, not the matrix legs
    assert [c.context for c in s[ADMIN].checks][0] == "ci"
    admin_cmds = [cmd for cmd, _ in s[ADMIN].checks[0].steps]
    assert admin_cmds == ["gitleaks detect --source . --no-banner --redact", "scripts/ci-test.sh"]
    assert [cmd for cmd, _ in s[PAWL].checks[0].steps] == ["make check"]
    assert "pawl check --base origin/main" in [cmd for cmd, _ in s[CONTROL].checks[0].steps]
    assert [cmd for cmd, _ in s[KIT].checks[0].steps] == ["make check"]
    assert {"gitleaks"} <= set(s[ADMIN].tools) and "pawl" in s[CONTROL].tools and "shellcheck" in s[KIT].tools


def test_every_step_passes_the_same_safety_filter_as_repo_yaml_ci_steps():
    for spec in specs().values():
        for chk in spec.checks:
            cilane.parse_ci_steps({"ci": [{"run": c, "dir": d} for c, d in chk.steps]})  # raises on anything unsafe


def test_a_bad_spec_is_refused(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"o/r": {"tools": [], "checks": [{"context": "ci", "steps": ["rm -rf / ; ls"]}]}}))
    with pytest.raises(ValueError):
        repo_ci.load_specs(p)
    p.write_text(json.dumps({"o/r": {"tools": ["a b"], "checks": [{"context": "ci", "steps": ["make check"]}]}}))
    with pytest.raises(ValueError):
        repo_ci.load_specs(p)
    p.write_text(json.dumps({"o/r": {"tools": [], "checks": []}}))
    with pytest.raises(ValueError):  # a repo that checks nothing must not look green
        repo_ci.load_specs(p)


def test_unconfigured_repo_gets_nothing():
    assert repo_ci.spec_for("RyanJHamby/stencil") is None
    assert repo_ci.spec_for("RyanJHamby/autopilot") is None


def test_settings_opt_in_validation(tmp_path):
    inst = f"{REPO}=11,{ADMIN}=12,{PAWL}=13"
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst))
    assert s.private_ci == frozenset()  # nothing runs for them until the owner opts in
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, APX_PRIVATE_CI=f"{ADMIN},{PAWL}"))
    assert s.private_ci == {ADMIN, PAWL}
    assert [c.context for c in s.private_checks(ADMIN)] == ["ci"]
    assert s.private_checks(REPO) == ()
    assert not s.full_loop(ADMIN) and not s.agents_allowed(ADMIN)  # checks only, even once shadow mode is off
    off = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, APX_PRIVATE_CI=ADMIN, APX_SHADOW="0"))
    assert not off.full_loop(ADMIN) and off.full_loop(REPO)
    for bad in (
        {"APX_PRIVATE_CI": CONTROL},  # not installed
        {"APX_PRIVATE_CI": REPO},  # installed but has no spec
        {"APX_PRIVATE_CI": "RyanJHamby/resume"},
    ):
        with pytest.raises(dm.ConfigError):
            dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=inst, **bad))
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
    assert meta[REPO]["contexts"] == ["guard / guard", "test"] and "spec_ci" not in meta[REPO]
    ctx = dm.check_contexts(s)
    assert ctx[ADMIN]["checks"][0]["context"] == "ci" and ctx[REPO] == {"guard": "guard / guard", "ci": "test"}


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
                raise planner.GitHubError(404, "nope")
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


def fake_bin(dirpath, names):
    for n in names:
        f = dirpath / n
        f.write_text("#!/bin/sh\n")
        f.chmod(f.stat().st_mode | stat.S_IXUSR)


def tools_cli(path, repos):
    return subprocess.run(
        [sys.executable, "-m", "autopilot.apx.repo_ci", "check-tools", repos, "--path", str(path)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )


def test_missing_tool_is_a_preflight_fail(tmp_path):
    fake_bin(tmp_path, ["git", "python3", "bash", "make"])  # no gitleaks
    r = tools_cli(tmp_path, ADMIN)
    assert r.returncode == 1
    assert any(line.startswith("FAIL") and "gitleaks" in line and "admin" in line for line in r.stdout.splitlines())


def test_all_tools_present_passes_and_nothing_configured_passes(tmp_path):
    needed = {t for r in (ADMIN, PAWL) for t in specs()[r].tools}
    fake_bin(tmp_path, sorted(needed))
    r = tools_cli(tmp_path, f"{ADMIN},{PAWL}")
    assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS" in r.stdout
    empty = tools_cli(tmp_path / "nothing", "")
    assert empty.returncode == 0 and "FAIL" not in empty.stdout


def test_unknown_repo_in_the_list_is_a_fail(tmp_path):
    r = tools_cli(tmp_path, "RyanJHamby/stencil")
    assert r.returncode == 1 and "FAIL" in r.stdout


@pytest.mark.parametrize("script", ["deploy/linux/preflight.sh", "deploy/apx-host-preflight.sh"])
def test_both_preflights_call_the_tool_check_for_configured_repos(script):
    text = (ROOT / script).read_text()
    assert "APX_PRIVATE_CI" in text and "autopilot.apx.repo_ci" in text and "check-tools" in text
    assert subprocess.run(["bash", "-n", str(ROOT / script)]).returncode == 0
