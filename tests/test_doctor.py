"""Characterization tests for `ap doctor` (cmd_doctor).

They pin down what doctor does, so refactoring it into the standard engine can't change behavior by accident. Two
tests were written as `test_known_gap_*`, recording that doctor missed dotted version tags and workflows autopilot
didn't write; the engine fixed both, and those two were flipped on purpose in the same change as the fix.
"""

import json
import re
import subprocess

import pytest

from autopilot import claude_floor, cli


def make_repo(tmp_path, files=None):
    def g(*a):
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    g("init", "-q", "-b", "main")
    for k, v in (files or {"pyproject.toml": "[project]\nname='x'\n"}).items():
        (tmp_path / k).write_text(v)
    g("add", ".")
    g("commit", "-qm", "base")
    return tmp_path


class FakeGh:
    """Stands in for `subprocess` inside cli. Only `gh` is answered (local `git` passes through), so no test touches
    the network or the real account.

    `ruleset` and `secrets` are the stdout of `gh api .../rulesets` and `gh secret list`. None means gh failed
    (not installed, not logged in), which doctor treats as "can't tell" and skips.
    """

    def __init__(self, ruleset=None, secrets=None):
        self.ruleset, self.secrets, self.calls = ruleset, secrets, []

    def run(self, cmd, **kwargs):
        if cmd[0] != "gh":
            assert cmd[0] == "git", f"doctor ran something other than git or gh: {cmd}"
            return subprocess.run(cmd, **kwargs)  # local git only, so it stays hermetic
        self.calls.append(cmd)
        out = {"api": self.ruleset, "secret": self.secrets}.get(cmd[1])
        if out is None:
            return subprocess.CompletedProcess(cmd, 1, "", "gh unavailable")
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def __getattr__(self, name):
        return getattr(subprocess, name)


@pytest.fixture(autouse=True)
def claude_at_floor(monkeypatch):
    """Doctor now checks the machine's Claude Code version; these tests are about repos, so the machine is fine unless a test says not."""
    monkeypatch.setattr(claude_floor, "probe", lambda binary="claude", run=None: "2.1.323 (Claude Code)\n")


@pytest.fixture
def repo(tmp_path):
    root = make_repo(tmp_path)
    cli.init_repo(root, "A", "standard")
    return root


def doctor(root, monkeypatch, capsys, gh=None):
    monkeypatch.setattr(cli, "subprocess", gh or FakeGh())
    code = cli.main(["doctor", str(root)])
    return code, capsys.readouterr().out


def test_a_repo_without_autopilot_fails(tmp_path, monkeypatch, capsys):
    code, out = doctor(make_repo(tmp_path), monkeypatch, capsys)
    assert code == 1
    assert "FAIL not installed" in out


def test_a_fresh_install_passes_when_gh_cannot_answer(repo, monkeypatch, capsys):
    gh = FakeGh()
    code, out = doctor(repo, monkeypatch, capsys, gh)
    assert code == 0
    assert "FAIL" not in out and "WARN" not in out
    assert "Manual checks" in out
    assert [c[1] for c in gh.calls] == ["api", "secret"]


def test_a_missing_installed_file_fails(repo, monkeypatch, capsys):
    (repo / ".autopilot/guard.py").unlink()
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1
    assert "FAIL missing .autopilot/guard.py" in out


def test_a_modified_installed_file_only_warns(repo, monkeypatch, capsys):
    with (repo / ".autopilot/CONSTITUTION.md").open("a") as f:
        f.write("\nlocal edit\n")
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 0
    assert "WARN modified since install: .autopilot/CONSTITUTION.md" in out


def test_an_old_kit_version_only_warns(repo, monkeypatch, capsys):
    path = repo / ".autopilot/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["kit_version"] = "0.0.1"
    path.write_text(json.dumps(manifest))
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 0
    assert "WARN kit 0.0.1" in out


def _unpin_first_action(repo, replacement):
    path = repo / ".github/workflows/guard.yml"
    text = path.read_text()
    assert re.search(r"@[0-9a-f]{40}", text), "fixture expects a SHA-pinned action in guard.yml"
    path.write_text(re.sub(r"@[0-9a-f]{40}", replacement, text, count=1))


def test_an_unpinned_autopilot_action_fails(repo, monkeypatch, capsys):
    _unpin_first_action(repo, "@main")
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1
    assert "FAIL guard.yml: action not pinned to a SHA" in out


def test_a_dotted_version_tag_is_flagged_as_unpinned(repo, monkeypatch, capsys):
    _unpin_first_action(repo, "@v4.2.2")
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1
    assert "FAIL guard.yml: action not pinned to a SHA" in out


