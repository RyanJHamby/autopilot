"""The work-hours freeze resolver (plan Part M M1, W0-10): Mon-Fri 08:30-18:30 America/New_York, from 2026-11-16.

Every instant below is given in UTC on purpose: the resolver must convert with zoneinfo, never with a fixed offset.
"""

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from autopilot import freeze

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parent.parent
REAL = REPO / "policy" / "time.yaml"


def utc(y, mo, d, h, m=0):
    return dt.datetime(y, mo, d, h, m, tzinfo=UTC)


def policy(**over):
    base = dict(effective_from=dt.date(2026, 1, 1), lift_dates=frozenset())
    base.update(over)
    return freeze.default_policy(**base)


# --- the real file ---------------------------------------------------------------------------------------------

def test_real_policy_file_matches_the_plan():
    p = freeze.load(REAL)
    assert p.timezone == "America/New_York"
    assert p.days == (0, 1, 2, 3, 4)
    assert (p.start, p.end) == (dt.time(8, 30), dt.time(18, 30))
    assert p.effective_from == dt.date(2026, 11, 16)
    assert p.wind_down_minutes == 20 and p.fail_closed is True and p.lift_dates == frozenset()


def test_real_policy_file_has_no_unknown_keys_and_is_quoted_times():
    raw = yaml.safe_load(REAL.read_text())
    assert set(raw) == {"timezone", "blackout", "effective_from", "wind_down_minutes", "fail_closed", "lift"}
    assert isinstance(raw["blackout"]["from"], str) and isinstance(raw["blackout"]["to"], str)  # unquoted 08:30 is an int in YAML 1.1


def test_default_policy_equals_the_real_file():
    real = freeze.load(REAL)
    d = freeze.default_policy()
    assert d == real


# --- before and after effective_from --------------------------------------------------------------------------

def test_no_blackout_before_effective_from():
    p = freeze.load(REAL)
    v = freeze.check(p, utc(2026, 11, 13, 15))  # Friday 10:00 EST
    assert not v.frozen and "effective" in v.reason


def test_first_frozen_instant_is_monday_1630_boundary():
    p = freeze.load(REAL)
    assert not freeze.check(p, utc(2026, 11, 16, 13, 29)).frozen  # 08:29 EST
    v = freeze.check(p, utc(2026, 11, 16, 13, 30))  # 08:30 EST
    assert v.frozen and v.until == dt.datetime(2026, 11, 16, 18, 30, tzinfo=freeze.ET)


def test_end_is_exclusive():
    p = freeze.load(REAL)
    assert freeze.check(p, utc(2026, 11, 16, 23, 29)).frozen  # 18:29 EST
    assert not freeze.check(p, utc(2026, 11, 16, 23, 30)).frozen  # 18:30 EST


def test_weekends_are_never_frozen():
    p = policy()
    assert not freeze.check(p, utc(2026, 11, 21, 15)).frozen  # Saturday noon
    assert not freeze.check(p, utc(2026, 11, 22, 15)).frozen  # Sunday noon


# --- DST: same wall clock, different UTC -----------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,edge_utc,frozen",
    [
        ("2027-03-15 EDT 08:29", utc(2027, 3, 15, 12, 29), False),
        ("2027-03-15 EDT 08:30", utc(2027, 3, 15, 12, 30), True),
        ("2027-03-15 EDT 18:29", utc(2027, 3, 15, 22, 29), True),
        ("2027-03-15 EDT 18:30", utc(2027, 3, 15, 22, 30), False),
        ("2027-11-08 EST 08:29", utc(2027, 11, 8, 13, 29), False),
        ("2027-11-08 EST 08:30", utc(2027, 11, 8, 13, 30), True),
        ("2027-11-08 EST 18:29", utc(2027, 11, 8, 23, 29), True),
        ("2027-11-08 EST 18:30", utc(2027, 11, 8, 23, 30), False),
    ],
)
def test_dst_days_follow_wall_clock_not_a_fixed_utc_offset(label, edge_utc, frozen):
    assert freeze.check(policy(), edge_utc).frozen is frozen, label


def test_until_is_wall_clock_after_the_dst_change():
    v = freeze.check(policy(), utc(2027, 3, 15, 15))
    assert v.until.astimezone(UTC) == utc(2027, 3, 15, 22, 30)


