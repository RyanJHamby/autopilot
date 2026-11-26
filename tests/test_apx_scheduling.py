"""Backlog O5: inside one pass, checks come before merges, at most N check jobs run at once and never two for one repo, and a
failing job does not stop the others."""

import threading
import time
from pathlib import Path

import pytest

from autopilot.apx import daemon
from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

A, B, C = "RyanJHamby/autopilot", "RyanJHamby/stencil", "RyanJHamby/drillpad-workspace"
CTX = {r: {"guard": "guard / guard", "ci": "build"} for r in (A, B, C)}


def sha(n: int) -> str:
    return f"{n:040x}"


class Api:
    def __init__(self):
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, method, path, body=None):
        with self._lock:
            self.calls.append((method, path, body))
        return {}


class Tracker:
    """Fake lanes that record start/end of every check job and the peak concurrency, overall and per repo."""

    def __init__(self, *, hold=0.05, crash_repo=None):
        self.hold, self.crash_repo = hold, crash_repo
        self.lock = threading.Lock()
        self.running: dict[str, int] = {}
        self.peak = 0
        self.peak_per_repo = 0
        self.events: list[tuple[str, str]] = []

    def deps(self, merged: list) -> ex.Deps:
        def checkout(repo, s):
            return Path(f"/co/{repo}/{s}")

        def guard(co, ref):
            repo = "/".join(co.parts[2:4])
            with self.lock:
                self.running[repo] = self.running.get(repo, 0) + 1
                self.peak = max(self.peak, sum(self.running.values()))
                self.peak_per_repo = max(self.peak_per_repo, self.running[repo])
                self.events.append(("start", repo))
            try:
                time.sleep(self.hold)
                if repo == self.crash_repo:
                    raise RuntimeError("lane blew up")
                return True, "clean"
            finally:
                with self.lock:
                    self.running[repo] -= 1
                    self.events.append(("end", repo))

        def ci(co):
            return True, "- PASS"

        def work(repo, issue, run_id):
            raise AssertionError("no agent runs in these tests")

        def automerge(repo, pr, s):
            with self.lock:
                self.events.append(("merge", repo))
            merged.append((repo, pr))
            return 0, "merged"

        return ex.Deps(checkout, guard, ci, work, automerge=automerge)


def check(repo: str, n: int) -> Action:
    return Action("check-pr", repo, sha(n), f"PR #{n}")


def heads(actions):
    return {(a.repo, a.ref): f"agent/{i}-x" for i, a in enumerate(actions)}


def run(actions, tracker, cap, merged=None):
    merged = [] if merged is None else merged
    api = Api()
    log = ex.execute(
        api,
        Ledger(),
        tracker.deps(merged),
        actions,
        contexts=CTX,
        head_refs=heads([a for a in actions if a.kind == "check-pr"]),
        dry_run=False,
        check_parallel=cap,
    )
    return log, api


# --- ordering --------------------------------------------------------------------------------------------------------------


def test_checks_run_before_merges_in_one_pass():
    t = Tracker(hold=0)
    acts = [Action("automerge", A, f"7:{sha(70)}", "PR #7"), check(B, 1), check(A, 2)]
    log, _ = run(acts, t, cap=2)
    kinds = [e[0] for e in t.events]
    assert kinds.index("merge") > max(i for i, k in enumerate(kinds) if k == "end")
    assert [line.split()[0] for line in log] == ["check-pr", "check-pr", "automerge"]


def test_pr_checks_before_main_checks_before_everything_else_and_planner_order_kept():
    acts = [
        Action("update-branch", A, "4", ""),
        Action("check-main", A, sha(9), "main"),
        Action("automerge", B, f"3:{sha(30)}", ""),
        check(B, 1),
        Action("run-agent", A, "12", ""),
        check(A, 2),
    ]
    got = [(a.kind, a.ref) for a in ex.order_actions(acts)]
    assert got == [
        ("check-pr", sha(1)),
        ("check-pr", sha(2)),
        ("check-main", sha(9)),
        ("update-branch", "4"),
        ("automerge", f"3:{sha(30)}"),
        ("run-agent", "12"),
    ]


