import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit" / "runtime"))
from demote import demoted_classes, effective_classes  # noqa: E402

NOW = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)


def m(cls, days_ago, **kw):
    return {"class": cls, "merged_at": (NOW - dt.timedelta(days=days_ago)).isoformat(), "sha": "abcdef123", **kw}


def test_clean_history_demotes_nothing():
    assert demoted_classes([m("docs-only", 1), m("docs-only", 3)], now=NOW) == {}


def test_revert_demotes_only_that_class():
    d = demoted_classes([m("docs-only", 2, reverted=True), m("lockfile-patch", 2)], now=NOW)
    assert list(d) == ["docs-only"]
    assert effective_classes(["docs-only", "lockfile-patch"], d) == ["lockfile-patch"]


def test_red_main_demotes():
    assert "tests-add-only" in demoted_classes([m("tests-add-only", 1, main_red=True)], now=NOW)


def test_old_incidents_age_out():
    assert demoted_classes([m("docs-only", 45, reverted=True)], now=NOW) == {}


def test_owner_policy_change_clears_earlier_incidents_only():
    changed = (NOW - dt.timedelta(days=1)).isoformat()
    assert demoted_classes([m("docs-only", 3, reverted=True)], now=NOW, policy_changed_at=changed) == {}
    assert demoted_classes([m("docs-only", 0.5, reverted=True)], now=NOW, policy_changed_at=changed) != {}
