"""One updater pass: decide, stage, test, swap, judge the last swap (docs/apx-updater-design.md, step 3a).

Order matters and is the whole point:
  1. HOLD present  -> do nothing at all (not even a rollback: a held host stays exactly as the owner left it).
  2. last swap judged by the canary: bad -> roll back and raise HOLD; pending -> change nothing yet.
  3. update_verify says the candidate is acceptable -> stage it beside the running release, run its tests with no secrets,
     and only then swap. A failed stage or test removes the staged copy and leaves `current` untouched.
Everything with side effects is injected (`stage`, `run_tests`, `candidate`, `running`), so the order is tested without a network.
Returns one status line; a skipped update is not a problem, a failed swap or a rollback is ("failed" / "rolled back" words).
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Callable, Optional

from . import release
from .github import Api
from .update_verify import verify


def run_update(
    root: Path,
    api: Api,
    *,
    repo: str,
    default_branch: str,
    owner: str,
    required_checks: list[str],
    candidate: str,
    status: dict,
    stage: Callable[[Path, str], None],
    run_tests: Callable[[Path], bool],
    now: Optional[dt.datetime] = None,
) -> str:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    hold = root / "HOLD"
    if hold.exists():
        try:
            why = hold.read_text()
        except OSError:
            why = ""
        if "rolled back" in why:  # keep the owner's alarm up until they look at it and delete HOLD
            return "update: rolled back earlier and held; look at it, then delete HOLD"
        return "update: HOLD is set, nothing adopted"

    judged = release.canary(root, status, now)
    if judged == "bad":
        back = release.rollback(root)
        return f"update: rolled back to {back[:7]} (the new release failed its canary); HOLD set"
    if judged == "pending":
        return "update: last swap still being watched"

    running = release.current(root)
    if running is None:
        return "update: no running release recorded (first install is manual)"
    ok, why = verify(api, repo, default_branch, running, candidate, owner=owner, required_checks=required_checks, now=now)
    if not ok:
        return f"update to {candidate[:7]} skipped: {why}"

    dest = release.release_dir(root, candidate)
    try:
        if dest.exists():
            shutil.rmtree(dest)  # a leftover from an interrupted pass is never trusted
        stage(root / "releases", candidate)
        if not run_tests(dest):
            shutil.rmtree(dest, ignore_errors=True)
            return f"update to {candidate[:7]} failed: tests did not pass on the new tree; nothing swapped"
        release.swap(root, candidate, now=now)
    except Exception as e:  # noqa: BLE001 - one bad stage must not leave a half-built release behind or stop the updater
        shutil.rmtree(dest, ignore_errors=True)
        return f"update to {candidate[:7]} failed: {type(e).__name__}; nothing swapped"
    release.prune(root)
    return f"update: swapped to {candidate[:7]} (was {running[:7]}); watching it"
