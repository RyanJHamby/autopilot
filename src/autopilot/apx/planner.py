"""apx planner: read-only. Looks at GitHub and the local ledger and returns what the executor WOULD do.

Nothing here writes to GitHub or starts a model. The executor (next piece) runs the returned actions through the lanes.
Fail closed: an unreadable repo variable, config or API error means "no actions" for that repo, never "assume yes".
"""

from __future__ import annotations

import base64
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
import gate  # noqa: E402
import rebase as kit_rebase  # noqa: E402
import tier as kit_tier  # noqa: E402
from guard import _matches  # noqa: E402

from .github import Api, GitHubError  # noqa: E402
from .ledger import Ledger  # noqa: E402

# Hard scope. Anything else raises, whatever the config says.
ALLOWED_REPOS = {"RyanJHamby/autopilot", "RyanJHamby/drillpad-workspace", "RyanJHamby/stencil"}
TRUSTED_PREFIXES = ("agent/", "dependabot/", "autopilot/kit-")


@dataclass(frozen=True)
class Action:
    kind: str  # "check-pr" | "run-agent"
    repo: str
    ref: str  # PR head sha, or issue number as text
    detail: str = ""


def _var(api: Api, repo: str, name: str) -> str | None:
    try:
        return str(api("GET", f"/repos/{repo}/actions/variables/{name}").get("value"))  # type: ignore[union-attr]
    except GitHubError:
        return None


def enabled(api: Api, repo: str) -> tuple[bool, str]:
    if _var(api, repo, "AUTOPILOT_ENABLED") != "true":
        return False, "AUTOPILOT_ENABLED is not 'true'"
    if _var(api, repo, "AUTOPILOT_PAUSED") == "true":
        return False, "AUTOPILOT_PAUSED"
    return True, "ok"


def load_cfg(api: Api, repo: str, default_branch: str) -> dict:
    """repo.yaml from the DEFAULT branch only (what the owner merged), never from a PR."""
    f = api("GET", f"/repos/{repo}/contents/.autopilot/repo.yaml?ref={default_branch}")
    cfg = yaml.safe_load(base64.b64decode(f["content"])) or {}  # type: ignore[index]
    hold = _var(api, repo, "AUTOPILOT_HOLD_UNTIL")
    if hold:
        cfg["hold_until"] = hold
    return cfg


def _trusted_pr(pr: dict, repo: str, owner: str) -> bool:
    head = pr.get("head") or {}
    if (head.get("repo") or {}).get("full_name") != repo:
        return False  # fork PRs never run here
    return head.get("ref", "").startswith(TRUSTED_PREFIXES) or (pr.get("user") or {}).get("login") == owner


APX_APP_SLUG = "autopilot-apx"


def base_commit_time(api: Api, repo: str, default_branch: str) -> str | None:
    """When the default branch last moved (ISO). A failed apx check older than this may have failed on config that has
    since changed, so it is worth one more look."""
    try:
        return api("GET", f"/repos/{repo}/commits/{default_branch}")["commit"]["committer"]["date"]  # type: ignore[index]
    except (GitHubError, KeyError, TypeError):
        return None  # only disables the retry-after-base-moves optimisation; checks still run


def plan_checks(
    api: Api, repo: str, owner: str, contexts: list[str], app_slug: str = APX_APP_SLUG, base_time: str | None = None
) -> list[Action]:
    out = []
    for pr in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
        if not _trusted_pr(pr, repo, owner):
            continue
        sha = pr["head"]["sha"]
        runs = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
        # only our OWN check runs count: when apx posts a required name (e.g. `guard / guard`), a failed Actions run of
        # the same name must not make apx think the work is already done
        ours = [c for c in runs if (c.get("app") or {}).get("slug", app_slug) == app_slug]
        # a FAILED result from before the base branch last moved is stale (e.g. it failed because repo.yaml had no ci:
        # list yet): do not count it, so the check is retried once per base movement. Successes are never retried.
        stale = lambda c: bool(base_time) and c.get("conclusion") == "failure" and (c.get("completed_at") or "9") < base_time  # noqa: E731
        have = {c["name"] for c in ours if not stale(c)}
        missing = [c for c in contexts if c not in have]
        if missing:
            out.append(Action("check-pr", repo, sha, f"PR #{pr['number']} missing {', '.join(missing)}"))
    return out


def _owner_vouches(api: Api, repo: str, issue: dict, owner: str) -> bool:
    """An issue may steer the agent only if the OWNER wrote it, or the owner applied the `agent-ready` label most recently (so a
    bot-proposed audit issue becomes eligible the moment the owner approves it by labelling it). Text written by anyone else is
    never an instruction by itself. Any error means no."""
    if (issue.get("user") or {}).get("login") == owner:
        return True
    try:
        events = api("GET", f"/repos/{repo}/issues/{issue['number']}/events?per_page=100")
        labelled = [e for e in events if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == "agent-ready"]  # type: ignore[union-attr]
        return bool(labelled) and (labelled[-1].get("actor") or {}).get("login") == owner
    except (GitHubError, OSError, KeyError, TypeError, AttributeError):
        return False


