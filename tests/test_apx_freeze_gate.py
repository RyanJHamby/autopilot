"""apx must not START anything (agent run, CI job, merge, branch update, updater test run) inside the work-hours freeze.

The window comes from policy/time.yaml through the one resolver, autopilot.freeze. There is no override. APX_ACTIVE_WINDOW can only
narrow what time.yaml allows. Instants are in UTC or ET and the clock is frozen, so none of this depends on when the suite runs.
"""

import base64
import datetime as dt
import inspect
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from test_apx_daemon import REPO, env

from autopilot import freeze
from autopilot.apx import daemon as dm
from autopilot.apx import executor as ex
from autopilot.apx import freeze_gate as fg
from autopilot.apx import ledger as ledger_mod
from autopilot.apx import update_main
from autopilot.apx.github import GitHubError
from autopilot.apx.planner import Action

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def et(y, mo, d, h, m=0):
    return dt.datetime(y, mo, d, h, m, tzinfo=ET)


MON_9AM = et(2026, 11, 16, 9)  # first frozen day, in the window
MON_7PM = et(2026, 11, 16, 19)


@pytest.fixture
def clock(monkeypatch):
    def set_(instant):
        monkeypatch.setattr(fg, "_clock", lambda: instant)

    return set_


def policy_file(tmp_path, monkeypatch, lift="[]", text=None):
    p = tmp_path / "time.yaml"
    p.write_text(
        text
        if text is not None
        else (
            f'timezone: America/New_York\nblackout:\n  days: [mon, tue, wed, thu, fri]\n  from: "08:30"\n  to: "18:30"\n'
            f"effective_from: 2026-11-16\nwind_down_minutes: 20\nfail_closed: true\nlift:\n  dates: {lift}\n"
        )
    )
    monkeypatch.setattr(fg, "POLICY_FILE", p)
    return p


# ---- the resolver wiring ----------------------------------------------------------------------------------------------------


def test_the_gate_uses_the_one_resolver_and_the_real_policy_file():
    assert fg.POLICY_FILE == freeze.DEFAULT_FILE
    assert "check_file" in inspect.getsource(fg)  # no second window arithmetic in this module
    assert not re.search(r"timedelta|ZoneInfo|weekday\(", inspect.getsource(fg))


@pytest.mark.parametrize(
    "instant, frozen",
    [
        (et(2026, 11, 16, 8, 29), False),
        (et(2026, 11, 16, 8, 30), True),
        (MON_9AM, True),
        (et(2026, 11, 20, 18, 29), True),  # a Friday
        (et(2026, 11, 16, 18, 30), False),
        (et(2026, 11, 21, 9), False),  # Saturday
        (et(2026, 11, 13, 9), False),  # a weekday before effective_from
    ],
)
def test_the_real_policy_in_and_out_of_the_window(clock, instant, frozen):
    clock(instant)
    assert (fg.frozen_reason() is not None) is frozen


@pytest.mark.parametrize(
    "utc_iso, frozen",
    [
        ("2026-11-16T13:29:00+00:00", False),  # 08:29 EST: winter, UTC-5
        ("2026-11-16T13:30:00+00:00", True),  # 08:30 EST
        ("2026-11-16T23:29:00+00:00", True),  # 18:29 EST
        ("2026-11-16T23:30:00+00:00", False),  # 18:30 EST
        ("2027-03-15T12:29:00+00:00", False),  # day after spring-forward: 08:29 EDT, UTC-4
        ("2027-03-15T12:30:00+00:00", True),  # 08:30 EDT: a hard-coded -5 would still call this free
        ("2027-03-15T22:29:00+00:00", True),  # 18:29 EDT
        ("2027-03-15T22:30:00+00:00", False),  # 18:30 EDT: a hard-coded -5 would still call this frozen
        ("2027-11-08T13:29:00+00:00", False),  # first Monday after fall-back: 08:29 EST
        ("2027-11-08T13:30:00+00:00", True),
    ],
)
def test_dst_boundaries_follow_new_york_not_a_fixed_offset(clock, utc_iso, frozen):
    clock(dt.datetime.fromisoformat(utc_iso))
    assert (fg.frozen_reason() is not None) is frozen