def test_workflows_not_written_by_autopilot_are_pin_checked_too(repo, monkeypatch, capsys):
    (repo / ".github/workflows/ci.yml").write_text(
        "name: ci\non: push\njobs:\n  t:\n    steps:\n      - uses: actions/checkout@main\n"
    )
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1
    assert "FAIL ci.yml: action not pinned to a SHA" in out


def test_a_workflow_that_hands_secrets_to_pr_code_fails(repo, monkeypatch, capsys):
    (repo / ".github/workflows/deploy.yml").write_text(
        "name: deploy\non:\n  push:\n  pull_request:\njobs:\n  t:\n    steps:\n      - run: echo ${{ secrets.DEPLOY_KEY }}\n"
    )
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1
    assert "FAIL deploy.yml: uses repo secrets on pull_request" in out


def test_ci_that_never_runs_on_push_only_warns(repo, monkeypatch, capsys):
    (repo / ".github/workflows/ci.yml").write_text("name: ci\non:\n  pull_request:\njobs:\n  t:\n    steps:\n      - run: true\n")
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 0
    assert "WARN no CI workflow triggers on push" in out


def test_claude_md_that_does_not_import_agents_md_only_warns(repo, monkeypatch, capsys):
    (repo / "CLAUDE.md").write_text("# mine\n")
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 0
    assert "WARN CLAUDE.md does not import AGENTS.md" in out


def test_a_missing_ruleset_fails_when_gh_can_see_rulesets(repo, monkeypatch, capsys):
    code, out = doctor(repo, monkeypatch, capsys, FakeGh(ruleset="some-other-ruleset\n"))
    assert code == 1
    assert "FAIL ruleset autopilot-main not applied" in out


def test_an_applied_ruleset_passes(repo, monkeypatch, capsys):
    code, out = doctor(repo, monkeypatch, capsys, FakeGh(ruleset="autopilot-main\n"))
    assert code == 0
    assert "FAIL ruleset" not in out


def test_a_missing_secret_only_warns_when_gh_can_see_secrets(repo, monkeypatch, capsys):
    code, out = doctor(repo, monkeypatch, capsys, FakeGh(secrets="OTHER_SECRET\t2026-01-01\n"))
    assert code == 0
    assert "WARN secret CLAUDE_CODE_OAUTH_TOKEN not set" in out


# --- the Claude Code version floor (W0-19): one machine-level check, printed once ---
def test_doctor_checks_the_claude_version_once_for_all_repos(tmp_path, monkeypatch, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for r in (a, b):
        make_repo(r)
        cli.init_repo(r, "A", "standard")
    calls = []
    monkeypatch.setattr(claude_floor, "probe", lambda binary="claude", run=None: calls.append(binary) or "2.1.323 (Claude Code)\n")
    monkeypatch.setattr(cli, "subprocess", FakeGh())
    cli.main(["doctor", str(a), str(b)])
    out = capsys.readouterr().out
    assert len(calls) == 1
    assert "2.1.323" in out and "2.1.302" in out
    assert out.index("2.1.323") < out.index("== a")  # printed first, once, not per repo


def test_doctor_fails_when_claude_is_below_the_floor(repo, monkeypatch, capsys):
    monkeypatch.setattr(claude_floor, "probe", lambda binary="claude", run=None: "2.1.301 (Claude Code)\n")
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1
    assert re.search(r"FAIL.*claude.*2\.1\.301.*2\.1\.302", out)


def test_doctor_fails_when_claude_cannot_be_run(repo, monkeypatch, capsys):
    def boom(binary="claude", run=None):
        raise claude_floor.FloorError("claude is not installed")

    monkeypatch.setattr(claude_floor, "probe", boom)
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1 and re.search(r"FAIL.*claude", out)


def test_doctor_fails_when_the_floor_file_is_broken(repo, monkeypatch, capsys, tmp_path):
    bad = tmp_path / "claude.yaml"
    bad.write_text("min_version: nope\n")
    monkeypatch.setattr(claude_floor, "FLOOR_FILE", bad)
    code, out = doctor(repo, monkeypatch, capsys)
    assert code == 1 and "floor" in out.lower()


def test_doctor_passes_at_the_floor_and_says_so(repo, monkeypatch, capsys):
    monkeypatch.setattr(claude_floor, "probe", lambda binary="claude", run=None: "2.1.302 (Claude Code)\n")
    code, out = doctor(repo, monkeypatch, capsys)
    assert re.search(r"OK.*claude.*2\.1\.302", out)