def test_dry_run_lists_actions_in_the_same_order():
    acts = [Action("automerge", A, f"7:{sha(70)}", ""), check(A, 1)]
    out = ex.execute(Api(), Ledger(), None, acts, contexts={}, head_refs={}, dry_run=True)  # type: ignore[arg-type]
    assert [line.split()[1] for line in out] == ["check-pr", "automerge"]


# --- bounded parallelism ---------------------------------------------------------------------------------------------------


def test_at_most_cap_check_jobs_at_once_and_they_do_overlap():
    t = Tracker(hold=0.1)
    acts = [check(A, 1), check(B, 2), check(C, 3)]
    run(acts, t, cap=2)
    assert t.peak == 2  # overlapped, and never more than the cap with three repos waiting


def test_never_two_jobs_for_the_same_repo():
    t = Tracker(hold=0.05)
    acts = [check(A, 1), check(A, 2), check(A, 3), check(B, 4), check(B, 5)]
    log, _ = run(acts, t, cap=4)
    assert t.peak_per_repo == 1
    assert t.peak <= 2  # only two repos, so at most two lanes
    assert len([line for line in log if line.startswith("check-pr")]) == 5


def test_cap_one_is_strictly_sequential():
    t = Tracker(hold=0.02)
    run([check(A, 1), check(B, 2), check(C, 3)], t, cap=1)
    assert t.peak == 1
    assert [e[0] for e in t.events] == ["start", "end"] * 3


def test_log_keeps_planned_order_whatever_order_jobs_finish_in():
    order = []

    def slow_first(repo):
        def job():
            time.sleep(0.15 if repo == A else 0)
            order.append(repo)
            return [f"done {repo}"]

        return job

    out = ex.run_check_jobs([(A, slow_first(A)), (B, slow_first(B))], cap=2)
    assert order == [B, A]  # B really finished first
    assert out == [[f"done {A}"], [f"done {B}"]]


# --- failure isolation -----------------------------------------------------------------------------------------------------


def test_a_failing_job_does_not_stop_the_others():
    t = Tracker(hold=0.02, crash_repo=B)
    acts = [check(A, 1), check(B, 2), check(B, 3), check(C, 4)]
    log, api = run(acts, t, cap=2)
    assert len([line for line in log if line.startswith("check-pr")]) == 4
    # the crashing lane still completes both of ITS checks as failures (fail closed), and the next job in that lane still ran
    completed = [c[2] for c in api.calls if c[1] == f"/repos/{B}/check-runs" and c[2].get("status") == "completed"]
    assert len([c for c in completed if c["conclusion"] == "failure"]) == 4  # guard + ci for sha 2 and sha 3
    assert ("start", A) in t.events and ("start", C) in t.events


def test_a_job_that_raises_out_of_the_executor_costs_only_its_slot():
    def boom():
        raise RuntimeError("scheduler-level crash")

    out = ex.run_check_jobs([(A, boom), (A, lambda: ["second ok"]), (B, lambda: ["other ok"])], cap=2)
    assert out[0] == [f"check job {A} crashed: RuntimeError"]
    assert out[1:] == [["second ok"], ["other ok"]]


def test_gate_still_holds_each_check_job():
    t = Tracker(hold=0)
    api = Api()
    acts = [check(A, 1), check(B, 2)]
    log = ex.execute(
        api, Ledger(), t.deps([]), acts, contexts=CTX, head_refs=heads(acts), dry_run=False,
        gate=lambda kind: "freeze", check_parallel=2,
    )
    assert all(line.startswith("held check-pr") for line in log) and api.calls == [] and t.events == []


# --- the setting -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, 5, -1, True, 1.5, "2"])
def test_cap_must_be_a_small_whole_number(bad):
    with pytest.raises(ValueError):
        ex.valid_parallel(bad)


def test_daemon_setting_defaults_to_two_and_refuses_bad_values():
    assert daemon._parallel("") == 2 == ex.DEFAULT_CHECK_PARALLEL
    assert daemon._parallel(" 3 ") == 3
    for bad in ("0", "9", "two", "1.5"):
        with pytest.raises(ValueError):
            daemon._parallel(bad)


def test_no_check_jobs_runs_nothing_and_does_not_crash():
    # Regression: a pass with no check jobs built a thread pool of 0 workers and crashed every idle pass.
    from autopilot.apx.executor import run_check_jobs

    assert run_check_jobs([], 2) == []
    assert run_check_jobs([], 1) == []
