import getpass
import json
import subprocess
import sys
from pathlib import Path

from autopilot.apx import sandbox, sandbox_job
from autopilot.apx.runas import Launcher

ROOT = Path(__file__).resolve().parent.parent
KIT = str(ROOT / "kit")
FAKE_KEY = "AK" + "IA" + "ABCDEFGHIJKLMNOP"  # assembled at runtime: this file holds nothing key-like
GIT_TOKEN = "opaque-git-token-" + "Zq7Wk" * 6


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, text=True).stdout.strip()


def make_remote(tmp_path, head_files):
    w = tmp_path / "remote"
    w.mkdir()
    git(w, "init", "-q")
    git(w, "config", "user.email", "t@example.com")
    git(w, "config", "user.name", "t")

    def commit(files, parent, ref):
        for n, t in files.items():
            (w / n).parent.mkdir(parents=True, exist_ok=True)
            (w / n).write_text(t)
        git(w, "add", "-A")
        sha = git(w, "commit-tree", git(w, "write-tree"), "-m", "c", *(["-p", parent] if parent else []))
        git(w, "update-ref", ref, sha)
        return sha

    base = commit({"README.md": "x\n", ".autopilot/repo.yaml": "mode: standard\n"}, None, "refs/heads/main")
    head = commit(head_files, base, "refs/heads/agent/1-1")
    return w, head


def lanes(tmp_path, sudo, remote, steps):
    (tmp_path / "ciwork").mkdir(exist_ok=True)  # the account setup script creates this in real use
    return sandbox.SandboxLanes(
        Launcher("apx-ci", sudo=sudo),
        base_branch="main",
        kit_dir=KIT,
        work_root=str(tmp_path / "ciwork"),
        python=sys.executable,
        code_dir=str(ROOT),
        home=str(tmp_path / "cihome"),
        token_for=lambda repo: GIT_TOKEN,
        steps_for=lambda repo: steps,
        toolchain_links=[],
        url_for=lambda repo: str(remote),
        expected_user=getpass.getuser(),  # the fake sudo does not change user
    )


def run_lane(L, head, ref="agent/1-1"):
    co = L.checkout("o/r", head)
    g_ok, g_out = L.guard(co, ref)
    return g_ok, g_out, L.ci(co)


def test_a_clean_pr_passes_guard_and_ci_inside_the_sandbox(fake_sudo, tmp_path):
    sudo, log = fake_sudo
    remote, head = make_remote(tmp_path, {"src/a.py": "x = 1\n", "probe.py": "import sys\nsys.exit(0)\n"})
    L = lanes(tmp_path, sudo, remote, [[f"{sys.executable} probe.py", ""]])
    g_ok, g_out, (c_ok, c_md) = run_lane(L, head)
    assert g_ok, g_out
    assert c_ok and "PASS" in c_md
    sent = json.dumps([json.loads(line) for line in log.read_text().splitlines()])
    assert GIT_TOKEN not in sent  # the token reached the job through the environment, never a command line
    assert "apx-ci" in sent  # and the job really was launched as the sandbox account


