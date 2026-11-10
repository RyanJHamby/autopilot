"""The scaffolder: what it plans per kind of repo, that it never overwrites, and that what it writes satisfies the rules it
claims to serve (the round trip is the main test)."""

import argparse
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from autopilot import standard
from autopilot.scaffold import command, core
from autopilot.scaffold import templates as t
from autopilot.standard import engine


def make(tmp_path: Path, files: dict[str, str] | None = None, name: str = "proj") -> Path:
    root = tmp_path / name
    root.mkdir()
    for rel, text in (files or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def ctx(**kw) -> core.Ctx:
    base = {"name": "proj", "owner": "Ryan", "public": True, "holder": "Ryan Hamby", "year": 2026}
    return core.Ctx(**{**base, **kw})


def by_path(actions: list[core.Action]) -> dict[str, core.Action]:
    return {a.path: a for a in actions}


def statuses(root: Path, c: core.Ctx) -> dict[str, str]:
    return {p: a.status for p, a in by_path(core.plan(root, c)).items()}


# --- what a public and a private repo get ------------------------------------------------------------------------


def test_a_public_repo_gets_the_public_files(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "[project]\n", "uv.lock": ""})
    s = statuses(root, core.read_ctx(root, "proj", "Ryan", True, holder="Ryan Hamby"))
    for path in ("LICENSE", "SECURITY.md", "CONTRIBUTING.md", ".github/dependabot.yml", ".gitignore", ".github/CODEOWNERS"):
        assert s[path] == "create", path


def test_a_private_repo_gets_no_license_security_or_contributing(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "[project]\n"})
    s = statuses(root, ctx(public=False))
    assert s["LICENSE"] == s["SECURITY.md"] == s["CONTRIBUTING.md"] == "skip"
    assert s[".gitignore"] == "create"  # the baseline still applies


def test_unknown_visibility_blocks_the_public_files_instead_of_guessing(tmp_path):
    s = statuses(make(tmp_path), ctx(public=None))
    assert s["LICENSE"] == s["SECURITY.md"] == "blocked"


def test_no_holder_means_no_license_and_nothing_written(tmp_path):
    root = make(tmp_path)
    actions = core.plan(root, ctx(holder=None))
    lic = by_path(actions)["LICENSE"]
    assert lic.status == "blocked" and "holder" in lic.note
    core.write(root, actions)
    assert not (root / "LICENSE").exists()


def test_the_license_names_the_holder_and_year(tmp_path):
    lic = by_path(core.plan(make(tmp_path), ctx()))["LICENSE"].content
    assert lic.startswith("MIT License") and "Copyright (c) 2026 Ryan Hamby" in lic


# --- never overwrite -----------------------------------------------------------------------------------------------


def test_an_existing_file_is_never_overwritten(tmp_path):
    root = make(tmp_path, {"LICENSE": "mine\n", ".gitignore": "keep\n"})
    actions = core.plan(root, ctx())
    assert by_path(actions)["LICENSE"].status == "exists"
    core.write(root, actions)
    assert (root / "LICENSE").read_text() == "mine\n" and (root / ".gitignore").read_text() == "keep\n"


@pytest.mark.parametrize("alias", ["LICENSE.md", "LICENSE.txt", "COPYING"])
def test_another_name_for_the_license_counts_as_present(tmp_path, alias):
    assert statuses(make(tmp_path, {alias: "x"}), ctx())["LICENSE"] == "exists"


def test_any_existing_issue_template_counts_as_present(tmp_path):
    root = make(tmp_path, {".github/ISSUE_TEMPLATE/experiment.md": "x"})
    assert statuses(root, ctx())[".github/ISSUE_TEMPLATE/bug.md"] == "exists"


def test_a_file_that_appears_between_plan_and_write_is_left_alone(tmp_path):
    root = make(tmp_path)
    actions = core.plan(root, ctx())
    (root / "LICENSE").write_text("raced\n")
    core.write(root, actions)
    assert (root / "LICENSE").read_text() == "raced\n"
    assert by_path(actions)["LICENSE"].status == "exists"


