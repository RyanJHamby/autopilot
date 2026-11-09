"""`ap new --create`: signed commit, GitHub repo, ruleset, and a read-back of the ruleset. Everything outward is faked."""

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from autopilot import cli
from autopilot.scaffold import core, new

PORTFOLIO = {"owner": "octo", "holder": "Octo Cat"}


def made(tmp_path, kind="cli", public=False):
    path, _, _ = new.create(tmp_path, "my-tool", kind, "octo", "Octo Cat", public)
    return path


class FakeGH:
    """Stands in for subprocess.run. Records every command; `gh api` is a tiny in-memory rulesets endpoint."""

    def __init__(self, *, gpgsign="true", key="KEY", create_rc=0, post_rc=0, narrow=None, enforcement="active"):
        self.calls, self.stored = [], None
        self.gpgsign, self.key, self.create_rc, self.post_rc = gpgsign, key, create_rc, post_rc
        self.narrow, self.enforcement = narrow, enforcement  # narrow: a rule type GitHub "silently drops"

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))

        def ok(out=""):
            return SimpleNamespace(returncode=0, stdout=out, stderr="")

        def fail(err):
            return SimpleNamespace(returncode=1, stdout="", stderr=err)

        if cmd[:2] == ["git", "-C"] and "config" in cmd:
            return ok({"commit.gpgsign": self.gpgsign, "user.signingkey": self.key}[cmd[-1]] + "\n")
        if cmd[0] == "git":
            return ok()
        if cmd[:3] == ["gh", "repo", "create"]:
            return ok() if self.create_rc == 0 else fail("name already exists")
        if cmd[0] == "gh" and cmd[1] == "api":
            url = cmd[2]
            if "--method" in cmd:
                if self.post_rc:
                    return fail("HTTP 403: Upgrade to GitHub Pro or make this repository public to enable this feature.")
                body = json.loads(kw["input"])
                body["id"], body["enforcement"] = 7, self.enforcement
                body["rules"] = [r for r in body["rules"] if r["type"] != self.narrow]
                self.stored = body
                return ok("{}")
            if url.endswith("/rulesets"):
                return ok(json.dumps([{"id": 7, "name": self.stored["name"]}] if self.stored else []))
            if url.endswith("/rulesets/7"):
                return ok(json.dumps(self.stored))
        raise AssertionError(f"unexpected command {cmd}")

    def outward(self):
        return [c for c in self.calls if c[0] == "gh"]

    def committed(self):
        return any(" commit " in " ".join(c) for c in self.calls)


def quiet(*_):
    return None


def real_git_init_else(gh, tmp_path):
    def run(cmd, **kw):  # the repo is really created and initialised; everything outward is the fake
        return subprocess.run(cmd, **kw) if cmd[:4] == ["git", "-C", str(tmp_path / "my-tool"), "init"] else gh(cmd, **kw)

    return run


@pytest.mark.parametrize("kind", new.NEW_KINDS)
def test_the_required_check_is_a_job_the_generated_ci_reports(tmp_path, kind):
    # A required check that never reports blocks every merge, so the name the ruleset requires must be a real job id.
    path = made(tmp_path, kind=kind)
    assert core.required_check(kind) in new.workflow_jobs(path)


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_the_generic_make_check_passes_a_clean_repo_and_fails_on_secrets(tmp_path):
    path = made(tmp_path, kind="notes")

    def git(*a):
        subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True, check=True)

    def mk():
        return subprocess.run(["make", "-C", str(path), "check"], capture_output=True, text=True)

    git("add", "-A")
    assert mk().returncode == 0, "a clean new repo must pass its own check"
    (path / ".env.example").write_text("TOKEN=\n")  # an example env file is fine
    git("add", "-A")
    assert mk().returncode == 0
    (path / ".env").write_text("TOKEN=x\n")
    assert mk().returncode == 0, "an ignored .env is not tracked, so it is not this check's business"
    git("add", "-f", ".env")  # someone forces it in: that is what the check exists to catch
    r = mk()
    assert r.returncode != 0 and ".env" in r.stdout
    git("rm", "-q", "--cached", ".env")
    marker = "-" * 5 + "BEGIN " + "RSA PRIVATE" + " KEY" + "-" * 5  # built from pieces: no literal header in this file
    (path / "notes.txt").write_text(marker + "\nabc\n")
    git("add", "-A")
    r = mk()
    assert r.returncode != 0 and "private key" in r.stdout


def test_create_signs_commits_creates_pushes_then_protects_and_reads_back(tmp_path):
    path, gh = made(tmp_path), FakeGH()
    slug = new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)
    assert slug == "octo/my-tool"
    cmds = [" ".join(c) for c in gh.calls]
    commit = next(c for c in cmds if " commit " in c)
    assert "-S" in commit.split()
    create = next(c for c in cmds if c.startswith("gh repo create"))
    assert "octo/my-tool --private" in create and "--push" in create

    def idx(s):
        return next(i for i, c in enumerate(cmds) if s in c)

    # order: commit -> create -> ruleset applied -> read back (there are GETs after the POST)
    assert idx(" commit ") < idx("gh repo create") < idx("--method POST") < len(cmds) - 1
    assert gh.stored["name"] == "autopilot-main"
    ctxs = [
        c["context"]
        for r in gh.stored["rules"]
        if r["type"] == "required_status_checks"
        for c in r["parameters"]["required_status_checks"]
    ]
    assert ctxs == ["test"], "a standalone repo requires its own CI job and NOT autopilot's `guard`"


