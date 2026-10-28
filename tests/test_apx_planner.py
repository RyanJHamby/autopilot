import base64
import datetime as dt

import pytest

from autopilot.apx import planner
from autopilot.apx.github import GitHubError
from autopilot.apx.ledger import Ledger

REPO = "RyanJHamby/stencil"
NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)
CFG = "mode: standard\ntier: A\n"


def pr(n, ref, sha, repo=REPO, user="RyanJHamby"):
    return {"number": n, "head": {"ref": ref, "sha": sha, "repo": {"full_name": repo}}, "user": {"login": user}}


class Fake:
    def __init__(self, **kw):
        self.vars = kw.get("vars", {"AUTOPILOT_ENABLED": "true"})
        self.open = kw.get("open", [])
        self.closed = kw.get("closed", [])
        self.issues = kw.get("issues", [])
        self.checks = kw.get("checks", {})
        self.cfg = kw.get("cfg", CFG)
        self.writes = []

    def __call__(self, method, path, body=None):
        if method != "GET":
            self.writes.append((method, path))
            raise AssertionError("planner must be read-only")
        if "/actions/variables/" in path:
            name = path.rsplit("/", 1)[1]
            if name not in self.vars:
                raise GitHubError(404, path, "nf")
            return {"value": self.vars[name]}
        if "/contents/.autopilot/repo.yaml" in path:
            return {"content": base64.b64encode(self.cfg.encode()).decode()}
        if "pulls?state=open" in path:
            return self.open
        if "pulls?state=closed" in path:
            return self.closed
        if "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            return {"check_runs": [{"name": n} for n in self.checks.get(sha, [])]}
        if "/issues?" in path:
            return self.issues
        raise AssertionError(path)


def issue(n, user="RyanJHamby", labels=("agent-ready",)):
    return {
        "number": n,
        "created_at": f"2026-10-2{n % 9}T00:00:00Z",
        "user": {"login": user},
        "labels": [{"name": x} for x in labels],
    }


def go(f, led=None, repos=None):
    return planner.plan(f, led or Ledger(), repos or {REPO: {"contexts": ["guard / guard", "build"]}}, now=NOW)[REPO]


def test_out_of_scope_repo_raises():
    with pytest.raises(ValueError):
        planner.plan(Fake(), Ledger(), {"RyanJHamby/resume": {}})


def test_fail_closed_when_not_enabled_or_paused():
    busy = dict(open=[pr(1, "agent/5-1", "s1")], issues=[issue(4)])  # work exists, so only the switch can stop it
    assert go(Fake(vars={}, **busy))["actions"] == []
    assert go(Fake(vars={"AUTOPILOT_ENABLED": "false"}, **busy))["actions"] == []
    r = go(Fake(vars={"AUTOPILOT_ENABLED": "true", "AUTOPILOT_PAUSED": "true"}, **busy))
    assert r["actions"] == [] and r["note"] == "AUTOPILOT_PAUSED"
    assert go(Fake(**busy))["actions"] != []  # control: enabled and not paused does plan work


def test_check_pr_planned_only_for_missing_contexts_and_trusted_heads():
    f = Fake(
        open=[
            pr(1, "agent/5-1", "s1"),
            pr(2, "agent/6-1", "s2"),
            pr(3, "evil/x", "s3", repo="attacker/stencil"),
            pr(4, "feature/z", "s4", user="stranger"),
            pr(5, "feature/own", "s5"),
        ],
        checks={"s1": ["guard / guard", "build"], "s2": ["guard / guard"], "s5": []},
    )
    acts = [(a.ref, a.detail) for a in go(f)["actions"] if a.kind == "check-pr"]
    assert [r for r, _ in acts] == ["s2", "s5"]
    assert "build" in acts[0][1] and "guard / guard" in acts[1][1]


def test_agent_run_planned_for_owner_issues_only_and_skips_prs_and_open_branches():
    f = Fake(
        open=[pr(9, "agent/3-77", "s9")],
        issues=[issue(3), issue(4), issue(5, user="stranger"), {**issue(6), "pull_request": {}}],
        checks={"s9": ["guard / guard", "build"]},
    )
    runs = [a.ref for a in go(f)["actions"] if a.kind == "run-agent"]
    assert runs == ["4"]


def test_merged_with_refs_issue_not_rerun_unless_retry():
    closed = [{"head": {"ref": "agent/4-1"}, "merged_at": "2026-10-27T00:00:00Z"}]
    assert [a for a in go(Fake(issues=[issue(4)], closed=closed))["actions"] if a.kind == "run-agent"] == []
    runs = [
        a.ref
        for a in go(Fake(issues=[issue(4, labels=("agent-ready", "retry"))], closed=closed))["actions"]
        if a.kind == "run-agent"
    ]
    assert runs == ["4"]


def test_inflight_and_daily_cap_come_from_ledger():
    led = Ledger()
    led.start(REPO, 4, now=NOW - dt.timedelta(minutes=5))
    assert [a for a in go(Fake(issues=[issue(4)]), led)["actions"] if a.kind == "run-agent"] == []
    led2 = Ledger()
    for i in range(2):
        rid = led2.start(REPO, 90 + i, now=NOW - dt.timedelta(hours=2 + i))
        led2.finish(rid, "success", now=NOW - dt.timedelta(hours=2 + i))
    r = go(Fake(issues=[issue(4)]), led2)
    assert r["actions"] == [] and "daily run cap" in r["note"]


def test_api_error_fails_closed_and_never_writes():
    class Boom(Fake):
        def __call__(self, method, path, body=None):
            if "pulls?state=open" in path:
                raise GitHubError(500, path, "x")
            return super().__call__(method, path, body)

    f = Boom()
    r = go(f)
    assert r["actions"] == [] and "fail closed" in r["note"] and f.writes == []
