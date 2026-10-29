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


def test_routed_api_routes_the_bare_repo_path_too_not_just_paths_below_it():
    used = []

    class Cache:
        def api_for(self, repo):
            return lambda m, p, b=None: used.append((repo, p)) or {"private": True}

    api = dm.routed_api(Cache())
    assert api("GET", f"/repos/{REPO}") == {"private": True}  # `GET /repos/owner/name` has no trailing slash
    assert used == [(REPO, f"/repos/{REPO}")]
    # and therefore a private repo is recognised as private through the real routing, not only through a direct fake
    assert dm.private_repos(api, [REPO]) == frozenset({REPO})
    with pytest.raises(ValueError):
        api("GET", "/repos/justowner")


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


def test_each_pass_prunes_stale_scratch_from_the_work_dir(tmp_path, monkeypatch):
    import os
    import time

    s = dm.Settings.from_env(env(tmp_path))
    s.work_dir.mkdir(parents=True)
    stale, fresh = s.work_dir / "pr-old", s.work_dir / "pr-new"
    stale.mkdir()
    fresh.mkdir()
    old = time.time() - 3 * 24 * 3600
    os.utime(stale, (old, old))

    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            raise GitHubError(404, path, "")  # not enabled: the pass ends quickly

        return api

    monkeypatch.delenv("APX_LIVE", raising=False)
    dm.run_once(s, api_factory=factory)
    assert not stale.exists() and fresh.exists()


def test_launchd_daemon_template_runs_as_the_unprivileged_account_and_holds_no_secret():
    import plistlib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "deploy"
    p = plistlib.loads((root / "launchd/com.autopilot.apx.daemon.plist").read_bytes())
    assert p["UserName"] == "apx" and p["UserName"] != "root" and p["RunAtLoad"] is False
    cmd = p["ProgramArguments"][-1]
    assert "--once --live" in cmd and "APX_LIVE=1" in cmd and "/Users/apx/.apx/apx.env" in cmd
    assert "TOKEN" not in cmd.upper() and "SECRET" not in cmd.upper()
    assert p["EnvironmentVariables"]["HOME"] == "/Users/apx"
    assert "ryanhamby" not in plistlib.dumps(p).decode()  # nothing points back into the owner's home


def test_install_script_refuses_admin_keeps_scope_narrow_and_deletes_nothing():
    from pathlib import Path

    s = (Path(__file__).resolve().parent.parent / "deploy/apx-install-mac.sh").read_text()
    assert "set -euo pipefail" in s and 'REPOS="${REPOS:-RyanJHamby/autopilot}"' in s
    assert "must NOT be an admin" in s and "DRY_RUN" in s
    assert "rm -r" not in s and "rm -f $" not in s.replace('rm -f "$TMP"', "")  # only its own temp file is ever removed
    for secret in ("app.pem", "claude-oauth"):
        assert "install -m 600" in s and secret in s


def test_pre_push_hook_runs_the_same_checks_as_ci():
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    hook = root / ".githooks/pre-push"
    s = hook.read_text()
    cmds = [ln.strip() for ln in s.splitlines() if ln.strip().startswith("$RUN ")]  # the commands, not the echo messages
    assert os.access(hook, os.X_OK) and "set -e" in s
    assert "$RUN ruff check ." in cmds and "$RUN pytest -q" in cmds
    ci = (root / ".github/workflows/ci.yml").read_text()
    assert "ruff check ." in ci and "pytest -q" in ci  # the hook and CI must keep running the same commands
    assert os.access(root / "scripts/install-hooks", os.X_OK)


def test_run_once_in_shadow_mode_never_plans_an_agent_run(tmp_path, monkeypatch):
    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            assert method == "GET"
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if "/issues?" in path:
                return [
                    {
                        "number": 9,
                        "created_at": "2026-10-20T00:00:00Z",
                        "user": {"login": "RyanJHamby"},
                        "labels": [{"name": "agent-ready"}],
                    }
                ]
            return []

        return api

    monkeypatch.delenv("APX_LIVE", raising=False)
    shadow = dm.run_once(dm.Settings.from_env(env(tmp_path)), api_factory=factory)
    assert not any("run-agent" in line for line in shadow)
    cut = dm.run_once(dm.Settings.from_env(env(tmp_path, APX_SHADOW="0", APX_AGENT_USER="apx-agent")), api_factory=factory)
    assert any(line.startswith("DRY-RUN run-agent") for line in cut)


