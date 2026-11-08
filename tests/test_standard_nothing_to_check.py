"""Two rules skip a repo that has nothing for them to check (a docs-only repo), and still fail one that does."""

from pathlib import Path

import pytest

from autopilot.scaffold import core as scaffold
from autopilot.standard import engine

RULES = ["dependency-updates", "one-check-entrypoint"]


def repo(tmp_path: Path, files: dict[str, str], name: str = "r") -> engine.Repo:
    root = tmp_path / name
    root.mkdir()
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return engine.Repo(root, github_public=True)


def outcome(r: engine.Repo) -> dict[str, str]:
    return {x.id: x.result for x in engine.run(r, only=RULES)}


def test_a_docs_only_repo_skips_both_rules(tmp_path):
    got = outcome(repo(tmp_path, {"README.md": "hi", "docs/journal.md": "x"}))
    assert got == {"dependency-updates": "skip", "one-check-entrypoint": "skip"}


def test_a_skip_says_why_and_is_not_a_pass(tmp_path):
    results = engine.run(repo(tmp_path, {"README.md": "hi"}), only=RULES)
    assert all(r.result == "skip" and r.findings for r in results)


@pytest.mark.parametrize(
    "manifest", ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "requirements.txt", "Dockerfile", "uv.lock"]
)
def test_a_repo_with_a_manifest_still_fails_both(tmp_path, manifest):
    assert outcome(repo(tmp_path, {manifest: ""})) == {"dependency-updates": "fail", "one-check-entrypoint": "fail"}


def test_a_repo_with_only_a_workflow_still_fails_both(tmp_path):
    assert outcome(repo(tmp_path, {".github/workflows/ci.yml": "on: push\n"})) == {
        "dependency-updates": "fail",
        "one-check-entrypoint": "fail",
    }


def test_a_makefile_without_check_fails_the_check_rule_but_has_nothing_to_update(tmp_path):
    assert outcome(repo(tmp_path, {"Makefile": "all:\n\ttrue\n"})) == {
        "dependency-updates": "skip",
        "one-check-entrypoint": "fail",
    }


def test_a_config_or_a_check_still_passes(tmp_path):
    got = outcome(
        repo(tmp_path, {"pyproject.toml": "", ".github/dependabot.yml": "version: 2\n", "Makefile": "check:\n\ttrue\n"})
    )
    assert got == {"dependency-updates": "pass", "one-check-entrypoint": "pass"}


def test_a_config_in_an_otherwise_empty_repo_is_a_pass_not_a_skip(tmp_path):
    assert outcome(repo(tmp_path, {".github/dependabot.yml": "version: 2\n"}))["dependency-updates"] == "pass"


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"README.md": "x"},
        {"pyproject.toml": ""},
        {"package.json": ""},
        {"Dockerfile": ""},
        {"go.mod": ""},
        {".github/workflows/ci.yml": "on: push\n"},
        {".github/workflows/x.yaml": "on: push\n"},
        {"Makefile": "all:\n"},
    ],
)
def test_the_engine_and_the_scaffolder_agree_on_whether_there_is_something_to_update(tmp_path, files):
    """The scaffolder declines to write a Dependabot config for exactly the repos the rule now skips."""
    r = repo(tmp_path, files)
    ctx = scaffold.read_ctx(r.path, "r", "owner", True)
    scaffolder_has_something = bool(ctx.ecosystems) or ctx.has_workflows
    rule_has_something = engine.run(r, only=["dependency-updates"])[0].result != "skip"
    assert rule_has_something == scaffolder_has_something
