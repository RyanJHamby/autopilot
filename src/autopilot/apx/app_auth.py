"""GitHub App authentication for apx, stdlib + the `openssl` binary (no extra Python dependency).

The private key is read from a file path the caller supplies and is only ever handed to `openssl`; it is never read into
Python strings, logged, or copied. Installation tokens are short-lived (1h) and cached in memory only.
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .github import Api, make_api
from .redact import register

REFRESH_MARGIN = 300  # seconds before expiry at which a cached token is replaced


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_jwt(app_id: str, key_path: Path, *, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}".encode()
    p = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key_path)], input=signing_input, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(
            "openssl could not sign the JWT (check the key path and format)"
        )  # never echo stderr: may name the key
    return f"{head}.{body}.{_b64(p.stdout)}"


@dataclass
class Token:
    value: str
    expires_at: float  # epoch seconds


class TokenCache:
    def __init__(self, app_id: str, key_path: Path, installations: dict[str, int], *, clock=time.time, api_factory=make_api):
        self.app_id, self.key_path, self.installations = app_id, key_path, installations
        self.clock, self.api_factory = clock, api_factory
        self._tokens: dict[str, Token] = {}

    def token_for(self, repo: str) -> str:
        t = self._tokens.get(repo)
        if t and t.expires_at - self.clock() > REFRESH_MARGIN:
            return t.value
        if repo not in self.installations:
            raise KeyError(f"no installation id configured for {repo}")
        jwt_api: Api = self.api_factory(make_jwt(self.app_id, self.key_path, now=int(self.clock())))
        r = jwt_api("POST", f"/app/installations/{self.installations[repo]}/access_tokens", {})
        exp = _parse_iso(r["expires_at"])  # type: ignore[index]
        self._tokens[repo] = Token(r["token"], exp)  # type: ignore[index]
        register(r["token"])  # type: ignore[index]  # scrubbed from anything apx later publishes
        return r["token"]  # type: ignore[index]

    def api_for(self, repo: str) -> Api:
        return self.api_factory(self.token_for(repo))


def _parse_iso(s: str) -> float:
    import datetime as dt

    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
