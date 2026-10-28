"""Report finished agent runs to the control-plane ledger (best effort; never blocks or fails a run).

The body is signed with HMAC-SHA256 under APX_WEBHOOK_SECRET (a different secret from GitHub's webhook secret), sent as the
`apx_run` event. The secret is read from a mode-600 file by the caller and only ever used to sign; it is not sent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
from typing import Callable

MODELS = {"haiku", "sonnet", "opus"}
OUTCOMES = {"success", "failure", "skipped", "cancelled"}


def build_body(repo: str, issue: int | None, model: str | None, turns: int | None, outcome: str, started_at: str) -> bytes:
    m = model if model in MODELS else "sonnet"  # unknown labels (e.g. full model ids) fall back to the default weight
    o = outcome if outcome in OUTCOMES else "failure"
    return json.dumps(
        {"repo": repo, "issue": issue, "model": m, "turns": turns, "outcome": o, "started_at": started_at}, separators=(",", ":")
    ).encode()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_reporter(url: str, secret: str, *, opener: Callable = urllib.request.urlopen) -> Callable[..., bool]:
    """Returns report(repo, issue, model, turns, outcome, started_at) -> bool (delivered). Swallows all errors."""
    if not url.startswith("https://"):
        raise ValueError("control-plane URL must be https")

    def report(repo: str, issue: int | None, model: str | None, turns: int | None, outcome: str, started_at: str) -> bool:
        body = build_body(repo, issue, model, turns, outcome, started_at)
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "x-github-event": "apx_run", "x-hub-signature-256": sign(secret, body)},
        )
        try:
            with opener(req, timeout=10) as r:
                return 200 <= r.status < 300
        except Exception:  # noqa: BLE001 - the ledger is observability, never a reason to fail or retry a run
            return False

    return report