def test_the_host_timezone_is_irrelevant(clock, monkeypatch):
    import time

    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    try:
        clock(MON_9AM.astimezone(UTC))
        assert fg.frozen_reason() is not None
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_lift_dates_from_time_yaml_lift_that_day_only(tmp_path, monkeypatch, clock):
    policy_file(tmp_path, monkeypatch, lift="[2026-11-17]")
    clock(et(2026, 11, 17, 9))
    assert fg.frozen_reason() is None
    clock(et(2026, 11, 18, 9))
    assert fg.frozen_reason() is not None


# ---- fail closed ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",  # empty
        "{{{ not yaml",
        "- a\n- list\n",
        "timezone: UTC\n",  # wrong keys
        'timezone: Europe/London\nblackout: {days: [mon,tue,wed,thu,fri], from: "08:30", to: "18:30"}\neffective_from: 2026-11-16\n'
        "wind_down_minutes: 20\nfail_closed: true\nlift: {dates: []}\n",
        'timezone: America/New_York\nblackout: {days: [mon,tue,wed,thu,fri], from: "08:30", to: "18:30"}\neffective_from: 2099-01-01\n'
        "wind_down_minutes: 20\nfail_closed: false\nlift: {dates: []}\n",
    ],
)
def test_a_broken_policy_means_the_default_window_never_free_and_never_a_lift(tmp_path, monkeypatch, clock, text):
    policy_file(tmp_path, monkeypatch, text=text)
    clock(MON_9AM)
    assert fg.frozen_reason() is not None
    clock(MON_7PM)
    assert fg.frozen_reason() is None  # the default window is the same window, so evenings are still open


def test_a_missing_policy_file_is_frozen_in_the_window(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(fg, "POLICY_FILE", tmp_path / "nope.yaml")
    clock(MON_9AM)
    assert fg.frozen_reason() is not None


def test_a_broken_policy_cannot_lift_a_date(tmp_path, monkeypatch, clock):
    policy_file(tmp_path, monkeypatch, lift="[2026-11-17]", text="timezone: America/New_York\nlift: {dates: [2026-11-17]}\n")
    clock(et(2026, 11, 17, 9))
    assert fg.frozen_reason() is not None


def test_a_resolver_that_raises_is_frozen(monkeypatch, clock):
    clock(MON_7PM)  # a time that would be free

    def boom(*a, **k):
        raise RuntimeError("resolver bug")

    monkeypatch.setattr(freeze, "check_file", boom)
    assert "resolver" in fg.frozen_reason()


@pytest.mark.parametrize("bad", [dt.datetime(2026, 11, 16, 19), None, "later"])
def test_a_clock_that_is_naive_missing_or_wrong_is_frozen(monkeypatch, bad):
    monkeypatch.setattr(fg, "_clock", lambda: bad)
    assert fg.frozen_reason() is not None


def test_a_clock_that_raises_is_frozen(monkeypatch):
    def boom():
        raise OSError("no clock")

    monkeypatch.setattr(fg, "_clock", boom)
    assert fg.frozen_reason() is not None


# ---- no override ------------------------------------------------------------------------------------------------------------


def test_no_environment_variable_or_argument_lifts_it(monkeypatch, clock):
    clock(MON_9AM)
    for name in ("APX_FREEZE_OFF", "APX_FORCE", "APX_OVERRIDE", "AUTOPILOT_FREEZE_OFF", "FREEZE_OVERRIDE", "APX_ACTIVE_WINDOW"):
        monkeypatch.setenv(name, "1")
    assert fg.frozen_reason() is not None
    for fn in (fg.frozen_reason, fg.action_gate, fg.pass_blocked):
        bad = [p for p in inspect.signature(fn).parameters if re.search(r"force|override|skip|bypass|ignore|unfreeze|lift", p)]
        assert not bad, (fn.__name__, bad)


# ---- the check-run setting --------------------------------------------------------------------------------------------------


def portfolio(tmp_path, monkeypatch, text):
    p = tmp_path / "portfolio.yaml"
    p.write_text(text)
    monkeypatch.setattr(fg, "PORTFOLIO_FILE", p)


@pytest.mark.parametrize(
    "text", ["", "defaults: {}\n", "defaults: {apx_freeze_gates_check_runs: yes please}\n", "defaults: {apx_freeze_gates_check_runs: 0}\n",
             "{{{ bad", "- a\n", "defaults: {apx_freeze_gates_check_runs: null}\n"],
)
def test_check_runs_are_gated_unless_the_setting_is_literally_false(tmp_path, monkeypatch, clock, text):
    portfolio(tmp_path, monkeypatch, text)
    clock(MON_9AM)
    assert fg.checks_gated() is True
    assert fg.action_gate("check-pr") is not None and fg.action_gate("check-main") is not None


def test_a_missing_portfolio_file_gates_check_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "PORTFOLIO_FILE", tmp_path / "nope.yaml")
    assert fg.checks_gated() is True