def test_a_second_run_creates_nothing(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "[project]\n"})
    core.write(root, core.plan(root, ctx()))
    assert [a.path for a in core.plan(root, ctx()) if a.status == "create"] == []


def test_planning_writes_nothing(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "[project]\n"})
    before = sorted(p.name for p in root.rglob("*"))
    core.plan(root, ctx())
    assert sorted(p.name for p in root.rglob("*")) == before


# --- boundaries ------------------------------------------------------------------------------------------------------


def test_a_pawl_repo_is_refused_entirely(tmp_path):
    root = make(tmp_path, {"policy/lanes.toml": ""})
    c = core.read_ctx(root, "proj", "Ryan", True, holder="Ryan Hamby")
    assert core.refusal(c) and "never both" in core.refusal(c)
    assert {a.status for a in core.plan(root, c)} == {"skip"}


def test_a_restricted_repo_is_refused(tmp_path):
    assert {a.status for a in core.plan(make(tmp_path), ctx(restricted=True))} == {"skip"}


@pytest.mark.parametrize("c", [ctx(kind="fork"), ctx(name="Ryan", owner="ryan")])
def test_forks_and_the_profile_repo_are_refused(tmp_path, c):
    assert core.refusal(c)
    assert {a.status for a in core.plan(make(tmp_path), c)} == {"skip"}


def test_an_autopilot_managed_repo_keeps_what_init_owns(tmp_path):
    root = make(tmp_path, {".autopilot/manifest.json": "{}"})
    s = statuses(root, core.read_ctx(root, "proj", "Ryan", True, holder="Ryan Hamby"))
    assert s[".github/CODEOWNERS"] == s[".github/pull_request_template.md"] == s[".github/ISSUE_TEMPLATE/bug.md"] == "skip"
    assert s["LICENSE"] == "create"  # what init does not write is still ours to add


# --- ecosystems, changelog, check entrypoint -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("files", "expect"),
    [
        ({"uv.lock": "", "pyproject.toml": ""}, ["uv"]),
        ({"pyproject.toml": ""}, ["pip"]),
        ({"package.json": "{}"}, ["npm"]),
        ({"Cargo.toml": ""}, ["cargo"]),
        ({"go.mod": ""}, ["gomod"]),
        ({"Dockerfile": ""}, ["docker"]),
        ({}, []),
    ],
)
def test_ecosystems_are_detected_from_manifests(tmp_path, files, expect):
    assert core.detect_ecosystems(make(tmp_path, files)) == expect


def test_dependabot_is_valid_yaml_with_known_ecosystems_and_actions_when_there_are_workflows():
    doc = yaml.safe_load(t.dependabot(["uv", "npm"], has_workflows=True))
    assert doc["version"] == 2
    assert [u["package-ecosystem"] for u in doc["updates"]] == ["uv", "npm", "github-actions"]
    assert all(u["schedule"]["interval"] == "weekly" for u in doc["updates"])


def test_no_manifests_and_no_workflows_means_no_dependabot_file(tmp_path):
    assert statuses(make(tmp_path), ctx())[".github/dependabot.yml"] == "skip"


def test_gitignore_has_one_section_per_language_family_and_never_ignores_results_or_docs():
    text = t.gitignore(["uv", "pip", "npm"])
    assert text.count("# python") == 1 and "# node" in text
    assert "results" not in text and "docs" not in text.replace("Generated", "")


def test_a_changelog_only_for_package_kinds(tmp_path):
    root = make(tmp_path)
    assert statuses(root, ctx(kind="library"))["CHANGELOG.md"] == "create"
    assert statuses(root, ctx(kind="notes"))["CHANGELOG.md"] == "skip"
    assert statuses(root, ctx())["CHANGELOG.md"] == "skip"


