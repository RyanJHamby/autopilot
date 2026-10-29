import subprocess
from pathlib import Path

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


def settings(tmp_path, ci_user="", agent_user=""):
    key = tmp_path / "k.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    key.chmod(0o600)
    oauth = tmp_path / "oauth"
    oauth.write_text("sk-ant-oat01-" + "A1b2-" * 16 + "\n")
    oauth.chmod(0o600)
    return dm.Settings.from_env(
        {
            "APX_APP_ID": "1",
            "APX_KEY_PATH": str(key),
            "APX_INSTALLATIONS": f"{REPO}=11",
            "APX_OAUTH_FILE": str(oauth),
            "APX_KIT_REPO": "o/kit",
            "APX_KIT_REF": "a" * 40,
            **({"APX_CI_USER": ci_user} if ci_user else {}),
            **({"APX_AGENT_USER": agent_user} if agent_user else {}),
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


class Stub:
    """Stands in for the sandbox account: a well-configured one can run, is not admin, and is denied the secrets."""

    def __init__(self, leak=(), admin=False, no_yaml=False, dead=False, wrong_user=False, no_workdir=False):
        self.leak, self.admin, self.no_yaml, self.dead, self.wrong_user, self.no_workdir = (
            leak,
            admin,
            no_yaml,
            dead,
            wrong_user,
            no_workdir,
        )

    def run(self, argv, **kw):
        if self.dead:
            raise RuntimeError("sudo failed")
        R = lambda rc, out="": type("R", (), {"returncode": rc, "stdout": out, "stderr": ""})()  # noqa: E731
        cmd, rest = argv[0], argv[1:]
        if cmd == "/usr/bin/id":
            return R(0, "someone-else\n" if self.wrong_user else "apx-ci\n")
        if cmd == "/usr/sbin/dseditgroup":
            return R(
                0 if self.admin else 67, "yes apx-ci is a member of admin" if self.admin else "no apx-ci is NOT a member of admin"
            )
        if cmd in ("/bin/cat", "/bin/ls"):
            name = "orchestrator home" if cmd == "/bin/ls" else ("Claude token" if "oauth" in rest[0] else "App key")
            return R(0 if name in self.leak else 1)
        if cmd == "/bin/sh":
            return R(1 if self.no_workdir else 0)
        if rest[:1] == ["-c"]:
            return R(1 if self.no_yaml else 0)
        return R(0)


def run(s, **kw):
    kw.setdefault("which", lambda t: f"/usr/bin/{t}")
    kw.setdefault("approved", lambda repo: ["a" * 40])
    kw.setdefault("api_factory", factory())
    kw.setdefault("launcher", Stub())
    return {c.name: c for c in dr.run_doctor(s, **kw)}


def test_clean_setup_passes_everything(tmp_path):
    out = run(settings(tmp_path, ci_user="apx-ci"))  # "clean" now includes the account split
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


def test_token_shape_accepts_a_plausible_token_and_rejects_junk(tmp_path):
    good = tmp_path / "good"
    good.write_text("sk-ant-oat01-" + "A1b2-" * 16 + "\n")
    c = dr.token_shape(str(good))
    assert c.ok and "chars" in c.detail
    for name, text in {
        "sentence": "this is the wrong thing from the clipboard that is long enough to pass length\n",
        "short": "sk-ant-short\n",
        "two lines": "sk-ant-" + "a" * 50 + "\nsecond\n",
        "empty": "",
        "quotes": '"' + "a" * 50 + '"',
        "command": "umask 077; pbpaste > ~/.apx/claude-oauth; pbcopy < /dev/null",
    }.items():
        f = tmp_path / name.replace(" ", "_")
        f.write_text(text)
        assert not dr.token_shape(str(f)).ok, name
    assert not dr.token_shape(str(tmp_path / "missing")).ok


def test_token_shape_never_puts_the_token_in_its_output(tmp_path):
    f = tmp_path / "t"
    secret = "sk-ant-" + "Zq9" * 20
    f.write_text(secret + " junk")
    c = dr.token_shape(str(f))
    assert not c.ok and secret not in c.detail and secret not in c.name


def test_doctor_includes_the_token_shape_check(tmp_path):
    s = settings(tmp_path)
    assert run(s)["claude token shape"].ok
    Path(s.oauth_file).write_text("not a token at all, just words from the clipboard that run long enough\n")
    Path(s.oauth_file).chmod(0o600)
    assert not run(s)["claude token shape"].ok


def test_a_properly_split_setup_passes_every_sandbox_check(tmp_path):
    out = run(settings(tmp_path, ci_user="apx-ci"))
    sandbox = {n: c for n, c in out.items() if "sandbox" in n}
    assert len(sandbox) == 7 and all(c.ok for c in sandbox.values()), {n: c.detail for n, c in sandbox.items() if not c.ok}


def test_no_sandbox_account_is_reported_as_a_failure_not_ignored(tmp_path):
    out = run(settings(tmp_path))
    c = out["sandbox account configured (APX_CI_USER)"]
    assert not c.ok and "holds the secrets" in c.detail


def test_every_way_the_sandbox_can_read_a_secret_fails_the_doctor(tmp_path):
    s = settings(tmp_path, ci_user="apx-ci")
    for what in ("App key", "Claude token", "orchestrator home"):
        out = run(s, launcher=Stub(leak=(what,)))
        c = out[f"sandbox account CANNOT read the {what}"]
        assert not c.ok and "split is not in place" in c.detail, what
        others = [n for n in out if n.startswith("sandbox account CANNOT") and n != f"sandbox account CANNOT read the {what}"]
        assert all(out[n].ok for n in others)  # only the leaking one fails


def test_other_sandbox_misconfigurations_each_fail_their_own_check(tmp_path):
    s = settings(tmp_path, ci_user="apx-ci")
    assert not run(s, launcher=Stub(admin=True))["sandbox account is not an admin"].ok
    assert not run(s, launcher=Stub(no_yaml=True))["sandbox python has PyYAML (guard config would silently vanish without it)"].ok
    assert not run(s, launcher=Stub(no_workdir=True))["sandbox work directory exists and is writable"].ok
    assert not run(s, launcher=Stub(wrong_user=True))["sandbox account is usable via sudo"].ok
    dead = run(s, launcher=Stub(dead=True))  # sudo not working at all must fail checks, never crash the doctor
    assert not dead["sandbox account is usable via sudo"].ok


class AgentStub:
    """Stands in for the model's account: usable, standard user, denied the write key and the orchestrator home, owns a valid token."""

    def __init__(self, leak=(), admin=False, bad_token=False, no_cli=False, no_workdir=False, dead=False):
        self.leak, self.admin, self.bad_token, self.no_cli, self.no_workdir, self.dead = (
            leak,
            admin,
            bad_token,
            no_cli,
            no_workdir,
            dead,
        )

    def run(self, argv, **kw):
        if self.dead:
            raise RuntimeError("sudo failed")
        R = lambda rc, out="": type("R", (), {"returncode": rc, "stdout": out, "stderr": ""})()  # noqa: E731
        cmd = argv[0]
        if cmd == "/usr/bin/id":
            return R(0, "apx-agent\n")
        if cmd == "/usr/sbin/dseditgroup":
            return R(
                0 if self.admin else 67,
                "yes apx-agent is a member of admin" if self.admin else "no apx-agent is NOT a member of admin",
            )
        if cmd == "/bin/cat":
            return R(0 if "App key" in self.leak else 1)
        if cmd == "/bin/ls":
            return R(0 if "orchestrator home" in self.leak else 1)
        if cmd == "/bin/sh":
            return R(1 if self.no_workdir else 0)
        if argv[1:2] == ["-c"]:
            return R(0, "BAD too short (3 chars)\n" if self.bad_token else "OK\n")
        if argv[1:2] == ["--version"]:
            return R(1 if self.no_cli else 0, "2.1.312 (Claude Code)\n")
        return R(0)


def run_agent_doctor(s, agent=None, **kw):
    kw.setdefault("which", lambda t: f"/usr/bin/{t}")
    kw.setdefault("approved", lambda repo: ["a" * 40])
    kw.setdefault("api_factory", factory())
    return {c.name: c for c in dr.run_doctor(s, launcher=Stub(), agent_launcher=agent or AgentStub(), **kw)}


def test_a_properly_configured_agent_account_passes_every_agent_check(tmp_path):
    out = run_agent_doctor(settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent"))
    expected = {
        "agent account is usable via sudo",
        "agent account is not an admin",
        "agent account CANNOT read the App key",
        "agent account CANNOT read the orchestrator home",
        "agent account can read its own Claude token (shape checked, value not shown)",
        "orchestrator no longer holds a copy of the Claude token",
        "agent account can run the claude CLI",
        "agent work directory exists and is writable",
    }
    assert expected <= set(out), expected - set(out)
    assert all(out[n].ok for n in expected), {n: out[n].detail for n in expected if not out[n].ok}
    assert (
        "claude oauth file file" not in out and "claude token shape" not in out
    )  # this account no longer checks the token itself


def test_without_an_agent_account_the_doctor_says_agent_runs_stay_blocked(tmp_path):
    out = run(settings(tmp_path, ci_user="apx-ci"))
    c = out["agent account configured (APX_AGENT_USER)"]
    assert c.ok and "blocked" in c.detail and "claude token shape" in out  # the legacy single-account layout is still checked


def test_every_way_the_agent_account_can_touch_the_write_key_fails(tmp_path):
    s = settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent")
    for what, name in (
        ("App key", "agent account CANNOT read the App key"),
        ("orchestrator home", "agent account CANNOT read the orchestrator home"),
    ):
        out = run_agent_doctor(s, AgentStub(leak=(what,)))
        assert not out[name].ok and "no write-key separation" in out[name].detail, what


def test_the_orchestrator_keeping_a_copy_of_the_claude_token_fails(tmp_path):
    s = settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent")
    kept = tmp_path / "claude-oauth"  # next to the App key, i.e. in the orchestrator's directory
    kept.write_text("still-here")
    out = run_agent_doctor(s)
    assert not out["orchestrator no longer holds a copy of the Claude token"].ok
    kept.unlink()
    assert run_agent_doctor(s)["orchestrator no longer holds a copy of the Claude token"].ok


def test_other_agent_misconfigurations_each_fail_their_own_check(tmp_path):
    s = settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent")
    assert not run_agent_doctor(s, AgentStub(admin=True))["agent account is not an admin"].ok
    assert not run_agent_doctor(s, AgentStub(bad_token=True))[
        "agent account can read its own Claude token (shape checked, value not shown)"
    ].ok
    assert not run_agent_doctor(s, AgentStub(no_cli=True))["agent account can run the claude CLI"].ok
    assert not run_agent_doctor(s, AgentStub(no_workdir=True))["agent work directory exists and is writable"].ok
    dead = run_agent_doctor(s, AgentStub(dead=True))  # sudo broken must fail checks, never crash the doctor
    assert not dead["agent account is usable via sudo"].ok
