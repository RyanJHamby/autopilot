"""CI/guard lane for the off-Actions executor: the same checks guard.yml runs, on owner hardware.

Ports guard.yml: the kit is fetched at a pinned 40-hex sha and verified, the guard config is read from the BASE
branch (so a PR cannot weaken the guard that judges it), and agent status is derived from the head ref name.
The result is a (ok, output) pair that the caller posts as a check run named like the ruleset context.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
AGENT_PREFIXES = ("agent/", "claude/")


class KitError(RuntimeError):
    pass


def validate_kit(kit_repo: str, kit_ref: str) -> None:
    if not SHA_RE.match(kit_ref or ""):
        raise KitError("kit_ref must be a full 40-hex commit sha")
    if not REPO_RE.match(kit_repo or ""):
        raise KitError("kit_repo must be owner/name")


def is_agent_ref(head_ref: str) -> bool:
    return head_ref.startswith(AGENT_PREFIXES)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], check=check, capture_output=True, text=True)


def fetch_kit(kit_repo: str, kit_ref: str, dest: Path, *, url: str | None = None) -> Path:
    """Shallow-fetch exactly `kit_ref` and refuse to continue unless HEAD equals it."""
    validate_kit(kit_repo, kit_ref)
    dest.mkdir(parents=True, exist_ok=True)
    _git(dest, "init", "-q")
    _git(dest, "fetch", "-q", "--depth", "1", url or f"https://github.com/{kit_repo}.git", kit_ref)
    _git(dest, "checkout", "-q", "FETCH_HEAD")
    if _git(dest, "rev-parse", "HEAD").stdout.strip() != kit_ref:
        raise KitError("kit sha mismatch")
    return dest


def run_guard(checkout: Path, kit_dir: Path, *, base: str, head: str, head_ref: str, tmp: Path) -> tuple[bool, str]:
    """Run kit guard.py over base...head in `checkout`. `base` is a ref like origin/main. Config comes from the base branch."""
    cfg = tmp / "repo.yaml"
    shown = _git(checkout, "show", f"{base}:.autopilot/repo.yaml", check=False)
    cfg.write_text(shown.stdout if shown.returncode == 0 else "")
    p = subprocess.run(
        [
            sys.executable,
            str(kit_dir / "runtime" / "guard.py"),
            "--base",
            base,
            "--head",
            head,
            "--agent",
            str(is_agent_ref(head_ref)).lower(),
            "--config",
            str(cfg),
        ],
        cwd=checkout,
        capture_output=True,
        text=True,
    )
    return p.returncode == 0, (p.stdout + p.stderr).strip()