def test_a_makefile_check_is_written_only_when_there_is_none(tmp_path):
    assert statuses(make(tmp_path, {"uv.lock": "", "pyproject.toml": ""}), ctx(ecosystems=["uv"]))["Makefile"] == "create"
    root = make(tmp_path, {"Makefile": "all:\n\ttrue\n"}, name="has-makefile")
    c = core.read_ctx(root, "proj", "Ryan", True)
    assert statuses(root, ctx(ecosystems=["uv"], has_check=c.has_check))["Makefile"] == "exists"
    assert (root / "Makefile").read_text() == "all:\n\ttrue\n"


def test_an_existing_check_target_or_ci_list_means_no_makefile(tmp_path):
    root = make(tmp_path, {"Makefile": "check:\n\ttrue\n", "pyproject.toml": ""})
    assert core.read_ctx(root, "proj", "Ryan", True).has_check
    root2 = make(tmp_path, {".autopilot/repo.yaml": "ci:\n  - x\n", "pyproject.toml": ""}, name="two")
    assert core.read_ctx(root2, "proj", "Ryan", True).has_check


def test_the_generated_makefile_has_real_tabs():
    assert all("\n\t" in body for body in t.MAKEFILE.values())


# --- templates --------------------------------------------------------------------------------------------------------


def test_an_unfilled_token_is_an_error_not_a_file():
    with pytest.raises(KeyError, match="holder"):
        t.fill("hello @@holder@@")
    assert t.fill("a @@x@@ b", x=1) == "a 1 b"


def test_github_actions_expressions_do_not_look_like_tokens():
    assert t.fill("${{ secrets.X }} @@a@@", a="b") == "${{ secrets.X }} b"


DAY_ZERO = {".githooks/pre-commit", ".editorconfig", "docs/decisions/README.md", "docs/runbooks/README.md"}


def test_every_rendered_file_is_free_of_tokens(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "", "uv.lock": ""})
    for a in core.plan(root, ctx(kind="library", ecosystems=["uv"], has_workflows=True)):
        # An existing repo skips the day-0 files (see test_scaffold_day0); everything else is created.
        assert a.path in DAY_ZERO or a.status == "create", a.path
        assert "@@" not in a.content, a.path
    fresh = make(tmp_path, name="fresh")
    for a in core.plan(fresh, ctx(kind="library", ecosystems=["uv"], has_workflows=True, empty=True)):
        assert "@@" not in a.content, a.path


def test_every_item_names_a_rule_that_exists_or_is_proposed():
    known = {c["id"] for c in standard.load_checks()["checks"]}
    for item in core.ITEMS:
        assert item.rule is None or item.rule in known | core.PROPOSED_RULES, item.path


# --- round trip: what it writes must satisfy the rules it claims to serve -----------------------------------------------


def test_what_the_scaffolder_writes_passes_the_rules_it_claims_to_serve(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "[project]\n", "uv.lock": ""})
    c = core.read_ctx(root, "proj", "Ryan", True, holder="Ryan Hamby", kind="library")
    core.write(root, core.plan(root, c))
    served = sorted({i.rule for i in core.ITEMS if i.rule in {x["id"] for x in standard.load_checks()["checks"]}})
    assert served, "expected the scaffolder to serve at least one rule in checks.yaml"
    results = engine.run(engine.Repo(root, github_public=True), only=served)
    failing = [(r.id, r.findings) for r in results if r.result not in ("pass", "skip")]
    assert failing == []


# --- the command: branch, clean tree, no commit ------------------------------------------------------------------------


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repo_with_history(tmp_path, name="proj"):
    root = make(tmp_path, {"pyproject.toml": "[project]\n", "uv.lock": ""}, name=name)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


def ns(repo, **kw):
    base = {
        "repos": [str(repo)],
        "portfolio": False,
        "root": "~/dev",
        "apply": False,
        "holder": None,
        "kind": None,
        "offline": True,
        "json": False,
    }
    return argparse.Namespace(**{**base, **kw})


