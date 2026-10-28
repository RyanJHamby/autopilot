"""Clone/fetch helpers for apx. The App token goes in through git's environment config, never argv or the URL, so it is not
visible in `ps` and is not written into .git/config of the checkout."""

from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _env(token: str | None) -> dict:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
            }
        )
    return env


def _git(cwd: Path, token: str | None, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], env=_env(token), capture_output=True, text=True)
    if p.returncode != 0:
        # git's stderr can contain the remote URL; it never contains the token (header only), but keep it short anyway
        raise RuntimeError(f"git {args[0]} failed: {p.stderr.strip()[-200:]}")
    return p.stdout


def checkout_pr(repo: str, sha: str, base_branch: str, dest: Path, token: str | None, *, url: str | None = None) -> Path:
    """Fresh checkout of `sha` with `origin/<base_branch>` present, so guard can diff base...head."""
    if not SHA_RE.match(sha) or not REPO_RE.match(repo) or not re.match(r"^[A-Za-z0-9._/-]+$", base_branch):
        raise ValueError("bad repo, sha or base branch")
    dest.mkdir(parents=True, exist_ok=True)
    _git(dest, None, "init", "-q")
    remote = url or f"https://github.com/{repo}.git"
    _git(dest, token, "remote", "add", "origin", remote)
    _git(
        dest,
        token,
        "fetch",
        "-q",
        "--depth",
        "200",
        "origin",
        f"+refs/heads/{base_branch}:refs/remotes/origin/{base_branch}",
        sha,
    )
    _git(dest, token, "checkout", "-q", "--detach", sha)
    return dest


def base_sha(dest: Path, base_branch: str) -> str:
    return _git(dest, None, "rev-parse", f"origin/{base_branch}").strip()
