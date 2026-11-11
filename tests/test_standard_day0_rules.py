"""The five day-0 rules: each has a passing and a failing fixture, and what `ap new` writes passes all of them.

They audit wiring (is the hook installed by `make setup`, is a secret scan in the Makefile). Whether a scan catches a secret is the
scaffold test's job, with real gitleaks. Blind spots are recorded as `limit` tests so they stay visible."""

import os
import subprocess

import pytest

from autopilot.scaffold import core
from autopilot.standard import engine, load_checks

RULES = ("hook-wired", "secret-scan-wired", "workflow-lint-wired", "dependency-cooldown", "standard-wired")


def new_repo(tmp_path, kind="app", ecosystems=None, name="proj"):
    root = tmp_path / name
    root.mkdir()
    ctx = core.Ctx(name=name, owner="o", public=False, kind=kind, ecosystems=ecosystems or [], empty=True, has_workflows=True)
    core.write(root, core.plan(root, ctx))
    return root


def check(rule, root):
    (r,) = engine.run(engine.Repo(root), only=[rule])
    return r.result, r.findings


def edit(root, rel, fn):
    p = root / rel
    p.write_text(fn(p.read_text()))


# --- what `ap new` writes passes all four -----------------------------------------------------------------------------


@pytest.mark.parametrize("kind,eco", [("app", []), ("notes", []), ("library", ["uv"]), ("cli", ["uv"])])
def test_a_fresh_repo_of_every_kind_passes_all_five(tmp_path, kind, eco):
    root = new_repo(tmp_path, kind, eco)
    got = {rule: check(rule, root) for rule in RULES}
    assert {k: v[0] for k, v in got.items()} == dict.fromkeys(RULES, "pass"), got


def test_the_rules_are_dated_and_fail_level_so_a_new_repo_is_strict_and_an_old_one_is_not_broken():
    rules = {c["id"]: c for c in load_checks()["checks"] if c["id"] in RULES}
    assert set(rules) == set(RULES)
    for rule in rules.values():
        assert str(rule["since"]) == "2026-11-10" and rule["level"] == "fail", rule["id"]


def git_born(root, date):
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{date}T12:00:00+00:00", "GIT_COMMITTER_DATE": f"{date}T12:00:00+00:00"}
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(var, None)
    for args in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-qm", "first"]):
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       cwd=root, check=True, capture_output=True, env=env)


def test_an_old_repo_missing_all_four_is_reported_at_warn_and_a_new_one_at_fail(tmp_path):
    for name, born in (("old", "2026-10-01"), ("new", "2026-11-11")):
        root = tmp_path / name
        root.mkdir()
        (root / "README.md").write_text("x\n")
        (root / ".github/workflows").mkdir(parents=True)
        (root / ".github/workflows/ci.yml").write_text("on: push\n")
        git_born(root, born)
    old = {r.id: r for r in engine.run(engine.Repo(tmp_path / "old"), only=list(RULES))}
    new = {r.id: r for r in engine.run(engine.Repo(tmp_path / "new"), only=list(RULES))}
    assert {r.level for r in old.values()} == {"warn"} and {r.result for r in old.values()} >= {"fail"}
    assert {r.level for r in new.values()} == {"fail"}
    assert engine.exit_code(list(old.values())) == 0 and engine.exit_code(list(new.values())) == 1


# --- hook-wired ----------------------------------------------------------------------------------------------------------


def test_hook_wired_fails_without_a_hook(tmp_path):
    root = new_repo(tmp_path)
    (root / ".githooks/pre-commit").unlink()
    result, findings = check("hook-wired", root)
    assert result == "fail" and any("no .githooks/pre-commit" in f for f in findings)


def test_hook_wired_fails_when_the_hook_is_not_executable_because_git_ignores_it(tmp_path):
    root = new_repo(tmp_path)
    (root / ".githooks/pre-commit").chmod(0o644)
    result, findings = check("hook-wired", root)
    assert result == "fail" and any("not executable" in f for f in findings)


def test_hook_wired_fails_when_the_hook_does_not_run_make(tmp_path):
    root = new_repo(tmp_path)
    (root / ".githooks/pre-commit").write_text("#!/bin/sh\nexit 0\n")
    result, findings = check("hook-wired", root)
    assert result == "fail" and any("does not run make" in f for f in findings)


def test_hook_wired_fails_without_a_setup_target_because_a_fresh_clone_would_never_get_the_hook(tmp_path):
    root = new_repo(tmp_path)
    edit(root, "Makefile", lambda s: s.replace("setup:", "installhooks:").replace(" setup ", " "))
    result, findings = check("hook-wired", root)
    assert result == "fail" and any("setup" in f for f in findings)


def test_LIMIT_hook_wired_cannot_see_that_quick_does_nothing(tmp_path):
    # The wiring is intact but `quick` is an empty target, so the hook runs and checks nothing. Recorded, not caught.
    root = new_repo(tmp_path)
    edit(root, "Makefile", lambda s: s.replace("quick: staged-secrets", "quick:"))
    assert check("hook-wired", root)[0] == "pass"


