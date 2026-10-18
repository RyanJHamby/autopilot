import datetime as dt
import json

import charter
import gate
import guard

CH = {
    "goals": [{"id": "G1", "text": "faster"}],
    "non_goals": ["rewrite in rust", "billing"],
    "proposals_per_week": 2,
    "backlog_max": 4,
    "auto_ready": True,
}
CH = {**charter.DEFAULTS, **CH}
BODY = "Make the board render under 50 ms on large inputs. Tests: a timing check."


def test_new_npm_dependency_flagged_but_bump_is_not():
    assert charter.added_dependencies("package.json", ['    "left-pad": "^1.3.0",'], []) == {"left-pad"}
    assert charter.added_dependencies("package.json", ['    "zod": "^3.2.0"'], ['    "zod": "^3.1.0"']) == set()
    assert charter.added_dependencies("package.json", ['  "version": "1.2.3",', '  "test": "vitest run"'], []) == set()


def test_python_dependencies():
    assert charter.added_dependencies("requirements.txt", ["httpx>=0.27"], ["requests"]) == {"httpx"}
    assert charter.added_dependencies("pyproject.toml", ['    "rich>=13",'], []) == {"rich"}
    assert charter.added_dependencies("pyproject.toml", ['description = "Some words here"'], []) == set()
    assert charter.added_dependencies("src/app.py", ["httpx>=0.27"], []) == set()


def test_guard_blocks_new_dependency_only_when_charter_forbids():
    ch = guard.FileChange(path="package.json", added=['    "left-pad": "^1.3.0",'])
    assert any(v.check == "new-dependency" for v in guard.analyze([ch], agent=True, allow_new_dependencies=False))
    assert not guard.analyze([ch], agent=True)  # default: allowed
    assert not guard.analyze([ch], agent=False, allow_new_dependencies=False)  # owner commits are not policed here


def test_lines_budget_blocks_dispatch():
    cfg = {"mode": "standard", "tier": "A", "charter": {"weekly_lines_budget": 100}}
    assert gate.decide(cfg, [], 0, role="implementer", lines_7d=99).allow
    d = gate.decide(cfg, [], 0, role="implementer", lines_7d=100)
    assert not d.allow and "weekly line budget" in d.reason
    assert gate.decide({"mode": "standard", "tier": "A"}, [], 0, role="implementer", lines_7d=10**6).allow  # no budget set


def test_lines_used_counts_only_recent_agent_merges():
    now = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
    pulls = [
        {"number": 1, "merged_at": "2026-10-17T00:00:00Z", "head": {"ref": "agent/5-1"}},
        {"number": 2, "merged_at": "2026-10-01T00:00:00Z", "head": {"ref": "agent/6-1"}},
        {"number": 3, "merged_at": "2026-10-17T00:00:00Z", "head": {"ref": "dependabot/x"}},
        {"number": 4, "merged_at": None, "head": {"ref": "agent/7-1"}},
    ]
    assert charter.lines_used(pulls, now, lambda n: {"additions": 10, "deletions": 5}) == 15


def _p(**kw):
    return {"title": "Speed up the board render", "goal": "G1", "body": BODY, **kw}


def test_proposals_valid_and_capped():
    raw = json.dumps([_p(), _p(title="Cache layout results"), _p(title="Third thing here")])
    ok, why = charter.validate_proposals(raw, CH, [], backlog=0)
    assert [p["title"] for p in ok] == ["Speed up the board render", "Cache layout results"]
    assert "over the weekly cap" in why


def test_proposals_respect_backlog_room():
    ok, why = charter.validate_proposals(json.dumps([_p()]), CH, [], backlog=4)
    assert ok == [] and "no room" in why[0]
    ok, _ = charter.validate_proposals(json.dumps([_p(), _p(title="Another valid one")]), CH, [], backlog=3)
    assert len(ok) == 1


def test_proposals_rejections():
    cases = [
        _p(goal="G9"),
        _p(title="short"),
        _p(body="too short"),
        _p(body=BODY + " see https://example.com"),
        _p(body=BODY + " Also rewrite in Rust."),
        _p(title="Billing page speedup now"),
    ]
    ok, why = charter.validate_proposals(json.dumps(cases), {**CH, "proposals_per_week": 9, "backlog_max": 9}, [], 0)
    assert ok == [] and len(why) == len(cases)


def test_proposals_dedupe_against_open_and_closed_titles():
    ok, why = charter.validate_proposals(json.dumps([_p()]), CH, ["speed up the BOARD render!"], 0)
    assert ok == [] and "duplicate" in why[0]


def test_proposals_garbage_json():
    assert charter.validate_proposals("not json", CH, [], 0)[0] == []
    assert charter.validate_proposals('{"a": 1}', CH, [], 0)[0] == []