def test_the_shipped_default_gates_check_runs():
    assert fg.checks_gated() is True
    import yaml

    assert yaml.safe_load(Path(fg.PORTFOLIO_FILE).read_text())["defaults"]["apx_freeze_gates_check_runs"] is True


def test_with_the_setting_false_only_check_runs_may_proceed_in_the_window(tmp_path, monkeypatch, clock):
    portfolio(tmp_path, monkeypatch, "defaults: {apx_freeze_gates_check_runs: false}\n")
    clock(MON_9AM)
    assert fg.checks_gated() is False
    assert fg.action_gate("check-pr") is None and fg.action_gate("check-main") is None
    for kind in ("run-agent", "fix-ci", "automerge", "update-branch", "something-new"):
        assert fg.action_gate(kind) is not None, kind


def test_an_unknown_action_kind_is_held_in_the_window(clock):
    clock(MON_9AM)
    assert fg.action_gate("brand-new-kind") is not None
    clock(MON_7PM)
    assert fg.action_gate("brand-new-kind") is None


# ---- APX_ACTIVE_WINDOW may only narrow --------------------------------------------------------------------------------------


def win(spec, **kw):
    from autopilot.apx import window

    return window.parse(spec, **kw)


def test_a_wider_apx_window_cannot_widen_the_freeze(clock):
    clock(MON_9AM)
    assert fg.pass_blocked(win("00:01-23:59", weekends="1")) is not None
    assert fg.pass_blocked(win("08:00-20:00")) is not None
    assert fg.pass_blocked(None) is not None


def test_a_narrower_apx_window_closes_what_time_yaml_leaves_open(clock):
    clock(MON_7PM)
    assert fg.pass_blocked(None) is None
    assert fg.pass_blocked(win("22:00-23:00")) is not None  # evening is free by policy, closed by the narrower setting
    assert fg.pass_blocked(win("18:30-23:00")) is None


def test_the_window_note_and_the_freeze_note_both_say_why(clock):
    clock(MON_9AM)
    assert "freeze" in fg.pass_blocked(None).lower()
    clock(MON_7PM)
    assert "active window" in fg.pass_blocked(win("22:00-23:00"))


# ---- the executor holds every action before it starts -----------------------------------------------------------------------


class Boom:
    """Fails the test if any lane is touched."""

    def __getattr__(self, name):
        raise AssertionError(f"lane {name} touched")


def deps_that_record(calls):
    def mk(name, ret):
        def f(*a, **k):
            calls.append(name)
            return ret

        return f

    return ex.Deps(
        checkout=mk("checkout", Path("/tmp")),
        guard=mk("guard", (True, "")),
        ci=mk("ci", (True, "")),
        work_on_issue=mk("work", ex.IssueResult(False, problems="x")),
        automerge=mk("automerge", (0, "")),
        fix_ci=mk("fix", ex.IssueResult(False, problems="x")),
    )


ALL = [
    Action("check-pr", REPO, "a" * 40, "PR #1"),
    Action("check-main", REPO, "b" * 40, "main"),
    Action("run-agent", REPO, "9", "x"),
    Action("fix-ci", REPO, f"4:{'c' * 40}", "x"),
    Action("automerge", REPO, f"4:{'c' * 40}", ""),
    Action("update-branch", REPO, "4", ""),
]


