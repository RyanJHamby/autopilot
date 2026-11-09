"""`ap standard template`: the template is the scaffolder's own output for a synthetic repo, so it cannot drift from it."""

import subprocess
from pathlib import Path

import pytest

from autopilot.scaffold import core, template
from autopilot.standard import engine

# The generic layer. A new scaffolder item that applies to a public repo with workflows lands in the template; this list makes
# that a deliberate decision (the test fails until it is edited here).
EXPECTED = [
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/bug.md",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    ".gitignore",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
]
# Rules the template does not serve: they belong to `pow init` (journal) and to AGENTS.md/CLAUDE.md, which come per repo.
NOT_SERVED = {"journal-present", "thin-claude-md"}


def build(tmp_path: Path, owner="octo", holder="Octo Cat") -> tuple[Path, list[str]]:
    out = tmp_path / "tpl"
    written, _ = template.render(out, owner, holder)
    return out, written


def test_the_template_is_exactly_the_generic_layer(tmp_path):
    _, written = build(tmp_path)
    assert written == EXPECTED


def test_every_file_comes_from_the_scaffolder_plan(tmp_path):
    out, _ = build(tmp_path)
    plan = core.plan(tmp_path / "elsewhere-empty", template.synthetic_ctx("octo", "Octo Cat"))
    for a in plan:
        if a.status == "create":
            assert (out / a.path).read_text() == a.content, a.path


def test_the_template_passes_every_rule_it_serves(tmp_path):
    out, _ = build(tmp_path)
    results = engine.run(engine.Repo(out, github_public=True))
    failed = {r.id for r in results if r.result == "fail"}
    assert failed == NOT_SERVED


def test_per_repo_files_are_left_out(tmp_path):
    out, written = build(tmp_path)
    for left_out in (
        "pyproject.toml",
        "Makefile",
        "justfile",
        "CHANGELOG.md",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ):
        assert left_out not in written
        assert not (out / left_out).exists()


def test_owner_and_holder_are_filled_not_left_as_placeholders(tmp_path):
    out, _ = build(tmp_path)
    assert (out / ".github/CODEOWNERS").read_text().rstrip().endswith("* @octo")
    assert "Octo Cat" in (out / "LICENSE").read_text()
    for p in out.rglob("*"):
        if p.is_file():
            assert "@@" not in p.read_text(), p


def test_readme_has_the_ai_disclosure_heading(tmp_path):
    out, _ = build(tmp_path)
    assert "## How this was built" in (out / "README.md").read_text()


def test_no_holder_is_an_error_not_a_guess(tmp_path):
    with pytest.raises(ValueError, match="holder"):
        template.render(tmp_path / "tpl", "octo", None)


def test_a_non_empty_directory_is_refused_and_left_alone(tmp_path):
    out = tmp_path / "tpl"
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    with pytest.raises(ValueError, match="not empty"):
        template.render(out, "octo", "Octo Cat")
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


def test_a_failed_render_writes_nothing(tmp_path):
    with pytest.raises(ValueError):
        template.render(tmp_path / "tpl", "octo", None)
    assert list((tmp_path / "tpl").iterdir()) == []


def test_it_never_runs_git_or_gh(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError(f"ran a subprocess: {a}")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    ns = type("NS", (), {"out_dir": str(tmp_path / "t2"), "owner": None, "holder": None})()
    assert template.cmd_template(ns, load_portfolio=lambda: {"owner": "octo", "holder": "Octo Cat"}) == 0


def test_the_cli_command_is_wired(tmp_path):
    r = subprocess.run(["uv", "run", "ap", "standard", "template", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "out_dir" in r.stdout
