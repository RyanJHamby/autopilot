import subprocess

import pytest

from autopilot.apx import daemon as dm
from autopilot.apx import doctor as dr
from autopilot.apx.github import GitHubError

REPO = "RyanJHamby/stencil"
GOOD_PERMS = {
    "metadata": "read",
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "write",
    "actions_variables": "read",
}


def settings(tmp_path):
    key = tmp_path / "k.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    key.chmod(0o600)
    oauth = tmp_path / "oauth"
    oauth.write_text("t")
    oauth.chmod(0o600)
    return dm.Settings.from_env(
        {
            "APX_APP_ID": "1",
            "APX_KEY_PATH": str(key),
            "APX_INSTALLATIONS": f"{REPO}=11",
            "APX_OAUTH_FILE": str(oauth),
            "APX_KIT_REPO": "o/kit",
            "APX_KIT_REF": "a" * 40,
        }
    )


def factory(perms=None, repos=None, app_id=1, fail_app=False):
    perms = GOOD_PERMS if perms is None else perms
    repos = [REPO] if repos is None else repos

    def make(token):
        def api(method, path, body=None):
            if fail_app:
                raise GitHubError(401, path, "bad")
            if path == "/app":
                return {"id": app_id, "permissions": perms}
            if path.startswith("/app/installations/"):
                return {"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"}
            if path.startswith("/installation/repositories"):
                return {"repositories": [{"full_name": r} for r in repos]}
            raise AssertionError(path)

        return api

    return make


def run(s, **kw):
    kw.setdefault("which", lambda t: f"/usr/bin/{t}")
    kw.setdefault("approved", lambda repo: ["a" * 40])
    kw.setdefault("api_factory", factory())
    return {c.name: c for c in dr.run_doctor(s, **kw)}


def test_clean_setup_passes_everything(tmp_path):
    out = run(settings(tmp_path))
    assert all(c.ok for c in out.values()), {n: c.detail for n, c in out.items() if not c.ok}
    text, ok = dr.render(list(out.values()))
    assert ok and "all checks passed" in text


@pytest.mark.parametrize("extra", ["administration", "workflows", "secrets", "environments", "actions", "members"])
def test_app_with_a_dangerous_extra_permission_fails(tmp_path, extra):
    out = run(settings(tmp_path), api_factory=factory(perms={**GOOD_PERMS, extra: "write"}))
    assert not out["app has no extra permissions"].ok and extra in out["app has no extra permissions"].detail


def test_missing_or_too_high_permissions_fail(tmp_path):
    s = settings(tmp_path)
    lacking = {k: v for k, v in GOOD_PERMS.items() if k != "checks"}
    assert not run(s, api_factory=factory(perms=lacking))["app permission checks>=write"].ok
    assert not run(s, api_factory=factory(perms={**GOOD_PERMS, "actions_variables": "write"}))[
        "app permissions not above need"
    ].ok
    assert not run(s, api_factory=factory(perms={**GOOD_PERMS, "contents": "read"}))["app permission contents>=write"].ok


def test_installation_on_extra_repos_fails(tmp_path):
    out = run(settings(tmp_path), api_factory=factory(repos=[REPO, "RyanJHamby/resume"]))
    c = out[f"installation for {REPO}"]
    assert not c.ok and "OUT OF SCOPE" in c.detail


def test_wrong_app_id_and_auth_failure(tmp_path):
    assert not run(settings(tmp_path), api_factory=factory(app_id=999))["app id matches"].ok
    out = run(settings(tmp_path), api_factory=factory(fail_app=True))
    assert not out["app authentication"].ok and "app id matches" not in out


def test_open_key_permissions_and_missing_tools_and_unapproved_kit_fail(tmp_path):
    s = settings(tmp_path)
    s.key_path.chmod(0o644)
    assert not run(s)["app key file"].ok
    s.key_path.chmod(0o600)
    assert not run(s, which=lambda t: None if t == "claude" else "/x")["tool claude"].ok
    assert run(s, which=lambda t: None if t == "gh" else "/x")["tool gh"].ok  # gh is optional
    out = run(s, approved=lambda repo: ["b" * 40])
    assert not out["kit sha is approved"].ok

    def boom(repo):
        raise OSError("net")

    assert not run(s, approved=boom)["kit sha is approved"].ok


def test_doctor_cli_exit_codes(tmp_path, monkeypatch, capsys):
    s = settings(tmp_path)  # built before patching from_env
    monkeypatch.setattr(dr, "run_doctor", lambda s: [dr.Check("x", True, "")])
    monkeypatch.setattr(dm.Settings, "from_env", classmethod(lambda cls, env=None: s))
    assert dm.main(["--doctor"]) == 0
    monkeypatch.setattr(dr, "run_doctor", lambda s: [dr.Check("x", False, "bad")])
    assert dm.main(["--doctor"]) == 1
    assert "FAIL" in capsys.readouterr().out
