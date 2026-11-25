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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import caps, journal
from .checks import post_check, post_pending
from .github import Api
from .ledger import Ledger
from .planner import MAIN_CTX_SEP, TRUSTED_PREFIXES, Action
from .redact import WITHHELD, redact, strip_output_blocks


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
    # ci_checks(checkout, [{"context", "steps": [[cmd, dir], ...]}]) -> {context: (ok, markdown)}; for repos with a repo_ci.json spec
    ci_checks: Callable[[Path, list], dict[str, tuple[bool, str]]] | None = None


@dataclass
class IssueResult:
    ok: bool
    summary: str = ""
    problems: str = ""
    pr_number: int | None = None
    turns: int | None = None
    model: str | None = None
    model_id: str | None = None  # resolved model id from the CLI's JSON
    cost_usd: float | None = None  # the CLI's total_cost_usd for the run (None = not reported)


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


def run_check_pr_spec(api: Api, deps: Deps, action: Action, *, checks: list[dict], public: bool = True) -> dict[str, bool]:
    """A private repo with a repo_ci.json spec: no guard kit (these repos have no repo.yaml), one check run per required context.
    Same fail-closed rule as run_check_pr: every context ends COMPLETED, even when checkout or the lane crashes."""
    repo, sha = action.repo, action.ref
    names = [c["context"] for c in checks]
    for n in names:
        post_pending(api, repo, sha, n)
    show = (lambda t: strip_output_blocks(t)) if public else (lambda t: t)
    try:
        co = deps.checkout(repo, sha)
    except Exception as e:  # noqa: BLE001
        for n in names:
            post_check(api, repo, sha, n, False, f"checkout failed: {type(e).__name__}")
        return {n: False for n in names}
    try:
        if deps.ci_checks is None:
            raise RuntimeError("no CI lane for repo specs")
        results = deps.ci_checks(co, checks)
    except Exception as e:  # noqa: BLE001
        results = {n: (False, f"ci lane crashed: {type(e).__name__}") for n in names}
    out = {}
    for n in names:
        ok, text = results.get(n, (False, "not run: the lane returned no result for this check"))
        post_check(api, repo, sha, n, bool(ok), show(text))
        out[n] = bool(ok)
    return out


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


SUMMARY_TAIL = 600  # how much of the model's own summary a private repo's note keeps
MODEL_WITHHELD = "(model output withheld on public repositories)"


def failure_reason(r: "IssueResult | None", *, public: bool, crash: BaseException | None = None) -> str:
    """Why a run ended without a PR, safe to store and to post. r.problems is apx's own text (guard violations, a runner error); it is
    redacted, and on a public repo anything after a code fence is dropped (as for check summaries). The model's summary is model output:
    a private repo keeps its redacted tail, a public repo never stores or posts it."""
    if crash is not None:
        return f"apx crashed during the run ({type(crash).__name__})"
    if r is None:
        return "no result"
    why = redact(r.problems or "no reason given")
    if public:
        why = strip_output_blocks(why)
        why = why.replace(WITHHELD, "(raw output withheld on public repositories)")
    parts = [" ".join(why.split())]
    if r.summary:
        parts.append(MODEL_WITHHELD if public else "Model summary (tail): " + " ".join(redact(r.summary[-SUMMARY_TAIL:]).split()))
    return redact(" ".join(parts))


def _detail_turns(detail: str) -> int:
    """The run's turn cap from the action detail, as daemon.parse_detail reads it (default 25)."""
    for p in detail.split():
        if p.startswith("turns="):
            try:
                return int(p.split("=", 1)[1])
            except ValueError:
                break
    return 25


