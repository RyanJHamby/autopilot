"""Post check runs so an external executor can satisfy the same required contexts the Actions jobs did.

automerge.py reads check-runs (not commit statuses), and PATs cannot create check runs, so this needs an App token.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .github import Api
from .redact import redact

MAX_TEXT = 60000  # the Checks API caps summary/text at 65535 chars
_version: str | None = None


def code_version() -> str:
    """Short commit of the apx code that is running, so a check run says which version produced it (a stale clone on the
    host is otherwise invisible from GitHub). Cached; 'unknown' if git or the checkout is unavailable."""
    global _version
    if _version is None:
        try:
            root = Path(__file__).resolve().parents[3]
            _version = (
                subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                ).stdout.strip()
                or "unknown"
            )
        except Exception:  # noqa: BLE001 - a footer must never break a check
            _version = "unknown"
    return _version


def _clip(s: str) -> str:
    body = redact(s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + "\n...[truncated]")
    return f"{body}\n\n_apx {code_version()}_"


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
