"""deploy/linux/release.sh: move the Linux host to an exact commit of main. Run for real against temp dirs and a local bare remote.

The script runs its git steps as APX_USER; here that is the account running the tests, so no root and no setpriv are needed.
It replaces a hand sequence that broke three ways on the first real host (2026-11-14): the bootstrap clone lacked the commit,
the updater clone fetched nothing because the bootstrap clone's main had not moved, and `current` was pointed at a release
directory that did not exist yet."""

import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "deploy" / "linux" / "release.sh"
BOOTSTRAP = ROOT / "deploy" / "linux" / "bootstrap.sh"

# deploy/linux/release.sh is a Linux-host script (GNU coreutils: `mv -T`, `ln -T`, GNU stat). It runs on the Linux CI host and in
# Actions; on macOS the BSD tools reject those flags, so these tests are skipped there rather than made to pass on tools the
# script never runs with.
pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
    pytest.mark.skipif(sys.platform != "linux", reason="release.sh is a Linux-host script (GNU coreutils)"),
]


def git(*args, cwd=None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull}
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def commit(work: Path, name: str) -> str:
    (work / name).write_text(name)
    git("add", name, cwd=work)
    git("-c", "commit.gpgsign=false", "commit", "-qm", name, cwd=work)
    return git("rev-parse", "HEAD", cwd=work)


class Host:
    """A bare remote standing in for GitHub, and a shared tree laid out as the first bootstrap leaves it."""

    def __init__(self, tmp: Path):
        self.remote = tmp / "remote.git"
        self.work = tmp / "work"
        self.shared = tmp / "srv"
        git("init", "-q", "--bare", "-b", "main", str(self.remote))
        git("clone", "-q", str(self.remote), str(self.work))
        git("checkout", "-q", "-b", "main", cwd=self.work)
        self.first = commit(self.work, "a")
        git("push", "-q", "origin", "main", cwd=self.work)
        self.shared.mkdir()
        (self.shared / "releases").mkdir()
        git("clone", "-q", str(self.remote), str(self.shared / "autopilot"))
        git("clone", "-q", "--no-hardlinks", str(self.shared / "autopilot"), str(self.shared / "releases" / self.first))
        git("clone", "-q", "--no-hardlinks", str(self.shared / "autopilot"), str(self.shared / "updater"))
        os.symlink(f"releases/{self.first}", self.shared / "current")

    def push_main(self, name: str) -> str:
        sha = commit(self.work, name)
        git("push", "-q", "origin", "main", cwd=self.work)
        return sha

    def run(self, sha: str, **extra) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "SHARED": str(self.shared),
            "APX_SHA": sha,
            "APX_USER": getpass.getuser(),
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        env |= extra
        return subprocess.run(["bash", str(RELEASE)], env=env, capture_output=True, text=True)

    def current(self) -> str:
        return os.readlink(self.shared / "current")

    def assert_current_resolves(self):
        cur = self.shared / "current"
        assert cur.is_symlink() and cur.resolve().is_dir(), f"current dangles: {os.readlink(cur)}"
        assert not (self.shared / ".current.new").exists() and not (self.shared / ".current.new").is_symlink()


@pytest.fixture
def host(tmp_path):
    return Host(tmp_path)


def test_script_is_valid_bash_executable_and_shellcheck_clean():
    assert subprocess.run(["bash", "-n", str(RELEASE)], capture_output=True).returncode == 0
    assert RELEASE.stat().st_mode & 0o111
    if shutil.which("shellcheck"):
        r = subprocess.run(["shellcheck", str(RELEASE)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("bad", ["", "abc123", "HEAD", "main", "0" * 39, "A" * 40, "0" * 40 + " ; true"])
def test_anything_but_a_full_lowercase_sha_is_refused_before_any_change(host, bad):
    r = host.run(bad)
    assert r.returncode != 0 and "40-character" in r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}"


def test_a_new_main_commit_is_fetched_into_both_clones_built_verified_and_switched_to(host):
    new = host.push_main("b")  # neither clone has it yet: the two fetch failures from the first host
    r = host.run(new)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{new}"
    assert git("rev-parse", "HEAD", cwd=host.shared / "current") == new
    assert git("rev-parse", "HEAD", cwd=host.shared / "updater") == new
    assert git("rev-parse", "HEAD", cwd=host.shared / "autopilot") == new
    assert git("rev-parse", "refs/heads/main", cwd=host.shared / "autopilot") == new, "the updater fetches this clone's main"
    assert os.readlink(host.shared / "previous") == f"releases/{host.first}"
    assert f"releases/{host.first}" in r.stdout and "rollback" in r.stdout.lower()
    host.assert_current_resolves()
    assert not [p for p in (host.shared / "releases").iterdir() if p.name.startswith(".")], "no staging dir left behind"


def test_running_it_again_for_the_same_sha_changes_nothing_and_keeps_the_rollback_target(host):
    new = host.push_main("b")
    assert host.run(new).returncode == 0
    r = host.run(new)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{new}"
    assert os.readlink(host.shared / "previous") == f"releases/{host.first}"
    host.assert_current_resolves()


def test_rolling_back_to_the_previous_release_is_the_same_command(host):
    new = host.push_main("b")
    assert host.run(new).returncode == 0
    r = host.run(host.first)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}"
    assert git("rev-parse", "HEAD", cwd=host.shared / "updater") == host.first
    host.assert_current_resolves()


