"""Post check runs so an external executor can satisfy the same required contexts the Actions jobs did.

automerge.py reads check-runs (not commit statuses), and PATs cannot create check runs, so this needs an App token.
"""

from __future__ import annotations

from .github import Api

MAX_TEXT = 60000  # the Checks API caps summary/text at 65535 chars


def _clip(s: str) -> str:
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + "\n...[truncated]"


def post_check(api: Api, repo: str, sha: str, name: str, ok: bool, summary: str, *, details_url: str | None = None):
    """One completed check run. `name` must equal the ruleset context exactly (e.g. `guard / guard`)."""
    body = {
        "name": name,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success" if ok else "failure",
        "output": {"title": name, "summary": _clip(summary or name)},
    }
    if details_url:
        body["details_url"] = details_url
    return api("POST", f"/repos/{repo}/check-runs", body)


def post_pending(api: Api, repo: str, sha: str, name: str):
    """Mark a check as running so automerge sees an unfinished check instead of 'no checks reported'."""
    return api(
        "POST",
        f"/repos/{repo}/check-runs",
        {"name": name, "head_sha": sha, "status": "in_progress", "output": {"title": name, "summary": "running"}},
    )