# --- secret-scan-wired ---------------------------------------------------------------------------------------------------


def test_secret_scan_wired_fails_when_no_scanner_is_named(tmp_path):
    root = new_repo(tmp_path)
    edit(root, "Makefile", lambda s: s.replace("gitleaks", "scanner"))
    assert check("secret-scan-wired", root)[0] == "fail"


def test_secret_scan_wired_is_not_fooled_by_a_commented_out_scanner(tmp_path):
    root = new_repo(tmp_path)
    (root / "Makefile").write_text("# gitleaks git --staged\ncheck:\n\ttrue\n")
    assert check("secret-scan-wired", root)[0] == "fail"


def test_secret_scan_wired_accepts_a_pre_commit_config(tmp_path):
    root = new_repo(tmp_path)
    (root / "Makefile").write_text("check:\n\ttrue\n")
    (root / ".pre-commit-config.yaml").write_text("repos:\n  - repo: https://github.com/gitleaks/gitleaks\n")
    assert check("secret-scan-wired", root)[0] == "pass"


# --- workflow-lint-wired -------------------------------------------------------------------------------------------------


def test_workflow_lint_wired_skips_a_repo_with_no_workflows(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    assert check("workflow-lint-wired", root)[0] == "skip"


@pytest.mark.parametrize("missing", ["actionlint", "zizmor"])
def test_workflow_lint_wired_needs_both_linters(tmp_path, missing):
    root = new_repo(tmp_path)
    edit(root, "Makefile", lambda s: s.replace(missing, "nothing"))
    result, findings = check("workflow-lint-wired", root)
    assert result == "fail" and any(missing in f for f in findings)


# --- dependency-cooldown -------------------------------------------------------------------------------------------------


def test_dependency_cooldown_names_the_entry_that_has_none(tmp_path):
    root = new_repo(tmp_path, "library", ["uv"])
    (root / ".github/dependabot.yml").write_text(
        "version: 2\nupdates:\n  - package-ecosystem: uv\n    directory: /\n    schedule: {interval: weekly}\n"
    )
    result, findings = check("dependency-cooldown", root)
    assert result == "fail" and any("uv" in f for f in findings)


def test_dependency_cooldown_rejects_a_cooldown_of_zero_days(tmp_path):
    root = new_repo(tmp_path)
    edit(root, ".github/dependabot.yml", lambda s: s.replace("default-days: 7", "default-days: 0"))
    assert check("dependency-cooldown", root)[0] == "fail"


def test_dependency_cooldown_accepts_renovate_with_a_minimum_release_age(tmp_path):
    root = new_repo(tmp_path)
    (root / ".github/dependabot.yml").unlink()
    (root / "renovate.json").write_text('{"minimumReleaseAge": "7 days"}\n')
    assert check("dependency-cooldown", root)[0] == "pass"
    (root / "renovate.json").write_text('{"extends": ["config:recommended"]}\n')
    assert check("dependency-cooldown", root)[0] == "fail"


def test_dependency_cooldown_skips_when_there_is_no_updater_at_all(tmp_path):
    root = new_repo(tmp_path)
    (root / ".github/dependabot.yml").unlink()
    assert check("dependency-cooldown", root)[0] == "skip"  # `dependency-updates` is the rule that reports the absence


def test_dependency_cooldown_is_unknown_not_a_pass_when_the_config_does_not_parse(tmp_path):
    root = new_repo(tmp_path)
    (root / ".github/dependabot.yml").write_text("updates: [unclosed\n")
    assert check("dependency-cooldown", root)[0] == "unknown"


# --- standard-wired ----------------------------------------------------------------------------------------------------


def test_standard_wired_fails_when_the_makefile_never_runs_the_standard(tmp_path):
    root = new_repo(tmp_path)
    edit(root, "Makefile", lambda s: s.replace("ap standard check", "echo skipped"))
    result, findings = check("standard-wired", root)
    assert result == "fail" and any("ap standard check" in f for f in findings)


def test_standard_wired_fails_when_check_does_not_depend_on_it(tmp_path):
    # The target exists, but nothing that CI or an agent runs calls it, so the tripwire never blocks.
    root = new_repo(tmp_path)
    edit(root, "Makefile", lambda s: s.replace("check: quick tracked-secrets workflow-lint standard", "check: quick tracked-secrets workflow-lint"))
    assert check("standard-wired", root)[0] == "fail"


def test_standard_wired_is_not_fooled_by_a_commented_out_call(tmp_path):
    root = new_repo(tmp_path)
    (root / "Makefile").write_text("# ap standard check . --offline\ncheck: standard\nstandard:\n\ttrue\n")
    assert check("standard-wired", root)[0] == "fail"


def test_LIMIT_standard_wired_cannot_see_that_ap_is_missing_from_the_machine(tmp_path):
    # The wiring is intact; on a machine without `ap` the target only warns. A repo audited there passes while checking nothing.
    root = new_repo(tmp_path)
    assert check("standard-wired", root)[0] == "pass"