# --- the machine's timezone is irrelevant ---------------------------------------------------------------------

def test_laptop_in_another_timezone_still_follows_et():
    p = policy()
    tokyo = dt.timezone(dt.timedelta(hours=9))
    la = dt.timezone(dt.timedelta(hours=-8))
    # 2026-11-17 14:00 EST is 04:00 next day in Tokyo and 11:00 in LA: frozen in all views
    for tz in (tokyo, la):
        assert freeze.check(p, utc(2026, 11, 17, 19).astimezone(tz)).frozen
    # 2026-11-17 19:00 EST is 09:00 next day in Tokyo (inside the window there) but is not frozen in ET
    assert not freeze.check(p, utc(2026, 11, 18, 0).astimezone(tokyo)).frozen


def test_naive_datetime_is_rejected_not_guessed():
    with pytest.raises(ValueError):
        freeze.check(policy(), dt.datetime(2026, 11, 17, 12))


# --- holidays: lift only if listed -----------------------------------------------------------------------------

def test_us_holiday_is_frozen_unless_listed():
    thanksgiving = utc(2026, 11, 26, 15)  # Thursday 10:00 EST
    assert freeze.check(policy(), thanksgiving).frozen
    lifted = policy(lift_dates=frozenset({dt.date(2026, 11, 26)}))
    v = freeze.check(lifted, thanksgiving)
    assert not v.frozen and "lift" in v.reason


def test_lift_is_by_et_date_not_utc_date():
    lifted = policy(lift_dates=frozenset({dt.date(2026, 11, 26)}))
    assert not freeze.check(lifted, utc(2026, 11, 26, 14)).frozen  # still the 26th in ET
    assert freeze.check(lifted, utc(2026, 11, 27, 14)).frozen  # the 27th is a normal Friday


# --- wind-down -------------------------------------------------------------------------------------------------

def test_wind_down_starts_20_minutes_before_the_window():
    p = policy()
    before = freeze.check(p, utc(2026, 11, 17, 13, 9))  # 08:09 EST
    assert not before.frozen and not before.wind_down
    during = freeze.check(p, utc(2026, 11, 17, 13, 10))  # 08:10 EST
    assert not during.frozen and during.wind_down and "wind" in during.reason
    assert freeze.check(p, utc(2026, 11, 17, 13, 30)).wind_down is False  # frozen takes over


def test_no_wind_down_on_a_weekend_or_before_effective_from():
    assert not freeze.check(policy(), utc(2026, 11, 21, 13, 15)).wind_down
    assert not freeze.check(freeze.load(REAL), utc(2026, 11, 13, 13, 15)).wind_down


# --- clock skew ------------------------------------------------------------------------------------------------

def test_skew_over_two_minutes_refuses_even_outside_the_window():
    p = policy()
    night = utc(2026, 11, 17, 3)  # 22:00 EST
    v = freeze.check(p, night, reference=night + dt.timedelta(seconds=121))
    assert v.frozen and "skew" in v.reason


def test_skew_within_two_minutes_is_fine():
    night = utc(2026, 11, 17, 3)
    assert not freeze.check(policy(), night, reference=night + dt.timedelta(seconds=120)).frozen


# --- the policy file is validated, not trusted -----------------------------------------------------------------

GOOD = {
    "timezone": "America/New_York",
    "blackout": {"days": ["mon", "tue", "wed", "thu", "fri"], "from": "08:30", "to": "18:30"},
    "effective_from": dt.date(2026, 11, 16),
    "wind_down_minutes": 20,
    "fail_closed": True,
    "lift": {"dates": []},
}


def write(tmp_path, **over):
    d = {**GOOD, **over}
    p = tmp_path / "time.yaml"
    p.write_text(yaml.safe_dump(d))
    return p


def test_good_file_loads(tmp_path):
    assert freeze.load(write(tmp_path)).timezone == "America/New_York"