def test_a_gated_executor_starts_nothing_and_opens_no_ledger_row(tmp_path):
    api_calls, calls = [], []

    def api(method, path, body=None):
        api_calls.append((method, path))
        raise AssertionError("no API call may be made for a held action")

    led = ledger_mod.Ledger(str(tmp_path / "l.sqlite"))
    ctx = {REPO: {"guard": "g", "ci": "c"}}
    log = ex.execute(api, led, deps_that_record(calls), ALL, contexts=ctx, head_refs={}, dry_run=False, gate=lambda kind: "frozen: test")
    assert calls == [] and api_calls == []
    assert len(log) == len(ALL) and all(line.startswith("held ") and "frozen: test" in line for line in log)
    assert led.conn.execute("select count(*) from runs").fetchone()[0] == 0 if hasattr(led, "conn") else True


def test_the_gate_is_asked_before_each_action_so_a_pass_that_crosses_08_30_stops_midway(tmp_path):
    calls, asked = [], []
    open_for = iter([None, "frozen: 08:30 reached"])

    def gate(kind):
        asked.append(kind)
        return next(open_for, "frozen: 08:30 reached")

    def api(method, path, body=None):
        return {}

    led = ledger_mod.Ledger(str(tmp_path / "l.sqlite"))
    acts = [Action("automerge", REPO, f"4:{'c' * 40}", ""), Action("run-agent", REPO, "9", "x"), Action("update-branch", REPO, "4", "")]
    log = ex.execute(api, led, deps_that_record(calls), acts, contexts={}, head_refs={}, dry_run=False, gate=gate)
    assert asked == ["automerge", "run-agent", "update-branch"] and calls == ["automerge"]
    assert log[1].startswith("held ") and log[2].startswith("held ")


def test_a_gate_that_raises_holds_the_action(tmp_path):
    calls = []

    def gate(kind):
        raise RuntimeError("x")

    led = ledger_mod.Ledger(str(tmp_path / "l.sqlite"))
    log = ex.execute(lambda *a, **k: {}, led, deps_that_record(calls), ALL[2:3], contexts={}, head_refs={}, dry_run=False, gate=gate)
    assert calls == [] and log[0].startswith("held ")


def test_dry_run_is_unchanged_by_the_gate():
    log = ex.execute(Boom(), Boom(), None, ALL[:1], contexts={}, head_refs={}, dry_run=True, gate=lambda k: "frozen")  # type: ignore[arg-type]
    assert log[0].startswith("DRY-RUN check-pr")


# ---- the daemon: labelled issues and open PRs at 09:00 ET on a weekday ------------------------------------------------------


def live_factory(posts):
    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            if method != "GET":
                posts.append((method, path))
                return {}
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
                        "body": "## Acceptance\n- [ ] `uv run pytest tests/test_x.py`\n",
                    }
                ]
            if "/pulls?state=open" in path:
                return [
                    {
                        "number": 4,
                        "user": {"login": "RyanJHamby"},
                        "head": {"sha": "d" * 40, "ref": "agent/3-x", "repo": {"full_name": REPO}},
                    }
                ]
            if re.search(r"/repos/[^/]+/[^/]+$", path):
                return {"private": True}
            if path.endswith("/git/ref/heads/main"):
                return {"object": {"sha": "m" * 40}}
            if "/check-runs" in path:
                return {"check_runs": []}
            return []

        return api

    return factory


def live_settings(tmp_path):
    return dm.Settings.from_env(env(tmp_path, APX_AGENT_USER="apx-agent", APX_SHADOW="0"))


def test_run_once_at_0900_et_on_a_weekday_starts_nothing(tmp_path, monkeypatch, clock):
    clock(MON_9AM)
    monkeypatch.setenv("APX_LIVE", "1")
    posts = []
    monkeypatch.setattr(dm, "build_deps", lambda *a, **k: pytest.fail("deps were built: a lane could start"))
    out = dm.run_once(live_settings(tmp_path), live=True, api_factory=live_factory(posts))
    assert posts == [] and len(out) == 1 and "freeze" in out[0].lower() and "nothing ran" in out[0]


