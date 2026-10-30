import json
import subprocess

import pytest

from autopilot.apx import update_main as um
from autopilot.apx.daemon import Settings
from autopilot.apx.status import check_update, watch_once


class Spy:
    """A Launcher stand-in that records what would run, and as whom."""

    def __init__(self, rc=0, boom=None):
        self.rc, self.boom, self.calls = rc, boom, []
        self.user = "apx-ci"

    def run(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.boom:
            raise self.boom
        return subprocess.CompletedProcess(argv, self.rc, "", "")


def test_tests_run_the_new_trees_suite_without_writing_into_it(tmp_path):
    spy = Spy()
    assert um.make_run_tests(spy, "/venv/python", "/Users/apx-ci")(tmp_path) is True
    argv, kw = spy.calls[0]
    assert argv[:3] == ["/venv/python", "-m", "pytest"] and "no:cacheprovider" in argv
    assert (
        kw["cwd"] == str(tmp_path)
        and kw["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        and kw["env"]["PYTHONPATH"] == f"{tmp_path}/src"
    )
    assert (
        not any("TOKEN" in k or "KEY" in k for k in kw["env"]) and "secret_env" not in kw
    )  # nothing secret reaches the new tree


def test_a_red_suite_a_crash_or_a_timeout_is_never_a_pass(tmp_path):
    assert um.make_run_tests(Spy(rc=1), "p", "h")(tmp_path) is False
    assert um.make_run_tests(Spy(boom=subprocess.TimeoutExpired("x", 1)), "p", "h")(tmp_path) is False
    assert um.make_run_tests(Spy(boom=OSError("no sudo rule")), "p", "h")(tmp_path) is False


def settings(ci_user):
    return Settings(
        owner="o",
        app_id="1",
        key_path="/k",
        installations={"RyanJHamby/autopilot": 1},
        oauth_file="",
        kit_repo="x",
        kit_ref="y",
        ci_user=ci_user,
    )


def patch_world(monkeypatch, tmp_path, ci_user):
    monkeypatch.setattr(um.Settings, "from_env", classmethod(lambda cls, env=None: settings(ci_user)))
    monkeypatch.setattr(um, "TokenCache", lambda *a, **k: object())
    monkeypatch.setattr(um, "routed_api", lambda c: lambda m, p, b=None: {"object": {"sha": "b" * 40}})
    monkeypatch.setenv("APX_RELEASES_ROOT", str(tmp_path))
    monkeypatch.setenv("APX_UPDATE_STATUS", str(tmp_path / "update.json"))
    monkeypatch.delenv("APX_UPDATE_LIVE", raising=False)


def test_dry_run_changes_nothing_and_says_what_it_would_do(monkeypatch, tmp_path, capsys):
    patch_world(monkeypatch, tmp_path, "apx-ci")
    assert um.main([]) == 0
    assert "dry-run" in capsys.readouterr().out and not (tmp_path / "releases").exists()


def test_live_needs_both_the_flag_and_the_env(monkeypatch, tmp_path, capsys):
    patch_world(monkeypatch, tmp_path, "apx-ci")
    um.main(["--live"])  # flag without APX_UPDATE_LIVE=1
    assert "dry-run" in capsys.readouterr().out


def test_live_refuses_without_a_ci_account(monkeypatch, tmp_path, capsys):
    patch_world(monkeypatch, tmp_path, "")
    monkeypatch.setenv("APX_UPDATE_LIVE", "1")
    um.main(["--live"])
    out = capsys.readouterr().out
    assert "failed" in out and "no CI account" in out
    assert json.loads((tmp_path / "update.json").read_text())["ok"] is False


def test_an_unexpected_error_is_reported_not_raised(monkeypatch, tmp_path, capsys):
    patch_world(monkeypatch, tmp_path, "apx-ci")
    monkeypatch.setattr(um, "routed_api", lambda c: (_ for _ in ()).throw(RuntimeError("x")))
    assert um.main([]) == 0
    assert "update failed: RuntimeError" in capsys.readouterr().out


def write(path, line):
    path.write_text(
        json.dumps(
            {
                "ok": "failed" not in line and "rolled back" not in line,
                "problems": [line] if "failed" in line or "rolled back" in line else [],
            }
        )
    )


def test_the_watcher_raises_an_updater_rollback_and_keeps_it_up(tmp_path):
    st = tmp_path / "status.json"
    import datetime as dt

    st.write_text(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "ok": True, "problems": []}))
    up = tmp_path / "update.json"
    sent = []
    note = lambda t, m: sent.append(m)  # noqa: E731
    write(up, "update: swapped to abc1234; watching it")
    assert watch_once(st, tmp_path / "s", notifier=note, update_path=up) == "ok" and sent == []
    write(up, "update: rolled back to 1234567 (the new release failed its canary); HOLD set")
    assert watch_once(st, tmp_path / "s", notifier=note, update_path=up) == "problem" and "updater" in sent[-1]
    n = len(sent)
    assert watch_once(st, tmp_path / "s", notifier=note, update_path=up) == "problem" and len(sent) == n  # once, not every check


