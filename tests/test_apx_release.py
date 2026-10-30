import datetime as dt
import os

import pytest

from autopilot.apx import release as rel

T0 = dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.timezone.utc)


def stage(root, sha, age=0):
    d = root / "releases" / sha
    d.mkdir(parents=True)
    (d / "marker").write_text(sha)
    os.utime(d, (T0.timestamp() - age, T0.timestamp() - age))
    return d


def test_swap_points_current_and_remembers_previous(tmp_path):
    stage(tmp_path, "aaaaaaa")
    stage(tmp_path, "bbbbbbb")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    assert rel.current(tmp_path) == "aaaaaaa" and not (tmp_path / "previous").exists()
    rel.swap(tmp_path, "bbbbbbb", now=T0)
    assert rel.current(tmp_path) == "bbbbbbb"
    assert (tmp_path / "previous").resolve().name == "aaaaaaa"
    assert (tmp_path / "current" / "marker").read_text() == "bbbbbbb"


def test_swap_to_the_running_release_changes_nothing(tmp_path):
    stage(tmp_path, "aaaaaaa")
    stage(tmp_path, "bbbbbbb")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    rel.swap(tmp_path, "bbbbbbb", now=T0)
    rel.swap(tmp_path, "bbbbbbb", now=T0)
    assert (tmp_path / "previous").resolve().name == "aaaaaaa"  # not overwritten with itself


def test_swap_refuses_unstaged_and_non_hex_shas(tmp_path):
    stage(tmp_path, "aaaaaaa")
    with pytest.raises(FileNotFoundError):
        rel.swap(tmp_path, "ccccccc")
    for bad in ("../etc", "aaaaaaa/../..", "main", "", "ABCDEF1", "a" * 41):
        with pytest.raises(ValueError):
            rel.release_dir(tmp_path, bad)
    assert rel.current(tmp_path) is None


def test_current_is_never_missing_during_a_swap(tmp_path):
    stage(tmp_path, "aaaaaaa")
    stage(tmp_path, "bbbbbbb")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    rel.swap(tmp_path, "bbbbbbb", now=T0)
    assert not list(tmp_path.glob(".*.tmp"))  # the temp link was renamed over, not left behind


def test_rollback_restores_previous_and_raises_hold(tmp_path):
    stage(tmp_path, "aaaaaaa")
    stage(tmp_path, "bbbbbbb")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    rel.swap(tmp_path, "bbbbbbb", now=T0)
    assert rel.rollback(tmp_path) == "aaaaaaa"
    assert rel.current(tmp_path) == "aaaaaaa" and (tmp_path / "HOLD").exists()


def test_rollback_without_a_previous_refuses(tmp_path):
    stage(tmp_path, "aaaaaaa")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    with pytest.raises(FileNotFoundError):
        rel.rollback(tmp_path)
    assert not (tmp_path / "HOLD").exists() and rel.current(tmp_path) == "aaaaaaa"


def swapped(tmp_path):
    stage(tmp_path, "aaaaaaa")
    stage(tmp_path, "bbbbbbb")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    rel.swap(tmp_path, "bbbbbbb", now=T0)


def st(minutes, ok=True, version="bbbbbbb"):
    return {"ts": (T0 + dt.timedelta(minutes=minutes)).isoformat(), "ok": ok, "version": version}


def test_canary_has_nothing_to_judge_without_a_swap(tmp_path):
    assert rel.canary(tmp_path, st(1), T0) == "none"


def test_canary_pending_then_healthy_then_bad(tmp_path):
    swapped(tmp_path)
    at = lambda m: T0 + dt.timedelta(minutes=m)  # noqa: E731
    assert rel.canary(tmp_path, st(-5), at(2)) == "pending"  # only an older status so far
    assert rel.canary(tmp_path, st(3), at(3)) == "pending"  # ok but too soon to trust
    assert rel.canary(tmp_path, st(6), at(6)) == "healthy"
    assert rel.canary(tmp_path, st(2, ok=False), at(3)) == "bad"  # a failed pass after the swap
    assert rel.canary(tmp_path, st(-5), at(16)) == "bad"  # no pass finished at all
    assert rel.canary(tmp_path, st(7, version="aaaaaaa"), at(7)) == "pending"  # ok, but still running the OLD code


def test_canary_missing_status_is_pending_then_bad(tmp_path):
    swapped(tmp_path)
    assert rel.canary(tmp_path, {}, T0 + dt.timedelta(minutes=5)) == "pending"
    assert rel.canary(tmp_path, {}, T0 + dt.timedelta(minutes=16)) == "bad"


def test_prune_keeps_newest_three_plus_current_and_previous(tmp_path):
    for i, sha in enumerate(["1111111", "2222222", "3333333", "4444444", "5555555", "6666666"]):
        stage(tmp_path, sha, age=100 - i * 10)  # 6666666 is newest
    rel.swap(tmp_path, "1111111", now=T0)
    rel.swap(tmp_path, "2222222", now=T0)  # current=2222222, previous=1111111, both old
    gone = rel.prune(tmp_path)
    left = {d.name for d in (tmp_path / "releases").iterdir()}
    assert gone == ["3333333"] and left == {"1111111", "2222222", "4444444", "5555555", "6666666"}


def test_current_still_exists_at_the_instant_of_the_rename(tmp_path, monkeypatch):
    stage(tmp_path, "aaaaaaa")
    stage(tmp_path, "bbbbbbb")
    rel.swap(tmp_path, "aaaaaaa", now=T0)
    seen = []
    real = os.replace

    def spy(src, dst):
        seen.append((tmp_path / "current").is_symlink() if os.path.basename(dst) == "current" else None)
        real(src, dst)

    monkeypatch.setattr(rel.os, "replace", spy)
    rel.swap(tmp_path, "bbbbbbb", now=T0)
    assert True in seen and False not in seen  # never a moment without a `current`


def test_canary_stops_judging_after_the_watch_window(tmp_path):
    swapped(tmp_path)
    late = T0 + dt.timedelta(hours=3)
    assert rel.canary(tmp_path, st(170, ok=False), late) == "none"  # a failure hours later is not the release's fault
    assert rel.canary(tmp_path, {}, late) == "none"
    assert rel.canary(tmp_path, st(2, ok=False), T0 + dt.timedelta(minutes=29)) == "bad"  # still inside the window
