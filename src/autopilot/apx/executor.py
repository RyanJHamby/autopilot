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

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .checks import post_check, post_pending
from .github import Api
from .ledger import Ledger
from .planner import Action
from .redact import strip_output_blocks


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
    # automerge(repo, pr_number, head_sha) -> (rc, output); only present once a repo is cut over from Actions
    automerge: Callable[[str, int, str], tuple[int, str]] | None = None
    # report(repo, issue, model, turns, outcome, started_at) -> bool; best effort, failures are ignored
    report: Callable[..., bool] | None = None
    # fix_ci(repo, issue, run_id, pr_number, head_sha, detail) -> IssueResult; adds a commit to the failing PR's branch
    fix_ci: Callable[[str, int, int, int, str, str], "IssueResult"] | None = None


@dataclass
class IssueResult:
    ok: bool
    summary: str = ""
    problems: str = ""
    pr_number: int | None = None
    turns: int | None = None
    model: str | None = None


def run_check_pr(
    api: Api, deps: Deps, action: Action, *, guard_ctx: str, ci_ctx: str, head_ref: str, public: bool = True
) -> dict[str, bool]:
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
    post_check(api, repo, sha, guard_ctx, g_ok, strip_output_blocks(g_out) if public else g_out)
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
    post_check(api, repo, sha, ci_ctx, c_ok, strip_output_blocks(c_out) if public else c_out)
    res[ci_ctx] = c_ok
    return res


def run_check_main(api: Api, deps: Deps, action: Action, *, ci_ctx: str, head_ref: str, public: bool = True) -> bool | None:
    """Run the repo's CI on the default branch head and post it under the CI check name. True/False is the CI result; None means the
    lane could not run at all (nothing is posted, so a lane problem never makes main look red)."""
    repo, sha = action.repo, action.ref
    post_pending(api, repo, sha, ci_ctx)
    try:
        co = deps.checkout(repo, sha)
        deps.guard(co, head_ref)  # the sandbox runs guard and CI as one job; main against itself has an empty diff
        c_ok, c_out = deps.ci(co)
    except Exception:  # noqa: BLE001
        post_check(api, repo, sha, ci_ctx, False, "main check could not run (lane crashed); nothing to fix in the repo")
        return None
    if not c_ok and c_out.startswith("not run:"):
        post_check(api, repo, sha, ci_ctx, False, "main check could not run: " + c_out[:200])
        return None
    post_check(api, repo, sha, ci_ctx, c_ok, strip_output_blocks(c_out) if public else c_out)
    return c_ok


def _flag_needs_human(api: Api, repo: str, issue: int) -> None:
    try:
        api("POST", f"/repos/{repo}/issues/{issue}/labels", {"labels": ["needs-human"]})
    except Exception:  # noqa: BLE001 - best effort; the ledger row still records the failure
        pass


def run_agent(api: Api, ledger: Ledger, deps: Deps, action: Action, *, hard: bool = False) -> str:
    """Returns 'success' or 'failure'. The ledger row is closed on every path, including a crash (which re-raises)."""
    repo, issue = action.repo, int(action.ref)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
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
        if deps.report is not None:
            try:
                deps.report(repo, issue, model, turns, conclusion, started)
            except Exception:  # noqa: BLE001 - reporting must never mask the run's own outcome
                pass
    return conclusion


