"""apx executor: carries out the planner's actions through the lanes. Dry-run is the default and touches nothing.

Every side effect goes through an injected `Deps` callable, so this module is pure orchestration and fully testable
with fakes. Rules it enforces:
- a PR check always ends in a COMPLETED check run for every required context, even if a lane crashes or is skipped
  (fail closed: an exception posts a failure, never leaves a check pending or absent)
- a failed guard stops CI from running the PR's code, and CI's context is reported as failed-skipped
- the model never holds GitHub credentials; only the trusted committer pushes, and only `agent/*` branches
- the ledger row is always closed, whatever happens
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .checks import post_check, post_pending
from .github import Api
from .ledger import Ledger
from .planner import Action


@dataclass
class Deps:
    # checkout(repo, sha) -> Path of a clean checkout at sha with origin/<base> available
    checkout: Callable[[str, str], Path]
    # guard(checkout, head_ref) -> (ok, output)
    guard: Callable[[Path, str], tuple[bool, str]]
    # ci(checkout) -> (ok, markdown)
    ci: Callable[[Path], tuple[bool, str]]
    # work_on_issue(repo, issue, run_id) -> Outcome-like with .ok, .summary, .violations, .branch, .commit_args or None
    work_on_issue: Callable[[str, int, int], "IssueResult"]


@dataclass
class IssueResult:
    ok: bool
    summary: str = ""
    problems: str = ""
    pr_number: int | None = None
    turns: int | None = None
    model: str | None = None


def run_check_pr(api: Api, deps: Deps, action: Action, *, guard_ctx: str, ci_ctx: str, head_ref: str) -> dict[str, bool]:
    repo, sha = action.repo, action.ref
    post_pending(api, repo, sha, guard_ctx)
    post_pending(api, repo, sha, ci_ctx)
    res = {}
    try:
        co = deps.checkout(repo, sha)
    except Exception as e:  # noqa: BLE001 - any failure must still complete both checks
        msg = f"checkout failed: {type(e).__name__}"
        post_check(api, repo, sha, guard_ctx, False, msg)
        post_check(api, repo, sha, ci_ctx, False, msg)
        return {guard_ctx: False, ci_ctx: False}
    try:
        g_ok, g_out = deps.guard(co, head_ref)
    except Exception as e:  # noqa: BLE001
        g_ok, g_out = False, f"guard lane crashed: {type(e).__name__}"
    post_check(api, repo, sha, guard_ctx, g_ok, g_out)
    res[guard_ctx] = g_ok
    if not g_ok:
        # do not run the PR's code when the guard rejected it
        post_check(api, repo, sha, ci_ctx, False, "not run: guard failed")
        res[ci_ctx] = False
        return res
    try:
        c_ok, c_out = deps.ci(co)
    except Exception as e:  # noqa: BLE001
        c_ok, c_out = False, f"ci lane crashed: {type(e).__name__}"
    post_check(api, repo, sha, ci_ctx, c_ok, c_out)
    res[ci_ctx] = c_ok
    return res


def _flag_needs_human(api: Api, repo: str, issue: int) -> None:
    try:
        api("POST", f"/repos/{repo}/issues/{issue}/labels", {"labels": ["needs-human"]})
    except Exception:  # noqa: BLE001 - best effort; the ledger row still records the failure
        pass


def run_agent(api: Api, ledger: Ledger, deps: Deps, action: Action, *, hard: bool = False) -> str:
    """Returns 'success' or 'failure'. The ledger row is closed on every path, including a crash (which re-raises)."""
    repo, issue = action.repo, int(action.ref)
    run_id = ledger.start(repo, issue, hard=hard)
    conclusion, model, turns = "failure", None, None
    try:
        r = deps.work_on_issue(repo, issue, run_id)
        model, turns = r.model, r.turns
        if r.ok and r.pr_number:
            conclusion = "success"
        else:
            _flag_needs_human(api, repo, issue)  # blocked or rejected: the label the gate already understands
    except Exception:
        _flag_needs_human(api, repo, issue)
        raise
    finally:
        ledger.finish(run_id, conclusion, model=model, turns=turns)
    return conclusion


def execute(
    api: Api,
    ledger: Ledger,
    deps: Deps,
    actions: list[Action],
    *,
    contexts: dict[str, dict],
    head_refs: dict[tuple[str, str], str],
    dry_run: bool = True,
) -> list[str]:
    """contexts: {repo: {"guard": "guard / guard", "ci": "build"}}; head_refs: {(repo, sha): head branch name}."""
    log = []
    for a in actions:
        if dry_run:
            log.append(f"DRY-RUN {a.kind} {a.repo} {a.ref} {a.detail}")
            continue
        if a.kind == "check-pr":
            ctx = contexts[a.repo]
            r = run_check_pr(api, deps, a, guard_ctx=ctx["guard"], ci_ctx=ctx["ci"], head_ref=head_refs[(a.repo, a.ref)])
            log.append(f"check-pr {a.repo} {a.ref[:7]} {r}")
        elif a.kind == "run-agent":
            try:
                log.append(f"run-agent {a.repo} #{a.ref} {run_agent(api, ledger, deps, a)}")
            except Exception as e:  # noqa: BLE001 - one bad issue must not stop the loop
                log.append(f"run-agent {a.repo} #{a.ref} crashed: {type(e).__name__}")
        elif a.kind == "update-branch":
            try:
                api("PUT", f"/repos/{a.repo}/pulls/{int(a.ref)}/update-branch", {})
                log.append(f"update-branch {a.repo} #{a.ref} ok")
            except Exception as e:  # noqa: BLE001 - a PR that cannot be updated must not stop the loop
                log.append(f"update-branch {a.repo} #{a.ref} failed: {type(e).__name__}")
        else:
            raise ValueError(f"unknown action {a.kind}")
    return log
