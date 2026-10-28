from pathlib import Path

import pytest

from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

REPO = "RyanJHamby/stencil"
CTX = {REPO: {"guard": "guard / guard", "ci": "build"}}


class Api:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {}

    def checks(self):
        return [(c[2]["name"], c[2].get("status"), c[2].get("conclusion")) for c in self.calls if c[1].endswith("/check-runs")]

    def labels(self):
        return [c for c in self.calls if c[1].endswith("/labels")]


def deps(**kw):
    calls = []

    def checkout(repo, sha):
        calls.append("checkout")
        if kw.get("checkout_err"):
            raise OSError("disk")
        return Path("/x")

    def guard(co, ref):
        calls.append("guard")
        if kw.get("guard_err"):
            raise RuntimeError("boom")
        return kw.get("guard", (True, "clean"))

    def ci(co):
        calls.append("ci")
        if kw.get("ci_err"):
            raise RuntimeError("boom")
        return kw.get("ci", (True, "- PASS"))

    def work(repo, issue, run_id):
        calls.append("work")
        if kw.get("work_err"):
            raise RuntimeError("model crashed")
        return kw.get("work", ex.IssueResult(True, pr_number=5, turns=7, model="sonnet"))

    d = ex.Deps(checkout, guard, ci, work)
    d.calls = calls  # type: ignore[attr-defined]
    return d


def pr_action():
    return Action("check-pr", REPO, "abc1234", "PR #1")


def run_pr(api, d):
    return ex.execute(api, Ledger(), d, [pr_action()], contexts=CTX, head_refs={(REPO, "abc1234"): "agent/5-1"}, dry_run=False)


def test_dry_run_is_the_default_and_touches_nothing():
    api, d = Api(), deps()
    acts = [pr_action(), Action("run-agent", REPO, "4", "")]
    log = ex.execute(api, Ledger(), d, acts, contexts=CTX, head_refs={})
    assert api.calls == [] and d.calls == [] and all(line.startswith("DRY-RUN") for line in log)


def test_green_pr_completes_both_checks_pending_first():
    api, d = Api(), deps()
    run_pr(api, d)
    assert api.checks() == [
        ("guard / guard", "in_progress", None),
        ("build", "in_progress", None),
        ("guard / guard", "completed", "success"),
        ("build", "completed", "success"),
    ]


def test_guard_failure_blocks_ci_and_still_completes_ci_context():
    api, d = Api(), deps(guard=(False, "[secret]"))
    run_pr(api, d)
    assert "ci" not in d.calls  # the PR's code never ran
    assert api.checks()[-2:] == [("guard / guard", "completed", "failure"), ("build", "completed", "failure")]


@pytest.mark.parametrize("kw", [{"checkout_err": 1}, {"guard_err": 1}, {"ci_err": 1}])
def test_any_lane_crash_fails_closed_with_no_pending_left(kw):
    api, d = Api(), deps(**kw)
    run_pr(api, d)
    done = {n: c for n, s, c in api.checks() if s == "completed"}
    assert done == {"guard / guard": done["guard / guard"], "build": done["build"]}
    assert "failure" in done.values() and "success" not in (done.get("build") if kw.get("ci_err") else "x")


