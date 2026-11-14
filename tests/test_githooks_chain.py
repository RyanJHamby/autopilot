"""The repo's .githooks/ replaces the global hooks dir (core.hooksPath is one directory), so each hook here must first run the global
hook of the same name: the freeze gate, identity gate and secret scan live there. Everything below runs real git against throwaway
repos with a throwaway HOME; nothing reads or writes the developer's own git config or hooks.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".githooks"


def _write_exe(path: Path, body: str, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(mode)


class Box:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.log = tmp / "calls.log"
        self.bin = tmp / "bin"
        self.global_hooks = tmp / "global-hooks"
        self.repo = tmp / "repo"
        self.remote = tmp / "remote.git"
        # a fake `uv` stands in for ruff/pytest: it records the call and succeeds unless told to fail
        _write_exe(self.bin / "uv", f'echo "own: uv $*" >> "{self.log}"\n[ -e "{tmp}/own-fails" ] && exit 1\nexit 0\n')
        self.env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig"),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=tmp)
        self.git("init", "-q", "--bare", str(self.remote), cwd=tmp)
        self.git("remote", "add", "origin", str(self.remote))
        shutil.copytree(HOOKS, self.repo / ".githooks")  # the hooks under test, executable bits kept
        self.git("config", "core.hooksPath", ".githooks")
        (self.repo / "f.txt").write_text("x")
        self.git("add", ".")

    def git(self, *args, cwd=None, check=True):
        p = subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)
        if check and p.returncode:
            raise AssertionError(f"git {args} failed: {p.stderr}")
        return p

    def global_hooks_path(self, value):
        self.git("config", "--global", "core.hooksPath", str(value), cwd=self.tmp)

    def global_hook(self, name, body="exit 0\n", mode=0o755):
        _write_exe(self.global_hooks / name, f'echo "global: {name} $*" >> "{self.log}"\n' + body, mode)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def commit(self, msg="m"):
        return self.git("commit", "-q", "-m", msg, check=False)

    def push(self):
        return self.git("push", "-q", "origin", "main", check=False)

    def head_exists(self):
        return self.git("rev-parse", "-q", "--verify", "HEAD", check=False).returncode == 0


@pytest.fixture()
def box(tmp_path):
    return Box(tmp_path)


@pytest.fixture()
def wired(box):
    box.global_hooks_path(box.global_hooks)
    for n in ("pre-commit", "commit-msg", "pre-push"):
        box.global_hook(n)
    return box


def test_global_pre_commit_runs_and_blocks_a_commit(wired):
    wired.global_hook("pre-commit", "echo frozen >&2\nexit 1\n")
    p = wired.commit()
    assert p.returncode != 0 and not wired.head_exists()
    assert "global: pre-commit" in wired.calls() and "frozen" in p.stderr


def test_global_commit_msg_runs_with_the_message_file_and_blocks(wired):
    wired.global_hook("commit-msg", 'grep -q . "$1" || exit 2\nexit 1\n')
    p = wired.commit("nope")
    assert p.returncode != 0 and not wired.head_exists()
    assert any(c.startswith("global: commit-msg ") and "COMMIT_EDITMSG" in c for c in wired.calls())


def test_a_passing_global_chain_lets_the_commit_through_in_order(wired):
    assert wired.commit().returncode == 0 and wired.head_exists()
    assert wired.calls()[0] == "global: pre-commit" and wired.calls()[1].startswith("global: commit-msg ")


def test_global_pre_push_runs_first_gets_its_args_and_stdin_and_blocks_before_own_checks(wired):
    assert wired.commit().returncode == 0
    wired.global_hook("pre-push", f'cat > "{wired.tmp}/stdin"\nexit 1\n')
    p = wired.push()
    assert p.returncode != 0
    assert not any(c.startswith("own:") for c in wired.calls()), "own checks must not run once the global gate failed"
    assert str(wired.remote) in wired.calls()[-1]  # remote name and url were passed through
    assert "refs/heads/main" in (wired.tmp / "stdin").read_text()  # git's ref lines reached the global hook
    assert wired.git("--git-dir", str(wired.remote), "rev-parse", "-q", "--verify", "main", check=False).returncode != 0


def test_when_the_global_pre_push_passes_the_repos_own_checks_run_after_it_unchanged(wired):
    assert wired.commit().returncode == 0
    assert wired.push().returncode == 0
    calls = wired.calls()
    gi = next(i for i, c in enumerate(calls) if c.startswith("global: pre-push"))
    own = [c for c in calls if c.startswith("own:")]
    assert own == ["own: uv run ruff check .", "own: uv run pytest -q"] and calls.index(own[0]) > gi


def test_own_checks_still_block_a_push_when_the_global_hook_passes(wired):
    assert wired.commit().returncode == 0
    (wired.tmp / "own-fails").write_text("")
    assert wired.push().returncode != 0


def test_no_global_hooks_path_means_only_the_repos_own_checks_run(box):
    assert box.commit().returncode == 0
    assert box.push().returncode == 0
    assert [c for c in box.calls() if c.startswith("own:")] == ["own: uv run ruff check .", "own: uv run pytest -q"]
    assert not any(c.startswith("global:") for c in box.calls())


@pytest.mark.parametrize("spelling", ["same", "relative", "symlink", "trailing-slash"])
def test_a_global_path_that_points_back_at_this_repos_githooks_is_skipped_not_looped(box, spelling):
    target = box.repo / ".githooks"
    if spelling == "same":
        value = target
    elif spelling == "relative":
        value = ".githooks"  # relative to the worktree, which is where git runs hooks
    elif spelling == "symlink":
        value = box.tmp / "link-to-githooks"
        value.symlink_to(target)
    else:
        value = f"{target}/"
    box.global_hooks_path(value)
    assert box.commit().returncode == 0
    assert box.push().returncode == 0
    assert [c for c in box.calls() if c.startswith("own:")] == ["own: uv run ruff check .", "own: uv run pytest -q"]


def test_tilde_in_the_global_path_is_expanded(box):
    gh = box.home / "hooks"
    box.global_hooks = gh
    box.global_hooks_path("~/hooks")
    box.global_hook("pre-commit", "exit 1\n")
    assert box.commit().returncode != 0 and "global: pre-commit" in box.calls()


@pytest.mark.parametrize("name", ["pre-commit", "commit-msg", "pre-push"])
def test_a_global_hook_that_exists_but_is_not_executable_fails_closed(wired, name):
    if name == "pre-push":
        assert wired.commit().returncode == 0  # something to push; the commit-side global hooks are still fine here
    wired.global_hook(name, mode=0o644)
    p = wired.push() if name == "pre-push" else wired.commit()
    assert p.returncode != 0 and "not executable" in p.stderr
    assert not any(c.startswith("own:") for c in wired.calls())


def test_a_global_hooks_dir_without_that_hook_is_not_an_error(box):
    box.global_hooks_path(box.global_hooks)
    box.global_hook("pre-commit")  # only one of the three exists
    assert box.commit().returncode == 0 and box.push().returncode == 0


def test_a_global_hooks_path_that_does_not_exist_is_not_an_error(box):
    box.global_hooks_path(box.tmp / "no-such-dir")
    assert box.commit().returncode == 0


def test_the_global_hook_runs_inside_the_repo_so_it_can_inspect_the_index(wired):
    wired.global_hook("pre-commit", f'git diff --cached --name-only > "{wired.tmp}/staged"\nexit 0\n')
    assert wired.commit().returncode == 0
    assert "f.txt" in (wired.tmp / "staged").read_text().split()


def test_every_hook_file_here_is_executable_and_uses_the_one_shared_chain_helper():
    names = {p.name for p in HOOKS.iterdir()}
    assert {"pre-commit", "commit-msg", "pre-push"} <= names
    for p in HOOKS.iterdir():
        assert p.stat().st_mode & stat.S_IXUSR, p
        if p.name in ("pre-commit", "commit-msg", "pre-push"):
            assert "_chain-global" in p.read_text(), f"{p.name} must chain to the global hook"
