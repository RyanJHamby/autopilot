"""The standard's engine: each rule has a passing and a failing fixture, so a check that always passes turns a test red."""

import os
import subprocess
from types import SimpleNamespace

import guard
import pytest

from autopilot.standard import engine, load_checks

SHA = "a" * 40


def write(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


OLD = "2026-01-01"  # before every rule's `since`: an existing repo, so a rule dated later is grandfathered to warn


def git_repo(root, files=None, born=OLD):
    """A repo with one commit dated `born`. Backdated by default so tests about exit codes and clones model an *existing* repo;
    a test about the day-0 floor passes a recent `born` (see test_standard_since and test_standard_day0_rules)."""
    write(root, files or {"README.md": "x\n"})
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{born}T12:00:00+00:00", "GIT_COMMITTER_DATE": f"{born}T12:00:00+00:00"}
    for args in (["init", "-q", "-b", "main"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b"]):
        subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, check=True, capture_output=True, env=env)
    return root


def check(rule, root, **kw):
    """Run one rule against a directory and return (result, findings)."""
    (r,) = engine.run(engine.Repo(root, **kw), only=[rule])
    return r.result, r.findings


def wf(body, name="ci.yml"):
    return {f".github/workflows/{name}": body}


GOOD_WF = (
    "name: ci\non: push\npermissions:\n  contents: read\njobs:\n  t:\n    steps:\n      - uses: actions/checkout@" + SHA + "\n"
)


def test_every_rule_has_a_check_and_every_check_has_a_rule():
    ids = {c["id"] for c in load_checks()["checks"]}
    assert set(engine.CHECKS) == ids, f"no check: {ids - set(engine.CHECKS)}; no rule: {set(engine.CHECKS) - ids}"


def test_the_protected_list_matches_the_guard_the_engine_mirrors():
    assert engine.PROTECTED == guard.DEFAULT_PROTECTED


def test_every_rule_returns_a_valid_result_on_an_empty_directory(tmp_path):
    for r in engine.run(engine.Repo(tmp_path)):
        assert r.result in {"pass", "fail", "unknown", "skip"}, r


# --- pinned-actions ---------------------------------------------------------------------------------------------


def test_pinned_actions_passes_for_a_sha(tmp_path):
    assert check("pinned-actions", write(tmp_path, wf(GOOD_WF)))[0] == "pass"


@pytest.mark.parametrize("ref", ["main", "v4", "v4.2.2", "v1.2.3-rc.1", "abc123", "A" * 40])
def test_pinned_actions_fails_for_a_tag_branch_or_short_sha(tmp_path, ref):
    result, findings = check("pinned-actions", write(tmp_path, wf(GOOD_WF.replace(SHA, ref))))
    assert result == "fail" and "ci.yml: action not pinned to a SHA" in findings[0]


def test_pinned_actions_checks_workflows_autopilot_did_not_write_and_yaml_extensions(tmp_path):
    write(tmp_path, wf(GOOD_WF.replace(SHA, "main"), name="build.yaml"))
    assert check("pinned-actions", tmp_path)[0] == "fail"


def test_pinned_actions_fails_for_an_action_with_no_ref_at_all(tmp_path):
    result, findings = check(
        "pinned-actions",
        write(tmp_path, wf("on: push\npermissions: {}\njobs:\n  t:\n    steps:\n      - uses: actions/checkout\n")),
    )
    assert result == "fail" and "actions/checkout" in findings[0]


def test_pinned_actions_ignores_local_docker_and_commented_uses(tmp_path):
    body = "on: push\npermissions: {}\njobs:\n  t:\n    steps:\n      - uses: ./local\n      - uses: docker://alpine:3\n      # - uses: x/y@main\n"
    assert check("pinned-actions", write(tmp_path, wf(body)))[0] == "pass"


def test_pinned_actions_catches_a_quoted_ref_and_a_reusable_workflow(tmp_path):
    body = "on: push\npermissions: {}\njobs:\n  a:\n    uses: o/r/.github/workflows/x.yml@main\n  b:\n    steps:\n      - uses: 'o/r@v1'\n"
    result, findings = check("pinned-actions", write(tmp_path, wf(body)))
    assert result == "fail" and len(findings) == 2


# --- workflow-permissions ---------------------------------------------------------------------------------------


def test_workflow_permissions_passes_when_set(tmp_path):
    assert check("workflow-permissions", write(tmp_path, wf(GOOD_WF)))[0] == "pass"


def test_workflow_permissions_fails_when_missing(tmp_path):
    body = "on: push\njobs:\n  t:\n    permissions:\n      contents: read\n    steps: []\n"
    result, findings = check("workflow-permissions", write(tmp_path, wf(body)))
    assert result == "fail" and "ci.yml" in findings[0], "job-level permissions don't count as top-level"


def test_workflow_permissions_is_unknown_for_a_workflow_that_does_not_parse(tmp_path):
    assert check("workflow-permissions", write(tmp_path, wf("on: [push\n  : bad")))[0] == "unknown"


# --- no-privileged-triggers -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "on", ["pull_request_target", "[push, pull_request_target]", "\n  pull_request_target:\n    types: [opened]"]
)
def test_privileged_trigger_is_caught_in_every_yaml_shape(tmp_path, on):
    assert check("no-privileged-triggers", write(tmp_path, wf(f"on: {on}\njobs: {{}}\n")))[0] == "fail"


def test_privileged_trigger_passes_for_pull_request(tmp_path):
    assert check("no-privileged-triggers", write(tmp_path, wf(GOOD_WF)))[0] == "pass"


def test_the_bare_on_key_is_read_even_though_pyyaml_turns_it_into_true():
    assert engine.triggers({True: "push"}) == {"push"} and engine.triggers({"on": ["a", "b"]}) == {"a", "b"}


# --- secret-exposed-workflows -----------------------------------------------------------------------------------


def test_a_workflow_handing_secrets_to_pr_code_fails(tmp_path):
    body = "on:\n  pull_request:\njobs:\n  t:\n    steps:\n      - run: echo ${{ secrets.DEPLOY_KEY }}\n"
    result, findings = check("secret-exposed-workflows", write(tmp_path, wf(body)))
    assert result == "fail" and "deploy" not in findings[0] and "ci.yml: uses repo secrets on pull_request" in findings[0]


def test_secret_exposure_passes_with_an_agent_exclusion_or_only_github_token(tmp_path):
    safe = (
        "on:\n  pull_request:\n    branches-ignore: ['agent/**']\njobs:\n  t:\n    steps:\n      - run: echo ${{ secrets.K }}\n"
    )
    token = "on:\n  pull_request:\njobs:\n  t:\n    steps:\n      - run: echo ${{ secrets.GITHUB_TOKEN }}\n"
    assert check("secret-exposed-workflows", write(tmp_path, wf(safe)))[0] == "pass"
    assert check("secret-exposed-workflows", write(tmp_path, wf(token, name="b.yml")))[0] == "pass"


# --- codeowners-cover-protected-paths ---------------------------------------------------------------------------

FULL_OWNERS = "/.github/ @me\n/.autopilot/ @me\n/.claude/ @me\n/AGENTS.md @me\n/CLAUDE.md @me\n/.mcp.json @me\n/CODEOWNERS @me\n"


def test_codeowners_passes_when_every_protected_path_has_an_owner(tmp_path):
    assert check("codeowners-cover-protected-paths", write(tmp_path, {"CODEOWNERS": FULL_OWNERS}))[0] == "pass"


def test_codeowners_fails_when_there_is_no_file(tmp_path):
    result, findings = check("codeowners-cover-protected-paths", tmp_path)
    assert (result, findings) == ("fail", ["no CODEOWNERS file"])


def test_codeowners_fails_for_each_uncovered_path(tmp_path):
    result, findings = check("codeowners-cover-protected-paths", write(tmp_path, {"CODEOWNERS": "/.github/ @me\n"}))
    assert result == "fail" and any(".mcp.json" in f for f in findings) and not any(f.startswith(".github/**") for f in findings)


def test_a_codeowners_line_with_no_owner_does_not_count(tmp_path):
    result, findings = check(
        "codeowners-cover-protected-paths", write(tmp_path, {"CODEOWNERS": FULL_OWNERS.replace("/.mcp.json @me", "/.mcp.json")})
    )
    assert result == "fail" and any(".mcp.json" in f for f in findings)


def test_a_catch_all_covers_everything_and_the_extra_protected_paths_are_required(tmp_path):
    cfg = "guard:\n  extra_protected:\n    - src/engine/**\n"
    write(tmp_path, {"CODEOWNERS": FULL_OWNERS, ".autopilot/repo.yaml": cfg})
    result, findings = check("codeowners-cover-protected-paths", tmp_path)
    assert result == "fail" and findings == ["src/engine/** is not owned in CODEOWNERS"]
    (tmp_path / "CODEOWNERS").write_text(FULL_OWNERS + "/src/engine/ @me\n")
    assert check("codeowners-cover-protected-paths", tmp_path)[0] == "pass"
    (tmp_path / "CODEOWNERS").write_text("* @me\n")
    assert check("codeowners-cover-protected-paths", tmp_path)[0] == "pass"


def test_codeowners_in_the_github_directory_is_found(tmp_path):
    assert check("codeowners-cover-protected-paths", write(tmp_path, {".github/CODEOWNERS": FULL_OWNERS}))[0] == "pass"


# --- no-tracked-secrets -----------------------------------------------------------------------------------------


def test_a_tracked_env_file_fails(tmp_path):
    result, findings = check("no-tracked-secrets", git_repo(tmp_path, {".env": "K=1\n", "a.py": ""}))
    assert result == "fail" and findings == [".env is tracked by git"]


@pytest.mark.parametrize("name", ["deploy.pem", "id_rsa", "service-account.json", ".env.production", "sub/dir/.env"])
def test_secret_file_names_are_recognised(name):
    assert engine.secret_file(name)


@pytest.mark.parametrize("name", [".env.example", ".env.sample", "docs/journal.md", "key.pub", "secrets-and-keys.md", "env.py"])
def test_ordinary_files_are_not_flagged(name):
    assert not engine.secret_file(name)


def test_a_clean_repo_passes_and_a_non_git_directory_is_unknown(tmp_path):
    clean, plain = tmp_path / "clean", tmp_path / "plain"
    clean.mkdir()
    plain.mkdir()
    assert check("no-tracked-secrets", git_repo(clean, {"a.py": ""}))[0] == "pass"
    assert check("no-tracked-secrets", plain)[0] == "unknown"


def test_an_untracked_secret_is_not_flagged_because_git_does_not_hold_it(tmp_path):
    git_repo(tmp_path, {"a.py": ""})
    (tmp_path / ".env").write_text("K=1\n")
    assert check("no-tracked-secrets", tmp_path)[0] == "pass"


# --- thin-claude-md, one-check-entrypoint, license, ruleset -----------------------------------------------------


def test_claude_md_must_import_agents_md(tmp_path):
    assert check("thin-claude-md", tmp_path)[0] == "fail"
    assert check("thin-claude-md", write(tmp_path, {"CLAUDE.md": "# mine\n"}))[0] == "fail"
    assert check("thin-claude-md", write(tmp_path, {"CLAUDE.md": "@AGENTS.md\n"}))[0] == "pass"


def test_one_check_entrypoint_accepts_a_make_target_or_a_ci_list_and_nothing_else(tmp_path):
    assert check("one-check-entrypoint", write(tmp_path, {"Makefile": "test:\n\tpytest\n"}))[0] == "fail"
    assert check("one-check-entrypoint", write(tmp_path, {"Makefile": "check:\n\tpytest\n"}))[0] == "pass"
    other = tmp_path / "o"
    assert check("one-check-entrypoint", write(other, {".autopilot/repo.yaml": "ci:\n  - uv run pytest\n"}))[0] == "pass"
    empty = tmp_path / "e"
    assert check("one-check-entrypoint", write(empty, {".autopilot/repo.yaml": "ci: []\n", "pyproject.toml": ""}))[0] == "fail"


def test_license_applies_only_to_public_repos_and_needs_a_file(tmp_path):
    assert check("license-present", tmp_path, entry={"public": True})[0] == "fail"
    assert check("license-present", write(tmp_path, {"LICENSE": "MIT"}), entry={"public": True})[0] == "pass"
    assert check("license-present", tmp_path / "x", entry={"public": False})[0] == "skip"


def test_license_is_skipped_not_passed_when_the_repo_is_not_in_the_portfolio(tmp_path):
    result, findings = check("license-present", tmp_path)
    assert result == "skip" and "not in the portfolio" in findings[0]


def gh(returncode=0, out=""):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode, out, "")