def test_a_missing_update_file_is_fine(tmp_path):
    assert check_update(tmp_path / "nope.json") == ("ok", "")
    (tmp_path / "bad.json").write_text("{")
    assert check_update(tmp_path / "bad.json") == ("ok", "")


def test_hold_after_a_rollback_keeps_saying_so(tmp_path):
    from autopilot.apx.update import run_update

    (tmp_path / "HOLD").write_text("rolled back; remove this file")
    msg = run_update(
        tmp_path,
        None,
        repo="o/r",
        default_branch="main",
        owner="o",
        required_checks=[],
        candidate="a" * 40,
        status={},
        stage=None,
        run_tests=None,
    )
    assert "rolled back" in msg


@pytest.mark.parametrize("name", ["rolled back"])
def test_rolled_back_counts_as_a_status_problem_word(name):
    from autopilot.apx.status import problems_in

    assert problems_in([f"x {name} y"])


class FakeCache:
    def read_token_for(self, repo):
        return "tok"


def live_world(monkeypatch, tmp_path, lock_free):
    import contextlib

    patch_world(monkeypatch, tmp_path, "apx-ci")
    monkeypatch.setattr(um, "TokenCache", lambda *a, **k: FakeCache())
    monkeypatch.setenv("APX_UPDATE_LIVE", "1")
    calls = []
    monkeypatch.setattr(um, "run_update", lambda *a, **k: calls.append(1) or "update: swapped")

    @contextlib.contextmanager
    def lock(work_dir):
        yield lock_free

    monkeypatch.setattr(um, "single_instance", lock)
    return calls


def test_a_running_pass_blocks_the_swap(monkeypatch, tmp_path, capsys):
    calls = live_world(monkeypatch, tmp_path, lock_free=False)
    um.main(["--live"])
    assert calls == [] and "a pass is running" in capsys.readouterr().out


def test_with_the_lock_free_the_update_runs(monkeypatch, tmp_path, capsys):
    calls = live_world(monkeypatch, tmp_path, lock_free=True)
    um.main(["--live"])
    assert calls == [1] and "swapped" in capsys.readouterr().out


def test_code_dir_follows_current_once_it_exists(tmp_path):
    s = settings("apx-ci")
    s.shared_dir = str(tmp_path)
    assert s.code_dir() == f"{tmp_path}/autopilot"
    (tmp_path / "rel").mkdir()
    (tmp_path / "current").symlink_to(tmp_path / "rel")
    assert s.code_dir() == f"{tmp_path}/current"


def test_the_host_scripts_and_plists_are_well_formed():
    import plistlib
    import subprocess
    from pathlib import Path

    d = Path(__file__).resolve().parent.parent / "deploy"
    for sh in ("apx-updater-setup.sh", "apx-switch-to-current.sh"):
        assert subprocess.run(["bash", "-n", str(d / sh)]).returncode == 0
    p = plistlib.loads((d / "launchd" / "com.autopilot.apx.updater.plist").read_bytes())
    cmd = p["ProgramArguments"][-1]
    assert p["UserName"] == "apx" and "--live" not in cmd and "APX_UPDATE_LIVE" not in cmd  # phase 1 is a dry run
    assert (
        p["WorkingDirectory"] == "/Users/Shared/apx/updater" and "/releases/" not in cmd
    )  # never runs from a release it manages
    sw = (d / "apx-switch-to-current.sh").read_text()
    assert "--live" in sw and "APX_UPDATE_LIVE=1" in sw and "/updater/src" in sw and ".bak" in sw