def test_contexts_are_shadow_by_default_and_real_only_for_authoritative_repos(tmp_path):
    two = "RyanJHamby/stencil=11,RyanJHamby/drillpad-workspace=11,RyanJHamby/autopilot=11"
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=two))
    for repo in ("RyanJHamby/stencil", "RyanJHamby/drillpad-workspace", "RyanJHamby/autopilot"):
        assert s.contexts(repo) == {"guard": "apx / guard", "ci": "apx / build"}
    a = dm.Settings.from_env(
        env(tmp_path, APX_INSTALLATIONS=two, APX_AUTHORITATIVE="RyanJHamby/stencil,RyanJHamby/drillpad-workspace")
    )
    assert a.contexts("RyanJHamby/stencil") == {"guard": "guard / guard", "ci": "build"}
    assert a.contexts("RyanJHamby/drillpad-workspace") == {"guard": "guard / guard", "ci": "test"}
    assert a.contexts("RyanJHamby/autopilot") == {"guard": "apx / guard", "ci": "apx / build"}  # not listed: still shadow
    cut = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=two, APX_SHADOW="0"))
    assert cut.contexts("RyanJHamby/stencil")["ci"] == "build" and cut.contexts("RyanJHamby/autopilot")["ci"] == "test"


def test_authoritative_must_name_installed_repos_only(tmp_path):
    with pytest.raises(dm.ConfigError):
        dm.Settings.from_env(
            env(tmp_path, APX_AUTHORITATIVE="RyanJHamby/drillpad-workspace")
        )  # only stencil is installed in env()


def test_authoritative_repo_checks_run_under_the_required_names_end_to_end(tmp_path, monkeypatch):
    two = "RyanJHamby/stencil=11,RyanJHamby/autopilot=11"
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=two, APX_AUTHORITATIVE="RyanJHamby/stencil"))

    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            assert method == "GET"
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if "/check-runs" in path:
                return {"check_runs": []}
            if "pulls?state=open" in path:
                return [
                    {
                        "number": 3,
                        "head": {
                            "ref": "feature/x",
                            "sha": "s" * 40,
                            "repo": {"full_name": path.split("/")[2] + "/" + path.split("/")[3]},
                        },
                        "user": {"login": "RyanJHamby"},
                    }
                ]
            return []

        return api

    monkeypatch.delenv("APX_LIVE", raising=False)
    out = dm.run_once(s, api_factory=factory)
    line = {
        r: next(x for x in out if x.startswith(f"DRY-RUN check-pr {r}")) for r in ("RyanJHamby/stencil", "RyanJHamby/autopilot")
    }
    assert "missing guard / guard, build" in line["RyanJHamby/stencil"]
    assert "missing apx / guard, apx / build" in line["RyanJHamby/autopilot"]


TWO = "RyanJHamby/stencil=11,RyanJHamby/drillpad-workspace=11"


def test_cutover_turns_on_the_full_loop_for_named_repos_only(tmp_path):
    s = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=TWO, APX_CUTOVER="RyanJHamby/drillpad-workspace"))
    assert s.full_loop("RyanJHamby/drillpad-workspace") and not s.full_loop("RyanJHamby/stencil")
    assert s.contexts("RyanJHamby/drillpad-workspace") == {"guard": "guard / guard", "ci": "test"}  # real names
    assert s.contexts("RyanJHamby/stencil") == {"guard": "apx / guard", "ci": "apx / build"}  # still shadow
    all_cut = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=TWO, APX_SHADOW="0"))
    assert all_cut.full_loop("RyanJHamby/stencil") and all_cut.full_loop("RyanJHamby/drillpad-workspace")
    assert not dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=TWO)).full_loop("RyanJHamby/stencil")