def run_fix(root, capsys, public=True, **kw):
    pf = {"owner": "Ryan", "repos": {root.name: {"enabled": True, "public": public}}}
    code = command.cmd_fix(ns(root, **kw), repo_name=lambda p: p.name, load_portfolio=lambda: pf)
    return code, capsys.readouterr().out


def test_dry_run_prints_the_plan_and_changes_nothing(tmp_path, capsys):
    root = repo_with_history(tmp_path)
    code, out = run_fix(root, capsys, holder="Ryan Hamby")
    assert code == 0 and "create   LICENSE" in out and "dry run: nothing was written" in out
    assert git(root, "status", "--porcelain") == "" and git(root, "branch", "--show-current") == "main"


def test_apply_writes_on_a_new_branch_and_does_not_commit(tmp_path, capsys):
    root = repo_with_history(tmp_path)
    head = git(root, "rev-parse", "HEAD")
    code, out = run_fix(root, capsys, apply=True, holder="Ryan Hamby")
    assert code == 0 and "standard/scaffold" in out
    assert git(root, "branch", "--show-current") == command.BRANCH
    assert git(root, "rev-parse", "HEAD") == head, "nothing may be committed"
    assert (root / "LICENSE").is_file() and (root / ".github/dependabot.yml").is_file()
    assert "LICENSE" in git(root, "status", "--porcelain")


def test_apply_refuses_a_dirty_tree_and_writes_nothing(tmp_path, capsys):
    root = repo_with_history(tmp_path)
    (root / "scratch.txt").write_text("wip")
    code, out = run_fix(root, capsys, apply=True, holder="Ryan Hamby")
    assert code == 1 and "not clean" in out
    assert not (root / "LICENSE").exists() and git(root, "branch", "--show-current") == "main"


def test_apply_on_a_repo_with_nothing_missing_makes_no_branch(tmp_path, capsys):
    done = {
        ".gitignore": "x\n",
        ".github/CODEOWNERS": "* @Ryan\n",
        ".github/pull_request_template.md": "x\n",
        ".github/ISSUE_TEMPLATE/bug.md": "x\n",
    }
    root = make(tmp_path, done)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    code, out = run_fix(root, capsys, public=False, apply=True)
    assert code == 0 and "wrote" not in out
    assert git(root, "branch", "--show-current") == "main"


def test_a_private_repo_is_planned_without_a_license(tmp_path, capsys):
    root = repo_with_history(tmp_path)
    _, out = run_fix(root, capsys, public=False, holder="Ryan Hamby")
    assert "skip     LICENSE" in out and "private repo" in out


def test_json_output_lists_each_action(tmp_path, capsys):
    root = repo_with_history(tmp_path)
    _, out = run_fix(root, capsys, json=True, holder="Ryan Hamby")
    doc = json.loads(out)
    assert doc["applied"] is False and doc["repos"][0]["repo"] == "proj"
    assert {a["path"]: a["status"] for a in doc["repos"][0]["actions"]}["LICENSE"] == "create"


def test_a_missing_clone_is_an_error_by_name(tmp_path, capsys):
    pf = {"owner": "Ryan", "repos": {"ghost": {"enabled": True}}}
    code = command.cmd_fix(
        ns(tmp_path, repos=[], portfolio=True, root=str(tmp_path / "nowhere")),
        repo_name=lambda p: p.name,
        load_portfolio=lambda: pf,
    )
    assert code == 1 and "no clone of ghost" in capsys.readouterr().out


def test_with_nothing_to_check_it_says_so(tmp_path, capsys):
    code = command.cmd_fix(ns(tmp_path, repos=[]), repo_name=lambda p: p.name, load_portfolio=lambda: {"owner": "Ryan"})
    assert code == 2 and "nothing to do" in capsys.readouterr().out