def test_a_commit_not_on_main_is_refused_and_nothing_moves(host):
    git("checkout", "-q", "-b", "side", cwd=host.work)
    side = commit(host.work, "evil")
    git("push", "-q", "origin", "side", cwd=host.work)
    r = host.run(side)
    assert r.returncode != 0 and "not on origin/main" in r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}"
    assert not (host.shared / "releases" / side).exists()
    assert git("rev-parse", "HEAD", cwd=host.shared / "updater") == host.first
    assert not (host.shared / "previous").exists()
    host.assert_current_resolves()


def test_a_sha_that_does_not_exist_is_refused(host):
    r = host.run("f" * 40)
    assert r.returncode != 0 and "not on origin/main" in r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}"
    host.assert_current_resolves()


def test_a_release_dir_whose_head_is_not_its_name_is_refused_and_current_is_untouched(host):
    new = host.push_main("b")
    stale = host.shared / "releases" / new
    git(
        "clone", "-q", "--no-hardlinks", str(host.shared / "autopilot"), str(stale)
    )  # sits at the first commit, named as the new one
    r = host.run(new)
    assert r.returncode != 0 and "HEAD" in r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}"
    assert git("rev-parse", "HEAD", cwd=stale) == host.first, "the bad dir is reported, not repaired or deleted"
    assert not (host.shared / "previous").exists()
    host.assert_current_resolves()


def test_a_release_dir_that_is_not_a_git_checkout_is_refused(host):
    new = host.push_main("b")
    (host.shared / "releases" / new).mkdir()
    r = host.run(new)
    assert r.returncode != 0
    assert host.current() == f"releases/{host.first}"
    host.assert_current_resolves()


def planted_rollback(host, rel: str, *, ignore: str = "") -> tuple[str, Path]:
    """Move to a new commit, then plant `rel` in the old (previous) release, as an account that can write the shared tree could."""
    new = host.push_main("b")
    assert host.run(new).returncode == 0
    old = host.shared / "releases" / host.first
    if ignore:
        (old / ".git" / "info").mkdir(exist_ok=True)
        (old / ".git" / "info" / "exclude").write_text(ignore + "\n")
    (old / rel).parent.mkdir(parents=True, exist_ok=True)
    (old / rel).write_text("import os  # runs at interpreter start\n")
    return new, old / rel


@pytest.mark.parametrize("rel", ["src/sitecustomize.py", "src/autopilot/json.py", "evil.pth"])
def test_an_untracked_file_in_an_existing_release_is_refused_and_current_is_untouched(host, rel):
    new, planted = planted_rollback(host, rel)
    r = host.run(host.first)
    assert r.returncode != 0 and "untracked or ignored" in r.stdout and "move it aside" in r.stdout.lower(), r.stdout + r.stderr
    assert host.current() == f"releases/{new}", "current never moves to a release with extra files"
    assert planted.exists(), "the dir is reported for a look, never cleaned or deleted"
    host.assert_current_resolves()


def test_an_ignored_file_in_an_existing_release_is_refused_too(host):
    """__pycache__/, *.egg-info and the like are gitignored, and a planted .pyc or .pth there is just as live as a .py file."""
    new, planted = planted_rollback(host, "src/__pycache__/os.cpython-312.pyc", ignore="__pycache__/")
    assert git("status", "--porcelain", "--untracked-files=all", cwd=planted.parents[2]) == "", "invisible without --ignored"
    r = host.run(host.first)
    assert r.returncode != 0 and "untracked or ignored" in r.stdout, r.stdout + r.stderr
    assert host.current() == f"releases/{new}" and planted.exists()