def test_cutover_must_name_installed_repos_only(tmp_path):
    with pytest.raises(dm.ConfigError):
        dm.Settings.from_env(env(tmp_path, APX_CUTOVER="RyanJHamby/drillpad-workspace"))  # only stencil is installed in env()


def test_merge_lane_exists_only_when_something_is_cut_over(tmp_path):
    fn = lambda *a: (0, "")  # noqa: E731
    shadow = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=TWO))
    some = dm.Settings.from_env(env(tmp_path, APX_INSTALLATIONS=TWO, APX_CUTOVER="RyanJHamby/stencil"))
    assert dm.select_automerge(shadow, fn) is None and dm.select_automerge(some, fn) is fn


def test_run_once_plans_agent_runs_and_merges_only_for_the_cutover_repo(tmp_path, monkeypatch):
    s = dm.Settings.from_env(
        env(tmp_path, APX_INSTALLATIONS=TWO, APX_CUTOVER="RyanJHamby/drillpad-workspace", APX_AGENT_USER="apx-agent")
    )

    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            assert method == "GET"
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if "/issues?" in path:
                return [
                    {
                        "number": 9,
                        "created_at": "2026-10-20T00:00:00Z",
                        "user": {"login": "RyanJHamby"},
                        "labels": [{"name": "agent-ready"}],
                    }
                ]
            return []

        return api

    monkeypatch.delenv("APX_LIVE", raising=False)
    out = dm.run_once(s, api_factory=factory)
    assert any(x.startswith("DRY-RUN run-agent RyanJHamby/drillpad-workspace 9") for x in out)
    assert not any("run-agent RyanJHamby/stencil" in x for x in out)  # same issue shape on stencil, but it is still shadow


def test_timer_is_not_a_background_job_which_macos_throttles_to_efficiency_cores():
    import plistlib
    from pathlib import Path

    for name in ("com.autopilot.apx.daemon.plist", "com.autopilot.apx.plist"):
        p = plistlib.loads((Path(__file__).resolve().parent.parent / "deploy/launchd" / name).read_bytes())
        assert p["ProcessType"] in ("Interactive", "Standard"), name  # Background made the CI lane ~4x slower on Apple Silicon
        assert "LowPriorityIO" not in p and "Nice" not in p, name


def test_ci_toolchain_links_default_to_cargo_and_are_owner_configurable(tmp_path):
    assert dm.Settings.from_env(env(tmp_path)).ci_toolchain_links == (".cargo",)
    assert dm.Settings.from_env(env(tmp_path, APX_CI_TOOLCHAIN_LINKS=".cargo,.rustup")).ci_toolchain_links == (
        ".cargo",
        ".rustup",
    )
    assert dm.Settings.from_env(env(tmp_path, APX_CI_TOOLCHAIN_LINKS="")).ci_toolchain_links == ()


def test_ci_lane_runs_base_branch_steps_with_the_linked_toolchain_home(tmp_path, monkeypatch):
    real_home = tmp_path / "apxhome"
    (real_home / ".cargo" / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(real_home))
    s = dm.Settings.from_env(env(tmp_path))
    s.work_dir.mkdir(parents=True)
    co = tmp_path / "co"
    co.mkdir()
    git(co, "init", "-q")
    git(co, "config", "user.email", "t@example.com")
    git(co, "config", "user.name", "t")
    (co / "probe.py").write_text(
        "import os,sys\nsys.exit(0 if os.path.isdir(os.path.join(os.environ['HOME'], '.cargo', 'bin')) else 1)\n"
    )
    (co / ".autopilot").mkdir()
    (co / ".autopilot" / "repo.yaml").write_text(f"ci:\n  - '{sys.executable} probe.py'\n")
    git(co, "add", "-A")
    sha = git(co, "commit-tree", git(co, "write-tree"), "-m", "i")
    git(co, "update-ref", "refs/remotes/origin/main", sha)
    ok, md = dm.ci_lane(s, co)
    assert ok, md  # the probe only passes if the lane linked .cargo into its scratch HOME
    s2 = dm.Settings.from_env(env(tmp_path, APX_CI_TOOLCHAIN_LINKS=""))
    ok2, _ = dm.ci_lane(s2, co)
    assert not ok2  # control: with no links the same step fails