# --- where the public/private answer came from -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("public", "asked", "entry", "expect"),
    [
        (True, True, {"public": True}, "public per GitHub"),
        (False, False, {"public": False}, "private per GitHub"),
        (True, True, {}, "public per GitHub (portfolio disagrees; GitHub used)"),
        (False, False, {"public": True}, "private per GitHub (portfolio disagrees; GitHub used)"),
        (True, None, {"public": True}, "public per portfolio (GitHub not asked or unreachable)"),
        (False, None, {}, "private per portfolio (GitHub not asked or unreachable)"),
        (None, None, None, "unknown (not in the portfolio and GitHub not asked or unreachable)"),
    ],
)
def test_the_source_of_the_public_answer_is_stated(public, asked, entry, expect):
    assert command.visibility(public, asked, entry) == expect


def test_the_report_shows_the_source_and_json_carries_it(tmp_path, capsys):
    root = repo_with_history(tmp_path)
    _, out = run_fix(root, capsys, holder="Ryan Hamby")
    assert "[public per portfolio (GitHub not asked or unreachable)]" in out
    _, js = run_fix(root, capsys, json=True, holder="Ryan Hamby")
    assert json.loads(js)["repos"][0]["visibility"].startswith("public per portfolio")


# --- workflow templates ------------------------------------------------------------------------------------------------


def test_every_action_in_the_workflow_templates_is_pinned_to_a_full_sha():
    import re

    from autopilot.scaffold import templates as t

    for text in (t.CI_UV, t.RELEASE_UV):
        uses = re.findall(r"uses:\s*(\S+)", text)
        assert uses
        assert all(re.fullmatch(r".+@[0-9a-f]{40}", u) for u in uses), uses


def test_release_grants_id_token_to_the_publish_job_only():
    import yaml

    from autopilot.scaffold import templates as t

    wf = yaml.safe_load(t.RELEASE_UV)
    assert wf["permissions"] == {"contents": "read"}
    assert "id-token" not in wf["jobs"]["build"].get("permissions", {})
    assert wf["jobs"]["publish"]["permissions"] == {"id-token": "write"}
    assert wf["jobs"]["publish"]["environment"] == "pypi"
    assert wf[True]["push"]["tags"] == ["v*"]  # YAML reads the key `on` as boolean True


def test_ci_and_release_are_gated_by_ecosystem_kind_and_visibility(tmp_path):
    root = make(tmp_path, {})
    uv = dict(ecosystems=["uv"], holder="R")
    got = statuses(root, ctx(public=True, kind="library", **uv))
    assert got[".github/workflows/ci.yml"] == "create" and got[".github/workflows/release.yml"] == "create"
    assert statuses(root, ctx(public=False, kind="library", **uv))[".github/workflows/release.yml"] == "skip"
    assert statuses(root, ctx(public=True, kind="app", **uv))[".github/workflows/release.yml"] == "skip"
    assert statuses(root, ctx(public=True, kind="library", ecosystems=["npm"]))[".github/workflows/ci.yml"] == "skip"
    assert statuses(root, ctx(public=True, kind="library", autopilot_managed=True, **uv))[".github/workflows/ci.yml"] == "skip"


def test_any_existing_workflow_counts_as_ci(tmp_path):
    root = make(tmp_path, {".github/workflows/test.yml": "name: t\n"})
    assert statuses(root, ctx(ecosystems=["uv"]))[".github/workflows/ci.yml"] == "exists"


# --- skeleton and layout -------------------------------------------------------------------------------------------------


def new_package(tmp_path: Path, kind: str = "library", name: str = "my-lib", **kw) -> tuple[Path, core.Ctx]:
    root = make(tmp_path, {}, name=name)
    c = core.read_ctx(root, name, "Ryan", True, holder="Ryan Hamby", kind=kind, **kw)
    return root, c