def test_the_same_pass_at_7pm_does_start_work_so_the_test_above_can_fail(tmp_path, monkeypatch, clock):
    clock(MON_7PM)
    monkeypatch.setenv("APX_LIVE", "1")
    calls = []
    monkeypatch.setattr(dm, "build_deps", lambda *a, **k: deps_that_record(calls))
    posts = []
    out = dm.run_once(live_settings(tmp_path), live=True, api_factory=live_factory(posts))
    assert "check-pr" in " ".join(out) or "check-pr" in str(posts) or calls
    assert "work" in calls or any(x.startswith("run-agent") for x in out)


def test_run_once_midpass_freeze_holds_what_is_left(tmp_path, monkeypatch, clock):
    """The pass is allowed to begin at 18:29 ET... but not to keep starting work after 08:30 the next morning."""
    clock(et(2026, 11, 16, 8, 29))
    monkeypatch.setenv("APX_LIVE", "1")
    calls = []
    ticks = iter([et(2026, 11, 16, 8, 29), et(2026, 11, 16, 8, 29)] + [et(2026, 11, 16, 8, 31)] * 200)
    monkeypatch.setattr(fg, "_clock", lambda: next(ticks))
    monkeypatch.setattr(dm, "build_deps", lambda *a, **k: deps_that_record(calls))
    out = dm.run_once(live_settings(tmp_path), live=True, api_factory=live_factory([]))
    assert calls == [] and any(line.startswith("held ") for line in out)


def patch_main(monkeypatch, tmp_path, st):
    monkeypatch.setattr(dm.Settings, "from_env", classmethod(lambda cls, e=None: st))
    monkeypatch.setattr(dm, "run_once", lambda *a, **k: pytest.fail("a pass ran"))
    monkeypatch.setenv("APX_STATUS", str(tmp_path / "status.json"))


def test_main_is_idle_in_the_window_even_with_a_wide_apx_window(tmp_path, monkeypatch, clock):
    import json

    clock(MON_9AM)
    st = dm.Settings.from_env(env(tmp_path, APX_ACTIVE_WINDOW="00:01-23:59"))
    patch_main(monkeypatch, tmp_path, st)
    assert dm.main(["--once", "--live"]) == 0
    body = json.loads((tmp_path / "status.json").read_text())
    assert body["idle"] is True and "freeze" in body["lines"][0].lower()


def test_main_with_no_apx_window_at_all_is_still_idle_in_the_window(tmp_path, monkeypatch, clock):
    clock(MON_9AM)
    st = dm.Settings.from_env(env(tmp_path))
    assert st.active_window is None
    patch_main(monkeypatch, tmp_path, st)
    assert dm.main(["--once"]) == 0


def test_main_runs_a_pass_out_of_the_window(tmp_path, monkeypatch, clock):
    clock(MON_7PM)
    st = dm.Settings.from_env(env(tmp_path))
    monkeypatch.setattr(dm.Settings, "from_env", classmethod(lambda cls, e=None: st))
    monkeypatch.setenv("APX_STATUS", str(tmp_path / "status.json"))
    ran = []
    monkeypatch.setattr(dm, "run_once", lambda *a, **k: ran.append(1) or ["ok"])
    assert dm.main(["--once"]) == 0 and ran == [1]


def test_the_updater_does_not_fetch_test_or_swap_in_the_window(tmp_path, monkeypatch, clock):
    clock(MON_9AM)
    st = dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci"))
    monkeypatch.setattr(update_main.Settings, "from_env", classmethod(lambda cls, e=None: st))
    monkeypatch.setattr(update_main, "TokenCache", lambda *a, **k: pytest.fail("the updater reached for GitHub in the freeze"))
    monkeypatch.setenv("APX_UPDATE_STATUS", str(tmp_path / "u.json"))
    monkeypatch.setenv("APX_UPDATE_LIVE", "1")
    monkeypatch.setenv("APX_RELEASES_ROOT", str(tmp_path))
    assert update_main.main(["--live"]) == 0
    assert "freeze" in (tmp_path / "u.json").read_text().lower()