def test_agent_success_closes_ledger_and_does_not_flag():
    api, d, led = Api(), deps(), Ledger()
    ex.execute(api, led, d, [Action("run-agent", REPO, "4", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert api.labels() == [] and led.runs(REPO)[0]["conclusion"] == "success" and led.inflight_issues(REPO) == set()


def test_agent_rejected_patch_flags_needs_human_and_records_failure():
    api, d, led = Api(), deps(work=ex.IssueResult(False, problems="[protected-path]")), Ledger()
    ex.execute(api, led, d, [Action("run-agent", REPO, "4", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert api.labels()[0][2] == {"labels": ["needs-human"]} and led.runs(REPO)[0]["conclusion"] == "failure"


def test_agent_crash_is_contained_flagged_and_ledger_closed():
    api, d, led = Api(), deps(work_err=1), Ledger()
    log = ex.execute(
        api,
        led,
        d,
        [Action("run-agent", REPO, "4", ""), Action("run-agent", REPO, "5", "")],
        contexts=CTX,
        head_refs={},
        dry_run=False,
    )
    assert len(log) == 2 and all("crashed" in line for line in log)  # one bad issue does not stop the loop
    assert len(api.labels()) == 2 and led.inflight_issues(REPO) == set()
    assert [r["conclusion"] for r in led.runs(REPO)] == ["failure", "failure"]


def test_unknown_action_kind_raises():
    with pytest.raises(ValueError):
        ex.execute(Api(), Ledger(), deps(), [Action("merge", REPO, "1")], contexts=CTX, head_refs={}, dry_run=False)


def test_update_branch_action_puts_and_survives_failure():
    api = Api()
    log = ex.execute(
        api, Ledger(), deps(), [Action("update-branch", REPO, "7", "behind")], contexts=CTX, head_refs={}, dry_run=False
    )
    assert api.calls == [("PUT", f"/repos/{REPO}/pulls/7/update-branch", {})] and log == [f"update-branch {REPO} #7 ok"]

    class Failing(Api):
        def __call__(self, method, path, body=None):
            raise RuntimeError("422")

    log = ex.execute(
        Failing(), Ledger(), deps(), [Action("update-branch", REPO, "7", "")], contexts=CTX, head_refs={}, dry_run=False
    )
    assert "failed" in log[0]


def test_automerge_action_runs_lane_and_reports_and_is_inert_when_disabled():
    api = Api()
    d = deps()
    d.automerge = lambda repo, n, sha: (0, "MERGE docs-only")
    log = ex.execute(api, Ledger(), d, [Action("automerge", REPO, "9:abc", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert log == [f"automerge {REPO} #9 rc=0 MERGE docs-only"]
    log = ex.execute(api, Ledger(), deps(), [Action("automerge", REPO, "9:abc", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert "not enabled" in log[0]

    def boom(repo, n, sha):
        raise RuntimeError("x")

    d2 = deps()
    d2.automerge = boom
    assert (
        "failed"
        in ex.execute(api, Ledger(), d2, [Action("automerge", REPO, "9:abc", "")], contexts=CTX, head_refs={}, dry_run=False)[0]
    )


def test_finished_runs_are_reported_and_reporter_failure_cannot_change_the_outcome():
    sent = []
    d = deps()
    d.report = lambda *a: sent.append(a) or True
    led = Ledger()
    ex.execute(Api(), led, d, [Action("run-agent", REPO, "4", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert len(sent) == 1 and sent[0][:5] == (REPO, 4, "sonnet", 7, "success")

    def boom(*a):
        raise RuntimeError("down")

    d2 = deps()
    d2.report = boom
    led2 = Ledger()
    log = ex.execute(Api(), led2, d2, [Action("run-agent", REPO, "4", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert log == [f"run-agent {REPO} #4 success"] and led2.runs(REPO)[0]["conclusion"] == "success"


def test_crashed_runs_are_still_reported_as_failures():
    sent = []
    d = deps(work_err=1)
    d.report = lambda *a: sent.append(a) or True
    ex.execute(Api(), Ledger(), d, [Action("run-agent", REPO, "4", "")], contexts=CTX, head_refs={}, dry_run=False)
    assert sent and sent[0][4] == "failure"


def test_a_network_error_while_posting_one_pr_check_does_not_lose_the_rest_of_the_pass():
    import urllib.error

    class Flaky(Api):
        def __call__(self, method, path, body=None):
            if "/check-runs" in path and "abc1234" in str(body):
                raise urllib.error.URLError("dns")
            return super().__call__(method, path, body)

    api = Flaky()
    other = Action("check-pr", REPO, "def5678", "PR #2")
    log = ex.execute(
        api,
        Ledger(),
        deps(),
        [pr_action(), other],
        contexts=CTX,
        head_refs={(REPO, "abc1234"): "agent/5-1", (REPO, "def5678"): "agent/6-1"},
        dry_run=False,
    )
    assert "failed: URLError" in log[0] and "def5678"[:7] in log[1] and "failed" not in log[1]  # the second PR still got checked