def test_ruleset_present_passes_fails_and_is_unknown_when_gh_cannot_answer(tmp_path):
    assert check("ruleset-present", tmp_path, slug="o/r", gh=gh(0, "main-protection\n"))[0] == "pass"
    assert check("ruleset-present", tmp_path, slug="o/r", gh=gh(0, ""))[0] == "fail"
    assert check("ruleset-present", tmp_path, slug="o/r", gh=gh(1))[0] == "unknown"
    assert check("ruleset-present", tmp_path)[0] == "unknown"


def test_ruleset_present_is_unknown_when_gh_is_not_installed(tmp_path):
    def boom(cmd, **kw):
        raise FileNotFoundError("gh")

    assert check("ruleset-present", tmp_path, slug="o/r", gh=boom)[0] == "unknown"


# --- advisory rules (presence only) -----------------------------------------------------------------------------


def test_agents_md_budget(tmp_path):
    assert check("agents-md-budget", tmp_path)[0] == "skip"
    assert check("agents-md-budget", write(tmp_path, {"AGENTS.md": "x\n" * 60}))[0] == "pass"
    assert check("agents-md-budget", write(tmp_path, {"AGENTS.md": "x\n" * 61}))[0] == "fail"


def test_how_this_was_built_looks_for_the_heading_only(tmp_path):
    assert check("how-this-was-built", write(tmp_path, {"README.md": "# x\n"}))[0] == "fail"
    assert check("how-this-was-built", write(tmp_path, {"README.md": "# x\n## How this was built\n"}))[0] == "pass"


