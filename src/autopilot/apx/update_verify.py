"""Should the host adopt this commit of autopilot's own code? Pure decision over GitHub API reads; it changes nothing.

Why strict: the host code IS the executor, so whoever can land code on main controls the App key and the Claude token. A commit is
adopted only when ALL of these hold (docs/apx-updater-design.md), and any read error means no:
 1. it is the head of the default branch and a fast-forward of what runs now (history rewrites are never adopted);
 2. it is the merge of a PR that the OWNER merged; or that apx's own merge lane merged AND nothing that changed since the running
    release is runtime code (only docs, specs, results, .github callers, markdown: see `non_runtime`). Code reaches the host only
    through the owner's merge; a lane merge of non-code (e.g. a kit-bump) must not stall every later update. Any other merger: no;
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
COMPARE_FILE_CAP = 300  # GitHub's compare API lists at most this many files; at or past it the list may be cut short
NON_RUNTIME_DIRS = ("docs/", "specs/", "results/", ".github/")  # none of these is imported or run by the host


def non_runtime(path: str) -> bool:
    """True only for files the host never imports or runs. Deliberately an allowlist: tests, deploy scripts, kit, apps, policy,
    pyproject and lockfiles all count as runtime, so a lane merge touching any of them needs the owner."""
    return path.startswith(NON_RUNTIME_DIRS) or path.endswith(".md")


def _runtime_change(cmp: dict) -> str | None:
    """None when the compare lists every changed file and none is runtime; otherwise a short reason."""
    files = cmp.get("files")
    if not isinstance(files, list):
        return "file list unavailable"
    if len(files) >= COMPARE_FILE_CAP:
        return f"{len(files)}+ files changed (list may be cut short)"
    for f in files:
        name = f.get("filename") or ""
        if not non_runtime(name) or not non_runtime(f.get("previous_filename") or name):
            return f"changes runtime code ({name})"
    return None


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
        merger = ((pr.get("merged_by") or {}).get("login") or "").lower()  # type: ignore[union-attr]
        if merger == f"{app_slug}[bot]".lower():
            why = _runtime_change(cmp)  # type: ignore[arg-type]
            if why:
                return False, f"merged by the apx lane but {why}; needs an owner merge"
        elif merger != owner.lower():
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
