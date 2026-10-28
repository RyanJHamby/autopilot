"""apx planner: read-only. Looks at GitHub and the local ledger and returns what the executor WOULD do.

Nothing here writes to GitHub or starts a model. The executor (next piece) runs the returned actions through the lanes.
Fail closed: an unreadable repo variable, config or API error means "no actions" for that repo, never "assume yes".
"""

from __future__ import annotations

import base64
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
import gate  # noqa: E402

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


def plan_checks(api: Api, repo: str, owner: str, contexts: list[str]) -> list[Action]:
    out = []
    for pr in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
        if not _trusted_pr(pr, repo, owner):
            continue
        sha = pr["head"]["sha"]
        have = {c["name"] for c in api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]}  # type: ignore[index]
        missing = [c for c in contexts if c not in have]
        if missing:
            out.append(Action("check-pr", repo, sha, f"PR #{pr['number']} missing {', '.join(missing)}"))
    return out


def plan_agent_runs(api: Api, repo: str, owner: str, ledger: Ledger, default_branch: str, now=None) -> tuple[list[Action], str]:
    cfg = load_cfg(api, repo, default_branch)
    open_prs = api("GET", f"/repos/{repo}/pulls?state=open&per_page=100")
    branches = [p["head"]["ref"] for p in open_prs]  # type: ignore[union-attr]
    n_agent = sum(1 for b in branches if b.startswith("agent/"))
    d = gate.decide(cfg, ledger.runs(repo), n_agent, role="implementer", now=now)
    if not d.allow:
        return [], d.reason
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
        if "pull_request" not in i and (i.get("user") or {}).get("login") == owner
    ]
    issues = [i for i in issues if not gate.skip_merged(i["number"], {ln["name"] for ln in i["labels"]}, merged)]
    picked = gate.pick_issues(issues, branches + [f"agent/{n}-inflight" for n in inflight], max(d.remaining, 0))
    return [Action("run-agent", repo, str(n), f"model={d.model} effort={d.effort} turns={d.max_turns}") for n in picked], "ok"


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
            actions = plan_checks(api, repo, owner, meta.get("contexts", ["guard / guard"]))
            runs, note = plan_agent_runs(api, repo, owner, ledger, meta.get("default_branch", "main"), now)
            result[repo] = {"actions": actions + runs, "note": note}
        except (GitHubError, KeyError, ValueError, yaml.YAMLError) as e:
            result[repo] = {"actions": [], "note": f"planner error (fail closed): {type(e).__name__}"}
    return result
