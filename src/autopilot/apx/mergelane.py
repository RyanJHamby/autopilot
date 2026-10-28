"""Merge lane: run the kit's own automerge.py (same rules as the Actions job) from apx.

Only enabled after a repo is cut over from Actions (never in shadow mode). automerge.py stays the single source of truth
for what may merge: tier-0 classes the owner opted into, all checks green, class not demoted, head sha unchanged. This
module adds only the plumbing: policy comes from the DEFAULT branch checkout, env is an allowlist plus the App token.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "TERM")


def merge_env(token: str, repo: str, owner: str, kit_repo: str, home: Path, source: dict | None = None) -> dict:
    src = os.environ if source is None else source
    env = {k: src[k] for k in ENV_ALLOW if k in src}
    env.update(
        {
            "HOME": str(home),
            "GH_TOKEN": token,
            "GH_REPO": repo,  # makes gh expand {owner}/{repo} without a configured remote
            "GITHUB_REPOSITORY_OWNER": owner,
            "KIT_REPO": kit_repo,
        }
    )
    return env


def run_automerge(
    checkout: Path,
    kit_dir: Path,
    *,
    repo: str,
    pr: int,
    head_sha: str,
    token: str,
    owner: str,
    kit_repo: str,
    base: str,
    tmp: Path,
    dry_run: bool = False,
) -> tuple[int, str]:
    """checkout = clean checkout of the default branch with `base` (e.g. origin/main) present. Returns (rc, output)."""
    policy = checkout / ".autopilot" / "merge-policy.yaml"
    if not policy.exists():
        return 0, "no merge-policy; nothing to do"
    copy = tmp / "merge-policy.yaml"
    copy.write_text(policy.read_text())
    argv = [
        sys.executable,
        str(kit_dir / "runtime" / "automerge.py"),
        "--pr",
        str(int(pr)),
        "--head-sha",
        head_sha,
        "--policy",
        str(copy),
        "--base",
        base,
    ] + (["--dry-run"] if dry_run else [])
    p = subprocess.run(
        argv, cwd=checkout, env=merge_env(token, repo, owner, kit_repo, tmp), capture_output=True, text=True, timeout=300
    )
    return p.returncode, (p.stdout + p.stderr).strip()[-2000:]