def test_a_rejected_pr_never_has_its_code_run(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    marker = tmp_path / "ran.txt"
    remote, head = make_remote(
        tmp_path, {"src/a.py": f'KEY = "{FAKE_KEY}"\n', "probe.py": f"open({str(marker)!r}, 'w').write('ran')\n"}
    )
    L = lanes(tmp_path, sudo, remote, [[f"{sys.executable} probe.py", ""]])
    g_ok, g_out, (c_ok, c_md) = run_lane(L, head)
    assert not g_ok and "secret" in g_out
    assert not c_ok and "not run" in c_md
    assert not marker.exists()  # the PR's CI command was never executed


def test_a_failing_ci_step_is_reported_with_its_step_lines(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, head = make_remote(tmp_path, {"probe.py": "import sys\nsys.exit(4)\n"})
    L = lanes(tmp_path, sudo, remote, [[f"{sys.executable} probe.py", ""]])
    g_ok, _, (c_ok, c_md) = run_lane(L, head)
    assert g_ok and not c_ok and "FAIL" in c_md and "exit 4" in c_md


def test_a_job_that_cannot_run_fails_both_checks_without_a_traceback(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, head = make_remote(tmp_path, {"a.txt": "x\n"})
    L = lanes(tmp_path, sudo, remote, [])
    L.base_branch = "no-such-branch"
    g_ok, g_out, (c_ok, c_md) = run_lane(L, head)
    assert not g_ok and g_out.startswith("sandbox job failed:") and "Traceback" not in g_out
    assert not c_ok


def test_a_hung_or_missing_sandbox_becomes_an_error_result(tmp_path):
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    slow.chmod(0o755)
    # a "sudo" that just sleeps stands in for a sandbox that never answers
    res = sandbox.run_in_sandbox(
        Launcher("apx-ci", sudo=str(slow)),
        {"work_root": str(tmp_path)},
        None,
        python=sys.executable,
        code_dir=str(ROOT),
        home=str(tmp_path),
        timeout=1,
    )
    assert "error" in res and "TimeoutExpired" in res["error"]
    res2 = sandbox.run_in_sandbox(
        Launcher("apx-ci", sudo=str(tmp_path / "missing")),
        {"work_root": str(tmp_path)},
        None,
        python=sys.executable,
        code_dir=str(ROOT),
        home=str(tmp_path),
    )
    assert "error" in res2


def test_job_main_prints_one_json_line_and_never_a_traceback(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("not json"))
    assert sandbox_job.main() == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and "error" in json.loads(out[0])


def test_a_missing_work_directory_gives_an_actionable_error(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    res = sandbox.run_in_sandbox(
        Launcher("apx-ci", sudo=sudo),
        {"work_root": str(tmp_path / "does-not-exist")},
        None,
        python=sys.executable,
        code_dir=str(ROOT),
        home=str(tmp_path),
    )
    assert "apx-ci-account.sh" in res["error"]


def test_the_git_token_reaches_the_job_through_the_environment_only(fake_sudo, tmp_path):
    sudo, log = fake_sudo
    echo = tmp_path / "echo-python"
    echo.write_text('#!/bin/sh\nprintf \'{"seen": "%s"}\\n\' "$APX_GIT_TOKEN"\n')
    echo.chmod(0o755)
    (tmp_path / "w").mkdir()
    res = sandbox.run_in_sandbox(
        Launcher("apx-ci", sudo=sudo),
        {"work_root": str(tmp_path / "w")},
        GIT_TOKEN,
        python=str(echo),
        code_dir=str(ROOT),
        home=str(tmp_path),
    )
    assert res == {"seen": GIT_TOKEN}  # delivered
    assert GIT_TOKEN not in log.read_text()  # never in a command line
    none = sandbox.run_in_sandbox(
        Launcher("apx-ci", sudo=sudo),
        {"work_root": str(tmp_path / "w")},
        None,
        python=str(echo),
        code_dir=str(ROOT),
        home=str(tmp_path),
    )
    assert none == {"seen": ""}  # no token, no variable


def test_the_job_reads_the_token_from_the_environment_and_prunes_old_scratch(tmp_path, monkeypatch):
    import io
    import os
    import time

    seen = {}
    monkeypatch.setenv("APX_GIT_TOKEN", GIT_TOKEN)
    monkeypatch.setattr(sandbox_job, "run_job", lambda req, token: seen.setdefault("token", token) and {"ok": 1})
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert sandbox_job.main() == 0 and seen["token"] == GIT_TOKEN

    root = tmp_path / "w"
    old = root / "pr-old"
    old.mkdir(parents=True)
    t = time.time() - 3 * 24 * 3600
    os.utime(old, (t, t))
    remote, head = make_remote(tmp_path, {"a.txt": "x\n"})
    req = {
        "repo": "o/r",
        "sha": head,
        "base_branch": "main",
        "head_ref": "agent/1-1",
        "kit_dir": KIT,
        "steps": [[f"{sys.executable} -c pass", ""]],
        "toolchain_links": [],
        "work_root": str(root),
        "url": str(remote),
    }
    monkeypatch.undo()
    sandbox_job.run_job(req, None)
    assert not old.exists()  # stale scratch from earlier jobs is cleared at the start of every job


def test_every_result_says_which_account_ran_it(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, head = make_remote(tmp_path, {"probe.py": "import sys\nsys.exit(0)\n"})
    L = lanes(tmp_path, sudo, remote, [[f"{sys.executable} probe.py", ""]])
    g_ok, g_out, (c_ok, c_md) = run_lane(L, head)
    assert g_ok and c_ok
    assert f"_ran as {getpass.getuser()}_" in g_out and f"_ran as {getpass.getuser()}_" in c_md


def test_a_job_that_ran_as_the_wrong_account_is_refused_and_its_pr_gets_no_credit(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    remote, head = make_remote(tmp_path, {"probe.py": "import sys\nsys.exit(0)\n"})
    L = lanes(tmp_path, sudo, remote, [[f"{sys.executable} probe.py", ""]])
    L.expected_user = "apx-ci"  # but the (fake) sudo ran it as the current user
    g_ok, g_out, (c_ok, c_md) = run_lane(L, head)
    assert not g_ok and "ran as" in g_out and "result refused" in g_out
    assert not c_ok and "not run" in c_md  # a clean guard/CI result from the wrong account is never accepted


def test_the_expected_account_defaults_to_the_launcher_account_not_anyone(tmp_path):
    L = sandbox.SandboxLanes(
        Launcher("apx-ci"),
        base_branch="main",
        kit_dir="/k",
        work_root="/w",
        python="/p",
        code_dir="/c",
        home="/h",
        token_for=lambda r: "t",
        steps_for=lambda r: [],
        toolchain_links=[],
    )
    assert L.expected_user == "apx-ci"