def test_private_repos_only_includes_repos_the_api_confirms_private():
    class A:
        def __call__(self, method, path, body=None):
            if path.endswith("/priv"):
                return {"private": True}
            if path.endswith("/pub"):
                return {"private": False}
            if path.endswith("/odd"):
                return {}  # no private field: not confirmed
            raise GitHubError(500, path, "x")  # lookup failure: not confirmed

    got = dm.private_repos(A(), ["o/priv", "o/pub", "o/odd", "o/err"])
    assert got == frozenset({"o/priv"})


def test_a_pass_registers_the_claude_token_so_it_is_scrubbed_from_output(tmp_path, monkeypatch):
    from autopilot.apx import redact

    redact.forget_all()
    token = "opaque-claude-token-" + "Zx3Qv" * 8
    s = dm.Settings.from_env(env(tmp_path))
    open(s.oauth_file, "w").write(token + "\n")
    monkeypatch.delenv("APX_LIVE", raising=False)

    def factory(t):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            raise GitHubError(404, path, "")

        return api

    assert redact.redact(f"x {token}") == f"x {token}"  # control: not yet known
    dm.run_once(s, api_factory=factory)
    assert token not in redact.redact(f"x {token}")
    redact.forget_all()


def _gate_factory():
    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            assert method == "GET"
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if "/issues?" in path:
                return [
                    {
                        "number": 9,
                        "created_at": "2026-10-20T00:00:00Z",
                        "user": {"login": "RyanJHamby"},
                        "labels": [{"name": "agent-ready"}],
                    }
                ]
            return []

        return api

    return factory


def test_agent_runs_stay_off_after_cutover_until_a_dedicated_agent_account_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("APX_LIVE", raising=False)
    no_agent = dm.Settings.from_env(env(tmp_path, APX_SHADOW="0"))
    assert no_agent.full_loop("RyanJHamby/stencil") and not no_agent.agents_allowed("RyanJHamby/stencil")
    out = dm.run_once(no_agent, api_factory=_gate_factory())
    assert not any("run-agent" in line for line in out)
    assert any("agent runs blocked" in line and "S1b" in line for line in out)  # the reason is visible, not silent
    with_agent = dm.Settings.from_env(env(tmp_path, APX_SHADOW="0", APX_AGENT_USER="apx-agent"))
    assert with_agent.agents_allowed("RyanJHamby/stencil")
    out2 = dm.run_once(with_agent, api_factory=_gate_factory())
    assert any(line.startswith("DRY-RUN run-agent") for line in out2)


def test_sandbox_and_agent_accounts_are_validated_and_must_differ(tmp_path):
    ok = dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci", APX_AGENT_USER="apx-agent"))
    assert ok.ci_user == "apx-ci" and ok.agent_user == "apx-agent"
    bad_cases = (
        {"APX_CI_USER": "root"},
        {"APX_CI_USER": "apx"},
        {"APX_AGENT_USER": "Bad User"},
        {"APX_CI_USER": "same", "APX_AGENT_USER": "same"},
    )
    for bad in bad_cases:
        with pytest.raises(dm.ConfigError):
            dm.Settings.from_env(env(tmp_path, **bad))
    assert dm.Settings.from_env(env(tmp_path)).ci_user == ""  # default: today's behaviour


