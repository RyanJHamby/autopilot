import datetime as dt
import json
import plistlib
import stat
from pathlib import Path

import pytest

from autopilot.apx import daemon as dm
from autopilot.apx import status

NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=dt.timezone.utc)
PLIST = Path(__file__).resolve().parent.parent / "deploy" / "launchd" / "com.autopilot.apx.watch.plist"


def test_the_status_file_is_atomic_world_readable_redacted_and_marks_problems(tmp_path):
    key = "sk-ant-" + "oat01-" + "Kp4_" * 12
    p = tmp_path / "status.json"
    assert status.write_status(p, ["r/a: 0 action(s) - ok", f"r/b: planner error {key}"], live=True, version="abc1234", now=NOW)
    body = json.loads(p.read_text())
    assert body["ok"] is False and body["live"] is True and body["version"] == "abc1234"
    assert key not in p.read_text()
    assert stat.S_IMODE(p.stat().st_mode) == 0o644
    assert [f.name for f in tmp_path.iterdir()] == ["status.json"]  # no temp file left behind
    assert status.write_status(p, ["r/a: ok"], live=False, now=NOW) and json.loads(p.read_text())["ok"] is True


def test_writing_status_never_raises(tmp_path):
    assert status.write_status(tmp_path / "no" / "such" / "dir" / "s.json", ["x"], live=False) is False


@pytest.mark.parametrize(
    "mins,lines,level",
    [(1, ["a: ok"], "ok"), (30, ["a: ok"], "stale"), (1, ["a: planner error (fail closed): TimeoutError"], "problem")],
)
def test_check_status_levels(tmp_path, mins, lines, level):
    p = tmp_path / "s.json"
    status.write_status(p, lines, live=True, now=NOW - dt.timedelta(minutes=mins))
    assert status.check_status(p, now=NOW)[0] == level


def test_a_missing_or_garbled_status_file_is_reported_not_crashed_on(tmp_path):
    assert status.check_status(tmp_path / "none.json", now=NOW)[0] == "missing"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert status.check_status(bad, now=NOW)[0] == "missing"
    bad.write_text('{"ts": "garbage"}')
    assert status.check_status(bad, now=NOW)[0] == "missing"


def test_the_watcher_notifies_once_per_problem_and_once_when_it_clears(tmp_path):
    p, state, sent = tmp_path / "s.json", tmp_path / "state", []
    note = lambda t, m: sent.append((t, m))  # noqa: E731
    status.write_status(p, ["a: ok"], live=True, now=NOW)
    assert status.watch_once(p, state, now=NOW, notifier=note) == "ok" and sent == []  # healthy and quiet
    later = NOW + dt.timedelta(minutes=40)
    for _ in range(3):
        assert status.watch_once(p, state, now=later, notifier=note) == "stale"
    assert len(sent) == 1 and "40 minutes" in sent[0][1]  # three checks, one notification
    status.write_status(p, ["a: ok"], live=True, now=later)
    assert status.watch_once(p, state, now=later, notifier=note) == "ok"
    assert len(sent) == 2 and "running again" in sent[1][1]
    status.watch_once(p, state, now=later, notifier=note)
    assert len(sent) == 2


def test_a_growing_staleness_does_not_renotify_but_a_different_problem_does(tmp_path):
    p, state, sent = tmp_path / "s.json", tmp_path / "state", []
    note = lambda t, m: sent.append(m)  # noqa: E731
    status.write_status(p, ["a: ok"], live=True, now=NOW)
    for mins in (30, 35, 40, 120):
        status.watch_once(p, state, now=NOW + dt.timedelta(minutes=mins), notifier=note)
    assert len(sent) == 1  # still stale, only longer
    now = NOW + dt.timedelta(minutes=121)
    status.write_status(p, ["a: planner error (fail closed): TimeoutError"], live=True, now=now)
    status.watch_once(p, state, now=now, notifier=note)
    status.write_status(p, ["a: crashed: ValueError"], live=True, now=now)
    status.watch_once(p, state, now=now, notifier=note)
    assert len(sent) == 3  # each distinct problem is told once


def test_the_notification_text_is_passed_as_arguments_never_spliced_into_the_script(monkeypatch):
    seen = {}
    monkeypatch.setattr(status.subprocess, "run", lambda argv, **k: seen.setdefault("argv", argv))
    status.notify("apx", 'a "quote" and \\ and $(rm -rf x)')
    argv = seen["argv"]
    assert argv[0] == "/usr/bin/osascript" and argv[-1] == 'a "quote" and \\ and $(rm -rf x)'
    assert "quote" not in argv[2] and "rm -rf" not in argv[2]  # the script text itself never contains the message


def test_status_never_touches_the_network_or_any_other_person():
    src = Path(status.__file__).read_text()
    for banned in ("urllib", "requests", "http", "smtp", "socket", "slack", "mailto"):
        assert banned not in src.lower().replace("world-readable", ""), banned


def test_the_launch_agent_runs_the_watcher_as_the_owner_with_no_secrets_and_lints():
    text = PLIST.read_text()
    assert "autopilot.apx.status" in text and "<key>UserName</key>" not in text  # a LaunchAgent: runs as the logged-in owner
    assert "TOKEN" not in text and "KEY" not in text.replace("<key>", "").replace("</key>", "")
    plist = plistlib.loads(PLIST.read_bytes())  # parses on any OS (plutil exists only on macOS)
    assert plist["Label"] == "com.autopilot.apx.watch" and plist["StartInterval"] == 300 and "RunAtLoad" in plist


def test_main_writes_status_after_a_pass_and_records_a_crash(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    monkeypatch.setenv("APX_STATUS", str(p))
    from test_apx_daemon import env

    for k, v in env(tmp_path).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(dm, "run_once", lambda s, live=False: ["r/a: 0 action(s) - ok"])
    assert dm.main(["--once"]) == 0 and json.loads(p.read_text())["ok"] is True
    monkeypatch.setattr(dm, "run_once", lambda s, live=False: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        dm.main(["--once"])
    body = json.loads(p.read_text())
    assert body["ok"] is False and "pass crashed: RuntimeError" in body["problems"][0]
