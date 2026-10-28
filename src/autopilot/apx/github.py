"""Minimal GitHub REST access for apx: one injectable callable, so everything above it is testable with a fake."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

# api(method, path, body=None) -> parsed JSON (dict/list) ; raises GitHubError on non-2xx
Api = Callable[..., object]


class GitHubError(RuntimeError):
    def __init__(self, status: int, path: str, detail: str):
        super().__init__(f"{status} {path}: {detail[:300]}")
        self.status = status


def make_api(token: str, *, base: str = "https://api.github.com") -> Api:
    """Real client. The token is passed in by the caller (never read from disk here) and never logged."""

    def api(method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise GitHubError(e.code, path, e.read().decode(errors="replace")) from None
        return json.loads(raw) if raw else {}

    return api