def test_build_deps_uses_the_sandbox_lanes_only_when_a_ci_account_is_configured(tmp_path, monkeypatch):
    from autopilot.apx import guardlane
    from autopilot.apx.sandbox import SandboxLanes

    monkeypatch.setattr(guardlane, "fetch_kit", lambda repo, ref, dest: dest)  # no network in this test
    plain = dm.build_deps(dm.Settings.from_env(env(tmp_path)), lambda *a, **k: {}, lambda r: "t", {})
    boxed = dm.build_deps(dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci")), lambda *a, **k: {}, lambda r: "t", {})
    assert not isinstance(getattr(plain.guard, "__self__", None), SandboxLanes)
    assert isinstance(boxed.guard.__self__, SandboxLanes) and isinstance(boxed.checkout.__self__, SandboxLanes)
    assert boxed.guard.__self__.launcher.user == "apx-ci"
    assert "/Users/Shared/apx/kit" in boxed.guard.__self__.kit_dir  # the kit lives where the sandbox account can read it


class _IssueApi:
    """Just enough of GitHub for work_on_issue plus the commit path; records every write."""

    def __init__(self):
        self.writes = []

    def __call__(self, method, path, body=None):
        if method != "GET":
            self.writes.append((method, path, body))
        if path.endswith("/issues/4"):
            return {"title": "Add feature", "body": "please"}
        if path.endswith("/comments?per_page=100"):
            return []
        if "contents/.autopilot/repo.yaml" in path:
            return {"content": base64.b64encode(b"commands:\n  - pytest -q\n").decode()}
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "b" * 40}}
        if "/git/commits/" in path:
            return {"tree": {"sha": "T0"}}
        if path.endswith("/git/blobs"):
            return {"sha": "B1"}
        if path.endswith("/git/trees"):
            return {"sha": "T1"}
        if path.endswith("/git/commits"):
            return {"sha": "C1"}
        if path.endswith("/pulls"):
            return {"number": 21}
        return {}


def _agent_settings(tmp_path):
    return dm.Settings.from_env(env(tmp_path, APX_AGENT_USER="apx-agent", APX_OAUTH_FILE=""))


def test_with_an_agent_account_the_model_gets_a_read_only_token_and_this_account_makes_the_commit(tmp_path):
    from autopilot.apx.committer import FileChange

    s = _agent_settings(tmp_path)
    api, seen = _IssueApi(), {}

    def run_agent(req, token):
        seen["req"], seen["token"] = req, token
        return {"ok": True, "summary": "did it", "turns": 6}, [FileChange("f.py", "100644", b"x = 1\n")]

    r = dm.work_on_issue(
        s, api, lambda repo: "WRITE-TOKEN", REPO, 4, 77, "model=sonnet effort=low turns=12",
        read_token_for=lambda repo: "READ-ONLY-TOKEN", run_agent=run_agent,
    )  # fmt: skip
    assert r.ok and r.pr_number == 21 and r.turns == 6
    assert seen["token"] == "READ-ONLY-TOKEN" and seen["token"] != "WRITE-TOKEN"  # the model never gets the write token
    req = seen["req"]
    assert req["base_sha"] == "b" * 40 and req["max_turns"] == 12 and req["commands"] == ["pytest -q"]
    assert req["work_root"] == "/Users/apx-agent/work" and req["binary"] == "/Users/apx-agent/.local/bin/claude"
    refs = [w for w in api.writes if w[1].endswith("/git/refs")]
    assert refs and refs[0][2]["ref"] == "refs/heads/agent/4-77"  # and this account is the one that wrote to GitHub


def test_a_rejected_or_failed_agent_run_makes_no_commit_and_says_why(tmp_path):
    s = _agent_settings(tmp_path)
    for result, expect in (
        ({"ok": False, "summary": "s", "violations": ["[protected-path] .github/x.yml"], "turns": 2}, "protected-path"),
        ({"ok": False, "error": "agent ran as 'x', expected 'apx-agent'; result refused"}, "result refused"),
    ):
        api = _IssueApi()
        r = dm.work_on_issue(
            s, api, lambda repo: "w", REPO, 4, 1, "", read_token_for=lambda repo: "ro", run_agent=lambda req, tok: (result, [])
        )
        assert not r.ok and expect in r.problems
        assert api.writes == []  # nothing was blobbed, committed, pushed or opened


def test_an_agent_account_without_a_read_only_token_source_is_a_config_error(tmp_path):
    with pytest.raises(dm.ConfigError):
        dm.work_on_issue(_agent_settings(tmp_path), _IssueApi(), lambda r: "w", REPO, 4, 1, "")