def run_fix(api: Api, ledger: Ledger, deps: Deps, action: Action) -> str:
    """One red-CI retry of an open agent PR. Returns 'success', 'failure' or 'skipped: why'. The PR must still be open, still be at the
    head the planner saw, and still be an agent/* branch; otherwise nothing runs. The ledger row is closed on every path."""
    repo = action.repo
    pr_number, sha = action.ref.split(":", 1)
    pr = api("GET", f"/repos/{repo}/pulls/{int(pr_number)}")
    ref = (pr.get("head") or {}).get("ref", "")  # type: ignore[union-attr]
    m = re.match(r"agent/(\d+)-", ref)
    if pr.get("state") != "open" or (pr.get("head") or {}).get("sha") != sha or not m:  # type: ignore[union-attr]
        return "skipped: PR changed since it was planned"
    if deps.fix_ci is None:
        return "skipped: fixes are not enabled"
    issue = int(m.group(1))
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = ledger.start(repo, issue, kind="fix", ref=sha)
    conclusion, model, turns = "failure", None, None
    try:
        r = deps.fix_ci(repo, issue, run_id, int(pr_number), sha, action.detail)
        model, turns = r.model, r.turns
        if r.ok:
            conclusion = "success"
        else:
            # the PR is an issue too: the label stops further retries and tells the owner
            _flag_needs_human(api, repo, int(pr_number))
    except Exception:
        _flag_needs_human(api, repo, int(pr_number))
        raise
    finally:
        ledger.finish(run_id, conclusion, model=model, turns=turns)
        if deps.report is not None:
            try:
                deps.report(repo, issue, model, turns, conclusion, started)
            except Exception:  # noqa: BLE001 - reporting must never mask the run's own outcome
                pass
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
    private_repos: frozenset | None = None,
) -> list[str]:
    """contexts: {repo: {"guard": "guard / guard", "ci": "build"}}; head_refs: {(repo, sha): head branch name}.
    private_repos: repos known to be private. Everything else is treated as PUBLIC (fail closed), and a public repo's check
    summary gets step names and durations only, never the raw tail of a failing command."""
    log = []
    for a in actions:
        if dry_run:
            log.append(f"DRY-RUN {a.kind} {a.repo} {a.ref} {a.detail}")
            continue
        if a.kind == "check-pr":
            ctx = contexts[a.repo]
            try:
                r = run_check_pr(
                    api,
                    deps,
                    a,
                    guard_ctx=ctx["guard"],
                    ci_ctx=ctx["ci"],
                    head_ref=head_refs[(a.repo, a.ref)],
                    public=a.repo not in (private_repos or frozenset()),
                )
                log.append(f"check-pr {a.repo} {a.ref[:7]} {r}")
            except Exception as e:  # noqa: BLE001 - e.g. a network error posting a check; the next pass retries this PR
                log.append(f"check-pr {a.repo} {a.ref[:7]} failed: {type(e).__name__}")
        elif a.kind == "check-main":
            try:
                r = run_check_main(
                    api,
                    deps,
                    a,
                    ci_ctx=contexts[a.repo]["ci"],
                    head_ref=a.detail.split()[0],
                    public=a.repo not in (private_repos or frozenset()),
                )
                log.append(
                    f"check-main {a.repo} {a.ref[:7]} {'green' if r else 'failed (main is red)' if r is False else 'could not run'}"
                )
            except Exception as e:  # noqa: BLE001
                log.append(f"check-main {a.repo} {a.ref[:7]} crashed: {type(e).__name__}")
        elif a.kind == "run-agent":
            try:
                log.append(f"run-agent {a.repo} #{a.ref} {run_agent(api, ledger, deps, a)}")
            except Exception as e:  # noqa: BLE001 - one bad issue must not stop the loop
                log.append(f"run-agent {a.repo} #{a.ref} crashed: {type(e).__name__}")
        elif a.kind == "fix-ci":
            try:
                log.append(f"fix-ci {a.repo} {a.ref[:12]} {run_fix(api, ledger, deps, a)}")
            except Exception as e:  # noqa: BLE001 - one bad PR must not stop the loop
                log.append(f"fix-ci {a.repo} {a.ref[:12]} crashed: {type(e).__name__}")
        elif a.kind == "automerge":
            if deps.automerge is None:
                log.append(f"automerge {a.repo} {a.ref}: lane not enabled")
                continue
            num, sha = a.ref.split(":", 1)
            try:
                rc, out = deps.automerge(a.repo, int(num), sha)
                log.append(f"automerge {a.repo} #{num} rc={rc} {out.splitlines()[-1] if out else ''}")
            except Exception as e:  # noqa: BLE001
                log.append(f"automerge {a.repo} #{num} failed: {type(e).__name__}")
        elif a.kind == "update-branch":
            try:
                api("PUT", f"/repos/{a.repo}/pulls/{int(a.ref)}/update-branch", {})
                log.append(f"update-branch {a.repo} #{a.ref} ok")
            except Exception as e:  # noqa: BLE001 - a PR that cannot be updated must not stop the loop
                log.append(f"update-branch {a.repo} #{a.ref} failed: {type(e).__name__}")
        else:
            raise ValueError(f"unknown action {a.kind}")
    return log