@pytest.mark.parametrize(
    "over",
    [
        {"timezone": "UTC"},
        {"timezone": "Europe/London"},
        {"fail_closed": False},
        {"fail_closed": "yes"},
        {"blackout": {"days": ["mon"], "from": "08:30", "to": "18:30"}},
        {"blackout": {"days": ["mon", "tue", "wed", "thu", "fri"], "from": "18:30", "to": "08:30"}},
        {"blackout": {"days": ["mon", "tue", "wed", "thu", "fri"], "from": "8:30", "to": "18:30"}},
        {"blackout": {"days": ["mon", "tue", "wed", "thu", "fri"], "from": 510, "to": "18:30"}},
        {"effective_from": "2026-11-16"},
        {"wind_down_minutes": -1},
        {"wind_down_minutes": True},
        {"lift": {"dates": ["2026-11-26"]}},
        {"lift": {"dates": [dt.date(2026, 11, 14)]}},  # a Saturday: nothing to lift, so the entry is a mistake
        {"lift": "none"},
    ],
)
def test_bad_values_are_refused_not_defaulted(tmp_path, over):
    with pytest.raises(freeze.PolicyError):
        freeze.load(write(tmp_path, **over))


def test_unknown_key_is_refused(tmp_path):
    with pytest.raises(freeze.PolicyError):
        freeze.load(write(tmp_path, bypass=True))


def test_missing_key_is_refused(tmp_path):
    p = write(tmp_path)
    d = yaml.safe_load(p.read_text())
    del d["fail_closed"]
    p.write_text(yaml.safe_dump(d))
    with pytest.raises(freeze.PolicyError):
        freeze.load(p)


def test_missing_and_unparseable_files_are_refused(tmp_path):
    with pytest.raises(freeze.PolicyError):
        freeze.load(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    with pytest.raises(freeze.PolicyError):
        freeze.load(bad)


# --- fail closed -----------------------------------------------------------------------------------------------

def test_unreadable_policy_uses_the_default_window_inside_hours(tmp_path):
    inside = utc(2026, 11, 17, 15)
    v = freeze.check_file(tmp_path / "missing.yaml", clock=lambda: inside)
    assert v.frozen and "default" in v.reason


def test_unreadable_policy_does_not_freeze_the_night(tmp_path):
    night = utc(2026, 11, 17, 3)
    v = freeze.check_file(tmp_path / "missing.yaml", clock=lambda: night)
    assert not v.frozen


def test_unreadable_policy_does_not_freeze_before_effective_from(tmp_path):
    v = freeze.check_file(tmp_path / "missing.yaml", clock=lambda: utc(2026, 11, 13, 15))
    assert not v.frozen


def test_clock_failure_is_frozen():
    def boom():
        raise OSError("no clock")

    v = freeze.check_file(REAL, clock=boom)
    assert v.frozen and "clock" in v.reason


def test_lift_in_a_broken_file_is_not_honoured(tmp_path):
    thanksgiving = utc(2026, 11, 26, 15)
    p = write(tmp_path, fail_closed=False, lift={"dates": [dt.date(2026, 11, 26)]})
    assert freeze.check_file(p, clock=lambda: thanksgiving).frozen


# --- no bypass -------------------------------------------------------------------------------------------------

def test_environment_cannot_lift_the_freeze(monkeypatch):
    for k in ("PLAN_NOW", "FREEZE_OVERRIDE", "AUTOPILOT_FREEZE_OFF", "PUSH_SCAN_OVERRIDE", "APX_ACTIVE_WINDOW"):
        monkeypatch.setenv(k, "1")
    assert freeze.check_file(REAL, clock=lambda: utc(2026, 11, 17, 15)).frozen


def test_cli_exit_codes_and_no_flag_to_lift_it(tmp_path):
    def run(*args, env=None):
        return subprocess.run(
            [sys.executable, "-m", "autopilot.freeze", *args], cwd=REPO, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin", **(env or {})},
        )

    r = run("--at", "2026-11-17T15:00:00+00:00")
    assert r.returncode == 1 and "frozen" in r.stdout and "18:30" in r.stdout
    assert run("--at", "2026-11-17T03:00:00+00:00").returncode == 0
    assert run("--at", "garbage").returncode == 1  # an unparseable time is frozen, not "ok"
    assert run("--at", "2026-11-17T15:00:00+00:00", env={"FREEZE_OVERRIDE": "1"}).returncode == 1
    assert run("--lift").returncode != 0  # argparse refuses an unknown flag
