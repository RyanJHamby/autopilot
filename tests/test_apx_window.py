import datetime as dt

import pytest

from autopilot.apx import daemon, release, window
from autopilot.apx.daemon import ConfigError, Settings

UTC = dt.timezone.utc
W = window.parse("18:00-08:30")


def at(y, mo, d, h, m=0, tz="America/New_York"):
    from zoneinfo import ZoneInfo

    return dt.datetime(y, mo, d, h, m, tzinfo=ZoneInfo(tz))


def test_empty_spec_means_always_on():
    assert window.parse("") is None and window.parse("  ") is None


@pytest.mark.parametrize("bad", ["18:00", "6pm-8am", "25:00-08:00", "18:00-18:00", "18:00-08:60", "-"])
def test_malformed_specs_are_refused_not_treated_as_always_on(bad):
    with pytest.raises(ValueError):
        window.parse(bad)


def test_unknown_zone_is_refused():
    with pytest.raises(ValueError):
        window.parse("18:00-08:30", tz="Mars/Olympus")


def test_weekday_hours_are_closed_and_nights_are_open():
    # Friday 2026-10-30
    assert not W.is_open(at(2026, 10, 30, 8, 30))  # the end is exclusive
    assert not W.is_open(at(2026, 10, 30, 12))
    assert not W.is_open(at(2026, 10, 30, 17, 59))
    assert W.is_open(at(2026, 10, 30, 18, 0))
    assert W.is_open(at(2026, 10, 30, 8, 29))
    assert W.is_open(at(2026, 10, 29, 23, 59))


def test_weekends_are_open_all_day_unless_turned_off():
    sat_noon = at(2026, 10, 31, 12)
    assert W.is_open(sat_noon)
    assert not window.parse("18:00-08:30", weekends="0").is_open(sat_noon)


def test_it_uses_the_zone_not_utc_and_follows_dst():
    # 2026-10-30 21:00 UTC is 17:00 EDT (closed); 22:00 UTC is 18:00 EDT (open)
    assert not W.is_open(dt.datetime(2026, 10, 30, 21, 0, tzinfo=UTC))
    assert W.is_open(dt.datetime(2026, 10, 30, 22, 0, tzinfo=UTC))
    # after DST ends (2026-11-01) the same UTC hour is one hour earlier locally: 22:00 UTC = 17:00 EST (closed on Monday)
    assert not W.is_open(dt.datetime(2026, 11, 2, 22, 0, tzinfo=UTC))
    assert W.is_open(dt.datetime(2026, 11, 2, 23, 0, tzinfo=UTC))


def test_same_day_window_without_wrap():
    w = window.parse("09:00-17:00", weekends="0")
    assert w.is_open(at(2026, 10, 30, 9)) and not w.is_open(at(2026, 10, 30, 17))


def test_minutes_left_counts_to_the_close_and_is_zero_when_closed():
    assert window.minutes_left(W, at(2026, 10, 30, 7, 50)) == 40
    assert window.minutes_left(W, at(2026, 10, 30, 12)) == 0


ENV = {
    "APX_APP_ID": "1",
    "APX_KEY_PATH": "/k",
    "APX_INSTALLATIONS": "RyanJHamby/autopilot=1",
    "APX_OAUTH_FILE": "/o",
    "APX_KIT_REPO": "RyanJHamby/autopilot-kit",
    "APX_KIT_REF": "a" * 40,
}


def test_settings_reads_the_window_and_rejects_a_bad_one():
    assert Settings.from_env({**ENV}).active_window is None
    s = Settings.from_env({**ENV, "APX_ACTIVE_WINDOW": "18:00-08:30", "APX_ACTIVE_TZ": "America/New_York"})
    assert s.active_window == W
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, "APX_ACTIVE_WINDOW": "nonsense"})


def test_a_pass_outside_the_window_runs_nothing_and_writes_an_idle_heartbeat(tmp_path, monkeypatch):
    st = Settings.from_env({**ENV, "APX_ACTIVE_WINDOW": "18:00-08:30"})
    monkeypatch.setattr(daemon.Settings, "from_env", classmethod(lambda cls, env=None: st))
    monkeypatch.setattr(daemon, "run_once", lambda *a, **k: pytest.fail("a pass ran outside the window"))
    closed = at(2026, 10, 30, 12).astimezone(UTC)

    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return closed

    monkeypatch.setattr(daemon.dt, "datetime", Clock)
    out = tmp_path / "status.json"
    monkeypatch.setenv("APX_STATUS", str(out))
    assert daemon.main(["--once"]) == 0
    import json

    body = json.loads(out.read_text())
    assert body["idle"] is True and body["ok"] is True and "outside the active window" in body["lines"][0]


def test_an_idle_heartbeat_is_never_proof_for_the_canary(tmp_path):
    import json

    root = tmp_path
    swapped = dt.datetime(2026, 10, 30, 22, 0, tzinfo=UTC)
    (root / "swap.json").write_text(json.dumps({"sha": "b" * 40, "previous": "a" * 40, "at": swapped.isoformat()}))
    later = swapped + dt.timedelta(minutes=20)
    status = {"ts": later.isoformat(), "ok": True, "version": "b" * 7, "idle": True}
    assert release.canary(root, status, later) == "pending"
    assert release.canary(root, {**status, "idle": False}, later) == "healthy"