def test_a_clean_existing_release_is_reused_in_place(host):
    new = host.push_main("b")
    assert host.run(new).returncode == 0
    old = host.shared / "releases" / host.first
    inode = old.stat().st_ino
    r = host.run(host.first)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}" and old.stat().st_ino == inode, "reused, not rebuilt"


def test_after_moving_a_dirty_release_aside_the_same_command_rebuilds_it(host):
    new, planted = planted_rollback(host, "src/sitecustomize.py")
    old = host.shared / "releases" / host.first
    old.rename(host.shared / f"{host.first}.dirty")  # what the refusal tells the operator to do (outside releases/)
    r = host.run(host.first)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{host.first}" and not (old / "src" / "sitecustomize.py").exists()


def test_a_first_install_with_no_current_and_no_updater_creates_both(host):
    os.unlink(host.shared / "current")
    shutil.rmtree(host.shared / "updater")
    new = host.push_main("b")
    r = host.run(new)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{new}"
    assert git("rev-parse", "HEAD", cwd=host.shared / "updater") == new
    assert not (host.shared / "previous").exists()
    host.assert_current_resolves()


def test_a_dangling_current_left_by_hand_is_replaced_not_recorded_as_the_rollback(host):
    os.unlink(host.shared / "current")
    os.symlink("releases/" + "e" * 40, host.shared / "current")
    new = host.push_main("b")
    r = host.run(new)
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.current() == f"releases/{new}"
    assert not (host.shared / "previous").exists(), "a dangling target is no rollback"
    host.assert_current_resolves()


def test_current_that_is_a_real_directory_is_refused(host):
    os.unlink(host.shared / "current")
    (host.shared / "current").mkdir()
    new = host.push_main("b")
    r = host.run(new)
    assert r.returncode != 0 and "not a symlink" in r.stdout + r.stderr
    assert (host.shared / "current").is_dir() and not (host.shared / "current").is_symlink()


def test_dry_run_prints_the_steps_and_changes_nothing(host):
    new = host.push_main("b")
    before = git("rev-parse", "refs/remotes/origin/main", cwd=host.shared / "autopilot")
    r = host.run(new, DRY_RUN="1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRY-RUN" in r.stdout and "fetch" in r.stdout and "mv -T" in r.stdout
    assert host.current() == f"releases/{host.first}"
    assert not (host.shared / "releases" / new).exists()
    assert git("rev-parse", "refs/remotes/origin/main", cwd=host.shared / "autopilot") == before, "a dry run fetches nothing"


def test_the_release_is_made_readable_by_the_sandbox_even_under_a_tight_umask(host):
    new = host.push_main("b")
    env = {
        **os.environ,
        "SHARED": str(host.shared),
        "APX_SHA": new,
        "APX_USER": getpass.getuser(),
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    r = subprocess.run(["bash", "-c", f"umask 077; exec bash {RELEASE}"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    mode = (host.shared / "releases" / new / "b").stat().st_mode
    assert mode & 0o044 == 0o044 and mode & 0o022 == 0


# --- how bootstrap uses it -----------------------------------------------------------------------------------------------------------


def code(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))


def test_bootstrap_hands_an_apx_sha_to_the_release_script_before_it_renders_the_rules():
    c = code(BOOTSTRAP)
    assert 'bash "$here/release.sh"' in c
    assert c.index('bash "$here/release.sh"') < c.index("autopilot.apx.nftrules nft")
    assert 'checkout -q --detach "$WANT_SHA"' not in c, "the unfetched checkout that failed on the first host is gone"


def test_the_switch_is_atomic_and_checked_before_it_happens():
    c = code(RELEASE)
    assert "mv -T" in c and "ln -sfn" in c
    assert c.index("merge-base --is-ancestor") < c.index("rev-parse HEAD") < c.index("mv -T")


def test_what_runs_from_a_release_writes_no_bytecode_into_it():
    """release.sh refuses ignored files too, so __pycache__ written by the daemon or the rule renderer would block every rollback."""
    unit = (ROOT / "deploy" / "linux" / "systemd" / "apx.service").read_text()
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit and "WorkingDirectory=/srv/apx/current" in unit
    assert 'render_env=(env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$SHARED/current/src")' in code(BOOTSTRAP)
