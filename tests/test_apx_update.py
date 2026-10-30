import datetime as dt

from autopilot.apx import release as rel
from autopilot.apx.update import run_update

T0 = dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.timezone.utc)
RUN = "a" * 40
CAND = "b" * 40
CHECKS = ["apx / guard", "apx / build"]
MERGED = T0 - dt.timedelta(hours=1)


class Gh:
    """Enough of GitHub for verify() to say yes; `ok=False` makes the candidate a non-owner merge."""

    def __init__(self, ok=True):
        self.ok = ok

    def __call__(self, method, path, body=None):
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": CAND}}
        if "/compare/" in path:
            return {"status": "ahead", "behind_by": 0}
        if path.endswith(f"/commits/{CAND}"):
            return {"commit": {"verification": {"verified": True}}}
        if path.endswith("/pulls"):
            return [{"number": 7, "merge_commit_sha": CAND}]
        if path.endswith("/pulls/7"):
            return {
                "merged_at": MERGED.isoformat(),
                "merged_by": {"login": "owner" if self.ok else "someone"},
                "labels": [],
                "head": {"sha": "c" * 40},
            }
        if "/check-runs" in path:
            return {"check_runs": [{"name": n, "conclusion": "success", "app": {"slug": "autopilot-apx"}} for n in CHECKS]}
        raise AssertionError(path)


def install(root):
    (root / "releases" / RUN).mkdir(parents=True)
    rel.swap(root, RUN, now=T0 - dt.timedelta(days=1))


def go(root, gh=None, status=None, stage=None, tests=None):
    calls = []

    def default_stage(releases, sha):
        calls.append("stage")
        (releases / sha).mkdir()

    def default_tests(path):
        calls.append("tests")
        return True

    msg = run_update(
        root,
        gh or Gh(),
        repo="o/r",
        default_branch="main",
        owner="owner",
        required_checks=CHECKS,
        candidate=CAND,
        status=status or {},
        stage=stage or default_stage,
        run_tests=tests or default_tests,
        now=T0,
    )
    return msg, calls


def test_a_good_candidate_is_staged_tested_then_swapped(tmp_path):
    install(tmp_path)
    msg, calls = go(tmp_path)
    assert calls == ["stage", "tests"] and rel.current(tmp_path) == CAND and "swapped" in msg


def test_hold_stops_everything_even_a_pending_rollback(tmp_path):
    install(tmp_path)
    (tmp_path / "HOLD").write_text("x")
    msg, calls = go(tmp_path)
    assert calls == [] and rel.current(tmp_path) == RUN and "HOLD" in msg


def test_a_refused_candidate_is_not_even_fetched(tmp_path):
    install(tmp_path)
    msg, calls = go(tmp_path, gh=Gh(ok=False))
    assert calls == [] and rel.current(tmp_path) == RUN and "skipped" in msg and "failed" not in msg


def test_failing_tests_leave_current_alone_and_remove_the_staged_copy(tmp_path):
    install(tmp_path)
    msg, calls = go(tmp_path, tests=lambda p: False)
    assert rel.current(tmp_path) == RUN and not (tmp_path / "releases" / CAND).exists() and "failed" in msg


def test_a_crashing_stage_leaves_current_alone_and_no_half_release(tmp_path):
    install(tmp_path)

    def boom(releases, sha):
        (releases / sha).mkdir()
        raise RuntimeError("network")

    msg, _ = go(tmp_path, stage=boom)
    assert rel.current(tmp_path) == RUN and not (tmp_path / "releases" / CAND).exists() and "failed" in msg


def test_a_leftover_staged_copy_is_never_trusted(tmp_path):
    install(tmp_path)
    left = tmp_path / "releases" / CAND
    left.mkdir()
    (left / "planted").write_text("x")
    go(tmp_path)
    assert (
        rel.current(tmp_path) == CAND and not (tmp_path / "releases" / CAND / "planted").exists()
    )  # replaced, not reused, not tripped over


def test_a_bad_canary_rolls_back_and_raises_hold_before_considering_anything_new(tmp_path):
    install(tmp_path)
    (tmp_path / "releases" / CAND).mkdir()
    rel.swap(tmp_path, CAND, now=T0 - dt.timedelta(minutes=3))
    bad = {"ts": (T0 - dt.timedelta(minutes=1)).isoformat(), "ok": False, "version": CAND[:7]}
    msg, calls = go(tmp_path, status=bad)
    assert rel.current(tmp_path) == RUN and (tmp_path / "HOLD").exists() and "rolled back" in msg and calls == []


def test_a_pending_canary_changes_nothing(tmp_path):
    install(tmp_path)
    (tmp_path / "releases" / CAND).mkdir()
    rel.swap(tmp_path, CAND, now=T0 - dt.timedelta(minutes=2))
    msg, calls = go(tmp_path, status={})
    assert rel.current(tmp_path) == CAND and calls == [] and "watched" in msg


def test_no_running_release_means_manual_first_install(tmp_path):
    msg, calls = go(tmp_path)
    assert calls == [] and "manual" in msg


def test_a_successful_swap_prunes_old_releases(tmp_path):
    import os

    install(tmp_path)
    for i, sha in enumerate(["1" * 40, "2" * 40, "3" * 40, "4" * 40]):
        d = tmp_path / "releases" / sha
        d.mkdir()
        os.utime(d, (T0.timestamp() - 9000 - i, T0.timestamp() - 9000 - i))
    go(tmp_path)
    left = {d.name for d in (tmp_path / "releases").iterdir()}
    assert CAND in left and RUN in left and len(left) <= 4
