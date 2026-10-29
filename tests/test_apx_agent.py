import getpass
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from autopilot.apx import agent_job, sandbox
from autopilot.apx.runas import Launcher

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_TOKEN = "sk-ant-" + "oat01-" + "Kp4_" * 12  # assembled at runtime; matches the token shape on purpose
GIT_TOKEN = "opaque-readonly-git-token-" + "Zq7Wk" * 5


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, text=True).stdout.strip()


def make_remote(tmp_path):
    w = tmp_path / "remote"
    w.mkdir()
    git(w, "init", "-q")
    git(w, "config", "user.email", "t@example.com")
    git(w, "config", "user.name", "t")
    (w / "README.md").write_text("hello\n")
    (w / "old.txt").write_text("remove me\n")
    (w / ".autopilot").mkdir()
    (w / ".autopilot" / "repo.yaml").write_text("mode: standard\n")
    git(w, "add", "-A")
    sha = git(w, "commit-tree", git(w, "write-tree"), "-m", "base")
    git(w, "update-ref", "refs/heads/main", sha)
    return w, sha


def fake_claude(tmp_path, body):
    """A stand-in for the claude CLI that records what its process could see, then edits the worktree."""
    seen = tmp_path / "claude-seen.json"
    f = tmp_path / "claude"
    f.write_text(
        "#!"
        + sys.executable
        + "\n"
        + textwrap.dedent(
            f"""
            import json, os, sys
            json.dump({{"env": sorted(os.environ), "token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"), "cwd": os.getcwd()}}, open({str(seen)!r}, "w"))
            """
        )
        + textwrap.dedent(body)
    )
    f.chmod(0o755)
    return str(f), seen


def request(tmp_path, remote, base, binary, **over):
    tok = tmp_path / "claude-oauth"
    tok.write_text(CLAUDE_TOKEN + "\n")
    (tmp_path / "agentwork").mkdir(exist_ok=True)
    req = {
        "repo": "o/r",
        "base_sha": base,
        "base_branch": "main",
        "issue": 5,
        "prompt": "do the thing",
        "model": "sonnet",
        "effort": "low",
        "max_turns": 10,
        "commands": ["pytest -q"],
        "work_root": str(tmp_path / "agentwork"),
        "binary": binary,
        "url": str(remote),
        "oauth_file": str(tok),
    }
    req.update(over)
    return req


EDIT = """
open("feature.py", "w").write("x = 1\\n")
os.remove("old.txt")
print(json.dumps({"result": "added feature, removed old", "num_turns": 4}))
"""


def run(tmp_path, sudo, req, **kw):
    return sandbox.run_agent_in_sandbox(
        Launcher("apx-agent", sudo=sudo),
        req,
        GIT_TOKEN,
        python=sys.executable,
        code_dir=str(ROOT),
        home=str(tmp_path / "agenthome"),
        expected_user=getpass.getuser(),  # the fake sudo does not change user
        **kw,
    )


def test_the_model_edits_a_checkout_and_its_changes_come_back_as_data(fake_sudo, tmp_path):
    sudo, log = fake_sudo
    remote, base = make_remote(tmp_path)
    binary, _ = fake_claude(tmp_path, EDIT)
    res, changes = run(tmp_path, sudo, request(tmp_path, remote, base, binary))
    assert res["ok"] and res["turns"] == 4 and "added feature" in res["summary"]
    by_path = {c.path: c for c in changes}
    assert by_path["feature.py"].content == b"x = 1\n" and by_path["feature.py"].mode == "100644"
    assert by_path["old.txt"].content is None  # a deletion comes back as a deletion
    sent = log.read_text()
    assert GIT_TOKEN not in sent and CLAUDE_TOKEN not in sent  # neither token was ever on a command line