@pytest.mark.parametrize("gh", [FakeGH(gpgsign="false"), FakeGH(key="")], ids=["gpgsign-off", "no-signing-key"])
def test_create_refuses_before_anything_outward_when_signing_is_off(tmp_path, gh):
    path = made(tmp_path)
    with pytest.raises(new.PublishError, match="signing"):
        new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)
    assert gh.outward() == [] and not gh.committed()


def test_create_refuses_before_committing_when_the_required_check_is_not_a_job(tmp_path):
    path, gh = made(tmp_path), FakeGH()
    (path / ".github/workflows/ci.yml").write_text("name: ci\non: push\njobs:\n  other:\n    runs-on: ubuntu-latest\n    steps: []\n")
    with pytest.raises(new.PublishError, match="never reports blocks every merge"):
        new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)
    assert gh.outward() == [] and not gh.committed()


def test_a_failed_repo_create_stops_before_the_ruleset_and_says_what_to_check(tmp_path):
    path, gh = made(tmp_path), FakeGH(create_rc=1)
    with pytest.raises(new.PublishError, match="octo/my-tool"):
        new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)
    assert not any(c[:2] == ["gh", "api"] for c in gh.calls)


def test_a_refused_ruleset_says_the_repo_exists_unprotected_and_how_to_fix_it(tmp_path):
    path, gh = made(tmp_path), FakeGH(post_rc=1)
    with pytest.raises(new.PublishError) as e:
        new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)
    msg = str(e.value)
    assert "UNPROTECTED" in msg and "ap ruleset octo/my-tool --standalone --check test --apply" in msg
    assert "free GitHub plan" in msg
    # the cause GitHub gave must reach the user, not be replaced by a vaguer read-back failure
    assert "applying the ruleset failed" in msg and "Upgrade to GitHub Pro" in msg


@pytest.mark.parametrize("dropped", ["required_signatures", "pull_request", "non_fast_forward", "deletion", "required_status_checks"])
def test_a_ruleset_that_reads_back_narrower_than_asked_is_an_error(tmp_path, dropped):
    path, gh = made(tmp_path), FakeGH(narrow=dropped)
    with pytest.raises(new.PublishError, match="did not read back"):
        new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)


def test_a_ruleset_that_is_not_active_is_an_error(tmp_path):
    path, gh = made(tmp_path), FakeGH(enforcement="evaluate")
    with pytest.raises(new.PublishError, match="not 'active'"):
        new.publish(path, "my-tool", "octo", "cli", False, run=gh, say=quiet)


def test_the_command_with_create_reports_success_and_the_remaining_steps(tmp_path, capsys):
    ns = SimpleNamespace(name="my-tool", kind="cli", public=False, root=str(tmp_path), owner=None, holder=None, create=True)
    assert new.cmd_new(ns, load_portfolio=lambda: PORTFOLIO, run=real_git_init_else(FakeGH(), tmp_path)) == 0
    out = capsys.readouterr().out
    assert "created, pushed and protected" in out and "pow init" in out and "discovers the repo from GitHub" in out


def test_the_command_with_create_keeps_the_directory_and_exits_1_on_failure(tmp_path, capsys):
    ns = SimpleNamespace(name="my-tool", kind="cli", public=False, root=str(tmp_path), owner=None, holder=None, create=True)
    assert new.cmd_new(ns, load_portfolio=lambda: PORTFOLIO, run=real_git_init_else(FakeGH(gpgsign="false"), tmp_path)) == 1
    assert "signing" in capsys.readouterr().out and (tmp_path / "my-tool").is_dir()


def test_without_create_nothing_outward_is_ever_called(tmp_path):
    gh = FakeGH()
    ns = SimpleNamespace(name="my-tool", kind="cli", public=False, root=str(tmp_path), owner=None, holder=None)  # no `create`
    new.cmd_new(ns, load_portfolio=lambda: PORTFOLIO, run=real_git_init_else(gh, tmp_path))
    assert gh.calls == []


# ---- the ruleset helpers and `ap ruleset --standalone` ----------------------------------------------------------------------------
def test_verify_ruleset_accepts_what_apply_wrote_and_names_every_problem():
    gh = FakeGH()
    assert cli.apply_ruleset("o/r", ["test"], run=gh)[0] == 0
    assert cli.verify_ruleset("o/r", ["test"], run=gh) == []
    assert any("'lint'" in p for p in cli.verify_ruleset("o/r", ["test", "lint"], run=gh))  # a check nobody asked GitHub for
    assert "not present" in cli.verify_ruleset("o/r", ["test"], run=FakeGH())[0]


def test_apply_ruleset_updates_in_place_instead_of_posting_a_duplicate():
    gh = FakeGH()
    cli.apply_ruleset("o/r", ["test"], run=gh)
    cli.apply_ruleset("o/r", ["test"], run=gh)
    assert [c[c.index("--method") + 1] for c in gh.calls if "--method" in c] == ["POST", "PUT"]


def test_ruleset_standalone_requires_a_check_and_never_requires_guard(capsys):
    ns = SimpleNamespace(repo="octo/x", check=[], central=False, apply=False, standalone=True)
    assert cli.cmd_ruleset(ns) == 1 and "--check" in capsys.readouterr().out
    ns = SimpleNamespace(repo="octo/x", check=["test"], central=False, apply=False, standalone=True)
    assert cli.cmd_ruleset(ns) == 0
    out = capsys.readouterr().out
    assert '"context": "test"' in out and '"guard"' not in out
    managed = SimpleNamespace(repo="octo/x", check=["ci"], central=False, apply=False)  # onboard --finish builds no `standalone`
    assert cli.cmd_ruleset(managed) == 0 and '"context": "guard"' in capsys.readouterr().out
