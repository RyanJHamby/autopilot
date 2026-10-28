import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit" / "runtime"))
import rebase  # noqa: E402

BASE = {
    "head_ref": "agent/5-x",
    "mergeable_state": "dirty",
    "protected": False,
    "labels": set(),
    "attempted_today": False,
    "inflight": False,
    "merged": False,
}


def d(**kw):
    return rebase.decide({**BASE, **kw})


def test_behind_updates_branch():
    assert d(mergeable_state="behind") == "update-branch"
    assert d(mergeable_state="behind", protected=True) == "update-branch"


def test_clean_states_are_noop():
    for s in ("clean", "blocked", "unstable", "unknown", "has_hooks"):
        assert d(mergeable_state=s) == "noop"


def test_dirty_redispatches():
    assert d() == "redispatch"


def test_dirty_caps_and_guards():
    assert d(attempted_today=True) == "noop"
    assert d(inflight=True) == "noop"
    assert d(merged=True) == "noop"
    assert d(protected=True) == "noop"
    assert d(labels={"hold"}) == "noop"
    assert d(labels={"needs-human"}) == "noop"


def test_non_agent_pr_never_touched():
    for ref in ("feature/x", "dependabot/npm/y", "autopilot/kit-fix-1"):
        assert d(head_ref=ref, mergeable_state="behind") == "noop"
        assert d(head_ref=ref) == "noop"


NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)


def fake_gh(prs, runs=(), files=None):
    def gh(*a):
        if a[0] == "run":
            return list(runs)
        url = a[1]
        if url.startswith("repos/{owner}/{repo}/issues"):
            return [{"number": n, "pull_request": {}, "labels": []} for n in prs]
        if url.endswith("/files?per_page=100"):
            return files or []
        if "pulls?state=closed" in url:
            return []
        n = int(url.rsplit("/", 1)[1])
        return {"head": {"ref": prs[n][0]}, "mergeable_state": prs[n][1]}

    return gh


def test_run_dispatches_only_dirty_agent_pr_once_per_day(monkeypatch):
    calls = []
    monkeypatch.setattr(rebase.subprocess, "run", lambda *a, **k: calls.append(a[0]))
    prs = {5: ("agent/5-x", "dirty"), 6: ("feature/y", "dirty"), 7: ("agent/7-z", "clean")}
    sent = []
    out = rebase.run({}, gh=fake_gh(prs), dispatch=lambda cfg, i: sent.append(i), now=NOW)
    assert out == [(5, "redispatch"), (7, "noop")]
    assert sent == [5]
    assert ["gh", "pr", "edit", "5", "--add-label", "needs-rebase"] in calls

    recent = [{"createdAt": "2026-10-28T03:00:00Z", "status": "completed", "displayTitle": "agent #5"}]
    sent.clear()
    out = rebase.run({}, gh=fake_gh(prs, runs=recent), dispatch=lambda cfg, i: sent.append(i), now=NOW)
    assert out[0] == (5, "noop") and sent == []


def test_run_protected_dirty_pr_is_left_alone(monkeypatch):
    monkeypatch.setattr(rebase.subprocess, "run", lambda *a, **k: None)
    sent = []
    out = rebase.run(
        {},
        gh=fake_gh({5: ("agent/5-x", "dirty")}, files=[{"filename": ".github/workflows/a.yml"}]),
        dispatch=lambda cfg, i: sent.append(i),
        now=NOW,
    )
    assert out == [(5, "noop")] and sent == []