def _post_failure(api: Api, repo: str, number: int, what: str, reason: str, *, turns, max_turns: int, cost_usd, run_id: int) -> None:
    """One comment on the issue (or PR) when a run ends without a PR or fix. Best effort, like the label: never breaks the pass."""
    cost = f"${cost_usd:.2f} (API-equivalent)" if isinstance(cost_usd, (int, float)) else "not reported"
    body = (
        f"apx {what} failed: {reason.rstrip('.')}. Turns: {turns if turns is not None else 'unknown'} of {max_turns}. "
        f"Estimated cost: {cost}. Run id: {run_id}. Remove `needs-human` to retry."
    )
    try:
        api("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})
    except Exception:  # noqa: BLE001
        pass


def _report(deps: Deps, repo, issue, model, turns, conclusion, started) -> None:
    if deps.report is not None:
        try:
            deps.report(repo, issue, model, turns, conclusion, started)
        except Exception:  # noqa: BLE001 - reporting must never mask the run's own outcome
            pass


def run_agent(api: Api, ledger: Ledger, deps: Deps, action: Action, *, hard: bool = False, public: bool = True) -> str:
    """Returns 'success' or 'failure'. The ledger row is closed on every path, including a crash (which re-raises)."""
    return run_agent_outcome(api, ledger, deps, action, hard=hard, public=public)[0]


def run_agent_outcome(
    api: Api, ledger: Ledger, deps: Deps, action: Action, *, hard: bool = False, public: bool = True
) -> tuple[str, str]:
    """(conclusion, reason); reason is '' on success. A run that ends without a PR is labelled needs-human, its reason goes into the
    ledger note and one issue comment. Repos not known to be private are public: the model's output is withheld from both."""
    repo, issue = action.repo, int(action.ref)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = ledger.start(repo, issue, hard=hard, budget_usd=caps.detail_budget(action.detail))
    conclusion, model, turns, model_id, cost_usd, reason = "failure", None, None, None, None, ""
    try:
        r = deps.work_on_issue(repo, issue, run_id)
        model, turns, model_id, cost_usd = r.model, r.turns, r.model_id, r.cost_usd
        if r.ok and r.pr_number:
            conclusion = "success"
        else:
            reason = failure_reason(r, public=public)
    except Exception as e:
        reason = failure_reason(None, public=public, crash=e)
        raise
    finally:
        ledger.finish(run_id, conclusion, model=model, turns=turns, model_id=model_id, cost_usd=cost_usd, note=reason or None)
        if conclusion != "success":
            _flag_needs_human(api, repo, issue)  # blocked or rejected: the label the gate already understands
            _post_failure(api, repo, issue, "agent run", reason, turns=turns, max_turns=_detail_turns(action.detail),
                          cost_usd=cost_usd, run_id=run_id)
        _report(deps, repo, issue, model, turns, conclusion, started)
    return conclusion, reason


def run_fix(api: Api, ledger: Ledger, deps: Deps, action: Action, *, public: bool = True) -> str:
    """One red-CI retry of an open agent PR. Returns 'success', 'failure' or 'skipped: why'. The PR must still be open, still be at the
    head the planner saw, and still be an agent/* branch; otherwise nothing runs. The ledger row is closed on every path. A failure is
    recorded like run_agent's: ledger note, needs-human on the PR and one comment there."""
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
    run_id = ledger.start(repo, issue, kind="fix", ref=sha, budget_usd=caps.detail_budget(action.detail))
    conclusion, model, turns, model_id, cost_usd, reason = "failure", None, None, None, None, ""
    try:
        r = deps.fix_ci(repo, issue, run_id, int(pr_number), sha, action.detail)
        model, turns, model_id, cost_usd = r.model, r.turns, r.model_id, r.cost_usd
        if r.ok:
            conclusion = "success"
        else:
            reason = failure_reason(r, public=public)
    except Exception as e:
        reason = failure_reason(None, public=public, crash=e)
        raise
    finally:
        ledger.finish(run_id, conclusion, model=model, turns=turns, model_id=model_id, cost_usd=cost_usd, note=reason or None)
        if conclusion != "success":
            # the PR is an issue too: the label stops further retries and tells the owner
            _flag_needs_human(api, repo, int(pr_number))
            _post_failure(api, repo, int(pr_number), "CI fix run", reason, turns=turns, max_turns=_detail_turns(action.detail),
                          cost_usd=cost_usd, run_id=run_id)
        _report(deps, repo, issue, model, turns, conclusion, started)
    return f"{conclusion}: {reason[:160]}" if reason else conclusion


# Order inside one pass (backlog O5): PR checks first, so a PR's first result never waits behind a slow main suite, an agent run or
# a merge; then default-branch checks; then every other action (merges, branch updates, journal fixes, agent runs, CI fixes) in the
# planner's own order. The sort is stable, so the planner's order is kept inside each phase.
PHASES = {"check-pr": 0, "check-main": 1}
LAST_PHASE = 2
CHECK_JOB_KINDS = frozenset({"check-pr", "check-main"})  # the only kinds that may run in parallel
DEFAULT_CHECK_PARALLEL = 2  # the daemon's default (APX_CHECK_PARALLEL); execute() itself defaults to 1, one job at a time
MAX_CHECK_PARALLEL = 4  # each job is a checkout plus a full test suite under the same apx cgroup (MemoryMax): keep it small


def order_actions(actions: list[Action]) -> list[Action]:
    return sorted(actions, key=lambda a: PHASES.get(a.kind, LAST_PHASE))


def valid_parallel(n: object) -> int:
    """The check-job cap: a whole number from 1 to MAX_CHECK_PARALLEL. Anything else is refused (ValueError), never clamped."""
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_CHECK_PARALLEL:
        raise ValueError(f"check parallelism must be a whole number from 1 to {MAX_CHECK_PARALLEL}, got {n!r}")
    return n


def run_check_jobs(jobs: list[tuple[str, Callable[[], list[str]]]], cap: int) -> list[list[str]]:
    """Run (repo, job) pairs with at most `cap` jobs at once and never two for the same repo: each repo's jobs form one lane that
    runs in order, and `cap` workers take lanes. Results come back in the jobs' original order. A job that raises costs only
    itself: its slot gets a crash line and the lane goes on."""
    cap = valid_parallel(cap)
    results: list[list[str]] = [[] for _ in jobs]
    lanes: dict[str, list[int]] = {}
    for i, (repo, _) in enumerate(jobs):
        lanes.setdefault(repo, []).append(i)

    def run_lane(idx: list[int]) -> None:
        for i in idx:
            repo, job = jobs[i]
            try:
                results[i] = job()
            except Exception as e:  # noqa: BLE001 - one bad job must not stop its lane or the others
                results[i] = [f"check job {repo} crashed: {type(e).__name__}"]

    if cap == 1 or len(lanes) == 1:
        for idx in lanes.values():
            run_lane(idx)
        return results
    with ThreadPoolExecutor(max_workers=min(cap, len(lanes)), thread_name_prefix="apx-check") as pool:
        for f in [pool.submit(run_lane, idx) for idx in lanes.values()]:
            f.result()  # run_lane catches everything; this only re-raises a bug in the scheduler itself
    return results


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
    gate: Callable[[str], str | None] | None = None,
    check_parallel: int = 1,
) -> list[str]:
    """contexts: {repo: {"guard": "guard / guard", "ci": "build"}}; head_refs: {(repo, sha): head branch name}.
    private_repos: repos known to be private. Everything else is treated as PUBLIC (fail closed), and a public repo's check
    summary gets step names and durations only, never the raw tail of a failing command.
    gate(kind) is asked before EACH live action and returns a reason to hold it (the work-hours freeze) or None. A gate that raises
    holds the action. Held actions touch nothing and open no ledger row; the planner offers them again on the next pass.
    Actions run in PHASES order. PR and main checks run first, up to `check_parallel` at once and at most one per repo; every
    other action runs after them, one at a time. The log keeps the phase order whatever order the checks finish in."""
    actions = order_actions(actions)
    if dry_run:
        return [f"DRY-RUN {a.kind} {a.repo} {a.ref} {a.detail}" for a in actions]
    cap = valid_parallel(check_parallel)
    checks = [a for a in actions if a.kind in CHECK_JOB_KINDS]
    rest = [a for a in actions if a.kind not in CHECK_JOB_KINDS]

    def one(a: Action) -> list[str]:
        return _execute_one(api, ledger, deps, a, contexts=contexts, head_refs=head_refs, private_repos=private_repos, gate=gate)

    log: list[str] = []
    for lines in run_check_jobs([(a.repo, (lambda a=a: one(a))) for a in checks], cap):
        log += lines
    for a in rest:
        log += one(a)
    return log


