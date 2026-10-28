import base64
import re
import subprocess
import sys
import textwrap

import pytest

from autopilot.apx import daemon as dm
from autopilot.apx.github import GitHubError

REPO = "RyanJHamby/stencil"
KIT = "a" * 40


def env(tmp_path, **over):
    key = tmp_path / "k.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    key.chmod(0o600)
    oauth = tmp_path / "oauth"
    oauth.write_text("tok-abc\n")
    oauth.chmod(0o600)
    e = {
        "APX_APP_ID": "1",
        "APX_KEY_PATH": str(key),
        "APX_INSTALLATIONS": f"{REPO}=11",
        "APX_OAUTH_FILE": str(oauth),
        "APX_KIT_REPO": "o/kit",
        "APX_KIT_REF": KIT,
        "APX_DB": str(tmp_path / "db.sqlite"),
        "APX_WORK": str(tmp_path / "work"),
    }
    e.update(over)
    return e


def test_settings_validation(tmp_path):
    s = dm.Settings.from_env(env(tmp_path))
    assert s.shadow and s.contexts(REPO) == {"guard": "apx / guard", "ci": "apx / build"}
    assert dm.Settings.from_env(env(tmp_path, APX_SHADOW="0")).contexts(REPO)["guard"] == "guard / guard"
    for bad in [
        {"APX_INSTALLATIONS": "RyanJHamby/resume=1"},  # outside scope
        {"APX_KIT_REF": "main"},  # not a pinned sha
        {"APX_INSTALLATIONS": f"{REPO}=notanint"},
    ]:
        with pytest.raises((dm.ConfigError, ValueError)):  # ValueError: non-int installation id
            dm.Settings.from_env(env(tmp_path, **bad))
    e = env(tmp_path)
    del e["APX_APP_ID"]
    with pytest.raises(dm.ConfigError):
        dm.Settings.from_env(e)


def test_secret_file_must_be_private(tmp_path):
    f = tmp_path / "s"
    f.write_text("x\n")
    f.chmod(0o644)
    with pytest.raises(dm.ConfigError):
        dm.read_secret_file(str(f))
    f.chmod(0o600)
    assert dm.read_secret_file(str(f)) == "x"


def test_routed_api_picks_token_by_repo_and_rejects_other_paths():
    used = []

    class Cache:
        def api_for(self, repo):
            return lambda m, p, b=None: used.append((repo, m, p)) or {}

    api = dm.routed_api(Cache())
    api("GET", f"/repos/{REPO}/pulls")
    assert used == [(REPO, "GET", f"/repos/{REPO}/pulls")]
    with pytest.raises(ValueError):
        api("GET", "/user")


def test_parse_detail():
    assert dm.parse_detail("model=opus effort=high turns=60") == {"model": "opus", "effort": "high", "turns": 60}
    assert dm.parse_detail("")["model"] == "sonnet"


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, text=True).stdout.strip()


def remote(tmp_path):
    w = tmp_path / "remote"
    w.mkdir()
    git(w, "init", "-q")
    git(w, "config", "user.email", "t@example.com")
    git(w, "config", "user.name", "t")
    (w / ".autopilot").mkdir()
    (w / ".autopilot" / "repo.yaml").write_text("commands:\n  - pytest -q\n")
    (w / "README.md").write_text("hi\n")
    git(w, "add", "-A")
    sha = git(w, "commit-tree", git(w, "write-tree"), "-m", "i")
    git(w, "update-ref", "refs/heads/main", sha)
    return w, sha