def plan_agent_runs(
    api: Api,
    repo: str,
    owner: str,
    ledger: Ledger,
    default_branch: str,
    now=None,
    rebase_issues: list[int] | None = None,
    ci_contexts: list[str] | None = None,
) -> tuple[list[Action], str]:
    cfg = load_cfg(api, repo, default_branch)
    open_prs = api("GET", f"/repos/{repo}/pulls?state=open&per_page=100")
    branches = [p["head"]["ref"] for p in open_prs]  # type: ignore[union-attr]
    n_agent = sum(1 for b in branches if b.startswith("agent/"))
    d = gate.decide(cfg, ledger.runs(repo), n_agent, role="implementer", now=now)
    if not d.allow:
        return [], d.reason
    detail = f"model={d.model} effort={d.effort} turns={d.max_turns}"
    # finishing an open PR comes before starting new work, and shares the same daily cap
    fixes = plan_ci_fixes(api, repo, owner, ledger, ci_contexts or [], limit=max(d.remaining, 0))
    fixes = [Action(a.kind, a.repo, a.ref, f"{a.detail} {detail}") for a in fixes]
    remaining = max(d.remaining, 0) - len(fixes)
    closed = api("GET", f"/repos/{repo}/pulls?state=closed&per_page=100")
    merged = gate.merged_agent_issues(closed)  # type: ignore[arg-type]
    inflight = ledger.inflight_issues(repo)
    raw = api("GET", f"/repos/{repo}/issues?labels=agent-ready&state=open&per_page=100")
    issues = [
        {
            "number": i["number"],
            "createdAt": i["created_at"],
            "labels": [{"name": ln["name"]} for ln in i.get("labels", [])],
        }
        for i in raw  # type: ignore[union-attr]
        if "pull_request" not in i and _owner_vouches(api, repo, i, owner)
    ]
    issues = [i for i in issues if not gate.skip_merged(i["number"], {ln["name"] for ln in i["labels"]}, merged)]
    picked = gate.pick_issues(issues, branches + [f"agent/{n}-inflight" for n in inflight], max(remaining, 0))
    acts = fixes + [Action("run-agent", repo, str(n), detail) for n in picked]
    room = remaining - len(picked)  # re-runs for conflicted PRs share the same daily cap
    for n in rebase_issues or []:
        if room <= 0:
            break
        if str(n) not in {a.ref for a in acts}:
            acts.append(Action("run-agent", repo, str(n), detail + " rebase=1"))
            room -= 1
    return acts, "ok"


MAX_CI_FIXES = 2


def plan_ci_fixes(
    api: Api, repo: str, owner: str, ledger: Ledger, ci_contexts: list[str], *, limit: int, app_slug: str = APX_APP_SLUG
) -> list[Action]:
    """Open agent PRs whose CI check (posted by apx) FAILED on the current head get one more agent attempt, at most MAX_CI_FIXES
    per issue and one per head. Only the CI check counts: a failed guard means the patch broke a rule, and a retry would just
    try again to break it. `limit` is what the daily cap has left, so retries never exceed the cap."""
    out: list[Action] = []
    if limit <= 0:
        return out
    inflight = ledger.inflight_issues(repo)
    for pr in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
        if len(out) >= limit:
            break
        ref = pr["head"]["ref"]
        issue = kit_rebase.issue_of(ref)
        if issue is None or not _trusted_pr(pr, repo, owner) or pr.get("draft"):
            continue
        if "needs-human" in {ln["name"] for ln in pr.get("labels", [])}:
            continue
        sha = pr["head"]["sha"]
        if issue in inflight or ledger.fix_attempts(repo, issue) >= MAX_CI_FIXES or ledger.fixed_head(repo, issue, sha):
            continue
        runs = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
        ours = [c for c in runs if (c.get("app") or {}).get("slug") == app_slug]
        if not ours or any(c.get("status") != "completed" for c in ours):
            continue  # nothing posted yet, or still running: not a verdict
        if any(c["name"] in ci_contexts and c.get("conclusion") == "failure" for c in ours) and not any(
            c.get("conclusion") == "failure" for c in ours if c["name"] not in ci_contexts
        ):
            n = ledger.fix_attempts(repo, issue) + 1
            out.append(
                Action("fix-ci", repo, f"{pr['number']}:{sha}", f"PR #{pr['number']} issue #{issue} CI red; fix attempt {n}")
            )
    return out


