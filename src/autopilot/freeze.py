"""The work-hours freeze resolver (plan Part M M1, work item W0-10).

One pure function, `check(policy, now)`, says whether personal-repo work must stop. The window is Mon-Fri 08:30-18:30
America/New_York from 2026-11-16, read from policy/time.yaml. It is converted with zoneinfo, never with a UTC offset,
and the machine's own timezone is irrelevant.

There is no override: no environment variable, flag or argument lifts the freeze. The only lift is a date listed in
time.yaml (owner-edited). Anything unreadable or inconsistent fails closed: a bad policy file falls back to the default
window below (the same values), a clock that cannot be read is frozen, and clock skew over two minutes is frozen.

    python -m autopilot.freeze [--at ISO8601] [--file PATH]     exit 0 = free, exit 1 = frozen (reason on stdout)
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ET = ZoneInfo("America/New_York")
TIMEZONE = "America/New_York"
MAX_SKEW = dt.timedelta(minutes=2)
DEFAULT_FILE = Path(__file__).resolve().parents[2] / "policy" / "time.yaml"
_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_KEYS = {"timezone", "blackout", "effective_from", "wind_down_minutes", "fail_closed", "lift"}


class PolicyError(ValueError):
    """time.yaml is missing, unreadable or breaks a rule. Callers treat this as the default window, never as 'free'."""


@dataclass(frozen=True)
class Policy:
    timezone: str
    days: tuple[int, ...]
    start: dt.time
    end: dt.time
    effective_from: dt.date
    wind_down_minutes: int
    fail_closed: bool
    lift_dates: frozenset[dt.date]


@dataclass(frozen=True)
class Verdict:
    frozen: bool
    reason: str
    until: dt.datetime | None = None  # when the freeze ends (ET), set while frozen
    wind_down: bool = False  # inside the checkpoint period just before the window


def default_policy(**over) -> Policy:
    """The plan's M1 values. Used when time.yaml cannot be trusted, so a broken file never means 'no freeze'."""
    p = Policy(
        timezone=TIMEZONE, days=(0, 1, 2, 3, 4), start=dt.time(8, 30), end=dt.time(18, 30),
        effective_from=dt.date(2026, 11, 16), wind_down_minutes=20, fail_closed=True, lift_dates=frozenset(),
    )
    return Policy(**{**p.__dict__, **over})


def _hhmm(value, name: str) -> dt.time:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":" or not (value[:2] + value[3:]).isdigit():
        raise PolicyError(f"{name} must be a quoted HH:MM string, got {value!r}")
    h, m = int(value[:2]), int(value[3:])
    if h > 23 or m > 59:
        raise PolicyError(f"{name} is not a time: {value!r}")
    return dt.time(h, m)


def load(path) -> Policy:
    try:
        raw = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as e:
        raise PolicyError(f"cannot read {path}: {e}") from e
    if not isinstance(raw, dict):
        raise PolicyError("time.yaml must be a mapping")
    if set(raw) != _KEYS:
        raise PolicyError(f"time.yaml keys must be exactly {sorted(_KEYS)}, got {sorted(raw)}")
    if raw["timezone"] != TIMEZONE:
        raise PolicyError(f"timezone must be {TIMEZONE} (M1-02), got {raw['timezone']!r}")
    if raw["fail_closed"] is not True:
        raise PolicyError("fail_closed must be true (M1-06)")
    bl = raw["blackout"]
    if not isinstance(bl, dict) or set(bl) != {"days", "from", "to"}:
        raise PolicyError("blackout needs exactly days, from, to")
    days = bl["days"]
    if days != ["mon", "tue", "wed", "thu", "fri"]:
        raise PolicyError("blackout.days must be [mon, tue, wed, thu, fri] (M1)")
    start, end = _hhmm(bl["from"], "blackout.from"), _hhmm(bl["to"], "blackout.to")
    if start >= end:
        raise PolicyError("blackout.from must be before blackout.to (the window does not cross midnight)")
    eff = raw["effective_from"]
    if type(eff) is not dt.date:
        raise PolicyError(f"effective_from must be an unquoted YYYY-MM-DD date, got {eff!r}")
    wd = raw["wind_down_minutes"]
    if type(wd) is not int or wd < 0:
        raise PolicyError(f"wind_down_minutes must be a non-negative integer, got {wd!r}")
    lift = raw["lift"]
    if not isinstance(lift, dict) or set(lift) != {"dates"} or not isinstance(lift["dates"], list):
        raise PolicyError("lift must be {dates: [...]}")
    dates = []
    for d in lift["dates"]:
        if type(d) is not dt.date:
            raise PolicyError(f"lift.dates entries must be unquoted YYYY-MM-DD dates, got {d!r}")
        if d.weekday() not in (0, 1, 2, 3, 4):
            raise PolicyError(f"lift date {d} is not a weekday, so there is nothing to lift")
        dates.append(d)
    return Policy(TIMEZONE, (0, 1, 2, 3, 4), start, end, eff, wd, True, frozenset(dates))


def check(policy: Policy, now: dt.datetime, reference: dt.datetime | None = None) -> Verdict:
    """Is the freeze in force at `now`? `now` must be timezone-aware. `reference` is an independent clock reading
    (e.g. from a network or hardware source); if it differs by more than two minutes the answer is frozen."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if reference is not None:
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise ValueError("reference must be timezone-aware")
        if abs(reference - now) > MAX_SKEW:
            return Verdict(True, "clock skew over 2 minutes: refusing until the clocks agree")
    local = now.astimezone(ET)
    day = local.date()
    if day < policy.effective_from:
        return Verdict(False, f"before effective_from {policy.effective_from}: no freeze yet")
    if local.weekday() not in policy.days:
        return Verdict(False, "weekend")
    start = dt.datetime.combine(day, policy.start, tzinfo=ET)
    end = dt.datetime.combine(day, policy.end, tzinfo=ET)
    if day in policy.lift_dates:
        return Verdict(False, f"window lifted for {day} in time.yaml")
    if start <= local < end:
        return Verdict(True, f"work-hours freeze until {end:%H:%M} ET", until=end)
    wind = start - dt.timedelta(minutes=policy.wind_down_minutes)
    if wind <= local < start:
        return Verdict(False, f"winding down: freeze starts at {start:%H:%M} ET", wind_down=True)
    return Verdict(False, "outside the window")


def check_file(path=DEFAULT_FILE, clock=None, reference: dt.datetime | None = None) -> Verdict:
    """Read the policy and the clock and answer, failing closed on any problem."""
    now = None
    try:
        now = (clock or (lambda: dt.datetime.now(dt.timezone.utc)))()
    except Exception as e:  # noqa: BLE001 - any clock failure is frozen
        return Verdict(True, f"clock unreadable ({type(e).__name__}): frozen")
    try:
        policy = load(path)
        note = ""
    except PolicyError as e:
        policy = default_policy()
        note = f"time.yaml unusable ({e}); using the default window. "
    try:
        v = check(policy, now, reference)
    except ValueError as e:
        return Verdict(True, f"{note}bad clock value: {e}")
    return Verdict(v.frozen, note + v.reason, v.until, v.wind_down) if note else v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--at", help="ISO 8601 instant with offset, for tests and drills; omitted means now")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    a = ap.parse_args(argv)
    clock = None
    if a.at:
        def clock():
            return dt.datetime.fromisoformat(a.at)
    v = check_file(a.file, clock=clock)
    print(("frozen: " if v.frozen else "free: ") + v.reason)
    return 1 if v.frozen else 0


if __name__ == "__main__":
    sys.exit(main())