def test_the_models_process_gets_its_own_token_and_no_github_credentials(fake_sudo, tmp_path, monkeypatch):
    sudo, _ = fake_sudo
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-the-model")
    remote, base = make_remote(tmp_path)
    binary, seen = fake_claude(tmp_path, EDIT)
    res, _ = run(tmp_path, sudo, request(tmp_path, remote, base, binary))
    assert res["ok"]
    saw = json.loads(seen.read_text())
    assert saw["token"] == CLAUDE_TOKEN  # it can use its own subscription token
    assert not {"APX_GIT_TOKEN", "GITHUB_TOKEN", "GH_TOKEN", "GIT_CONFIG_VALUE_0"} & set(
        saw["env"]
    )  # but holds no GitHub credential
    assert "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB" in saw["env"]


def test_a_patch_the_guard_rejects_returns_no_changes(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, base = make_remote(tmp_path)
    binary, _ = fake_claude(
        tmp_path,
        """
os.makedirs(".github/workflows", exist_ok=True)
open(".github/workflows/x.yml", "w").write("on: push\\n")
print(json.dumps({"result": "done", "num_turns": 1}))
""",
    )
    res, changes = run(tmp_path, sudo, request(tmp_path, remote, base, binary))
    assert not res["ok"] and changes == []
    assert any("protected" in v.lower() for v in res["violations"])  # nothing the guard rejected can be committed


def test_a_result_from_the_wrong_account_is_refused_and_yields_no_changes(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, base = make_remote(tmp_path)
    binary, _ = fake_claude(tmp_path, EDIT)
    res, changes = sandbox.run_agent_in_sandbox(
        Launcher("apx-agent", sudo=sudo),
        request(tmp_path, remote, base, binary),
        GIT_TOKEN,
        python=sys.executable,
        code_dir=str(ROOT),
        home=str(tmp_path / "h"),
        # expected_user defaults to apx-agent, but the fake sudo ran it as the current user
    )
    assert not res["ok"] and "result refused" in res["error"] and changes == []


def test_a_failing_model_run_is_reported_without_a_traceback(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, base = make_remote(tmp_path)
    binary, _ = fake_claude(tmp_path, 'sys.stderr.write("rate limited"); sys.exit(3)')
    res, changes = run(tmp_path, sudo, request(tmp_path, remote, base, binary))
    assert not res["ok"] and "claude exited 3" in res["error"] and "Traceback" not in res["error"] and changes == []
    bad, none = run(tmp_path, sudo, request(tmp_path, remote, base, binary, base_branch="no-such-branch"))
    assert not bad["ok"] and none == []


def test_an_oversized_result_is_refused_instead_of_streamed_through_the_orchestrator(tmp_path, monkeypatch):
    remote, base = make_remote(tmp_path)
    binary, _ = fake_claude(tmp_path, EDIT)
    monkeypatch.setattr(agent_job, "MAX_RESULT_BYTES", 4)
    out = agent_job.run_agent(request(tmp_path, remote, base, binary), None)
    assert not out["ok"] and out["changes"] == [] and "too large" in out["violations"][0]


def test_job_main_prints_one_json_line_and_never_a_traceback(monkeypatch, capsys):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert agent_job.main() == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and "error" in json.loads(lines[0])


def test_the_git_token_reaches_the_job_only_through_the_environment(monkeypatch, tmp_path):
    import io

    seen = {}
    monkeypatch.setenv("APX_GIT_TOKEN", GIT_TOKEN)
    monkeypatch.setattr(agent_job, "run_agent", lambda req, token: seen.setdefault("t", token) and {"ok": True})
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert agent_job.main() == 0 and seen["t"] == GIT_TOKEN


def test_stale_scratch_from_earlier_agent_jobs_is_cleared_at_the_start_of_each_job(tmp_path):
    import os
    import time

    remote, base = make_remote(tmp_path)
    binary, _ = fake_claude(tmp_path, EDIT)
    req = request(tmp_path, remote, base, binary)
    old = Path(req["work_root"]) / "agent-old"
    old.mkdir(parents=True)
    t = time.time() - 3 * 24 * 3600
    os.utime(old, (t, t))
    assert agent_job.run_agent(req, None)["ok"]
    assert not old.exists()