def test_journal_and_dependency_updates(tmp_path):
    assert check("journal-present", tmp_path)[0] == "fail"
    assert check("journal-present", write(tmp_path, {"docs/journal.md": ""}))[0] == "pass"
    assert check("dependency-updates", write(tmp_path / "d", {"pyproject.toml": ""}))[0] == "fail"
    assert check("dependency-updates", write(tmp_path, {".github/dependabot.yml": "version: 2\n"}))[0] == "pass"


# --- the runner -------------------------------------------------------------------------------------------------


def test_a_check_that_raises_is_unknown_never_pass(tmp_path, monkeypatch):
    def broken(repo):
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.CHECKS, "journal-present", broken)
    result, findings = check("journal-present", tmp_path)
    assert result == "unknown" and "RuntimeError: boom" in findings[0]


def test_a_rule_with_no_implementation_is_unknown(tmp_path, monkeypatch):
    monkeypatch.delitem(engine.CHECKS, "journal-present")
    assert check("journal-present", tmp_path)[0] == "unknown"


def result(level, outcome):
    return SimpleNamespace(level=level, result=outcome)


def test_only_a_failing_level_fail_rule_sets_the_exit_code():
    assert engine.exit_code([result("fail", "fail")]) == 1
    assert engine.exit_code([result("warn", "fail")]) == 0
    assert engine.exit_code([result("fail", "unknown")]) == 0
    assert engine.exit_code([result("fail", "pass"), result("fail", "skip")]) == 0


def test_strict_makes_an_unanswered_fail_level_rule_fail_but_not_a_warn_one():
    assert engine.exit_code([result("fail", "unknown")], strict=True) == 1
    assert engine.exit_code([result("warn", "unknown")], strict=True) == 0


def test_json_output_carries_label_level_and_findings(tmp_path):
    out = engine.to_json("r", engine.run(engine.Repo(tmp_path), only=["journal-present"]))
    assert out == {
        "repo": "r",
        "results": [
            {"id": "journal-present", "label": "advisory", "level": "warn", "result": "fail", "findings": ["no docs/journal.md"]}
        ],
    }
