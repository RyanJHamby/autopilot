"""Release layout, atomic swap and canary rollback for apx's own code (docs/apx-updater-design.md, step 2). Local files only, no network.

    <root>/releases/<sha>/   one checkout per release
    <root>/current  -> releases/<sha>   what launchd runs
    <root>/previous -> releases/<old>   what a rollback returns to
    <root>/HOLD                         while present, the updater adopts nothing
    <root>/swap.json                    the last swap, for the canary

The symlink is replaced with rename(2), so a reader sees the old release or the new one, never a missing `current`.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional

SHA = re.compile(r"[0-9a-f]{7,40}")
KEEP = 3
HEALTHY_AFTER = dt.timedelta(minutes=6)  # three 2-minute passes
DEAD_AFTER = dt.timedelta(minutes=15)  # no pass at all since the swap
WATCH_FOR = dt.timedelta(
    minutes=30
)  # after this a swap is no longer judged: a later failure is not the release's fault to roll back


def _link(root: Path, name: str, target: Path) -> None:
    tmp = root / f".{name}.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(target)
    os.replace(tmp, root / name)


def _target(root: Path, name: str) -> Optional[str]:
    p = root / name
    return p.resolve().name if p.is_symlink() else None


def current(root: Path) -> Optional[str]:
    return _target(root, "current")


def release_dir(root: Path, sha: str) -> Path:
    if not SHA.fullmatch(sha):  # the sha becomes a path component: nothing but hex gets through
        raise ValueError(f"not a commit sha: {sha!r}")
    return root / "releases" / sha


def swap(root: Path, sha: str, *, now: Optional[dt.datetime] = None) -> None:
    """Point `current` at an already-staged release; remember what it replaced."""
    new = release_dir(root, sha)
    if not new.is_dir():
        raise FileNotFoundError(f"release {sha} is not staged")
    old = current(root)
    if old == sha:
        return
    if old is not None:
        _link(root, "previous", root / "releases" / old)
    _link(root, "current", new)
    at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    (root / "swap.json").write_text(json.dumps({"sha": sha, "previous": old, "at": at.isoformat()}))


def rollback(root: Path) -> str:
    """Return `current` to the release it replaced and raise HOLD so the same commit is not retried. Returns the sha now current."""
    prev = _target(root, "previous")
    if prev is None or not (root / "releases" / prev).is_dir():
        raise FileNotFoundError("no previous release to return to")
    _link(root, "current", root / "releases" / prev)
    (root / "HOLD").write_text("rolled back; remove this file to let the updater adopt commits again\n")
    return prev


def canary(root: Path, status: dict, now: dt.datetime) -> str:
    """'none' (no swap to judge, or it is older than WATCH_FOR), 'pending', 'healthy' or 'bad', from the last swap and the latest status file.

    bad: the first pass after the swap reported a problem, or no pass has finished within DEAD_AFTER.
    healthy: a pass finished at least HEALTHY_AFTER after the swap, reported ok, and ran the new code.
    This sees only the latest status, so it must be called about as often as passes run (every 2 minutes) to catch a transient failure.
    """
    try:
        sw = json.loads((root / "swap.json").read_text())
        swapped = dt.datetime.fromisoformat(sw["at"])
        sha = sw["sha"]
    except (OSError, ValueError, KeyError):
        return "none"
    if now - swapped > WATCH_FOR:
        return "none"
    try:
        ts = dt.datetime.fromisoformat(status["ts"])
    except (KeyError, ValueError, TypeError):
        ts = None
    if ts is None or ts <= swapped:
        return "bad" if now - swapped > DEAD_AFTER else "pending"
    if not status.get("ok", False):
        return "bad"
    if ts - swapped >= HEALTHY_AFTER and str(status.get("version", "")) == sha[:7]:
        return "healthy"
    return "pending"


def prune(root: Path, keep: int = KEEP) -> list[str]:
    """Delete the oldest releases beyond `keep`, never `current` or `previous`. Returns what went."""
    rel = root / "releases"
    if not rel.is_dir():
        return []
    protected = {current(root), _target(root, "previous")}
    dirs = sorted(
        (d for d in rel.iterdir() if d.is_dir() and SHA.fullmatch(d.name)), key=lambda d: d.stat().st_mtime, reverse=True
    )
    gone = []
    for d in dirs[keep:]:
        if d.name not in protected:
            shutil.rmtree(d)
            gone.append(d.name)
    return gone
