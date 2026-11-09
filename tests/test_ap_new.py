"""`ap new`: a new local repo that starts on the standard, and stops before anything outward-facing."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from autopilot.scaffold import new
from autopilot.standard import engine

PORTFOLIO = {"owner": "octo", "holder": "Octo Cat"}
# Owned by `pow init` and AGENTS.md/CLAUDE.md, which are per-repo owner steps.
POW_STEPS = {"journal-present", "thin-claude-md"}


def make(tmp_path, name="my-tool", kind="library", public=True, holder="Octo Cat", **kw):
    return new.create(tmp_path, name, kind, "octo", holder, public, **kw)


def files(path: Path) -> set[str]:
    return {str(p.relative_to(path)) for p in path.rglob("*") if p.is_file() and ".git/" not in str(p)}


def test_a_library_gets_the_package_skeleton_and_the_hygiene_layer(tmp_path):
    path, written, _ = make(tmp_path)
    assert {"pyproject.toml", "src/my_tool/__init__.py", "tests/test_smoke.py", ".github/workflows/ci.yml", "LICENSE"} <= files(
        path
    )
    assert sorted(files(path)) == written


def test_an_app_gets_no_package_files(tmp_path):
    path, _, _ = make(tmp_path, kind="app", public=False)
    got = files(path)
    assert "pyproject.toml" not in got and not any(p.startswith("src/") for p in got)
    assert {"README.md", ".gitignore", ".github/CODEOWNERS"} <= got


def test_private_repos_get_no_public_only_files(tmp_path):
    path, _, _ = make(tmp_path, public=False)
    assert not {"LICENSE", "SECURITY.md", "CONTRIBUTING.md"} & files(path)


@pytest.mark.parametrize("kind", new.NEW_KINDS)
def test_only_the_pow_steps_still_fail_the_standard(tmp_path, kind):
    path, _, _ = make(tmp_path, kind=kind)
    failed = {r.id for r in engine.run(engine.Repo(path, github_public=True)) if r.result == "fail"}
    # Kinds with no package ecosystem get no justfile to scaffold, so their commands are an owner step too.
    assert failed == POW_STEPS | ({"commands-documented"} if kind in ("app", "notes") else set())


def test_git_is_initialised_on_main_with_no_commit(tmp_path):
    path, _, _ = make(tmp_path)
    assert (
        subprocess.run(["git", "-C", str(path), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
        == "main"
    )
    assert subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True).returncode != 0


@pytest.mark.parametrize("bad", ["", "-x", "a b", "a/b", "x.git", "../x", "octo", "OCTO"])
def test_bad_names_are_refused_and_nothing_is_made(tmp_path, bad):
    with pytest.raises(ValueError):
        make(tmp_path, name=bad)
    assert list(tmp_path.iterdir()) == []


def test_an_existing_directory_is_refused_and_untouched(tmp_path):
    (tmp_path / "my-tool").mkdir()
    (tmp_path / "my-tool" / "keep.txt").write_text("mine")
    with pytest.raises(ValueError, match="already exists"):
        make(tmp_path)
    assert files(tmp_path / "my-tool") == {"keep.txt"}


def test_a_public_repo_without_a_holder_is_refused_and_leaves_nothing(tmp_path):
    with pytest.raises(ValueError, match="holder"):
        make(tmp_path, holder=None)
    assert list(tmp_path.iterdir()) == []


def test_a_failed_git_init_leaves_nothing_behind(tmp_path):
    bad = lambda *a, **k: SimpleNamespace(returncode=1, stderr="boom", stdout="")  # noqa: E731
    with pytest.raises(ValueError, match="git init failed"):
        make(tmp_path, run=bad)
    assert list(tmp_path.iterdir()) == []


def test_the_command_runs_no_git_commit_and_no_gh(tmp_path):
    seen = []

    def spy(cmd, **kw):
        seen.append(cmd)
        return subprocess.run(cmd, **kw)

    ns = SimpleNamespace(name="my-tool", kind="cli", public=True, root=str(tmp_path), owner=None, holder=None)
    assert new.cmd_new(ns, load_portfolio=lambda: PORTFOLIO, run=spy) == 0
    assert [c[:4] for c in seen] == [["git", "-C", str(tmp_path / "my-tool"), "init"]]


def test_the_command_prints_the_owner_steps_and_refuses_cleanly(tmp_path, capsys):
    ns = SimpleNamespace(name="my-tool", kind="library", public=False, root=str(tmp_path), owner=None, holder=None)
    assert new.cmd_new(ns, load_portfolio=lambda: PORTFOLIO) == 0
    out = capsys.readouterr().out
    assert "pow init" in out and "gh repo create octo/my-tool --private" in out and "nothing outward-facing was done" in out
    assert new.cmd_new(ns, load_portfolio=lambda: PORTFOLIO) == 1  # second time: the directory exists
    assert "already exists" in capsys.readouterr().out


def test_every_skeleton_readme_has_the_ai_disclosure_heading(tmp_path):
    for kind in new.NEW_KINDS:
        path, _, _ = make(tmp_path, name=f"r-{kind}", kind=kind)
        assert "## How this was built" in (path / "README.md").read_text()


def test_the_cli_command_is_wired():
    r = subprocess.run(["uv", "run", "ap", "new", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--kind" in r.stdout
