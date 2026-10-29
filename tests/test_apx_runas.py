import json
import os
import sys
import textwrap

import pytest

from autopilot.apx.runas import Launcher

SECRET = "super-secret-token-value-9f8e7d"


@pytest.fixture()
def fake_sudo(tmp_path):
    """A stand-in for sudo: records its argv, drops the environment except PATH and --preserve-env names (like env_reset), runs the rest."""
    log = tmp_path / "sudo.log"
    f = tmp_path / "sudo"
    f.write_text(
        "#!"
        + sys.executable
        + "\n"
        + textwrap.dedent(
            f"""
            import json, os, sys
            args = sys.argv[1:]
            open({str(log)!r}, "a").write(json.dumps(args) + "\\n")
            keep, user = [], None
            while args:
                a = args.pop(0)
                if a == "-n":
                    continue
                if a == "-u":
                    user = args.pop(0)
                    continue
                if a.startswith("--preserve-env="):
                    keep = a.split("=", 1)[1].split(",")
                    continue
                if a == "--":
                    break
            env = {{"PATH": "/usr/bin:/bin"}}
            env.update({{k: os.environ[k] for k in keep if k in os.environ}})
            os.execvpe(args[0], args, env)
            """
        )
    )
    f.chmod(0o755)
    return str(f), log


def argvs(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_no_user_is_a_plain_run_and_passes_secrets_in_the_environment():
    r = Launcher(None).run(
        [sys.executable, "-c", "import os;print(os.environ['TOK'], os.environ['A'])"],
        env={"A": "1", "PATH": os.environ["PATH"]},
        secret_env={"TOK": "t"},
        capture_output=True,
        text=True,
    )
    assert r.stdout.split() == ["t", "1"]


def test_sandbox_run_enters_the_directory_and_uses_a_clean_environment(fake_sudo, tmp_path, monkeypatch):
    sudo, log = fake_sudo
    monkeypatch.setenv("ORCHESTRATOR_ONLY", "must-not-leak")
    work = tmp_path / "work"
    work.mkdir()
    code = "import os;print(os.getcwd());print(sorted(os.environ))"
    r = Launcher("apx-ci", sudo=sudo).run(
        [sys.executable, "-c", code], cwd=str(work), env={"HOME": "/h", "CI": "true"}, capture_output=True, text=True
    )
    out = r.stdout.splitlines()
    assert r.returncode == 0 and os.path.realpath(out[0]) == os.path.realpath(str(work))
    assert "ORCHESTRATOR_ONLY" not in out[1] and "HOME" in out[1] and "CI" in out[1]
    sent = argvs(log)[0]
    assert sent[:3] == ["-n", "-u", "apx-ci"]


def test_secrets_reach_the_child_but_never_appear_in_any_command_line(fake_sudo, tmp_path):
    sudo, log = fake_sudo
    r = Launcher("apx-ci", sudo=sudo).run(
        [sys.executable, "-c", "import os;print(os.environ['GIT_CONFIG_VALUE_0'])"],
        cwd=str(tmp_path),
        env={"HOME": "/h"},
        secret_env={"GIT_CONFIG_VALUE_0": SECRET},
        capture_output=True,
        text=True,
    )
    assert r.stdout.strip() == SECRET  # delivered through the environment
    assert SECRET not in log.read_text()  # but the argv that anyone could read with ps never held it
    assert "--preserve-env=GIT_CONFIG_VALUE_0" in argvs(log)[0]


def test_the_child_exit_code_and_a_missing_directory_are_reported(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    ok = Launcher("apx-ci", sudo=sudo).run([sys.executable, "-c", "raise SystemExit(3)"], cwd=str(tmp_path), capture_output=True)
    assert ok.returncode == 3
    gone = Launcher("apx-ci", sudo=sudo).run([sys.executable, "-c", "pass"], cwd=str(tmp_path / "nope"), capture_output=True)
    assert gone.returncode == 97  # the wrapper refuses to run anywhere but the requested directory


@pytest.mark.parametrize("user", ["root", "apx", "Bad User", "", "a;b"])
def test_only_a_plain_unprivileged_account_name_is_accepted(user):
    with pytest.raises(ValueError):
        Launcher(user).wrap(["true"], "/", {}, [])


def test_malformed_inputs_are_refused():
    L = Launcher("apx-ci")
    for argv in ([], ["A=1", "x"], ["ok", "a\0b"]):
        with pytest.raises(ValueError):
            L.wrap(argv, "/", {}, [])
    with pytest.raises(ValueError):
        L.wrap(["true"], "/", {}, ["lower_case"])
    with pytest.raises(ValueError):
        L.wrap(["true"], "/", {"bad name": "x"}, [])
    with pytest.raises(ValueError):
        L.wrap(["true"], "/", {"OK": "a\0b"}, [])


def test_sudo_is_an_absolute_path_by_default():
    assert Launcher("apx-ci").wrap(["true"], "/", {}, [])[0] == "/usr/bin/sudo"
