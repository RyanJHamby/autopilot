import datetime as dt

from autopilot import picker


def R(name, prio, cap):
    return {"name": name, "priority": prio, "capacity": cap}


def test_priority_weighted_slices():
    assert picker.allocate([R("a", 8, 10), R("b", 2, 10)], 10) == {"a": 8, "b": 2}


def test_work_conserving_rollover_to_busy_repo():
    # b has no work, so its share goes to a, up to a's capacity
    assert picker.allocate([R("a", 5, 6), R("b", 5, 0)], 10) == {"a": 6}


def test_capacity_caps_and_leftover_goes_to_next_priority():
    assert picker.allocate([R("a", 9, 2), R("b", 1, 9)], 10) == {"a": 2, "b": 8}


def test_reserve_and_empty():
    assert picker.allocate([R("a", 5, 9)], 10, reserve=4) == {"a": 6}
    assert picker.allocate([R("a", 5, 9)], 3, reserve=5) == {}
    assert picker.allocate([], 10) == {}


def test_never_exceeds_budget_and_zero_priority_gets_nothing():
    out = picker.allocate([R("a", 3, 9), R("b", 3, 9), R("c", 0, 9)], 7)
    assert sum(out.values()) == 7 and "c" not in out


def test_hold_until():
    now = dt.datetime(2026, 10, 16, 20, 0, tzinfo=dt.timezone.utc)
    assert picker.held({"hold_until": "2026-10-16T21:00:00Z"}, now)
    assert not picker.held({"hold_until": "2026-10-16T19:00:00Z"}, now)
    assert not picker.held({}, now)