class Api:
    def __init__(self, sha):
        self.sha, self.calls = sha, []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/issues/4"):
            return {"title": "Add feature", "body": "please"}
        if path.endswith("/issues/4/comments?per_page=100"):
            return [{"user": {"login": "RyanJHamby"}, "body": "do it"}, {"user": {"login": "x"}, "body": "evil"}]
        if "contents/.autopilot/repo.yaml" in path:
            return {"content": base64.b64encode(b"commands:\n  - pytest -q\n").decode()}
        if "/actions/variables/" in path:
            raise GitHubError(404, path, "")
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": self.sha}}
        if "/git/commits/" in path:
            return {"tree": {"sha": "T0"}}
        if path.endswith("/git/blobs"):
            return {"sha": "B1"}
        if path.endswith("/git/trees"):
            return {"sha": "T1"}
        if path.endswith("/git/commits"):
            return {"sha": "C1"}
        if path.endswith("/pulls"):
            return {"number": 12}
        return {}


def fake_claude(tmp_path, body):
    f = tmp_path / "claude"
    f.write_text("#!" + sys.executable + "\nimport json, os, sys\n" + textwrap.dedent(body))
    f.chmod(0o755)
    return str(f)


def test_work_on_issue_end_to_end_with_fake_claude_and_api(tmp_path):
    rem, sha = remote(tmp_path)
    s = dm.Settings.from_env(env(tmp_path))
    api = Api(sha)
    b = fake_claude(
        tmp_path,
        """
        prompt = sys.argv[sys.argv.index("-p") + 1]
        assert "evil" not in prompt and "do it" in prompt   # stranger's comment filtered, owner's kept
        open("feature.py", "w").write("x = 1\\n")
        print(json.dumps({"result": "added feature", "num_turns": 3}))
        """,
    )
    r = dm.work_on_issue(s, api, lambda repo: None, REPO, 4, 99, "model=sonnet effort=low turns=10", binary=b, url=str(rem))
    assert r.ok and r.pr_number == 12 and r.turns == 3
    posts = [c for c in api.calls if c[0] == "POST"]
    ref = next(c for c in posts if c[1].endswith("/git/refs"))
    assert ref[2]["ref"] == "refs/heads/agent/4-99"
    pr = next(c for c in posts if c[1].endswith("/pulls"))
    assert pr[2]["title"] == "Add feature (agent #4)" and "Refs #4" in pr[2]["body"]


def test_work_on_issue_rejects_protected_path_without_any_write(tmp_path):
    rem, sha = remote(tmp_path)
    s = dm.Settings.from_env(env(tmp_path))
    api = Api(sha)
    b = fake_claude(
        tmp_path,
        """
        os.makedirs(".github/workflows", exist_ok=True)
        open(".github/workflows/x.yml", "w").write("on: push\\n")
        print(json.dumps({"result": "done", "num_turns": 1}))
        """,
    )
    r = dm.work_on_issue(s, api, lambda repo: None, REPO, 4, 100, "", binary=b, url=str(rem))
    assert not r.ok and "protected" in r.problems.lower()
    assert [c for c in api.calls if c[0] == "POST"] == []  # no blob, commit, ref or PR


def test_run_once_is_dry_run_unless_both_flags(tmp_path, monkeypatch):
    s = dm.Settings.from_env(env(tmp_path))
    writes = []

    def factory(token):
        def api(method, path, body=None):
            if method != "GET" or path.startswith("/app/"):
                if path.startswith("/app/"):
                    return {"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"}
                writes.append((method, path))
                return {}
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if "/check-runs" in path:
                return {"check_runs": []}
            if re.search(r"/pulls/\d+$", path):
                return {"mergeable_state": "clean", "labels": []}
            if "pulls?" in path:
                return (
                    [
                        {
                            "number": 1,
                            "head": {"ref": "agent/5-1", "sha": "s" * 40, "repo": {"full_name": REPO}},
                            "user": {"login": "RyanJHamby"},
                        }
                    ]
                    if "state=open" in path
                    else []
                )
            return []

        return api

    monkeypatch.delenv("APX_LIVE", raising=False)
    out = dm.run_once(s, live=True, api_factory=factory)  # --live but no APX_LIVE=1 -> still dry
    assert any(line.startswith("DRY-RUN check-pr") for line in out) and writes == []
    out2 = dm.run_once(s, live=False, api_factory=factory)
    assert writes == [] and any(line.startswith("DRY-RUN") for line in out2)


