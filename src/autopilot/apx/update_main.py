"""Entry point for the updater: `python -m autopilot.apx.update_main` (docs/apx-updater-design.md, step 3b).

Runs as the `apx` account on its own timer. It must be run from a copy of this package that is NOT under `releases/`: the thing that
decides what to trust is never updated by the thing it updates. Dry-run by default; `--live` AND APX_UPDATE_LIVE=1 swap releases.
Reads the same apx.env as the daemon. Writes one line to update.json (the owner's watcher shows a problem as a local notification).
No outbound network beyond api.github.com / github.com, no other recipient.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import gitops, release, window
from .app_auth import TokenCache
from .daemon import Settings, routed_api, single_instance
from .github import make_api
from .redact import redact
from .runas import Launcher
from .status import DEFAULT_STATUS, DEFAULT_UPDATE_STATUS, write_status
from .update import run_update

REPO = "RyanJHamby/autopilot"
SETTLE_MIN = 45  # a swap needs the canary's 30 minutes plus margin inside the active window
CHECKS = ("apx / guard", "apx / build")  # the shadow names autopilot gets from apx; Actions' own checks are not trusted here


def make_stage(token: str):
    def stage(releases: Path, sha: str) -> None:
        gitops.checkout_pr(REPO, sha, "main", releases / sha, token, root=releases)

    return stage


def make_run_tests(launcher: Launcher, python: str, home: str):
    """The new tree's own suite, run as the no-secrets account, with bytecode and cache writes off so the release stays untouched."""

    def run_tests(path: Path) -> bool:
        env = {
            "PYTHONPATH": f"{path}/src",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": home,
            "PATH": f"/opt/homebrew/bin:{home}/.local/bin:/usr/bin:/bin",
            "CI": "true",
            "LANG": "en_US.UTF-8",
        }
        try:
            p = launcher.run(
                [python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
                cwd=str(path),
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:  # noqa: BLE001 - a timeout or a missing sudo rule is a failed test run, never an update
            return False
        return p.returncode == 0

    return run_tests


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="apx updater (dry-run unless --live and APX_UPDATE_LIVE=1)")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args(argv)
    s = Settings.from_env()
    root = Path(os.environ.get("APX_RELEASES_ROOT", s.shared_dir))
    out = os.environ.get("APX_UPDATE_STATUS", DEFAULT_UPDATE_STATUS)
    live = args.live and os.environ.get("APX_UPDATE_LIVE") == "1"
    now = dt.datetime.now(dt.timezone.utc)
    if s.active_window and not s.active_window.is_open(now):
        line = window.idle_line(s.active_window)  # outside the owner's hours: no API call, no test run, no swap
    else:
        try:
            cache = TokenCache(s.app_id, s.key_path, s.installations, api_factory=make_api)
            api = routed_api(cache)
            head = api("GET", f"/repos/{REPO}/git/ref/heads/main")["object"]["sha"]  # type: ignore[index]
            try:
                status = json.loads(Path(DEFAULT_STATUS).read_text())
            except (OSError, ValueError):
                status = {}
            if live and not s.ci_user:
                line = "update failed: no CI account configured, refusing to run a new tree's tests with secrets in reach"
            elif not live:
                line = f"dry-run: would consider {head[:7]} (running {release.current(root)})"
            else:
                with single_instance(s.work_dir) as got:  # never swap under a running pass: it would mix two releases
                    line = (
                        "update: a pass is running, will try again next tick"
                        if not got
                        else run_update(
                            root,
                            api,
                            repo=REPO,
                            default_branch="main",
                            owner=s.owner,
                            required_checks=list(CHECKS),
                            candidate=head,
                            status=status,
                            can_swap=not s.active_window or window.minutes_left(s.active_window, now) >= SETTLE_MIN,
                            stage=make_stage(cache.read_token_for(REPO)),
                            run_tests=make_run_tests(
                                Launcher(s.ci_user or None), f"{s.shared_dir}/venv/bin/python", f"/Users/{s.ci_user}"
                            ),
                        )
                    )
        except Exception as e:  # noqa: BLE001 - the updater must report, not crash silently
            line = f"update failed: {type(e).__name__}"
    line = redact(line)
    write_status(out, [line], live=live)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