def test_an_empty_directory_gets_a_skeleton_for_a_package_kind(tmp_path):
    root, c = new_package(tmp_path)
    s = statuses(root, c)
    for path in ("pyproject.toml", "README.md", "src/my_lib/__init__.py", "src/my_lib/py.typed", "tests/test_smoke.py"):
        assert s[path] == "create", path
    assert s["Makefile"] == s[".github/workflows/ci.yml"] == s[".github/workflows/release.yml"] == "create"


def test_the_skeleton_is_never_written_into_a_populated_repo(tmp_path):
    root = make(tmp_path, {"main.py": "print(1)\n"})
    c = core.read_ctx(root, "proj", "Ryan", True, holder="H", kind="library")
    assert not c.empty
    assert not any(p.startswith("src/") or p in ("pyproject.toml", "README.md") for p in statuses(root, c))


def test_a_git_only_directory_counts_as_empty_but_a_non_package_kind_gets_no_skeleton(tmp_path):
    root = make(tmp_path)
    (root / ".git").mkdir()
    assert core.read_ctx(root, "proj", "Ryan", True, kind="cli").empty
    assert "pyproject.toml" not in statuses(root, core.read_ctx(root, "proj", "Ryan", True, holder="H", kind="notes"))


def test_a_private_skeleton_names_no_license_and_a_missing_holder_names_no_author(tmp_path):
    text = t.pyproject("p", "p", "o", None, False, False)
    assert "license" not in text and "authors" not in text
    assert 'license = "MIT"' in t.pyproject("p", "p", "o", "H", True, False)


def test_a_cli_skeleton_declares_an_entry_point(tmp_path):
    import tomllib

    root, c = new_package(tmp_path, kind="cli", name="my-tool")
    core.write(root, core.plan(root, c))
    meta = tomllib.loads((root / "pyproject.toml").read_text())
    assert meta["project"]["scripts"] == {"my-tool": "my_tool:main"}
    assert "def main" in (root / "src/my_tool/__init__.py").read_text()


def test_layout_notes_report_drift_and_change_nothing(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "[project]\n", "test_a.py": "def test_a(): pass\n"})
    before = sorted(p.name for p in root.rglob("*"))
    notes = core.layout_notes(root, core.read_ctx(root, "proj", "Ryan", True, kind="library"))
    assert any("tests" in n for n in notes) and any("src/" in n for n in notes)
    assert sorted(p.name for p in root.rglob("*")) == before
    assert core.layout_notes(root, core.read_ctx(root, "proj", "Ryan", True, kind="app")) == []


def test_a_scaffolded_skeleton_passes_the_standard_rules_it_serves(tmp_path):
    root, c = new_package(tmp_path)
    core.write(root, core.plan(root, c))
    ids = {x["id"] for x in standard.load_checks()["checks"]}
    served = sorted({i.rule for i in core.ITEMS + core.SKELETON if i.rule in ids})
    assert {"license-present", "pinned-actions", "one-check-entrypoint", "gitignore-present"} <= set(served)
    failing = [
        (r.id, r.findings)
        for r in engine.run(engine.Repo(root, github_public=True), only=served)
        if r.result not in ("pass", "skip")
    ]
    assert failing == []


def test_a_second_run_on_a_scaffolded_skeleton_creates_nothing(tmp_path):
    root, c = new_package(tmp_path)
    core.write(root, core.plan(root, c))
    again = core.read_ctx(root, "my-lib", "Ryan", True, holder="Ryan Hamby", kind="library")
    assert [a.path for a in core.plan(root, again) if a.status == "create"] == []


def test_codeowners_names_the_owner_with_an_at_sign(tmp_path):
    """A bare `* name` is not a valid owner on GitHub. The placeholder regex once swallowed the literal `@`."""
    root = make(tmp_path)
    text = by_path(core.plan(root, ctx(owner="RyanJHamby")))[".github/CODEOWNERS"].content
    rules = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    assert rules == ["* @RyanJHamby"]
    for line in rules:
        assert all(owner.startswith("@") for owner in line.split()[1:])