def test_merge_lane_is_off_in_shadow_mode_and_planned_after_cutover(tmp_path, monkeypatch):
    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"}
            assert method == "GET"
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if "/check-runs" in path:
                return {
                    "check_runs": [{"name": "guard / guard", "status": "completed"}, {"name": "build", "status": "completed"}]
                }
            if re.search(r"/pulls/\d+$", path):
                return {"mergeable_state": "clean", "labels": []}
            if "pulls?state=open" in path:
                return [
                    {
                        "number": 1,
                        "head": {"ref": "agent/5-1", "sha": "s" * 40, "repo": {"full_name": REPO}},
                        "user": {"login": "RyanJHamby"},
                    }
                ]
            return []

        return api

    monkeypatch.delenv("APX_LIVE", raising=False)
    shadow = dm.run_once(dm.Settings.from_env(env(tmp_path)), api_factory=factory)
    assert not any("automerge" in line for line in shadow)
    cut = dm.run_once(dm.Settings.from_env(env(tmp_path, APX_SHADOW="0")), api_factory=factory)
    assert any(line.startswith("DRY-RUN automerge") for line in cut)


def test_select_automerge_is_none_in_shadow_mode(tmp_path):
    shadow = dm.Settings.from_env(env(tmp_path))
    cut = dm.Settings.from_env(env(tmp_path, APX_SHADOW="0"))
    fn = lambda *a: (0, "")  # noqa: E731
    assert dm.select_automerge(shadow, fn) is None and dm.select_automerge(cut, fn) is fn


def test_make_report_needs_both_url_and_a_private_secret_file(tmp_path):
    assert dm.make_report(dm.Settings.from_env(env(tmp_path))) is None
    url_only = dm.Settings.from_env(env(tmp_path, APX_CONTROL_URL="https://cp.example/hook"))
    assert dm.make_report(url_only) is None  # a URL without a signing secret must not report unsigned
    sec = tmp_path / "wh"
    sec.write_text("s\n")
    sec.chmod(0o600)
    ok = dm.Settings.from_env(env(tmp_path, APX_CONTROL_URL="https://cp.example/hook", APX_WEBHOOK_SECRET_FILE=str(sec)))
    assert callable(dm.make_report(ok))
    sec.chmod(0o644)
    with pytest.raises(dm.ConfigError):
        dm.make_report(ok)


def test_single_instance_lock_blocks_a_second_pass_and_releases_after(tmp_path):
    with dm.single_instance(tmp_path) as first:
        assert first is True
        with dm.single_instance(tmp_path) as second:
            assert second is False  # overlapping tick must not run
    with dm.single_instance(tmp_path) as again:
        assert again is True  # released when the first pass ended


def test_run_once_skips_when_another_pass_holds_the_lock(tmp_path):
    s = dm.Settings.from_env(env(tmp_path))
    with dm.single_instance(s.work_dir):
        out = dm.run_once(s, api_factory=lambda t: (_ for _ in ()).throw(AssertionError("must not touch GitHub")))
    assert out == ["another apx pass is still running; skipping this tick"]


def test_launchd_template_is_valid_and_not_auto_started():
    import plistlib
    from pathlib import Path

    p = plistlib.loads((Path(__file__).resolve().parent.parent / "deploy/launchd/com.autopilot.apx.plist").read_bytes())
    assert p["Label"] == "com.autopilot.apx" and p["StartInterval"] == 120 and p["RunAtLoad"] is False
    cmd = p["ProgramArguments"][-1]
    assert "--once --live" in cmd and "APX_LIVE=1" in cmd
    assert "TOKEN" not in cmd.upper() and "SECRET" not in cmd.upper()  # settings are paths in ~/apx.env, never inline secrets
