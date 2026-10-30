"""Should the host adopt this commit of autopilot's own code? Pure decision over GitHub API reads; it changes nothing.

Why strict: the host code IS the executor, so whoever can land code on main controls the App key and the Claude token. A commit is
adopted only when ALL of these hold (docs/apx-updater-design.md), and any read error means no:
 1. it is the head of the default branch and a fast-forward of what runs now (history rewrites are never adopted);
 2. it is the merge of a PR that the OWNER merged (not apx's merge lane, not a bot, not anyone else);
 3. GitHub reports the commit Verified;
 4. the required checks are green on the PR head, posted by the apx App (an Actions result of the same name cannot stand in);
 5. the PR carries no `hold` label and the local HOLD switch is off;
 6. a settling delay has passed since the merge, so a merge the owner regrets can be stopped before the host runs it.
Rule 7 of the design (the new tree builds and its tests pass as apx-ci) is the caller's job: it needs a checkout.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from .github import Api, GitHubError
from .planner import APX_APP_SLUG

SETTLE = dt.timedelta(minutes=15)
HOLD_LABEL = "hold"


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def verify(
    api: Api,
    repo: str,
    default_branch: str,
    running: str,
    candidate: str,
    *,
    owner: str,
    required_checks: list[str],
    hold_switch: bool = False,
    now: Optional[dt.datetime] = None,
    settle: dt.timedelta = SETTLE,
    app_slug: str = APX_APP_SLUG,
) -> tuple[bool, str]:
    """(ok, reason). The reason is one short line for the status file; on ok it is 'ok'."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    try:
        if hold_switch:
            return False, "HOLD switch is on"
        if candidate == running:
            return False, "already running this commit"
        head = api("GET", f"/repos/{repo}/git/ref/heads/{default_branch}")["object"]["sha"]  # type: ignore[index]
        if head != candidate:
            return False, f"not the head of {default_branch}"
        cmp = api("GET", f"/repos/{repo}/compare/{running}...{candidate}")
        if cmp.get("status") != "ahead" or cmp.get("behind_by", 1) != 0:  # type: ignore[union-attr]
            return False, f"not a fast-forward of the running commit ({cmp.get('status')})"  # type: ignore[union-attr]
        commit = api("GET", f"/repos/{repo}/commits/{candidate}")
        if not ((commit.get("commit") or {}).get("verification") or {}).get("verified"):  # type: ignore[union-attr]
            return False, "commit is not Verified"
        prs = [p for p in api("GET", f"/repos/{repo}/commits/{candidate}/pulls") if p.get("merge_commit_sha") == candidate]  # type: ignore[union-attr]
        if len(prs) != 1:
            return False, "not the merge commit of exactly one PR"
        pr = api("GET", f"/repos/{repo}/pulls/{prs[0]['number']}")
        if not pr.get("merged_at"):  # type: ignore[union-attr]
            return False, "PR is not merged"
        if ((pr.get("merged_by") or {}).get("login") or "").lower() != owner.lower():  # type: ignore[union-attr]
            return False, "merged by someone other than the owner"
        if any(lb.get("name") == HOLD_LABEL for lb in pr.get("labels") or []):  # type: ignore[union-attr]
            return False, "PR is labelled hold"
        if now < _parse(pr["merged_at"]) + settle:  # type: ignore[index]
            return False, "settling: merged less than the delay ago"
        runs = api("GET", f"/repos/{repo}/commits/{pr['head']['sha']}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
        for name in required_checks:
            ours = [c for c in runs if c.get("name") == name and (c.get("app") or {}).get("slug") == app_slug]
            if not ours or any(c.get("conclusion") != "success" for c in ours):
                return False, f"required check {name!r} is not green from the apx App"
    except (GitHubError, OSError, KeyError, TypeError, AttributeError, ValueError) as e:
        return False, f"could not verify ({type(e).__name__})"
    return True, "ok"