def test_with_an_agent_account_the_orchestrator_never_reads_the_claude_token(tmp_path):
    from autopilot.apx import redact

    redact.forget_all()
    s = _agent_settings(tmp_path)
    assert s.oauth_file == "/Users/apx-agent/.apx/claude-oauth"  # lives in the agent's home, not ours
    dm._register_known_secrets(s)  # must not even try to read it (the path is not readable here)
    legacy = dm.Settings.from_env(env(tmp_path))
    open(legacy.oauth_file, "w").write("legacy-claude-token-" + "Zx3Qv" * 6 + "\n")
    dm._register_known_secrets(legacy)
    assert "legacy-claude-token" not in redact.redact(
        "x legacy-claude-token-" + "Zx3Qv" * 6
    )  # the legacy path still registers it
    redact.forget_all()


def test_the_orchestrator_skips_a_readable_claude_token_when_an_agent_account_owns_it(tmp_path):
    from autopilot.apx import redact

    redact.forget_all()
    token = "agent-owned-claude-token-" + "Qm8Rt" * 6
    f = tmp_path / "readable-token"
    f.write_text(token + "\n")
    f.chmod(0o600)
    s = dm.Settings.from_env(env(tmp_path, APX_AGENT_USER="apx-agent", APX_OAUTH_FILE=str(f)))
    dm._register_known_secrets(s)
    assert token in redact.redact(f"x {token}")  # not registered: this account never handles the agent's token
    dm._register_known_secrets(
        dm.Settings.from_env(env(tmp_path, APX_OAUTH_FILE=str(f)))
    )  # control: the legacy layout registers it
    assert token not in redact.redact(f"x {token}")
    redact.forget_all()


def test_a_live_pass_hands_the_read_only_token_source_to_build_deps(tmp_path, monkeypatch):
    from autopilot.apx import executor as ex

    s = dm.Settings.from_env(env(tmp_path, APX_AGENT_USER="apx-agent", APX_SHADOW="0"))
    seen = {}

    def fake_build_deps(settings, api, token_for, details, read_token_for=None):
        seen["read"] = read_token_for
        return ex.Deps(lambda r, sha: None, lambda co, ref: (True, ""), lambda co: (True, ""), lambda *a: None)

    monkeypatch.setattr(dm, "build_deps", fake_build_deps)
    monkeypatch.setenv("APX_LIVE", "1")

    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            if "/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if re.search(r"/repos/[^/]+/[^/]+$", path):
                return {"private": True}
            return []

        return api

    dm.run_once(s, live=True, api_factory=factory)
    assert callable(seen["read"])  # without it the agent path would raise a config error on the first issue


def test_one_repo_dropping_its_connection_costs_that_repo_the_pass_not_the_whole_pass():
    import http.client

    def api(method, path, body=None):
        if "/RyanJHamby/autopilot/" in path:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        if "/RyanJHamby/stencil/" in path:
            raise GitHubError(502, path, "bad gateway")
        return [{"head": {"sha": "s1", "ref": "agent/1-1"}}]

    heads, failed = dm.open_heads(api, ["RyanJHamby/autopilot", "RyanJHamby/stencil", "RyanJHamby/drillpad-workspace"])
    assert heads == {("RyanJHamby/drillpad-workspace", "s1"): "agent/1-1"}  # the healthy repo is still served
    assert failed == {"RyanJHamby/autopilot", "RyanJHamby/stencil"}


def test_a_surprising_response_shape_also_only_costs_that_repo():
    heads, failed = dm.open_heads(lambda m, p, b=None: [{"head": None}], ["RyanJHamby/autopilot"])
    assert heads == {} and failed == {"RyanJHamby/autopilot"}


def test_actions_for_a_repo_whose_prs_could_not_be_listed_wait_for_the_next_pass():
    from autopilot.apx.planner import Action

    acts = [Action("check-pr", "a/x", "s"), Action("run-agent", "b/y", "1"), Action("check-pr", "a/x", "t")]
    assert dm.readable_only(acts, {"a/x"}) == [acts[1]] and dm.readable_only(acts, set()) == acts