def plan_merges(api: Api, repo: str, owner: str) -> list[Action]:
    """Candidates for the kit's automerge: trusted open PRs whose head has check runs and none still running.
    The kit decides whether each one actually merges; this only avoids calling it on PRs that are plainly not ready."""
    out = []
    for pr in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
        if not _trusted_pr(pr, repo, owner) or pr.get("draft"):
            continue
        sha = pr["head"]["sha"]
        runs = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
        if runs and all(r.get("status") == "completed" for r in runs):
            out.append(Action("automerge", repo, f"{pr['number']}:{sha}", f"PR #{pr['number']}"))
    return out


def plan_rebases(api: Api, repo: str, owner: str, ledger: Ledger, now: dt.datetime | None = None) -> list[Action]:
    """Behind agent PRs get GitHub's signed update-branch; conflicted ones are re-run from a fresh base (once a day).
    Reuses the kit's rebase.decide so Actions and apx can never disagree about what to do."""
    now = now or dt.datetime.now(dt.timezone.utc)
    day_ago = now - dt.timedelta(hours=24)
    out: list[Action] = []
    merged: set[int] | None = None
    inflight = ledger.inflight_issues(repo)
    for brief in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
        if not _trusted_pr(brief, repo, owner):
            continue
        ref = brief["head"]["ref"]
        issue = kit_rebase.issue_of(ref)
        if issue is None:
            continue
        pr = api("GET", f"/repos/{repo}/pulls/{brief['number']}")  # mergeable_state is computed on the single-PR endpoint
        state = pr.get("mergeable_state")  # type: ignore[union-attr]
        protected = False
        if state == "dirty":
            files = api("GET", f"/repos/{repo}/pulls/{brief['number']}/files?per_page=100")
            protected = any(_matches(f.get("filename", ""), kit_tier.PROTECTED_TIER2) for f in files)  # type: ignore[union-attr]
            if merged is None:
                merged = gate.merged_agent_issues(api("GET", f"/repos/{repo}/pulls?state=closed&per_page=100"))  # type: ignore[arg-type]
        labels = {ln["name"] for ln in pr.get("labels", [])}  # type: ignore[union-attr]
        act = kit_rebase.decide(
            {
                "head_ref": ref,
                "mergeable_state": state,
                "protected": protected,
                "labels": labels,
                "attempted_today": ledger.attempted_since(repo, issue, day_ago),
                "inflight": issue in inflight,
                "merged": gate.skip_merged(issue, labels, merged or set()),
            }
        )
        if act == kit_rebase.UPDATE:
            out.append(Action("update-branch", repo, str(brief["number"]), f"PR #{brief['number']} is behind"))
        elif act == kit_rebase.REDISPATCH:
            out.append(Action("rebase-agent", repo, str(issue), f"PR #{brief['number']} conflicts; re-run from a fresh base"))
    return out


def plan(api: Api, ledger: Ledger, repos: dict[str, dict], owner: str = "RyanJHamby", now=None) -> dict[str, dict]:
    """repos: {"o/r": {"default_branch": "main", "contexts": ["guard / guard", "build"]}} -> {"o/r": {"actions": [...], "note": str}}"""
    result: dict[str, dict] = {}
    for repo, meta in repos.items():
        if repo not in ALLOWED_REPOS:
            raise ValueError(f"{repo} is outside apx scope")
        try:
            ok, why = enabled(api, repo)
            if not ok:
                result[repo] = {"actions": [], "note": why}
                continue
            actions = plan_checks(
                api,
                repo,
                owner,
                meta.get("contexts", ["guard / guard"]),
                base_time=base_commit_time(api, repo, meta.get("default_branch", "main")),
            )
            if not meta.get("loop", meta.get("agents")):
                # shadow mode: Actions is still the system of record, so apx only reports checks. Updating branches or
                # running agents here would race the Actions jobs and open duplicate PRs.
                result[repo] = {"actions": actions, "note": "shadow: checks only"}
                continue
            rebases = plan_rebases(api, repo, owner, ledger, now)
            updates = [a for a in rebases if a.kind == "update-branch"]
            if meta.get("agents"):
                redo = [int(a.ref) for a in rebases if a.kind == "rebase-agent"]
                runs, note = plan_agent_runs(
                    api,
                    repo,
                    owner,
                    ledger,
                    meta.get("default_branch", "main"),
                    now,
                    rebase_issues=redo,
                    ci_contexts=meta.get("ci_contexts"),
                )
            else:
                runs, note = [], "agent runs blocked: no dedicated agent account (backlog S1b)"
            merges = plan_merges(api, repo, owner) if meta.get("merge") else []  # off in shadow mode: Actions still merges
            result[repo] = {"actions": actions + runs + updates + merges, "note": note}
        except (
            GitHubError,
            OSError,
            KeyError,
            ValueError,
            TypeError,
            AttributeError,
            yaml.YAMLError,
        ) as e:  # OSError: DNS/URLError
            result[repo] = {"actions": [], "note": f"planner error (fail closed): {type(e).__name__}"}
    return result
