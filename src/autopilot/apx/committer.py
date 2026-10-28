"""Trusted committer: turns an already-checked worktree into a branch + PR through the git data API.

No model runs here. Commits are created WITHOUT author/committer so GitHub attributes them to the App and signs them
(to be confirmed by the live spike; if they show Unverified, fall back to a registered signing key). The runner never
sees the token that this uses.
"""

from __future__ import annotations

import base64
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .github import Api

OK_MODES = {"100644", "100755"}


@dataclass
class FileChange:
    path: str
    mode: str
    content: bytes | None  # None = deleted


def _git(worktree: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(worktree), *args], check=True, capture_output=True).stdout


def changes_from_worktree(worktree: Path, base: str) -> list[FileChange]:
    """What changed vs `base`, read from the worktree files. Refuses symlinks/submodules (patchcheck should have already)."""
    _git(worktree, "add", "-A", "-N")
    out = _git(worktree, "diff", "--name-status", "--no-renames", "-z", base).decode()
    parts = [p for p in out.split("\0") if p]
    changes: list[FileChange] = []
    for status, path in zip(parts[0::2], parts[1::2]):
        if status.startswith("D"):
            changes.append(FileChange(path, "100644", None))
            continue
        f = worktree / path
        if f.is_symlink() or not f.is_file():
            raise ValueError(f"refusing non-regular file: {path}")
        mode = "100755" if f.stat().st_mode & 0o111 else "100644"
        if mode not in OK_MODES:
            raise ValueError(f"unsupported mode {mode}: {path}")
        changes.append(FileChange(path, mode, f.read_bytes()))
    return changes


def commit_and_pr(
    api: Api,
    repo: str,
    base_sha: str,
    branch: str,
    changes: list[FileChange],
    *,
    message: str,
    title: str,
    body: str,
    base_branch: str,
) -> dict:
    """blobs -> tree -> commit -> ref -> PR. Returns {commit, pr_number}. The ref is created only after the commit exists."""
    if not branch.startswith("agent/"):
        raise ValueError("apx only pushes agent/* branches")
    if not changes:
        raise ValueError("nothing to commit")
    base_commit = api("GET", f"/repos/{repo}/git/commits/{base_sha}")
    entries = []
    for c in changes:
        if c.content is None:
            entries.append({"path": c.path, "mode": c.mode, "type": "blob", "sha": None})
            continue
        blob = api("POST", f"/repos/{repo}/git/blobs", {"content": base64.b64encode(c.content).decode(), "encoding": "base64"})
        entries.append({"path": c.path, "mode": c.mode, "type": "blob", "sha": blob["sha"]})
    tree = api("POST", f"/repos/{repo}/git/trees", {"base_tree": base_commit["tree"]["sha"], "tree": entries})
    commit = api("POST", f"/repos/{repo}/git/commits", {"message": message, "tree": tree["sha"], "parents": [base_sha]})
    api("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    pr = api("POST", f"/repos/{repo}/pulls", {"title": title, "head": branch, "base": base_branch, "body": body})
    return {"commit": commit["sha"], "pr_number": pr["number"]}