def _execute_one(
    api: Api,
    ledger: Ledger,
    deps: Deps,
    a: Action,
    *,
    contexts: dict[str, dict],
    head_refs: dict[tuple[str, str], str],
    private_repos: frozenset | None,
    gate: Callable[[str], str | None] | None,
) -> list[str]:
    """One live action; returns its log lines."""
    log: list[str] = []
    if gate is not None:
        try:
            held = gate(a.kind)
        except Exception as e:  # noqa: BLE001 - a gate that cannot answer holds the action
            held = f"gate failed ({type(e).__name__})"
        if held:
            log.append(f"held {a.kind} {a.repo} {a.ref[:12]}: {held}")
            return log
    if a.kind == "check-pr":
        ctx = contexts[a.repo]
        if "checks" in ctx:
            try:
                r = run_check_pr_spec(api, deps, a, checks=ctx["checks"], public=a.repo not in (private_repos or frozenset()))
                log.append(f"check-pr {a.repo} {a.ref[:7]} {r}")
            except Exception as e:  # noqa: BLE001 - the next pass retries this PR
                log.append(f"check-pr {a.repo} {a.ref[:7]} failed: {type(e).__name__}")
            return log
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
    elif a.kind == "check-main" and "checks" in contexts[a.repo]:
        # spec repo: the spec lane, narrowed to the one context this action names (no second lane)
        ctx_name = a.detail.partition(MAIN_CTX_SEP)[2]
        try:
            one = [c for c in contexts[a.repo]["checks"] if c["context"] == ctx_name]
            if not one:
                raise LookupError("context not in spec")
            r = run_check_pr_spec(api, deps, a, checks=one, public=a.repo not in (private_repos or frozenset()))
            log.append(f"check-main {a.repo} {a.ref[:7]} {ctx_name} {'green' if all(r.values()) else 'failed (main is red)'}")
        except Exception as e:  # noqa: BLE001 - the next pass retries this head
            log.append(f"check-main {a.repo} {a.ref[:7]} {ctx_name} crashed: {type(e).__name__}")
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
            public = a.repo not in (private_repos or frozenset())
            concl, why = run_agent_outcome(api, ledger, deps, a, public=public)
            log.append(f"run-agent {a.repo} #{a.ref} {concl}: {why[:200]}" if why else f"run-agent {a.repo} #{a.ref} {concl}")
        except Exception as e:  # noqa: BLE001 - one bad issue must not stop the loop
            log.append(f"run-agent {a.repo} #{a.ref} crashed: {type(e).__name__}")
    elif a.kind == "fix-ci":
        try:
            log.append(f"fix-ci {a.repo} {a.ref[:12]} {run_fix(api, ledger, deps, a, public=a.repo not in (private_repos or frozenset()))}")
        except Exception as e:  # noqa: BLE001 - one bad PR must not stop the loop
            log.append(f"fix-ci {a.repo} {a.ref[:12]} crashed: {type(e).__name__}: {' '.join(str(e).split())[:160]}")
    elif a.kind == "automerge":
        if deps.automerge is None:
            log.append(f"automerge {a.repo} {a.ref}: lane not enabled")
            return log
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
    elif a.kind == journal.KIND:
        try:
            log.append(f"{journal.KIND} {a.repo} {journal.resolve(api, a.repo, a.ref, TRUSTED_PREFIXES)}")
        except Exception as e:  # noqa: BLE001 - a PR that cannot be resolved must not stop the loop; the next pass looks again
            log.append(f"{journal.KIND} {a.repo} #{a.ref.split(':')[0]} failed: {type(e).__name__}")
    else:
        raise ValueError(f"unknown action {a.kind}")
    return log
